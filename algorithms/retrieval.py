# algorithms/retrieval.py


def _iter_candidates(manager):
    for pallet in manager.active_pallets:
        remaining = 12 - len(pallet.retrieved)
        for box in pallet.boxes:
            if box in pallet.retrieved or box.position is None:
                continue
            yield box, pallet, remaining


def _movement_cost(manager, box, t):
    pos = box.position
    key = (pos.aisle, pos.y)
    cur_x = manager.shuttle_x[key]
    wait = max(0, manager.shuttle_free_at[key] - t)
    return (
        wait
        + manager._shuttle_move_cost(key, cur_x, pos.x)
        + manager._shuttle_move_cost(key, pos.x, 0)
    )


def _blocked_penalty(manager, box, penalty=60):
    return penalty if manager.silo.is_blocked(box.position) else 0


class CheapestBoxFirst:
    name = "cheapest_box_first"

    def choose_box(self, manager, t):
        best = None
        best_cost = float("inf")

        for box, pallet, _ in _iter_candidates(manager):
            cost = _movement_cost(manager, box, t) + _blocked_penalty(manager, box, 40)

            if cost < best_cost:
                best_cost = cost
                best = (box, pallet)

        return best


class FinishPalletFirstRetrieval:
    name = "finish_pallet_first_retrieval"

    def choose_box(self, manager, t):
        best = None
        best_score = float("inf")

        for box, pallet, remaining in _iter_candidates(manager):
            score = (
                _movement_cost(manager, box, t)
                + _blocked_penalty(manager, box, 60)
                + remaining * 10
            )

            if score < best_score:
                best_score = score
                best = (box, pallet)

        return best


class UnblockedFirstRetrieval:
    name = "unblocked_first_retrieval"

    def choose_box(self, manager, t):
        best = None
        best_score = float("inf")

        for box, pallet, remaining in _iter_candidates(manager):
            pos = box.position
            score = (
                _movement_cost(manager, box, t)
                + _blocked_penalty(manager, box, 200)
                + (0 if pos.z == 1 else 35)
                + remaining * 3
            )

            if score < best_score:
                best_score = score
                best = (box, pallet)

        return best


class DepthAwareRetrieval:
    name = "depth_aware_retrieval"

    def choose_box(self, manager, t):
        best = None
        best_score = float("inf")

        for box, pallet, remaining in _iter_candidates(manager):
            pos = box.position
            rear_penalty = 20 if pos.z == 2 else 0
            score = (
                _movement_cost(manager, box, t)
                + _blocked_penalty(manager, box, 120)
                + rear_penalty
                + remaining * 6
            )

            if score < best_score:
                best_score = score
                best = (box, pallet)

        return best


class ShuttleReadyRetrieval:
    name = "shuttle_ready_retrieval"

    def choose_box(self, manager, t):
        best = None
        best_score = float("inf")

        for box, pallet, remaining in _iter_candidates(manager):
            pos = box.position
            key = (pos.aisle, pos.y)
            wait = max(0, manager.shuttle_free_at[key] - t)
            score = (
                wait * 3
                + _movement_cost(manager, box, t)
                + _blocked_penalty(manager, box, 80)
                + remaining * 4
            )

            if score < best_score:
                best_score = score
                best = (box, pallet)

        return best


class PalletBatchRetrieval:
    name = "pallet_batch_retrieval"

    def choose_box(self, manager, t):
        best = None
        best_score = float("inf")

        for box, pallet, remaining in _iter_candidates(manager):
            already_progress = len(pallet.retrieved)
            score = (
                _movement_cost(manager, box, t)
                + _blocked_penalty(manager, box, 90)
                - already_progress * 8
                + remaining * 4
            )

            if score < best_score:
                best_score = score
                best = (box, pallet)

        return best


class RelocationOpportunisticRetrieval:
    name = "relocation_opportunistic_retrieval"

    def choose_box(self, manager, t):
        best = None
        best_score = float("inf")

        active_needed = {
            box.box_id
            for pallet in manager.active_pallets
            for box in pallet.boxes
            if box not in pallet.retrieved and box.position is not None
        }

        for box, pallet, remaining in _iter_candidates(manager):
            pos = box.position
            blocked_penalty = 0
            if manager.silo.is_blocked(pos):
                blocking = manager.silo.get_blocking_box(pos)
                blocked_penalty = 25 if blocking and blocking.box_id in active_needed else 130

            score = _movement_cost(manager, box, t) + blocked_penalty + remaining * 5

            if score < best_score:
                best_score = score
                best = (box, pallet)

        return best
