import math
from eve_pi.extraction.decay import calculate_cycle_outputs
from eve_pi.extraction.yield_calc import (
    total_extraction_yield,
    effective_hourly_rate,
    yield_ratio_vs_baseline,
)


def test_single_cycle_output_close_to_base():
    """First cycle output should be close to qty_per_cycle."""
    outputs = list(calculate_cycle_outputs(
        qty_per_cycle=6965, cycle_time_seconds=1800, total_cycles=1,
    ))
    assert len(outputs) == 1
    assert outputs[0] > 6965 * 0.5
    assert outputs[0] < 6965 * 4.0  # bar_width=2.0, noise up to 1.8x


def test_decay_over_time():
    """Later cycles should produce less than earlier cycles on average."""
    outputs = list(calculate_cycle_outputs(
        qty_per_cycle=6965, cycle_time_seconds=1800, total_cycles=48,
    ))
    first_quarter_avg = sum(outputs[:12]) / 12
    last_quarter_avg = sum(outputs[36:]) / 12
    assert last_quarter_avg < first_quarter_avg


def test_simplified_mode_no_noise():
    """Simplified mode should produce monotonically decreasing output."""
    outputs = list(calculate_cycle_outputs(
        qty_per_cycle=6965, cycle_time_seconds=1800, total_cycles=48, simplified=True,
    ))
    for i in range(1, len(outputs)):
        assert outputs[i] <= outputs[i - 1]


def test_total_yield_1day():
    """Total yield for a 1-day program."""
    total = total_extraction_yield(qty_per_cycle=6965, program_duration_hours=24)
    assert total > 0
    assert isinstance(total, int)


def test_effective_hourly_rate():
    """Effective hourly rate should decrease with longer programs."""
    rate_1d = effective_hourly_rate(qty_per_cycle=6965, program_duration_hours=24)
    rate_4d = effective_hourly_rate(qty_per_cycle=6965, program_duration_hours=96)
    assert rate_4d < rate_1d


def test_yield_ratio_4day():
    """4-day cycle should yield roughly 45-50% of 1-day baseline."""
    ratio = yield_ratio_vs_baseline(program_duration_hours=96, baseline_hours=24)
    assert 0.35 < ratio < 0.60
