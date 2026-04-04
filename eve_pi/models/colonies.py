from dataclasses import dataclass


@dataclass(frozen=True)
class Facility:
    name: str
    cpu_tf: int
    power_mw: int
    storage_m3: int = 0


@dataclass(frozen=True)
class CommandCenterLevel:
    level: int
    cpu_tf: int
    power_mw: int
    storage_m3: int
