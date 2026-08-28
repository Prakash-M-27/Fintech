import asyncio
import json
import logging
from datetime import datetime

import websockets

from config import TWELVEDATA_API_KEY
from pipeline import price_handler

logger = logging.getLogger(__name__)

WS_URL = f"wss://ws.twelvedata.com/v1/quotes/price?apikey={TWELVEDATA_API_KEY}"

SYMBOLS = {
    "gold": "XAU/USD",
}


async def connect_twelvedata() -> None:
    while True:
        try:
            async with websockets.connect(WS_URL, ping_interval=20) as ws:
                await ws.send(json.dumps({"action": "subscribe", "params": {"symbols": ",".join(SYMBOLS.values())}}))
                logger.info("Connected to TwelveData WebSocket (%s)", ",".join(SYMBOLS.values()))
                async for message in ws:
                    try:
                        data = json.loads(message)
                    except json.JSONDecodeError:
                        continue

                    if data.get("event") == "price":
                        symbol = data.get("symbol", "")
                        price = data.get("price")
                        if price is None:
                            continue
                        asset = next((k for k, s in SYMBOLS.items() if s == symbol), None)
                        if not asset:
                            continue
                        payload = {
                            "asset": asset,
                            "price": float(price),
                            "change": float(data["change"]) if data.get("change") is not None else None,
                            "change_pct": float(data["change_percentage"]) if data.get("change_percentage") is not None else None,
                            "volume": int(data["volume"]) if data.get("volume") is not None else None,
                            "timestamp": datetime.now().isoformat() + "Z",
                            "meta": {"symbol": symbol, "type": data.get("type"), "status": "open" if data.get("is_green") is not None else None},
                        }
                        await price_handler(asset, payload)
                        logger.info("%s updated: %s", asset, price)
        except Exception as exc:
            logger.error("TwelveData WebSocket error: %s", exc)
            await asyncio.sleep(5)