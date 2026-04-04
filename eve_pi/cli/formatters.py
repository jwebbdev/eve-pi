"""Output formatting for CLI results."""
from eve_pi.optimizer.allocator import OptimizationResult


def format_result(result: OptimizationResult) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("OPTIMIZATION RESULT")
    lines.append("=" * 80)
    lines.append("")
    lines.append(f"Total ISK/day:  {result.total_isk_per_day:>15,.0f}")
    lines.append(f"Total ISK/week: {result.total_isk_per_week:>15,.0f}")
    lines.append(f"Total volume/day: {result.total_volume_per_day:>12,.0f} m3")
    lines.append(f"Total volume/week: {result.total_volume_per_week:>11,.0f} m3")
    lines.append(f"Colonies: {len(result.assignments)}")
    lines.append("")
    lines.append("-" * 80)
    lines.append(f"{'#':<3} {'Product':<30} {'Setup':<12} {'Planet':<10} {'ISK/day':>12} {'m3/day':>8}")
    lines.append("-" * 80)
    for i, a in enumerate(result.assignments, 1):
        lines.append(
            f"{i:<3} {a.product:<30} {a.setup.value:<12} {a.planet_type:<10} "
            f"{a.isk_per_day:>12,.0f} {a.volume_per_day:>8,.0f}"
        )
    lines.append("-" * 80)
    return "\n".join(lines)
