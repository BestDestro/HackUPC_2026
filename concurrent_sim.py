"""
concurrent_sim.py - Event-driven concurrent simulation.

Boxes arrive at 1000/hour (~3.6s each) while pallets are being extracted.
Shuttles are shared resources between INPUT and OUTPUT operations.
Each shuttle tracks busy_until (timestamp when it becomes free).
"""

import heapq
import time as time_module
from collections import Counter, defaultdict
from typing import Optional, List, Tuple

from models import Position, Box, Pallet
from silo import Silo, NUM_AISLES, NUM_Y
from shuttle import ShuttleManager, HANDLING_TIME
from csv_loader import load_silo_from_csv


MAX_ACTIVE_PALLETS = 8
BOXES_PER_PALLET = 12
BOX_ARRIVAL_RATE = 1000  # boxes per hour
BOX_INTERVAL = 3600.0 / BOX_ARRIVAL_RATE  # ~3.6 seconds


class ConcurrentManager:
    """
    Event-driven manager that interleaves INPUT and OUTPUT operations.
    Each shuttle has a busy_until timestamp; tasks are only assigned
    to shuttles that are free at the current simulation time.
    """

    def __init__(self, silo: Silo, shuttle_mgr: ShuttleManager):
        self.silo = silo
        self.shuttle_mgr = shuttle_mgr

        # Shuttle availability: (aisle, y) -> time when shuttle becomes free
        self.shuttle_free_at: dict = {}
        for a in range(1, NUM_AISLES + 1):
            for y in range(1, NUM_Y + 1):
                self.shuttle_free_at[(a, y)] = 0.0

        # Shuttle current X position tracker (separate from shuttle.current_x
        # which we still use for distance, but here we track time-aware position)
        self.shuttle_x: dict = {}
        for a in range(1, NUM_AISLES + 1):
            for y in range(1, NUM_Y + 1):
                self.shuttle_x[(a, y)] = 0

        # Input queue: boxes waiting at the head to be stored
        self.input_queue: List[Tuple[float, Box]] = []  # (arrival_time, box)

        # Pallet management
        self.active_pallets: List[Pallet] = []
        self.completed_pallets: List[Pallet] = []
        self.all_boxes: dict = {}
        self.pallet_completion_times: List[float] = []

        # Metrics
        self.boxes_stored = 0
        self.boxes_retrieved = 0
        self.total_relocations = 0
        self.sim_time = 0.0

        # Snapshots for dashboard visualization
        self.snapshots: List[dict] = []
        self._last_snapshot_time = -999.0

    # =========================================================================
    # SHUTTLE HELPERS
    # =========================================================================

    def _shuttle_move_cost(self, key, from_x, to_x):
        """Cost of moving a shuttle from from_x to to_x."""
        return HANDLING_TIME + abs(from_x - to_x)

    def _get_free_shuttles_at(self, t: float) -> List[tuple]:
        """Get all shuttle keys that are free at time t."""
        return [k for k, free_t in self.shuttle_free_at.items() if free_t <= t]

    def _execute_store(self, box: Box, pos: Position, t: float) -> float:
        """Execute a store operation. Returns completion time."""
        key = (pos.aisle, pos.y)
        cur_x = self.shuttle_x[key]

        # Move to head (pick box), then to position (drop box)
        t_to_head = self._shuttle_move_cost(key, cur_x, 0)
        t_to_pos = self._shuttle_move_cost(key, 0, pos.x)
        total = t_to_head + t_to_pos

        finish_time = max(t, self.shuttle_free_at[key]) + total
        self.shuttle_free_at[key] = finish_time
        self.shuttle_x[key] = pos.x

        self.silo.place_box(box, pos)
        self.boxes_stored += 1
        return finish_time

    def _execute_retrieve(self, box: Box, t: float) -> float:
        """Execute a retrieve operation. Returns completion time."""
        pos = box.position
        key = (pos.aisle, pos.y)
        cur_x = self.shuttle_x[key]
        total = 0.0

        # Handle Z=2 blockage
        if self.silo.is_blocked(pos):
            blocking_box = self.silo.get_blocking_box(pos)
            if blocking_box:
                self.total_relocations += 1
                # Check if blocking box is needed by active pallet
                sent_to_pallet = False
                for pallet in self.active_pallets:
                    if blocking_box in pallet.boxes and blocking_box not in pallet.retrieved:
                        # Send blocking box directly to output
                        t_pick = self._shuttle_move_cost(key, cur_x, pos.x)
                        t_drop = self._shuttle_move_cost(key, pos.x, 0)
                        total += t_pick + t_drop
                        self.silo.remove_box(blocking_box.box_id)
                        pallet.retrieved.append(blocking_box)
                        blocking_box.position = None
                        self.boxes_retrieved += 1
                        cur_x = 0
                        sent_to_pallet = True
                        break

                if not sent_to_pallet:
                    # Relocate to nearest available
                    nearest = self.silo.find_nearest_available(pos.aisle, pos.y, pos.x)
                    if nearest is None:
                        for yy in range(1, NUM_Y + 1):
                            nearest = self.silo.find_nearest_available(pos.aisle, yy, pos.x)
                            if nearest:
                                break
                    if nearest:
                        t_pick = self._shuttle_move_cost(key, cur_x, pos.x)
                        t_drop = self._shuttle_move_cost(key, pos.x, nearest.x)
                        total += t_pick + t_drop
                        self.silo.remove_box(blocking_box.box_id)
                        self.silo.place_box(blocking_box, nearest)
                        cur_x = nearest.x

        # Pick target box and bring to head
        t_to_box = self._shuttle_move_cost(key, cur_x, pos.x)
        t_to_head = self._shuttle_move_cost(key, pos.x, 0)
        total += t_to_box + t_to_head

        finish_time = max(t, self.shuttle_free_at[key]) + total
        self.shuttle_free_at[key] = finish_time
        self.shuttle_x[key] = 0

        self.silo.remove_box(box.box_id)
        box.position = None
        self.boxes_retrieved += 1
        return finish_time

    # =========================================================================
    # PLACEMENT SELECTION (same as before but time-aware)
    # =========================================================================

    def _find_best_store_position(self, box: Box, t: float) -> Optional[Position]:
        """Find best position for storing a box, preferring free shuttles."""
        dest_per_aisle = defaultdict(int)
        for bid in self.silo.get_boxes_for_destination(box.destination):
            p = self.silo.get_box_position(bid)
            if p:
                dest_per_aisle[p.aisle] += 1

        best = None
        best_score = float('inf')

        for aisle in range(1, NUM_AISLES + 1):
            for y in range(1, NUM_Y + 1):
                key = (aisle, y)
                available = self.silo.get_available_positions_for_shuttle(aisle, y)
                if not available:
                    continue

                pos = min(available, key=lambda p: (p.x, p.z))
                cur_x = self.shuttle_x[key]

                # Time cost
                wait = max(0, self.shuttle_free_at[key] - t)
                cycle = self._shuttle_move_cost(key, cur_x, 0) + \
                        self._shuttle_move_cost(key, 0, pos.x)

                # Scoring
                z_pen = 0 if pos.z == 1 else 15
                group_bonus = -min(dest_per_aisle.get(aisle, 0) * 2, 10)
                score = wait + cycle + z_pen + pos.x * 0.3 + group_bonus

                if score < best_score:
                    best_score = score
                    best = pos

        return best

    # =========================================================================
    # PALLET MANAGEMENT
    # =========================================================================

    def _update_pallets(self):
        """Fill active pallet slots from eligible destinations."""
        still_active = []
        for p in self.active_pallets:
            if p.is_complete:
                self.completed_pallets.append(p)
                self.pallet_completion_times.append(self.sim_time)
            else:
                still_active.append(p)
        self.active_pallets = still_active

        slots = MAX_ACTIVE_PALLETS - len(self.active_pallets)
        if slots <= 0:
            return

        active_dests = {p.destination for p in self.active_pallets}
        eligible = [d for d in self.silo.get_destinations_with_enough_boxes(BOXES_PER_PALLET)
                    if d not in active_dests]

        # Score by retrieval cost
        scored = []
        for dest in eligible:
            ids = list(self.silo.get_boxes_for_destination(dest))[:BOXES_PER_PALLET]
            cost = 0
            for bid in ids:
                p = self.silo.get_box_position(bid)
                if p:
                    cost += HANDLING_TIME + p.x + HANDLING_TIME + p.x
                    if self.silo.is_blocked(p):
                        cost += 40
            scored.append((dest, cost))
        scored.sort(key=lambda x: x[1])

        for dest, _ in scored[:slots]:
            ids = list(self.silo.get_boxes_for_destination(dest))[:BOXES_PER_PALLET]
            boxes = [self.all_boxes[bid] for bid in ids]
            self.active_pallets.append(Pallet(destination=dest, boxes=boxes, reserved=True))

    def _pick_best_retrieval(self, t: float) -> Optional[Tuple[Box, 'Pallet']]:
        """Pick the cheapest box to retrieve across all active pallets."""
        best = None
        best_cost = float('inf')

        for pallet in self.active_pallets:
            for box in pallet.boxes:
                if box in pallet.retrieved or box.position is None:
                    continue
                pos = box.position
                key = (pos.aisle, pos.y)
                cur_x = self.shuttle_x[key]
                wait = max(0, self.shuttle_free_at[key] - t)
                cost = wait + self._shuttle_move_cost(key, cur_x, pos.x) + \
                       self._shuttle_move_cost(key, pos.x, 0)
                if self.silo.is_blocked(pos):
                    cost += 40
                if cost < best_cost:
                    best_cost = cost
                    best = (box, pallet)

        return best

    # =========================================================================
    # MAIN SIMULATION LOOP
    # =========================================================================

    def run(self, incoming_boxes: List[Box], duration_hours: float = None,
            verbose: bool = True) -> dict:
        """
        Run the concurrent simulation.

        Args:
            incoming_boxes: Boxes arriving over time (1000/hour rate).
            duration_hours: If None, run until all boxes stored and all
                           possible pallets extracted.
            verbose: Print progress.
        """
        # Schedule arrivals
        for i, box in enumerate(incoming_boxes):
            arrival = i * BOX_INTERVAL
            self.input_queue.append((arrival, box))
            self.all_boxes[box.box_id] = box

        next_arrival_idx = 0
        pending_input: List[Box] = []  # Boxes at the head waiting for storage
        tick = 0
        last_print = -1

        while True:
            # Find current simulation time = earliest possible event
            # (next arrival or earliest shuttle becoming free)
            candidates = []
            if next_arrival_idx < len(self.input_queue):
                candidates.append(self.input_queue[next_arrival_idx][0])
            free_times = [ft for ft in self.shuttle_free_at.values() if ft > self.sim_time]
            if free_times:
                candidates.append(min(free_times))
            if not candidates:
                if not pending_input and not self.active_pallets:
                    break
                candidates.append(self.sim_time + 0.1)

            self.sim_time = min(candidates) if candidates else self.sim_time

            # Absorb all arrivals up to sim_time
            while (next_arrival_idx < len(self.input_queue) and
                   self.input_queue[next_arrival_idx][0] <= self.sim_time):
                _, box = self.input_queue[next_arrival_idx]
                pending_input.append(box)
                next_arrival_idx += 1

            # Update pallets
            self._update_pallets()

            # Assign tasks to free shuttles
            actions_taken = True
            while actions_taken:
                actions_taken = False

                # Try to store pending input boxes
                stored_boxes = []
                for box in pending_input:
                    pos = self._find_best_store_position(box, self.sim_time)
                    if pos:
                        key = (pos.aisle, pos.y)
                        if self.shuttle_free_at[key] <= self.sim_time:
                            self._execute_store(box, pos, self.sim_time)
                            stored_boxes.append(box)
                            actions_taken = True
                for b in stored_boxes:
                    pending_input.remove(b)

                # Try to retrieve pallet boxes
                self._update_pallets()
                if self.active_pallets:
                    pick = self._pick_best_retrieval(self.sim_time)
                    if pick:
                        box, pallet = pick
                        pos = box.position
                        key = (pos.aisle, pos.y)
                        if self.shuttle_free_at[key] <= self.sim_time:
                            self._execute_retrieve(box, self.sim_time)
                            pallet.retrieved.append(box)
                            actions_taken = True

            # Take snapshot every ~30 sim-seconds for dashboard
            if self.sim_time - self._last_snapshot_time >= 30:
                self._take_snapshot(pending_input)
                self._last_snapshot_time = self.sim_time

            # Progress logging
            if verbose:
                elapsed_min = int(self.sim_time / 60)
                if elapsed_min > last_print and elapsed_min % 5 == 0:
                    last_print = elapsed_min
                    print(f"  t={self.sim_time:>7.0f}s ({elapsed_min}min) | "
                          f"stored={self.boxes_stored} pending={len(pending_input)} "
                          f"retrieved={self.boxes_retrieved} "
                          f"pallets={len(self.completed_pallets)} "
                          f"occupancy={self.silo.occupancy_rate:.1%}")

            # Termination check
            all_arrived = next_arrival_idx >= len(self.input_queue)
            no_pending = len(pending_input) == 0
            no_active = len(self.active_pallets) == 0
            no_eligible = len(self.silo.get_destinations_with_enough_boxes(BOXES_PER_PALLET)) == 0
            all_shuttles_free = all(ft <= self.sim_time for ft in self.shuttle_free_at.values())

            if all_arrived and no_pending and no_active and no_eligible and all_shuttles_free:
                break

            # Safety: advance time if stuck
            if not actions_taken:
                next_events = []
                if next_arrival_idx < len(self.input_queue):
                    next_events.append(self.input_queue[next_arrival_idx][0])
                busy = [ft for ft in self.shuttle_free_at.values() if ft > self.sim_time]
                if busy:
                    next_events.append(min(busy))
                if next_events:
                    self.sim_time = min(next_events)
                else:
                    break

            tick += 1
            if tick > 500000:
                if verbose:
                    print("  WARNING: Safety break at 500k ticks")
                break

        # Final pallet flush
        self._update_pallets()
        self._take_snapshot(pending_input)

        result = self._build_metrics(incoming_boxes, pending_input)
        result['snapshots'] = self.snapshots
        return result

    def _take_snapshot(self, pending_input):
        """Capture current state for dashboard visualization."""
        # Per-aisle occupancy
        aisle_occ = {}
        for a in range(1, NUM_AISLES + 1):
            count = sum(1 for pos, box in self.silo.grid.items()
                        if box is not None and pos.aisle == a)
            total = 2 * 60 * NUM_Y * 2  # sides * x * y * z
            aisle_occ[a] = count

        # Shuttle utilization: how many are busy right now
        busy_count = sum(1 for ft in self.shuttle_free_at.values() if ft > self.sim_time)

        # Per-aisle shuttle positions
        shuttle_positions = {}
        for (a, y), x in self.shuttle_x.items():
            shuttle_positions[f'A{a}_Y{y}'] = x

        self.snapshots.append({
            'time': self.sim_time,
            'time_min': self.sim_time / 60.0,
            'boxes_stored': self.boxes_stored,
            'boxes_retrieved': self.boxes_retrieved,
            'pending_input': len(pending_input),
            'pallets_completed': len(self.completed_pallets),
            'active_pallets': len(self.active_pallets),
            'occupancy': self.silo.occupied_count,
            'occupancy_pct': self.silo.occupancy_rate * 100,
            'relocations': self.total_relocations,
            'shuttles_busy': busy_count,
            'shuttles_idle': 32 - busy_count,
            'aisle_1': aisle_occ.get(1, 0),
            'aisle_2': aisle_occ.get(2, 0),
            'aisle_3': aisle_occ.get(3, 0),
            'aisle_4': aisle_occ.get(4, 0),
        })

    def _build_metrics(self, incoming_boxes, pending_input) -> dict:
        """Build final metrics dictionary."""
        pallets_done = len(self.completed_pallets)
        remaining = self.silo.occupied_count

        shuttle_times = list(self.shuttle_free_at.values())
        max_time = max(shuttle_times)
        avg_time = sum(shuttle_times) / len(shuttle_times)

        avg_per_pallet = max_time / pallets_done if pallets_done else 0

        return {
            "sim_time": self.sim_time,
            "boxes_arrived": len(incoming_boxes),
            "boxes_stored": self.boxes_stored,
            "boxes_retrieved": self.boxes_retrieved,
            "boxes_pending_input": len(pending_input),
            "pallets_completed": pallets_done,
            "full_pallet_pct": f"{(pallets_done * 12 / max(self.boxes_stored,1)) * 100:.1f}%",
            "avg_time_per_pallet": f"{avg_per_pallet:.1f}s",
            "total_relocations": self.total_relocations,
            "remaining_in_silo": remaining,
            "silo_occupancy": f"{self.silo.occupancy_rate:.1%}",
            "shuttle_max_time": f"{max_time:.1f}s",
            "shuttle_avg_time": f"{avg_time:.1f}s",
        }


def run_concurrent_from_csv(csv_path: str, num_incoming: int = 1000,
                            num_destinations: int = 20,
                            verbose: bool = True) -> dict:
    """
    Run concurrent simulation:
    1. Load initial silo from CSV.
    2. Generate incoming boxes (arriving at 1000/hr).
    3. Simultaneously store incoming + extract pallets.
    """
    import random
    random.seed(42)

    if verbose:
        print(f"\n{'='*70}")
        print(f"  CONCURRENT SCENARIO")
        print(f"  Initial state: {csv_path}")
        print(f"  Incoming boxes: {num_incoming} at {BOX_ARRIVAL_RATE}/hour")
        print(f"  Destinations: {num_destinations}")
        print(f"{'='*70}")

    # Initialize
    silo = Silo()
    shuttle_mgr = ShuttleManager()
    manager = ConcurrentManager(silo, shuttle_mgr)

    # Load CSV
    if verbose:
        print(f"\n--- Loading initial silo state ---")
    result = load_silo_from_csv(csv_path, silo)
    all_boxes = result["all_boxes"]
    stats = result["stats"]

    # Register pre-loaded boxes
    manager.all_boxes.update(all_boxes)
    manager.boxes_stored = stats["loaded"]

    if verbose:
        print(f"  Pre-loaded: {stats['loaded']} boxes ({silo.occupancy_rate:.1%} occupancy)")
        ready = silo.get_destinations_with_enough_boxes(12)
        print(f"  Destinations ready: {len(ready)}")

    # Get existing destinations from silo
    existing_dests = list(set(b.destination for b in all_boxes.values()))

    # Generate incoming boxes using the same destinations
    if verbose:
        print(f"\n--- Generating {num_incoming} incoming boxes ---")

    incoming = []
    source = "3055769"
    for i in range(num_incoming):
        dest = random.choice(existing_dests[:num_destinations])
        bulk = 90000 + i
        box_id = f"{source}{dest}{bulk:05d}"
        incoming.append(Box.from_id(box_id))

    # Run concurrent simulation
    if verbose:
        print(f"\n--- Running concurrent simulation ---")
        print(f"  Box arrival interval: {BOX_INTERVAL:.1f}s")
        total_time_est = num_incoming * BOX_INTERVAL
        print(f"  Estimated arrival span: {total_time_est:.0f}s ({total_time_est/60:.1f}min)")

    start_real = time_module.time()
    metrics = manager.run(incoming, verbose=verbose)
    real_time = time_module.time() - start_real

    if verbose:
        print(f"\n--- FINAL CONCURRENT METRICS ---")
        for k, v in metrics.items():
            label = k.replace('_', ' ').title()
            print(f"  {label:<25} {v}")
        print(f"  {'Real Compute Time':<25} {real_time:.2f}s")

    metrics["real_compute_time"] = f"{real_time:.2f}s"
    return metrics
