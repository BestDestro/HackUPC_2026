# algorithms/retrieval.py

class CheapestBoxFirst:
    name = "cheapest_box_first"

    def choose_box(self, manager, t):
        best = None
        best_cost = float("inf")

        for pallet in manager.active_pallets:
            for box in pallet.boxes:
                if box in pallet.retrieved or box.position is None:
                    continue

                pos = box.position
                key = (pos.aisle, pos.y)
                cur_x = manager.shuttle_x[key]

                wait = max(0, manager.shuttle_free_at[key] - t)
                cost = (
                    wait
                    + manager._shuttle_move_cost(key, cur_x, pos.x)
                    + manager._shuttle_move_cost(key, pos.x, 0)
                )

                if manager.silo.is_blocked(pos):
                    cost += 40

                if cost < best_cost:
                    best_cost = cost
                    best = (box, pallet)

        return best
    
class FinishPalletFirstRetrieval:
    name = "finish_pallet_first_retrieval"

    def choose_box(self, manager, t):
        best = None
        best_score = float("inf")

        for pallet in manager.active_pallets:
            remaining = 12 - len(pallet.retrieved)

            for box in pallet.boxes:
                if box in pallet.retrieved or box.position is None:
                    continue

                pos = box.position
                key = (pos.aisle, pos.y)
                cur_x = manager.shuttle_x[key]

                wait = max(0, manager.shuttle_free_at[key] - t)

                movement_cost = (
                    manager._shuttle_move_cost(key, cur_x, pos.x)
                    + manager._shuttle_move_cost(key, pos.x, 0)
                )

                blocked_penalty = 60 if manager.silo.is_blocked(pos) else 0

                # cuanto menos queda para cerrar el pallet, menor score
                finish_bonus = remaining * 10

                score = wait + movement_cost + blocked_penalty + finish_bonus

                if score < best_score:
                    best_score = score
                    best = (box, pallet)

        return best