from dataclasses import dataclass
from typing import List, Tuple


@dataclass(frozen=True)
class Material:
    name: str
    tier: str  # "r0", "p1", "p2", "p3", "p4"
    type_id: int
    volume_m3: float


@dataclass(frozen=True)
class Recipe:
    output: str
    tier_from: str  # e.g., "r0", "p1", "p2", "p3"
    tier_to: str    # e.g., "p1", "p2", "p3", "p4"
    inputs: List[Tuple[str, int]]  # [(material_name, quantity_per_cycle), ...]
    output_per_cycle: int
    cycle_seconds: int

    @property
    def output_per_hour(self) -> float:
        return self.output_per_cycle * (3600 / self.cycle_seconds)
