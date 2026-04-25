# algorithms/storage.py

from collections import Counter, defaultdict
from typing import Optional

from models import Box, Position
from silo import NUM_AISLES, NUM_Y


def _destination_aisle_counts(manager, destination: str) -> Counter:
    counts = Counter()
    for bid in manager.silo.get_boxes_for_destination(destination):
        pos = manager.silo.get_box_position(bid)
        if pos:
            counts[pos.aisle] += 1
    return counts


def _destination_lane_counts(manager, destination: str) -> Counter:
    counts = Counter()
    for bid in manager.silo.get_boxes_for_destination(destination):
        pos = manager.silo.get_box_position(bid)
        if pos:
            counts[(pos.aisle, pos.y)] += 1
    return counts


def _aisle_occupancy_counts(manager) -> Counter:
    counts = Counter()
    for pos, box in manager.silo.grid.items():
        if box is not None:
            counts[pos.aisle] += 1
    return counts


def _lane_occupancy_counts(manager) -> Counter:
    counts = Counter()
    for pos, box in manager.silo.grid.items():
        if box is not None:
            counts[(pos.aisle, pos.y)] += 1
    return counts


def _store_cycle(manager, key, pos, t):
    cur_x = manager.shuttle_x[key]
    wait = max(0, manager.shuttle_free_at[key] - t)
    return (
        wait
        + manager._shuttle_move_cost(key, cur_x, 0)
        + manager._shuttle_move_cost(key, 0, pos.x)
    )


class GreedyStorage:
    name = "greedy_storage"

    def choose_position(self, manager, box: Box, t: float) -> Optional[Position]:
        dest_per_aisle = _destination_aisle_counts(manager, box.destination)

        best = None
        best_score = float("inf")

        for aisle in range(1, NUM_AISLES + 1):
            for y in range(1, NUM_Y + 1):
                key = (aisle, y)
                available = manager.silo.get_available_positions_for_shuttle(aisle, y)

                if not available:
                    continue

                pos = min(available, key=lambda p: (p.x, p.z))
                cycle = _store_cycle(manager, key, pos, t)

                z_penalty = 0 if pos.z == 1 else 15
                grouping_bonus = -min(dest_per_aisle.get(aisle, 0) * 2, 10)

                score = cycle + z_penalty + pos.x * 0.3 + grouping_bonus

                if score < best_score:
                    best_score = score
                    best = pos

        return best


class DestinationGroupedStorage:
    name = "destination_grouped_storage"

    def choose_position(self, manager, box, t):
        dest_by_aisle = _destination_aisle_counts(manager, box.destination)

        best = None
        best_score = float("inf")

        for key, available in manager.silo.available_by_shuttle.items():
            aisle, y = key
            for pos in available:
                cycle = _store_cycle(manager, key, pos, t)

                grouping_bonus = -dest_by_aisle.get(aisle, 0) * 5
                z_penalty = 0 if pos.z == 1 else 25
                distance_penalty = pos.x * 0.2

                score = cycle + z_penalty + distance_penalty + grouping_bonus

                if score < best_score:
                    best_score = score
                    best = pos

        return best


class BalancedStorage:
    name = "balanced_storage"

    def choose_position(self, manager, box, t):
        best = None
        best_score = float("inf")

        for key, available in manager.silo.available_by_shuttle.items():
            if not available:
                continue

            aisle, y = key
            pos = min(available, key=lambda p: (p.x, p.z))

            cycle = _store_cycle(manager, key, pos, t)

            shuttle_load_penalty = manager.shuttle_free_at[key] * 0.05
            z_penalty = 0 if pos.z == 1 else 20
            distance_penalty = pos.x * 0.2

            score = cycle + shuttle_load_penalty + z_penalty + distance_penalty

            if score < best_score:
                best_score = score
                best = pos

        return best


class NearestHeadStorage:
    name = "nearest_head_storage"

    def choose_position(self, manager, box, t):
        best = None
        best_score = float("inf")

        for key, available in manager.silo.available_by_shuttle.items():
            if not available:
                continue

            pos = min(available, key=lambda p: (p.x, p.z))
            wait = max(0, manager.shuttle_free_at[key] - t)
            score = wait * 2.0 + pos.x + (0 if pos.z == 1 else 35)

            if score < best_score:
                best_score = score
                best = pos

        return best


class AisleSpreadStorage:
    name = "aisle_spread_storage"

    def choose_position(self, manager, box, t):
        aisle_load = _aisle_occupancy_counts(manager)
        dest_aisles = _destination_aisle_counts(manager, box.destination)
        best = None
        best_score = float("inf")

        for key, available in manager.silo.available_by_shuttle.items():
            if not available:
                continue

            aisle, _ = key
            pos = min(available, key=lambda p: (p.x, p.z))
            cycle = _store_cycle(manager, key, pos, t)
            aisle_balance = aisle_load[aisle] * 0.03
            grouping_bonus = -min(dest_aisles[aisle] * 1.5, 8)
            z_penalty = 0 if pos.z == 1 else 25

            score = cycle + pos.x * 0.25 + aisle_balance + z_penalty + grouping_bonus
            if score < best_score:
                best_score = score
                best = pos

        return best


class RetrievalFriendlyStorage:
    name = "retrieval_friendly_storage"

    def choose_position(self, manager, box, t):
        lane_load = _lane_occupancy_counts(manager)
        dest_lane = _destination_lane_counts(manager, box.destination)
        best = None
        best_score = float("inf")

        for key, available in manager.silo.available_by_shuttle.items():
            if not available:
                continue

            candidates = sorted(available, key=lambda p: (p.z, p.x))[:6]
            for pos in candidates:
                cycle = _store_cycle(manager, key, pos, t)
                lane_balance = lane_load[key] * 0.04
                grouping_bonus = -min(dest_lane[key] * 3, 12)
                z_penalty = 0 if pos.z == 1 else 45
                depth_pair_penalty = 0
                if pos.z == 2:
                    depth_pair_penalty = 10 + pos.x * 0.15

                score = (
                    cycle
                    + pos.x * 0.35
                    + lane_balance
                    + z_penalty
                    + depth_pair_penalty
                    + grouping_bonus
                )
                if score < best_score:
                    best_score = score
                    best = pos

        return best


class DenseLaneStorage:
    name = "dense_lane_storage"

    def choose_position(self, manager, box, t):
        dest_lane = _destination_lane_counts(manager, box.destination)
        best = None
        best_score = float("inf")

        for key, available in manager.silo.available_by_shuttle.items():
            if not available:
                continue

            candidates = sorted(available, key=lambda p: (abs(p.x - manager.shuttle_x[key]), p.z))[:10]
            for pos in candidates:
                cycle = _store_cycle(manager, key, pos, t)
                lane_grouping = -min(dest_lane[key] * 6, 30)
                z_penalty = 4 if pos.z == 2 and dest_lane[key] >= 4 else (0 if pos.z == 1 else 18)
                score = cycle + pos.x * 0.15 + z_penalty + lane_grouping

                if score < best_score:
                    best_score = score
                    best = pos

        return best
