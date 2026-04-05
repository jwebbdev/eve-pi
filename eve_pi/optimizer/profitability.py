"""Calculate ISK/day for different colony setups."""
from typing import Dict, Optional
from eve_pi.capacity.planet_capacity import SetupType
from eve_pi.data.loader import GameData
from eve_pi.extraction.yield_calc import yield_ratio_vs_baseline
from eve_pi.market.esi import MarketData


def calculate_extraction_profit(
    p1_name: str,
    market_data: Dict[str, MarketData],
    extraction_rate_r0_per_hour: int,
    cycle_days: float,
    num_factories: int,
    tax_rate: float,
    game_data: GameData,
    use_sell_orders: bool = False,
) -> float:
    """
    Calculate daily ISK profit for an R0->P1 extraction colony.
    """
    mkt = market_data.get(p1_name)
    if not mkt:
        return 0.0
    recipe = game_data.get_recipe("r0_to_p1", p1_name)
    if not recipe:
        return 0.0
    p1_per_hour = num_factories * recipe.output_per_hour
    ratio = yield_ratio_vs_baseline(
        program_duration_hours=cycle_days * 24, baseline_hours=24.0,
    )
    effective_p1_per_hour = p1_per_hour * ratio
    daily_output = effective_p1_per_hour * 24
    sell_price = mkt.get_sell_price(use_sell_orders)
    revenue = daily_output * sell_price
    export_tax = revenue * tax_rate
    return revenue - export_tax


def calculate_factory_profit(
    product_name: str,
    setup: SetupType,
    num_factories: int,
    market_data: Dict[str, MarketData],
    tax_rate: float,
    game_data: GameData,
    use_sell_orders: bool = False,
) -> float:
    """Calculate daily ISK profit for a factory colony (buy inputs, sell output)."""
    tier_key = {
        SetupType.P1_TO_P2: "p1_to_p2",
        SetupType.P2_TO_P3: "p2_to_p3",
        SetupType.P3_TO_P4: "p3_to_p4",
    }.get(setup)
    if not tier_key:
        return 0.0
    recipe = game_data.get_recipe(tier_key, product_name)
    if not recipe:
        return 0.0
    output_mkt = market_data.get(product_name)
    if not output_mkt:
        return 0.0
    output_per_hour = recipe.output_per_hour * num_factories
    daily_output = output_per_hour * 24
    sell_price = output_mkt.get_sell_price(use_sell_orders)
    revenue = daily_output * sell_price
    export_tax = revenue * tax_rate
    input_cost = 0.0
    import_tax = 0.0
    for input_name, qty_per_cycle in recipe.inputs:
        input_mkt = market_data.get(input_name)
        if not input_mkt:
            return 0.0
        input_per_hour = qty_per_cycle * (3600 / recipe.cycle_seconds) * num_factories
        daily_input = int(input_per_hour * 24)
        _, cost, _ = input_mkt.get_purchase_cost(daily_input)
        input_cost += cost
        import_tax += cost * tax_rate
    return revenue - export_tax - input_cost - import_tax


def calculate_r0_p2_profit(
    p2_name: str,
    market_data: Dict[str, MarketData],
    extraction_rate_r0_per_hour: int,
    cycle_days: float,
    tax_rate: float,
    game_data: GameData,
    use_sell_orders: bool = False,
) -> float:
    """Calculate daily ISK profit for an R0->P2 single-planet extraction colony."""
    output_mkt = market_data.get(p2_name)
    if not output_mkt:
        return 0.0
    p2_per_hour = 5.0
    ratio = yield_ratio_vs_baseline(
        program_duration_hours=cycle_days * 24, baseline_hours=24.0,
    )
    effective_p2_per_hour = p2_per_hour * ratio
    daily_output = effective_p2_per_hour * 24
    sell_price = output_mkt.get_sell_price(use_sell_orders)
    revenue = daily_output * sell_price
    export_tax = revenue * tax_rate
    return revenue - export_tax
