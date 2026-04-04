from eve_pi.cli.main import build_parser
from eve_pi.cli.optimize import _parse_characters


def test_parser_optimize_command():
    parser = build_parser()
    args = parser.parse_args([
        "optimize", "--system", "J153003", "--characters", "6",
        "--ccu-level", "4", "--cycle-days", "4", "--trips-per-week", "2",
        "--cargo-m3", "60000", "--mode", "self_sufficient", "--tax-rate", "0.05",
    ])
    assert args.command == "optimize"
    assert args.system == "J153003"
    assert args.characters == "6"
    assert args.cycle_days == 4.0
    assert args.mode == "self_sufficient"


def test_parse_characters_count():
    chars = _parse_characters("6", default_ccu=4, default_planets=6)
    assert len(chars) == 6
    assert chars[0].name == "Char1"
    assert chars[0].ccu_level == 4


def test_parse_characters_names():
    chars = _parse_characters("Alice,Bob,Charlie", default_ccu=5, default_planets=6)
    assert len(chars) == 3
    assert chars[0].name == "Alice"
    assert chars[1].name == "Bob"
    assert all(c.ccu_level == 5 for c in chars)


def test_parse_characters_names_with_ccu():
    chars = _parse_characters("Alice:5,Bob:4,Charlie:3", default_ccu=4, default_planets=6)
    assert len(chars) == 3
    assert chars[0].name == "Alice"
    assert chars[0].ccu_level == 5
    assert chars[1].ccu_level == 4
    assert chars[2].ccu_level == 3


def test_parse_characters_mixed():
    chars = _parse_characters("Alice:5,Bob,Charlie:3", default_ccu=4, default_planets=6)
    assert chars[0].ccu_level == 5
    assert chars[1].name == "Bob"
    assert chars[1].ccu_level == 4  # uses default
    assert chars[2].ccu_level == 3


def test_parse_characters_with_planets():
    chars = _parse_characters("Alice:5:6,Bob:4:5,Charlie:3:4", default_ccu=4, default_planets=6)
    assert chars[0].max_planets == 6  # IC V
    assert chars[1].max_planets == 5  # IC IV
    assert chars[2].max_planets == 4  # IC III


def test_parse_characters_mixed_planets():
    chars = _parse_characters("Alice:5:6,Bob,Charlie:4", default_ccu=5, default_planets=6)
    assert chars[0].max_planets == 6
    assert chars[0].ccu_level == 5
    assert chars[1].max_planets == 6  # default
    assert chars[1].ccu_level == 5    # default
    assert chars[2].max_planets == 6  # default (only ccu specified)
    assert chars[2].ccu_level == 4


def test_parser_template_command():
    parser = build_parser()
    args = parser.parse_args([
        "template", "--planet-type", "Gas", "--setup", "P1-P2", "--product", "Coolant",
    ])
    assert args.command == "template"
    assert args.planet_type == "Gas"
    assert args.product == "Coolant"


def test_parser_template_convert():
    parser = build_parser()
    args = parser.parse_args([
        "template", "convert", "--input", "my_template.json",
        "--to-planet-type", "Barren", "--to-product", "Construction Blocks",
    ])
    assert args.command == "template"
    assert args.template_command == "convert"
    assert args.input == "my_template.json"
    assert args.to_planet_type == "Barren"
