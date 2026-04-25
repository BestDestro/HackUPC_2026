"""
silo.py - Silo grid state management using hash maps for O(1) lookups.

The silo is a 3D grid:
  - 4 Aisles (1-4)
  - 2 Sides per aisle (1, 2)
  - 60 X positions per side (0-59)
  - 8 Y levels per position (1-8)
  - 2 Z depths per level (1, 2)

Total capacity: 4 * 2 * 60 * 8 * 2 = 7,680 slots
"""

from collections import defaultdict
from typing import Optional, List, Set, Dict, Tuple

from models import Position, Box


# Silo dimensions
NUM_AISLES = 4
NUM_SIDES = 2
NUM_X = 60
NUM_Y = 8
NUM_Z = 2


class Silo:
    """Manages the physical grid state of the silo with O(1) hash map lookups."""

    def __init__(self):
        # ---- Primary State (Hash Maps) ----
        # Position -> Box (or None)
        self.grid: Dict[Position, Optional[Box]] = {}
        # Box ID -> Position
        self.box_locations: Dict[str, Position] = {}
        # Destination -> Set of Box IDs currently in silo
        self.destination_inventory: Dict[str, Set[str]] = defaultdict(set)

        # ---- Available spaces index, grouped by (aisle, y) for fast shuttle-aware lookup ----
        # (aisle, y) -> set of available Positions
        self.available_by_shuttle: Dict[Tuple[int, int], Set[Position]] = defaultdict(set)

        # Initialize all positions as empty
        self._initialize_grid()

    def _initialize_grid(self):
        """Create all positions and mark them as available."""
        for aisle in range(1, NUM_AISLES + 1):
            for side in range(1, NUM_SIDES + 1):
                for x in range(1, NUM_X + 1):  # 1-based: 1 to 60
                    for y in range(1, NUM_Y + 1):
                        for z in range(1, NUM_Z + 1):
                            pos = Position(aisle, side, x, y, z)
                            self.grid[pos] = None
                            self.available_by_shuttle[(aisle, y)].add(pos)

    @property
    def total_capacity(self) -> int:
        return NUM_AISLES * NUM_SIDES * NUM_X * NUM_Y * NUM_Z

    @property
    def occupied_count(self) -> int:
        return len(self.box_locations)

    @property
    def occupancy_rate(self) -> float:
        return self.occupied_count / self.total_capacity

    # ---- Core Operations ----

    def place_box(self, box: Box, position: Position) -> bool:
        """
        Place a box at a specific position.
        Returns True if successful, False if position is occupied or Z-constraint violated.
        """
        # Check position is free
        if self.grid.get(position) is not None:
            return False

        # Z-constraint: cannot place at Z=2 if Z=1 is empty
        if position.z == 2:
            z1_pos = Position(position.aisle, position.side, position.x, position.y, 1)
            if self.grid.get(z1_pos) is None:
                return False

        # Place the box
        self.grid[position] = box
        box.position = position
        self.box_locations[box.box_id] = position
        self.destination_inventory[box.destination].add(box.box_id)

        # Remove from available index
        shuttle_key = (position.aisle, position.y)
        self.available_by_shuttle[shuttle_key].discard(position)

        # If we placed at Z=1, Z=2 above is now potentially available (if empty)
        if position.z == 1:
            z2_pos = Position(position.aisle, position.side, position.x, position.y, 2)
            if self.grid.get(z2_pos) is None:
                self.available_by_shuttle[shuttle_key].add(z2_pos)

        return True

    def force_place_box(self, box: Box, position: Position) -> bool:
        """
        Place a box at a specific position WITHOUT Z-constraint validation.
        Used for loading initial state from CSV where Z=2 may exist without Z=1
        (e.g., Z=1 was already extracted before the snapshot).
        Returns True if successful, False only if position is already occupied.
        """
        # Check position is free
        if self.grid.get(position) is not None:
            return False

        # Place the box (no Z-constraint check)
        self.grid[position] = box
        box.position = position
        self.box_locations[box.box_id] = position
        self.destination_inventory[box.destination].add(box.box_id)

        # Remove from available index
        shuttle_key = (position.aisle, position.y)
        self.available_by_shuttle[shuttle_key].discard(position)

        # Update Z=2 availability based on current state
        if position.z == 1:
            z2_pos = Position(position.aisle, position.side, position.x, position.y, 2)
            if self.grid.get(z2_pos) is None:
                self.available_by_shuttle[shuttle_key].add(z2_pos)
        elif position.z == 2:
            # If we placed at Z=2 and Z=1 is empty, Z=1 is still available
            # but Z=2 is no longer available (just placed)
            pass

        return True

    def remove_box(self, box_id: str) -> Optional[Box]:
        """
        Remove a box from the silo by its ID.
        Returns the Box if found, None otherwise.
        Does NOT check Z-constraint (caller must handle relocation).
        """
        if box_id not in self.box_locations:
            return None

        position = self.box_locations[box_id]
        box = self.grid[position]

        # Clear grid
        self.grid[position] = None
        del self.box_locations[box_id]
        box.position = None

        # Update destination inventory
        self.destination_inventory[box.destination].discard(box_id)
        if not self.destination_inventory[box.destination]:
            del self.destination_inventory[box.destination]

        # Update available index
        shuttle_key = (position.aisle, position.y)
        self.available_by_shuttle[shuttle_key].add(position)

        # If we removed from Z=1, Z=2 is no longer reachable for placement
        if position.z == 1:
            z2_pos = Position(position.aisle, position.side, position.x, position.y, 2)
            if self.grid.get(z2_pos) is None:
                # Z=2 was available but now Z=1 is empty, so Z=2 cannot be used
                self.available_by_shuttle[shuttle_key].discard(z2_pos)

        return box

    def is_blocked(self, position: Position) -> bool:
        """Check if a box at Z=2 is blocked by a box at Z=1."""
        if position.z != 2:
            return False
        z1_pos = Position(position.aisle, position.side, position.x, position.y, 1)
        return self.grid.get(z1_pos) is not None

    def get_blocking_box(self, position: Position) -> Optional[Box]:
        """Get the box at Z=1 that blocks access to Z=2 at the same location."""
        if position.z != 2:
            return None
        z1_pos = Position(position.aisle, position.side, position.x, position.y, 1)
        return self.grid.get(z1_pos)

    def get_box_at(self, position: Position) -> Optional[Box]:
        """Get the box at a specific position."""
        return self.grid.get(position)

    def get_box_position(self, box_id: str) -> Optional[Position]:
        """O(1) lookup: where is this box?"""
        return self.box_locations.get(box_id)

    def get_boxes_for_destination(self, destination: str) -> Set[str]:
        """Get all box IDs in the silo for a given destination."""
        return self.destination_inventory.get(destination, set())

    def get_destinations_with_enough_boxes(self, min_count: int = 12) -> List[str]:
        """Get all destinations that have at least min_count boxes ready for palletization."""
        return [
            dest for dest, boxes in self.destination_inventory.items()
            if len(boxes) >= min_count
        ]

    def get_available_positions_for_shuttle(self, aisle: int, y: int) -> Set[Position]:
        """Get all available positions reachable by a specific shuttle."""
        return self.available_by_shuttle.get((aisle, y), set())

    def find_nearest_available(self, aisle: int, y: int, from_x: int) -> Optional[Position]:
        """
        Find the nearest available position to a given X on the same (aisle, y).
        Prefers Z=1 over Z=2 to avoid future blockages.
        """
        available = self.get_available_positions_for_shuttle(aisle, y)
        if not available:
            return None

        # Sort by distance to from_x, then prefer Z=1
        best = min(available, key=lambda p: (abs(p.x - from_x), p.z))
        return best

    def get_stats(self) -> dict:
        """Return summary statistics of the silo state."""
        dest_counts = {dest: len(boxes) for dest, boxes in self.destination_inventory.items()}
        return {
            "total_capacity": self.total_capacity,
            "occupied": self.occupied_count,
            "occupancy_rate": f"{self.occupancy_rate:.1%}",
            "unique_destinations": len(self.destination_inventory),
            "destinations_ready_for_pallet": len(self.get_destinations_with_enough_boxes(12)),
            "destination_counts": dest_counts,
        }
