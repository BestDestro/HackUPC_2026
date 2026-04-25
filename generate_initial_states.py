from pathlib import Path
import random

import pandas as pd


DATA_DIR = Path("data")

ORIGINAL_CSV = DATA_DIR / "silo-semi-empty.csv"
MEDIUM_CSV = DATA_DIR / "silo-medium.csv"
NEARLY_FULL_CSV = DATA_DIR / "silo-nearly-full.csv"

SOURCE = "3055769"


def parse_destination(label: str) -> str | None:
    label = str(label).strip()

    if len(label) != 20 or not label.isdigit():
        return None

    return label[7:15]


def generate_unique_label(destination: str, used_labels: set[str], counter: int) -> str:
    while True:
        bulk_number = 80000 + counter
        label = f"{SOURCE}{destination}{bulk_number:05d}"

        if label not in used_labels:
            used_labels.add(label)
            return label

        counter += 1


def generate_filled_csv(
    input_csv: Path,
    output_csv: Path,
    target_occupancy: float,
    seed: int = 42,
):
    random.seed(seed)

    df = pd.read_csv(input_csv, dtype=str)

    if "posicion" not in df.columns or "etiqueta" not in df.columns:
        raise ValueError("El CSV debe tener columnas: posicion, etiqueta")

    df["posicion"] = df["posicion"].astype(str).str.zfill(11)
    df["etiqueta"] = df["etiqueta"].fillna("").astype(str).str.strip()

    capacity = len(df)
    target_occupied = int(capacity * target_occupancy)

    occupied_mask = df["etiqueta"] != ""
    current_occupied = int(occupied_mask.sum())

    if target_occupied <= current_occupied:
        print(f"{output_csv}: no hace falta rellenar, ya tiene {current_occupied} cajas.")
        df.to_csv(output_csv, index=False)
        return

    existing_destinations = sorted(
        {
            parse_destination(label)
            for label in df.loc[occupied_mask, "etiqueta"]
            if parse_destination(label) is not None
        }
    )

    if not existing_destinations:
        raise ValueError("No se encontraron destinos existentes en el CSV original.")

    used_labels = set(df.loc[occupied_mask, "etiqueta"])

    empty_indices = df[df["etiqueta"] == ""].index.tolist()
    random.shuffle(empty_indices)

    boxes_to_add = target_occupied - current_occupied

    if boxes_to_add > len(empty_indices):
        raise ValueError("No hay suficientes posiciones libres para alcanzar esa ocupación.")

    counter = 0

    for idx in empty_indices[:boxes_to_add]:
        destination = random.choice(existing_destinations)
        new_label = generate_unique_label(destination, used_labels, counter)

        df.loc[idx, "etiqueta"] = new_label
        counter += 1

    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    final_occupied = int((df["etiqueta"] != "").sum())
    print(
        f"{output_csv} generado: "
        f"{final_occupied}/{capacity} cajas "
        f"({final_occupied / capacity * 100:.2f}%)"
    )


def main():
    generate_filled_csv(
        input_csv=ORIGINAL_CSV,
        output_csv=MEDIUM_CSV,
        target_occupancy=0.50,
        seed=42,
    )

    generate_filled_csv(
        input_csv=ORIGINAL_CSV,
        output_csv=NEARLY_FULL_CSV,
        target_occupancy=0.90,
        seed=43,
    )


if __name__ == "__main__":
    main()