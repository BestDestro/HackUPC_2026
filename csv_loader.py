"""
csv_loader.py - Load initial silo state from the hackathon CSV file.

CSV Format:
  - Header: posicion,etiqueta
  - Position: 11-digit string (no separators): AASSSXXXYYYZZ
    - AA:  Aisle  (01-04)
    - SS:  Side   (01-02)
    - XXX: X pos  (001-060)
    - YY:  Y level (01-08)
    - ZZ:  Z depth (01-02)
  - Etiqueta (label): 20-digit box ID, or empty if slot is unoccupied.
"""

import csv
from typing import Tuple

from models import Position, Box
from silo import Silo


def parse_position(pos_str: str) -> Position:
    """Parse an 11-digit position string into a Position object."""
    aisle = int(pos_str[0:2])
    side = int(pos_str[2:4])
    x = int(pos_str[4:7])
    y = int(pos_str[7:9])
    z = int(pos_str[9:11])
    return Position(aisle, side, x, y, z)


def load_silo_from_csv(filepath: str, silo: Silo) -> dict:
    """
    Load initial silo state from a CSV file.

    Reads each row, parses the position and box ID, and places
    occupied boxes into the silo grid.

    Args:
        filepath: Path to the CSV file.
        silo: An initialized (empty) Silo instance.

    Returns:
        Dictionary with loading stats and the all_boxes registry.
    """
    all_boxes = {}  # box_id -> Box
    loaded = 0
    skipped = 0
    empty = 0
    errors = []

    with open(filepath, "r", encoding="utf-8") as f:
        reader = csv.reader(f)
        header = next(reader)  # Skip header

        for row_num, row in enumerate(reader, start=2):
            pos_str = row[0].strip()
            label = row[1].strip() if len(row) > 1 else ""

            if not label:
                empty += 1
                continue

            # Parse position
            try:
                position = parse_position(pos_str)
            except (ValueError, IndexError) as e:
                errors.append(f"Row {row_num}: Bad position '{pos_str}': {e}")
                skipped += 1
                continue

            # Parse box
            try:
                box = Box.from_id(label)
            except Exception as e:
                errors.append(f"Row {row_num}: Bad box ID '{label}': {e}")
                skipped += 1
                continue

            # Place box in silo (skip Z-constraint for initial state loading)
            success = silo.force_place_box(box, position)
            if success:
                all_boxes[box.box_id] = box
                loaded += 1
            else:
                errors.append(
                    f"Row {row_num}: Failed to place box {label} at {position} "
                    f"(occupied or Z-constraint)"
                )
                skipped += 1

    stats = {
        "loaded": loaded,
        "empty_slots": empty,
        "skipped": skipped,
        "errors": errors,
        "unique_destinations": len(set(b.destination for b in all_boxes.values())),
        "total_rows": loaded + empty + skipped,
    }

    return {"all_boxes": all_boxes, "stats": stats}
