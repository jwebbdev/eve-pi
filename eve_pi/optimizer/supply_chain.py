"""Self-sufficient supply chain balancing."""
from dataclasses import dataclass, field
from typing import Dict, List, Tuple
from eve_pi.data.loader import GameData


@dataclass
class SupplyRequirement:
    material: str
    quantity_per_day: float
    r0_resource: str
    planet_types: List[str]


def get_supply_requirements(
    product_name: str, tier_key: str, num_factories: int, game_data: GameData,
) -> List[SupplyRequirement]:
    """Calculate P1 supply requirements for a factory colony. Traces recipe back to P1 inputs."""
    recipe = game_data.get_recipe(tier_key, product_name)
    if not recipe:
        return []
    requirements = []
    for input_name, qty_per_cycle in recipe.inputs:
        input_tier = game_data.get_material_tier(input_name)
        if input_tier == "p1":
            qty_per_hour = qty_per_cycle * (3600 / recipe.cycle_seconds) * num_factories
            qty_per_day = qty_per_hour * 24
            r0_name = game_data.r0_for_p1(input_name)
            if r0_name:
                planet_types = game_data.planet_types_for_r0(r0_name)
                requirements.append(SupplyRequirement(
                    material=input_name, quantity_per_day=qty_per_day,
                    r0_resource=r0_name, planet_types=planet_types,
                ))
        elif input_tier == "p2":
            p2_recipe = game_data.get_recipe("p1_to_p2", input_name)
            if p2_recipe:
                for p1_name, p1_qty in p2_recipe.inputs:
                    p2_per_hour = qty_per_cycle * (3600 / recipe.cycle_seconds) * num_factories
                    p1_per_hour = p2_per_hour * (p1_qty / p2_recipe.output_per_cycle)
                    qty_per_day = p1_per_hour * 24
                    r0_name = game_data.r0_for_p1(p1_name)
                    if r0_name:
                        planet_types = game_data.planet_types_for_r0(r0_name)
                        requirements.append(SupplyRequirement(
                            material=p1_name, quantity_per_day=qty_per_day,
                            r0_resource=r0_name, planet_types=planet_types,
                        ))
    return requirements


def check_supply_balance(
    extraction_output: Dict[str, float], factory_demand: Dict[str, float],
) -> Tuple[bool, Dict[str, float]]:
    """Check if extraction output satisfies factory demand. Returns (balanced, deficit_dict)."""
    deficit = {}
    for material, needed in factory_demand.items():
        produced = extraction_output.get(material, 0.0)
        if produced < needed:
            deficit[material] = needed - produced
    return len(deficit) == 0, deficit
