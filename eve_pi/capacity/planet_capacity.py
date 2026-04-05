"""Calculate what colony setups fit on a given planet based on CPU/PG budget."""
from enum import Enum
from typing import Dict, Tuple
from eve_pi.data.loader import GameData


class SetupType(Enum):
    R0_TO_P1 = "r0_to_p1"
    R0_TO_P2 = "r0_to_p2"
    P1_TO_P2 = "p1_to_p2"
    P2_TO_P3 = "p2_to_p3"
    P3_TO_P4 = "p3_to_p4"


LAUNCHPAD_COUNT = {
    SetupType.R0_TO_P1: 1,
    SetupType.R0_TO_P2: 1,
    SetupType.P1_TO_P2: 1,
    SetupType.P2_TO_P3: 1,
    SetupType.P3_TO_P4: 2,
}

FACTORY_TYPE = {
    SetupType.R0_TO_P1: "basic_factory",
    SetupType.R0_TO_P2: "advanced_factory",
    SetupType.P1_TO_P2: "advanced_factory",
    SetupType.P2_TO_P3: "advanced_factory",
    SetupType.P3_TO_P4: "hightech_factory",
}


def min_link_distance(radius_km: float) -> float:
    """Minimum achievable link distance for a planet of given radius."""
    return max(0.0, -0.7716 + 0.012182 * radius_km)


def link_costs(distance_km: float) -> Tuple[float, float]:
    """Calculate link power (MW) and CPU (tf) for a given distance. Returns (power_mw, cpu_tf)."""
    power = 10.9952 + 0.1433 * distance_km
    cpu = 15.6475 + 0.1995 * distance_km
    return power, cpu


def calculate_lp_count(num_factories: int, setup: SetupType, game_data: GameData,
                       cycle_days: float = 4.0, product_name: str = None) -> int:
    """Calculate how many launchpads are needed based on factory throughput and cycle length.

    LP capacity is 10,000 m³. Factory planets need to hold cycle_days worth of inputs.
    """
    if setup in (SetupType.R0_TO_P1, SetupType.R0_TO_P2):
        return 1  # Extraction planets just need 1 LP for export

    # Determine input volume per hour for the factory setup
    tier_key = {
        SetupType.P1_TO_P2: "p1_to_p2",
        SetupType.P2_TO_P3: "p2_to_p3",
        SetupType.P3_TO_P4: "p3_to_p4",
    }.get(setup)

    if not tier_key:
        return 1

    # Get a representative recipe for volume calculation
    recipes = game_data.recipes.get(tier_key, {})
    if product_name and product_name in recipes:
        recipe = recipes[product_name]
    elif recipes:
        recipe = next(iter(recipes.values()))
    else:
        return 1

    # Calculate total input volume per hour
    input_vol_per_hour = 0.0
    for mat_name, qty_per_cycle in recipe.inputs:
        mat = game_data.materials.get(mat_name)
        vol = mat.volume_m3 if mat else 0.38
        qty_per_hour = qty_per_cycle * (3600 / recipe.cycle_seconds) * num_factories
        input_vol_per_hour += qty_per_hour * vol

    # Total volume needed for cycle_days
    total_vol = input_vol_per_hour * 24 * cycle_days

    # Each LP holds 10,000 m³
    import math
    lp_count = max(1, math.ceil(total_vol / 10000))

    return lp_count


def can_fit(
    radius_km: float,
    ccu_level: int,
    setup: SetupType,
    game_data: GameData,
    product_name: str = None,
    cycle_days: float = 4.0,
) -> Tuple[bool, int, Dict]:
    """
    Determine if a planet can support a setup and how many output factories fit.
    Returns (fits, max_output_factories, details_dict)
    """
    cc = game_data.command_center_levels.get(ccu_level)
    if cc is None:
        return False, 0, {"error": f"Invalid CCU level: {ccu_level}"}

    available_cpu = cc.cpu_tf
    available_power = cc.power_mw

    min_dist = min_link_distance(radius_km)
    link_power, link_cpu = link_costs(min_dist)
    link_power_per_factory = link_power * 1.5
    link_cpu_per_factory = link_cpu * 1.5

    lp = game_data.facilities["launchpad"]
    lp_count = LAUNCHPAD_COUNT.get(setup, 1)
    lp_total_cpu = lp.cpu_tf * lp_count
    lp_total_power = lp.power_mw * lp_count

    remaining_cpu = available_cpu - lp_total_cpu
    remaining_power = available_power - lp_total_power

    if remaining_cpu <= 0 or remaining_power <= 0:
        return False, 0, {
            "error": "Launchpads exceed CC capacity",
            "available_cpu": available_cpu, "available_power": available_power,
            "launchpad_cpu": lp_total_cpu, "launchpad_power": lp_total_power,
        }

    details = {
        "radius_km": radius_km, "ccu_level": ccu_level,
        "min_link_distance_km": min_dist, "launchpad_count": lp_count,
        "available_cpu": available_cpu, "available_power": available_power,
    }

    if setup == SetupType.R0_TO_P1:
        return _fit_extraction(remaining_cpu, remaining_power,
                               link_power_per_factory, link_cpu_per_factory, game_data, details)
    elif setup == SetupType.R0_TO_P2:
        return _fit_r0_to_p2(remaining_cpu, remaining_power,
                             link_power_per_factory, link_cpu_per_factory, game_data, details)
    else:
        return _fit_factory(available_cpu, available_power, link_power_per_factory,
                            link_cpu_per_factory, setup, game_data, details,
                            product_name, cycle_days)


def _fit_factory(available_cpu, available_power, link_power_per_factory,
                 link_cpu_per_factory, setup, game_data, details,
                 product_name=None, cycle_days=4.0):
    """Iteratively find max factories, accounting for LP count growing with throughput."""
    factory_key = FACTORY_TYPE[setup]
    factory = game_data.facilities[factory_key]
    lp = game_data.facilities["launchpad"]

    cost_per_factory_cpu = factory.cpu_tf + link_cpu_per_factory
    cost_per_factory_power = factory.power_mw + link_power_per_factory

    # Try increasing factory counts until budget exceeded
    best_factories = 0
    best_lp_count = 1

    for n_factories in range(1, 50):
        lp_count = calculate_lp_count(n_factories, setup, game_data, cycle_days, product_name)
        # Each LP also has a link
        lp_total_cpu = lp.cpu_tf * lp_count + link_cpu_per_factory * lp_count
        lp_total_power = lp.power_mw * lp_count + link_power_per_factory * lp_count

        factory_total_cpu = cost_per_factory_cpu * n_factories
        factory_total_power = cost_per_factory_power * n_factories

        total_cpu = lp_total_cpu + factory_total_cpu
        total_power = lp_total_power + factory_total_power

        if total_cpu <= available_cpu and total_power <= available_power:
            best_factories = n_factories
            best_lp_count = lp_count
        else:
            break

    details["factory_type"] = factory_key
    details["max_factories"] = best_factories
    details["launchpad_count"] = best_lp_count
    details["cost_per_factory_cpu"] = cost_per_factory_cpu
    details["cost_per_factory_power"] = cost_per_factory_power
    return best_factories > 0, best_factories, details


def _fit_extraction(remaining_cpu, remaining_power, link_power_per_factory,
                    link_cpu_per_factory, game_data, details):
    basic = game_data.facilities["basic_factory"]
    head = game_data.facilities["extractor_head"]
    ecu_base = game_data.facilities.get("extractor_base")
    ecu_base_cpu = ecu_base.cpu_tf if ecu_base else 400
    ecu_base_power = ecu_base.power_mw if ecu_base else 2600

    # Reserve ECU base structure cost (1 ECU for R0→P1)
    remaining_cpu -= ecu_base_cpu + link_cpu_per_factory  # ECU + its link
    remaining_power -= ecu_base_power + link_power_per_factory

    if remaining_cpu <= 0 or remaining_power <= 0:
        return False, 0, {"error": "ECU exceeds remaining capacity"}

    cost_per_factory_cpu = basic.cpu_tf + link_cpu_per_factory
    cost_per_factory_power = basic.power_mw + link_power_per_factory

    # Find the heads/factories split that maximizes output.
    # Each head extracts ~6,000 R0/hr at peak, each basic factory consumes 6,000 R0/hr.
    # With longer extraction cycles (e.g., 4 days), decay reduces effective R0/hr,
    # so we want MORE heads than factories to compensate.
    # Rule of thumb: target ~2 heads per factory to handle decay.
    best_factories = 0
    best_heads = 0
    for heads in range(1, 11):
        head_cpu = head.cpu_tf * heads
        head_power = head.power_mw * heads
        factory_cpu = remaining_cpu - head_cpu
        factory_power = remaining_power - head_power
        if factory_cpu <= 0 or factory_power <= 0:
            break
        max_by_cpu = int(factory_cpu / cost_per_factory_cpu)
        max_by_power = int(factory_power / cost_per_factory_power)
        # Cap factories: no more than heads (even with perfect extraction,
        # 1 head can only feed ~1 factory). Prefer extra heads for decay buffer.
        factories = min(max_by_cpu, max_by_power, heads)

        # Best = most factories that are actually fed
        if factories > best_factories:
            best_factories = factories
            best_heads = heads
    details["basic_factories"] = best_factories
    details["extractor_heads"] = best_heads
    details["factory_type"] = "basic_factory"
    details["max_factories"] = best_factories
    return best_factories > 0, best_factories, details


def _fit_r0_to_p2(remaining_cpu, remaining_power, link_power_per_factory,
                   link_cpu_per_factory, game_data, details):
    advanced = game_data.facilities["advanced_factory"]
    basic = game_data.facilities["basic_factory"]
    head = game_data.facilities["extractor_head"]
    ecu_base = game_data.facilities.get("extractor_base")
    ecu_base_cpu = ecu_base.cpu_tf if ecu_base else 400
    ecu_base_power = ecu_base.power_mw if ecu_base else 2600

    # Reserve: 1 advanced factory + 2 ECU bases (one per R0 type) + their links
    fixed_cpu = (advanced.cpu_tf + ecu_base_cpu * 2 + link_cpu_per_factory * 3)
    fixed_power = (advanced.power_mw + ecu_base_power * 2 + link_power_per_factory * 3)
    remaining_cpu -= fixed_cpu
    remaining_power -= fixed_power
    if remaining_cpu <= 0 or remaining_power <= 0:
        return False, 0, {"error": "Cannot fit advanced factory + 2 ECUs for R0->P2"}
    cost_per_basic_cpu = basic.cpu_tf + link_cpu_per_factory
    cost_per_basic_power = basic.power_mw + link_power_per_factory
    best_basics = 0
    best_heads = 0
    # Total heads split across 2 ECUs (1-10 per ECU)
    # Each basic factory needs ~1 head worth of R0, and basics are split
    # between 2 P1 types, so cap basics at total heads
    for heads in range(2, 21):
        if heads > 20:  # max 10 per ECU
            break
        head_cpu = head.cpu_tf * heads
        head_power = head.power_mw * heads
        factory_cpu = remaining_cpu - head_cpu
        factory_power = remaining_power - head_power
        if factory_cpu <= 0 or factory_power <= 0:
            break
        max_by_cpu = int(factory_cpu / cost_per_basic_cpu)
        max_by_power = int(factory_power / cost_per_basic_power)
        basics = min(max_by_cpu, max_by_power, heads)  # cap at heads
        if basics >= 2 and basics > best_basics:
            best_basics = basics
            best_heads = heads
    details["advanced_factories"] = 1
    details["basic_factories"] = best_basics
    details["extractor_heads"] = best_heads
    details["factory_type"] = "advanced_factory"
    details["max_factories"] = 1
    fits = best_basics >= 2 and best_heads >= 1
    return fits, 1, details
