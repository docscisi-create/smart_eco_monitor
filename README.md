# Smart Eco-Monitor v2.0

Real-time environmental monitoring system — ESP32 → FastAPI → Web Dashboard

## Architecture

```
[DHT22 + MQ135 + MQ7 + MQ2]
        ↓
    [ESP32]
        ↓  HTTP POST /data  (WiFi)
    [FastAPI Server]  ←──── WebSocket /ws  ────→  [Web Dashboard]
        ↓
  [sensor_data.xlsx]
```

## Quick Start

### 1. Install Python dependencies
```bash
pip install -r requirements.txt
```

### 2. Start the server
```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

### 3. Flash ESP32
- Open `arduino_esp32.ino` in Arduino IDE
- Install libraries: `WiFi`, `HTTPClient`, `ArduinoJson`, `DHT sensor library`
- Set your WiFi credentials and server IP in the sketch
- Flash to ESP32

### 4. Open Dashboard
- Navigate to `http://localhost:8000` or open `dashboard.html`
- Or run the Streamlit version: `streamlit run streamlit_dashboard.py`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/data` | Receive sensor reading from ESP32 |
| GET | `/data/latest` | Get most recent reading |
| GET | `/data/history?limit=200` | Get historical readings |
| GET | `/data/stats` | Summary statistics |
| WS | `/ws` | WebSocket real-time stream |
| DELETE | `/data` | Clear all stored data |
| GET | `/health` | Server health check |

## Sensor Wiring (ESP32)

| Sensor | ESP32 Pin | Notes |
|--------|-----------|-------|
| DHT22 DATA | GPIO 4 | 10kΩ pull-up to 3.3V |
| MQ135 AOUT | GPIO 34 | AQI / air quality |
| MQ7 AOUT | GPIO 35 | CO (carbon monoxide) |
| MQ2 AOUT | GPIO 32 | Smoke / LPG / gas |

## Alert Thresholds (configurable in dashboard)

| Sensor | Warning | Danger |
|--------|---------|--------|
| Temperature | — | > 45°C |
| Humidity | > 85% | — |
| AQI | — | > 100 |
| CO | — | > 100 ppm |
| Smoke | — | > 400 ppm |
