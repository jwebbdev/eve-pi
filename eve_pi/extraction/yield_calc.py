"""Higher-level extraction yield calculations."""
from eve_pi.extraction.decay import calculate_cycle_outputs


def _program_cycle_time(duration_hours: float) -> int:
    """Determine the cycle time CCP uses for a given program duration."""
    if duration_hours <= 25:
        return 1800   # 30 minutes
    elif duration_hours <= 50:
        return 3600   # 1 hour
    elif duration_hours <= 100:
        return 7200   # 2 hours
    elif duration_hours <= 200:
        return 14400  # 4 hours
    else:
        return 28800  # 8 hours


def total_extraction_yield(
    qty_per_cycle: int,
    program_duration_hours: float,
    simplified: bool = True,
) -> int:
    """Calculate total R0 extracted over a program of given duration."""
    cycle_time = _program_cycle_time(program_duration_hours)
    total_seconds = int(program_duration_hours * 3600)
    total_cycles = total_seconds // cycle_time

    return sum(calculate_cycle_outputs(
        qty_per_cycle=qty_per_cycle,
        cycle_time_seconds=cycle_time,
        total_cycles=total_cycles,
        simplified=simplified,
    ))


def effective_hourly_rate(
    qty_per_cycle: int,
    program_duration_hours: float,
    simplified: bool = True,
) -> float:
    """Calculate the effective average R0/hour over a program."""
    total = total_extraction_yield(qty_per_cycle, program_duration_hours, simplified)
    return total / program_duration_hours


def yield_ratio_vs_baseline(
    program_duration_hours: float,
    baseline_hours: float = 24.0,
    qty_per_cycle: int = 6965,
) -> float:
    """
    Calculate the yield ratio of a program vs a baseline program.
    Returns a ratio < 1.0 (longer programs yield less per hour).
    """
    rate_program = effective_hourly_rate(qty_per_cycle, program_duration_hours)
    rate_baseline = effective_hourly_rate(qty_per_cycle, baseline_hours)
    return rate_program / rate_baseline if rate_baseline > 0 else 0.0
