# algorithms/storage.py

from collections import defaultdict
from typing import Optional

from models import Box, Position
from silo import NUM_AISLES, NUM_Y


class GreedyStorage:
    name = "greedy_storage"

    def choose_position(self, manager, box: Box, t: float) -> Optional[Position]:
        dest_per_aisle = defaultdict(int)

        for bid in manager.silo.get_boxes_for_destination(box.destination):
            pos = manager.silo.get_box_position(bid)
            if pos:
                dest_per_aisle[pos.aisle] += 1

        best = None
        best_score = float("inf")

        for aisle in range(1, NUM_AISLES + 1):
            for y in range(1, NUM_Y + 1):
                key = (aisle, y)
                available = manager.silo.get_available_positions_for_shuttle(aisle, y)

                if not available:
                    continue

                pos = min(available, key=lambda p: (p.x, p.z))
                cur_x = manager.shuttle_x[key]

                wait = max(0, manager.shuttle_free_at[key] - t)
                cycle = (
                    manager._shuttle_move_cost(key, cur_x, 0)
                    + manager._shuttle_move_cost(key, 0, pos.x)
                )

                z_penalty = 0 if pos.z == 1 else 15
                grouping_bonus = -min(dest_per_aisle.get(aisle, 0) * 2, 10)

                score = wait + cycle + z_penalty + pos.x * 0.3 + grouping_bonus

                if score < best_score:
                    best_score = score
                    best = pos

        return best
    
class DestinationGroupedStorage:
    name = "destination_grouped_storage"

    def choose_position(self, manager, box, t):
        dest_by_aisle = {}

        for bid in manager.silo.get_boxes_for_destination(box.destination):
            pos = manager.silo.get_box_position(bid)
            if pos:
                dest_by_aisle[pos.aisle] = dest_by_aisle.get(pos.aisle, 0) + 1

        best = None
        best_score = float("inf")

        for key, available in manager.silo.available_by_shuttle.items():
            aisle, y = key
            cur_x = manager.shuttle_x[key]
            wait = max(0, manager.shuttle_free_at[key] - t)

            for pos in available:
                cycle = (
                    manager._shuttle_move_cost(key, cur_x, 0)
                    + manager._shuttle_move_cost(key, 0, pos.x)
                )

                grouping_bonus = -dest_by_aisle.get(aisle, 0) * 5
                z_penalty = 0 if pos.z == 1 else 25
                distance_penalty = pos.x * 0.2

                score = wait + cycle + z_penalty + distance_penalty + grouping_bonus

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
            cur_x = manager.shuttle_x[key]
            wait = max(0, manager.shuttle_free_at[key] - t)

            pos = min(available, key=lambda p: (p.x, p.z))

            cycle = (
                manager._shuttle_move_cost(key, cur_x, 0)
                + manager._shuttle_move_cost(key, 0, pos.x)
            )

            shuttle_load_penalty = manager.shuttle_free_at[key] * 0.05
            z_penalty = 0 if pos.z == 1 else 20
            distance_penalty = pos.x * 0.2

            score = wait + cycle + shuttle_load_penalty + z_penalty + distance_penalty

            if score < best_score:
                best_score = score
                best = pos

        return best
