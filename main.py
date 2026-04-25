"""
main.py - Entry point for the Hack the Flow logistics simulation.

Modes:
  python main.py concurrent <csv>          # Concurrent input+output (default 1000 boxes)
  python main.py concurrent <csv> <N>      # Concurrent with N incoming boxes
  python main.py csv <file>                # Extract-only from CSV
  python main.py                           # All synthetic scenarios (20, 40, 80)
  python main.py 20                        # Single synthetic scenario
"""

import sys
import os
from simulation import run_scenario, run_from_csv
from concurrent_sim import run_concurrent_from_csv


def print_comparison(results: dict):
    """Print a side-by-side comparison of all scenario results."""
    print(f"\n{'='*80}")
    print(f"{'COMPARISON ACROSS ALL SCENARIOS':^80}")
    print(f"{'='*80}")

    header = f"{'Metric':<30}"
    for n in sorted(results.keys()):
        header += f"{'  ' + str(n) + ' Dests':>16}"
    print(header)
    print("-" * 80)

    rows = [
        ("Pallets Completed", "pallets_completed"),
        ("Full Pallet %", "full_pallet_percentage"),
        ("Avg Time/Pallet", "avg_time_per_pallet"),
        ("Total Relocations", "total_relocations"),
        ("Max Shuttle Time", "max_shuttle_time"),
        ("Silo Occupancy", "silo_occupancy"),
    ]

    for label, key in rows:
        row = f"{label:<30}"
        for n in sorted(results.keys()):
            val = results[n].get(key, "N/A")
            row += f"{str(val):>16}"
        print(row)

    print("-" * 80)
    shuttle_rows = [
        ("Shuttle Avg Time", "avg_time"),
        ("Shuttle Max Time", "max_time"),
        ("Total Tasks", "total_tasks"),
        ("Total Distance", "total_distance"),
    ]

    for label, key in shuttle_rows:
        row = f"{label:<30}"
        for n in sorted(results.keys()):
            val = results[n].get("shuttle_stats", {}).get(key, "N/A")
            if isinstance(val, float):
                val = f"{val:.1f}"
            row += f"{str(val):>16}"
        print(row)

    print(f"{'='*80}\n")


def main():
    print("+==============================================================+")
    print("|           HACK THE FLOW - Logistics Simulator               |")
    print("|    Chaotic Storage + Greedy Algorithms + Hash Maps          |")
    print("+==============================================================+")

    # CONCURRENT MODE: python main.py concurrent <csv> [N_boxes]
    if len(sys.argv) >= 2 and sys.argv[1].lower() == "concurrent":
        csv_path = sys.argv[2] if len(sys.argv) >= 3 else "silo-semi-empty.csv"
        num_incoming = int(sys.argv[3]) if len(sys.argv) >= 4 else 1000

        if not os.path.exists(csv_path):
            print(f"ERROR: CSV file not found: {csv_path}")
            sys.exit(1)

        run_concurrent_from_csv(csv_path, num_incoming=num_incoming, verbose=True)
        return

    # CSV EXTRACT-ONLY MODE: python main.py csv <file>
    if len(sys.argv) >= 2 and sys.argv[1].lower() == "csv":
        csv_path = sys.argv[2] if len(sys.argv) >= 3 else "silo-semi-empty.csv"
        if not os.path.exists(csv_path):
            print(f"ERROR: CSV file not found: {csv_path}")
            sys.exit(1)
        run_from_csv(csv_path, verbose=True)
        return

    # SYNTHETIC MODE
    scenarios = [20, 40, 80]
    if len(sys.argv) > 1:
        try:
            requested = int(sys.argv[1])
            if requested in scenarios:
                scenarios = [requested]
            else:
                print(f"Invalid scenario: {requested}. Choose from: 20, 40, 80")
                print(f"Or use: python main.py concurrent <csv> [N]")
                sys.exit(1)
        except ValueError:
            print(f"Usage:")
            print(f"  python main.py                         # All synthetic")
            print(f"  python main.py 20                      # Single synthetic")
            print(f"  python main.py csv <file>              # Extract-only from CSV")
            print(f"  python main.py concurrent <csv> [N]    # Concurrent I/O")
            sys.exit(1)

    results = {}
    for num_dest in scenarios:
        max_pallets = 7680 // (num_dest * 12)
        pallets = min(max_pallets, 5)
        metrics = run_scenario(
            num_destinations=num_dest,
            pallets_per_destination=pallets,
            seed=42, verbose=True,
        )
        results[num_dest] = metrics

    if len(results) > 1:
        print_comparison(results)


if __name__ == "__main__":
    main()
