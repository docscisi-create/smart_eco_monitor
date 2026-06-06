/*
  Smart Eco-Monitor — ESP32 Sensor Node
  =====================================
  WiFi credentials are fetched from the server at startup.
  Enter them once at: https://smartecomonitor-production.up.railway.app/setup

  Sensors:
    - DHT22  → Temperature + Humidity   (pin 4)
    - MQ135  → AQI / Air Quality        (analog pin 34)
    - MQ7    → CO (Carbon Monoxide)     (analog pin 35)
    - MQ2    → Smoke / Gas              (analog pin 32)
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ─── Server ───────────────────────────────────────────────────────────────────
const char* SERVER_BASE = "https://smartecomonitor-production.up.railway.app";

// ─── Fallback WiFi (used only to fetch credentials from server) ───────────────
// Use any open network or a mobile hotspot just to reach the server once.
const char* BOOTSTRAP_SSID     = "YOUR_HOTSPOT_SSID";
const char* BOOTSTRAP_PASSWORD = "YOUR_HOTSPOT_PASS";

// ─── Pins ─────────────────────────────────────────────────────────────────────
#define DHT_PIN    4
#define DHT_TYPE   DHT22
#define MQ135_PIN  34
#define MQ7_PIN    35
#define MQ2_PIN    32
#define LED_OK     2

// ─── Timing ───────────────────────────────────────────────────────────────────
#define SEND_INTERVAL 2000

DHT dht(DHT_PIN, DHT_TYPE);

String real_ssid     = "";
String real_password = "";

// ─── Connect to a given WiFi ──────────────────────────────────────────────────
bool connectWiFi(const char* ssid, const char* pass, int retries = 20) {
  Serial.printf("Connecting to: %s ", ssid);
  WiFi.begin(ssid, pass);
  for (int i = 0; i < retries; i++) {
    if (WiFi.status() == WL_CONNECTED) {
      Serial.println("\n✅ Connected! IP: " + WiFi.localIP().toString());
      return true;
    }
    delay(500); Serial.print(".");
  }
  Serial.println("\n❌ Failed.");
  WiFi.disconnect();
  return false;
}

// ─── Fetch real WiFi credentials from server ─────────────────────────────────
bool fetchCredentials() {
  Serial.println("📥 Fetching WiFi config from server...");
  HTTPClient http;
  http.begin(String(SERVER_BASE) + "/config");
  http.setTimeout(8000);
  int code = http.GET();

  if (code != 200) {
    Serial.printf("❌ Config fetch failed: HTTP %d\n", code);
    http.end();
    return false;
  }

  String body = http.getString();
  http.end();

  StaticJsonDocument<256> doc;
  if (deserializeJson(doc, body)) {
    Serial.println("❌ JSON parse error");
    return false;
  }

  if (!doc["configured"].as<bool>()) {
    Serial.println("⚠️  No WiFi saved yet. Go to /setup on the website.");
    return false;
  }

  real_ssid     = doc["ssid"].as<String>();
  real_password = doc["password"].as<String>();
  Serial.println("✅ Got credentials for: " + real_ssid);
  return true;
}

// ─── Sensor readers ───────────────────────────────────────────────────────────
float readAQI()   { return constrain((analogRead(MQ135_PIN)/4095.0f)*500.0f,  0, 500);  }
float readCO()    { return constrain((analogRead(MQ7_PIN)  /4095.0f)*1000.0f, 0, 1000); }
float readSmoke() { return constrain((analogRead(MQ2_PIN)  /4095.0f)*1000.0f, 0, 1000); }

// ─── Send sensor data ─────────────────────────────────────────────────────────
bool sendData(float temp, float hum, float aqi, float co, float smoke) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi(real_ssid.c_str(), real_password.c_str());
    return false;
  }
  HTTPClient http;
  http.begin(String(SERVER_BASE) + "/data");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

  StaticJsonDocument<256> doc;
  doc["temp"] = temp; doc["hum"]  = hum;   doc["aqi"]  = aqi;
  doc["co"]   = co;   doc["smoke"]= smoke;  doc["device_id"] = "ESP32-01";

  String body; serializeJson(doc, body);
  int code = http.POST(body);
  http.end();

  if (code == 200) {
    Serial.printf("✅ Sent → T:%.1f H:%.1f AQI:%.0f CO:%.0f Smoke:%.0f\n",
                  temp, hum, aqi, co, smoke);
    return true;
  }
  Serial.printf("❌ HTTP %d\n", code);
  return false;
}

// ─── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);
  pinMode(LED_OK, OUTPUT);
  dht.begin();
  Serial.println("\n🌿 Smart Eco-Monitor starting...");

  // Step 1: connect via bootstrap hotspot to reach the server
  if (!connectWiFi(BOOTSTRAP_SSID, BOOTSTRAP_PASSWORD)) {
    Serial.println("⛔ Cannot reach server. Check bootstrap WiFi and restart.");
    while (true) { delay(5000); }
  }

  // Step 2: fetch the real credentials saved on the website
  if (!fetchCredentials()) {
    Serial.println("⛔ No credentials on server. Open /setup and save your WiFi.");
    while (true) { delay(5000); }
  }

  // Step 3: reconnect using the real home/office WiFi
  WiFi.disconnect();
  delay(500);
  if (!connectWiFi(real_ssid.c_str(), real_password.c_str())) {
    Serial.println("⛔ Could not connect to saved WiFi. Check credentials at /setup.");
    while (true) { delay(5000); }
  }

  Serial.println("🚀 Ready — sending sensor data every 2 seconds.");
}

// ─── Loop ─────────────────────────────────────────────────────────────────────
void loop() {
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  if (isnan(temp) || isnan(hum)) {
    Serial.println("⚠️  DHT22 read failed — check wiring");
    delay(2000); return;
  }

  bool ok = sendData(temp, hum, readAQI(), readCO(), readSmoke());

  digitalWrite(LED_OK, HIGH);
  delay(ok ? 100 : 500);
  digitalWrite(LED_OK, LOW);
  delay(SEND_INTERVAL);
}
