import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";

const viewport = document.getElementById("viewport");
const projectPicker = document.getElementById("project-picker");
const inputsList = document.getElementById("inputs-list");
const outputsList = document.getElementById("outputs-list");
const consoleEl = document.getElementById("console");
const consoleLog = document.getElementById("console-log");
const consoleActions = document.getElementById("console-actions");
const consoleToggle = document.getElementById("console-toggle");
const consoleClose = document.getElementById("console-close");
const simToggle = document.getElementById("sim-toggle");
const simLimitInput = document.getElementById("sim-limit");
const simStatusEl = document.getElementById("sim-status");
const activityLogEl = document.getElementById("activity-log");
const serialPanel = document.getElementById("console-serial");
const capturePanel = document.getElementById("console-capture");
let serialPollTimer = null;
const recorder = { on: false, steps: [], last: 0 };

let currentProjectId = null;
let currentModel = null;
let simRunning = false;
let simLimitS = null;
let simStartedAt = null;
let outputsPollTimer = null;
let statusPollTimer = null;
const outputIndicatorEls = {}; // net -> element, only populated for live_sim projects
const netLabels = {}; // net -> human label, from the manifest's io[] - generic across any project
const netRefs = {}; // net -> component ref, so an output can light up its real part in the 3D view
const lastOutputValues = {}; // net -> last polled value, to only log actual changes
const inputPressButtons = []; // buttons to enable/disable with sim state
// Which simulator backs this project: "wokwi" (real firmware, live, spends quota), "spice" (a
// recorded LTspice transient played back in real time - for boards with no MCU), or null.
let simMode = null;
const spiceSupplies = {}; // net -> volts chosen on the dashboard, applied on the next SPICE run
let spiceResult = null;
let playbackRaf = null;
let currentIo = []; // the manifest's io[] for the loaded project

// ---------------------------------------------------------------- 3D scene
const scene = new THREE.Scene();
// Background comes from the CSS vignette on #viewport (renderer is alpha:true), not a flat scene colour.

const camera = new THREE.PerspectiveCamera(45, 1, 1, 5000);
camera.position.set(150, 150, 150);

const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
viewport.appendChild(renderer.domElement);

const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;

// OrbitControls' own wheel zoom is DISABLED on purpose. In three.js r160+ it scales the camera distance
// by `0.95 ^ (zoomSpeed * |deltaY| * 0.01)` - i.e. proportionally to how large a deltaY the mouse driver
// reports. Plenty of mice/drivers (free-spin or "smooth scrolling" wheels especially) report deltaY in
// the thousands per notch instead of ~100, which turns a single notch into a 10x+ jump: the camera lands
// on minDistance or maxDistance immediately and there is nothing in between. No amount of `zoomSpeed`
// tuning fixes that, because the magnitude is hardware/driver dependent.
// Instead we use only the wheel's DIRECTION and apply a fixed step per event, so zooming is identical on
// every machine and always has many intermediate levels (~78 steps across the full min..max range).
controls.enableZoom = false;

const ZOOM_STEP = 1.08; // 8% per wheel notch

function zoomByNotches(direction) {
  const offset = camera.position.clone().sub(controls.target);
  const factor = direction > 0 ? ZOOM_STEP : 1 / ZOOM_STEP;
  const distance = THREE.MathUtils.clamp(
    offset.length() * factor,
    controls.minDistance,
    controls.maxDistance,
  );
  camera.position.copy(controls.target).add(offset.setLength(distance));
  controls.update();
  updateZoomReadout();
}

renderer.domElement.addEventListener(
  "wheel",
  (event) => {
    event.preventDefault(); // stop the page scrolling instead of zooming
    const direction = Math.sign(event.deltaY); // sign only - magnitude is deliberately ignored
    if (direction) zoomByNotches(direction);
  },
  { passive: false },
);

// Same zoom path as the wheel, for anyone who'd rather click (and as a guaranteed fallback if a given
// machine's wheel events ever misbehave again).
document.getElementById("zoom-in").addEventListener("click", () => zoomByNotches(-1));
document.getElementById("zoom-out").addEventListener("click", () => zoomByNotches(1));

// Lighting: a soft fill from above plus a key and a rim light, so the board reads as a solid object
// instead of a flat silhouette. Tone mapping keeps the bright silkscreen from blowing out while still
// letting an emissive (lit) LED visibly glow.
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.15;
renderer.outputColorSpace = THREE.SRGBColorSpace;

scene.add(new THREE.HemisphereLight(0xdfe7ff, 0x20222a, 1.35));
const keyLight = new THREE.DirectionalLight(0xffffff, 1.6);
keyLight.position.set(1, 2.2, 1.4);
scene.add(keyLight);
const fillLight = new THREE.DirectionalLight(0xbcd2ff, 0.5);
fillLight.position.set(-1.4, 0.8, -1);
scene.add(fillLight);
const rimLight = new THREE.DirectionalLight(0xffffff, 0.7);
rimLight.position.set(0, -1.5, -1.2);
scene.add(rimLight);

function resizeRenderer() {
  const { clientWidth: w, clientHeight: h } = viewport;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.updateProjectionMatrix();
}
new ResizeObserver(resizeRenderer).observe(viewport);
resizeRenderer();

// Shows the live camera distance and the allowed range. This exists because "the zoom is broken" is
// otherwise unfalsifiable from the outside: if this number changes as you scroll, the wheel is reaching
// OrbitControls and any remaining problem is the range/clipping; if it does NOT change, the wheel event
// is being swallowed before it gets here (page scroll, an overlaying element, etc).
const zoomReadout = document.getElementById("zoom-readout");
let lastReadout = "";

function updateZoomReadout() {
  if (!zoomReadout) return;
  const d = camera.position.distanceTo(controls.target);
  const text = `zoom ${d.toFixed(3)} (${controls.minDistance.toFixed(3)} - ${controls.maxDistance.toFixed(3)})`;
  if (text !== lastReadout) {
    zoomReadout.textContent = text;
    lastReadout = text;
  }
}

(function animate() {
  requestAnimationFrame(animate);
  controls.update();
  updateZoomReadout();
  renderer.render(scene, camera);
})();

function frameModel(object3d) {
  const box = new THREE.Box3().setFromObject(object3d);
  const size = box.getSize(new THREE.Vector3());
  const center = box.getCenter(new THREE.Vector3());
  const radius = Math.max(size.x, size.y, size.z) * 0.75 || 100;

  object3d.position.sub(center); // center the model at the origin
  controls.target.set(0, 0, 0);
  camera.position.set(radius, radius, radius);
  // Zoom bounds come FIRST, then the clipping planes are derived from them. Doing it this way makes it
  // structurally impossible for the near plane to sit inside the reachable zoom range - which is the bug
  // that kept coming back (an absolute near floor like 0.1 is larger than this model's whole minDistance,
  // because KiCad's GLB export uses real-world METERS: this board is ~0.26m, so radius is under 1 unit).
  // Never write an absolute number here; everything is a multiple of the model's measured radius.
  const minDistance = radius * 0.05; // right up close to a single component
  const maxDistance = radius * 20;   // whole board, comfortably far away  (=> ~400x zoom range)
  controls.minDistance = minDistance;
  controls.maxDistance = maxDistance;
  controls.zoomSpeed = 1.0;

  camera.near = minDistance / 20; // always well inside minDistance => can never clip the model
  camera.far = maxDistance * 3;
  camera.updateProjectionMatrix();
  controls.update();

  viewport.dataset.radius = radius;
  updateZoomReadout();
}

// ---------------------------------------------------------------- click a part in the 3D view
// The dashboard can already point at the 3D board; this makes it work the other way round too, so the
// model is something you interrogate rather than just look at. Generic: the node name IS the reference
// designator, so this needs no per-project data.
const raycaster = new THREE.Raycaster();
const pointer = new THREE.Vector2();
let pointerDownAt = null;

function refForObject(object) {
  // Walk up to the top-level node under the model root - that's the one named after the component.
  let node = object;
  while (node && node.parent && node.parent !== currentModel) node = node.parent;
  return node && node.name && refIndex[node.name] ? node.name : null;
}

renderer.domElement.addEventListener("pointerdown", (e) => {
  pointerDownAt = { x: e.clientX, y: e.clientY };
});

renderer.domElement.addEventListener("pointerup", (event) => {
  // Ignore drags (orbiting the camera shouldn't select anything).
  if (!pointerDownAt) return;
  const moved = Math.hypot(event.clientX - pointerDownAt.x, event.clientY - pointerDownAt.y);
  pointerDownAt = null;
  if (moved > 4 || !currentModel) return;

  const rect = renderer.domElement.getBoundingClientRect();
  pointer.x = ((event.clientX - rect.left) / rect.width) * 2 - 1;
  pointer.y = -((event.clientY - rect.top) / rect.height) * 2 + 1;
  raycaster.setFromCamera(pointer, camera);

  for (const hit of raycaster.intersectObject(currentModel, true)) {
    const ref = refForObject(hit.object);
    if (ref) {
      selectRef(ref);
      return;
    }
  }
});

// Shared by clicking in 3D and clicking a dashboard row.
function selectRef(ref) {
  highlightRef(ref);
  const component = refIndex[ref];
  const detail = component
    ? `${ref}${component.value ? " · " + component.value : ""}${component.footprint ? " · " + component.footprint : ""}`
    : ref;
  logActivity(`Selected ${detail}`, "press");

  // Pull the matching dashboard row into view and flash it, so 3D and the panel stay in sync.
  const row = document.querySelector(`.io-item[data-ref="${ref}"]`);
  if (row) {
    row.scrollIntoView({ block: "nearest", behavior: "smooth" });
    row.classList.add("selected");
    setTimeout(() => row.classList.remove("selected"), 1200);
  }
}

// ---------------------------------------------------------------- component glow (3D output state)
// Makes the REAL part in the 3D view light up when its output goes high - an LED actually glows on the
// board, not just a dot in the side panel. Works for any project: the GLB names each component node
// after its reference designator, and io_map.json already says which ref belongs to which output net.
const GLOW_COLORS = {
  RED: 0xff3322, GREEN: 0x33ff55, BLUE: 0x3388ff, YELLOW: 0xffdd22,
  ORANGE: 0xff9922, WHITE: 0xffffff,
};
const DEFAULT_GLOW = 0xffcc33;

function glowColorFor(ref) {
  const value = (refIndex[ref] && refIndex[ref].value) || "";
  for (const name in GLOW_COLORS) {
    if (value.toUpperCase().includes(name)) return GLOW_COLORS[name];
  }
  return DEFAULT_GLOW;
}

function setComponentGlow(ref, on) {
  if (!currentModel || !ref) return;
  const obj = currentModel.getObjectByName(ref);
  if (!obj) return;
  const color = glowColorFor(ref);
  obj.traverse((child) => {
    if (!child.isMesh || !child.material) return;
    // Materials are SHARED between components in KiCad's GLB export (this board has 8 parts but only
    // 6 materials), so lighting one LED would light every part sharing its material. Clone once per
    // mesh the first time we touch it, and remember the original emissive to restore later.
    if (!child.userData.glowReady) {
      child.material = child.material.clone();
      child.userData.glowReady = true;
      child.userData.baseEmissive = child.material.emissive
        ? child.material.emissive.clone()
        : new THREE.Color(0x000000);
      child.userData.baseEmissiveIntensity = child.material.emissiveIntensity ?? 1;
    }
    if (!child.material.emissive) return;
    if (on) {
      child.material.emissive.setHex(color);
      child.material.emissiveIntensity = 3.0;
    } else {
      child.material.emissive.copy(child.userData.baseEmissive);
      child.material.emissiveIntensity = child.userData.baseEmissiveIntensity;
    }
    child.material.needsUpdate = true;
  });
}

// Highlight every component on a net. NOTE: the GLB deliberately excludes copper (tracks/zones were
// dropped because 30k primitives crashed WebGL - see ROADMAP), so we highlight the PARTS on the net
// rather than its traces. That still answers "what does this net touch?".
let netHighlightRefs = [];

function highlightNet(net) {
  for (const ref of netHighlightRefs) setComponentGlow(ref, false);
  netHighlightRefs = [];
  const members = (currentNets[net] || []).map((s) => s.split(".")[0]);
  const unique = [...new Set(members)];
  for (const ref of unique) setComponentGlow(ref, true);
  netHighlightRefs = unique;
  logActivity(`Net ${net}: ${unique.length} component${unique.length === 1 ? "" : "s"} - ${unique.join(", ")}`,
              "press");
}

function clearAllGlows() {
  for (const ref of netHighlightRefs) setComponentGlow(ref, false);
  netHighlightRefs = [];
  for (const net in netRefs) setComponentGlow(netRefs[net], false);
}

// ---------------------------------------------------------------- highlight
// GLB node names are the real reference designators (confirmed by inspecting the export - the KiCad
// glTF exporter names each top-level component node after its ref, e.g. "R33", "U3", "D18").
let highlightHelper = null;

function highlightRef(ref) {
  if (!currentModel) return;
  const obj = currentModel.getObjectByName(ref);
  if (!obj) {
    logToConsole({ label: "Locate " + ref, ok: false, output: `No 3D node named "${ref}" found in this model - it may not have its own component mesh (e.g. a footprint with no 3D model assigned).` });
    return;
  }
  if (highlightHelper) {
    scene.remove(highlightHelper);
    highlightHelper.geometry.dispose();
    highlightHelper.material.dispose();
  }
  highlightHelper = new THREE.BoxHelper(obj, 0xffcc00);
  scene.add(highlightHelper);

  const worldPos = new THREE.Vector3();
  obj.getWorldPosition(worldPos);
  controls.target.copy(worldPos);
  controls.update();
}

document.getElementById("camera-presets").addEventListener("click", (e) => {
  const view = e.target.dataset.view;
  if (!view) return;
  const r = Number(viewport.dataset.radius) || 100;
  const pos = { iso: [r, r, r], top: [0, r * 1.4, 0.01], bottom: [0, -r * 1.4, 0.01] }[view];
  camera.position.set(...pos);
  controls.target.set(0, 0, 0);
  controls.update();
});

function loadModel(url) {
  if (currentModel) {
    scene.remove(currentModel);
    currentModel = null;
  }
  if (highlightHelper) {
    scene.remove(highlightHelper);
    highlightHelper.geometry.dispose();
    highlightHelper.material.dispose();
    highlightHelper = null;
  }
  new GLTFLoader().load(
    url,
    (gltf) => {
      currentModel = gltf.scene;
      scene.add(currentModel);
      frameModel(currentModel);
    },
    undefined,
    (err) => logToConsole({ label: "Model load", ok: false, output: String(err) }),
  );
}

// ---------------------------------------------------------------- dashboard
// components are keyed by ref in the manifest's flat list - build a lookup once per project.
let refIndex = {};
let netToRefs = {};
let currentNets = {}; // full net -> [REF.PIN] table from the manifest

function findRefForNet(net) {
  const refs = netToRefs[net];
  return refs && refs.length ? refs[0].split(".")[0] : null;
}

// ---------------------------------------------------------------- input widgets (extensible)
// Each input's `type` in io_map.json chooses its control. To support a NEW kind of input, add one entry
// here - nothing else in the platform needs to change, because the backend's /sim/input already sets a
// Wokwi control to any numeric value, and io_map.json is per-project data.
//
//   button / coin  momentary  - pulses the control (press, 80ms, release)
//   toggle/switch  latching   - sets 0 or 1 and leaves it
//   analog/pot/... continuous - slider sending any number in [min,max] (defaults 0..1023, step 1)
//
// Optional io_map.json fields used here: min, max, step, default, unit.
const INPUT_WIDGETS = {
  momentary: buildMomentaryWidget,
  toggle: buildToggleWidget,
  analog: buildAnalogWidget,
  pulse: buildPulseWidget,
};

const INPUT_TYPE_ALIASES = {
  button: "momentary", coin: "momentary", push: "momentary", momentary: "momentary",
  toggle: "toggle", switch: "toggle", latching: "toggle",
  analog: "analog", pot: "analog", potentiometer: "analog", slider: "analog", sensor: "analog",
  pulse: "pulse", coin: "pulse", encoder: "pulse", flow: "pulse", tacho: "pulse", counter: "pulse",
};

function buildInputWidget(item) {
  const kind = INPUT_TYPE_ALIASES[(item.type || "").toLowerCase()] || "momentary";
  return INPUT_WIDGETS[kind](item);
}

// Let the type be changed from inside the platform, not only in io_map.json. You often only discover
// that something is a pulse-counting input (rather than a plain button) by watching it misbehave.
// The change is persisted back to io_map.json + manifest.json, so it survives a reload.
const SELECTABLE_TYPES = ["momentary", "toggle", "analog", "pulse"];

function buildTypePicker(item, row) {
  const select = document.createElement("select");
  select.className = "io-type";
  select.title = "How this input behaves. Changing it is saved to the project.";
  const current = INPUT_TYPE_ALIASES[(item.type || "").toLowerCase()] || "momentary";
  for (const t of SELECTABLE_TYPES) {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    if (t === current) opt.selected = true;
    select.appendChild(opt);
  }
  select.addEventListener("click", (e) => e.stopPropagation());
  select.addEventListener("change", async (e) => {
    e.stopPropagation();
    item.type = select.value;
    await fetch(`/api/projects/${currentProjectId}/io`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ net: item.net, type: select.value }),
    });
    logActivity(`${item.label} is now a "${select.value}" input (saved)`, "press");
    // swap the widget in place for the new type
    const old = row.querySelector(".io-widget");
    const fresh = buildInputWidget(item);
    fresh.classList.add("io-widget");
    if (old) row.replaceChild(fresh, old);
  });
  return select;
}

function buildMomentaryWidget(item) {
  const btn = document.createElement("button");
  btn.className = "io-press";
  btn.textContent = "Press";
  btn.disabled = !simRunning;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    logActivity(`Pressed ${item.label}`, "press");
    recordStep({ net: item.net, kind: "press" });
    pressInput(item.net);
  });
  inputPressButtons.push(btn);
  return btn;
}

function buildToggleWidget(item) {
  const btn = document.createElement("button");
  btn.className = "io-press io-toggle";
  let on = Boolean(item.default);
  const paint = () => {
    btn.textContent = on ? "ON" : "OFF";
    btn.classList.toggle("on", on);
  };
  paint();
  btn.disabled = !simRunning;
  btn.addEventListener("click", (e) => {
    e.stopPropagation();
    on = !on;
    paint();
    logActivity(`${item.label} switched ${on ? "ON" : "OFF"}`, "press");
    recordStep({ net: item.net, kind: "value", value: on ? 1 : 0 });
    sendInput(item.net, on ? 1 : 0);
  });
  inputPressButtons.push(btn);
  return btn;
}

// Pulse-counting inputs (coin acceptor, flow meter, encoder, tachometer...). Firmware for these counts
// EDGES INSIDE A TIME WINDOW, so the whole burst must be injected at once by the backend - clicking a
// button N times can't work, because each click is a separate round trip landing 100s of ms apart.
function buildPulseWidget(item) {
  const wrap = document.createElement("div");
  wrap.className = "io-analog";
  const count = document.createElement("input");
  count.type = "number";
  count.min = 1;
  count.max = 64;
  count.value = item.pulses ?? 1;
  count.className = "io-pulse-count";
  count.title = "How many pulses to inject as one burst";
  const btn = document.createElement("button");
  btn.className = "io-press";
  btn.textContent = "Inject";
  btn.disabled = !simRunning;
  const fire = async (e) => {
    e.stopPropagation();
    const n = Number(count.value) || 1;
    logActivity(`Injected ${n} pulse${n === 1 ? "" : "s"} into ${item.label}`, "press");
    recordStep({ net: item.net, kind: "pulse", count: n });
    const res = await fetch(`/api/projects/${currentProjectId}/sim/pulse`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ net: item.net, count: n }),
    });
    const out = await res.json();
    if (out.burst_ms !== undefined) {
      logActivity(`  burst delivered in ${out.burst_ms}ms`, out.burst_ms < 300 ? "on" : "off");
    }
  };
  btn.addEventListener("click", fire);
  count.addEventListener("click", (e) => e.stopPropagation());
  wrap.append(count, btn);
  inputPressButtons.push(btn, count);
  return wrap;
}

function buildAnalogWidget(item) {
  const wrap = document.createElement("div");
  wrap.className = "io-analog";
  const min = item.min ?? 0;
  const max = item.max ?? 1023;
  const slider = document.createElement("input");
  slider.type = "range";
  slider.min = min;
  slider.max = max;
  slider.step = item.step ?? 1;
  slider.value = item.default ?? min;
  // In SPICE mode an analog input is a simulation parameter (e.g. a supply voltage): it's set BEFORE a
  // run rather than streamed into a running simulator, so it's always editable.
  const spice = simMode === "spice";
  if (spice) spiceSupplies[item.net] = Number(slider.value);
  slider.disabled = !simRunning && !spice;
  const readout = document.createElement("span");
  readout.className = "io-analog-value";
  const paint = () => {
    readout.textContent = `${slider.value}${item.unit ? " " + item.unit : ""}`;
  };
  paint();

  // Send while dragging, but throttled - each send is a round trip to the real simulator.
  let pending = null;
  slider.addEventListener("input", (e) => {
    e.stopPropagation();
    paint();
    if (spice) { spiceSupplies[item.net] = Number(slider.value); return; }
    if (pending) return;
    pending = setTimeout(() => {
      pending = null;
      sendInput(item.net, Number(slider.value));
    }, 120);
  });
  slider.addEventListener("change", (e) => {
    e.stopPropagation();
    const shown = `${slider.value}${item.unit ? " " + item.unit : ""}`;
    if (spice) {
      logActivity(`${item.label} set to ${shown} - press Run SPICE to simulate it`, "press");
      return;
    }
    logActivity(`${item.label} set to ${shown}`, "press");
    recordStep({ net: item.net, kind: "value", value: Number(slider.value) });
    sendInput(item.net, Number(slider.value));
  });
  slider.addEventListener("click", (e) => e.stopPropagation());

  wrap.append(slider, readout);
  if (!spice) inputPressButtons.push(slider);
  return wrap;
}

function renderIoList(container, items, kindClass, liveSim) {
  container.innerHTML = "";
  for (const item of items) {
    netLabels[item.net] = item.label; // generic across any project - just reads the manifest's own labels
    if (item.ref) netRefs[item.net] = item.ref;
    // Prefer the io_map's own explicit ref (the meaningful/illustrative component for this signal -
    // e.g. the button connector, not whatever alphabetically-first part happens to share its net).
    // Falling back to net-inference alone tends to always resolve to the MCU board, since its ref
    // sorts early and touches nearly every net - see webview/ROADMAP.md for how that bug was found.
    const ref = item.ref || findRefForNet(item.net);
    const comp = ref ? refIndex[ref] : null;
    const div = document.createElement("div");
    div.className = `io-item ${kindClass}`;
    if (ref) div.dataset.ref = ref;
    div.innerHTML = `
      ${comp && comp.icon ? `<img src="${iconUrl(comp.icon)}" alt="" />` : ""}
      <span class="io-label">${item.label}</span>
      <span class="io-net" title="Click to highlight every component on this net">${item.net}${ref ? " · " + ref : ""}</span>
    `;
    if (ref) {
      div.title = `Click to locate ${ref} on the 3D board`;
      div.addEventListener("click", (e) => {
        if (e.target.classList.contains("io-net")) { highlightNet(item.net); return; }
        if (e.target.tagName !== "BUTTON") selectRef(ref);
      });
    }

    if (liveSim && kindClass === "input") {
      if (simMode === "wokwi") div.appendChild(buildTypePicker(item, div));
      const widget = buildInputWidget(item);
      widget.classList.add("io-widget");
      div.appendChild(widget);
    }

    if (liveSim && kindClass === "output") {
      // Output renderers are a registry too: led -> dot (+3D glow), seven-segment -> digit,
      // buzzer/tone -> frequency readout, display -> screenshot button. Adding a kind is one branch.
      // A boolean dot works for LEDs/actuators; a display type gets a real digit readout instead -
      // driven generically by whatever the backend decodes (see wokwi_mcp.decode_seven_segment).
      const type = (item.type || "led").toLowerCase();
      let el;
      if (type === "seven-segment") {
        el = document.createElement("span");
        el.className = "io-digit";
        el.textContent = "-";
      } else if (type === "voltage" || type === "analog" || type === "level") {
        // A node voltage, shown as a number - e.g. a timing capacitor ramping between 1/3 and 2/3 VCC.
        el = document.createElement("span");
        el.className = "io-digit io-voltage";
        el.textContent = "-- V";
      } else if (type === "buzzer" || type === "tone" || type === "speaker") {
        // A tone output isn't on/off - what matters is the frequency it's being driven at, which the
        // logic-analyzer capture measures properly. Optional WebAudio playback makes it audible.
        el = document.createElement("span");
        el.className = "io-digit io-tone";
        el.textContent = "--";
        el.title = "Drive frequency (use Capture waveforms to measure). Click to hear it.";
        el.addEventListener("click", (e) => {
          e.stopPropagation();
          const hz = Number(el.dataset.hz || 0);
          if (hz > 0) playTone(hz);
        });
      } else if (type === "display" || type === "screen" || type === "oled") {
        el = document.createElement("button");
        el.className = "io-press";
        el.textContent = "Snapshot";
        el.title = "Ask the simulator what this display is actually showing";
        el.addEventListener("click", async (e) => {
          e.stopPropagation();
          const res = await fetch(`/api/projects/${currentProjectId}/sim/shot`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ partId: item.wokwi_part || item.ref }),
          });
          const data = await res.json();
          setConsoleOpen(true);
          logToConsole({ label: `Snapshot ${item.label}`, ok: data.ok, output: data.output || data.error });
        });
      } else {
        el = document.createElement("span");
        el.className = "io-indicator";
      }
      div.appendChild(el);
      outputIndicatorEls[item.net] = el;
    }

    container.appendChild(div);
  }
}

function iconUrl(relPath) {
  return `/${relPath}`; // app/assets/icons/... served from the app static root
}

// ---------------------------------------------------------------- console
function setConsoleOpen(open) {
  consoleEl.classList.toggle("closed", !open);
  try { localStorage.setItem("pcb-webview-console-open", open ? "1" : "0"); } catch {}
}
// Console tabs: Output (action results) | Serial (what the firmware prints) | Analyzer (VCD capture)
document.getElementById("console-tabs").addEventListener("click", (e) => {
  const tab = e.target.dataset.tab;
  if (!tab) return;
  for (const b of document.querySelectorAll("#console-tabs .tab")) b.classList.toggle("active", b.dataset.tab === tab);
  document.getElementById("console-log").classList.toggle("hidden", tab !== "log");
  serialPanel.classList.toggle("hidden", tab !== "serial");
  capturePanel.classList.toggle("hidden", tab !== "capture");
});

consoleToggle.addEventListener("click", () => setConsoleOpen(consoleEl.classList.contains("closed")));
consoleClose.addEventListener("click", () => setConsoleOpen(false));
try {
  setConsoleOpen(localStorage.getItem("pcb-webview-console-open") === "1");
} catch { setConsoleOpen(false); }

function logToConsole(entry) {
  const div = document.createElement("div");
  div.className = `log-entry ${entry.ok ? "ok" : "fail"}`;
  const when = entry.timestamp ? new Date(entry.timestamp * 1000).toLocaleTimeString() : "";
  div.innerHTML = `
    <div class="log-meta">${entry.label || entry.action_id || ""} ${when ? "· " + when : ""}
      ${entry.ok === false ? "· FAILED" : ""}</div>
    <pre></pre>
  `;
  div.querySelector("pre").textContent = entry.output || "";
  consoleLog.appendChild(div);
  consoleLog.scrollTop = consoleLog.scrollHeight;
}

async function runAction(action) {
  setConsoleOpen(true);
  logToConsole({ label: action.label, output: "running...", ok: true, timestamp: Date.now() / 1000 });
  const res = await fetch(`/api/projects/${currentProjectId}/actions/${action.id}`, { method: "POST" });
  const entry = await res.json();
  logToConsole(entry);
}

function renderActionButtons(actions) {
  consoleActions.innerHTML = "";
  if (simMode !== "wokwi") {
    // Capture/record drive a live Wokwi session; a SPICE project already gets full waveforms per run.
    for (const action of actions) {
      const btn = document.createElement("button");
      btn.textContent = action.label;
      btn.addEventListener("click", () => runAction(action));
      consoleActions.appendChild(btn);
    }
    return;
  }
  // Live-simulation tools, available whenever the project supports it (not per-action config).
  const capture = document.createElement("button");
  capture.textContent = "Capture waveforms";
  capture.title = "Logic-analyzer snapshot - real duty cycle/frequency, instead of sampling a PWM pin";
  capture.addEventListener("click", () => { setConsoleOpen(true); captureWaveforms(); });
  const record = document.createElement("button");
  record.textContent = "Record scenario";
  record.title = "Capture your clicks as a replayable Wokwi scenario (a cheap regression test)";
  record.addEventListener("click", () => toggleRecording(record));
  consoleActions.append(capture, record);
  for (const action of actions) {
    const btn = document.createElement("button");
    btn.textContent = action.label;
    btn.addEventListener("click", () => runAction(action));
    consoleActions.appendChild(btn);
  }
}

// ---------------------------------------------------------------- activity feed
// Plain-language "I pressed this, now this is happening" log - built purely from the manifest's own
// human labels (netLabels, populated generically in renderIoList) and by diffing polled output values
// against their last known value. No project-specific code or extra config file needed - any project
// that declares io[] labels gets this for free.
const MAX_ACTIVITY_LINES = 60;

function logActivity(text, cls) {
  const line = document.createElement("div");
  line.className = `activity-line ${cls || ""}`;
  const t = new Date().toLocaleTimeString();
  line.innerHTML = `<span class="t">${t}</span>${text}`;
  activityLogEl.appendChild(line);
  while (activityLogEl.children.length > MAX_ACTIVITY_LINES) activityLogEl.removeChild(activityLogEl.firstChild);
  activityLogEl.scrollTop = activityLogEl.scrollHeight;
}

// ---------------------------------------------------------------- live simulation
// Backed by a REAL wokwi-cli MCP session on the backend (real compiled firmware, real wiring) - this
// frontend never simulates anything itself. Every start/stop cycle spends the project's Wokwi quota;
// the backend logs it to that project's test/wokwi/USAGE_LOG.md automatically.
function setInputButtonsEnabled(enabled) {
  for (const btn of inputPressButtons) btn.disabled = !enabled;
}

// Make a measured tone audible - "the buzzer is being driven at 2.7kHz" is easier to judge by ear.
let audioCtx = null;
function playTone(hz, ms = 350) {
  try {
    audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)();
    const osc = audioCtx.createOscillator();
    const gain = audioCtx.createGain();
    osc.frequency.value = hz;
    gain.gain.value = 0.08;
    osc.connect(gain).connect(audioCtx.destination);
    osc.start();
    osc.stop(audioCtx.currentTime + ms / 1000);
  } catch {
    /* audio is a nicety - never let it break the dashboard */
  }
}

function setOutputIndicator(net, value) {
  const el = outputIndicatorEls[net];
  if (!el) return;
  if (el.classList.contains("io-tone")) {
    // filled in by the analyzer capture, which is the only reliable source for a driven frequency
    return;
  }
  if (el.classList.contains("io-digit")) {
    el.textContent = value === null || value === undefined ? "-" : String(value);
  } else {
    el.classList.toggle("on", value === true);
  }
}

function resetOutputIndicators() {
  clearAllGlows();
  for (const net in outputIndicatorEls) setOutputIndicator(net, null);
  for (const net in lastOutputValues) delete lastOutputValues[net];
}

async function pollOutputs() {
  const res = await fetch(`/api/projects/${currentProjectId}/sim/outputs`);
  const values = await res.json();
  for (const [net, value] of Object.entries(values)) {
    setOutputIndicator(net, value);
    setComponentGlow(netRefs[net], value === true); // light the real part in the 3D view
    if (lastOutputValues[net] !== undefined && lastOutputValues[net] !== value) {
      const label = netLabels[net] || net;
      const state =
        typeof value === "boolean" ? (value ? "ON" : "OFF") : value === null ? "blank" : String(value);
      logActivity(`${label} &rarr; ${state}`, value === true ? "on" : "off");
    }
    lastOutputValues[net] = value;
  }
}

async function pressInput(net) {
  await fetch(`/api/projects/${currentProjectId}/sim/press`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ net }),
  });
}

// Set an input to any value and leave it there (toggles, analog/sensor values, ...). The backend passes
// the number straight to the real simulator's control, so new input kinds need no backend change.
async function sendInput(net, value) {
  await fetch(`/api/projects/${currentProjectId}/sim/input`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ net, value }),
  });
}

function formatQuota(q) {
  return `quota: ${Math.round(q.remaining_s)}s / ${Math.round(q.quota_s)}s left this month`;
}

async function refreshQuotaLabel() {
  const res = await fetch(`/api/projects/${currentProjectId}/sim/quota`);
  if (!res.ok) return;
  simStatusEl.textContent = formatQuota(await res.json());
}

function tickElapsedLabel() {
  if (!simStartedAt) return;
  const elapsed = (Date.now() - simStartedAt) / 1000;
  const limitPart = simLimitS ? ` / ${simLimitS}s limit` : "";
  simStatusEl.textContent = `running: ${elapsed.toFixed(1)}s${limitPart}`;
}

// Polls the server's own view of the session, not just this tab's local state - if the time limit
// auto-stopped it (or it died for any other reason), this tab's UI catches up within one poll instead
// of showing "Stop Simulation" forever for a session that no longer exists.
async function pollStatus() {
  const res = await fetch(`/api/projects/${currentProjectId}/sim/status`);
  const status = await res.json();
  if (!status.running && simRunning) {
    await finishSimulationUI("Simulation stopped (time limit reached or ended remotely).");
  }
}

async function startSimulation() {
  simToggle.disabled = true;
  simToggle.textContent = "Starting...";
  simLimitInput.disabled = true;
  activityLogEl.innerHTML = "";
  simLimitS = Number(simLimitInput.value) || null;
  logActivity(`Simulation started${simLimitS ? ` (auto-stops after ${simLimitS}s)` : ""}`, "press");
  const res = await fetch(`/api/projects/${currentProjectId}/sim/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ limit_s: simLimitS }),
  });
  const entry = await res.json();
  logToConsole(entry);
  simToggle.disabled = false;
  if (!entry.ok) {
    simToggle.textContent = "Start Simulation";
    simLimitInput.disabled = false;
    return;
  }
  simRunning = true;
  simStartedAt = Date.now();
  simToggle.textContent = "Stop Simulation";
  simToggle.classList.add("running");
  setInputButtonsEnabled(true);
  outputsPollTimer = setInterval(pollOutputs, 400);
  serialPanel.textContent = "";
  serialPollTimer = setInterval(pollSerial, 700);
  statusPollTimer = setInterval(() => {
    tickElapsedLabel();
    pollStatus();
  }, 300);
}

// Shared by the user clicking "Stop Simulation" and by pollStatus() detecting a server-side auto-stop -
// both need to reset the same UI state, but only the manual path should also POST /sim/stop.
async function finishSimulationUI(message) {
  clearInterval(outputsPollTimer);
  clearInterval(statusPollTimer);
  clearInterval(serialPollTimer);
  outputsPollTimer = null;
  statusPollTimer = null;
  serialPollTimer = null;
  resetOutputIndicators();
  setInputButtonsEnabled(false);
  simRunning = false;
  simStartedAt = null;
  simToggle.disabled = false;
  simToggle.textContent = "Start Simulation";
  simToggle.classList.remove("running");
  simLimitInput.disabled = false;
  if (message) logToConsole({ label: "Simulation", ok: true, output: message, timestamp: Date.now() / 1000 });
  await refreshQuotaLabel();
}

async function stopSimulation() {
  simToggle.disabled = true;
  const res = await fetch(`/api/projects/${currentProjectId}/sim/stop`, { method: "POST" });
  const entry = await res.json();
  logToConsole(entry);
  await finishSimulationUI(null);
}

simToggle.addEventListener("click", () => {
  if (simMode === "spice") return playbackRaf ? stopPlayback("Playback stopped.") : runSpice();
  return simRunning ? stopSimulation() : startSimulation();
});

// ---------------------------------------------------------------- SPICE simulation + playback
// For boards with no microcontroller. The spice service (webview/services/spice -> the shared
// tools/boardgen/make_spice.py stage) runs a real LTspice transient on the board's own netlist; this
// replays it in real time: outputs light up, the real part glows in 3D, voltages tick, and the Analyzer
// tab shows every waveform with a moving playhead. Offline, and costs no quota.
async function runSpice() {
  stopPlayback();
  simToggle.disabled = true;
  simToggle.textContent = "Simulating...";
  activityLogEl.innerHTML = "";
  const supplies = { ...spiceSupplies };
  const shown = Object.entries(supplies).map(([n, v]) => `${n}=${v}V`).join(", ");
  logActivity(`Running LTspice on the board's netlist${shown ? " (" + shown + ")" : ""}...`, "press");
  let data;
  try {
    const res = await fetch("/api/services/spice/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project: currentProjectId, supplies }),
    });
    data = await res.json();
  } catch (err) {
    data = { ok: false, error: String(err) };
  }
  simToggle.disabled = false;
  simToggle.textContent = "Run SPICE";
  if (!data.traces) {
    // The core returns a hint naming the start command when the service is down.
    const why = data.error || data.hint || JSON.stringify(data);
    logActivity(`SPICE failed: ${why}`, "off");
    setConsoleOpen(true);
    logToConsole({ label: "SPICE", ok: false, output: `${why}\n\n${data.hint || ""}`, timestamp: Date.now() / 1000 });
    return;
  }
  spiceResult = data;
  logToConsole({ label: "SPICE transient", ok: data.ok, output: data.log, timestamp: Date.now() / 1000 });
  for (const c of data.checks || []) {
    logActivity(`${c.ok ? "PASS" : "FAIL"} ${c.net} ${c.field} = ${c.value} (target ${c.target} ±${c.tol_pct}%)`,
                c.ok ? "on" : "off");
  }
  renderSpiceAnalyzer(data);
  startPlayback();
}

function spiceOutputValue(item, trace, i, metrics) {
  const v = trace[i];
  const type = (item.type || "led").toLowerCase();
  if (type === "voltage" || type === "analog" || type === "level") return `${v.toFixed(2)} V`;
  const m = metrics || {};
  return v > ((m.min ?? 0) + (m.max ?? 1)) / 2; // on/off at the settled midpoint, e.g. a 555's OUT
}

function startPlayback() {
  const data = spiceResult;
  const n = data.points;
  const outputs = currentIo.filter((i) => i.kind === "output" && data.traces[i.net]);
  const heads = [...capturePanel.querySelectorAll(".wave-playhead")];
  // Anchor to the first frame's own timestamp: rAF's `now` is the frame START, which can be earlier
  // than a performance.now() taken here - that made the first frame's time negative (index -1).
  let t0 = null;
  let lastLoop = 0;
  simToggle.textContent = "Stop playback";
  simToggle.classList.add("running");
  const frame = (now) => {
    if (t0 === null) t0 = now;
    const elapsed = Math.max(0, (now - t0) / 1000);
    const loop = Math.floor(elapsed / data.tstop_s);
    if (loop !== lastLoop) { lastLoop = loop; logActivity("Replaying from power-on", "press"); }
    const t = elapsed % data.tstop_s;
    const i = Math.min(n - 1, Math.round((t / data.tstop_s) * (n - 1)));
    for (const item of outputs) {
      const value = spiceOutputValue(item, data.traces[item.net], i, data.metrics[item.net]);
      setOutputIndicator(item.net, value);
      if (typeof value === "boolean" && lastOutputValues[item.net] !== value) {
        setComponentGlow(netRefs[item.net], value); // only on change - it clones/updates materials
        if (lastOutputValues[item.net] !== undefined) {
          logActivity(`${netLabels[item.net] || item.net} &rarr; ${value ? "ON" : "OFF"} at t=${t.toFixed(2)}s`,
                      value ? "on" : "off");
        }
      }
      lastOutputValues[item.net] = value;
    }
    for (const h of heads) h.style.left = `${(t / data.tstop_s) * 100}%`;
    simStatusEl.textContent = `SPICE playback t = ${t.toFixed(2)} / ${data.tstop_s}s (real time)`;
    playbackRaf = requestAnimationFrame(frame);
  };
  playbackRaf = requestAnimationFrame(frame);
}

function stopPlayback(message) {
  if (playbackRaf) cancelAnimationFrame(playbackRaf);
  playbackRaf = null;
  resetOutputIndicators();
  if (simMode === "spice") {
    simToggle.textContent = "Run SPICE";
    simToggle.classList.remove("running");
    simStatusEl.textContent = "LTspice - offline, no quota";
  }
  if (message) logActivity(message, "off");
}

function renderSpiceAnalyzer(data) {
  // Show the tab FIRST - a canvas sized inside a hidden panel measures 0px wide.
  setConsoleOpen(true);
  document.querySelector('#console-tabs .tab[data-tab="capture"]').click();
  const rows = Object.entries(data.metrics).map(([name, m]) =>
    `<tr><td>${name}</td><td>${m.min ?? "-"} .. ${m.max ?? m.peak_ma ?? "-"} ${m.unit}</td>` +
    `<td>${m.freq_hz ?? "-"} Hz</td><td>${m.high_ms ?? "-"} / ${m.low_ms ?? "-"} ms</td>` +
    `<td>${m.duty_pct ?? "-"}%</td></tr>`).join("");
  const supplies = Object.entries(data.supplies).map(([n, v]) => `${n} = ${v} V`).join(", ");
  capturePanel.innerHTML =
    `<div style="margin-bottom:6px;color:var(--muted)">LTspice transient, ${data.tstop_s}s simulated ` +
    `from power-on &middot; ${supplies}</div>` +
    "<table><tr><th>signal</th><th>range</th><th>freq</th><th>high / low</th><th>duty</th></tr>" +
    rows + "</table>";
  const css = getComputedStyle(document.documentElement);
  const line = css.getPropertyValue("--accent").trim() || "#4f9dff";
  const grid = css.getPropertyValue("--border").trim() || "#2c2f38";
  const muted = css.getPropertyValue("--muted").trim() || "#8a8f9a";
  for (const [name, trace] of Object.entries(data.traces)) {
    const unit = (data.metrics[name] || {}).unit || "";
    const row = document.createElement("div");
    row.className = "wave-row";
    const canvas = document.createElement("canvas");
    const head = document.createElement("div");
    head.className = "wave-playhead";
    row.append(canvas, head);
    capturePanel.appendChild(row);
    const dpr = window.devicePixelRatio || 1;
    const w = row.clientWidth || 600;
    const h = 64;
    canvas.width = w * dpr;
    canvas.height = h * dpr;
    canvas.style.height = `${h}px`;
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    const lo = Math.min(...trace);
    const hi = Math.max(...trace);
    const span = hi - lo || 1;
    ctx.strokeStyle = grid;
    ctx.beginPath();
    ctx.moveTo(0, h - 0.5);
    ctx.lineTo(w, h - 0.5);
    ctx.stroke();
    ctx.strokeStyle = line;
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    trace.forEach((v, k) => {
      const x = (k / (trace.length - 1)) * w;
      const y = 4 + (1 - (v - lo) / span) * (h - 8);
      if (k) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    });
    ctx.stroke();
    ctx.fillStyle = muted;
    ctx.font = "11px sans-serif";
    ctx.fillText(`${name}  ${lo.toFixed(2)}..${hi.toFixed(2)} ${unit}`, 6, 13);
  }
}

// ---------------------------------------------------------------- serial console
// The firmware is usually telling you exactly what's wrong ("ERR:NEED2000:HAVE500"). Reading it beats
// inferring state from LED pins, which is how a whole debugging session got spent.
async function pollSerial() {
  const res = await fetch(`/api/projects/${currentProjectId}/sim/serial`);
  const data = await res.json();
  if (data.text) {
    serialPanel.textContent += data.text;
    serialPanel.scrollTop = serialPanel.scrollHeight;
  }
}

// ---------------------------------------------------------------- logic analyzer (VCD)
// Sampling a PWM pin is a coin flip; the waveform gives the real duty cycle and frequency.
async function captureWaveforms() {
  capturePanel.textContent = "capturing...";
  const res = await fetch(`/api/projects/${currentProjectId}/sim/capture`, { method: "POST" });
  const data = await res.json();
  if (!data.ok) {
    capturePanel.textContent = `capture failed: ${data.output || data.error}`;
    return;
  }
  const rows = Object.entries(data.signals || {})
    .filter(([, v]) => v.edges > 0)
    .sort((a, b) => (b[1].duty_pct ?? 0) - (a[1].duty_pct ?? 0));
  if (!rows.length) {
    capturePanel.textContent = `captured ${data.duration_s}s but nothing changed state in that window.`;
    return;
  }
  // push measured frequencies into any buzzer/tone readouts on the dashboard
  for (const [net, el] of Object.entries(outputIndicatorEls)) {
    if (!el.classList || !el.classList.contains("io-tone")) continue;
    const spec = rows.find(([name]) => name.includes(net) || net.includes(name));
    if (spec && spec[1].freq_hz) {
      el.dataset.hz = spec[1].freq_hz;
      el.textContent = `${spec[1].freq_hz}Hz`;
    }
  }

  capturePanel.innerHTML =
    `<div style="margin-bottom:6px;color:var(--muted)">${data.duration_s}s captured &middot; ` +
    `duty cycle is what a PWM output is really doing</div>` +
    "<table><tr><th>signal</th><th>duty</th><th>freq</th><th>edges</th><th>now</th></tr>" +
    rows.map(([name, v]) =>
      `<tr><td>${name}</td><td>${v.duty_pct ?? "-"}%</td><td>${v.freq_hz ?? "-"} Hz</td>` +
      `<td>${v.edges}</td><td>${v.state ? "HIGH" : "LOW"}</td></tr>`).join("") +
    "</table>";
}

// ---------------------------------------------------------------- scenario recorder
// Turns a click session into a replayable Wokwi scenario - a regression test that costs seconds of
// quota instead of a manual run every time.
function recordStep(step) {
  if (!recorder.on) return;
  const now = Date.now();
  step.delay_ms = recorder.last ? Math.min(5000, now - recorder.last) : 0;
  recorder.last = now;
  recorder.steps.push(step);
}

async function toggleRecording(btn) {
  if (!recorder.on) {
    recorder.on = true;
    recorder.steps = [];
    recorder.last = 0;
    btn.textContent = "Recording... (stop & save)";
    btn.classList.add("running");
    logActivity("Recording started - every input you use is being captured", "press");
    return;
  }
  recorder.on = false;
  btn.textContent = "Record scenario";
  btn.classList.remove("running");
  if (!recorder.steps.length) {
    logActivity("Nothing recorded", "off");
    return;
  }
  const res = await fetch(`/api/projects/${currentProjectId}/scenario`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name: `rec_${new Date().toISOString().slice(11, 19).replace(/:/g, "")}`,
                            steps: recorder.steps }),
  });
  const data = await res.json();
  logActivity(data.ok ? `Saved ${data.steps}-step scenario -> ${data.path}` : `Save failed: ${data.error}`,
              data.ok ? "on" : "off");
}

async function loadHistory() {
  const res = await fetch(`/api/projects/${currentProjectId}/log`);
  const entries = await res.json();
  consoleLog.innerHTML = "";
  for (const entry of entries) logToConsole(entry);
}

// ---------------------------------------------------------------- project loading
async function loadProject(id) {
  if (simRunning) await stopSimulation(); // never leave a Wokwi session billing in the background
  stopPlayback();

  currentProjectId = id;
  const manifest = await (await fetch(`/api/projects/${id}/manifest`)).json();

  refIndex = {};
  for (const c of manifest.components) refIndex[c.ref] = c;
  netToRefs = manifest.nets;
  currentNets = manifest.nets;

  inputPressButtons.length = 0;
  for (const key in outputIndicatorEls) delete outputIndicatorEls[key];
  for (const key in netLabels) delete netLabels[key];
  for (const key in netRefs) delete netRefs[key];
  for (const key in lastOutputValues) delete lastOutputValues[key];
  activityLogEl.innerHTML = "";

  // Wokwi wins when both exist (it runs the real firmware); SPICE covers boards with no MCU.
  simMode = manifest.live_sim ? "wokwi" : manifest.spice_sim ? "spice" : null;
  for (const key in spiceSupplies) delete spiceSupplies[key];
  spiceResult = null;
  currentIo = manifest.io;
  const liveSim = simMode === "wokwi";
  simToggle.disabled = !simMode;
  simToggle.textContent = simMode === "spice" ? "Run SPICE" : "Start Simulation";
  simToggle.classList.remove("running");
  // the whole "Limit [..] s" label - hiding only the input left a stray "Limit s" beside Run SPICE
  document.getElementById("sim-limit-label").style.visibility = liveSim ? "visible" : "hidden";
  simToggle.title = liveSim
    ? "Runs the real firmware in a real Wokwi simulation - spends Wokwi quota while running"
    : simMode === "spice"
      ? "Simulates the board's real netlist in LTspice, then replays it in real time - offline, no quota"
      : "This project has no simulation configured (no wokwi_map.json, no SPICE block in netlist.py)";
  simStatusEl.textContent = simMode === "spice" ? "LTspice - offline, no quota" : "";
  if (liveSim) await refreshQuotaLabel();
  capturePanel.innerHTML = "";

  const inputs = manifest.io.filter((i) => i.kind === "input");
  const outputs = manifest.io.filter((i) => i.kind === "output");
  renderIoList(inputsList, inputs, "input", Boolean(simMode));
  renderIoList(outputsList, outputs, "output", Boolean(simMode));

  renderActionButtons(manifest.actions || []);
  await loadHistory();

  loadModel(`/projects/${id}/${manifest.model}`);
}

async function init() {
  const projects = await (await fetch("/api/projects")).json();
  projectPicker.innerHTML = "";
  for (const p of projects) {
    const opt = document.createElement("option");
    opt.value = p.id;
    opt.textContent = p.name;
    projectPicker.appendChild(opt);
  }
  projectPicker.addEventListener("change", () => loadProject(projectPicker.value));
  if (projects.length) await loadProject(projects[0].id);
}

init();
