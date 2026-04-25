from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class Position:
    aisle: int
    side: int
    x: int
    y: int
    z: int

    @staticmethod
    def from_compact(value: str) -> "Position":
        """
        Convierte una posición tipo '01010010101' en:
        aisle=1, side=1, x=1, y=1, z=1

        Formato:
        AA SS XXX YY ZZ
        """
        value = str(value).strip().zfill(11)

        if len(value) != 11 or not value.isdigit():
            raise ValueError(f"Posición inválida: {value}")

        return Position(
            aisle=int(value[0:2]),
            side=int(value[2:4]),
            x=int(value[4:7]),
            y=int(value[7:9]),
            z=int(value[9:11]),
        )

    def to_compact(self) -> str:
        return (
            f"{self.aisle:02d}"
            f"{self.side:02d}"
            f"{self.x:03d}"
            f"{self.y:02d}"
            f"{self.z:02d}"
        )


@dataclass
class Box:
    box_id: str
    source: str
    destination: str
    bulk_number: str
    position: Optional[Position] = None

    @staticmethod
    def from_label(label: str) -> "Box":
        """
        Convierte una etiqueta de caja de 20 dígitos en:
        source      = primeros 7 dígitos
        destination = siguientes 8 dígitos
        bulk_number = últimos 5 dígitos
        """
        label = str(label).strip()

        if len(label) != 20 or not label.isdigit():
            raise ValueError(f"Etiqueta de caja inválida: {label}")

        return Box(
            box_id=label,
            source=label[0:7],
            destination=label[7:15],
            bulk_number=label[15:20],
        )