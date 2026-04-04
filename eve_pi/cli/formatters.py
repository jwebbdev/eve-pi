"""Output formatting for CLI results."""
from eve_pi.optimizer.allocator import OptimizationConstraints, OptimizationResult


def format_result(result: OptimizationResult, constraints: OptimizationConstraints = None) -> str:
    """Format optimization result for display.

    If constraints are provided and mode is self_sufficient, uses the new
    shipping plan + stockpile format. Otherwise falls back to the original format.
    """
    if constraints and constraints.mode == "self_sufficient":
        return _format_self_sufficient(result, constraints)
    return _format_default(result)


def _format_default(result: OptimizationResult) -> str:
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


def _format_self_sufficient(result: OptimizationResult, constraints: OptimizationConstraints) -> str:
    lines = []
    lines.append("=" * 80)
    lines.append("OPTIMIZATION RESULT -- Self-Sufficient")
    lines.append("=" * 80)
    lines.append("")

    # Build grouped display: factory chains show feeders indented beneath
    feed = result.feed_assignments
    feed_by_factory: dict = {}
    for a in feed:
        factory_product = a.feeds.replace("-> ", "").replace(" factory", "") if a.feeds else ""
        if factory_product not in feed_by_factory:
            feed_by_factory[factory_product] = []
        feed_by_factory[factory_product].append(a)

    # Manufacturing section (highest priority)
    manufacturing = result.manufacturing_assignments
    if manufacturing or constraints.manufacturing_needs:
        lines.append("MANUFACTURING (internal use, not exported):")
        if manufacturing:
            lines.append("")
            lines.append(f"  {'#':<3} {'Product':<20} {'Setup':<12} {'Planet':<10} {'Character':<16} {'ISK/day':>12} {'units/wk':>10}")
            lines.append(f"  {'--':<3} {'--------------------':<20} {'------------':<12} {'----------':<10} {'----------------':<16} {'----------':>12} {'--------':>10}")
            idx = 0
            for a in manufacturing:
                idx += 1
                # Estimate weekly output from volume
                output_units_per_week = a.volume_per_day * 7
                lines.append(
                    f"  {idx:<3} {a.product:<20} {a.setup.value:<12} {a.planet_type:<10} "
                    f"{a.character:<16} {a.isk_per_day:>12,.0f} {output_units_per_week:>10,.0f}"
                )
                feeders = feed_by_factory.get(a.product, [])
                for fa in feeders:
                    lines.append(
                        f"      -> {fa.product:<18} {fa.setup.value:<12} {fa.planet_type:<10} "
                        f"{fa.character:<16} {'':>12} {'[feed]':>10}"
                    )
        else:
            lines.append("  (Could not allocate manufacturing needs — check planet availability)")
        lines.append("")

    # Shipping plan section
    trips = constraints.hauling_trips_per_week
    cargo = constraints.cargo_capacity_m3
    max_vol_week = constraints.max_volume_per_week
    lines.append(
        f"SHIPPING PLAN ({trips} trips/week x {cargo:,.0f} m3 = {max_vol_week:,.0f} m3/week):"
    )
    lines.append(f"  Shipped ISK/week:  {result.shipped_isk_per_week:>15,.0f}")
    lines.append(f"  Shipped volume/week: {result.shipped_volume_per_week:>12,.0f} m3")
    lines.append("")

    shipped = result.shipped_assignments
    if shipped:
        lines.append(f"  {'#':<3} {'Product':<20} {'Setup':<12} {'Planet':<10} {'Character':<16} {'ISK/day':>12} {'m3/day':>8}")
        lines.append(f"  {'--':<3} {'--------------------':<20} {'------------':<12} {'----------':<10} {'----------------':<16} {'----------':>12} {'------':>8}")
        idx = 0
        for a in shipped:
            idx += 1
            lines.append(
                f"  {idx:<3} {a.product:<20} {a.setup.value:<12} {a.planet_type:<10} "
                f"{a.character:<16} {a.isk_per_day:>12,.0f} {a.volume_per_day:>8,.0f}"
            )
            # Show feeders for this factory
            feeders = feed_by_factory.get(a.product, [])
            for fa in feeders:
                lines.append(
                    f"      -> {fa.product:<18} {fa.setup.value:<12} {fa.planet_type:<10} "
                    f"{fa.character:<16} {'':>12} {'[feed]':>8}"
                )
    lines.append("")

    # Stockpile section
    stockpile = result.stockpile_assignments
    if stockpile:
        lines.append("STOCKPILE (produce locally, export when convenient):")
        lines.append(f"  Stockpile ISK/week: {result.stockpile_isk_per_day * 7:>14,.0f}")
        lines.append("")
        lines.append(f"  {'#':<3} {'Product':<20} {'Setup':<12} {'Planet':<10} {'Character':<16} {'ISK/day':>12} {'m3/day':>8}")
        lines.append(f"  {'--':<3} {'--------------------':<20} {'------------':<12} {'----------':<10} {'----------------':<16} {'----------':>12} {'------':>8}")
        for i, a in enumerate(stockpile, 1):
            lines.append(
                f"  {i:<3} {a.product:<20} {a.setup.value:<12} {a.planet_type:<10} "
                f"{a.character:<16} {a.isk_per_day:>12,.0f} {a.volume_per_day:>8,.0f}"
            )
        lines.append("")

    lines.append(
        f"TOTAL: {len(result.assignments)} colonies, "
        f"{result.total_isk_per_week:,.0f} ISK/week potential"
    )

    return "\n".join(lines)
