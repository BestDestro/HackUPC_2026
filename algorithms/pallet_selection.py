# algorithms/pallet_selection.py

from collections import Counter


BOXES_PER_PALLET = 12
HANDLING_TIME = 10


def _active_destinations(manager):
    return {p.destination for p in manager.active_pallets}


def _eligible_destinations(manager):
    active_dests = _active_destinations(manager)
    return [
        d for d in manager.silo.get_destinations_with_enough_boxes(BOXES_PER_PALLET)
        if d not in active_dests
    ]


def _candidate_box_ids(manager, destination: str):
    return sorted(manager.silo.get_boxes_for_destination(destination))[:BOXES_PER_PALLET]


def _destination_positions(manager, destination: str):
    positions = []
    for bid in _candidate_box_ids(manager, destination):
        pos = manager.silo.get_box_position(bid)
        if pos:
            positions.append(pos)
    return positions


def _position_cost(manager, pos):
    key = (pos.aisle, pos.y)
    cur_x = manager.shuttle_x.get(key, 0)
    wait = max(0, manager.shuttle_free_at.get(key, 0) - manager.sim_time)
    cost = wait + HANDLING_TIME + abs(cur_x - pos.x) + HANDLING_TIME + pos.x
    if manager.silo.is_blocked(pos):
        cost += 60
    return cost


class CheapestPalletFirst:
    name = "cheapest_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        scored = []
        for dest in _eligible_destinations(manager):
            positions = _destination_positions(manager, dest)
            cost = sum(_position_cost(manager, pos) for pos in positions)
            scored.append((dest, cost))

        scored.sort(key=lambda x: (x[1], x[0]))
        return [dest for dest, _ in scored[:available_slots]]


class LeastBlockedPalletFirst:
    name = "least_blocked_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        scored = []
        for dest in _eligible_destinations(manager):
            positions = _destination_positions(manager, dest)
            blocked_count = sum(1 for pos in positions if manager.silo.is_blocked(pos))
            distance_cost = sum(pos.x for pos in positions)
            scored.append((dest, blocked_count * 100 + distance_cost))

        scored.sort(key=lambda x: (x[1], x[0]))
        return [dest for dest, _ in scored[:available_slots]]


class MostBoxesFirst:
    name = "most_boxes_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        eligible = _eligible_destinations(manager)
        eligible.sort(
            key=lambda d: (-len(manager.silo.get_boxes_for_destination(d)), d),
        )
        return eligible[:available_slots]


class ShuttleBalancedPalletFirst:
    name = "shuttle_balanced_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        scored = []
        for dest in _eligible_destinations(manager):
            positions = _destination_positions(manager, dest)
            if not positions:
                continue

            lanes = Counter((p.aisle, p.y) for p in positions)
            lane_spread = len(lanes)
            busiest_lane = max(lanes.values())
            avg_wait = sum(
                max(0, manager.shuttle_free_at[(p.aisle, p.y)] - manager.sim_time)
                for p in positions
            ) / len(positions)
            avg_x = sum(p.x for p in positions) / len(positions)

            score = avg_wait + avg_x * 0.5 - lane_spread * 8 - busiest_lane * 2
            scored.append((dest, score))

        scored.sort(key=lambda x: (x[1], x[0]))
        return [dest for dest, _ in scored[:available_slots]]


class HighestDensityPalletFirst:
    name = "highest_density_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        scored = []
        for dest in _eligible_destinations(manager):
            positions = _destination_positions(manager, dest)
            if not positions:
                continue

            aisle_counts = Counter(p.aisle for p in positions)
            lane_counts = Counter((p.aisle, p.y) for p in positions)
            density_bonus = max(aisle_counts.values()) * 12 + max(lane_counts.values()) * 4
            blocked = sum(1 for p in positions if manager.silo.is_blocked(p))
            distance = sum(p.x for p in positions)
            score = distance + blocked * 80 - density_bonus
            scored.append((dest, score))

        scored.sort(key=lambda x: (x[1], x[0]))
        return [dest for dest, _ in scored[:available_slots]]


class MinRelocationRiskPalletFirst:
    name = "min_relocation_risk_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        scored = []
        for dest in _eligible_destinations(manager):
            positions = _destination_positions(manager, dest)
            if not positions:
                continue

            blocked = sum(1 for pos in positions if manager.silo.is_blocked(pos))
            rear = sum(1 for pos in positions if pos.z == 2)
            cost = sum(_position_cost(manager, pos) for pos in positions)
            score = blocked * 150 + rear * 25 + cost
            scored.append((dest, score))

        scored.sort(key=lambda x: (x[1], x[0]))
        return [dest for dest, _ in scored[:available_slots]]


class ThroughputPalletFirst:
    name = "throughput_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        eligible = _eligible_destinations(manager)
        eligible.sort(
            key=lambda d: (
                sum(_position_cost(manager, p) for p in _destination_positions(manager, d)),
                -len(manager.silo.get_boxes_for_destination(d)),
                d,
            ),
        )
        return eligible[:available_slots]


class ScarcityAwarePalletFirst:
    name = "scarcity_aware_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        eligible = _eligible_destinations(manager)
        eligible.sort(
            key=lambda d: (
                len(manager.silo.get_boxes_for_destination(d)) - BOXES_PER_PALLET,
                sum(p.x for p in _destination_positions(manager, d)),
                d,
            )
        )
        return eligible[:available_slots]
