"""Convert an existing PI template to a different planet type and/or product."""
import copy
from typing import Dict, Optional
from eve_pi.data.loader import GameData


def convert_template(
    template: Dict, to_planet_type: str = None, to_product: str = None,
    game_data: GameData = None,
) -> Dict:
    """Convert a template to a different planet type and/or product."""
    result = copy.deepcopy(template)
    if not game_data:
        game_data = GameData.load()

    # Build reverse lookup from the SOURCE planet type only (avoids ID collisions)
    old_structure_to_role = {}
    old_pln_id = template.get("Pln")
    for pt in game_data.planet_types.values():
        if pt.type_id == old_pln_id:
            for role, sid in pt.structures.items():
                old_structure_to_role[sid] = role
            break
    # Fallback: if source planet not identified, use all planet types
    if not old_structure_to_role:
        for pt in game_data.planet_types.values():
            for role, sid in pt.structures.items():
                old_structure_to_role[sid] = role

    # Find old product type ID from pins
    old_product_id = None
    for pin in result.get("P", []):
        if pin.get("S") is not None:
            old_product_id = pin["S"]
            break

    # Swap planet type
    if to_planet_type:
        new_pt = game_data.planet_types[to_planet_type]
        result["Pln"] = new_pt.type_id
        for pin in result.get("P", []):
            old_tid = pin.get("T")
            if old_tid is not None and old_tid in old_structure_to_role:
                role = old_structure_to_role[old_tid]
                new_tid = new_pt.structures.get(role)
                if new_tid is not None:
                    pin["T"] = new_tid

    # Swap product
    if to_product:
        new_mat = game_data.materials.get(to_product)
        new_type_id = new_mat.type_id if new_mat else None
        if new_type_id and old_product_id:
            # Swap input routes FIRST (before output ID changes)
            _swap_recipe_inputs(result, old_product_id, to_product, game_data)
            # Then swap output in pins and routes
            for pin in result.get("P", []):
                if pin.get("S") == old_product_id:
                    pin["S"] = new_type_id
            for route in result.get("R", []):
                if route.get("T") == old_product_id:
                    route["T"] = new_type_id
        result["Cmt"] = f"Converted: {to_product}"
        if to_planet_type:
            result["Cmt"] = f"{to_product} on {to_planet_type}"

    return result


def _swap_recipe_inputs(template, old_product_type_id, new_product, game_data):
    """Swap input material IDs in routes based on the new product's recipe."""
    old_input_ids = set()
    for route in template.get("R", []):
        tid = route.get("T")
        if tid is not None and tid != old_product_type_id:
            old_input_ids.add(tid)
    new_recipe = None
    for tier_key in ("p1_to_p2", "p2_to_p3", "p3_to_p4"):
        new_recipe = game_data.get_recipe(tier_key, new_product)
        if new_recipe:
            break
    if not new_recipe or not old_input_ids:
        return
    old_input_list = sorted(old_input_ids)
    new_input_ids = []
    for input_name, _ in new_recipe.inputs:
        mat = game_data.materials.get(input_name)
        if mat:
            new_input_ids.append(mat.type_id)
    if len(old_input_list) != len(new_input_ids):
        return
    id_map = dict(zip(old_input_list, new_input_ids))
    for route in template.get("R", []):
        tid = route.get("T")
        if tid in id_map:
            route["T"] = id_map[tid]
