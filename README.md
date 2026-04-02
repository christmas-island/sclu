# 🍺 SCLU — Standard Coors Light Units

> Because not all beers are created equal.

SCLU converts any alcoholic beverage to a universal unit — **how many Coors Lights is this thing?**

---

## The Formula

```
SCLU = (volume_ml × ABV_percent) / (355 × 4.2)
```

| Reference | Volume | ABV | SCLU |
|-----------|--------|-----|------|
| Coors Light (standard) | 355ml (12oz) | 4.2% | **1.00** |
| Coors Light Banquet | 355ml (12oz) | 5.0% | **1.19** |

The bot outputs **two values**:
- `SCLU₄.₂` — relative to standard Coors Light (4.2%)
- `SCLU₅.₀` — relative to Coors Light Banquet (5.0%)

### Example Outputs

| Drink | Volume | ABV | SCLU₄.₂ | SCLU₅.₀ |
|-------|--------|-----|---------|---------|
| Coors Light | 355ml | 4.2% | 1.00 | 0.84 |
| Bud Light 16oz | 473ml | 4.2% | 1.33 | 1.12 |
| IPA 12oz | 355ml | 7.0% | 1.67 | 1.40 |
| Wine 750ml | 750ml | 13.0% | 7.37 | 6.19 |
| Handle of vodka 1.75L | 1750ml | 40.0% | 94.08 | 78.99 |

---

## Features

- 📸 **Barcode scanning** — upload a photo of the barcode, bot looks it up automatically
- 🔍 **Product lookup** — searches Open Food Facts and UPC Item DB
- 🔤 **OCR fallback** — if barcode scan fails, reads the label text
- ✏️ **Manual mode** — `!sclu 16oz 5.5%` when photo isn't available
- ⚡ **Auto-scan channels** — configure channels where any image gets scanned automatically

---

## Setup

### 1. Clone and install

```bash
git clone https://github.com/christmas-island/sclu
cd sclu
pip install -r requirements.txt
```

> **Note:** `pyzbar` requires the ZBar system library.
> - macOS: `brew install zbar`
> - Ubuntu/Debian: `apt install libzbar0`
> - Windows: included in the wheel

> **Note:** `pytesseract` requires Tesseract OCR (optional, for label fallback):
> - macOS: `brew install tesseract`
> - Ubuntu/Debian: `apt install tesseract-ocr`

### 2. Configure

```bash
cp .env.example .env
# Edit .env and set DISCORD_TOKEN
```

### 3. Create a Discord bot

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Create New Application → Bot → Reset Token
3. Enable **Message Content Intent** under Privileged Gateway Intents
4. Copy token to `DISCORD_TOKEN` in `.env`
5. Invite bot with: `applications.commands` + `bot` scopes, with `Send Messages` + `Read Message History` permissions

### 4. Run

```bash
python bot.py
```

---

## Usage

### Photo mode (recommended)

1. Upload a photo of the barcode or label in Discord
2. Type `!sclu` in the same message

Or configure an auto-scan channel and just drop the photo — no command needed.

### Manual mode

```
!sclu 12oz 4.2%
!sclu 16oz 5.5%
!sclu 473ml 7.0%
```

### Slash command

```
/sclu image:<attach photo>
/sclu volume:16oz abv:5.5
```

### Help

```
!sclu help
```

---

## Docker

```bash
docker build -t sclu .
docker run -d --env-file .env sclu
```

*(Dockerfile coming soon — see [#4](https://github.com/christmas-island/sclu/issues/4))*

---

## Architecture

See [DESIGN.md](DESIGN.md) for the full design document including:
- Data flow diagrams
- Barcode lookup strategy
- OCR fallback approach
- ABV mode handling

---

## Contributing

Issues and PRs welcome. See [open issues](https://github.com/christmas-island/sclu/issues) for planned features.

---

## License

MIT
