"""Tests for the general PI template generator."""
import pytest

from eve_pi.data.loader import GameData
from eve_pi.templates.generator import generate_template


@pytest.fixture(scope="module")
def game_data():
    return GameData.load()


# ---------------------------------------------------------------------------
# Helper validation functions
# ---------------------------------------------------------------------------

def _build_link_graph(template: dict) -> dict:
    """Build adjacency set from links (1-indexed pins)."""
    adj = {}
    for link in template["L"]:
        s, d = link["S"], link["D"]
        adj.setdefault(s, set()).add(d)
        adj.setdefault(d, set()).add(s)
    return adj


def _validate_common(template: dict, ccu_level: int = 5):
    """Validate common template properties."""
    assert template is not None
    assert template["CmdCtrLv"] == ccu_level
    assert isinstance(template["Diam"], float)
    assert len(template["P"]) > 0
    assert len(template["L"]) > 0
    assert len(template["R"]) > 0

    # All La/Lo values must be floats
    for pin in template["P"]:
        assert isinstance(pin["La"], float), f"La is {type(pin['La'])}: {pin['La']}"
        assert isinstance(pin["Lo"], float), f"Lo is {type(pin['Lo'])}: {pin['Lo']}"


def _validate_links(template: dict):
    """Validate all link references point to valid pins (1-indexed)."""
    num_pins = len(template["P"])
    for link in template["L"]:
        assert 1 <= link["S"] <= num_pins, f"Link S={link['S']} out of range (1..{num_pins})"
        assert 1 <= link["D"] <= num_pins, f"Link D={link['D']} out of range (1..{num_pins})"
        assert link["S"] != link["D"], "Link cannot be self-referencing"


def _validate_routes(template: dict):
    """Validate all route paths follow actual link connections."""
    adj = _build_link_graph(template)
    num_pins = len(template["P"])

    for route in template["R"]:
        path = route["P"]
        assert len(path) >= 2, f"Route path too short: {path}"
        for pin in path:
            assert 1 <= pin <= num_pins, f"Route pin {pin} out of range (1..{num_pins})"
        # Verify each hop has a link
        for i in range(len(path) - 1):
            a, b = path[i], path[i + 1]
            assert b in adj.get(a, set()), (
                f"No link between pins {a} and {b} in route {path}. "
                f"Links from {a}: {adj.get(a, set())}"
            )


def _validate_material_ids(template: dict, game_data, expected_materials: dict):
    """Validate material IDs in routes match expectations.

    expected_materials: {type_id: material_name} for spot-checking.
    """
    route_type_ids = {r["T"] for r in template["R"]}
    for type_id, name in expected_materials.items():
        assert type_id in route_type_ids, f"Expected material {name} (ID {type_id}) in routes"


def _validate_structure_ids(template: dict, game_data, planet_type: str):
    """Validate structure type IDs match the planet type."""
    pt = game_data.planet_types[planet_type]
    valid_structure_ids = set(pt.structures.values())
    for pin in template["P"]:
        assert pin["T"] in valid_structure_ids, (
            f"Structure ID {pin['T']} not valid for {planet_type}. "
            f"Valid: {pt.structures}"
        )


# ---------------------------------------------------------------------------
# R0 -> P1
# ---------------------------------------------------------------------------

class TestR0ToP1:
    def test_generates_valid_template(self, game_data):
        t = generate_template("r0_to_p1", "Gas", "Water", game_data=game_data)
        _validate_common(t)
        _validate_links(t)
        _validate_routes(t)
        _validate_structure_ids(t, game_data, "Gas")

    def test_correct_pin_count(self, game_data):
        t = generate_template("r0_to_p1", "Gas", "Water", game_data=game_data)
        # LP + Storage + N basics + 1 ECU
        pins = t["P"]
        num_lp = sum(1 for p in pins if p["T"] == game_data.planet_types["Gas"].structures["launchpad"])
        num_storage = sum(1 for p in pins if p["T"] == game_data.planet_types["Gas"].structures["storage"])
        num_ecu = sum(1 for p in pins if p["T"] == game_data.planet_types["Gas"].structures["extractor"])
        num_basic = sum(1 for p in pins if p["T"] == game_data.planet_types["Gas"].structures["basic_factory"])
        assert num_lp == 1
        assert num_storage == 1
        assert num_ecu == 1
        assert num_basic >= 1

    def test_material_ids(self, game_data):
        t = generate_template("r0_to_p1", "Gas", "Water", game_data=game_data)
        water_id = game_data.materials["Water"].type_id
        r0_id = game_data.materials["Aqueous Liquids"].type_id
        _validate_material_ids(t, game_data, {water_id: "Water", r0_id: "Aqueous Liquids"})

    def test_different_planet_type(self, game_data):
        t = generate_template("r0_to_p1", "Barren", "Bacteria", game_data=game_data)
        _validate_common(t)
        _validate_links(t)
        _validate_routes(t)
        _validate_structure_ids(t, game_data, "Barren")

    def test_invalid_product_returns_none(self, game_data):
        t = generate_template("r0_to_p1", "Gas", "NonexistentProduct", game_data=game_data)
        assert t is None


# ---------------------------------------------------------------------------
# R0 -> P2
# ---------------------------------------------------------------------------

class TestR0ToP2:
    def test_generates_valid_template(self, game_data):
        t = generate_template("r0_to_p2", "Gas", "Coolant", game_data=game_data)
        _validate_common(t)
        _validate_links(t)
        _validate_routes(t)
        _validate_structure_ids(t, game_data, "Gas")

    def test_correct_pin_types(self, game_data):
        t = generate_template("r0_to_p2", "Gas", "Coolant", game_data=game_data)
        pt = game_data.planet_types["Gas"]
        pins = t["P"]
        num_lp = sum(1 for p in pins if p["T"] == pt.structures["launchpad"])
        num_storage = sum(1 for p in pins if p["T"] == pt.structures["storage"])
        num_advanced = sum(1 for p in pins if p["T"] == pt.structures["advanced_factory"])
        num_basic = sum(1 for p in pins if p["T"] == pt.structures["basic_factory"])
        num_ecu = sum(1 for p in pins if p["T"] == pt.structures["extractor"])
        assert num_lp == 1
        assert num_storage == 1
        assert num_advanced == 1
        assert num_basic >= 2  # at least 1 per P1 type
        assert num_ecu == 2

    def test_material_ids(self, game_data):
        t = generate_template("r0_to_p2", "Gas", "Coolant", game_data=game_data)
        coolant_id = game_data.materials["Coolant"].type_id
        electrolytes_id = game_data.materials["Electrolytes"].type_id
        water_id = game_data.materials["Water"].type_id
        _validate_material_ids(t, game_data, {
            coolant_id: "Coolant",
            electrolytes_id: "Electrolytes",
            water_id: "Water",
        })

    def test_small_planet(self, game_data):
        t = generate_template("r0_to_p2", "Gas", "Coolant", radius_km=2000.0, game_data=game_data)
        if t is not None:
            _validate_common(t)
            _validate_links(t)
            _validate_routes(t)


# ---------------------------------------------------------------------------
# P1 -> P2
# ---------------------------------------------------------------------------

class TestP1ToP2:
    def test_generates_valid_template(self, game_data):
        t = generate_template("p1_to_p2", "Gas", "Coolant", game_data=game_data)
        _validate_common(t)
        _validate_links(t)
        _validate_routes(t)
        _validate_structure_ids(t, game_data, "Gas")

    def test_no_extractors_or_storage(self, game_data):
        t = generate_template("p1_to_p2", "Gas", "Coolant", game_data=game_data)
        pt = game_data.planet_types["Gas"]
        pins = t["P"]
        num_ecu = sum(1 for p in pins if p["T"] == pt.structures["extractor"])
        num_storage = sum(1 for p in pins if p["T"] == pt.structures["storage"])
        assert num_ecu == 0
        assert num_storage == 0

    def test_correct_factory_count(self, game_data):
        t = generate_template("p1_to_p2", "Gas", "Coolant", game_data=game_data)
        pt = game_data.planet_types["Gas"]
        num_advanced = sum(1 for p in t["P"] if p["T"] == pt.structures["advanced_factory"])
        assert num_advanced >= 1

    def test_route_quantities(self, game_data):
        t = generate_template("p1_to_p2", "Gas", "Coolant", game_data=game_data)
        coolant_id = game_data.materials["Coolant"].type_id
        output_routes = [r for r in t["R"] if r["T"] == coolant_id]
        # Each factory should have one output route with Q=5
        for r in output_routes:
            assert r["Q"] == 5

    def test_input_routes_have_correct_quantity(self, game_data):
        t = generate_template("p1_to_p2", "Gas", "Coolant", game_data=game_data)
        electrolytes_id = game_data.materials["Electrolytes"].type_id
        input_routes = [r for r in t["R"] if r["T"] == electrolytes_id]
        for r in input_routes:
            assert r["Q"] == 40

    def test_all_factories_have_product_schematic(self, game_data):
        t = generate_template("p1_to_p2", "Gas", "Coolant", game_data=game_data)
        coolant_id = game_data.materials["Coolant"].type_id
        pt = game_data.planet_types["Gas"]
        for pin in t["P"]:
            if pin["T"] == pt.structures["advanced_factory"]:
                assert pin["S"] == coolant_id


# ---------------------------------------------------------------------------
# P2 -> P3
# ---------------------------------------------------------------------------

class TestP2ToP3:
    def test_generates_valid_template(self, game_data):
        t = generate_template("p2_to_p3", "Gas", "Condensates", game_data=game_data)
        _validate_common(t)
        _validate_links(t)
        _validate_routes(t)
        _validate_structure_ids(t, game_data, "Gas")

    def test_correct_input_quantity(self, game_data):
        t = generate_template("p2_to_p3", "Gas", "Condensates", game_data=game_data)
        coolant_id = game_data.materials["Coolant"].type_id
        input_routes = [r for r in t["R"] if r["T"] == coolant_id]
        for r in input_routes:
            assert r["Q"] == 10

    def test_output_quantity(self, game_data):
        t = generate_template("p2_to_p3", "Gas", "Condensates", game_data=game_data)
        condensates_id = game_data.materials["Condensates"].type_id
        output_routes = [r for r in t["R"] if r["T"] == condensates_id]
        for r in output_routes:
            assert r["Q"] == 3

    def test_three_input_recipe(self, game_data):
        """Test a P2->P3 recipe with 3 inputs (e.g. Biotech Research Reports)."""
        t = generate_template("p2_to_p3", "Gas", "Biotech Research Reports", game_data=game_data)
        _validate_common(t)
        _validate_links(t)
        _validate_routes(t)


# ---------------------------------------------------------------------------
# P3 -> P4
# ---------------------------------------------------------------------------

class TestP3ToP4:
    def test_generates_on_capable_planet(self, game_data):
        t = generate_template("p3_to_p4", "Barren", "Broadcast Node", game_data=game_data)
        _validate_common(t)
        _validate_links(t)
        _validate_routes(t)
        _validate_structure_ids(t, game_data, "Barren")

    def test_rejects_incapable_planet(self, game_data):
        t = generate_template("p3_to_p4", "Gas", "Broadcast Node", game_data=game_data)
        assert t is None

    def test_uses_hightech_factory(self, game_data):
        t = generate_template("p3_to_p4", "Barren", "Broadcast Node", game_data=game_data)
        pt = game_data.planet_types["Barren"]
        num_ht = sum(1 for p in t["P"] if p["T"] == pt.structures["hightech_factory"])
        assert num_ht >= 1

    def test_output_quantity(self, game_data):
        t = generate_template("p3_to_p4", "Barren", "Broadcast Node", game_data=game_data)
        bn_id = game_data.materials["Broadcast Node"].type_id
        output_routes = [r for r in t["R"] if r["T"] == bn_id]
        for r in output_routes:
            assert r["Q"] == 1

    def test_temperate_also_works(self, game_data):
        t = generate_template("p3_to_p4", "Temperate", "Broadcast Node", game_data=game_data)
        _validate_common(t)
        _validate_structure_ids(t, game_data, "Temperate")


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_invalid_setup_returns_none(self, game_data):
        t = generate_template("invalid_setup", "Gas", "Coolant", game_data=game_data)
        assert t is None

    def test_invalid_planet_type_returns_none(self, game_data):
        t = generate_template("p1_to_p2", "InvalidPlanet", "Coolant", game_data=game_data)
        assert t is None

    def test_ccu_level_in_template(self, game_data):
        for level in (3, 4, 5):
            t = generate_template("p1_to_p2", "Gas", "Coolant", ccu_level=level, game_data=game_data)
            if t is not None:
                assert t["CmdCtrLv"] == level

    def test_diam_matches_radius(self, game_data):
        t = generate_template("p1_to_p2", "Gas", "Coolant", radius_km=4000.0, game_data=game_data)
        if t is not None:
            assert t["Diam"] == 8000.0

    def test_loads_game_data_if_none(self):
        """generate_template should work when game_data is not passed."""
        t = generate_template("p1_to_p2", "Gas", "Coolant")
        assert t is not None
        _validate_common(t)
