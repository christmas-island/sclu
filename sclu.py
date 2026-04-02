"""
sclu.py — Standard Coors Light Units core logic

Handles:
  - SCLU calculation
  - Barcode extraction from image bytes
  - Product lookup (Open Food Facts → UPC Item DB → OCR fallback)
  - Volume parsing
"""

import io
import re
import logging
import asyncio
from dataclasses import dataclass, field
from typing import Optional

import aiohttp
import cv2
import numpy as np
from PIL import Image
from pyzbar import pyzbar

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SCLU_STANDARD_DIVISOR = 355 * 4.2   # 1491.0  — vs Coors Light (4.2%)
SCLU_BANQUET_DIVISOR  = 355 * 5.0   # 1775.0  — vs Coors Light Banquet (5.0%)

OFF_API_BASE   = "https://world.openfoodfacts.org/api/v0/product"
UPCDB_API_BASE = "https://api.upcitemdb.com/prod/trial/lookup"

# Known ABV fallback database (common beers). Extend as needed.
KNOWN_ABV: dict[str, float] = {
    "coors light":        4.2,
    "coors banquet":      5.0,
    "bud light":          4.2,
    "budweiser":          5.0,
    "miller lite":        4.2,
    "miller high life":   4.6,
    "pbr":                4.74,
    "pabst blue ribbon":  4.74,
    "corona extra":       4.6,
    "corona light":       4.1,
    "heineken":           5.0,
    "stella artois":      5.0,
    "dos equis":          4.2,
    "modelo especial":    4.4,
    "blue moon":          5.4,
    "sierra nevada pale": 5.6,
    "sam adams boston":   5.0,
    "white claw":         5.0,
    "truly":              5.0,
    "hard mountain dew":  5.0,
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class DrinkInfo:
    name:      str
    volume_ml: float
    abv:       float
    barcode:   Optional[str] = None
    source:    str = "unknown"
    abv_source: str = "lookup"


@dataclass
class SCLUResult:
    drink:    DrinkInfo
    sclu_42:  float   # vs standard Coors Light (4.2%)
    sclu_50:  float   # vs Coors Light Banquet (5.0%)
    commentary: str = ""


# ---------------------------------------------------------------------------
# SCLU calculation
# ---------------------------------------------------------------------------

def calculate_sclu(volume_ml: float, abv: float) -> tuple[float, float]:
    """Return (sclu_42, sclu_50) for a given volume/ABV."""
    alcohol_ml = volume_ml * (abv / 100)
    sclu_42 = alcohol_ml / (SCLU_STANDARD_DIVISOR / 100)
    sclu_50 = alcohol_ml / (SCLU_BANQUET_DIVISOR / 100)
    return round(sclu_42, 3), round(sclu_50, 3)


def get_commentary(sclu: float) -> str:
    if sclu < 0.5:
        return "Basically water. Sip on, friend. 💧"
    elif sclu < 1.5:
        return "Solid. You're playing the game. 🍺"
    elif sclu < 3.0:
        return "Now we're cooking. Respect. 🔥"
    elif sclu < 6.0:
        return "This is a statement beverage. 💪"
    else:
        return "You absolute unit. This is a multi-Coors equivalent situation. 🫡"


# ---------------------------------------------------------------------------
# Volume parsing
# ---------------------------------------------------------------------------

_VOLUME_PATTERNS = [
    # "355 ml", "355ml"
    (re.compile(r'(\d+(?:\.\d+)?)\s*ml', re.I), 1.0),
    # "12 fl oz", "12oz", "12 oz"
    (re.compile(r'(\d+(?:\.\d+)?)\s*(?:fl\.?\s*)?oz', re.I), 29.5735),
    # "1 L", "1.5l"
    (re.compile(r'(\d+(?:\.\d+)?)\s*l(?:iter)?s?', re.I), 1000.0),
    # "500 cl"
    (re.compile(r'(\d+(?:\.\d+)?)\s*cl', re.I), 10.0),
]


def parse_volume_ml(text: str) -> Optional[float]:
    """Try to extract a volume in ml from a text string."""
    for pattern, multiplier in _VOLUME_PATTERNS:
        m = pattern.search(text)
        if m:
            return float(m.group(1)) * multiplier
    return None


# ---------------------------------------------------------------------------
# Barcode extraction
# ---------------------------------------------------------------------------

def extract_barcode(image_bytes: bytes) -> Optional[str]:
    """
    Attempt to read a UPC/EAN barcode from image bytes using pyzbar.
    Tries multiple preprocessing passes to improve detection.
    """
    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        arr = np.array(img)
        bgr = cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)

        for preprocessed in _preprocess_variants(bgr):
            codes = pyzbar.decode(preprocessed)
            for code in codes:
                if code.type in ("EAN13", "EAN8", "UPCA", "UPCE", "CODE128", "CODE39"):
                    barcode_str = code.data.decode("utf-8", errors="ignore")
                    logger.info(f"Barcode found: {barcode_str} ({code.type})")
                    return barcode_str
    except Exception as e:
        logger.warning(f"Barcode extraction failed: {e}")
    return None


def _preprocess_variants(bgr):
    """Yield several preprocessed versions of the image to maximise scan success."""
    # Original
    yield bgr

    # Grayscale
    gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)
    yield gray

    # Upscale small images
    h, w = bgr.shape[:2]
    if max(h, w) < 800:
        scale = 800 / max(h, w)
        big = cv2.resize(bgr, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_CUBIC)
        yield big
        yield cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

    # Sharpen + threshold
    kernel = np.array([[-1,-1,-1],[-1,9,-1],[-1,-1,-1]])
    sharp = cv2.filter2D(gray, -1, kernel)
    _, thresh = cv2.threshold(sharp, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    yield thresh


# ---------------------------------------------------------------------------
# Product lookup — Open Food Facts
# ---------------------------------------------------------------------------

async def lookup_off(barcode: str, session: aiohttp.ClientSession) -> Optional[DrinkInfo]:
    """Query Open Food Facts for product info."""
    url = f"{OFF_API_BASE}/{barcode}.json"
    try:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            if data.get("status") != 1:
                return None

            product = data["product"]
            name    = product.get("product_name") or product.get("product_name_en", "Unknown")
            qty     = product.get("quantity", "")
            volume  = parse_volume_ml(qty)

            # ABV from nutriments
            abv = None
            nutriments = product.get("nutriments", {})
            for key in ("alcohol", "alcohol_100g", "alcohol_serving"):
                val = nutriments.get(key)
                if val is not None:
                    try:
                        abv = float(val)
                        break
                    except (ValueError, TypeError):
                        pass

            if volume is None:
                logger.debug(f"OFF: no volume found in quantity='{qty}'")
                return None

            abv_source = "off_nutriments"
            if abv is None:
                abv = _abv_from_name(name)
                abv_source = "known_db" if abv else "unknown"

            if abv is None:
                return None

            return DrinkInfo(
                name=name,
                volume_ml=volume,
                abv=abv,
                barcode=barcode,
                source="open_food_facts",
                abv_source=abv_source,
            )
    except Exception as e:
        logger.warning(f"OFF lookup failed for {barcode}: {e}")
        return None


# ---------------------------------------------------------------------------
# Product lookup — UPC Item DB
# ---------------------------------------------------------------------------

async def lookup_upcdb(barcode: str, session: aiohttp.ClientSession) -> Optional[DrinkInfo]:
    """Query UPC Item DB as a secondary source."""
    try:
        async with session.get(
            UPCDB_API_BASE,
            params={"upc": barcode},
            timeout=aiohttp.ClientTimeout(total=10),
        ) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            items = data.get("items", [])
            if not items:
                return None

            item    = items[0]
            name    = item.get("title", "Unknown")
            size    = item.get("size", "")
            volume  = parse_volume_ml(size)

            if volume is None:
                return None

            abv = _abv_from_name(name)
            if abv is None:
                return None

            return DrinkInfo(
                name=name,
                volume_ml=volume,
                abv=abv,
                barcode=barcode,
                source="upcitemdb",
                abv_source="known_db",
            )
    except Exception as e:
        logger.warning(f"UPC Item DB lookup failed for {barcode}: {e}")
        return None


# ---------------------------------------------------------------------------
# OCR fallback
# ---------------------------------------------------------------------------

def ocr_fallback(image_bytes: bytes) -> Optional[str]:
    """
    Use pytesseract to extract text from label when barcode scan fails.
    Returns extracted text for product-name search.
    """
    try:
        import pytesseract  # optional dependency
        img = Image.open(io.BytesIO(image_bytes))
        text = pytesseract.image_to_string(img)
        logger.info(f"OCR text: {text[:200]!r}")
        return text
    except ImportError:
        logger.warning("pytesseract not installed — OCR fallback unavailable")
        return None
    except Exception as e:
        logger.warning(f"OCR failed: {e}")
        return None


async def lookup_by_name(name: str, session: aiohttp.ClientSession) -> Optional[DrinkInfo]:
    """Search Open Food Facts by product name (OCR fallback path)."""
    try:
        url = "https://world.openfoodfacts.org/cgi/search.pl"
        params = {
            "search_terms": name,
            "search_simple": 1,
            "action": "process",
            "json": 1,
            "page_size": 5,
        }
        async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            products = data.get("products", [])
            for product in products:
                qty    = product.get("quantity", "")
                volume = parse_volume_ml(qty)
                if volume is None:
                    continue
                pname = product.get("product_name") or name
                abv = None
                nutriments = product.get("nutriments", {})
                for key in ("alcohol", "alcohol_100g"):
                    val = nutriments.get(key)
                    if val is not None:
                        try:
                            abv = float(val)
                            break
                        except (ValueError, TypeError):
                            pass
                if abv is None:
                    abv = _abv_from_name(pname)
                if abv is None:
                    continue
                return DrinkInfo(
                    name=pname,
                    volume_ml=volume,
                    abv=abv,
                    source="off_search",
                    abv_source="off_nutriments" if abv else "known_db",
                )
    except Exception as e:
        logger.warning(f"Name search failed: {e}")
    return None


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

async def process_image(image_bytes: bytes) -> Optional[SCLUResult]:
    """
    Full pipeline: barcode → lookup → calculate.
    Returns SCLUResult or None if everything fails.
    """
    headers = {"User-Agent": "SCLUBot/1.0 (github.com/christmas-island/sclu)"}

    async with aiohttp.ClientSession(headers=headers) as session:
        # Step 1: Extract barcode
        barcode = extract_barcode(image_bytes)

        drink = None
        if barcode:
            logger.info(f"Trying OFF lookup for {barcode}")
            drink = await lookup_off(barcode, session)

            if drink is None:
                logger.info(f"OFF miss, trying UPC Item DB for {barcode}")
                drink = await lookup_upcdb(barcode, session)

        # Step 2: OCR fallback
        if drink is None:
            logger.info("Barcode lookup failed, trying OCR")
            ocr_text = ocr_fallback(image_bytes)
            if ocr_text:
                # Try to extract a meaningful product name
                lines = [l.strip() for l in ocr_text.split("\n") if l.strip()]
                search_term = lines[0] if lines else ocr_text[:50]
                drink = await lookup_by_name(search_term, session)
                if drink:
                    drink.source += "+ocr"

    if drink is None:
        return None

    sclu_42, sclu_50 = calculate_sclu(drink.volume_ml, drink.abv)
    commentary = get_commentary(sclu_42)

    return SCLUResult(
        drink=drink,
        sclu_42=sclu_42,
        sclu_50=sclu_50,
        commentary=commentary,
    )


async def process_manual(volume_str: str, abv_str: str) -> Optional[SCLUResult]:
    """Handle manual !sclu <volume> <abv> input."""
    volume = parse_volume_ml(volume_str)
    if volume is None:
        # Try bare number as oz
        try:
            volume = float(volume_str) * 29.5735
        except ValueError:
            return None

    abv_str = abv_str.replace("%", "").strip()
    try:
        abv = float(abv_str)
    except ValueError:
        return None

    drink = DrinkInfo(
        name="Manual input",
        volume_ml=volume,
        abv=abv,
        source="manual",
        abv_source="manual",
    )
    sclu_42, sclu_50 = calculate_sclu(volume, abv)
    commentary = get_commentary(sclu_42)
    return SCLUResult(drink=drink, sclu_42=sclu_42, sclu_50=sclu_50, commentary=commentary)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _abv_from_name(name: str) -> Optional[float]:
    """Look up ABV from known-ABV database by fuzzy name match."""
    lower = name.lower()
    for key, abv in KNOWN_ABV.items():
        if key in lower:
            return abv
    return None


# ---------------------------------------------------------------------------
# CLI testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import sys

    async def _main():
        if len(sys.argv) == 3:
            result = await process_manual(sys.argv[1], sys.argv[2])
        elif len(sys.argv) == 2:
            with open(sys.argv[1], "rb") as f:
                image_bytes = f.read()
            result = await process_image(image_bytes)
        else:
            print("Usage: python sclu.py <image_path>  OR  python sclu.py <volume> <abv>")
            sys.exit(1)

        if result is None:
            print("Could not determine drink info.")
            sys.exit(1)

        d = result.drink
        print(f"\n🍺 {d.name}")
        print(f"   Volume: {d.volume_ml:.0f}ml  |  ABV: {d.abv}%")
        print(f"   SCLU₄.₂ = {result.sclu_42}")
        print(f"   SCLU₅.₀ = {result.sclu_50}")
        print(f"   {result.commentary}")

    asyncio.run(_main())
