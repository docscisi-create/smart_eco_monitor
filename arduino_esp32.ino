/*
  Smart Eco-Monitor — ESP32 Sensor Node
  =====================================
  Sensors:
    - DHT22  → Temperature + Humidity   (pin 4)
    - MQ135  → AQI / Air Quality        (analog pin 34)
    - MQ7    → CO (Carbon Monoxide)     (analog pin 35)
    - MQ2    → Smoke / Gas              (analog pin 32)

  Sends HTTP POST to FastAPI server every SEND_INTERVAL ms.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ─── WiFi ───────────────────────────────────────────────────────────────────
const char* WIFI_SSID     = "YOUR_WIFI_SSID";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";

// ─── Server ─────────────────────────────────────────────────────────────────
const char* SERVER_URL = "https://smartecomonitor-production.up.railway.app/data";  

// ─── Pins ────────────────────────────────────────────────────────────────────
#define DHT_PIN    4
#define DHT_TYPE   DHT22
#define MQ135_PIN  34   // AQI
#define MQ7_PIN    35   // CO
#define MQ2_PIN    32   // Smoke
#define LED_OK     2    // onboard LED — blinks on successful send

// ─── Timing ──────────────────────────────────────────────────────────────────
#define SEND_INTERVAL  2000    // ms between readings
#define RETRY_DELAY    5000    // ms before WiFi retry

DHT dht(DHT_PIN, DHT_TYPE);

// ─── Calibration (adjust to your sensor lot) ─────────────────────────────────
float mq135_scale = 0.1f;   // raw ADC → AQI index (approximate)
float mq7_scale   = 0.05f;  // raw ADC → CO ppm
float mq2_scale   = 0.15f;  // raw ADC → smoke ppm

void setup() {
  Serial.begin(115200);
  pinMode(LED_OK, OUTPUT);
  dht.begin();

  Serial.println("\n🌿 Smart Eco-Monitor starting...");
  connectWiFi();
}

void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 30) {
    delay(500);
    Serial.print(".");
    tries++;
  }
  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi connected. IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n❌ WiFi failed. Will retry...");
  }
}

float readAQI() {
  int raw = analogRead(MQ135_PIN);
  // Simple linear mapping: 0–4095 → 0–500 AQI range
  return constrain((raw / 4095.0f) * 500.0f, 0, 500);
}

float readCO() {
  int raw = analogRead(MQ7_PIN);
  // Approximate ppm: calibrate with known gas concentration for accuracy
  return constrain((raw / 4095.0f) * 1000.0f, 0, 1000);
}

float readSmoke() {
  int raw = analogRead(MQ2_PIN);
  return constrain((raw / 4095.0f) * 1000.0f, 0, 1000);
}

bool sendData(float temp, float hum, float aqi, float co, float smoke) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return false;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

  // Build JSON payload
  StaticJsonDocument<256> doc;
  doc["temp"]      = temp;
  doc["hum"]       = hum;
  doc["aqi"]       = aqi;
  doc["co"]        = co;
  doc["smoke"]     = smoke;
  doc["device_id"] = "ESP32-01";

  String body;
  serializeJson(doc, body);

  int httpCode = http.POST(body);
  http.end();

  if (httpCode == 200) {
    Serial.printf("✅ Sent → T:%.1f H:%.1f AQI:%.0f CO:%.0f Smoke:%.0f\n",
                  temp, hum, aqi, co, smoke);
    return true;
  } else {
    Serial.printf("❌ HTTP %d — server unreachable?\n", httpCode);
    return false;
  }
}

void loop() {
  // Read DHT22
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  // Validate DHT
  if (isnan(temp) || isnan(hum)) {
    Serial.println("⚠️  DHT22 read failed — check wiring");
    delay(2000);
    return;
  }

  // Read gas sensors
  float aqi   = readAQI();
  float co    = readCO();
  float smoke = readSmoke();

  // Send to server
  bool ok = sendData(temp, hum, aqi, co, smoke);

  // Blink LED
  digitalWrite(LED_OK, HIGH);
  delay(ok ? 100 : 500);
  digitalWrite(LED_OK, LOW);

  delay(SEND_INTERVAL);
}
