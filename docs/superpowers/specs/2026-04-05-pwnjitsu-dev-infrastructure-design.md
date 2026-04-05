# pwnjitsu.dev Infrastructure Design

## Overview

Multi-tool gaming website at pwnjitsu.dev, hosted on Railway with auto-deploy from GitHub. Two-repo architecture separating open-source tooling libraries from private web infrastructure.

## Repo Structure

### Public Repo: `eve-pi`

Open-source Python library + CLI for EVE Online PI optimization. No web layer.

**Contains:** `eve_pi/` (models, data, optimizer, capacity, extraction, market, templates, CLI), `tests/`, `pyproject.toml`, `CLAUDE.md`, reference templates, data files.

**Does not contain:** Web UI (FastAPI app, Jinja2 templates, static assets), deployment config, Caddyfile.

**Package:** Pure library + CLI. No FastAPI/Jinja2/uvicorn dependencies. Installable via `pip install git+https://github.com/<user>/eve-pi.git`.

### Private Repo: `pwnjitsu`

Web server, UI, landing page, deployment config. Imports eve-pi as a dependency.

```
pwnjitsu/
├── web/
│   ├── app.py                 # main FastAPI app, landing page
│   ├── routes/
│   │   └── eve_pi.py          # eve-pi UI routes mounted at /eve/pi
│   ├── templates/
│   │   ├── landing.html       # pwnjitsu.dev root — tool listing
│   │   ├── base.html          # shared layout (dark theme)
│   │   └── eve_pi/            # moved from eve_pi/web/templates/
│   └── static/                # CSS, assets
├── requirements.txt           # fastapi, uvicorn, jinja2, git+.../eve-pi.git
├── Dockerfile
├── railway.json
├── pyproject.toml
└── CLAUDE.md
```

## Routing

- `pwnjitsu.dev/` — landing page listing available tools
- `pwnjitsu.dev/eve/pi` — PI optimizer main page
- `pwnjitsu.dev/eve/pi/optimize` — form submission
- `pwnjitsu.dev/eve/pi/results` — results page
- `pwnjitsu.dev/eve/pi/api/*` — API endpoints
- `pwnjitsu.dev/eve/pi/template-converter` — template converter page

## Landing Page

Simple dark-themed page with pwnjitsu.dev branding. Card-style listing of available tools. Currently just the EVE PI Optimizer with a brief description and link. Designed to accommodate future tools as new cards.

## Deployment

### Railway

- Single service watching private `pwnjitsu` repo, `main` branch
- Auto-deploy on push to main
- Dockerfile-based Python deployment
- Custom domain: pwnjitsu.dev (CNAME record at registrar)
- Spending cap: ~$10/mo to start (app sleeps if cap hit, no surprise bills)

### Auto-deploy on eve-pi updates

All deployment-specific config lives in the private `pwnjitsu` repo. The public `eve-pi` repo has no knowledge of Railway or deployment.

- GitHub webhook configured in GitHub UI (not in code) on the `eve-pi` repo to notify the `pwnjitsu` repo on push events
- GitHub Action in the `pwnjitsu` repo listens for the webhook and triggers a Railway redeploy
- Result: pushing to eve-pi main automatically updates the live site, with zero deployment code in the public repo

### DNS

CNAME record for `pwnjitsu.dev` pointing to Railway's provided domain, configured at the domain registrar.

## Local Development

```bash
# Clone both repos side by side
C:\Development\
├── eve-pi/         # public repo
└── pwnjitsu/       # private repo

# Install eve-pi as editable dependency
cd pwnjitsu
pip install -e ../eve-pi
pip install -r requirements.txt

# Run locally
uvicorn web.app:app --reload --port 8000
# Site available at http://localhost:8000/eve/pi
```

Same routing structure locally as production. Changes to eve-pi library code are picked up immediately via the editable install.

## Migration Steps (High Level)

1. Create private GitHub repo `pwnjitsu`
2. Create public GitHub repo `eve-pi` (or make current repo public after cleaning)
3. Remove `eve_pi/web/` from the public repo
4. Move web code into the private repo's structure
5. Update imports/paths for the new `/eve/pi` prefix
6. Add Dockerfile and railway.json to private repo
7. Set up Railway service, custom domain, spending cap
8. Configure GitHub webhook + Action for auto-deploy
9. Point pwnjitsu.dev DNS to Railway
