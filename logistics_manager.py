"""
logistics_manager.py - The algorithmic brain of the system.

Implements:
  - Input Algorithm: Chaotic storage with greedy shuttle-aware placement.
  - Output Algorithm: Greedy extraction with dynamic pallet priority.
  - Z-Constraint Relocation: Smart handling of blocked Z=2 boxes.
  - Pallet Management: 8 active pallet slots with cache eviction.
"""

import random
from typing import Optional, List, Tuple, Set
from collections import defaultdict

from models import Position, Box, Task, Pallet
from silo import Silo, NUM_AISLES, NUM_Y
from shuttle import Shuttle, ShuttleManager, HANDLING_TIME


MAX_ACTIVE_PALLETS = 8  # 2 robots × 4 pallets each
BOXES_PER_PALLET = 12


class LogisticsManager:
    """
    The central decision-making engine.
    Orchestrates box input, output, shuttle assignments, and pallet formation.
    """

    def __init__(self, silo: Silo, shuttle_manager: ShuttleManager):
        self.silo = silo
        self.shuttle_manager = shuttle_manager

        # Pallet management
        self.active_pallets: List[Pallet] = []          # Currently being extracted (max 8)
        self.completed_pallets: List[Pallet] = []       # Fully shipped
        self.all_boxes: dict = {}                        # box_id -> Box (master registry)

        # Metrics
        self.total_input_time: float = 0.0
        self.total_output_time: float = 0.0
        self.total_relocations: int = 0
        self.boxes_stored: int = 0
        self.boxes_retrieved: int = 0

    # =========================================================================
    # INPUT ALGORITHM - Chaotic Storage + Greedy Placement
    # =========================================================================

    def store_box(self, box: Box) -> Tuple[Optional[Position], float]:
        """
        Store an incoming box into the silo using chaotic storage with
        greedy shuttle-aware placement.

        Optimized Strategy:
          1. For each of the 32 shuttles, find the nearest available position.
          2. Score each shuttle's best candidate (not all 7680 positions).
          3. Pick the best (shuttle, position) pair.

        Returns: (chosen_position, time_cost) or (None, 0) if silo is full.
        """
        self.all_boxes[box.box_id] = box

        # Pre-compute destination grouping counts per aisle (O(D) once, not per candidate)
        dest_per_aisle = defaultdict(int)
        for bid in self.silo.get_boxes_for_destination(box.destination):
            pos = self.silo.get_box_position(bid)
            if pos:
                dest_per_aisle[pos.aisle] += 1

        # For each shuttle, find its best available position
        shuttle_candidates = []
        for aisle in range(1, NUM_AISLES + 1):
            for y in range(1, NUM_Y + 1):
                shuttle = self.shuttle_manager.get_shuttle(aisle, y)
                available = self.silo.get_available_positions_for_shuttle(aisle, y)
                if not available:
                    continue

                # Find the best position for this shuttle: nearest to head, prefer Z=1
                best_pos = min(available, key=lambda p: (p.x, p.z))

                # Score this (shuttle, position) pair
                cycle_time = shuttle.estimate_store_cycle(best_pos.x)
                load_penalty = shuttle.current_time * 0.1
                z_penalty = 0 if best_pos.z == 1 else 15
                proximity_bonus = best_pos.x * 0.3
                grouping_bonus = -min(dest_per_aisle.get(aisle, 0) * 2, 10)

                score = cycle_time + load_penalty + z_penalty + proximity_bonus + grouping_bonus
                shuttle_candidates.append((shuttle, best_pos, score))

        if not shuttle_candidates:
            return None, 0.0  # Silo is full

        # Pick the best candidate
        _, best_pos, _ = min(shuttle_candidates, key=lambda c: c[2])
        shuttle = self.shuttle_manager.get_shuttle(best_pos.aisle, best_pos.y)

        # Execute the store cycle
        # Step 1: Shuttle moves to head (X=0) to pick up the box
        time_cost = shuttle.move_to_head()
        shuttle.carried_box = box

        # Step 2: Shuttle moves to the target position to drop the box
        time_cost += shuttle.move_to(best_pos.x)
        shuttle.carried_box = None
        shuttle.total_tasks_completed += 1

        # Place box in silo
        success = self.silo.place_box(box, best_pos)
        if not success:
            # Fallback: shouldn't happen, but handle gracefully
            return None, time_cost

        self.boxes_stored += 1
        self.total_input_time += time_cost
        return best_pos, time_cost

    # =========================================================================
    # OUTPUT ALGORITHM - Greedy Extraction + Dynamic Priority
    # =========================================================================

    def update_active_pallets(self):
        """
        Check if we can fill any of the 8 active pallet slots.
        Select destinations that have >= 12 boxes and minimize retrieval cost.
        """
        # Remove completed pallets from active list
        still_active = []
        for pallet in self.active_pallets:
            if pallet.is_complete:
                self.completed_pallets.append(pallet)
            else:
                still_active.append(pallet)
        self.active_pallets = still_active

        # Find destinations eligible for palletization
        available_slots = MAX_ACTIVE_PALLETS - len(self.active_pallets)
        if available_slots <= 0:
            return

        # Get destinations already being palletized
        active_destinations = {p.destination for p in self.active_pallets}

        # Find eligible destinations
        eligible = self.silo.get_destinations_with_enough_boxes(BOXES_PER_PALLET)
        eligible = [d for d in eligible if d not in active_destinations]

        if not eligible:
            return

        # Rank eligible destinations by estimated retrieval cost (greedy)
        scored = []
        for dest in eligible:
            box_ids = list(self.silo.get_boxes_for_destination(dest))[:BOXES_PER_PALLET]
            total_cost = 0
            for bid in box_ids:
                pos = self.silo.get_box_position(bid)
                if pos:
                    shuttle = self.shuttle_manager.get_shuttle(pos.aisle, pos.y)
                    total_cost += shuttle.estimate_retrieve_cycle(pos.x)
                    # Penalty for blocked boxes (Z=2 with Z=1 occupied)
                    if self.silo.is_blocked(pos):
                        total_cost += 40  # Relocation penalty estimate
            scored.append((dest, total_cost))

        # Sort by cost (cheapest first) and fill available slots
        scored.sort(key=lambda x: x[1])

        for dest, _ in scored[:available_slots]:
            box_ids = list(self.silo.get_boxes_for_destination(dest))[:BOXES_PER_PALLET]
            boxes = [self.all_boxes[bid] for bid in box_ids]
            pallet = Pallet(destination=dest, boxes=boxes, reserved=True)
            self.active_pallets.append(pallet)

    def extract_next_box(self) -> Tuple[Optional[Box], float]:
        """
        Extract the next box across all active pallets using dynamic priority.

        Strategy:
          1. Pool all boxes needed across all active pallets.
          2. For each, calculate the retrieval cost from its shuttle's current position.
          3. Pick the cheapest one (greedy with dynamic priority).
          4. Handle Z-constraint relocations if needed.

        Returns: (extracted_box, time_cost) or (None, 0) if nothing to extract.
        """
        if not self.active_pallets:
            return None, 0.0

        # Pool all boxes still needing extraction across all active pallets
        candidates = []
        for pallet in self.active_pallets:
            for box in pallet.boxes:
                if box not in pallet.retrieved and box.position is not None:
                    pos = box.position
                    shuttle = self.shuttle_manager.get_shuttle(pos.aisle, pos.y)
                    cost = shuttle.estimate_retrieve_cycle(pos.x)

                    # Check if blocked
                    blocked = self.silo.is_blocked(pos)
                    if blocked:
                        # Add relocation cost estimate
                        blocking_box = self.silo.get_blocking_box(pos)
                        if blocking_box:
                            nearest = self.silo.find_nearest_available(
                                pos.aisle, pos.y, pos.x
                            )
                            if nearest:
                                reloc_cost = (
                                    HANDLING_TIME + 0 +        # Pick Z=1 (already there)
                                    HANDLING_TIME + abs(pos.x - nearest.x) +  # Drop at nearest
                                    HANDLING_TIME + abs(nearest.x - pos.x)    # Return to pick Z=2
                                )
                                cost += reloc_cost
                            else:
                                cost += 200  # Heavy penalty: no space for relocation

                    candidates.append((box, pallet, cost, blocked))

        if not candidates:
            return None, 0.0

        # Greedy: pick the cheapest candidate
        candidates.sort(key=lambda c: c[2])
        best_box, best_pallet, _, is_blocked = candidates[0]
        pos = best_box.position
        shuttle = self.shuttle_manager.get_shuttle(pos.aisle, pos.y)
        total_time = 0.0

        # Handle relocation if blocked
        if is_blocked:
            blocking_box = self.silo.get_blocking_box(pos)
            if blocking_box:
                total_time += self._relocate_blocking_box(shuttle, pos, blocking_box)

        # Retrieve the box
        # Step 1: Move shuttle to box position
        total_time += shuttle.move_to(pos.x)
        shuttle.carried_box = best_box

        # Step 2: Remove from silo
        self.silo.remove_box(best_box.box_id)

        # Step 3: Move to head for palletization
        total_time += shuttle.move_to_head()
        shuttle.carried_box = None
        shuttle.total_tasks_completed += 1

        # Mark as retrieved
        best_pallet.retrieved.append(best_box)
        best_box.position = None
        self.boxes_retrieved += 1
        self.total_output_time += total_time

        return best_box, total_time

    def _relocate_blocking_box(self, shuttle: Shuttle, blocked_pos: Position,
                                blocking_box: Box) -> float:
        """
        Relocate the box at Z=1 that blocks access to Z=2.
        
        Optimization: if the blocking box is needed by an active pallet, 
        send it to the head instead of relocating.
        """
        time_cost = 0.0
        self.total_relocations += 1

        # Check if the blocking box is needed by any active pallet
        for pallet in self.active_pallets:
            if blocking_box in pallet.boxes and blocking_box not in pallet.retrieved:
                # Lucky! Send it directly to palletization output
                time_cost += shuttle.move_to(blocked_pos.x)
                shuttle.carried_box = blocking_box
                self.silo.remove_box(blocking_box.box_id)

                time_cost += shuttle.move_to_head()
                shuttle.carried_box = None
                shuttle.total_tasks_completed += 1

                pallet.retrieved.append(blocking_box)
                blocking_box.position = None
                self.boxes_retrieved += 1
                return time_cost

        # Normal relocation: move to nearest available slot
        nearest = self.silo.find_nearest_available(
            blocked_pos.aisle, blocked_pos.y, blocked_pos.x
        )
        if nearest is None:
            # Worst case: find ANY available slot on any shuttle level in same aisle
            for y in range(1, NUM_Y + 1):
                nearest = self.silo.find_nearest_available(
                    blocked_pos.aisle, y, blocked_pos.x
                )
                if nearest:
                    break

        if nearest is None:
            # Absolute worst case: should not happen with proper buffer management
            return 0.0

        # Pick the blocking box
        time_cost += shuttle.move_to(blocked_pos.x)
        shuttle.carried_box = blocking_box
        self.silo.remove_box(blocking_box.box_id)

        # Drop at nearest available
        time_cost += shuttle.move_to(nearest.x)
        shuttle.carried_box = None
        self.silo.place_box(blocking_box, nearest)
        shuttle.total_tasks_completed += 1

        return time_cost

    # =========================================================================
    # FULL EXTRACTION CYCLE
    # =========================================================================

    def run_extraction_cycle(self) -> dict:
        """
        Run a complete extraction cycle:
          1. Update active pallets (fill empty slots).
          2. Extract all boxes for active pallets.
          3. Repeat until no more pallets can be formed.

        Returns metrics dict.
        """
        total_time = 0.0
        extraction_count = 0

        while True:
            # Try to fill pallet slots
            self.update_active_pallets()

            if not self.active_pallets:
                break  # No more pallets to extract

            # Extract boxes until all active pallets are complete or stuck
            stuck_counter = 0
            while self.active_pallets:
                box, time = self.extract_next_box()
                if box is None:
                    stuck_counter += 1
                    if stuck_counter > 3:
                        break
                    continue
                stuck_counter = 0
                total_time += time
                extraction_count += 1

                # Check and refresh pallet slots after each extraction
                self.update_active_pallets()

        return {
            "total_extraction_time": total_time,
            "boxes_extracted": extraction_count,
            "pallets_completed": len(self.completed_pallets),
            "pallets_incomplete": len(self.active_pallets),
        }

    # =========================================================================
    # METRICS
    # =========================================================================

    def get_metrics(self) -> dict:
        """Comprehensive metrics for the simulation."""
        pallets_completed = len(self.completed_pallets)
        total_pallet_boxes = pallets_completed * BOXES_PER_PALLET

        shuttle_stats = self.shuttle_manager.get_stats()
        max_time = shuttle_stats["max_time"]

        avg_time_per_pallet = max_time / pallets_completed if pallets_completed > 0 else 0

        return {
            "boxes_stored": self.boxes_stored,
            "boxes_retrieved": self.boxes_retrieved,
            "pallets_completed": pallets_completed,
            "full_pallet_percentage": f"{(total_pallet_boxes / max(self.boxes_stored, 1)) * 100:.1f}%",
            "avg_time_per_pallet": f"{avg_time_per_pallet:.1f}s",
            "total_relocations": self.total_relocations,
            "max_shuttle_time": f"{max_time:.1f}s",
            "silo_occupancy": self.silo.get_stats()["occupancy_rate"],
            "shuttle_stats": shuttle_stats,
        }
