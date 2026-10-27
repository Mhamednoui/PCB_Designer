/*
  ============================================================
  ESP32 — ReflexMachine Controller
  ============================================================
  - WiFi Access Point: ReflexMachineWifi / 12345678999
  - Web server on 192.168.4.1
  - Serial2 <-> Arduino Mega (pins 16 RX2, 17 TX2)
  - Receives DIAG|, COIN:, ERR:, ACK: from Mega
  - Sends D, SET:KEY:VAL commands to Mega
  - Web UI served from PROGMEM (no SD card needed)
  - Watchdog via esp_task_wdt
  ============================================================
*/

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <esp_task_wdt.h>
#include <Preferences.h>

// ── WiFi AP credentials ───────────────────────────────────
#define AP_SSID     "ReflexMachineWifi"
#define AP_PASSWORD "12345678999"
#define AP_IP       IPAddress(192, 168, 4, 1)

// ── Serial to Mega ────────────────────────────────────────
// ESP32 Serial2: GPIO16 = RX2 (-> Mega TX1 pin18)
//                GPIO17 = TX2 (-> Mega RX1 pin19)
#define MEGA_BAUD   115200
#define RX2_PIN     16
#define TX2_PIN     17

// ── Web server ────────────────────────────────────────────
WebServer server(80);
Preferences prefs;

// ── Mega RX buffer ───────────────────────────────────────
static String megaLine   = "";
static bool   collecting = false;   // true while inside DIAG|START...DIAG|END
static bool   configResendPending = false;
static bool   initialConfigSent    = false;   // first config push deferred out of setup()
static uint32_t bootConfigDueMs    = 0;       // millis() at which to send initial config

// ── Diagnostic storage ────────────────────────────────────
// Stores last complete diagnostic as key=value pairs
struct DiagField { String key; String value; };
static DiagField diagFields[24];
static uint8_t   diagCount   = 0;
static bool      diagReady   = false;   // true once first full diag received
static bool      diagPending = false;   // true while waiting for DIAG|END

// ── Event log (last 20 lines) ─────────────────────────────
static String eventLog[20];
static uint8_t eventHead  = 0;   // next write slot (wraps mod 20)
static uint8_t eventCount = 0;   // total stored, saturates at 20

void pushEvent(const String& line) {
  eventLog[eventHead % 20] = line;
  eventHead++;
  if (eventCount < 20) eventCount++;
}

// ── Forward declarations ──────────────────────────────────

// ── Persistent config ─────────────────────────────────────
// Saved to /config.txt on SPIFFS, loaded on boot and sent to Arduino
struct Config {
  uint16_t pwmOn   = 100;
  uint32_t spd1    = 1400;
  uint32_t spd2    = 1100;
  uint32_t spd3    = 500;
  uint8_t  payment = 1;
};

Config cfg;

void loadConfig();
void saveConfig();
void sendConfigToArduino();

void handleRoot();
void handleDiag();
void handleSet();
void handleEvents();
void handleConfig();
void handleNotFound();
void parseMegaLine(const String& line);
void requestDiagnostic();
void readMega();

// ═════════════════════════════════════════════════════════
//  HTML PAGE (stored in flash)
// ═════════════════════════════════════════════════════════
const char HTML_PAGE[] PROGMEM = R"HTMLEOF(
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ReflexMachine</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700;900&display=swap');

  :root {
    --bg:      #050a0e;
    --panel:   #0a1520;
    --border:  #0d3348;
    --accent:  #00e5ff;
    --accent2: #ff6b00;
    --green:   #00ff88;
    --red:     #ff2255;
    --text:    #c8e6f0;
    --dim:     #456070;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'Share Tech Mono', monospace;
    min-height: 100vh;
    padding: 16px;
    background-image:
      radial-gradient(ellipse at 20% 0%, #001a2e 0%, transparent 60%),
      radial-gradient(ellipse at 80% 100%, #001a2e 0%, transparent 60%);
  }

  header {
    text-align: center;
    padding: 24px 0 20px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 24px;
  }
  header h1 {
    font-family: 'Orbitron', sans-serif;
    font-size: clamp(1.4rem, 5vw, 2.2rem);
    font-weight: 900;
    color: var(--accent);
    letter-spacing: 0.12em;
    text-shadow: 0 0 20px rgba(0,229,255,0.4);
  }
  header p { color: var(--dim); font-size: 0.78rem; margin-top: 6px; letter-spacing: 0.08em; }

  .grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 16px;
    max-width: 900px;
    margin: 0 auto;
  }
  @media(max-width: 600px) { .grid { grid-template-columns: 1fr; } }

  .card {
    background: var(--panel);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 18px;
  }
  .card.full { grid-column: 1 / -1; }

  .card-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 0.7rem;
    font-weight: 700;
    color: var(--accent);
    letter-spacing: 0.15em;
    text-transform: uppercase;
    margin-bottom: 14px;
    padding-bottom: 8px;
    border-bottom: 1px solid var(--border);
  }

  /* Diagnostic grid */
  .diag-grid {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0 20px;
  }
  .diag-row {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid #0d2030;
    min-width: 0;
  }
  .diag-row.full-row {
    grid-column: 1 / -1;
  }
  .diag-key { color: var(--dim); font-size: 0.75rem; white-space: nowrap; }
  .diag-val { color: var(--green); font-size: 0.82rem; font-weight: bold; text-align: right; margin-left: 8px; }

  /* State badge */
  .state-badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 4px;
    font-size: 0.78rem;
    font-weight: bold;
    letter-spacing: 0.1em;
  }
  .s0,.s6  { background:#112; color:var(--dim); }
  .s1      { background:#001a10; color:var(--green); }
  .s2,.s3,.s4 { background:#1a0e00; color:var(--accent2); }
  .s5      { background:#001020; color:var(--accent); }

  /* Controls */
  .control-row {
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 12px;
  }
  .control-row label { color: var(--dim); font-size: 0.78rem; min-width: 110px; }
  .control-row input {
    background: #040c14;
    border: 1px solid var(--border);
    color: var(--accent);
    font-family: 'Share Tech Mono', monospace;
    font-size: 0.85rem;
    padding: 6px 10px;
    border-radius: 4px;
    width: 100px;
    outline: none;
    transition: border-color 0.2s;
  }
  .control-row input:focus { border-color: var(--accent); }
  .control-row .unit { color: var(--dim); font-size: 0.72rem; }

  /* Buttons */
  .btn {
    font-family: 'Orbitron', sans-serif;
    font-size: 0.7rem;
    font-weight: 700;
    letter-spacing: 0.12em;
    padding: 8px 18px;
    border: none;
    border-radius: 4px;
    cursor: pointer;
    transition: all 0.15s;
  }
  .btn-primary { background: var(--accent); color: #000; }
  .btn-primary:hover { background: #33eeff; box-shadow: 0 0 12px rgba(0,229,255,0.5); }
  .btn-danger  { background: var(--red); color: #fff; }
  .btn-danger:hover  { background: #ff4466; }
  .btn-send    { background: var(--accent2); color: #000; font-size: 0.65rem; padding: 6px 12px; }
  .btn-send:hover    { background: #ff8833; }
  .btn-sm      { padding: 5px 12px; font-size: 0.62rem; }

  /* Toggle switch */
  .toggle-wrap { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
  .toggle-label { color: var(--dim); font-size: 0.78rem; min-width: 110px; }
  .toggle {
    position: relative; width: 48px; height: 24px; cursor: pointer;
  }
  .toggle input { opacity: 0; width: 0; height: 0; }
  .slider {
    position: absolute; inset: 0;
    background: #1a0010; border: 1px solid var(--red);
    border-radius: 12px; transition: 0.3s;
  }
  .slider::before {
    content: ''; position: absolute;
    width: 18px; height: 18px; left: 2px; top: 2px;
    background: var(--red); border-radius: 50%; transition: 0.3s;
  }
  input:checked + .slider { background: #001a08; border-color: var(--green); }
  input:checked + .slider::before { transform: translateX(24px); background: var(--green); }
  .toggle-state { font-size: 0.78rem; color: var(--dim); }

  /* Event log */
  .log-box {
    background: #030810;
    border: 1px solid var(--border);
    border-radius: 4px;
    padding: 10px 12px;
    height: 140px;
    overflow-y: auto;
    font-size: 0.72rem;
    line-height: 1.7;
  }
  .log-box .ev-coin    { color: var(--green); }
  .log-box .ev-ack     { color: var(--accent); }
  .log-box .ev-err     { color: var(--red); }
  .log-box .ev-diag    { color: var(--dim); }
  .log-box .ev-default { color: var(--text); }

  /* Status bar */
  .status-bar {
    max-width: 900px; margin: 16px auto 0;
    display: flex; justify-content: space-between; align-items: center;
    font-size: 0.7rem; color: var(--dim);
    padding: 8px 0;
    border-top: 1px solid var(--border);
  }
  #conn-dot {
    display: inline-block; width: 8px; height: 8px;
    border-radius: 50%; background: var(--green);
    margin-right: 6px;
    box-shadow: 0 0 6px var(--green);
    animation: pulse 2s infinite;
  }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.3} }

  .spinner {
    display: none; width: 14px; height: 14px;
    border: 2px solid var(--border); border-top-color: var(--accent);
    border-radius: 50%; animation: spin 0.7s linear infinite;
    margin-left: 8px; vertical-align: middle;
  }
  @keyframes spin { to{transform:rotate(360deg)} }
  .loading .spinner { display: inline-block; }

  .no-diag {
    text-align: center; padding: 30px;
    color: var(--dim); font-size: 0.8rem; letter-spacing: 0.08em;
  }
</style>
</head>
<body>

<header>
  <h1>&#9889; REFLEX MACHINE</h1>
  <p>ARDUINO MEGA CONTROL PANEL &nbsp;&#8212;&nbsp; 192.168.4.1</p>
</header>

<div class="grid" id="main-grid">

  <!-- Diagnostic card -->
  <div class="card full" id="diag-card">
    <div class="card-title">
      SYSTEM DIAGNOSTIC
      <button class="btn btn-primary btn-sm" id="refresh-btn" onclick="requestDiag()" style="float:right;margin-top:-2px">
        &#8635; REFRESH <span class="spinner" id="spin"></span>
      </button>
    </div>
    <div id="diag-content" class="no-diag">Requesting diagnostic from Arduino...</div>
  </div>

  <!-- Speed settings -->
  <div class="card">
    <div class="card-title">SPEED INTERVALS</div>

    <div class="control-row">
      <label>Speed 1 (slow)</label>
      <input type="number" id="spd1" min="50" max="60000" value="1400">
      <span class="unit">ms</span>
      <button class="btn btn-send" onclick="sendSet('SPD1','spd1')">SEND</button>
    </div>
    <div class="control-row">
      <label>Speed 2 (med)</label>
      <input type="number" id="spd2" min="50" max="60000" value="1100">
      <span class="unit">ms</span>
      <button class="btn btn-send" onclick="sendSet('SPD2','spd2')">SEND</button>
    </div>
    <div class="control-row">
      <label>Speed 3 (fast)</label>
      <input type="number" id="spd3" min="50" max="60000" value="500">
      <span class="unit">ms</span>
      <button class="btn btn-send" onclick="sendSet('SPD3','spd3')">SEND</button>
    </div>
  </div>

  <!-- PWM & Payment -->
  <div class="card">
    <div class="card-title">PWM &amp; PAYMENT</div>

    <div class="control-row">
      <label>PWM ON value</label>
      <input type="number" id="pwmon" min="0" max="255" value="100">
      <span class="unit">0-255</span>
      <button class="btn btn-send" onclick="sendSet('PWM_ON','pwmon')">SEND</button>
    </div>

    <div class="toggle-wrap" style="margin-top:16px">
      <span class="toggle-label">Payment Mode</span>
      <label class="toggle">
        <input type="checkbox" id="payment-toggle" checked onchange="sendPayment(this)">
        <span class="slider"></span>
      </label>
      <span class="toggle-state" id="payment-state">ON</span>
    </div>
    <div style="font-size:0.68rem;color:var(--dim);margin-top:4px">
      ON = coins required &nbsp;|&nbsp; OFF = free play
    </div>
  </div>

  <!-- Event log -->
  <div class="card full">
    <div class="card-title">EVENT LOG</div>
    <div class="log-box" id="log-box">
      <span class="ev-diag">Waiting for events...</span>
    </div>
  </div>

</div>

<div class="status-bar">
  <div><span id="conn-dot"></span> ACCESS POINT CONNECTED</div>
  <div id="last-update">No update yet</div>
</div>

<script>
const STATE_LABELS = {
  0:'IDLE', 1:'RESET', 2:'SPEED_1', 3:'SPEED_2',
  4:'SPEED_3', 5:'RELEASING', 6:'DONE'
};
const STATE_CLASS = {0:'s0',1:'s1',2:'s2',3:'s3',4:'s4',5:'s5',6:'s6'};

let lastDiagData = null;

// ── Request diagnostic from Arduino ──────────────────────
// /diag blocks on server side until Mega responds (up to 3s)
// so we just fire once and render what we get
function requestDiag() {
  const btn = document.getElementById('refresh-btn');
  btn.classList.add('loading');
  btn.disabled = true;
  document.getElementById('diag-content').innerHTML = '<div class="no-diag">Requesting from Arduino Mega...</div>';

  fetch('/diag')
    .then(r => r.json())
    .then(data => {
      btn.classList.remove('loading');
      btn.disabled = false;
      if (data.ready) {
        renderDiag(data.fields);
        document.getElementById('last-update').textContent = 'Updated: ' + new Date().toLocaleTimeString();
      } else {
        document.getElementById('diag-content').innerHTML =
          '<div class="no-diag" style="color:var(--red)">No response from Arduino — check wiring</div>';
      }
    })
    .catch(() => {
      btn.classList.remove('loading');
      btn.disabled = false;
      document.getElementById('diag-content').innerHTML =
        '<div class="no-diag" style="color:var(--red)">Connection error</div>';
    });
}

// ── Render diagnostic fields ──────────────────────────────
function renderDiag(fields) {
  const map = {};
  fields.forEach(f => map[f.key] = f.value);

  const state     = parseInt(map['state'] || '0');
  const stateLabel = STATE_LABELS[state] || 'UNKNOWN';
  const stateClass = STATE_CLASS[state]  || 's0';

  // Update speed/pwm inputs from live values
  if (map['spd1']) document.getElementById('spd1').value = map['spd1'];
  if (map['spd2']) document.getElementById('spd2').value = map['spd2'];
  if (map['spd3']) document.getElementById('spd3').value = map['spd3'];
  if (map['pwmOn']) document.getElementById('pwmon').value = map['pwmOn'];
  if (map['payment'] !== undefined) {
    const p = parseInt(map['payment']);
    document.getElementById('payment-toggle').checked = p === 1;
    document.getElementById('payment-state').textContent = p === 1 ? 'ON' : 'OFF';
  }



  const rows = [
    ['State',      `<span class="state-badge ${stateClass}">${stateLabel}</span>`, false],
    ['Last State', STATE_LABELS[parseInt(map['lastState']||'0')] || '—',           false],
    ['Uptime',     map['uptime']   || '—',                                          false],
    ['Free RAM',   (map['ram']     || '—') + ' B',                                  false],
    ['Coin Sum',   map['coinSum']  || '0',                                          false],
    ['Last Pulse', map['lastPulse']|| '—',                                          false],
    ['Release',    (map['releaseIdx']||'0') + ' / 10',                             false],
    ['Interval',   (map['releaseIntvl']||'—') + ' ms',                             false],
    ['Seeded',     map['seeded']==='1' ? '✓ YES' : '✗ NO',                         false],
    ['Spd1 (slow)', (map['spd1'] || '—') + ' ms',                                    false],
    ['Spd2 (med)',  (map['spd2'] || '—') + ' ms',                                    false],
    ['Spd3 (fast)', (map['spd3'] || '—') + ' ms',                                    false],
    ['Payment',    map['payment']==='1' ? 'REQUIRED' : 'FREE PLAY',                false],
    ['PWM Value',  (map['pwmOn'] || '—') + ' / 255',                               false],
    ['Coin Pin',   map['coinPin']==='1' ? '⚡ ACTIVE' : 'idle',                    false],
  ];

  if (map['resetTmo']) rows.push(['Reset TMO', map['resetTmo'] + ' remaining', true]);

  const html = `<div class="diag-grid">${
    rows.map(([k,v,full]) =>
      `<div class="diag-row${full?' full-row':''}">` +
      `<span class="diag-key">${k}</span>` +
      `<span class="diag-val">${v}</span></div>`
    ).join('')
  }</div>`;

  document.getElementById('diag-content').innerHTML = html;
}

// ── Send SET command ──────────────────────────────────────
function sendSet(key, inputId) {
  const val = document.getElementById(inputId).value;
  fetch('/set?key=' + key + '&val=' + encodeURIComponent(val))
    .then(r => r.json())
    .then(d => addLog(d.sent ? 'ACK' : 'ERR', 'SET:' + key + ':' + val + ' -> ' + (d.result||'?')))
    .catch(() => addLog('ERR', 'Send failed'));
}

function sendPayment(el) {
  const val = el.checked ? 1 : 0;
  document.getElementById('payment-state').textContent = val ? 'ON' : 'OFF';
  fetch('/set?key=PAYMENT&val=' + val)
    .then(r => r.json())
    .then(d => addLog(d.sent ? 'ACK' : 'ERR', 'SET:PAYMENT:' + val + ' -> ' + (d.result||'?')))
    .catch(() => addLog('ERR', 'Send failed'));
}

// ── Event log ─────────────────────────────────────────────
function addLog(type, msg) {
  const box = document.getElementById('log-box');
  const cls = type === 'ACK' ? 'ev-ack' : type === 'ERR' ? 'ev-err' :
              type === 'COIN' ? 'ev-coin' : 'ev-default';
  const ts  = new Date().toLocaleTimeString();
  const line = document.createElement('div');
  line.className = cls;
  line.textContent = '[' + ts + '] ' + msg;
  box.appendChild(line);
  box.scrollTop = box.scrollHeight;
  // keep max 50 lines
  while (box.children.length > 50) box.removeChild(box.firstChild);
}

// ── Poll event log from server ────────────────────────────
function pollEvents() {
  fetch('/events')
    .then(r => r.json())
    .then(data => {
      data.events.forEach(e => {
        if (e.startsWith('COIN:'))      addLog('COIN', e);
        else if (e.startsWith('ACK:'))  addLog('ACK',  e);
        else if (e.startsWith('ERR:'))  addLog('ERR',  e);
        else                            addLog('INFO', e);
      });
    })
    .catch(() => {});
}

// ── Fetch saved config from ESP32 to pre-fill inputs ─────
function loadSavedConfig() {
  fetch('/config')
    .then(r => r.json())
    .then(data => {
      if (data.pwmOn   !== undefined) document.getElementById('pwmon').value = data.pwmOn;
      if (data.spd1    !== undefined) document.getElementById('spd1').value  = data.spd1;
      if (data.spd2    !== undefined) document.getElementById('spd2').value  = data.spd2;
      if (data.spd3    !== undefined) document.getElementById('spd3').value  = data.spd3;
      if (data.payment !== undefined) {
        document.getElementById('payment-toggle').checked = data.payment === 1;
        document.getElementById('payment-state').textContent = data.payment === 1 ? 'ON' : 'OFF';
      }
    })
    .catch(() => {});
}

// ── Boot ──────────────────────────────────────────────────
window.onload = function() {
  loadSavedConfig();   // fill inputs from ESP32 NVS immediately
  requestDiag();       // request live data from Arduino
  setInterval(pollEvents, 3000);
};
</script>
</body>
</html>
)HTMLEOF";

// ═════════════════════════════════════════════════════════
//  CONFIG — SPIFFS load/save/send
//  File format: one KEY=VALUE per line
//    PWM_ON=100
//    SPD1=1400
//    SPD2=1100
//    SPD3=500
//    PAYMENT=1
// ═════════════════════════════════════════════════════════
void loadConfig() {
  // Always open read-write so namespace is created if it doesn't exist
  if (!prefs.begin("reflexcfg", false)) {
    Serial.println("NVS open failed — using defaults");
    return;
  }
  // "saved" key = 1 means we have real saved data, 0 = first boot
  bool hasSaved = prefs.getBool("saved", false);
  if (hasSaved) {
    cfg.pwmOn   = prefs.getUShort("pwmOn",   100);
    cfg.spd1    = prefs.getULong ("spd1",   1400);
    cfg.spd2    = prefs.getULong ("spd2",   1100);
    cfg.spd3    = prefs.getULong ("spd3",    500);
    cfg.payment = prefs.getUChar ("payment",   1);
    Serial.println("NVS config loaded: PWM=" + String(cfg.pwmOn) +
      " SPD1=" + String(cfg.spd1) +
      " SPD2=" + String(cfg.spd2) +
      " SPD3=" + String(cfg.spd3) +
      " PAY="  + String(cfg.payment));
  } else {
    Serial.println("NVS first boot — using hardcoded defaults");
  }
  prefs.end();
}

void saveConfig() {
  if (!prefs.begin("reflexcfg", false)) {
    Serial.println("NVS open failed — cannot save");
    return;
  }
  prefs.putBool  ("saved",   true);       // mark as having real saved data
  prefs.putUShort("pwmOn",   cfg.pwmOn);
  prefs.putULong ("spd1",    cfg.spd1);
  prefs.putULong ("spd2",    cfg.spd2);
  prefs.putULong ("spd3",    cfg.spd3);
  prefs.putUChar ("payment", cfg.payment);
  prefs.end();
  Serial.println("NVS saved: PWM=" + String(cfg.pwmOn) +
    " SPD1=" + String(cfg.spd1) +
    " SPD2=" + String(cfg.spd2) +
    " SPD3=" + String(cfg.spd3) +
    " PAY="  + String(cfg.payment));
}

void sendConfigToArduino() {
  // Send full config to Arduino — called on boot AND after every change
  Serial2.println("SET:PWM_ON:"  + String(cfg.pwmOn));  Serial2.flush(); delay(100);
  Serial2.println("SET:SPD1:"    + String(cfg.spd1));   Serial2.flush(); delay(100);
  Serial2.println("SET:SPD2:"    + String(cfg.spd2));   Serial2.flush(); delay(100);
  Serial2.println("SET:SPD3:"    + String(cfg.spd3));   Serial2.flush(); delay(100);
  Serial2.println("SET:PAYMENT:" + String(cfg.payment));Serial2.flush(); delay(100);
  Serial.println("Config sent to Arduino");
  pushEvent("CFG:PWM=" + String(cfg.pwmOn) +
    " S1=" + String(cfg.spd1) +
    " S2=" + String(cfg.spd2) +
    " S3=" + String(cfg.spd3) +
    " PAY=" + String(cfg.payment));
}

// ═════════════════════════════════════════════════════════
//  SETUP
// ═════════════════════════════════════════════════════════
void setup() {
  Serial.begin(115200);   // USB debug only

  // Watchdog — reset if stuck > 10s
  esp_task_wdt_init(10, true);
  esp_task_wdt_add(NULL);

  // Serial2 to Mega
  Serial2.begin(MEGA_BAUD, SERIAL_8N1, RX2_PIN, TX2_PIN);

  // Load config from NVS (Preferences) — always available, no partition needed
  loadConfig();

  // WiFi Access Point
  WiFi.softAP(AP_SSID, AP_PASSWORD);
  WiFi.setTxPower(WIFI_POWER_19_5dBm);
  WiFi.softAPConfig(AP_IP, AP_IP, IPAddress(255, 255, 255, 0));
  Serial.println("AP started: " + WiFi.softAPIP().toString());

  // Routes
  server.on("/",       HTTP_GET,  handleRoot);
  server.on("/diag",   HTTP_GET,  handleDiag);
  server.on("/set",    HTTP_GET,  handleSet);
  server.on("/events", HTTP_GET,  handleEvents);
  server.on("/config", HTTP_GET,  handleConfig);
  server.onNotFound(handleNotFound);
  server.begin();

  Serial.println("HTTP server started");

  // Defer first config push 3s (let Mega finish booting) without blocking
  // setup() — handled non-blockingly in loop() so the WDT and web server
  // stay responsive.
  bootConfigDueMs = millis() + 3000UL;
}

// ═════════════════════════════════════════════════════════
//  LOOP
// ═════════════════════════════════════════════════════════
void loop() {
  esp_task_wdt_reset();
  server.handleClient();
  readMega();

  // Deferred initial config push (replaces blocking delay(3000) in setup)
  if (!initialConfigSent && (int32_t)(millis() - bootConfigDueMs) >= 0) {
    initialConfigSent = true;
    sendConfigToArduino();
  }

  if (configResendPending) {
    configResendPending = false;
    sendConfigToArduino();
  }
}

// ═════════════════════════════════════════════════════════
//  READ FROM MEGA — non-blocking, called every loop
// ═════════════════════════════════════════════════════════
void readMega() {
  while (Serial2.available()) {
    char c = Serial2.read();
    if (c == '\n') {
      // Remove \r if Arduino sent \r\n (Serial.println behaviour)
      megaLine.trim();
      megaLine.replace("\r", "");
      if (megaLine.length() > 0) {
        parseMegaLine(megaLine);
      }
      megaLine = "";
    } else {
      megaLine += c;
      if (megaLine.length() > 200) megaLine = "";  // overflow guard
    }
  }
}

// ═════════════════════════════════════════════════════════
//  PARSE LINE FROM MEGA
// ═════════════════════════════════════════════════════════
void parseMegaLine(const String& line) {

  // ── DIAG block ────────────────────────────────────────
  if (line == "DIAG|START") {
    diagCount   = 0;
    diagPending = true;
    return;
  }

  if (line == "DIAG|END") {
    diagPending = false;
    diagReady   = true;

    // ── Config guard ──────────────────────────────────────
    // Compare what Arduino is running against NVS saved config.
    // If anything differs, resend the full config immediately.
    bool mismatch = false;
    for (uint8_t i = 0; i < diagCount; i++) {
      String k = diagFields[i].key;
      long   v = diagFields[i].value.toInt();
      if (k == "pwmOn"   && v != (long)cfg.pwmOn)   { mismatch = true; break; }
      if (k == "spd1"    && v != (long)cfg.spd1)    { mismatch = true; break; }
      if (k == "spd2"    && v != (long)cfg.spd2)    { mismatch = true; break; }
      if (k == "spd3"    && v != (long)cfg.spd3)    { mismatch = true; break; }
      if (k == "payment" && v != (long)cfg.payment) { mismatch = true; break; }
    }
    if (mismatch) {
      pushEvent("MISMATCH: resending config to Arduino");
      configResendPending = true;
    }
    return;
  }

  if (diagPending && line.startsWith("DIAG|")) {
    // Parse DIAG|key:value
    String body       = line.substring(5);   // strip "DIAG|"
    int    colonPos   = body.indexOf(':');
    if (colonPos > 0 && diagCount < 24) {
      diagFields[diagCount].key   = body.substring(0, colonPos);
      diagFields[diagCount].value = body.substring(colonPos + 1);
      diagCount++;
    }
    return;
  }

  // ── Other messages — push to event log ────────────────
  if (line.startsWith("COIN:") || line.startsWith("ACK:") ||
      line.startsWith("ERR:")  || line.startsWith("DIAG|")) {
    pushEvent(line);
  }
}

// ═════════════════════════════════════════════════════════
//  REQUEST DIAGNOSTIC FROM MEGA
// ═════════════════════════════════════════════════════════
void requestDiagnostic() {
  diagReady   = false;
  diagPending = false;
  diagCount   = 0;
  Serial2.println("D");
}

// ═════════════════════════════════════════════════════════
//  HTTP HANDLERS
// ═════════════════════════════════════════════════════════
void handleRoot() {
  // Just serve the page — JS will call /diag on load
  server.send_P(200, "text/html", HTML_PAGE);
}

void handleDiag() {
  // Send "D" to Arduino, then wait up to 3s for full response
  requestDiagnostic();

  uint32_t deadline = millis() + 3000UL;
  while (!diagReady && millis() < deadline) {
    esp_task_wdt_reset();
    readMega();
    delay(1);
  }

  String json = "{\"ready\":";
  json += diagReady ? "true" : "false";
  json += ",\"fields\":[";

  for (uint8_t i = 0; i < diagCount; i++) {
    if (i > 0) json += ",";
    json += "{\"key\":\"" + diagFields[i].key + "\",\"value\":\"" + diagFields[i].value + "\"}";
  }

  json += "]}";
  server.send(200, "application/json", json);
}

void handleSet() {
  if (!server.hasArg("key") || !server.hasArg("val")) {
    server.send(400, "application/json", "{\"sent\":false,\"result\":\"missing args\"}");
    return;
  }

  String key = server.arg("key");
  String val = server.arg("val");

  // Validate key
  if (key != "PWM_ON" && key != "SPD1" && key != "SPD2" &&
      key != "SPD3"   && key != "PAYMENT") {
    server.send(400, "application/json", "{\"sent\":false,\"result\":\"unknown key\"}");
    return;
  }

  // 1. Update in-memory config
  if      (key == "PWM_ON")  cfg.pwmOn   = (uint16_t)val.toInt();
  else if (key == "SPD1")    cfg.spd1    = (uint32_t)val.toInt();
  else if (key == "SPD2")    cfg.spd2    = (uint32_t)val.toInt();
  else if (key == "SPD3")    cfg.spd3    = (uint32_t)val.toInt();
  else if (key == "PAYMENT") cfg.payment = (uint8_t)val.toInt();

  // 2. Save to NVS immediately
  saveConfig();

  // 3. Send full config to Arduino
  sendConfigToArduino();

  server.send(200, "application/json", "{\"sent\":true,\"result\":\"saved\"}");
}

void handleConfig() {
  // Returns current saved config as JSON — used by JS on page load to fill inputs
  String json = "{";
  json += "\"pwmOn\":" + String(cfg.pwmOn) + ",";
  json += "\"spd1\":" + String(cfg.spd1) + ",";
  json += "\"spd2\":" + String(cfg.spd2) + ",";
  json += "\"spd3\":" + String(cfg.spd3) + ",";
  json += "\"payment\":" + String(cfg.payment);
  json += "}";
  server.send(200, "application/json", json);
}

void handleEvents() {
  // Return recent events as JSON array
  String json = "{\"events\":[";
  bool first = true;

  // Return last 10 events newest first
  uint8_t count = min((int)eventCount, 10);
  for (int i = count - 1; i >= 0; i--) {
    int idx = ((int)eventHead - 1 - i + 20) % 20;
    if (eventLog[idx].length() == 0) continue;
    if (!first) json += ",";
    // Escape quotes
    String escaped = eventLog[idx];
    escaped.replace("\"", "'");
    json += "\"" + escaped + "\"";
    first = false;
  }

  json += "]}";
  server.send(200, "application/json", json);
}

void handleNotFound() {
  server.send(404, "text/plain", "Not found");
}