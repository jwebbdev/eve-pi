"""General PI template generator for all setup types.

Generates EVE-importable template JSON dicts with hub-and-spoke layouts,
properly sized to fit the planet radius and CCU level.
"""
from typing import Dict, List, Optional, Tuple

from eve_pi.capacity.planet_capacity import can_fit, SetupType, min_link_distance
from eve_pi.data.loader import GameData


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_template(
    setup: str,
    planet_type: str,
    product: str,
    radius_km: float = 5000.0,
    ccu_level: int = 5,
    game_data: GameData = None,
) -> Optional[dict]:
    """Generate a complete EVE-importable template JSON dict.

    Args:
        setup: One of "r0_to_p1", "r0_to_p2", "p1_to_p2", "p2_to_p3", "p3_to_p4".
        planet_type: Planet type name, e.g. "Gas", "Barren".
        product: Output product name, e.g. "Coolant", "Bacteria".
        radius_km: Planet radius in km.
        ccu_level: Command Center Upgrade skill level (0-5).
        game_data: GameData instance; loaded fresh if None.

    Returns:
        Template dict ready for JSON export, or None if the setup cannot fit.
    """
    if game_data is None:
        game_data = GameData.load()

    if planet_type not in game_data.planet_types:
        return None

    generators = {
        "r0_to_p1": _generate_r0_to_p1,
        "r0_to_p2": _generate_r0_to_p2,
        "p1_to_p2": _generate_p1_to_p2,
        "p2_to_p3": _generate_p2_to_p3,
        "p3_to_p4": _generate_p3_to_p4,
    }

    gen = generators.get(setup)
    if gen is None:
        return None

    return gen(planet_type, product, radius_km, ccu_level, game_data)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _angular_step(radius_km: float) -> float:
    """Calculate angular step (radians) for minimum-distance pin placement."""
    min_link_km = max(1.0, min_link_distance(radius_km))
    step = (min_link_km / radius_km) * 1.1
    return max(step, 0.005)


def _place_factories_ring(cx: float, cy: float, step: float,
                          count: int, direction: float = 1.0) -> List[Tuple[float, float]]:
    """Place *count* factories in rows of 2, extending in *direction* from center.

    Returns list of (la, lo) tuples.
    """
    positions = []
    for i in range(count):
        row = i // 2
        col = i % 2
        la = round(cx + (col - 0.5) * step, 5)
        lo = round(cy + direction * step * (1 + row), 5)
        positions.append((la, lo))
    return positions


def _parent_pin(index: int, pin_a: int = 1, pin_b: int = 2) -> int:
    """Alternate hub connection: even indices -> pin_a, odd -> pin_b."""
    return pin_a if index % 2 == 0 else pin_b


# ---------------------------------------------------------------------------
# R0 -> P1
# ---------------------------------------------------------------------------

def _generate_r0_to_p1(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    recipe = game_data.get_recipe("r0_to_p1", product)
    if not recipe:
        return None

    r0_name = recipe.inputs[0][0]
    r0_qty = recipe.inputs[0][1]

    fits, _, details = can_fit(radius_km, ccu_level, SetupType.R0_TO_P1, game_data)
    if not fits:
        return None

    num_basics = details.get("basic_factories", 1)
    num_heads = details.get("extractor_heads", 1)

    p1_id = game_data.materials[product].type_id
    r0_id = game_data.materials[r0_name].type_id

    step = _angular_step(radius_km)
    cx, cy = 1.5, 3.0

    # Pins: LP(1), Storage(2), Basic factories(3..N+2), ECU(N+3)
    pins: List[dict] = [
        {"H": 0, "La": float(round(cx, 5)), "Lo": float(round(cy, 5)),
         "S": None, "T": pt.structures["launchpad"]},
        {"H": 0, "La": float(round(cx + step, 5)), "Lo": float(round(cy, 5)),
         "S": None, "T": pt.structures["storage"]},
    ]
    links: List[dict] = [
        {"D": 2, "Lv": 0, "S": 1},  # LP <-> Storage
    ]

    # Place basic factories
    factory_positions = _place_factories_ring(cx, cy, step, num_basics, direction=1.0)
    factory_start = len(pins) + 1  # 1-indexed
    for i, (la, lo) in enumerate(factory_positions):
        pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                     "S": p1_id, "T": pt.structures["basic_factory"]})
        parent = _parent_pin(i)
        links.append({"D": len(pins), "Lv": 0, "S": parent})

    # ECU
    ecu_pin = len(pins) + 1
    pins.append({"H": num_heads, "La": float(round(cx - step * 2, 5)),
                 "Lo": float(round(cy, 5)),
                 "S": r0_id, "T": pt.structures["extractor"]})
    links.append({"D": ecu_pin, "Lv": 0, "S": 2})  # ECU -> Storage

    # Routes
    routes: List[dict] = []

    # R0: Storage -> each Basic Factory
    for i in range(num_basics):
        pin = factory_start + i
        parent = _parent_pin(i)
        # Route must follow links: Storage(2) -> parent -> factory
        if parent == 1:
            path = [2, 1, pin]
        else:
            path = [2, pin]
        routes.append({"P": path, "Q": r0_qty, "T": r0_id})

    # P1: each Basic Factory -> LP
    for i in range(num_basics):
        pin = factory_start + i
        parent = _parent_pin(i)
        if parent == 1:
            path = [pin, 1]
        else:
            path = [pin, 2, 1]
        routes.append({"P": path, "Q": recipe.output_per_cycle, "T": p1_id})

    # ECU program route: ECU -> Storage
    routes.append({"P": [ecu_pin, 2], "Q": r0_qty, "T": r0_id})

    return {
        "CmdCtrLv": ccu_level,
        "Cmt": f"R0-P1 {product} on {planet_type_name} ({num_basics} basic, {num_heads} heads)",
        "Diam": round(radius_km * 2.0, 1),
        "L": links,
        "P": pins,
        "Pln": pt.type_id,
        "R": routes,
    }


# ---------------------------------------------------------------------------
# R0 -> P2
# ---------------------------------------------------------------------------

def _generate_r0_to_p2(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    p2_recipe = game_data.get_recipe("p1_to_p2", product)
    if not p2_recipe:
        return None

    p1_a_name = p2_recipe.inputs[0][0]
    p1_b_name = p2_recipe.inputs[1][0]
    r0_a_name = game_data.r0_for_p1(p1_a_name)
    r0_b_name = game_data.r0_for_p1(p1_b_name)
    if not r0_a_name or not r0_b_name:
        return None

    fits, _, details = can_fit(radius_km, ccu_level, SetupType.R0_TO_P2, game_data)
    if not fits:
        return None

    num_basics = details.get("basic_factories", 4)
    num_heads_total = details.get("extractor_heads", 4)
    basics_per_type = num_basics // 2
    heads_per_ecu = min(num_heads_total // 2, 10)

    if basics_per_type < 1:
        basics_per_type = 1

    p2_id = game_data.materials[product].type_id
    p1_a_id = game_data.materials[p1_a_name].type_id
    p1_b_id = game_data.materials[p1_b_name].type_id
    r0_a_id = game_data.materials[r0_a_name].type_id
    r0_b_id = game_data.materials[r0_b_name].type_id

    step = _angular_step(radius_km)
    cx, cy = 1.5, 3.0

    # Pins: LP(1), Storage(2), Advanced(3), Basic-A(4...), Basic-B(...), ECU-A, ECU-B
    pins: List[dict] = [
        {"H": 0, "La": float(round(cx, 5)), "Lo": float(round(cy, 5)),
         "S": None, "T": pt.structures["launchpad"]},
        {"H": 0, "La": float(round(cx + step, 5)), "Lo": float(round(cy, 5)),
         "S": None, "T": pt.structures["storage"]},
        {"H": 0, "La": float(round(cx - step, 5)), "Lo": float(round(cy, 5)),
         "S": p2_id, "T": pt.structures["advanced_factory"]},
    ]
    links: List[dict] = [
        {"D": 2, "Lv": 0, "S": 1},  # LP <-> Storage
        {"D": 3, "Lv": 0, "S": 1},  # LP <-> Advanced
    ]

    # Basic-A factories (+Lo direction)
    basic_a_start = len(pins) + 1
    for i in range(basics_per_type):
        row = i // 2
        col = i % 2
        la = round(cx + (col - 0.5) * step, 5)
        lo = round(cy + step * (1 + row), 5)
        pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                     "S": p1_a_id, "T": pt.structures["basic_factory"]})
        parent = _parent_pin(i)
        links.append({"D": len(pins), "Lv": 0, "S": parent})

    # Basic-B factories (-Lo direction)
    basic_b_start = len(pins) + 1
    for i in range(basics_per_type):
        row = i // 2
        col = i % 2
        la = round(cx + (col - 0.5) * step, 5)
        lo = round(cy - step * (1 + row), 5)
        pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                     "S": p1_b_id, "T": pt.structures["basic_factory"]})
        parent = _parent_pin(i)
        links.append({"D": len(pins), "Lv": 0, "S": parent})

    # ECUs
    ecu_a_pin = len(pins) + 1
    pins.append({"H": heads_per_ecu, "La": float(round(cx + step * 2, 5)),
                 "Lo": float(round(cy, 5)),
                 "S": r0_a_id, "T": pt.structures["extractor"]})
    links.append({"D": ecu_a_pin, "Lv": 0, "S": 2})

    ecu_b_pin = len(pins) + 1
    pins.append({"H": heads_per_ecu, "La": float(round(cx - step * 2, 5)),
                 "Lo": float(round(cy, 5)),
                 "S": r0_b_id, "T": pt.structures["extractor"]})
    links.append({"D": ecu_b_pin, "Lv": 0, "S": 2})

    # Routes
    routes: List[dict] = []

    # R0-A: Storage -> each Basic-A
    for i in range(basics_per_type):
        pin = basic_a_start + i
        parent = _parent_pin(i)
        path = [2, 1, pin] if parent == 1 else [2, pin]
        routes.append({"P": path, "Q": 3000, "T": r0_a_id})

    # R0-B: Storage -> each Basic-B
    for i in range(basics_per_type):
        pin = basic_b_start + i
        parent = _parent_pin(i)
        path = [2, 1, pin] if parent == 1 else [2, pin]
        routes.append({"P": path, "Q": 3000, "T": r0_b_id})

    # P1-A: Basic-A -> Advanced(3)
    for i in range(basics_per_type):
        pin = basic_a_start + i
        parent = _parent_pin(i)
        path = [pin, 1, 3] if parent == 1 else [pin, 2, 1, 3]
        routes.append({"P": path, "Q": 20, "T": p1_a_id})

    # P1-B: Basic-B -> Advanced(3)
    for i in range(basics_per_type):
        pin = basic_b_start + i
        parent = _parent_pin(i)
        path = [pin, 1, 3] if parent == 1 else [pin, 2, 1, 3]
        routes.append({"P": path, "Q": 20, "T": p1_b_id})

    # P2 output: Advanced -> LP
    routes.append({"P": [3, 1], "Q": 5, "T": p2_id})

    # ECU program routes
    routes.append({"P": [ecu_a_pin, 2], "Q": 3000, "T": r0_a_id})
    routes.append({"P": [ecu_b_pin, 2], "Q": 3000, "T": r0_b_id})

    return {
        "CmdCtrLv": ccu_level,
        "Cmt": (f"R0-P2 {product} on {planet_type_name} "
                f"({basics_per_type}+{basics_per_type} basic, "
                f"{heads_per_ecu}+{heads_per_ecu} heads)"),
        "Diam": round(radius_km * 2.0, 1),
        "L": links,
        "P": pins,
        "Pln": pt.type_id,
        "R": routes,
    }


# ---------------------------------------------------------------------------
# P1 -> P2
# ---------------------------------------------------------------------------

def _generate_p1_to_p2(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData) -> Optional[dict]:
    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p1_to_p2",
        setup_type=SetupType.P1_TO_P2,
        factory_key="advanced_factory",
        label_prefix="P1-P2",
    )


# ---------------------------------------------------------------------------
# P2 -> P3
# ---------------------------------------------------------------------------

def _generate_p2_to_p3(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData) -> Optional[dict]:
    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p2_to_p3",
        setup_type=SetupType.P2_TO_P3,
        factory_key="advanced_factory",
        label_prefix="P2-P3",
    )


# ---------------------------------------------------------------------------
# P3 -> P4
# ---------------------------------------------------------------------------

def _generate_p3_to_p4(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    if not pt.p4_capable:
        return None

    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p3_to_p4",
        setup_type=SetupType.P3_TO_P4,
        factory_key="hightech_factory",
        label_prefix="P3-P4",
    )


# ---------------------------------------------------------------------------
# Shared factory-only generator (P1->P2, P2->P3, P3->P4)
# ---------------------------------------------------------------------------

def _generate_factory_setup(
    planet_type_name: str,
    product: str,
    radius_km: float,
    ccu_level: int,
    game_data: GameData,
    recipe_tier: str,
    setup_type: SetupType,
    factory_key: str,
    label_prefix: str,
) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    recipe = game_data.get_recipe(recipe_tier, product)
    if not recipe:
        return None

    fits, max_factories, details = can_fit(radius_km, ccu_level, setup_type, game_data)
    if not fits:
        return None

    num_factories = details.get("max_factories", max_factories)
    product_id = game_data.materials[product].type_id

    # Resolve input material IDs
    input_info = []  # (name, type_id, qty_per_cycle)
    for mat_name, qty in recipe.inputs:
        input_info.append((mat_name, game_data.materials[mat_name].type_id, qty))

    step = _angular_step(radius_km)
    cx, cy = 1.5, 3.0

    # Determine number of launchpads: add second LP when factories > 12
    num_lps = 2 if num_factories > 12 else 1

    # Build hub pins
    pins: List[dict] = []
    links: List[dict] = []

    # LP 1
    pins.append({"H": 0, "La": float(round(cx, 5)), "Lo": float(round(cy, 5)),
                 "S": None, "T": pt.structures["launchpad"]})

    if num_lps == 2:
        # LP 2
        pins.append({"H": 0, "La": float(round(cx + step, 5)), "Lo": float(round(cy, 5)),
                     "S": None, "T": pt.structures["launchpad"]})
        links.append({"D": 2, "Lv": 0, "S": 1})  # LP1 <-> LP2

    # Place factories
    factory_start = len(pins) + 1  # 1-indexed
    factory_positions = _place_factories_ring(cx, cy, step, num_factories, direction=1.0)
    for i, (la, lo) in enumerate(factory_positions):
        pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                     "S": product_id, "T": pt.structures[factory_key]})
        if num_lps == 2:
            # Split: first half -> LP1, second half -> LP2
            parent = 1 if i < num_factories // 2 else 2
        else:
            parent = 1
        links.append({"D": len(pins), "Lv": 0, "S": parent})

    # Routes
    routes: List[dict] = []

    for i in range(num_factories):
        factory_pin = factory_start + i
        if num_lps == 2:
            parent = 1 if i < num_factories // 2 else 2
        else:
            parent = 1

        # Input routes: LP -> factory (one per input material)
        for mat_name, mat_id, qty in input_info:
            if parent == 1:
                path = [1, factory_pin]
            else:
                path = [1, 2, factory_pin] if num_lps == 2 else [1, factory_pin]
            routes.append({"P": path, "Q": qty, "T": mat_id})

        # Output route: factory -> LP (always route to LP 1 for pickup)
        if parent == 1:
            path = [factory_pin, 1]
        else:
            path = [factory_pin, 2, 1] if num_lps == 2 else [factory_pin, 1]
        routes.append({"P": path, "Q": recipe.output_per_cycle, "T": product_id})

    return {
        "CmdCtrLv": ccu_level,
        "Cmt": f"{label_prefix} {product} on {planet_type_name} ({num_factories} factories)",
        "Diam": round(radius_km * 2.0, 1),
        "L": links,
        "P": pins,
        "Pln": pt.type_id,
        "R": routes,
    }
