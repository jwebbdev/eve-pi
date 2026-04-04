from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class PlanetType:
    name: str
    type_id: int
    p4_capable: bool
    resources: List[str]
    structures: Dict[str, int]  # role -> type_id


@dataclass
class Planet:
    planet_id: int
    planet_type: PlanetType
    radius_km: float

    @property
    def min_link_distance_km(self) -> float:
        return max(0.0, -0.7716 + 0.012182 * self.radius_km)


@dataclass
class SolarSystem:
    name: str
    system_id: int
    planets: List[Planet] = field(default_factory=list)

    @property
    def planet_composition(self) -> Dict[str, int]:
        counts: Dict[str, int] = {}
        for p in self.planets:
            name = p.planet_type.name
            counts[name] = counts.get(name, 0) + 1
        return counts
