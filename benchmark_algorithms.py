"""
Benchmark multiple logistics algorithms against the initial CSV and generated
initial states.

Example:
  python benchmark_algorithms.py --incoming 1000
  python benchmark_algorithms.py --algorithms baseline retrieval_friendly throughput
"""

import argparse
import csv
import random
import time
from pathlib import Path

from concurrent_sim import available_algorithm_configs, run_concurrent_from_csv


DEFAULT_STATE_SPECS = {
    "initial": None,
    "light_25": 0.25,
    "medium_45": 0.45,
    "heavy_70": 0.70,
}


def _read_csv_rows(csv_path: Path):
    with csv_path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        return list(reader)


def _write_csv_rows(csv_path: Path, rows):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["posicion", "etiqueta"])
        writer.writeheader()
        writer.writerows(rows)


def _extract_destinations(rows):
    destinations = sorted({r["etiqueta"][7:15] for r in rows if r.get("etiqueta")})
    if not destinations:
        raise ValueError("No destinations found in base CSV")
    return destinations


def _make_variant_rows(base_rows, occupancy, seed):
    rng = random.Random(seed)
    total_slots = len(base_rows)
    target_occupied = int(round(total_slots * occupancy))

    occupied = [r.copy() for r in base_rows if r.get("etiqueta")]
    empty = [r.copy() for r in base_rows if not r.get("etiqueta")]
    destinations = _extract_destinations(base_rows)
    used_labels = {r["etiqueta"] for r in occupied}

    rng.shuffle(occupied)
    rng.shuffle(empty)

    selected = occupied[: min(len(occupied), target_occupied)]
    needed = max(0, target_occupied - len(selected))

    generated_counter = 0
    for row in empty[:needed]:
        while True:
            dest = destinations[generated_counter % len(destinations)]
            label = f"3055769{dest}{generated_counter:05d}"
            generated_counter += 1
            if label not in used_labels:
                used_labels.add(label)
                break
        selected.append({"posicion": row["posicion"], "etiqueta": label})

    selected_by_pos = {r["posicion"]: r["etiqueta"] for r in selected}
    variant_rows = []
    for row in base_rows:
        label = selected_by_pos.get(row["posicion"], "")
        variant_rows.append({"posicion": row["posicion"], "etiqueta": label})
    return variant_rows


def prepare_initial_states(base_csv: Path, output_dir: Path, state_specs, seed: int):
    rows = _read_csv_rows(base_csv)
    states = {}

    for state_name, occupancy in state_specs.items():
        if occupancy is None:
            states[state_name] = base_csv
            continue

        variant_path = output_dir / f"silo-{state_name}.csv"
        variant_rows = _make_variant_rows(rows, occupancy, seed + len(states) * 101)
        _write_csv_rows(variant_path, variant_rows)
        states[state_name] = variant_path

    return states


def _parse_number(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace("%", "").replace("s", "").replace("h", "")
    try:
        return float(text)
    except ValueError:
        return 0.0


def _score(metrics):
    # Primary goal: complete more pallets. Tie-breakers: retrieve more boxes,
    # finish earlier, and avoid relocations.
    return (
        metrics["pallets_completed"] * 100_000
        + metrics["boxes_retrieved"] * 100
        - _parse_number(metrics["sim_time"]) * 0.1
        - metrics["total_relocations"] * 5
    )


def run_benchmark(args):
    base_csv = Path(args.csv).resolve()
    output_dir = Path(args.output_dir).resolve()
    states_dir = output_dir / "states"
    state_specs = {
        name: DEFAULT_STATE_SPECS[name]
        for name in args.states
    }
    states = prepare_initial_states(base_csv, states_dir, state_specs, args.seed)

    algorithms = args.algorithms or available_algorithm_configs()
    rows = []

    started = time.time()
    total_runs = len(states) * len(algorithms)
    run_idx = 0

    for state_name, state_path in states.items():
        for algorithm in algorithms:
            run_idx += 1
            print(f"[{run_idx:>3}/{total_runs}] {state_name:<10} {algorithm:<22}", flush=True)
            metrics = run_concurrent_from_csv(
                str(state_path),
                num_incoming=args.incoming,
                num_destinations=args.destinations,
                algorithm_config=algorithm,
                verbose=False,
            )

            rows.append({
                "state": state_name,
                "algorithm": algorithm,
                "incoming": args.incoming,
                "destinations": args.destinations,
                "sim_time": metrics["sim_time"],
                "boxes_stored": metrics["boxes_stored"],
                "boxes_retrieved": metrics["boxes_retrieved"],
                "pallets_completed": metrics["pallets_completed"],
                "full_pallet_pct": metrics["full_pallet_pct"],
                "avg_time_per_pallet": metrics["avg_time_per_pallet"],
                "total_relocations": metrics["total_relocations"],
                "remaining_in_silo": metrics["remaining_in_silo"],
                "silo_occupancy": metrics["silo_occupancy"],
                "score": round(_score(metrics), 2),
                "real_compute_time": metrics["real_compute_time"],
            })

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "algorithm_benchmark.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    md_path = output_dir / "algorithm_benchmark.md"
    write_markdown_report(md_path, rows, time.time() - started)

    print(f"\nResults written to: {csv_path}")
    print(f"Report written to:  {md_path}")


def write_markdown_report(path: Path, rows, elapsed):
    by_algorithm = {}
    for row in rows:
        by_algorithm.setdefault(row["algorithm"], []).append(row)

    summary = []
    for algorithm, alg_rows in by_algorithm.items():
        avg_score = sum(r["score"] for r in alg_rows) / len(alg_rows)
        pallets = sum(r["pallets_completed"] for r in alg_rows)
        retrieved = sum(r["boxes_retrieved"] for r in alg_rows)
        relocations = sum(r["total_relocations"] for r in alg_rows)
        avg_time = sum(_parse_number(r["sim_time"]) for r in alg_rows) / len(alg_rows)
        summary.append((avg_score, algorithm, pallets, retrieved, relocations, avg_time))

    summary.sort(reverse=True)

    lines = [
        "# Algorithm benchmark",
        "",
        f"Runs: {len(rows)}",
        f"Real compute time: {elapsed:.2f}s",
        "",
        "## Overall ranking",
        "",
        "| Rank | Algorithm | Avg score | Pallets | Boxes retrieved | Relocations | Avg sim time |",
        "|---:|---|---:|---:|---:|---:|---:|",
    ]

    for idx, (avg_score, algorithm, pallets, retrieved, relocations, avg_time) in enumerate(summary, 1):
        lines.append(
            f"| {idx} | {algorithm} | {avg_score:.1f} | {pallets} | "
            f"{retrieved} | {relocations} | {avg_time:.1f}s |"
        )

    lines.extend([
        "",
        "## Per-state winners",
        "",
        "| State | Winner | Pallets | Boxes retrieved | Relocations | Sim time |",
        "|---|---|---:|---:|---:|---:|",
    ])

    for state in sorted({r["state"] for r in rows}):
        state_rows = [r for r in rows if r["state"] == state]
        winner = max(state_rows, key=lambda r: r["score"])
        lines.append(
            f"| {state} | {winner['algorithm']} | {winner['pallets_completed']} | "
            f"{winner['boxes_retrieved']} | {winner['total_relocations']} | "
            f"{winner['sim_time']:.1f}s |"
        )

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args():
    parser = argparse.ArgumentParser(description="Compare logistics algorithm configs")
    parser.add_argument("--csv", default="data/silo-semi-empty.csv")
    parser.add_argument("--incoming", type=int, default=600)
    parser.add_argument("--destinations", type=int, default=20)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", default="benchmark_results")
    parser.add_argument(
        "--states",
        nargs="+",
        choices=list(DEFAULT_STATE_SPECS),
        default=list(DEFAULT_STATE_SPECS),
    )
    parser.add_argument(
        "--algorithms",
        nargs="+",
        choices=available_algorithm_configs(),
        default=None,
    )
    return parser.parse_args()


if __name__ == "__main__":
    run_benchmark(parse_args())
