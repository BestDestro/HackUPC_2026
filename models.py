"""
models.py - Core data classes for the logistics simulation.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Position:
    """Represents a physical location in the silo grid."""
    aisle: int    # 1-4
    side: int     # 1 (Left) or 2 (Right)
    x: int        # 0-59 (length from head)
    y: int        # 1-8  (height level)
    z: int        # 1-2  (depth)

    def to_string(self) -> str:
        """Format as the 11-digit string: AISLE_SIDE_X_Y_Z."""
        return f"{self.aisle:02d}_{self.side:02d}_{self.x:03d}_{self.y:02d}_{self.z:02d}"

    def __hash__(self):
        return hash((self.aisle, self.side, self.x, self.y, self.z))

    def __eq__(self, other):
        if not isinstance(other, Position):
            return False
        return (self.aisle, self.side, self.x, self.y, self.z) == \
               (other.aisle, other.side, other.x, other.y, other.z)

    def __repr__(self):
        return f"Pos(A{self.aisle},S{self.side},X{self.x},Y{self.y},Z{self.z})"


@dataclass
class Box:
    """
    Represents a unit load (box) with a unique 20-digit identity.
    Source:      first 7 digits  (warehouse)
    Destination: next 8 digits
    Bulk number: last 5 digits
    """
    box_id: str           # Full 20-digit code
    source: str           # First 7 digits
    destination: str      # Next 8 digits
    bulk_number: str      # Last 5 digits
    position: Optional[Position] = None  # Current location in silo (None if not stored yet)

    @classmethod
    def from_id(cls, box_id: str) -> "Box":
        """Parse a 20-digit box ID into its components."""
        return cls(
            box_id=box_id,
            source=box_id[:7],
            destination=box_id[7:15],
            bulk_number=box_id[15:],
        )

    def __hash__(self):
        return hash(self.box_id)

    def __eq__(self, other):
        if not isinstance(other, Box):
            return False
        return self.box_id == other.box_id

    def __repr__(self):
        return f"Box({self.box_id}, dest={self.destination})"


@dataclass
class Task:
    """A unit of work for a shuttle."""
    task_type: str          # 'STORE', 'RETRIEVE', 'RELOCATE'
    box: Box
    target_position: Optional[Position] = None  # Where to put (STORE/RELOCATE) or pick from (RETRIEVE)
    relocation_target: Optional[Position] = None  # For RELOCATE: where to move the blocking box
    pallet_id: Optional[str] = None  # Which pallet this retrieval is for


@dataclass
class Pallet:
    """A pallet is a set of 12 boxes with the same destination."""
    destination: str
    boxes: list = field(default_factory=list)     # List of Box objects assigned to this pallet
    retrieved: list = field(default_factory=list)  # Boxes already extracted from silo
    reserved: bool = False

    @property
    def is_complete(self) -> bool:
        return len(self.retrieved) == 12

    @property
    def boxes_remaining(self) -> int:
        return 12 - len(self.retrieved)

    def __repr__(self):
        return f"Pallet(dest={self.destination}, retrieved={len(self.retrieved)}/12)"
