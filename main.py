from pathlib import Path

from src.loader import load_silo_from_csv


def main():
    csv_path = Path("data/silo-semi-empty.csv")

    silo = load_silo_from_csv(csv_path)

    silo.print_stats()
    silo.print_destinations_summary()


if __name__ == "__main__":
    main()