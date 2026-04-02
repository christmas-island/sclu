# SCLU Design Document

**Standard Coors Light Units** — because not all beers are created equal.

---

## Overview

SCLU is a Discord bot that accepts a photo of any alcoholic beverage (typically showing the barcode or label), looks up its volume and ABV, and converts it to Standard Coors Light Units — a universal measure of alcohol content relative to a 12oz Coors Light.

---

## Formula

```
SCLU = (volume_ml × ABV_percent) / (355 × 4.2)
```

Where:
- `355 ml` = 12 fl oz (standard Coors Light can)
- `4.2%` = Coors Light standard ABV
- `5.0%` = Coors Light Banquet ABV (secondary mode)

**Examples:**
- 12oz Coors Light (4.2% ABV) → 1.00 SCLU
- 16oz can of Bud Light (4.2% ABV) → 1.33 SCLU
- 12oz IPA (7.0% ABV) → 1.67 SCLU
- 750ml wine (13% ABV) → 7.37 SCLU
- 1.75L handle of vodka (40% ABV) → 94.08 SCLU

Both modes are always output:
- `SCLU₄.₂` — relative to standard Coors Light (4.2%)
- `SCLU₅.₀` — relative to Coors Light Banquet (5.0%)

---

## Architecture

```
Discord User
     │
     │  uploads image (barcode photo or label)
     ▼
┌─────────────────────────────────────────┐
│              Discord Bot                │
│              (bot.py)                   │
│  - discord.py event handler             │
│  - on_message: detect image attachments │
│  - !sclu command or auto-detect         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│          Barcode Extractor              │
│          (sclu.py)                      │
│  - pyzbar (ZBar) — scan barcode         │
│  - OpenCV for image preprocessing      │
│  - Returns: barcode string (UPC/EAN)    │
└──────────────┬──────────────────────────┘
               │ barcode or None
               ▼
┌─────────────────────────────────────────┐
│           Product Lookup                │
│           (sclu.py)                     │
│  Primary:   Open Food Facts API         │
│  Secondary: UPC Item DB (free tier)     │
│  Fallback:  OCR label extraction        │
│                                         │
│  Returns: {name, volume_ml, abv}        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│           SCLU Calculator               │
│           (sclu.py)                     │
│  - calculate(volume_ml, abv)            │
│  - Returns: sclu_42, sclu_50            │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│         Discord Response                │
│         (bot.py)                        │
│  - Formatted embed with drink info      │
│  - Both SCLU values displayed           │
│  - Fun commentary based on SCLU value   │
└─────────────────────────────────────────┘
```

---

## Tech Stack

| Component | Choice | Rationale |
|-----------|--------|-----------|
| Language | Python 3.11+ | Great library ecosystem, barcode/OCR support |
| Discord | discord.py 2.x | Most mature, well-documented |
| Barcode scan | pyzbar + OpenCV | ZBar is battle-tested for UPC/EAN |
| Primary lookup | Open Food Facts | Free, no API key, huge database |
| Secondary lookup | UPC Item DB | Fills gaps in OFF for US products |
| OCR fallback | pytesseract | Label OCR when barcode scan fails |
| HTTP | aiohttp | Async, matches discord.py's event loop |
| Env config | python-dotenv | Standard .env loading |

### Why discord.py over interactions.py?
discord.py 2.x has full slash command support via `app_commands`, and has better community support. interactions.py is good but less battle-tested for production bots.

### Why Open Food Facts?
- No API key required
- Returns `nutriments` + `quantity` + `product_name`
- Community-maintained, strong beer/beverage coverage
- Fallback to UPCitemdb for US-specific products

---

## Data Flow

### Happy Path (barcode scan → OFF lookup)

```
1. User posts image to Discord
2. Bot downloads attachment to memory buffer
3. pyzbar decodes barcode from image
4. OFF API: GET /product/{barcode}.json
5. Extract: product_name, quantity (→ volume_ml), nutriments.alcohol
6. calculate_sclu(volume_ml, abv)
7. Reply with embed
```

### Fallback: UPC Item DB

```
3b. If OFF returns no result or missing ABV:
4b. UPCitemdb API: GET /trial/lookup?upc={barcode}
5b. Extract product name, size
6b. ABV may still be unknown → use known-ABV DB or prompt user
```

### Fallback: OCR Label

```
3c. If pyzbar fails to find barcode:
4c. pytesseract OCR on full image
5c. Extract brand name / product name from text
6c. Search OFF by product name
7c. Lower confidence — flag in response
```

### Fallback: User-Provided Values

```
If all lookups fail:
!sclu 16oz 5.5%   →  manual input mode
```

---

## ABV Handling

Two output modes are always calculated and displayed:
- **Standard** (`SCLU₄.₂`): divisor = `355 × 4.2 = 1491`
- **Banquet** (`SCLU₅.₀`): divisor = `355 × 5.0 = 1775`

ABV data sources (priority order):
1. Open Food Facts `nutriments.alcohol` field
2. UPC Item DB extended data
3. Internal ABV database (`abv_db.json`) — common beers by brand
4. User prompt (bot asks for ABV if unknown)

---

## Response Format

```
🍺 **Bud Light** (16 fl oz / 473ml, 4.2% ABV)

📊 Standard Coors Light Units:
  SCLU₄.₂ = **1.33** ← vs standard (4.2%)
  SCLU₅.₀ = **1.12** ← vs Banquet (5.0%)

💬 That's 1.33x a Coors Light. Respectable.
```

Commentary tiers:
- `< 0.5` → "Basically water. Sip on, friend."
- `0.5–1.5` → "Solid. You're playing the game."
- `1.5–3.0` → "Now we're cooking. Respect."
- `3.0–6.0` → "This is a statement beverage."
- `> 6.0` → "You absolute unit. This is a multi-Coors equivalent situation."

---

## Commands

| Command | Description |
|---------|-------------|
| `!sclu` (+ image) | Process attached image |
| `!sclu <volume> <abv>` | Manual input, e.g. `!sclu 16oz 5.5%` |
| `!sclu help` | Show help |
| `/sclu` | Slash command equivalent |

---

## Future Work

- Mobile-friendly web UI (upload photo, get SCLU on the spot)
- Expanded ABV database (crowd-sourced, with PR workflow)
- More barcode lookup sources (Untappd API, BeerAdvocate integration)
- SCLU leaderboard / session tracking
- Support for cocktails and mixed drinks
- `!scluboard` — track who's drinking what in a server

---

## Security & Rate Limiting

- Discord attachment downloads: stream to memory, never write to disk
- OFF API: no key needed, but add User-Agent header to be polite
- UPC Item DB: free tier has rate limits — cache results in memory
- Tesseract OCR: runs locally, no external call

---

## Deployment

Target: Docker container, runs on any VPS.

```
docker build -t sclu .
docker run -d --env-file .env sclu
```

Or: deploy to Railway/Fly.io with a single Dockerfile.
