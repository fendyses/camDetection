// camDetection - ESP32 warning light
//
// The camDetection app sends one line over USB every half second:
//   "ON"  -> a chosen object (e.g. a cow) is on the road  -> blink the light
//   "OFF" -> nothing on the road                          -> light off
// The light is OFF at power-up, and goes OFF by itself if the app stops
// sending (app closed, Mac asleep, cable pulled).
//
// Wiring: LED (with a 220 ohm resistor) or relay module input on LIGHT_PIN, GND to GND.
//         Buzzer + (or module I/O pin) on BUZZER_PIN, buzzer - to GND. It beeps with each blink.

const int LIGHT_PIN = 4;           // D4 on the ESP32 DEVKIT V1 (change if your LED / relay is elsewhere)
const bool ACTIVE_HIGH = true;     // most LEDs: true. Many relay boards switch on LOW: set false
const int BUZZER_PIN = 18;         // D18 on the ESP32 DEVKIT V1 (-1 = no buzzer)
const bool BUZZER_PASSIVE = false; // false = active buzzer (beeps on its own); true = passive (needs a tone)
const int BUZZER_TONE_HZ = 2700;   // pitch for a passive buzzer
const unsigned long BLINK_MS = 300;     // on/off time of each blink
const unsigned long TIMEOUT_MS = 3000;  // no message for this long -> light off

bool blinking = false;
bool lightOn = false;
unsigned long lastMessage = 0;
unsigned long lastToggle = 0;
String line;

void setBuzzer(bool on) {
  if (BUZZER_PIN < 0) return;
  if (BUZZER_PASSIVE) {
    if (on) tone(BUZZER_PIN, BUZZER_TONE_HZ); else noTone(BUZZER_PIN);
  } else {
    digitalWrite(BUZZER_PIN, on ? HIGH : LOW);
  }
}

void setLight(bool on) {
  lightOn = on;
  digitalWrite(LIGHT_PIN, (on == ACTIVE_HIGH) ? HIGH : LOW);
  setBuzzer(on);                   // beep together with the light
}

void setup() {
  pinMode(LIGHT_PIN, OUTPUT);
  if (BUZZER_PIN >= 0) pinMode(BUZZER_PIN, OUTPUT);
  setLight(false);                 // default: light off
  Serial.begin(115200);
  Serial.println("COW LIGHT READY");
}

void loop() {
  while (Serial.available()) {
    char c = Serial.read();
    if (c == '\n' || c == '\r') {
      line.trim();
      if (line == "ON")  { blinking = true;  lastMessage = millis(); }
      if (line == "OFF") { blinking = false; lastMessage = millis(); }
      line = "";
    } else if (line.length() < 16) {
      line += c;
    }
  }

  if (blinking && millis() - lastMessage > TIMEOUT_MS) {
    blinking = false;              // app went quiet - fail safe
  }

  if (blinking) {
    if (millis() - lastToggle >= BLINK_MS) {
      lastToggle = millis();
      setLight(!lightOn);
    }
  } else if (lightOn) {
    setLight(false);
  }
}
