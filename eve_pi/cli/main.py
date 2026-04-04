"""CLI entry point for eve-pi."""
import argparse
import sys


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="eve-pi", description="EVE Online Planetary Interaction Optimizer")
    subparsers = parser.add_subparsers(dest="command")

    opt_parser = subparsers.add_parser("optimize", help="Optimize colony allocation")
    opt_parser.add_argument("--system", required=True, help="System name (e.g., J153003)")
    opt_parser.add_argument("--characters", type=str, default="1",
                            help="Character specs. Examples: '6', 'Alice,Bob', 'Alice:5,Bob:4' (name:ccu), "
                            "'Alice:5:6,Bob:4:5' (name:ccu:planets)")
    opt_parser.add_argument("--ccu-level", type=int, default=5,
                            help="Default Command Center Upgrades level (0-5), used when not specified per character")
    opt_parser.add_argument("--max-planets", type=int, default=6,
                            help="Default max planets per character (Interplanetary Consolidation, 1-6)")
    opt_parser.add_argument("--cycle-days", type=float, default=4.0, help="Extractor restart cadence in days")
    opt_parser.add_argument("--trips-per-week", type=int, default=2, help="Hauling trips per week")
    opt_parser.add_argument("--cargo-m3", type=float, default=60000.0, help="Cargo capacity in m3")
    opt_parser.add_argument("--mode", choices=["self_sufficient", "import", "hybrid"], default="self_sufficient")
    opt_parser.add_argument("--tax-rate", type=float, default=0.05, help="POCO tax rate")

    tpl_parser = subparsers.add_parser("template", help="Generate or convert templates")
    tpl_parser.add_argument("--planet-type", help="Planet type (e.g., Gas)")
    tpl_parser.add_argument("--setup", help="Setup type (e.g., P1-P2)")
    tpl_parser.add_argument("--product", help="Product name (e.g., Coolant)")

    tpl_sub = tpl_parser.add_subparsers(dest="template_command")
    conv_parser = tpl_sub.add_parser("convert", help="Convert an existing template")
    conv_parser.add_argument("--input", required=True, help="Input template JSON file")
    conv_parser.add_argument("--to-planet-type", help="Target planet type")
    conv_parser.add_argument("--to-product", help="Target product")

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "optimize":
        from eve_pi.cli.optimize import run_optimize
        run_optimize(args)
    elif args.command == "template":
        from eve_pi.cli.template import run_template
        run_template(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
