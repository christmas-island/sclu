"""
bot.py — SCLU Discord Bot

Commands:
  !sclu                — attach an image to scan
  !sclu 16oz 5.5%      — manual input
  !sclu help           — show help
  /sclu                — slash command (attach image)
"""

import os
import io
import logging
import asyncio

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from sclu import process_image, process_manual, SCLUResult

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Bot setup
# ---------------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

HELP_TEXT = """**🍺 SCLU — Standard Coors Light Units**

Measure any drink in terms of how many Coors Lights it equals.

**Usage:**
`!sclu` + attach a photo of the barcode or label
`!sclu 16oz 5.5%` — manual: volume + ABV
`!sclu 473ml 7.0%` — works in ml too
`/sclu` — slash command with image attachment

**Formula:**
`SCLU = (volume_ml × ABV%) / (355 × 4.2)`

1 Coors Light (12oz, 4.2%) = **1.00 SCLU₄.₂**
"""


def build_embed(result: SCLUResult) -> discord.Embed:
    d = result.drink
    title = f"🍺 {d.name}"

    volume_fl_oz = d.volume_ml / 29.5735
    desc = (
        f"**{d.volume_ml:.0f} ml** ({volume_fl_oz:.1f} fl oz)  •  **{d.abv}% ABV**\n\n"
        f"📊 **Standard Coors Light Units:**\n"
        f"> SCLU₄.₂ = **{result.sclu_42}** ← vs standard (4.2%)\n"
        f"> SCLU₅.₀ = **{result.sclu_50}** ← vs Banquet (5.0%)\n\n"
        f"💬 {result.commentary}"
    )

    embed = discord.Embed(
        title=title,
        description=desc,
        color=discord.Color.gold(),
    )

    source_label = {
        "open_food_facts": "Open Food Facts",
        "upcitemdb":       "UPC Item DB",
        "manual":          "Manual input",
        "off_search+ocr":  "OCR + Open Food Facts search",
    }.get(d.source, d.source)

    embed.set_footer(text=f"Source: {source_label}  |  ABV source: {d.abv_source}")
    return embed


async def _download_attachment(attachment: discord.Attachment) -> bytes:
    buffer = io.BytesIO()
    await attachment.save(buffer)
    return buffer.getvalue()


async def _handle_image(ctx_or_interaction, image_bytes: bytes, followup: bool = False):
    """Run the SCLU pipeline and reply."""
    send = _get_send(ctx_or_interaction, followup)

    result = await process_image(image_bytes)
    if result is None:
        await send(
            "❌ Couldn't identify the drink. Try:\n"
            "• A clearer barcode photo\n"
            "• Manual: `!sclu 12oz 4.2%`"
        )
        return

    embed = build_embed(result)
    await send(embed=embed)


def _get_send(ctx_or_interaction, followup: bool):
    """Return the appropriate send coroutine."""
    if isinstance(ctx_or_interaction, commands.Context):
        return ctx_or_interaction.reply
    else:
        if followup:
            return ctx_or_interaction.followup.send
        return ctx_or_interaction.response.send_message


# ---------------------------------------------------------------------------
# Prefix commands
# ---------------------------------------------------------------------------

@bot.command(name="sclu")
async def sclu_prefix(ctx: commands.Context, *args):
    """Main !sclu command handler."""
    # Help
    if args and args[0].lower() == "help":
        await ctx.reply(HELP_TEXT)
        return

    # Manual input: !sclu 16oz 5.5%
    if len(args) >= 2:
        async with ctx.typing():
            result = await process_manual(args[0], args[1])
        if result is None:
            await ctx.reply("❌ Couldn't parse that. Try: `!sclu 16oz 5.5%` or `!sclu 473ml 7.0%`")
            return
        embed = build_embed(result)
        await ctx.reply(embed=embed)
        return

    # Image attachment
    if ctx.message.attachments:
        attachment = ctx.message.attachments[0]
        if not attachment.content_type or not attachment.content_type.startswith("image/"):
            await ctx.reply("Please attach an image (photo of the barcode or label).")
            return
        async with ctx.typing():
            image_bytes = await _download_attachment(attachment)
            await _handle_image(ctx, image_bytes)
        return

    # Nothing provided
    await ctx.reply(
        "Attach a barcode/label photo or use manual mode:\n"
        "`!sclu 12oz 4.2%`\n"
        "`!sclu help` for full usage"
    )


# ---------------------------------------------------------------------------
# Slash commands
# ---------------------------------------------------------------------------

@bot.tree.command(name="sclu", description="Convert a drink to Standard Coors Light Units")
@app_commands.describe(
    image="Photo of the barcode or label",
    volume="Volume (e.g. 16oz, 473ml) — for manual mode",
    abv="ABV percent (e.g. 5.5) — for manual mode",
)
async def sclu_slash(
    interaction: discord.Interaction,
    image: discord.Attachment = None,
    volume: str = None,
    abv: str = None,
):
    await interaction.response.defer()

    if volume and abv:
        result = await process_manual(volume, abv)
        if result is None:
            await interaction.followup.send("❌ Couldn't parse those values. Try `volume=16oz abv=5.5`")
            return
        await interaction.followup.send(embed=build_embed(result))
        return

    if image:
        if not image.content_type or not image.content_type.startswith("image/"):
            await interaction.followup.send("Please attach an image.")
            return
        image_bytes = await _download_attachment(image)
        await _handle_image(interaction, image_bytes, followup=True)
        return

    await interaction.followup.send(HELP_TEXT)


# ---------------------------------------------------------------------------
# Auto-scan: react to images posted in sclu-designated channels
# ---------------------------------------------------------------------------

AUTOSCAN_CHANNELS: set[str] = set(
    os.getenv("AUTOSCAN_CHANNELS", "").split(",")
) - {""}


@bot.event
async def on_message(message: discord.Message):
    if message.author.bot:
        return

    # Auto-scan if in designated channel and image is attached
    if (
        str(message.channel.id) in AUTOSCAN_CHANNELS
        or (hasattr(message.channel, "name") and message.channel.name in AUTOSCAN_CHANNELS)
    ):
        image_attachments = [
            a for a in message.attachments
            if a.content_type and a.content_type.startswith("image/")
        ]
        if image_attachments:
            async with message.channel.typing():
                image_bytes = await _download_attachment(image_attachments[0])
                ctx = await bot.get_context(message)
                await _handle_image(ctx, image_bytes)
            return  # don't process_commands too — avoid double response

    await bot.process_commands(message)


# ---------------------------------------------------------------------------
# Bot lifecycle events
# ---------------------------------------------------------------------------

@bot.event
async def on_ready():
    logger.info(f"SCLU bot ready — logged in as {bot.user} ({bot.user.id})")
    try:
        synced = await bot.tree.sync()
        logger.info(f"Synced {len(synced)} slash commands")
    except Exception as e:
        logger.error(f"Failed to sync slash commands: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    token = os.getenv("DISCORD_TOKEN")
    if not token:
        raise RuntimeError("DISCORD_TOKEN not set in environment")
    bot.run(token)
