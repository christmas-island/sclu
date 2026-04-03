"""
api.py — SCLU FastAPI Web Backend

Endpoints:
  GET  /                    — serves web/index.html
  GET  /app.js              — serves web/app.js
  POST /api/sclu/image      — process image (multipart), returns SCLUResult JSON
  GET  /api/sclu/barcode    — lookup barcode by code string, returns SCLUResult JSON
  GET  /api/sclu/manual     — manual calc: ?volume=16oz&abv=5.5, returns SCLUResult JSON
  GET  /api/health          — health check
"""

import os
import logging
from pathlib import Path

from fastapi import FastAPI, File, UploadFile, HTTPException, Query
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from sclu import (
    process_image,
    process_manual,
    calculate_sclu,
    get_commentary,
    extract_barcode,
    lookup_off,
    lookup_upcdb,
    SCLUResult,
    DrinkInfo,
)
import aiohttp

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI(title="SCLU API", version="1.0.0", docs_url="/api/docs", redoc_url=None)

# CORS — allow all origins so the web UI can call from any domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).parent / "web"


def result_to_dict(result: SCLUResult) -> dict:
    d = result.drink
    return {
        "name": d.name,
        "volume_ml": d.volume_ml,
        "abv": d.abv,
        "barcode": d.barcode,
        "source": d.source,
        "abv_source": d.abv_source,
        "sclu_42": result.sclu_42,
        "sclu_50": result.sclu_50,
        "commentary": result.commentary,
    }


# ---------------------------------------------------------------------------
# Static file serving
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def serve_index():
    index = WEB_DIR / "index.html"
    if not index.exists():
        raise HTTPException(status_code=404, detail="index.html not found")
    return HTMLResponse(content=index.read_text(), media_type="text/html")


@app.get("/app.js", include_in_schema=False)
async def serve_appjs():
    appjs = WEB_DIR / "app.js"
    if not appjs.exists():
        raise HTTPException(status_code=404, detail="app.js not found")
    return FileResponse(appjs, media_type="application/javascript")


# ---------------------------------------------------------------------------
# API endpoints
# ---------------------------------------------------------------------------

@app.post("/api/sclu/image")
async def sclu_from_image(file: UploadFile = File(...)):
    """
    Accept an image upload, scan/OCR it, look up the product, and return SCLU values.
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="File must be an image")

    try:
        image_bytes = await file.read()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {e}")

    logger.info(f"Processing image upload: {file.filename}, size={len(image_bytes)} bytes")

    result = await process_image(image_bytes)
    if result is None:
        raise HTTPException(
            status_code=422,
            detail="Could not identify the drink. Try a clearer barcode photo or use manual entry."
        )

    return JSONResponse(result_to_dict(result))


@app.get("/api/sclu/barcode")
async def sclu_from_barcode(code: str = Query(..., description="UPC/EAN barcode string")):
    """
    Look up a product by barcode and return SCLU values.
    """
    if not code or len(code) < 4:
        raise HTTPException(status_code=400, detail="Invalid barcode")

    logger.info(f"Barcode lookup: {code}")

    headers = {"User-Agent": "SCLUBot/1.0 (github.com/christmas-island/sclu)"}
    async with aiohttp.ClientSession(headers=headers) as session:
        drink = await lookup_off(code, session)
        if drink is None:
            drink = await lookup_upcdb(code, session)

    if drink is None:
        raise HTTPException(
            status_code=404,
            detail=f"Product not found for barcode {code}. Try manual entry."
        )

    sclu_42, sclu_50 = calculate_sclu(drink.volume_ml, drink.abv)
    commentary = get_commentary(sclu_42)
    result = SCLUResult(drink=drink, sclu_42=sclu_42, sclu_50=sclu_50, commentary=commentary)
    return JSONResponse(result_to_dict(result))


@app.get("/api/sclu/manual")
async def sclu_manual(
    volume: str = Query(..., description="Volume string, e.g. '16oz', '473ml', '0.5L'"),
    abv: float = Query(..., description="ABV percent, e.g. 5.5"),
    name: str = Query(default="", description="Drink name (optional)"),
):
    """
    Calculate SCLU from manual volume + ABV input.
    """
    if abv <= 0 or abv > 100:
        raise HTTPException(status_code=400, detail="ABV must be between 0 and 100")

    logger.info(f"Manual SCLU: volume={volume}, abv={abv}, name={name}")

    # process_manual takes (volume_str, abv_str)
    result = await process_manual(volume, str(abv))
    if result is None:
        raise HTTPException(
            status_code=400,
            detail=f"Could not parse volume: '{volume}'. Use formats like '16oz', '473ml', '0.5L'"
        )

    # Override name if provided
    if name:
        result.drink.name = name

    return JSONResponse(result_to_dict(result))


@app.get("/api/health")
async def health():
    return {"status": "ok", "service": "sclu-api"}


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("API_PORT", 8080))
    uvicorn.run("api:app", host="0.0.0.0", port=port, reload=False)
