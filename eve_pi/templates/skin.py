"""Apply a 'skin' (planet type + recipe) to a topology to produce an importable template."""
from typing import Dict
from eve_pi.data.loader import GameData
from eve_pi.templates.topology import Topology, PinRole

ROLE_TO_STRUCTURE_KEY = {
    PinRole.LAUNCHPAD: "launchpad",
    PinRole.BASIC_FACTORY: "basic_factory",
    PinRole.ADVANCED_FACTORY: "advanced_factory",
    PinRole.HIGHTECH_FACTORY: "hightech_factory",
    PinRole.STORAGE: "storage",
    PinRole.EXTRACTOR: "extractor",
    PinRole.COMMAND_CENTER: "command_center",
}


def apply_skin(
    topology: Topology, planet_type: str, product: str,
    game_data: GameData, ccu_level: int = 5,
) -> Dict:
    """Apply planet type structure IDs and product material IDs to a topology."""
    pt = game_data.planet_types[planet_type]
    product_mat = game_data.materials.get(product)
    product_type_id = product_mat.type_id if product_mat else None

    pins = []
    for pin_def in topology.pins:
        role = pin_def["role"]
        structure_key = ROLE_TO_STRUCTURE_KEY.get(role)
        structure_id = pt.structures.get(structure_key) if structure_key else None
        pin = {
            "H": pin_def.get("heads", 0),
            "La": pin_def["latitude"],
            "Lo": pin_def["longitude"],
            "S": product_type_id if pin_def.get("schematic") == "output" else None,
            "T": structure_id,
        }
        pins.append(pin)

    links = []
    for src, dst in topology.links:
        links.append({"D": dst + 1, "Lv": 0, "S": src + 1})

    return {
        "CmdCtrLv": ccu_level,
        "Cmt": f"{product} on {planet_type}",
        "Diam": 4440.0,
        "L": links,
        "P": pins,
        "Pln": pt.type_id,
        "R": [],
    }
