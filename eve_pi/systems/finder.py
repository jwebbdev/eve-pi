"""System search and product availability functions."""
from dataclasses import dataclass
from typing import Dict, List, Optional, Set


@dataclass
class SystemMatch:
    """A system that matches product requirements."""
    system_id: int
    name: str
    security: float
    planets: Dict[str, int]  # planet_type -> count
    wh_class: Optional[int] = None


def find_matching_systems(
    system_index: Dict[str, dict],
    required_r0s: List[str],
    planet_types_for_r0: callable,
    space: str = "k",
    wh_classes: Optional[Set[int]] = None,
) -> List[SystemMatch]:
    """Find systems whose planet types can produce all required R0 resources.

    Args:
        system_index: GameData.system_index mapping system_id -> {name, security, planets, wh_class?}
        required_r0s: List of R0 resource names that must all be producible
        planet_types_for_r0: Callable that returns planet type names for an R0 (GameData.planet_types_for_r0)
        space: "k" for K-space, "j" for J-space
        wh_classes: Set of wormhole classes to include (J-space only). None means all.

    Returns:
        List of matching SystemMatch objects (unsorted).
    """
    if wh_classes is None:
        wh_classes = {1, 2, 3, 4, 5, 6}

    # Pre-compute which planet types can provide each R0
    r0_planet_options = []
    for r0 in required_r0s:
        pts = planet_types_for_r0(r0)
        if not pts:
            return []  # Unknown R0, no matches possible
        r0_planet_options.append(set(pts))

    matches = []
    for system_id, entry in system_index.items():
        is_wh = "wh_class" in entry
        if space == "k" and is_wh:
            continue
        if space == "j" and not is_wh:
            continue
        if space == "j" and entry.get("wh_class") not in wh_classes:
            continue

        system_planets = set(entry["planets"].keys())
        if all(system_planets & opts for opts in r0_planet_options):
            matches.append(SystemMatch(
                system_id=int(system_id),
                name=entry["name"],
                security=entry["security"],
                planets=entry["planets"],
                wh_class=entry.get("wh_class"),
            ))

    return matches


def get_system_products(
    planet_composition: Dict[str, int],
    game_data,
) -> Dict[str, List[str]]:
    """Get all products producible in a system given its planet type composition.

    Args:
        planet_composition: Dict of planet_type_name -> count
        game_data: GameData instance with planet_types, recipes, materials

    Returns:
        Dict with keys "p1", "p2", "p3", "p4", each a sorted list of product names.
    """
    # Collect R0 resources available from these planet types
    r0_available = set()
    has_p4_planet = False
    for pt_name, count in planet_composition.items():
        pt = game_data.planet_types.get(pt_name)
        if pt:
            for r0 in pt.resources:
                r0_available.add(r0)
            if pt.p4_capable:
                has_p4_planet = True

    # Trace production chain
    p1_available = set()
    for p1_name, recipe in game_data.recipes.get("r0_to_p1", {}).items():
        if recipe.inputs[0][0] in r0_available:
            p1_available.add(p1_name)

    p2_available = set()
    for p2_name, recipe in game_data.recipes.get("p1_to_p2", {}).items():
        if all(inp[0] in p1_available for inp in recipe.inputs):
            p2_available.add(p2_name)

    p3_available = set()
    for p3_name, recipe in game_data.recipes.get("p2_to_p3", {}).items():
        if all(inp[0] in p2_available for inp in recipe.inputs):
            p3_available.add(p3_name)

    p4_available = set()
    if has_p4_planet:
        for p4_name, recipe in game_data.recipes.get("p3_to_p4", {}).items():
            inputs_ok = True
            for inp_name, qty in recipe.inputs:
                tier = game_data.get_material_tier(inp_name)
                if tier == "p3" and inp_name not in p3_available:
                    inputs_ok = False
                elif tier == "p1" and inp_name not in p1_available:
                    inputs_ok = False
            if inputs_ok:
                p4_available.add(p4_name)

    return {
        "p1": sorted(p1_available),
        "p2": sorted(p2_available),
        "p3": sorted(p3_available),
        "p4": sorted(p4_available),
    }
