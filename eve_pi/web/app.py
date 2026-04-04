"""FastAPI web UI for the EVE PI Optimizer."""
import json
import traceback
from pathlib import Path
from typing import List, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from eve_pi.cli.optimize import PLANET_TYPE_IDS
from eve_pi.data.loader import GameData
from eve_pi.market.esi import ESIClient
from eve_pi.models.characters import Character
from eve_pi.models.planets import Planet, SolarSystem
from eve_pi.optimizer.allocator import (
    ColonyAssignment,
    ManufacturingNeed,
    OptimizationConstraints,
    OptimizationResult,
    optimize,
)
from eve_pi.templates.converter import convert_template

app = FastAPI(title="EVE PI Optimizer")
app.mount("/static", StaticFiles(directory=Path(__file__).parent / "static"), name="static")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")

# Load game data once at startup
game_data = GameData.load()



def _get_product_lists() -> dict:
    """Build categorized product lists from game data."""
    products_by_tier = {"p1": [], "p2": [], "p3": [], "p4": []}
    for name, mat in game_data.materials.items():
        if mat.tier in products_by_tier:
            products_by_tier[mat.tier].append(name)
    for tier in products_by_tier:
        products_by_tier[tier].sort()
    return products_by_tier


def _get_planet_type_names() -> list:
    """Get sorted list of planet type names."""
    return sorted(game_data.planet_types.keys())


def _render(request, template_name, **context):
    """Helper to render a template with Starlette 1.0 compatible args."""
    return templates.TemplateResponse(request, template_name, context)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    products_by_tier = _get_product_lists()
    all_products = []
    for tier in ("p1", "p2", "p3", "p4"):
        all_products.extend(products_by_tier[tier])

    return _render(request, "index.html",
                   products_by_tier=products_by_tier,
                   all_products=all_products,
                   planet_types=_get_planet_type_names())


@app.post("/optimize", response_class=HTMLResponse)
async def run_optimization(request: Request):
    form = await request.form()

    # Parse form data
    system_name = form.get("system", "").strip()
    mode = form.get("mode", "self_sufficient")
    cycle_days = float(form.get("cycle_days", 4))
    trips_per_week = int(form.get("trips_per_week", 2))
    cargo_m3 = float(form.get("cargo_m3", 60000))
    tax_rate = float(form.get("tax_rate", 0.05))

    # Parse characters from dynamic form fields
    char_names = form.getlist("char_name")
    char_ccus = form.getlist("char_ccu")
    char_planets = form.getlist("char_max_planets")

    characters = []
    for i in range(len(char_names)):
        name = char_names[i].strip() if i < len(char_names) else f"Char{i+1}"
        ccu = int(char_ccus[i]) if i < len(char_ccus) else 5
        max_p = int(char_planets[i]) if i < len(char_planets) else 6
        if name:
            characters.append(Character(name=name, ccu_level=ccu, max_planets=max_p))

    if not characters:
        characters = [Character(name="Char1", ccu_level=5, max_planets=6)]

    # Parse manufacturing needs
    mfg_products = form.getlist("mfg_product")
    mfg_quantities = form.getlist("mfg_quantity")
    manufacturing_needs = []
    for i in range(len(mfg_products)):
        product = mfg_products[i].strip() if i < len(mfg_products) else ""
        qty = int(mfg_quantities[i]) if i < len(mfg_quantities) else 0
        if product and qty > 0:
            manufacturing_needs.append(ManufacturingNeed(product=product, quantity_per_week=qty))

    # Preserve form values for re-rendering
    form_values = {
        "system": system_name,
        "mode": mode,
        "cycle_days": cycle_days,
        "trips_per_week": trips_per_week,
        "cargo_m3": cargo_m3,
        "tax_rate": tax_rate,
        "characters": [{"name": c.name, "ccu_level": c.ccu_level, "max_planets": c.max_planets} for c in characters],
        "manufacturing_needs": [{"product": m.product, "quantity_per_week": m.quantity_per_week} for m in manufacturing_needs],
    }

    products_by_tier = _get_product_lists()
    all_products = []
    for tier in ("p1", "p2", "p3", "p4"):
        all_products.extend(products_by_tier[tier])

    base_ctx = dict(
        form_values=form_values,
        products_by_tier=products_by_tier,
        all_products=all_products,
        planet_types=_get_planet_type_names(),
    )

    if not system_name:
        return _render(request, "index.html", error="System name is required.", **base_ctx)

    error = None
    result = None
    constraints = None

    try:
        esi = ESIClient()

        # Resolve system
        system_id = esi.resolve_system_id(system_name)
        if not system_id:
            return _render(request, "index.html",
                           error=f"Could not find system '{system_name}'. Check spelling and try again.",
                           **base_ctx)

        # Fetch planets
        raw_planets = esi.fetch_system_planets(system_id)
        planets = []
        for rp in raw_planets:
            type_name = PLANET_TYPE_IDS.get(rp["type_id"])
            if type_name and type_name in game_data.planet_types:
                planets.append(Planet(
                    planet_id=rp["planet_id"],
                    planet_type=game_data.planet_types[type_name],
                    radius_km=3000.0,
                ))
        system = SolarSystem(name=system_name, system_id=system_id, planets=planets)

        # Fetch market data
        market = esi.fetch_all_pi_market_data(game_data.materials)

        # Build constraints and optimize
        constraints = OptimizationConstraints(
            system=system,
            characters=characters,
            mode=mode,
            cycle_days=cycle_days,
            hauling_trips_per_week=trips_per_week,
            cargo_capacity_m3=cargo_m3,
            tax_rate=tax_rate,
            manufacturing_needs=manufacturing_needs,
        )
        result = optimize(constraints, market, game_data)

    except Exception as e:
        error = f"Optimization failed: {str(e)}"

    if error:
        return _render(request, "index.html", error=error, **base_ctx)

    # Build feed map for display grouping
    feed_by_factory = {}
    for a in result.feed_assignments:
        factory_product = a.feeds.replace("-> ", "").replace(" factory", "") if a.feeds else ""
        if factory_product not in feed_by_factory:
            feed_by_factory[factory_product] = []
        feed_by_factory[factory_product].append(a)

    return _render(request, "results.html",
                   result=result,
                   constraints=constraints,
                   feed_by_factory=feed_by_factory,
                   form_values=form_values)


@app.get("/template-converter", response_class=HTMLResponse)
async def template_converter_page(request: Request):
    products_by_tier = _get_product_lists()
    converter_products = []
    for tier in ("p2", "p3", "p4"):
        converter_products.extend(products_by_tier[tier])
    return _render(request, "template_converter.html",
                   planet_types=_get_planet_type_names(),
                   products=converter_products)


@app.post("/template/convert", response_class=JSONResponse)
async def convert_template_route(request: Request):
    form = await request.form()
    template_json = form.get("template_json", "").strip()
    to_planet_type = form.get("to_planet_type", "").strip() or None
    to_product = form.get("to_product", "").strip() or None

    if not template_json:
        return JSONResponse({"error": "Template JSON is required."}, status_code=400)

    try:
        template = json.loads(template_json)
    except json.JSONDecodeError as e:
        return JSONResponse({"error": f"Invalid JSON: {str(e)}"}, status_code=400)

    try:
        result = convert_template(template, to_planet_type, to_product, game_data)
        return JSONResponse({"result": result})
    except Exception as e:
        return JSONResponse({"error": f"Conversion failed: {str(e)}"}, status_code=500)



if __name__ == "__main__":
    import uvicorn
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port)
