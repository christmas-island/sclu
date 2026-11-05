# sclu

SCLU (Standard Coors Light Units) — Discord bot + FastAPI web UI that
converts any alcoholic beverage into Coors Light equivalents via barcode
scan, product lookup, or OCR. Python, no test suite.

See [README.md](README.md) for setup/deploy and [DESIGN.md](DESIGN.md)
for the formula and pipeline architecture.

## Layout

- `sclu.py` — core: formula, volume parsing, barcode extract, Open Food
  Facts / UPC Item DB lookup, OCR fallback, `process_image` /
  `process_manual`
- `bot.py` — Discord bot (`!sclu`, slash `/sclu`, auto-scan channels)
- `api.py` — FastAPI app serving `web/` and JSON conversion endpoints
- `web/` — static browser UI (`index.html`, `app.js`)
- `Dockerfile` / `docker-compose.yml` — bot + API services

## Required

```sh
pip install -r requirements.txt
cp .env.example .env   # set DISCORD_TOKEN
python bot.py          # Discord bot
python api.py          # web API (port from API_PORT, default 8080)
docker compose up -d --build
```

- System deps (see Dockerfile): `libzbar0` (pyzbar), `libgl1` +
  `libglib2.0-0` (OpenCV), `tesseract-ocr` (optional OCR).
- `DISCORD_TOKEN` is required for the bot; Message Content Intent must be
  enabled in the Discord app.

## Key libraries

- **discord.py** — bot
- **pyzbar** + **opencv-python-headless** — barcode extraction
- **aiohttp** — product API lookups (Open Food Facts, UPC Item DB)
- **pytesseract** — label OCR fallback
- **fastapi** / **uvicorn** — web API

## Maintaining this index

- Update the affected `AGENTS.md` files in the same change when paths,
  responsibilities, commands, dependencies, or conventions change.
- Keep indexes brief: record semantic entry points and non-obvious
  constraints; link to existing documentation instead of duplicating it.
- Add a directory index only when it provides useful navigation beyond its
  parent; omit generated, vendored, and fixture trees.
- Do not add `CLAUDE.md` files; Claude Code reads `AGENTS.md` natively, and
  a `CLAUDE.md` anywhere in the tree stops every `AGENTS.md` from loading.
