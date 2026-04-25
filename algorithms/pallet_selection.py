# algorithms/pallet_selection.py

from concurrent_sim import BOXES_PER_PALLET, HANDLING_TIME


class CheapestPalletFirst:
    name = "cheapest_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        active_dests = {p.destination for p in manager.active_pallets}

        eligible = [
            d for d in manager.silo.get_destinations_with_enough_boxes(BOXES_PER_PALLET)
            if d not in active_dests
        ]

        scored = []

        for dest in eligible:
            ids = list(manager.silo.get_boxes_for_destination(dest))[:BOXES_PER_PALLET]
            cost = 0

            for bid in ids:
                pos = manager.silo.get_box_position(bid)
                if pos:
                    cost += HANDLING_TIME + pos.x + HANDLING_TIME + pos.x
                    if manager.silo.is_blocked(pos):
                        cost += 40

            scored.append((dest, cost))

        scored.sort(key=lambda x: x[1])
        return [dest for dest, _ in scored[:available_slots]]
    
class LeastBlockedPalletFirst:
    name = "least_blocked_pallet_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        active_dests = {p.destination for p in manager.active_pallets}

        eligible = [
            d for d in manager.silo.get_destinations_with_enough_boxes(BOXES_PER_PALLET)
            if d not in active_dests
        ]

        scored = []

        for dest in eligible:
            ids = list(manager.silo.get_boxes_for_destination(dest))[:BOXES_PER_PALLET]

            blocked_count = 0
            distance_cost = 0

            for bid in ids:
                pos = manager.silo.get_box_position(bid)
                if not pos:
                    continue

                distance_cost += pos.x

                if manager.silo.is_blocked(pos):
                    blocked_count += 1

            score = blocked_count * 100 + distance_cost

            scored.append((dest, score))

        scored.sort(key=lambda x: x[1])
        return [dest for dest, _ in scored[:available_slots]]
    
class MostBoxesFirst:
    name = "most_boxes_first"

    def choose_destinations(self, manager, available_slots: int) -> list[str]:
        active_dests = {p.destination for p in manager.active_pallets}

        eligible = [
            d for d in manager.silo.get_destinations_with_enough_boxes(BOXES_PER_PALLET)
            if d not in active_dests
        ]

        eligible.sort(
            key=lambda d: len(manager.silo.get_boxes_for_destination(d)),
            reverse=True,
        )

        return eligible[:available_slots]