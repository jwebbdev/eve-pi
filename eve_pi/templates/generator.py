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
    cycle_days: float = 4.0,
) -> Optional[dict]:
    """Generate a complete EVE-importable template JSON dict.

    Args:
        setup: One of "r0_to_p1", "r0_to_p2", "p1_to_p2", "p2_to_p3", "p3_to_p4".
        planet_type: Planet type name, e.g. "Gas", "Barren".
        product: Output product name, e.g. "Coolant", "Bacteria".
        radius_km: Planet radius in km.
        ccu_level: Command Center Upgrade skill level (0-5).
        game_data: GameData instance; loaded fresh if None.
        cycle_days: Restocking cycle in days (affects LP count for factory setups).

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

    return gen(planet_type, product, radius_km, ccu_level, game_data, cycle_days)


# ---------------------------------------------------------------------------
# Layout helpers
# ---------------------------------------------------------------------------

def _angular_step(radius_km: float) -> float:
    """Calculate angular step (radians) for minimum-distance pin placement."""
    min_link_km = max(1.0, min_link_distance(radius_km))
    step = (min_link_km / radius_km) * 1.1
    return max(step, 0.005)


def _hex_grid_positions(cx: float, cy: float, step: float,
                        count: int) -> List[Tuple[float, float, int]]:
    """Place structures in a honeycomb pattern radiating from center.

    Returns list of (la, lo, parent_index) where parent_index is the
    0-based index in this list of the nearest neighbor toward center,
    or -1 if directly adjacent to center (hub).

    Each ring has 6 more positions than the previous:
    - Ring 1: 6 positions (directly around hub)
    - Ring 2: 12 positions
    - Ring 3: 18 positions
    Total through ring 3: 36 positions (more than enough for any PI setup).
    """
    import math

    # Hex grid: offset coordinates converted to axial
    # step_la = step (vertical), step_lo = step (horizontal)
    # In a hex grid, alternating rows are offset by half a step
    half = step * 0.5
    row_height = step * 0.866  # sqrt(3)/2

    # Generate positions in concentric hex rings around center
    # Ring N has 6*N positions
    all_positions = []  # (la, lo, distance_from_center)

    # Ring 1: 6 immediate neighbors
    ring1 = [
        (cx + step, cy),              # right
        (cx - step, cy),              # left
        (cx + half, cy + row_height), # upper-right
        (cx - half, cy + row_height), # upper-left
        (cx + half, cy - row_height), # lower-right
        (cx - half, cy - row_height), # lower-left
    ]

    # Ring 2: 12 positions
    ring2 = [
        (cx + step * 2, cy),                        # far right
        (cx - step * 2, cy),                        # far left
        (cx, cy + row_height * 2),                  # top
        (cx, cy - row_height * 2),                  # bottom
        (cx + step * 1.5, cy + row_height),         # right-up
        (cx - step * 1.5, cy + row_height),         # left-up
        (cx + step * 1.5, cy - row_height),         # right-down
        (cx - step * 1.5, cy - row_height),         # left-down
        (cx + step, cy + row_height * 2),           # upper-right-far
        (cx - step, cy + row_height * 2),           # upper-left-far
        (cx + step, cy - row_height * 2),           # lower-right-far
        (cx - step, cy - row_height * 2),           # lower-left-far
    ]

    # Ring 3: 18 more positions
    ring3 = [
        (cx + step * 3, cy),
        (cx - step * 3, cy),
        (cx + step * 2.5, cy + row_height),
        (cx - step * 2.5, cy + row_height),
        (cx + step * 2.5, cy - row_height),
        (cx - step * 2.5, cy - row_height),
        (cx + step * 2, cy + row_height * 2),
        (cx - step * 2, cy + row_height * 2),
        (cx + step * 2, cy - row_height * 2),
        (cx - step * 2, cy - row_height * 2),
        (cx + half, cy + row_height * 3),
        (cx - half, cy + row_height * 3),
        (cx + half, cy - row_height * 3),
        (cx - half, cy - row_height * 3),
        (cx + step * 1.5, cy + row_height * 3),
        (cx - step * 1.5, cy + row_height * 3),
        (cx + step * 1.5, cy - row_height * 3),
        (cx - step * 1.5, cy - row_height * 3),
    ]

    all_slots = ring1 + ring2 + ring3

    # For each position, find its nearest neighbor that's closer to center (parent)
    results = []
    for i in range(min(count, len(all_slots))):
        la, lo = all_slots[i]
        la = round(float(la), 5)
        lo = round(float(lo), 5)

        dist_to_center = math.sqrt((la - cx) ** 2 + (lo - cy) ** 2)

        # Find parent: nearest already-placed position that's closer to center
        parent_idx = -1  # default: link to hub
        best_dist = float('inf')

        for j in range(len(results)):
            pla, plo, _ = results[j]
            p_dist_to_center = math.sqrt((pla - cx) ** 2 + (plo - cy) ** 2)
            if p_dist_to_center >= dist_to_center:
                continue  # parent must be closer to center
            link_dist = math.sqrt((la - pla) ** 2 + (lo - plo) ** 2)
            if link_dist < best_dist:
                best_dist = link_dist
                parent_idx = j

        results.append((la, lo, parent_idx))

    return results


def _parent_pin(index: int, pin_a: int = 1, pin_b: int = 2) -> int:
    """Alternate hub connection: even indices -> pin_a, odd -> pin_b."""
    return pin_a if index % 2 == 0 else pin_b


# ---------------------------------------------------------------------------
# R0 -> P1
# ---------------------------------------------------------------------------

def _generate_r0_to_p1(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData, cycle_days: float = 4.0) -> Optional[dict]:
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

    # Place basic factories in hex grid with tree linking
    tree = _hex_grid_positions(cx, cy, step, num_basics)
    factory_start = len(pins) + 1  # 1-indexed

    for i, (la, lo, parent_idx) in enumerate(tree):
        pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                     "S": p1_id, "T": pt.structures["basic_factory"]})
        # Link: factories chain to each other, ring-1 factories link to LP or Storage
        if parent_idx == -1:
            link_to = _parent_pin(i)  # alternate LP(1) / Storage(2)
        else:
            link_to = factory_start + parent_idx
        links.append({"D": len(pins), "Lv": 0, "S": link_to})

    # ECU
    ecu_pin = len(pins) + 1
    pins.append({"H": num_heads, "La": float(round(cx - step * 2, 5)),
                 "Lo": float(round(cy, 5)),
                 "S": r0_id, "T": pt.structures["extractor"]})
    links.append({"D": ecu_pin, "Lv": 0, "S": 2})  # ECU -> Storage

    # Build path from each factory back to hub (following parent chain)
    def _path_to_hub(factory_index: int) -> List[int]:
        path = [factory_start + factory_index]
        idx = factory_index
        while True:
            parent_idx = tree[idx][2]
            if parent_idx == -1:
                # This factory links to LP or Storage
                hub_pin = _parent_pin(idx)
                path.append(hub_pin)
                break
            else:
                path.append(factory_start + parent_idx)
                idx = parent_idx
        return path

    # Routes
    routes: List[dict] = []

    # R0: Storage -> each Basic Factory (R0 can't route through factories!)
    # For R0, every factory must have a direct link to LP or Storage
    # Since tree factories may chain through other factories, R0 routes need
    # to go Storage -> LP -> factory (for ring-1 factories linked to LP)
    # or Storage -> factory (for ring-1 factories linked to Storage)
    # For deeper factories, R0 CAN route through other basic factories
    # because EVE allows R0 to pass through — wait, no it can't!
    # R0 routing through basic factories fails. So for extraction setups,
    # ALL factories must link directly to LP or Storage (no chaining).
    # Re-link: override tree parents so all connect to LP or Storage
    links_override = []
    for i in range(len(links)):
        if links[i]["D"] >= factory_start and links[i]["D"] <= factory_start + num_basics - 1:
            # This is a factory link — force it to LP or Storage
            factory_idx = links[i]["D"] - factory_start
            links[i]["S"] = _parent_pin(factory_idx)

    for i in range(num_basics):
        pin = factory_start + i
        parent = _parent_pin(i)
        if parent == 1:
            routes.append({"P": [2, 1, pin], "Q": r0_qty, "T": r0_id})
        else:
            routes.append({"P": [2, pin], "Q": r0_qty, "T": r0_id})

    # P1: each Basic Factory -> LP
    for i in range(num_basics):
        pin = factory_start + i
        parent = _parent_pin(i)
        if parent == 1:
            routes.append({"P": [pin, 1], "Q": recipe.output_per_cycle, "T": p1_id})
        else:
            routes.append({"P": [pin, 2, 1], "Q": recipe.output_per_cycle, "T": p1_id})

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
                       game_data: GameData, cycle_days: float = 4.0) -> Optional[dict]:
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
                       game_data: GameData, cycle_days: float = 4.0) -> Optional[dict]:
    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p1_to_p2", setup_type=SetupType.P1_TO_P2,
        factory_key="advanced_factory", label_prefix="P1-P2", cycle_days=cycle_days,
    )


# ---------------------------------------------------------------------------
# P2 -> P3
# ---------------------------------------------------------------------------

def _generate_p2_to_p3(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData, cycle_days: float = 4.0) -> Optional[dict]:
    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p2_to_p3", setup_type=SetupType.P2_TO_P3,
        factory_key="advanced_factory", label_prefix="P2-P3", cycle_days=cycle_days,
    )


# ---------------------------------------------------------------------------
# P3 -> P4
# ---------------------------------------------------------------------------

def _generate_p3_to_p4(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData, cycle_days: float = 4.0) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    if not pt.p4_capable:
        return None

    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p3_to_p4", setup_type=SetupType.P3_TO_P4,
        factory_key="hightech_factory", label_prefix="P3-P4", cycle_days=cycle_days,
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
    cycle_days: float = 4.0,
) -> Optional[dict]:
    from eve_pi.capacity.planet_capacity import calculate_lp_count

    pt = game_data.planet_types[planet_type_name]
    recipe = game_data.get_recipe(recipe_tier, product)
    if not recipe:
        return None

    fits, max_factories, details = can_fit(radius_km, ccu_level, setup_type, game_data,
                                           product_name=product, cycle_days=cycle_days)
    if not fits:
        return None

    num_factories = details.get("max_factories", max_factories)
    num_lps = details.get("launchpad_count", 1)
    product_id = game_data.materials[product].type_id

    # Resolve input material IDs
    input_info = []  # (name, type_id, qty_per_cycle)
    for mat_name, qty in recipe.inputs:
        input_info.append((mat_name, game_data.materials[mat_name].type_id, qty))

    step = _angular_step(radius_km)
    cx, cy = 1.5, 3.0

    # Build hub pins: LPs at center
    pins: List[dict] = []
    links: List[dict] = []

    # LP 1 (pin 1) at center
    pins.append({"H": 0, "La": float(round(cx, 5)), "Lo": float(round(cy, 5)),
                 "S": None, "T": pt.structures["launchpad"]})

    # Additional LPs around center
    lp_offsets = [(step, 0), (-step, 0), (0, step), (0, -step),
                  (step, step), (-step, step)]
    for lp_i in range(1, num_lps):
        off_la, off_lo = lp_offsets[(lp_i - 1) % len(lp_offsets)]
        pins.append({"H": 0, "La": float(round(cx + off_la, 5)),
                     "Lo": float(round(cy + off_lo, 5)),
                     "S": None, "T": pt.structures["launchpad"]})
        links.append({"D": len(pins), "Lv": 0, "S": 1})  # link to LP1

    # Place factories in a tree radiating from LP cluster
    factory_start = len(pins) + 1  # 1-indexed pin number of first factory
    tree = _hex_grid_positions(cx, cy, step, num_factories)

    for i, (la, lo, parent_idx) in enumerate(tree):
        pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                     "S": product_id, "T": pt.structures[factory_key]})
        # Link to parent: -1 means hub (pin 1), otherwise link to parent factory
        if parent_idx == -1:
            link_to = 1  # LP
        else:
            link_to = factory_start + parent_idx  # parent factory pin (1-indexed)
        links.append({"D": len(pins), "Lv": 0, "S": link_to})

    # Build path from each factory back to LP (following parent chain)
    def _path_to_lp(factory_index: int) -> List[int]:
        """Build route path from a factory back to LP 1, following the tree."""
        path = [factory_start + factory_index]
        idx = factory_index
        while True:
            parent_idx = tree[idx][2]
            if parent_idx == -1:
                path.append(1)  # LP
                break
            else:
                path.append(factory_start + parent_idx)
                idx = parent_idx
        return path

    # Routes
    routes: List[dict] = []

    for i in range(num_factories):
        factory_pin = factory_start + i
        path_to_lp = _path_to_lp(i)
        path_from_lp = list(reversed(path_to_lp))

        # Input routes: LP -> factory (one per input material)
        for mat_name, mat_id, qty in input_info:
            routes.append({"P": path_from_lp, "Q": qty, "T": mat_id})

        # Output route: factory -> LP
        routes.append({"P": path_to_lp, "Q": recipe.output_per_cycle, "T": product_id})

    return {
        "CmdCtrLv": ccu_level,
        "Cmt": f"{label_prefix} {product} on {planet_type_name} ({num_factories} fac, {num_lps} LP, {cycle_days}d cycle)",
        "Diam": round(radius_km * 2.0, 1),
        "L": links,
        "P": pins,
        "Pln": pt.type_id,
        "R": routes,
    }
