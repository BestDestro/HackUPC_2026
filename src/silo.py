from collections import defaultdict
from typing import Dict, Optional

from .models import Position, Box


class Silo:
    def __init__(self):
        self.positions: Dict[Position, Optional[Box]] = {}
        self.box_location: Dict[str, Position] = {}
        self.boxes_by_destination = defaultdict(list)

        self._create_empty_silo()

    def _create_empty_silo(self):
        """
        Crea las 7.680 posiciones posibles del silo:
        4 pasillos × 2 lados × 60 X × 8 Y × 2 Z
        """
        for aisle in range(1, 5):
            for side in range(1, 3):
                for x in range(1, 61):
                    for y in range(1, 9):
                        for z in range(1, 3):
                            pos = Position(
                                aisle=aisle,
                                side=side,
                                x=x,
                                y=y,
                                z=z,
                            )
                            self.positions[pos] = None

    def add_box(self, box: Box, position: Position):
        """
        Añade una caja al silo en una posición concreta.
        Se usa para cargar el estado inicial desde CSV.
        """
        if position not in self.positions:
            raise ValueError(f"La posición no existe en el silo: {position}")

        if self.positions[position] is not None:
            raise ValueError(f"La posición ya está ocupada: {position}")

        box.position = position
        self.positions[position] = box
        self.box_location[box.box_id] = position
        self.boxes_by_destination[box.destination].append(box)

    def occupied_count(self) -> int:
        return sum(1 for box in self.positions.values() if box is not None)

    def empty_count(self) -> int:
        return len(self.positions) - self.occupied_count()

    def capacity(self) -> int:
        return len(self.positions)

    def destination_count(self) -> int:
        return len(self.boxes_by_destination)

    def possible_pallets(self) -> int:
        """
        Cada palé son 12 cajas del mismo destino.
        """
        return sum(
            len(boxes) // 12
            for boxes in self.boxes_by_destination.values()
        )

    def stats(self) -> dict:
        occupied = self.occupied_count()
        capacity = self.capacity()

        return {
            "capacity": capacity,
            "occupied": occupied,
            "empty": self.empty_count(),
            "occupancy_pct": round(occupied / capacity * 100, 2),
            "destinations": self.destination_count(),
            "possible_pallets": self.possible_pallets(),
        }

    def print_stats(self):
        stats = self.stats()

        print("\n=== Initial silo state ===")
        for key, value in stats.items():
            print(f"{key}: {value}")

    def print_destinations_summary(self):
        print("\n=== Destinations summary ===")

        for destination, boxes in sorted(self.boxes_by_destination.items()):
            pallets = len(boxes) // 12
            remainder = len(boxes) % 12

            print(
                f"Destination {destination} | "
                f"boxes={len(boxes)} | "
                f"pallets={pallets} | "
                f"remainder={remainder}"
            )