"""Build a feasibility matrix: for each planet, what setups are physically possible."""
from dataclasses import dataclass
from typing import Dict, List, Optional
from eve_pi.capacity.planet_capacity import SetupType, can_fit
from eve_pi.data.loader import GameData
from eve_pi.models.planets import Planet, SolarSystem


@dataclass
class FeasibleOption:
    planet: Planet
    setup: SetupType
    product: str
    max_factories: int
    details: Dict
    output_per_hour: float = 0.0
    output_volume_per_day: float = 0.0


def build_feasibility_matrix(
    system: SolarSystem,
    ccu_level: int,
    game_data: GameData,
) -> List[FeasibleOption]:
    """
    For each planet, calculate all possible colony setups that physically fit.
    Returns a list of FeasibleOption, one per (planet, setup, product) combo.
    """
    options: List[FeasibleOption] = []

    for planet in system.planets:
        pt = planet.planet_type

        # R0->P1 extraction: one option per R0 resource on this planet
        for r0_name in pt.resources:
            fits, max_fac, details = can_fit(
                planet.radius_km, ccu_level, SetupType.R0_TO_P1, game_data
            )
            if fits and max_fac > 0:
                recipe = _find_r0_recipe(r0_name, game_data)
                if recipe:
                    p1_per_hour = recipe.output_per_hour * max_fac
                    p1_mat = game_data.materials.get(recipe.output)
                    vol_per_day = p1_per_hour * 24 * (p1_mat.volume_m3 if p1_mat else 0.38)
                    options.append(FeasibleOption(
                        planet=planet, setup=SetupType.R0_TO_P1,
                        product=recipe.output, max_factories=max_fac,
                        details=details, output_per_hour=p1_per_hour,
                        output_volume_per_day=vol_per_day,
                    ))

        # R0->P2: for each P2 where BOTH P1 inputs can be extracted from this planet
        for p2_name, recipe in game_data.recipes.get("p1_to_p2", {}).items():
            p1_inputs = [inp[0] for inp in recipe.inputs]
            all_available = True
            for p1_name in p1_inputs:
                r0_name = game_data.r0_for_p1(p1_name)
                if r0_name is None or r0_name not in pt.resources:
                    all_available = False
                    break
            if all_available:
                fits, max_fac, details = can_fit(
                    planet.radius_km, ccu_level, SetupType.R0_TO_P2, game_data
                )
                if fits:
                    p2_mat = game_data.materials.get(p2_name)
                    vol_per_day = 5.0 * 24 * (p2_mat.volume_m3 if p2_mat else 0.75)
                    options.append(FeasibleOption(
                        planet=planet, setup=SetupType.R0_TO_P2,
                        product=p2_name, max_factories=1,
                        details=details, output_per_hour=5.0,
                        output_volume_per_day=vol_per_day,
                    ))

        # Factory setups: P1->P2, P2->P3 on ALL planets
        for setup, tier_key in [
            (SetupType.P1_TO_P2, "p1_to_p2"),
            (SetupType.P2_TO_P3, "p2_to_p3"),
        ]:
            fits, max_fac, details = can_fit(
                planet.radius_km, ccu_level, setup, game_data
            )
            if fits and max_fac > 0:
                for product_name, recipe in game_data.recipes.get(tier_key, {}).items():
                    output_per_hour = recipe.output_per_hour * max_fac
                    mat = game_data.materials.get(product_name)
                    vol_per_day = output_per_hour * 24 * (mat.volume_m3 if mat else 0.75)
                    options.append(FeasibleOption(
                        planet=planet, setup=setup,
                        product=product_name, max_factories=max_fac,
                        details=details, output_per_hour=output_per_hour,
                        output_volume_per_day=vol_per_day,
                    ))

        # P3->P4: only on Barren or Temperate (p4_capable)
        if pt.p4_capable:
            fits, max_fac, details = can_fit(
                planet.radius_km, ccu_level, SetupType.P3_TO_P4, game_data
            )
            if fits and max_fac > 0:
                for product_name, recipe in game_data.recipes.get("p3_to_p4", {}).items():
                    output_per_hour = recipe.output_per_hour * max_fac
                    mat = game_data.materials.get(product_name)
                    vol_per_day = output_per_hour * 24 * (mat.volume_m3 if mat else 100.0)
                    options.append(FeasibleOption(
                        planet=planet, setup=SetupType.P3_TO_P4,
                        product=product_name, max_factories=max_fac,
                        details=details, output_per_hour=output_per_hour,
                        output_volume_per_day=vol_per_day,
                    ))

    return options


def _find_r0_recipe(r0_name: str, game_data: GameData):
    """Find the R0->P1 recipe that uses this R0 resource."""
    for product, recipe in game_data.recipes.get("r0_to_p1", {}).items():
        if recipe.inputs[0][0] == r0_name:
            return recipe
    return None
