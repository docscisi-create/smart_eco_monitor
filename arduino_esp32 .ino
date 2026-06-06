/*
  Smart Eco-Monitor — ESP32 Sensor Node
  =====================================
  Sensors:
    - DHT22  → Temperature + Humidity   (pin 4)
    - MQ135  → AQI / Air Quality        (analog pin 34)
    - MQ7    → CO (Carbon Monoxide)     (analog pin 35)
    - MQ2    → Smoke / Gas              (analog pin 32)

  WiFi credentials are entered via Serial Monitor at startup.
  No need to hardcode SSID or password in the code.
*/

#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// ─── Server ──────────────────────────────────────────────────────────────────
const char* SERVER_URL = "https://smartecomonitor-production.up.railway.app/data";

// ─── Pins ─────────────────────────────────────────────────────────────────────
#define DHT_PIN    4
#define DHT_TYPE   DHT22
#define MQ135_PIN  34
#define MQ7_PIN    35
#define MQ2_PIN    32
#define LED_OK     2

// ─── Timing ───────────────────────────────────────────────────────────────────
#define SEND_INTERVAL  2000
#define RETRY_DELAY    5000

// ─── Calibration ──────────────────────────────────────────────────────────────
float mq135_scale = 0.1f;
float mq7_scale   = 0.05f;
float mq2_scale   = 0.15f;

DHT dht(DHT_PIN, DHT_TYPE);

// ─── WiFi credentials (filled at runtime) ─────────────────────────────────────
String wifi_ssid     = "";
String wifi_password = "";

// ─── Read a line from Serial (blocks until Enter is pressed) ──────────────────
String readLine() {
  String input = "";
  while (true) {
    if (Serial.available()) {
      char c = Serial.read();
      if (c == '\n' || c == '\r') {
        if (input.length() > 0) return input;   // ignore empty Enter presses
      } else {
        input += c;
        Serial.print(c);   // echo character back so user can see what they type
      }
    }
  }
}

// ─── Ask user for credentials via Serial Monitor ──────────────────────────────
void askCredentials() {
  Serial.println("\n========================================");
  Serial.println("   Smart Eco-Monitor — WiFi Setup");
  Serial.println("========================================");
  Serial.println("Open Serial Monitor at 115200 baud.");
  Serial.println("Make sure 'No line ending' is selected.");
  Serial.println();

  Serial.print("Enter WiFi name (SSID): ");
  wifi_ssid = readLine();
  Serial.println();

  Serial.print("Enter WiFi password:    ");
  wifi_password = readLine();
  Serial.println();

  Serial.println("----------------------------------------");
  Serial.println("SSID     : " + wifi_ssid);
  Serial.println("Password : ********");
  Serial.println("----------------------------------------");
}

// ─── Connect to WiFi ──────────────────────────────────────────────────────────
void connectWiFi() {
  Serial.print("Connecting to WiFi");
  WiFi.begin(wifi_ssid.c_str(), wifi_password.c_str());

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 30) {
    delay(500);
    Serial.print(".");
    tries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.println("\n✅ WiFi connected! IP: " + WiFi.localIP().toString());
  } else {
    Serial.println("\n❌ WiFi failed. Check SSID/password and restart.");
    Serial.println("Restarting in 5 seconds...");
    delay(5000);
    ESP.restart();   // restart so user can re-enter credentials
  }
}

// ─── Sensor readers ───────────────────────────────────────────────────────────
float readAQI() {
  int raw = analogRead(MQ135_PIN);
  return constrain((raw / 4095.0f) * 500.0f, 0, 500);
}

float readCO() {
  int raw = analogRead(MQ7_PIN);
  return constrain((raw / 4095.0f) * 1000.0f, 0, 1000);
}

float readSmoke() {
  int raw = analogRead(MQ2_PIN);
  return constrain((raw / 4095.0f) * 1000.0f, 0, 1000);
}

// ─── Send data to server ──────────────────────────────────────────────────────
bool sendData(float temp, float hum, float aqi, float co, float smoke) {
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
    return false;
  }

  HTTPClient http;
  http.begin(SERVER_URL);
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);

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

// ─── Setup ────────────────────────────────────────────────────────────────────
void setup() {
  Serial.begin(115200);
  delay(1000);   // give Serial Monitor time to open

  pinMode(LED_OK, OUTPUT);
  dht.begin();

  Serial.println("\n🌿 Smart Eco-Monitor starting...");

  askCredentials();   // prompt user for WiFi name + password
  connectWiFi();
}

// ─── Main loop ────────────────────────────────────────────────────────────────
void loop() {
  float temp = dht.readTemperature();
  float hum  = dht.readHumidity();

  if (isnan(temp) || isnan(hum)) {
    Serial.println("⚠️  DHT22 read failed — check wiring");
    delay(2000);
    return;
  }

  float aqi   = readAQI();
  float co    = readCO();
  float smoke = readSmoke();

  bool ok = sendData(temp, hum, aqi, co, smoke);

  digitalWrite(LED_OK, HIGH);
  delay(ok ? 100 : 500);
  digitalWrite(LED_OK, LOW);

  delay(SEND_INTERVAL);
}
