"""CLI handler for template commands."""
import json
import sys
from eve_pi.data.loader import GameData
from eve_pi.templates.converter import convert_template


def run_template(args):
    gd = GameData.load()
    if hasattr(args, "template_command") and args.template_command == "convert":
        _run_convert(args, gd)
    elif args.planet_type and args.product:
        _run_generate(args, gd)
    else:
        print("Usage: eve-pi template --planet-type <type> --setup <setup> --product <product>")
        print("       eve-pi template convert --input <file> --to-planet-type <type> --to-product <product>")


def _run_convert(args, gd):
    try:
        with open(args.input, "r", encoding="utf-8") as f:
            template = json.load(f)
    except (IOError, json.JSONDecodeError) as e:
        print(f"Error reading template: {e}")
        sys.exit(1)
    result = convert_template(
        template=template, to_planet_type=args.to_planet_type,
        to_product=args.to_product, game_data=gd,
    )
    print(json.dumps(result, separators=(",", ":")))


def _run_generate(args, gd):
    print(f"Template generation for {args.planet_type} {args.setup} {args.product}")
    print("(Built-in topology generation coming in a future update)")
