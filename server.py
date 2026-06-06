"""
Smart Eco-Monitor — FastAPI Backend
Run: uvicorn server:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from datetime import datetime
import pandas as pd
import os, asyncio, json
from typing import Optional

app = FastAPI(title="Smart Eco-Monitor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FILE = "sensor_data.xlsx"
latest: dict = {}
clients: list[WebSocket] = []

if not os.path.exists(FILE):
    pd.DataFrame(columns=["date","time","temp","hum","aqi","co","smoke"]).to_excel(FILE, index=False)


class SensorData(BaseModel):
    temp: float
    hum: float
    aqi: float
    co: float
    smoke: float
    device_id: Optional[str] = "ESP32"


@app.post("/data")
async def receive_data(data: SensorData):
    """ESP32/Arduino POSTs sensor readings here."""
    global latest
    now = datetime.now()
    row = {
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M:%S"),
        "temp": round(data.temp, 2),
        "hum": round(data.hum, 2),
        "aqi": round(data.aqi, 2),
        "co": round(data.co, 2),
        "smoke": round(data.smoke, 2),
    }
    latest = {**row, "device": data.device_id, "ts": now.isoformat()}

    # Save to Excel every reading
    try:
        df = pd.read_excel(FILE)
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
        df.to_excel(FILE, index=False)
    except Exception as e:
        print(f"Excel error: {e}")

    # Push to all WebSocket clients
    msg = json.dumps(latest)
    dead = []
    for ws in clients:
        try:
            await ws.send_text(msg)
        except:
            dead.append(ws)
    for ws in dead:
        clients.remove(ws)

    return {"status": "ok", "received": row}


@app.get("/data/latest")
def get_latest():
    """Dashboard polls this endpoint."""
    return latest if latest else {"error": "no data yet"}


@app.get("/data/history")
def get_history(limit: int = 200):
    """Return last N readings from Excel."""
    if not os.path.exists(FILE):
        return []
    df = pd.read_excel(FILE)
    return df.tail(limit).to_dict(orient="records")


@app.get("/data/stats")
def get_stats():
    """Summary statistics for analytics."""
    if not os.path.exists(FILE):
        return {}
    df = pd.read_excel(FILE)
    if df.empty:
        return {}
    cols = ["temp","hum","aqi","co","smoke"]
    stats = {}
    for c in cols:
        if c in df.columns:
            stats[c] = {
                "min": round(float(df[c].min()), 2),
                "max": round(float(df[c].max()), 2),
                "avg": round(float(df[c].mean()), 2),
                "last": round(float(df[c].iloc[-1]), 2) if len(df) else 0,
            }
    stats["total_readings"] = len(df)
    return stats


@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """Real-time WebSocket stream."""
    await ws.accept()
    clients.append(ws)
    try:
        # Send latest immediately on connect
        if latest:
            await ws.send_text(json.dumps(latest))
        while True:
            await ws.receive_text()   # keep alive
    except WebSocketDisconnect:
        clients.remove(ws)


@app.get("/health")
def health():
    return {"status": "running", "clients": len(clients), "readings": len(pd.read_excel(FILE)) if os.path.exists(FILE) else 0}


@app.delete("/data")
def clear_data():
    """Reset all stored data."""
    pd.DataFrame(columns=["date","time","temp","hum","aqi","co","smoke"]).to_excel(FILE, index=False)
    return {"status": "cleared"}
