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


def can_fit(
    radius_km: float,
    ccu_level: int,
    setup: SetupType,
    game_data: GameData,
    product_name: str = None,
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
        return _fit_factory(remaining_cpu, remaining_power,
                            link_power_per_factory, link_cpu_per_factory, setup, game_data, details)


def _fit_factory(remaining_cpu, remaining_power, link_power_per_factory,
                 link_cpu_per_factory, setup, game_data, details):
    factory_key = FACTORY_TYPE[setup]
    factory = game_data.facilities[factory_key]
    cost_per_factory_cpu = factory.cpu_tf + link_cpu_per_factory
    cost_per_factory_power = factory.power_mw + link_power_per_factory
    max_by_cpu = int(remaining_cpu / cost_per_factory_cpu) if cost_per_factory_cpu > 0 else 0
    max_by_power = int(remaining_power / cost_per_factory_power) if cost_per_factory_power > 0 else 0
    max_factories = min(max_by_cpu, max_by_power)
    details["factory_type"] = factory_key
    details["max_factories"] = max_factories
    details["cost_per_factory_cpu"] = cost_per_factory_cpu
    details["cost_per_factory_power"] = cost_per_factory_power
    return max_factories > 0, max_factories, details


def _fit_extraction(remaining_cpu, remaining_power, link_power_per_factory,
                    link_cpu_per_factory, game_data, details):
    basic = game_data.facilities["basic_factory"]
    head = game_data.facilities["extractor_head"]
    cost_per_factory_cpu = basic.cpu_tf + link_cpu_per_factory
    cost_per_factory_power = basic.power_mw + link_power_per_factory
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
        factories = min(max_by_cpu, max_by_power)
        if factories > best_factories or (factories == best_factories and heads > best_heads):
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
    adv_cpu = advanced.cpu_tf + link_cpu_per_factory
    adv_power = advanced.power_mw + link_power_per_factory
    remaining_cpu -= adv_cpu
    remaining_power -= adv_power
    if remaining_cpu <= 0 or remaining_power <= 0:
        return False, 0, {"error": "Cannot fit advanced factory for R0->P2"}
    cost_per_basic_cpu = basic.cpu_tf + link_cpu_per_factory
    cost_per_basic_power = basic.power_mw + link_power_per_factory
    best_basics = 0
    best_heads = 0
    for heads in range(1, 11):
        head_cpu = head.cpu_tf * heads
        head_power = head.power_mw * heads
        factory_cpu = remaining_cpu - head_cpu
        factory_power = remaining_power - head_power
        if factory_cpu <= 0 or factory_power <= 0:
            break
        max_by_cpu = int(factory_cpu / cost_per_basic_cpu)
        max_by_power = int(factory_power / cost_per_basic_power)
        basics = min(max_by_cpu, max_by_power)
        if basics >= 2 and (basics > best_basics or (basics == best_basics and heads > best_heads)):
            best_basics = basics
            best_heads = heads
    details["advanced_factories"] = 1
    details["basic_factories"] = best_basics
    details["extractor_heads"] = best_heads
    details["factory_type"] = "advanced_factory"
    details["max_factories"] = 1
    fits = best_basics >= 2 and best_heads >= 1
    return fits, 1, details
