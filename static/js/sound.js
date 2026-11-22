// Sound_Toggle and tiny WebAudio tones. No audio files are used.
// Why off by default: surprise noise is rude, and phones may be in a quiet place.

const KEY = "pawleenSound";

let enabled = false;
let ctx = null; // created lazily, because browsers only allow audio after a tap

// localStorage can throw (private mode, blocked storage), so every access is guarded.
function readSaved() {
  try {
    return localStorage.getItem(KEY) === "on";
  } catch (err) {
    return false;
  }
}

function save(value) {
  try {
    localStorage.setItem(KEY, value ? "on" : "off");
  } catch (err) {
    // The toggle still works for this visit; it just will not be remembered.
  }
}

export function isEnabled() {
  return enabled;
}

// One short sine tone. `delay` (seconds) lets us chain notes into a tiny melody.
function tone(freq, delay, length) {
  const AudioCtx = window.AudioContext || window.webkitAudioContext;
  if (!AudioCtx) return;
  if (!ctx) ctx = new AudioCtx();
  if (ctx.state === "suspended") ctx.resume();
  const start = ctx.currentTime + delay;
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.type = "sine";
  osc.frequency.value = freq;
  // Quick fade in and out avoids clicks; low volume keeps it gentle.
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(0.12, start + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  osc.connect(gain).connect(ctx.destination);
  osc.start(start);
  osc.stop(start + length + 0.02);
}

// Each play function does nothing when sound is off or audio fails.
function play(notes) {
  if (!enabled) return;
  try {
    for (const [freq, delay, length] of notes) tone(freq, delay, length);
  } catch (err) {
    // Sound is a bonus; never let it break the booth.
  }
}

export function playSubmit() {
  play([[220, 0, 0.15], [330, 0.12, 0.2]]);
}

export function playStepComplete() {
  play([[523, 0, 0.12]]);
}

export function playResult() {
  play([[392, 0, 0.15], [523, 0.14, 0.15], [659, 0.28, 0.3]]);
}

function render(button) {
  button.setAttribute("aria-pressed", String(enabled));
  button.setAttribute("aria-label", enabled ? "Sound on" : "Sound off");
  button.textContent = enabled ? "🔊" : "🔇";
}

// Wires the top-bar button and restores the saved choice.
export function initSound(button) {
  enabled = readSaved();
  render(button);
  button.addEventListener("click", () => {
    enabled = !enabled;
    save(enabled);
    render(button);
    // The click is a user gesture, so this also unlocks audio and confirms it works.
    if (enabled) playStepComplete();
  });
}
