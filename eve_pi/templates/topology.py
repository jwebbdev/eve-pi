"""Topology definitions for PI colony templates."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Tuple


class PinRole(Enum):
    LAUNCHPAD = "launchpad"
    BASIC_FACTORY = "basic_factory"
    ADVANCED_FACTORY = "advanced_factory"
    HIGHTECH_FACTORY = "hightech_factory"
    STORAGE = "storage"
    EXTRACTOR = "extractor"
    COMMAND_CENTER = "command_center"


@dataclass
class Topology:
    name: str
    pins: List[Dict]  # Each has: role (PinRole), latitude, longitude, optional heads/schematic
    links: List[Tuple[int, int]]  # Pairs of pin indices
    routes: List[Dict] = field(default_factory=list)

    def pin_indices_by_role(self, role: PinRole) -> List[int]:
        return [i for i, p in enumerate(self.pins) if p["role"] == role]
