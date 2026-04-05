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
    lp_count: int = None,
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
        "p2_to_p4": _generate_p2_to_p4,
    }

    gen = generators.get(setup)
    if gen is None:
        return None

    return gen(planet_type, product, radius_km, ccu_level, game_data, cycle_days, lp_count)


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
                       game_data: GameData, cycle_days: float = 4.0, lp_count: int = None) -> Optional[dict]:
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
                       game_data: GameData, cycle_days: float = 4.0, lp_count: int = None) -> Optional[dict]:
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
                       game_data: GameData, cycle_days: float = 4.0, lp_count: int = None) -> Optional[dict]:
    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p1_to_p2", setup_type=SetupType.P1_TO_P2,
        factory_key="advanced_factory", label_prefix="P1-P2",
        cycle_days=cycle_days, lp_count_override=lp_count,
    )


# ---------------------------------------------------------------------------
# P2 -> P3
# ---------------------------------------------------------------------------

def _generate_p2_to_p3(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData, cycle_days: float = 4.0, lp_count: int = None) -> Optional[dict]:
    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p2_to_p3", setup_type=SetupType.P2_TO_P3,
        factory_key="advanced_factory", label_prefix="P2-P3",
        cycle_days=cycle_days, lp_count_override=lp_count,
    )


# ---------------------------------------------------------------------------
# P3 -> P4
# ---------------------------------------------------------------------------

def _generate_p3_to_p4(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData, cycle_days: float = 4.0, lp_count: int = None) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    if not pt.p4_capable:
        return None

    return _generate_factory_setup(
        planet_type_name, product, radius_km, ccu_level, game_data,
        recipe_tier="p3_to_p4", setup_type=SetupType.P3_TO_P4,
        factory_key="hightech_factory", label_prefix="P3-P4",
        cycle_days=cycle_days, lp_count_override=lp_count,
    )


# ---------------------------------------------------------------------------
# P2 -> P4 (multi-tier: P2 inputs → internal P3 → P4 output)
# ---------------------------------------------------------------------------

def _generate_p2_to_p4(planet_type_name: str, product: str,
                       radius_km: float, ccu_level: int,
                       game_data: GameData, cycle_days: float = 4.0, lp_count: int = None) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    if not pt.p4_capable:
        return None

    p4_recipe = game_data.get_recipe("p3_to_p4", product)
    if not p4_recipe:
        return None

    # Analyze the full input chain: P4 <- P3s <- P2s (and maybe P1s)
    # Build list of intermediate P3 factories needed and their P2 inputs
    intermediates = []  # [(p3_name, p3_recipe, adv_per_ht)]
    direct_inputs = []  # [(mat_name, mat_id, qty, tier)] for P1 inputs that go direct to HT

    for input_name, qty in p4_recipe.inputs:
        tier = game_data.get_material_tier(input_name)
        if tier == "p3":
            p3_recipe = game_data.get_recipe("p2_to_p3", input_name)
            if not p3_recipe:
                return None
            # Each HT factory needs qty P3/hr. Each Adv produces 3 P3/hr.
            adv_needed_per_ht = max(1, -(-qty // 3))  # ceiling division
            intermediates.append((input_name, p3_recipe, adv_needed_per_ht))
        elif tier in ("p1", "p2"):
            mat = game_data.materials.get(input_name)
            if not mat:
                return None
            direct_inputs.append((input_name, mat.type_id, qty, tier))

    # Calculate how many HT + Adv fit in the budget
    import math
    cc = game_data.command_center_levels.get(ccu_level)
    if not cc:
        return None

    min_dist = min_link_distance(radius_km)
    from eve_pi.capacity.planet_capacity import link_costs as _link_costs
    lp_mw, lc_tf = _link_costs(min_dist)
    link_pw = lp_mw * 1.5
    link_cp = lc_tf * 1.5

    adv = game_data.facilities["advanced_factory"]
    ht = game_data.facilities["hightech_factory"]
    lp_fac = game_data.facilities["launchpad"]

    # Collect all unique import materials for LP count
    import_materials = {}  # name -> (type_id, qty_per_ht_per_hr)
    for p3_name, p3_recipe, adv_per_ht in intermediates:
        for p2_name, p2_qty in p3_recipe.inputs:
            mat = game_data.materials.get(p2_name)
            if mat and p2_name not in import_materials:
                import_materials[p2_name] = (mat.type_id, p2_qty)
    for name, type_id, qty, tier in direct_inputs:
        if name not in import_materials:
            import_materials[name] = (type_id, qty)

    # LP count: default from unique input count, or override
    if lp_count and lp_count > 0:
        num_lps = lp_count
    else:
        num_lps = max(1, math.ceil(len(import_materials) / 3))

    # Total Adv factories needed per HT factory
    total_adv_per_ht = sum(a for _, _, a in intermediates)

    # Iteratively find max HT factories
    best_n_ht = 0
    for n_ht in range(1, 20):
        n_adv = total_adv_per_ht * n_ht

        lp_cost_cpu = (lp_fac.cpu_tf + link_cp) * num_lps
        lp_cost_pw = (lp_fac.power_mw + link_pw) * num_lps
        ht_cost_cpu = (ht.cpu_tf + link_cp) * n_ht
        ht_cost_pw = (ht.power_mw + link_pw) * n_ht
        adv_cost_cpu = (adv.cpu_tf + link_cp) * n_adv
        adv_cost_pw = (adv.power_mw + link_pw) * n_adv

        total_cpu = lp_cost_cpu + ht_cost_cpu + adv_cost_cpu
        total_pw = lp_cost_pw + ht_cost_pw + adv_cost_pw

        if total_cpu <= cc.cpu_tf and total_pw <= cc.power_mw:
            best_n_ht = n_ht
        else:
            break

    if best_n_ht < 1:
        return None

    n_ht = best_n_ht
    p4_id = game_data.materials[product].type_id

    step = _angular_step(radius_km)
    cx, cy = 1.5, 3.0

    pins: List[dict] = []
    links: List[dict] = []
    routes: List[dict] = []

    # Place LPs
    pins.append({"H": 0, "La": float(round(cx, 5)), "Lo": float(round(cy, 5)),
                 "S": None, "T": pt.structures["launchpad"]})
    lp_offsets = [(step, 0), (-step, 0), (0, step), (0, -step), (step, step), (-step, step)]
    for lp_i in range(1, num_lps):
        off_la, off_lo = lp_offsets[(lp_i - 1) % len(lp_offsets)]
        pins.append({"H": 0, "La": float(round(cx + off_la, 5)),
                     "Lo": float(round(cy + off_lo, 5)),
                     "S": None, "T": pt.structures["launchpad"]})
        links.append({"D": len(pins), "Lv": 0, "S": 1})

    # Place ALL factories in one hex grid offset from the LP cluster
    # Offset grid center so factories don't overlap with LPs
    total_adv = total_adv_per_ht * n_ht
    total_factories = n_ht + total_adv
    grid_cx = cx
    grid_cy = cy + step * 2  # offset grid below LP cluster
    all_positions = _hex_grid_positions(grid_cx, grid_cy, step, total_factories)

    # Assign: first n_ht positions are HT factories
    ht_start = len(pins) + 1
    for i in range(n_ht):
        la, lo, parent_idx = all_positions[i]
        pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                     "S": p4_id, "T": pt.structures["hightech_factory"]})
        factory_pin = len(pins)
        if parent_idx == -1 or parent_idx + ht_start > factory_pin:
            links.append({"D": factory_pin, "Lv": 0, "S": 1})
        else:
            links.append({"D": factory_pin, "Lv": 0, "S": ht_start + parent_idx})

    # Remaining positions are Adv factories, assigned round-robin to P3 types
    adv_groups = {}  # p3_name -> (list of pin_numbers, p3_type_id, p3_recipe)
    adv_start = len(pins) + 1
    adv_idx = 0
    for inter_idx, (p3_name, p3_recipe, adv_per_ht) in enumerate(intermediates):
        p3_id = game_data.materials[p3_name].type_id
        n_adv_for_this = adv_per_ht * n_ht
        adv_group_pins = []

        for j in range(n_adv_for_this):
            grid_idx = n_ht + adv_idx
            if grid_idx >= len(all_positions):
                break
            la, lo, parent_idx = all_positions[grid_idx]
            pins.append({"H": 0, "La": float(la), "Lo": float(lo),
                         "S": p3_id, "T": pt.structures["advanced_factory"]})
            factory_pin = len(pins)
            # Link to parent in the grid (could be HT or another Adv)
            if parent_idx == -1:
                links.append({"D": factory_pin, "Lv": 0, "S": 1})
            else:
                parent_pin = ht_start + parent_idx  # parent is at this grid position
                links.append({"D": factory_pin, "Lv": 0, "S": parent_pin})
            adv_group_pins.append(factory_pin)
            adv_idx += 1

        adv_groups[p3_name] = (adv_group_pins, p3_id, p3_recipe)

    # Build adjacency for route pathfinding
    adj = {}
    for link in links:
        s, d = link["S"], link["D"]
        adj.setdefault(s, set()).add(d)
        adj.setdefault(d, set()).add(s)

    def _find_path(start: int, end: int) -> Optional[List[int]]:
        """BFS shortest path between two pins."""
        from collections import deque
        if start == end:
            return [start]
        visited = {start}
        queue = deque([(start, [start])])
        while queue:
            node, path = queue.popleft()
            for neighbor in adj.get(node, set()):
                if neighbor == end:
                    return path + [neighbor]
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return None

    # Routes: P2 inputs from LPs to Adv factories
    for p3_name, (adv_pins, p3_id, p3_recipe) in adv_groups.items():
        for i, adv_pin in enumerate(adv_pins):
            assigned_lp = (i % num_lps) + 1

            # P2 input routes: LP -> Adv
            for p2_name, p2_qty in p3_recipe.inputs:
                p2_id = game_data.materials[p2_name].type_id
                path = _find_path(assigned_lp, adv_pin)
                if path:
                    routes.append({"P": path, "Q": p2_qty, "T": p2_id})

            # P3 output routes: Adv -> nearest HT factory
            # Round-robin assign to HT factories
            target_ht = ht_start + (i % n_ht)
            path = _find_path(adv_pin, target_ht)
            if path:
                routes.append({"P": path, "Q": 3, "T": p3_id})

    # Direct P1 inputs to HT factories (for recipes like Nano-Factory)
    for name, type_id, qty, tier in direct_inputs:
        for i in range(n_ht):
            ht_pin = ht_start + i
            assigned_lp = (i % num_lps) + 1
            path = _find_path(assigned_lp, ht_pin)
            if path:
                routes.append({"P": path, "Q": qty, "T": type_id})

    # P4 output routes: HT -> LP (round-robin)
    for i in range(n_ht):
        ht_pin = ht_start + i
        assigned_lp = (i % num_lps) + 1
        path = _find_path(ht_pin, assigned_lp)
        if path:
            routes.append({"P": path, "Q": 1, "T": p4_id})

    return {
        "CmdCtrLv": ccu_level,
        "Cmt": f"P2-P4 {product} on {planet_type_name} ({n_ht} HT, {total_adv_per_ht * n_ht} Adv, {num_lps} LP)",
        "Diam": round(radius_km * 2.0, 1),
        "L": links,
        "P": pins,
        "Pln": pt.type_id,
        "R": routes,
    }


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
    lp_count_override: int = None,
) -> Optional[dict]:
    pt = game_data.planet_types[planet_type_name]
    recipe = game_data.get_recipe(recipe_tier, product)
    if not recipe:
        return None

    # Use override LP count, or calculate from capacity model
    if lp_count_override and lp_count_override > 0:
        num_lps = lp_count_override
        # Calculate max factories with this LP count reserved
        lp_facility = game_data.facilities["launchpad"]
        cc = game_data.command_center_levels.get(ccu_level)
        if not cc:
            return None
        min_dist = min_link_distance(radius_km)
        from eve_pi.capacity.planet_capacity import link_costs as _link_costs
        lp_mw, lc_tf = _link_costs(min_dist)
        link_pw_per = lp_mw * 1.5
        link_cp_per = lc_tf * 1.5

        lp_total_cpu = (lp_facility.cpu_tf + link_cp_per) * num_lps
        lp_total_power = (lp_facility.power_mw + link_pw_per) * num_lps
        remaining_cpu = cc.cpu_tf - lp_total_cpu
        remaining_power = cc.power_mw - lp_total_power

        factory = game_data.facilities[factory_key]
        cost_cpu = factory.cpu_tf + link_cp_per
        cost_power = factory.power_mw + link_pw_per

        if remaining_cpu <= 0 or remaining_power <= 0:
            return None
        num_factories = min(
            int(remaining_cpu / cost_cpu) if cost_cpu > 0 else 0,
            int(remaining_power / cost_power) if cost_power > 0 else 0,
        )
    else:
        fits, max_factories, details = can_fit(radius_km, ccu_level, setup_type, game_data,
                                               product_name=product, cycle_days=cycle_days)
        if not fits:
            return None
        num_factories = details.get("max_factories", max_factories)
        num_lps = details.get("launchpad_count", 1)

    if num_factories < 1:
        return None

    # Round down to nearest multiple of LP count for even distribution
    if num_lps > 1:
        num_factories = (num_factories // num_lps) * num_lps
        if num_factories < 1:
            return None

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

    # Round-robin LP assignment: factory i -> LP (i % num_lps) + 1
    # All LPs are linked to LP 1, so routes from LP N go through LP 1 if needed
    factory_lp = {}  # factory_index -> lp_pin (1-indexed)
    for i in range(num_factories):
        factory_lp[i] = (i % num_lps) + 1  # LP pins are 1..num_lps

    # Build path from each factory to its assigned LP (following parent chain)
    def _path_to_lp(factory_index: int) -> List[int]:
        """Build route path from a factory to its assigned LP, following the tree."""
        target_lp = factory_lp[factory_index]
        path = [factory_start + factory_index]
        idx = factory_index
        while True:
            parent_idx = tree[idx][2]
            if parent_idx == -1:
                # Reached a hub-connected factory — route to assigned LP
                if target_lp == 1:
                    path.append(1)
                else:
                    path.append(1)  # go through LP1
                    path.append(target_lp)  # then to assigned LP
                break
            else:
                path.append(factory_start + parent_idx)
                idx = parent_idx
        return path

    # Routes
    routes: List[dict] = []

    for i in range(num_factories):
        lp_pin = factory_lp[i]
        path_to_lp = _path_to_lp(i)
        path_from_lp = list(reversed(path_to_lp))

        # Input routes: assigned LP -> factory (one per input material)
        for mat_name, mat_id, qty in input_info:
            routes.append({"P": path_from_lp, "Q": qty, "T": mat_id})

        # Output route: factory -> assigned LP
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
