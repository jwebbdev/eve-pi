"""
CCP's official extraction decay formula.
Source: https://developers.eveonline.com/docs/guides/pi/
"""
import math
from typing import Iterator

DECAY_FACTOR = 0.012  # Dogma attribute 1683
NOISE_FACTOR = 0.8    # Dogma attribute 1687


def calculate_cycle_outputs(
    qty_per_cycle: int,
    cycle_time_seconds: int,
    total_cycles: int,
    simplified: bool = False,
) -> Iterator[int]:
    """
    Yield the R0 output for each cycle of an extraction program.

    Args:
        qty_per_cycle: Base extraction quantity per cycle (from ESI or estimated)
        cycle_time_seconds: Duration of one cycle in seconds
        total_cycles: Number of cycles in the program
        simplified: If True, strip noise for monotonic decay (faster for optimization)

    Yields:
        Integer output for each cycle
    """
    bar_width = cycle_time_seconds / 900.0

    for cycle in range(total_cycles):
        t = (cycle + 0.5) * bar_width
        decay_value = qty_per_cycle / (1.0 + t * DECAY_FACTOR)

        if simplified:
            yield int(bar_width * decay_value)
        else:
            phase_shift = pow(qty_per_cycle, 0.7)
            sin_a = math.cos(phase_shift + t * (1.0 / 12.0))
            sin_b = math.cos(phase_shift / 2.0 + t * 0.2)
            sin_c = math.cos(t * 0.5)
            sin_stuff = max((sin_a + sin_b + sin_c) / 3.0, 0.0)
            bar_height = decay_value * (1.0 + NOISE_FACTOR * sin_stuff)
            yield int(bar_width * bar_height)
