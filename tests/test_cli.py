from eve_pi.cli.main import build_parser


def test_parser_optimize_command():
    parser = build_parser()
    args = parser.parse_args([
        "optimize", "--system", "J153003", "--characters", "6",
        "--ccu-level", "4", "--cycle-days", "4", "--trips-per-week", "2",
        "--cargo-m3", "60000", "--mode", "self_sufficient", "--tax-rate", "0.05",
    ])
    assert args.command == "optimize"
    assert args.system == "J153003"
    assert args.characters == 6
    assert args.cycle_days == 4.0
    assert args.mode == "self_sufficient"


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
