"""
concurrent_sim.py - Event-driven concurrent simulation.

Boxes arrive at 1000/hour (~3.6s each) while pallets are being extracted.
Shuttles are shared resources between INPUT and OUTPUT operations.
Each shuttle tracks busy_until (timestamp when it becomes free).
"""

import heapq
import time as time_module
from collections import Counter, defaultdict
from statistics import median
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
        self.box_entered_silo_at: dict = {}
        self.box_dwell_times: List[float] = []
        self.sim_time = 0.0

        # Snapshots for dashboard visualization
        self.snapshots: List[dict] = []
        self._last_snapshot_time = -999.0
        self.trace_events: List[dict] = []
        self._event_id = 0

    # =========================================================================
    # SHUTTLE HELPERS
    # =========================================================================

    def _shuttle_move_cost(self, key, from_x, to_x):
        """Cost of moving a shuttle from from_x to to_x."""
        return HANDLING_TIME + abs(from_x - to_x)

    def _position_label(self, pos: Optional[Position]) -> str:
        if pos is None:
            return "HEAD"
        return f"A{pos.aisle}-S{pos.side}-X{pos.x}-Y{pos.y}-Z{pos.z}"

    def _record_trace_event(
        self,
        event_type: str,
        box: Box,
        key: tuple,
        start_time: float,
        end_time: float,
        box_from_x: int,
        box_to_x: int,
        shuttle_from_x: int,
        shuttle_to_x: int,
        from_position: Optional[Position],
        to_position: Optional[Position],
        reason: str,
        decision: str,
        related_box_id: Optional[str] = None,
    ):
        self._event_id += 1
        aisle, y = key
        self.trace_events.append({
            "event_id": self._event_id,
            "event_type": event_type,
            "box_id": box.box_id,
            "destination": box.destination,
            "related_box_id": related_box_id or "",
            "shuttle_id": f"A{aisle}_Y{y}",
            "aisle": aisle,
            "y": y,
            "start_time": round(start_time, 3),
            "end_time": round(end_time, 3),
            "duration": round(max(0.0, end_time - start_time), 3),
            "start_min": round(start_time / 60.0, 3),
            "end_min": round(end_time / 60.0, 3),
            "box_from_x": box_from_x,
            "box_to_x": box_to_x,
            "shuttle_from_x": shuttle_from_x,
            "shuttle_to_x": shuttle_to_x,
            "from_position": self._position_label(from_position),
            "to_position": self._position_label(to_position),
            "reason": reason,
            "decision": decision,
        })

    def register_initial_boxes(self, boxes: dict, stored_at: float = 0.0):
        """Track pre-loaded boxes as already inside the silo and expose them to playback."""
        for box_id, box in boxes.items():
            self.box_entered_silo_at[box_id] = stored_at
            pos = box.position
            if pos is None:
                continue
            key = (pos.aisle, pos.y)
            self._record_trace_event(
                event_type="INITIAL",
                box=box,
                key=key,
                start_time=stored_at,
                end_time=stored_at,
                box_from_x=pos.x,
                box_to_x=pos.x,
                shuttle_from_x=self.shuttle_x.get(key, 0),
                shuttle_to_x=self.shuttle_x.get(key, 0),
                from_position=pos,
                to_position=pos,
                reason="Box loaded from the initial CSV state.",
                decision="Initial state before live playback begins.",
            )

    def _record_box_stored(self, box: Box, stored_at: float):
        self.box_entered_silo_at[box.box_id] = stored_at

    def _record_box_retrieved(self, box: Box, retrieved_at: float):
        stored_at = self.box_entered_silo_at.pop(box.box_id, None)
        if stored_at is not None:
            self.box_dwell_times.append(max(0.0, retrieved_at - stored_at))

    def _format_duration(self, seconds: float) -> str:
        if seconds >= 3600:
            return f"{seconds / 3600:.2f}h"
        if seconds >= 60:
            return f"{seconds / 60:.1f}min"
        return f"{seconds:.1f}s"

    def _get_free_shuttles_at(self, t: float) -> List[tuple]:
        """Get all shuttle keys that are free at time t."""
        return [k for k, free_t in self.shuttle_free_at.items() if free_t <= t]

    def _execute_store(self, box: Box, pos: Position, t: float) -> float:
        """Execute a store operation. Returns completion time."""
        key = (pos.aisle, pos.y)
        cur_x = self.shuttle_x[key]
        start_time = max(t, self.shuttle_free_at[key])

        # Move to head (pick box), then to position (drop box)
        t_to_head = self._shuttle_move_cost(key, cur_x, 0)
        t_to_pos = self._shuttle_move_cost(key, 0, pos.x)
        total = t_to_head + t_to_pos

        finish_time = start_time + total
        self.shuttle_free_at[key] = finish_time
        self.shuttle_x[key] = pos.x

        self.silo.place_box(box, pos)
        self._record_box_stored(box, finish_time)
        self.boxes_stored += 1
        self._record_trace_event(
            event_type="STORE",
            box=box,
            key=key,
            start_time=start_time,
            end_time=finish_time,
            box_from_x=0,
            box_to_x=pos.x,
            shuttle_from_x=cur_x,
            shuttle_to_x=pos.x,
            from_position=None,
            to_position=pos,
            reason=(
                "The active storage heuristic selected this slot using shuttle availability, "
                "travel cost, and destination grouping."
            ),
            decision="The box enters from HEAD and is stored in the best free slot available now.",
        )
        return finish_time

    def _execute_retrieve(self, box: Box, t: float) -> float:
        """Execute a retrieve operation. Returns completion time."""
        pos = box.position
        key = (pos.aisle, pos.y)
        cur_x = self.shuttle_x[key]
        total = 0.0
        time_cursor = max(t, self.shuttle_free_at[key])

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
                        event_start = time_cursor
                        event_end = time_cursor + t_pick + t_drop
                        total += t_pick + t_drop
                        self.silo.remove_box(blocking_box.box_id)
                        pallet.retrieved.append(blocking_box)
                        blocking_box.position = None
                        self._record_box_retrieved(blocking_box, event_end)
                        self.boxes_retrieved += 1
                        self._record_trace_event(
                            event_type="RETRIEVE_BLOCKER",
                            box=blocking_box,
                            key=key,
                            start_time=event_start,
                            end_time=event_end,
                            box_from_x=pos.x,
                            box_to_x=0,
                            shuttle_from_x=cur_x,
                            shuttle_to_x=0,
                            from_position=Position(pos.aisle, pos.side, pos.x, pos.y, 1),
                            to_position=None,
                            reason=(
                                "The target box was behind a front box that also belonged to an active pallet."
                            ),
                            decision="The blocking box was sent directly to output instead of being relocated.",
                            related_box_id=box.box_id,
                        )
                        cur_x = 0
                        time_cursor = event_end
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
                        event_start = time_cursor
                        event_end = time_cursor + t_pick + t_drop
                        total += t_pick + t_drop
                        from_position = Position(pos.aisle, pos.side, pos.x, pos.y, 1)
                        self.silo.remove_box(blocking_box.box_id)
                        self.silo.place_box(blocking_box, nearest)
                        self._record_trace_event(
                            event_type="RELOCATE",
                            box=blocking_box,
                            key=key,
                            start_time=event_start,
                            end_time=event_end,
                            box_from_x=pos.x,
                            box_to_x=nearest.x,
                            shuttle_from_x=cur_x,
                            shuttle_to_x=nearest.x,
                            from_position=from_position,
                            to_position=nearest,
                            reason="The target box was blocked and needed a clear path for retrieval.",
                            decision="The front box was relocated to the nearest available slot.",
                            related_box_id=box.box_id,
                        )
                        cur_x = nearest.x
                        time_cursor = event_end

        # Pick target box and bring to head
        t_to_box = self._shuttle_move_cost(key, cur_x, pos.x)
        t_to_head = self._shuttle_move_cost(key, pos.x, 0)
        event_start = time_cursor
        event_end = time_cursor + t_to_box + t_to_head
        total += t_to_box + t_to_head

        finish_time = event_end
        self.shuttle_free_at[key] = finish_time
        self.shuttle_x[key] = 0

        self.silo.remove_box(box.box_id)
        box.position = None
        self._record_box_retrieved(box, finish_time)
        self.boxes_retrieved += 1
        self._record_trace_event(
            event_type="RETRIEVE",
            box=box,
            key=key,
            start_time=event_start,
            end_time=event_end,
            box_from_x=pos.x,
            box_to_x=0,
            shuttle_from_x=cur_x,
            shuttle_to_x=0,
            from_position=pos,
            to_position=None,
            reason=(
                "The active retrieval logic prioritized this box using shuttle cost, "
                "pallet urgency, and blocking penalties."
            ),
            decision="The box was retrieved to HEAD because it was an efficient active pallet candidate.",
        )
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
                
                # Only evaluate shuttles that are currently free
                if self.shuttle_free_at[key] > t:
                    continue
                    
                available = self.silo.get_available_positions_for_shuttle(aisle, y)
                if not available:
                    continue

                pos = min(available, key=lambda p: (p.x, p.z))
                cur_x = self.shuttle_x[key]

                # Time cost (wait is 0 because we already filtered busy shuttles)
                cycle = self._shuttle_move_cost(key, cur_x, 0) + \
                        self._shuttle_move_cost(key, 0, pos.x)

                # Scoring
                z_pen = 0 if pos.z == 1 else 15
                group_bonus = -min(dest_per_aisle.get(aisle, 0) * 2, 10)
                score = cycle + z_pen + pos.x * 0.3 + group_bonus

                if score < best_score:
                    best_score = score
                    best = pos

        return best

    # =========================================================================
    # PALLET MANAGEMENT
    def _update_pallets(self, lookahead_threshold: int = BOXES_PER_PALLET):
        """
        [B] Fill active pallet slots with lookahead.
        Uses a dynamic threshold: activates pallets with >= lookahead_threshold boxes
        instead of always waiting for the full BOXES_PER_PALLET.
        This lets the system start extracting earlier when boxes are accumulating.
        """
        still_active = []
        for p in self.active_pallets:
            # Top up boxes if the pallet was created with lookahead (<12 boxes)
            if len(p.boxes) < BOXES_PER_PALLET:
                all_ids = list(self.silo.get_boxes_for_destination(p.destination))
                current_ids = {b.box_id for b in p.boxes}
                for bid in all_ids:
                    if bid not in current_ids and bid in self.all_boxes:
                        p.boxes.append(self.all_boxes[bid])
                        if len(p.boxes) == BOXES_PER_PALLET:
                            break

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

        # [B] Dynamic threshold: if we have many free slots, be more aggressive
        threshold = lookahead_threshold
        eligible = [d for d in self.silo.get_destinations_with_enough_boxes(threshold)
                    if d not in active_dests]

        if not eligible:
            return

        # Score: prefer destinations with most boxes (closer to a full pallet)
        # and lowest average retrieval distance
        scored = []
        for dest in eligible:
            all_ids = list(self.silo.get_boxes_for_destination(dest))
            count = len(all_ids)
            ids = all_ids[:BOXES_PER_PALLET]
            cost = 0
            for bid in ids:
                p = self.silo.get_box_position(bid)
                if p:
                    cost += HANDLING_TIME + p.x + HANDLING_TIME + p.x
                    if self.silo.is_blocked(p):
                        cost += 40
            # Penalize destinations with fewer boxes (prefer those closest to 12)
            fullness_bonus = -(count * 5)  # more boxes = lower cost = higher priority
            scored.append((dest, cost + fullness_bonus, ids))
        scored.sort(key=lambda x: x[1])

        for dest, _, ids in scored[:slots]:
            boxes = [self.all_boxes[bid] for bid in ids if bid in self.all_boxes]
            if boxes:
                self.active_pallets.append(Pallet(destination=dest, boxes=boxes, reserved=True))

    def _assign_all_retrievals(self, t: float) -> int:
        """
        [A+C] Multi-shuttle parallel retrieval with round-robin by aisle.

        Instead of picking a single best box globally, this method:
        1. Groups pending boxes by (aisle, y) shuttle key
        2. Picks the best candidate per shuttle (that is free at time t)
        3. Assigns retrievals to ALL free shuttles simultaneously

        Returns the number of retrievals assigned.
        """
        # Build candidate map: shuttle_key -> list of (cost, box, pallet)
        candidates: dict = defaultdict(list)
        assigned_boxes: set = set()  # avoid assigning same box twice

        for pallet in self.active_pallets:
            for box in pallet.boxes:
                if box in pallet.retrieved or box.position is None:
                    continue
                if id(box) in assigned_boxes:
                    continue
                pos = box.position
                key = (pos.aisle, pos.y)

                # Only consider free shuttles
                if self.shuttle_free_at[key] > t:
                    continue

                cur_x = self.shuttle_x[key]
                cost = (self._shuttle_move_cost(key, cur_x, pos.x) +
                        self._shuttle_move_cost(key, pos.x, 0))
                if self.silo.is_blocked(pos):
                    cost += 40
                candidates[key].append((cost, box, pallet))

        if not candidates:
            return 0

        # [C] Round-robin by aisle: pick best candidate per free shuttle
        # Sort each shuttle's candidates by cost
        assigned_keys: set = set()
        total_assigned = 0

        for key, cands in candidates.items():
            if key in assigned_keys:
                continue
            cands.sort(key=lambda x: x[0])
            _, box, pallet = cands[0]
            self._execute_retrieve(box, t)
            pallet.retrieved.append(box)
            assigned_keys.add(key)
            assigned_boxes.add(id(box))
            total_assigned += 1

        return total_assigned

    def _pick_best_retrieval(self, t: float) -> Optional[Tuple[Box, 'Pallet']]:
        """Pick the cheapest box to retrieve across all active pallets (single pick)."""
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

            # [B] Lookahead threshold: 8 when many slots free, else 12
            lookahead = 8 if (MAX_ACTIVE_PALLETS - len(self.active_pallets)) >= 4 else BOXES_PER_PALLET
            self._update_pallets(lookahead_threshold=lookahead)

            # [A+C+D] Assign tasks to ALL free shuttles — output and input in parallel
            actions_taken = True
            while actions_taken:
                actions_taken = False

                # [A+C] Assign retrievals to ALL free shuttles simultaneously
                self._update_pallets(lookahead_threshold=lookahead)
                if self.active_pallets:
                    n = self._assign_all_retrievals(self.sim_time)
                    if n > 0:
                        actions_taken = True

                # Store pending input boxes (all free shuttles not already busy)
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
        result['trace_events'] = self.trace_events
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
        avg_dwell = (sum(self.box_dwell_times) / len(self.box_dwell_times)
                     if self.box_dwell_times else 0.0)
        median_dwell = median(self.box_dwell_times) if self.box_dwell_times else 0.0

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
            'avg_time_in_silo_sec': avg_dwell,
            'median_time_in_silo_sec': median_dwell,
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
        effective_hours = self.sim_time / 3600 if self.sim_time > 0 else 0
        pallets_per_hour = pallets_done / effective_hours if effective_hours > 0 else 0
        boxes_per_hour = self.boxes_retrieved / effective_hours if effective_hours > 0 else 0
        avg_dwell = (sum(self.box_dwell_times) / len(self.box_dwell_times)
                     if self.box_dwell_times else 0.0)
        median_dwell = median(self.box_dwell_times) if self.box_dwell_times else 0.0

        return {
            "sim_time": self.sim_time,
            "boxes_arrived": len(incoming_boxes),
            "boxes_stored": self.boxes_stored,
            "boxes_retrieved": self.boxes_retrieved,
            "boxes_pending_input": len(pending_input),
            "pallets_completed": pallets_done,
            "pallets_per_hour": f"{pallets_per_hour:.1f}",
            "boxes_per_hour": f"{boxes_per_hour:.0f}",
            "full_pallet_pct": f"{(pallets_done * 12 / max(self.boxes_stored,1)) * 100:.1f}%",
            "avg_time_per_pallet": f"{avg_per_pallet:.1f}s",
            "avg_time_in_silo": self._format_duration(avg_dwell) if self.box_dwell_times else "N/A",
            "avg_time_in_silo_sec": avg_dwell,
            "median_time_in_silo": self._format_duration(median_dwell) if self.box_dwell_times else "N/A",
            "median_time_in_silo_sec": median_dwell,
            "boxes_with_time_in_silo": len(self.box_dwell_times),
            "total_relocations": self.total_relocations,
            "remaining_in_silo": remaining,
            "silo_occupancy": f"{self.silo.occupancy_rate:.1%}",
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
    manager.register_initial_boxes(all_boxes)

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


def run_continuous(csv_path: str, duration_hours: float = 8.0,
                   num_destinations: int = 20,
                   arrival_rate: int = BOX_ARRIVAL_RATE,
                   seed: int = 42,
                   verbose: bool = True,
                   algo_mode: str = "Optimized") -> dict:
    """
    CONTINUOUS FLOW simulation — the real operational scenario.

    Boxes arrive at `arrival_rate` per hour, NON-STOP, for `duration_hours`.
    The system must maintain equilibrium: extract pallets fast enough that
    the silo never fills up. If occupancy hits ~90%, the system is failing.

    Unlike run_concurrent_from_csv (fixed N boxes), here:
      - Boxes are generated ON-THE-FLY as sim_time advances
      - The loop runs until sim_time >= duration_seconds
      - Final output phase drains any remaining full pallets after cutoff

    Args:
        csv_path: CSV file with initial silo state.
        duration_hours: How many hours to simulate (default 8h = one shift).
        num_destinations: How many destinations to use.
        arrival_rate: Boxes per hour (default 1000).
        seed: Random seed for reproducibility.
        verbose: Print progress.

    Returns:
        Metrics dict including snapshots for dashboard.
    """
    import random
    random.seed(seed)

    interval = 3600.0 / arrival_rate  # seconds between boxes
    duration_secs = duration_hours * 3600.0
    total_expected = int(duration_hours * arrival_rate)

    if verbose:
        print(f"\n{'='*70}")
        print(f"  CONTINUOUS FLOW — REAL SCENARIO")
        print(f"  Initial state: {csv_path}")
        print(f"  Duration: {duration_hours:.1f}h ({duration_secs:.0f}s)")
        print(f"  Arrival rate: {arrival_rate} boxes/hour ({interval:.1f}s interval)")
        print(f"  Expected total boxes: ~{total_expected:,}")
        print(f"  Silo capacity: 7,680 slots")
        print(f"  CRITICAL: system must stay in equilibrium!")
        print(f"{'='*70}")

    # ── Initialize ────────────────────────────────────────────────────────────
    silo = Silo()
    shuttle_mgr = ShuttleManager()
    manager = ConcurrentManager(silo, shuttle_mgr)

    if verbose:
        print(f"\n--- Loading initial silo state ---")

    result = load_silo_from_csv(csv_path, silo)
    all_boxes = result["all_boxes"]
    stats = result["stats"]
    manager.all_boxes.update(all_boxes)
    manager.boxes_stored = stats["loaded"]
    manager.register_initial_boxes(all_boxes)
    existing_dests = list(set(b.destination for b in all_boxes.values()))

    if verbose:
        print(f"  Pre-loaded: {stats['loaded']} boxes ({silo.occupancy_rate:.1%} occupancy)")
        print(f"  Available destinations: {len(existing_dests)}")

    source = "3055769"
    box_counter = 0           # sequential counter for box IDs
    next_arrival_time = 0.0   # next box arrival in sim-seconds
    pending_input: List[Box] = []

    # State tracking
    sim_time = 0.0
    last_snapshot = -999.0
    last_print = -1
    tick = 0
    start_real = time_module.time()

    # Overload tracking
    overload_events: List[dict] = []
    peak_occupancy = silo.occupancy_rate

    # ── Main Loop ─────────────────────────────────────────────────────────────
    # Phase 1: Run until duration is reached (continuous input)
    input_active = True

    while True:
        # Determine next event time
        candidates = []
        if input_active and next_arrival_time <= duration_secs:
            candidates.append(next_arrival_time)

        busy = [ft for ft in manager.shuttle_free_at.values() if ft > sim_time]
        if busy:
            candidates.append(min(busy))

        if not candidates:
            # No more arrivals and no busy shuttles
            if not pending_input and not manager.active_pallets:
                break
            candidates.append(sim_time + 0.1)

        sim_time = min(candidates)
        manager.sim_time = sim_time

        # Stop generating new boxes once duration is reached
        if sim_time > duration_secs:
            input_active = False

        # Generate all boxes that have arrived up to sim_time
        if input_active:
            while next_arrival_time <= sim_time and next_arrival_time <= duration_secs:
                dest = random.choice(existing_dests[:num_destinations])
                box_id = f"{source}{dest}{box_counter:05d}"
                box = Box.from_id(box_id)
                manager.all_boxes[box_id] = box
                pending_input.append(box)
                box_counter += 1
                next_arrival_time += interval

        occupancy = silo.occupancy_rate
        peak_occupancy = max(peak_occupancy, occupancy)

        # Overload alert
        if occupancy > 0.85:
            overload_events.append({'time': sim_time, 'occupancy': occupancy})

        # Strategy Selection
        if algo_mode == "Naive":
            lookahead = BOXES_PER_PALLET # Strict 12, no lookahead
            allow_output = (occupancy > 0.50) or not input_active
        else:
            # [B] Dynamic lookahead: aggressive when many pallet slots free
            lookahead = 8 if (MAX_ACTIVE_PALLETS - len(manager.active_pallets)) >= 4 else BOXES_PER_PALLET
            allow_output = True

        manager._update_pallets(lookahead_threshold=lookahead)

        actions_taken = True
        while actions_taken:
            actions_taken = False

            manager._update_pallets(lookahead_threshold=lookahead)
            
            if allow_output and manager.active_pallets:
                if algo_mode == "Naive":
                    # Simulate sequential constraint: assign max 1 retrieval per tick
                    for p in manager.active_pallets:
                        for b in p.boxes:
                            if b not in p.retrieved and b.position:
                                if manager.shuttle_free_at[(b.position.aisle, b.position.y)] <= sim_time:
                                    manager._execute_retrieve(b, sim_time)
                                    actions_taken = True
                                    break
                        if actions_taken: break
                else:
                    # [A+C] Assign retrievals to ALL free shuttles in parallel
                    n = manager._assign_all_retrievals(sim_time)
                    if n > 0:
                        actions_taken = True

            # Store pending input boxes on remaining free shuttles
            stored_boxes = []
            for box in pending_input:
                pos = manager._find_best_store_position(box, sim_time)
                if pos:
                    key = (pos.aisle, pos.y)
                    if manager.shuttle_free_at[key] <= sim_time:
                        manager._execute_store(box, pos, sim_time)
                        stored_boxes.append(box)
                        actions_taken = True
            for b in stored_boxes:
                pending_input.remove(b)

        # Snapshot every 60 sim-seconds (more granular for continuous mode)
        if sim_time - last_snapshot >= 60:
            manager._take_snapshot(pending_input)
            last_snapshot = sim_time

        # Progress every 30 min of sim time
        if verbose:
            elapsed_min = int(sim_time / 60)
            if elapsed_min > last_print and elapsed_min % 30 == 0:
                last_print = elapsed_min
                phase = "INPUT+OUTPUT" if input_active else "OUTPUT DRAIN"
                warn = " [!OVERLOAD!]" if occupancy > 0.85 else ""
                print(f"  t={sim_time:>7.0f}s ({elapsed_min:>4}min) [{phase}] | "
                      f"arrived={box_counter:>5} stored={manager.boxes_stored:>5} "
                      f"pending={len(pending_input):>3} "
                      f"pallets={len(manager.completed_pallets):>4} "
                      f"occ={occupancy:.1%}{warn}")

        # Termination check (post-duration drain)
        if not input_active:
            no_pending = len(pending_input) == 0
            no_active = len(manager.active_pallets) == 0
            no_eligible = len(silo.get_destinations_with_enough_boxes(12)) == 0
            all_free = all(ft <= sim_time for ft in manager.shuttle_free_at.values())
            if no_pending and no_active and no_eligible and all_free:
                break

        # Advance time if stuck
        if not actions_taken:
            next_events = []
            if input_active and next_arrival_time <= duration_secs:
                next_events.append(next_arrival_time)
            busy = [ft for ft in manager.shuttle_free_at.values() if ft > sim_time]
            if busy:
                next_events.append(min(busy))
            if next_events:
                sim_time = min(next_events)
                manager.sim_time = sim_time
            else:
                break

        tick += 1
        if tick > 2_000_000:
            if verbose:
                print("  WARNING: Safety break at 2M ticks")
            break

    real_elapsed = time_module.time() - start_real
    manager._update_pallets()
    manager._take_snapshot(pending_input)

    # ── Final Metrics ─────────────────────────────────────────────────────────
    pallets_done = len(manager.completed_pallets)
    shuttle_times = list(manager.shuttle_free_at.values())
    max_stime = max(shuttle_times)
    avg_stime = sum(shuttle_times) / len(shuttle_times)
    avg_dwell = (sum(manager.box_dwell_times) / len(manager.box_dwell_times)
                 if manager.box_dwell_times else 0.0)
    median_dwell = median(manager.box_dwell_times) if manager.box_dwell_times else 0.0

    # Throughput rate
    effective_hours = sim_time / 3600
    pallets_per_hour = pallets_done / effective_hours if effective_hours > 0 else 0
    boxes_per_hour_out = manager.boxes_retrieved / effective_hours if effective_hours > 0 else 0

    metrics = {
        "mode": "continuous",
        "duration_hours": duration_hours,
        "sim_time_hours": f"{sim_time/3600:.2f}h",
        "boxes_arrived": box_counter,
        "boxes_generated": box_counter,
        "boxes_stored": manager.boxes_stored,
        "boxes_retrieved": manager.boxes_retrieved,
        "boxes_pending_final": len(pending_input),
        "pallets_completed": pallets_done,
        "pallets_per_hour": f"{pallets_per_hour:.1f}",
        "boxes_per_hour": f"{boxes_per_hour_out:.0f}",
        "boxes_out_per_hour": f"{boxes_per_hour_out:.0f}",
        "full_pallet_pct": f"{(pallets_done * 12 / max(manager.boxes_stored, 1)) * 100:.1f}%",
        "avg_time_per_pallet": f"{max_stime / pallets_done:.1f}s" if pallets_done else "N/A",
        "avg_time_in_silo": manager._format_duration(avg_dwell) if manager.box_dwell_times else "N/A",
        "avg_time_in_silo_sec": avg_dwell,
        "median_time_in_silo": manager._format_duration(median_dwell) if manager.box_dwell_times else "N/A",
        "median_time_in_silo_sec": median_dwell,
        "boxes_with_time_in_silo": len(manager.box_dwell_times),
        "total_relocations": manager.total_relocations,
        "peak_occupancy": f"{peak_occupancy:.1%}",
        "final_occupancy": f"{silo.occupancy_rate:.1%}",
        "remaining_in_silo": silo.occupied_count,
        "overload_events": len(overload_events),
        "shuttle_avg_time": f"{avg_stime:.1f}s",
        "snapshots": manager.snapshots,
        "trace_events": manager.trace_events,
    }

    if verbose:
        print(f"\n{'='*70}")
        print(f"  CONTINUOUS SIMULATION COMPLETE")
        print(f"{'='*70}")
        print(f"  Duration simulated:    {sim_time/3600:.2f}h ({sim_time:.0f}s)")
        print(f"  Boxes generated:       {box_counter:,}")
        print(f"  Boxes stored:          {manager.boxes_stored:,}")
        print(f"  Boxes retrieved:       {manager.boxes_retrieved:,}")
        print(f"  Avg box stay:          {metrics['avg_time_in_silo']}")
        print(f"  Median box stay:       {metrics['median_time_in_silo']}")
        print(f"  Pallets completed:     {pallets_done:,}")
        print(f"  Pallets/hour:          {pallets_per_hour:.1f}")
        print(f"  Boxes out/hour:        {boxes_per_hour_out:.0f}")
        print(f"  Peak occupancy:        {peak_occupancy:.1%}")
        print(f"  Final occupancy:       {silo.occupancy_rate:.1%}")
        print(f"  Overload events (>85%):{len(overload_events)}")
        print(f"  Total relocations:     {manager.total_relocations:,}")
        print(f"  Real compute time:     {real_elapsed:.2f}s")
        if overload_events:
            print(f"\n  [!] OVERLOAD DETECTED at {len(overload_events)} moments!")
            print(f"      First at t={overload_events[0]['time']:.0f}s "
                  f"({overload_events[0]['occupancy']:.1%} occ)")
        else:
            print(f"\n  [OK] System stayed in equilibrium throughout")

    metrics["real_compute_time"] = f"{real_elapsed:.2f}s"
    return metrics
