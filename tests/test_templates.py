import json
from eve_pi.data.loader import GameData
from eve_pi.templates.topology import Topology, PinRole
from eve_pi.templates.skin import apply_skin
from eve_pi.templates.converter import convert_template


def test_topology_creation():
    topo = Topology(
        name="test_extraction",
        pins=[
            {"role": PinRole.LAUNCHPAD, "latitude": 1.0, "longitude": 2.0},
            {"role": PinRole.BASIC_FACTORY, "latitude": 1.1, "longitude": 2.1},
            {"role": PinRole.EXTRACTOR, "latitude": 1.2, "longitude": 2.2, "heads": 10},
        ],
        links=[(0, 1), (1, 2)],
    )
    assert len(topo.pins) == 3
    assert len(topo.links) == 2


def test_apply_skin():
    gd = GameData.load()
    topo = Topology(
        name="test_p1_factory",
        pins=[
            {"role": PinRole.LAUNCHPAD, "latitude": 1.0, "longitude": 2.0},
            {"role": PinRole.ADVANCED_FACTORY, "latitude": 1.1, "longitude": 2.1, "schematic": "output"},
        ],
        links=[(0, 1)],
    )
    template = apply_skin(topo, planet_type="Gas", product="Coolant", game_data=gd)
    assert isinstance(template, dict)
    assert template["P"][0]["T"] == 2543  # Gas launchpad
    assert template["P"][1]["T"] == 2494  # Gas advanced factory
    assert template["P"][1]["S"] == 9832  # Coolant type ID


def test_convert_template():
    gd = GameData.load()
    original = {
        "CmdCtrLv": 5,
        "Cmt": "P1->P2 Factory: Coolant",
        "Pln": 13,  # Gas
        "P": [
            {"H": 0, "La": 1.0, "Lo": 2.0, "S": None, "T": 2543},   # Gas Launchpad
            {"H": 0, "La": 1.1, "Lo": 2.1, "S": 9832, "T": 2494},   # Gas Advanced + Coolant
        ],
        "L": [{"D": 2, "Lv": 0, "S": 1}],
        "R": [{"P": [0, 1], "Q": 40, "T": 2390}],  # Electrolytes route
    }
    converted = convert_template(
        template=original, to_planet_type="Barren",
        to_product="Construction Blocks", game_data=gd,
    )
    assert converted["Pln"] == 2016  # Barren type ID
    assert converted["P"][0]["T"] == 2544  # Barren Launchpad
    assert converted["P"][1]["T"] == 2474  # Barren Advanced Factory
    assert converted["P"][1]["S"] == 3828  # Construction Blocks type ID
    assert "Construction Blocks" in converted["Cmt"]
