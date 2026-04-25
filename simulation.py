"""
simulation.py - Simulation engine that generates box traffic and runs scenarios.

Generates synthetic boxes for 20, 40, or 80 destination scenarios,
feeds them through the LogisticsManager, and collects metrics.
Also supports loading initial silo state from the hackathon CSV files.
"""

import random
import time as time_module
from typing import List
from collections import Counter

from models import Box
from silo import Silo
from shuttle import ShuttleManager
from logistics_manager import LogisticsManager, BOXES_PER_PALLET
from csv_loader import load_silo_from_csv


def generate_box_id(source: str, destination: str, bulk_number: int) -> str:
    """Generate a 20-digit box ID from components."""
    return f"{source}{destination}{bulk_number:05d}"


def generate_boxes(num_destinations: int, pallets_per_destination: int = 3,
                   boxes_per_pallet: int = BOXES_PER_PALLET) -> List[Box]:
    """
    Generate a set of boxes for the simulation.

    Args:
        num_destinations: Number of unique destinations (20, 40, or 80).
        pallets_per_destination: How many full pallets worth of boxes per destination.
        boxes_per_pallet: Boxes per pallet (default 12).

    Returns:
        Shuffled list of Box objects.
    """
    boxes = []
    source = "3010028"  # Fixed warehouse source

    for dest_idx in range(num_destinations):
        # Generate an 8-digit destination code
        destination = f"{dest_idx + 1:08d}"

        for pallet_idx in range(pallets_per_destination):
            for box_idx in range(boxes_per_pallet):
                bulk_num = dest_idx * 1000 + pallet_idx * 100 + box_idx + 1
                box_id = generate_box_id(source, destination, bulk_num)
                box = Box.from_id(box_id)
                boxes.append(box)

    # Shuffle to simulate real-world arrival order (chaotic input)
    random.shuffle(boxes)
    return boxes


def run_scenario(num_destinations: int, pallets_per_destination: int = 3,
                 seed: int = 42, verbose: bool = True) -> dict:
    """
    Run a full simulation scenario with synthetic data.

    Phase 1: INPUT  - Store all incoming boxes into the silo.
    Phase 2: OUTPUT - Extract boxes to form complete pallets.

    Args:
        num_destinations: Number of unique destinations.
        pallets_per_destination: Full pallets per destination.
        seed: Random seed for reproducibility.
        verbose: Print progress.

    Returns:
        Dictionary with all metrics.
    """
    random.seed(seed)

    total_boxes = num_destinations * pallets_per_destination * BOXES_PER_PALLET

    if verbose:
        print(f"\n{'='*70}")
        print(f"  SCENARIO: {num_destinations} Destinations (Synthetic)")
        print(f"  Pallets per destination: {pallets_per_destination}")
        print(f"  Total boxes: {total_boxes}")
        print(f"  Silo capacity: 7,680 slots")
        print(f"  Occupancy after fill: {total_boxes/7680:.1%}")
        print(f"{'='*70}")

    # Check capacity
    if total_boxes > 7680:
        print(f"  WARNING: {total_boxes} boxes exceeds silo capacity of 7,680!")
        print(f"  Reducing pallets_per_destination to fit.")
        pallets_per_destination = 7680 // (num_destinations * BOXES_PER_PALLET)
        total_boxes = num_destinations * pallets_per_destination * BOXES_PER_PALLET
        print(f"  Adjusted: {pallets_per_destination} pallets/dest, {total_boxes} total boxes")

    # Initialize system
    silo = Silo()
    shuttle_mgr = ShuttleManager()
    manager = LogisticsManager(silo, shuttle_mgr)

    # Generate boxes
    boxes = generate_boxes(num_destinations, pallets_per_destination)

    # =========================================================================
    # PHASE 1: INPUT - Store all boxes
    # =========================================================================
    if verbose:
        print(f"\n--- Phase 1: STORING {len(boxes)} boxes ---")

    start_real = time_module.time()
    failed_stores = 0

    for i, box in enumerate(boxes):
        pos, cost = manager.store_box(box)
        if pos is None:
            failed_stores += 1
        if verbose and (i + 1) % 500 == 0:
            print(f"  Stored {i+1}/{len(boxes)} boxes... "
                  f"(occupancy: {silo.occupancy_rate:.1%})")

    input_real_time = time_module.time() - start_real

    if verbose:
        print(f"  [OK] Input complete: {manager.boxes_stored} stored, "
              f"{failed_stores} failed")
        print(f"  Real time: {input_real_time:.2f}s")
        print(f"  Silo occupancy: {silo.occupancy_rate:.1%}")
        print(f"  Destinations ready for pallet: "
              f"{len(silo.get_destinations_with_enough_boxes(12))}")

    # =========================================================================
    # PHASE 2: OUTPUT - Extract boxes to form pallets
    # =========================================================================
    if verbose:
        print(f"\n--- Phase 2: EXTRACTING pallets ---")

    start_real = time_module.time()
    extraction_result = manager.run_extraction_cycle()
    output_real_time = time_module.time() - start_real

    if verbose:
        print(f"  [OK] Extraction complete:")
        print(f"    Boxes extracted: {extraction_result['boxes_extracted']}")
        print(f"    Pallets completed: {extraction_result['pallets_completed']}")
        print(f"    Pallets incomplete: {extraction_result['pallets_incomplete']}")
        print(f"    Real time: {output_real_time:.2f}s")

    # =========================================================================
    # METRICS
    # =========================================================================
    metrics = manager.get_metrics()
    metrics["scenario"] = {
        "num_destinations": num_destinations,
        "pallets_per_destination": pallets_per_destination,
        "total_boxes_generated": len(boxes),
        "failed_stores": failed_stores,
    }
    metrics["real_time"] = {
        "input_phase": f"{input_real_time:.2f}s",
        "output_phase": f"{output_real_time:.2f}s",
    }

    if verbose:
        print(f"\n--- FINAL METRICS ---")
        print(f"  Pallets completed:     {metrics['pallets_completed']}")
        print(f"  Full pallet %:         {metrics['full_pallet_percentage']}")
        print(f"  Avg time per pallet:   {metrics['avg_time_per_pallet']}")
        print(f"  Total relocations:     {metrics['total_relocations']}")
        print(f"  Max shuttle time:      {metrics['max_shuttle_time']}")
        shuttle_stats = metrics['shuttle_stats']
        print(f"  Shuttle avg time:      {shuttle_stats['avg_time']:.1f}s")
        print(f"  Shuttle max time:      {shuttle_stats['max_time']:.1f}s")
        print(f"  Total shuttle tasks:   {shuttle_stats['total_tasks']}")
        print(f"  Total distance:        {shuttle_stats['total_distance']}")

    return metrics


def run_from_csv(csv_path: str, verbose: bool = True) -> dict:
    """
    Run extraction from a pre-loaded silo state (CSV file).

    The CSV defines the initial occupancy. We skip the input phase
    and go directly to pallet extraction.

    Args:
        csv_path: Path to the silo CSV file (e.g. silo-semi-empty.csv).
        verbose: Print progress.

    Returns:
        Dictionary with all metrics.
    """
    if verbose:
        print(f"\n{'='*70}")
        print(f"  SCENARIO: Load from CSV")
        print(f"  File: {csv_path}")
        print(f"{'='*70}")

    # Initialize system
    silo = Silo()
    shuttle_mgr = ShuttleManager()
    manager = LogisticsManager(silo, shuttle_mgr)

    # Load initial state from CSV
    if verbose:
        print(f"\n--- Loading silo state from CSV ---")

    start_real = time_module.time()
    result = load_silo_from_csv(csv_path, silo)
    all_boxes = result["all_boxes"]
    stats = result["stats"]
    load_time = time_module.time() - start_real

    # Register all loaded boxes in the manager
    manager.all_boxes = all_boxes
    manager.boxes_stored = stats["loaded"]

    if verbose:
        print(f"  Loaded: {stats['loaded']} boxes")
        print(f"  Empty slots: {stats['empty_slots']}")
        print(f"  Skipped/errors: {stats['skipped']}")
        print(f"  Silo occupancy: {silo.occupancy_rate:.1%}")
        print(f"  Unique destinations: {stats['unique_destinations']}")
        print(f"  Load time: {load_time:.3f}s")

        if stats["errors"]:
            print(f"  ERRORS ({len(stats['errors'])}):")
            for err in stats["errors"][:5]:
                print(f"    - {err}")

        # Show destination breakdown
        dest_counts = Counter(b.destination for b in all_boxes.values())
        print(f"\n  --- Destination Breakdown ---")
        print(f"  {'Destination':<15} {'Boxes':>6} {'Full Pallets':>13} {'Remainder':>10}")
        print(f"  {'-'*48}")
        total_pallets = 0
        for dest, count in sorted(dest_counts.items()):
            full = count // 12
            rem = count % 12
            total_pallets += full
            print(f"  {dest:<15} {count:>6} {full:>13} {rem:>10}")
        print(f"  {'-'*48}")
        print(f"  {'TOTAL':<15} {sum(dest_counts.values()):>6} {total_pallets:>13}")

        ready = silo.get_destinations_with_enough_boxes(12)
        print(f"\n  Destinations ready for pallet (>=12 boxes): {len(ready)}")

    # =========================================================================
    # EXTRACTION - Extract boxes to form pallets
    # =========================================================================
    if verbose:
        print(f"\n--- Extracting pallets ---")

    start_real = time_module.time()
    extraction_result = manager.run_extraction_cycle()
    output_real_time = time_module.time() - start_real

    if verbose:
        print(f"  [OK] Extraction complete:")
        print(f"    Boxes extracted: {extraction_result['boxes_extracted']}")
        print(f"    Pallets completed: {extraction_result['pallets_completed']}")
        print(f"    Pallets incomplete: {extraction_result['pallets_incomplete']}")
        print(f"    Real time: {output_real_time:.2f}s")

    # Remaining boxes in silo (not part of any full pallet)
    remaining_in_silo = silo.occupied_count
    remaining_dests = Counter()
    for bid, pos in silo.box_locations.items():
        box = all_boxes.get(bid)
        if box:
            remaining_dests[box.destination] += 1

    if verbose and remaining_in_silo > 0:
        print(f"\n  --- Remaining in Silo (not enough for full pallet) ---")
        print(f"  Total remaining: {remaining_in_silo} boxes")
        for dest, count in sorted(remaining_dests.items()):
            print(f"    {dest}: {count} boxes")

    # =========================================================================
    # METRICS
    # =========================================================================
    metrics = manager.get_metrics()
    metrics["scenario"] = {
        "csv_file": csv_path,
        "initial_boxes": stats["loaded"],
        "unique_destinations": stats["unique_destinations"],
    }
    metrics["real_time"] = {
        "load_phase": f"{load_time:.3f}s",
        "output_phase": f"{output_real_time:.2f}s",
    }
    metrics["remaining_in_silo"] = remaining_in_silo

    if verbose:
        print(f"\n--- FINAL METRICS ---")
        print(f"  Pallets completed:     {metrics['pallets_completed']}")
        print(f"  Full pallet %:         {metrics['full_pallet_percentage']}")
        print(f"  Avg time per pallet:   {metrics['avg_time_per_pallet']}")
        print(f"  Total relocations:     {metrics['total_relocations']}")
        print(f"  Max shuttle time:      {metrics['max_shuttle_time']}")
        print(f"  Remaining in silo:     {remaining_in_silo}")
        shuttle_stats = metrics['shuttle_stats']
        print(f"  Shuttle avg time:      {shuttle_stats['avg_time']:.1f}s")
        print(f"  Shuttle max time:      {shuttle_stats['max_time']:.1f}s")
        print(f"  Total shuttle tasks:   {shuttle_stats['total_tasks']}")
        print(f"  Total distance:        {shuttle_stats['total_distance']}")

    return metrics
