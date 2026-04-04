from dataclasses import dataclass


@dataclass
class Character:
    name: str
    ccu_level: int = 4
    max_planets: int = 6
