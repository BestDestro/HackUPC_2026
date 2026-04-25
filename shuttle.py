"""
shuttle.py - Shuttle movement, time tracking, and task queue management.

Each shuttle operates on a single (Aisle, Y-level) and can carry 1 box at a time.
Time formula: t = 10 + d (10s handling + distance traveled in X).
All shuttles start at X=0 at t=0.
"""

from collections import deque
from typing import Optional, List

from models import Position, Box, Task


HANDLING_TIME = 10  # Fixed handling time in seconds


class Shuttle:
    """
    Represents a single shuttle operating at a specific (aisle, y_level).
    Manages its position, task queue, and accumulated time.
    """

    def __init__(self, aisle: int, y_level: int):
        self.aisle = aisle
        self.y_level = y_level
        self.current_x: int = 0         # Start at the head
        self.current_time: float = 0.0  # Accumulated time
        self.carried_box: Optional[Box] = None  # Currently holding (max 1)
        self.task_queue: deque = deque()  # Pending tasks
        self.total_tasks_completed: int = 0
        self.total_distance_traveled: int = 0

    @property
    def shuttle_id(self) -> str:
        return f"A{self.aisle}_Y{self.y_level}"

    @property
    def is_idle(self) -> bool:
        return len(self.task_queue) == 0 and self.carried_box is None

    @property
    def queue_length(self) -> int:
        return len(self.task_queue)

    def move_to(self, target_x: int) -> float:
        """
        Move the shuttle to target_x. Returns the time cost.
        Time = HANDLING_TIME + |current_x - target_x|
        """
        distance = abs(self.current_x - target_x)
        time_cost = HANDLING_TIME + distance
        self.current_x = target_x
        self.current_time += time_cost
        self.total_distance_traveled += distance
        return time_cost

    def move_to_head(self) -> float:
        """Move shuttle to X=0 (the head/entrance)."""
        return self.move_to(0)

    def estimate_time_to(self, target_x: int) -> float:
        """Estimate time to reach target_x without actually moving."""
        return HANDLING_TIME + abs(self.current_x - target_x)

    def estimate_store_cycle(self, target_x: int) -> float:
        """
        Estimate full cycle time for storing a box:
        1. Move to head (pick up box)
        2. Move to target position (drop box)
        """
        time_to_head = HANDLING_TIME + abs(self.current_x - 0)
        time_to_target = HANDLING_TIME + abs(0 - target_x)
        return time_to_head + time_to_target

    def estimate_retrieve_cycle(self, box_x: int) -> float:
        """
        Estimate full cycle time for retrieving a box:
        1. Move to box position (pick up box)
        2. Move to head (drop box for palletization)
        """
        time_to_box = HANDLING_TIME + abs(self.current_x - box_x)
        time_to_head = HANDLING_TIME + abs(box_x - 0)
        return time_to_box + time_to_head

    def add_task(self, task: Task):
        """Add a task to the shuttle's queue."""
        self.task_queue.append(task)

    def add_task_priority(self, task: Task):
        """Add a task to the front of the queue (urgent)."""
        self.task_queue.appendleft(task)

    def peek_next_task(self) -> Optional[Task]:
        """Look at the next task without removing it."""
        if self.task_queue:
            return self.task_queue[0]
        return None

    def pop_next_task(self) -> Optional[Task]:
        """Remove and return the next task."""
        if self.task_queue:
            return self.task_queue.popleft()
        return None

    def __repr__(self):
        return (f"Shuttle({self.shuttle_id}, x={self.current_x}, "
                f"time={self.current_time:.0f}s, queue={self.queue_length})")


class ShuttleManager:
    """
    Manages all 32 shuttles (4 aisles × 8 Y-levels).
    Provides methods to find the best shuttle for a given task.
    """

    def __init__(self):
        self.shuttles: dict = {}
        for aisle in range(1, 5):
            for y in range(1, 9):
                shuttle = Shuttle(aisle, y)
                self.shuttles[(aisle, y)] = shuttle

    def get_shuttle(self, aisle: int, y: int) -> Shuttle:
        """Get a specific shuttle by its aisle and Y-level."""
        return self.shuttles[(aisle, y)]

    def get_all_shuttles(self) -> List[Shuttle]:
        """Get all 32 shuttles."""
        return list(self.shuttles.values())

    def get_shuttles_for_aisle(self, aisle: int) -> List[Shuttle]:
        """Get all 8 shuttles in a specific aisle."""
        return [self.shuttles[(aisle, y)] for y in range(1, 9)]

    def get_least_busy_shuttle(self, aisle: Optional[int] = None) -> Shuttle:
        """
        Find the shuttle with the smallest accumulated time (least loaded).
        Optionally filter by aisle.
        """
        candidates = self.get_all_shuttles()
        if aisle is not None:
            candidates = self.get_shuttles_for_aisle(aisle)
        return min(candidates, key=lambda s: (s.current_time, s.queue_length))

    def get_fastest_shuttle_for_store(self, target_positions: list) -> tuple:
        """
        Given a list of candidate positions, find the (shuttle, position)
        pair that minimizes the store cycle time.
        Returns (best_shuttle, best_position, estimated_time).
        """
        best = None
        for pos in target_positions:
            shuttle = self.shuttles[(pos.aisle, pos.y)]
            cycle_time = shuttle.estimate_store_cycle(pos.x)
            total_time = shuttle.current_time + cycle_time  # absolute time
            if best is None or total_time < best[2]:
                best = (shuttle, pos, total_time)
        return best

    def get_max_time(self) -> float:
        """Get the maximum accumulated time across all shuttles (simulation bottleneck)."""
        return max(s.current_time for s in self.shuttles.values())

    def get_total_time(self) -> float:
        """Get the sum of all shuttle times."""
        return sum(s.current_time for s in self.shuttles.values())

    def get_stats(self) -> dict:
        """Return summary statistics for all shuttles."""
        shuttles = self.get_all_shuttles()
        times = [s.current_time for s in shuttles]
        return {
            "total_shuttles": len(shuttles),
            "max_time": max(times),
            "min_time": min(times),
            "avg_time": sum(times) / len(times),
            "total_tasks": sum(s.total_tasks_completed for s in shuttles),
            "total_distance": sum(s.total_distance_traveled for s in shuttles),
        }
