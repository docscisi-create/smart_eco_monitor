"""
Smart Eco-Monitor — FastAPI Backend
Run: uvicorn server:app --host 0.0.0.0 --port 8000 --reload

Changes vs original:
  - Added root GET / route (fixes "Not Found" on Railway)
  - Replaced ephemeral Excel file with in-memory deque (Railway filesystem is wiped on restart)
  - readings deque capped at MAX_READINGS to bound memory
  - /health no longer crashes when FILE doesn't exist
  - /data/stats and /data/history work purely from in-memory list
  - WebSocket cleanup is thread-safe (copied list before iterating)
  - Removed unused HTMLResponse + asyncio imports
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime
from collections import deque
from typing import Optional
import json

# ─── Config ──────────────────────────────────────────────────────────────────
MAX_READINGS = 10_000   # cap in-memory history

app = FastAPI(title="Smart Eco-Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── State ───────────────────────────────────────────────────────────────────
readings: deque[dict] = deque(maxlen=MAX_READINGS)
latest: dict = {}
clients: list[WebSocket] = []


# ─── Models ──────────────────────────────────────────────────────────────────
class SensorData(BaseModel):
    temp: float
    hum: float
    aqi: float
    co: float
    smoke: float
    device_id: Optional[str] = "ESP32"


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/")
def root():
    """Root route — confirms the API is reachable and lists endpoints."""
    return {
        "service": "Smart Eco-Monitor API",
        "status": "running",
        "total_readings": len(readings),
        "endpoints": {
            "POST /data":          "Submit a sensor reading (ESP32)",
            "GET  /data/latest":   "Most recent reading",
            "GET  /data/history":  "Last N readings  (?limit=200)",
            "GET  /data/stats":    "Min / max / avg per sensor",
            "GET  /health":        "Health check",
            "WS   /ws":            "Real-time WebSocket stream",
            "DELETE /data":        "Clear all stored readings",
            "GET  /docs":          "Interactive API docs (Swagger UI)",
        },
    }


@app.post("/data")
async def receive_data(data: SensorData):
    """ESP32 POSTs sensor readings here."""
    global latest
    now = datetime.now()

    row = {
        "date":  now.strftime("%Y-%m-%d"),
        "time":  now.strftime("%H:%M:%S"),
        "temp":  round(data.temp,  2),
        "hum":   round(data.hum,   2),
        "aqi":   round(data.aqi,   2),
        "co":    round(data.co,    2),
        "smoke": round(data.smoke, 2),
    }

    readings.append(row)
    latest = {**row, "device": data.device_id, "ts": now.isoformat()}

    # Push to all connected WebSocket clients
    msg  = json.dumps(latest)
    dead = []
    for ws in list(clients):          # iterate a copy so removal is safe
        try:
            await ws.send_text(msg)
        except Exception:
            dead.append(ws)
    for ws in dead:
        if ws in clients:
            clients.remove(ws)

    return {"status": "ok", "received": row}


@app.get("/data/latest")
def get_latest():
    """Return the most recent sensor reading."""
    return latest if latest else {"error": "no data yet"}


@app.get("/data/history")
def get_history(limit: int = 200):
    """Return the last `limit` readings (default 200)."""
    data = list(readings)
    return data[-limit:]


@app.get("/data/stats")
def get_stats():
    """Min / max / avg / last for every sensor column."""
    if not readings:
        return {}

    cols = ["temp", "hum", "aqi", "co", "smoke"]
    stats: dict = {}

    for col in cols:
        values = [r[col] for r in readings if col in r]
        if not values:
            continue
        stats[col] = {
            "min":  round(min(values), 2),
            "max":  round(max(values), 2),
            "avg":  round(sum(values) / len(values), 2),
            "last": round(values[-1], 2),
        }

    stats["total_readings"] = len(readings)
    return stats


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Real-time WebSocket stream — push every new reading to connected clients."""
    await ws.accept()
    clients.append(ws)
    try:
        if latest:
            await ws.send_text(json.dumps(latest))
        while True:
            await ws.receive_text()   # keeps connection alive
    except WebSocketDisconnect:
        if ws in clients:
            clients.remove(ws)


@app.get("/health")
def health():
    """Quick health check."""
    return {
        "status":         "running",
        "connected_clients": len(clients),
        "total_readings": len(readings),
    }


@app.delete("/data")
def clear_data():
    """Wipe all in-memory readings and reset latest."""
    global latest
    readings.clear()
    latest = {}
    return {"status": "cleared"}
