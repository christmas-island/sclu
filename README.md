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

### 3. Create a Discord bot application

1. Go to [discord.com/developers/applications](https://discord.com/developers/applications)
2. Click **New Application** → give it a name (e.g. "SCLU Bot") → Create
3. Go to **Bot** in the left sidebar
4. Click **Reset Token** → copy it → paste into `DISCORD_TOKEN` in your `.env`
5. Under **Privileged Gateway Intents**, enable:
   - ✅ **Message Content Intent** (required to read image attachments)
   - ✅ **Server Members Intent** (optional, for future features)
6. Click **Save Changes**

### 4. Invite the bot to your server

Go to **OAuth2 → URL Generator** in the left sidebar and configure:

**Scopes:**
- ✅ `bot`
- ✅ `applications.commands`

**Bot Permissions:**
- ✅ Read Messages / View Channels
- ✅ Send Messages
- ✅ Embed Links
- ✅ Attach Files
- ✅ Read Message History
- ✅ Use Slash Commands

Copy the generated URL and open it in your browser to add the bot to any server where you have **Manage Server** permissions.

**Quick invite URL template** (replace `YOUR_CLIENT_ID` with your app's Client ID from the OAuth2 page):

```
https://discord.com/oauth2/authorize?client_id=YOUR_CLIENT_ID&scope=bot+applications.commands&permissions=274877975552
```

> **Finding your Client ID:** Go to your application → **General Information** → copy the Application ID.

> **Permissions integer `274877975552`** encodes: Read Messages, Send Messages, Embed Links, Attach Files, Read Message History, Use Slash Commands. Generate your own at [discordapi.com/permissions.html](https://discordapi.com/permissions.html) if you need to customize.

### 5. Configure auto-scan channels (optional)

To have the bot automatically SCLU any image dropped in specific channels (no `!sclu` command needed), add channel IDs to your `.env`:

```bash
# Comma-separated Discord channel IDs
AUTOSCAN_CHANNELS=123456789012345678,987654321098765432
```

To find a channel ID: right-click the channel in Discord → **Copy Channel ID** (requires Developer Mode — enable it under User Settings → Advanced).

### 6. Run

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

## Deployment

> **All deployment methods require `DISCORD_TOKEN` to be set.** If you use auto-scan channels, `AUTOSCAN_CHANNELS` must also be set. See `.env.example` for the full list of env vars.

### Docker (recommended)

The easiest way to run SCLU:

```bash
cp .env.example .env
# Edit .env and set DISCORD_TOKEN (and optionally AUTOSCAN_CHANNELS)

docker compose up -d
```

This builds the image and starts the bot with automatic restarts. To rebuild after pulling updates:

```bash
docker compose up -d --build
```

Or run without Compose:

```bash
docker build -t sclu .
docker run -d --env-file .env --restart unless-stopped sclu
```

### Fly.io

```bash
flyctl launch          # creates fly.toml — pick a region, say No to databases
flyctl secrets set DISCORD_TOKEN=your-token-here
flyctl secrets set AUTOSCAN_CHANNELS=channel-id-1,channel-id-2   # optional
flyctl deploy
```

Scale to one machine (bots don't need redundancy):

```bash
flyctl scale count 1
```

### Railway

[![Deploy on Railway](https://railway.com/button.svg)](https://railway.com/template)

1. Click **Deploy on Railway** (or connect your fork)
2. Set environment variables in the Railway dashboard:
   - `DISCORD_TOKEN` (required)
   - `AUTOSCAN_CHANNELS` (optional)
3. Railway auto-deploys on push

### Self-hosted VPS (systemd)

After cloning, installing deps, and creating your `.env`:

```ini
# /etc/systemd/system/sclu-bot.service
[Unit]
Description=SCLU Discord Bot
After=network.target

[Service]
Type=simple
User=sclu
WorkingDirectory=/opt/sclu
EnvironmentFile=/opt/sclu/.env
ExecStart=/opt/sclu/venv/bin/python bot.py
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now sclu-bot
```

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
