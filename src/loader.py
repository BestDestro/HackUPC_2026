import csv
from pathlib import Path

from .models import Position, Box
from .silo import Silo


def load_silo_from_csv(csv_path: str | Path) -> Silo:
    csv_path = Path(csv_path)

    if not csv_path.exists():
        raise FileNotFoundError(f"No existe el CSV: {csv_path}")

    silo = Silo()

    loaded_boxes = 0
    skipped_empty = 0

    with csv_path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        expected_columns = {"posicion", "etiqueta"}
        actual_columns = set(reader.fieldnames or [])

        if not expected_columns.issubset(actual_columns):
            raise ValueError(
                f"El CSV debe tener columnas {expected_columns}. "
                f"Columnas encontradas: {actual_columns}"
            )

        for row_number, row in enumerate(reader, start=2):
            raw_position = str(row["posicion"]).strip()
            raw_label = str(row["etiqueta"]).strip()

            if raw_label == "" or raw_label.lower() == "nan":
                skipped_empty += 1
                continue

            try:
                position = Position.from_compact(raw_position)
                box = Box.from_label(raw_label)
                silo.add_box(box, position)
                loaded_boxes += 1

            except Exception as error:
                raise ValueError(
                    f"Error en fila {row_number}: "
                    f"posicion={raw_position}, etiqueta={raw_label}. "
                    f"Detalle: {error}"
                ) from error

    print(f"CSV loaded: {csv_path}")
    print(f"Boxes loaded: {loaded_boxes}")
    print(f"Empty rows skipped: {skipped_empty}")

    return silo