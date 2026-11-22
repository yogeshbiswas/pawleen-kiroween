// Entry point. Holds the shared state and the screen switcher.

import { prepareImage, PrepError } from "/static/js/image-prep.js";
import { MESSAGES } from "/static/js/messages.js";
import { summon } from "/static/js/api.js";

export const SCREENS = ["booth", "progress", "result", "gallery", "error"];

// Why one object: every later module reads and writes the same state.
export const state = {
  screen: "booth",
  petPrepared: null, // result of prepareImage for the pet photo
  costumePrepared: null, // result of prepareImage for the costume photo
  description: "",
  busy: false, // true while a summon request runs
};

// Shows one screen and hides the others. Unknown names are ignored.
export function showScreen(name) {
  if (!SCREENS.includes(name)) {
    console.warn("Unknown screen:", name);
    return;
  }
  for (const section of document.querySelectorAll("[data-screen]")) {
    section.hidden = section.dataset.screen !== name;
  }
  state.screen = name;
  window.scrollTo(0, 0);
}

// Exposed so it can be called from the browser console: showScreen('result')
window.showScreen = showScreen;

// The nav button flips between the booth and the gallery.
const navButton = document.getElementById("nav-toggle");
navButton?.addEventListener("click", () => {
  const toGallery = state.screen !== "gallery";
  showScreen(toGallery ? "gallery" : "booth");
  navButton.textContent = toGallery ? "🎃 Booth" : "🖼️ Gallery";
});

// ---- Booth form (task 8.5) ----

const DESCRIPTION_MAX = 200;
const $ = (id) => document.getElementById(id);

function show(el, text) {
  if (text !== undefined) el.textContent = text;
  el.hidden = false;
}

// Enabled only when a pet photo is ready AND there is a costume photo or text.
export function canSummon() {
  return Boolean(state.petPrepared) &&
    (Boolean(state.costumePrepared) || state.description.trim() !== "");
}

const summonButton = $("summon-button");
const summonHint = $("summon-hint");

export function updateSummonButton() {
  const ready = canSummon();
  // Why disabled while busy: stops a double click from sending two requests.
  summonButton.disabled = !ready || state.busy;
  summonHint.hidden = ready;
}

// Called by the summon code (task 8.6) when a request starts or ends.
export function setBusy(busy) {
  state.busy = busy;
  updateSummonButton();
}

// Sets up one upload slot. `key` is the state field that holds the prepared image.
// Why a helper: the pet and costume uploads behave the same, only the ids differ.
function setupUpload({ key, prefix, notesSmall }) {
  const input = $(`${prefix}-input`);
  const preview = $(`${prefix}-preview`);
  const previewBox = $(`${prefix}-preview-box`);
  const darkroom = $(`${prefix}-darkroom`);
  const error = $(`${prefix}-error`);
  const small = notesSmall ? $(`${prefix}-small`) : null;
  const removeButton = $(`${prefix}-remove`);
  let previewUrl = null;
  let latestRun = 0; // Why: ignore a slow older file if a newer one was picked

  function clearPreview() {
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = null;
    preview.removeAttribute("src");
    previewBox.hidden = true;
  }

  input.addEventListener("change", async () => {
    const file = input.files && input.files[0];
    input.value = ""; // lets the same file be chosen again later
    if (!file) return;

    const run = ++latestRun;
    error.hidden = true;
    show(darkroom, MESSAGES.darkroom);
    try {
      const prepared = await prepareImage(file);
      if (run !== latestRun) return;
      // A valid new file replaces the old one.
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = URL.createObjectURL(prepared.blob);
      preview.src = previewUrl;
      previewBox.hidden = false;
      state[key] = prepared;
      if (small) {
        small.textContent = MESSAGES.smallPhoto;
        small.hidden = !prepared.small;
      }
    } catch (err) {
      if (run !== latestRun) return;
      // Rejected file: the previous selection and preview stay as they were.
      const code = err instanceof PrepError ? err.code : "unreadable";
      show(error, code === "type" ? MESSAGES.fileType : MESSAGES.unreadable);
    } finally {
      if (run === latestRun) darkroom.hidden = true;
      updateSummonButton();
    }
  });

  removeButton.addEventListener("click", () => {
    latestRun++; // cancels any file still being prepared
    state[key] = null;
    clearPreview();
    error.hidden = true;
    darkroom.hidden = true;
    if (small) small.hidden = true;
    updateSummonButton();
  });
}

setupUpload({ key: "petPrepared", prefix: "pet", notesSmall: true });
setupUpload({ key: "costumePrepared", prefix: "costume", notesSmall: false });

// Description: live counter, chips, and a trim message on long pastes.
const description = $("description");
const counter = $("description-count");
const trimmed = $("description-trimmed");

function syncDescription() {
  state.description = description.value;
  counter.textContent = `${description.value.length} / ${DESCRIPTION_MAX}`;
  updateSummonButton();
}

description.addEventListener("input", () => {
  trimmed.hidden = true;
  syncDescription();
});

// Why check on paste: maxlength cuts the text silently, so we compare the
// lengths ourselves to tell the visitor what happened.
description.addEventListener("paste", (event) => {
  const pasted = event.clipboardData ? event.clipboardData.getData("text") : "";
  const selected = description.selectionEnd - description.selectionStart;
  const newLength = description.value.length - selected + pasted.length;
  if (newLength > DESCRIPTION_MAX) {
    // Delayed so it runs after the input event, which hides the message.
    setTimeout(() => show(trimmed, MESSAGES.descriptionTrimmed), 0);
  }
});

for (const chip of document.querySelectorAll("#chips .chip")) {
  chip.addEventListener("click", () => {
    description.value = chip.dataset.text.slice(0, DESCRIPTION_MAX);
    trimmed.hidden = true;
    syncDescription();
  });
}

$("booth-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.busy || !canSummon()) return;
  startSummon();
});

// ---- Summon stream and Progress_Screen (task 8.6) ----

const STEP_ORDER = ["gatekeeping", "brewing", "checking"];
const STEP_PERCENT = { gatekeeping: 0, brewing: 33, checking: 66 }; // Req 7.4: 0, 33, 66, 100
const STEP_ICONS = ["🔮", "🧪", "🔍"];
const STEP_TEXT = {
  gatekeeping: MESSAGES.stepGatekeeping,
  brewing: MESSAGES.stepBrewing,
  checking: MESSAGES.stepChecking,
};
const ROTATE_MS = 4000; // Req 7.7
const READY_PAUSE_MS = 900; // short pause so the visitor sees the 100 % bar

state.judgePass = null; // set by the judge task; sent only as a header
state.result = null; // the last result event, shown by the result screen (task 8.7)

let summonAbort = null; // lets the back button stop a running request
let rotateTimer = null;
let readyTimer = null;

function setProgress(percent) {
  $("progress-fill").style.width = `${percent}%`;
  $("progress-track").setAttribute("aria-valuenow", String(percent));
}

// Rows before the current step are done (✅), the current one glows, later ones are dimmed.
// Passing an index past the last row marks every row complete.
function setActiveIndex(index) {
  document.querySelectorAll("#progress-steps li").forEach((row, i) => {
    const rowState = i < index ? "complete" : i === index ? "active" : "pending";
    row.dataset.state = rowState;
    row.querySelector(".step-icon").textContent = rowState === "complete" ? "✅" : STEP_ICONS[i];
  });
}

function stopRotation() {
  clearInterval(rotateTimer);
  rotateTimer = null;
}

function startRotation() {
  stopRotation();
  const sub = $("progress-sub");
  let i = 0;
  sub.textContent = MESSAGES.brewingLines[0];
  sub.hidden = false;
  rotateTimer = setInterval(() => {
    i = (i + 1) % MESSAGES.brewingLines.length;
    sub.textContent = MESSAGES.brewingLines[i];
  }, ROTATE_MS);
}

function resetProgress() {
  stopRotation();
  clearTimeout(readyTimer);
  setActiveIndex(0);
  setProgress(0);
  $("progress-message").textContent = MESSAGES.stepGatekeeping;
  $("progress-sub").hidden = true;
}

function handleStep(data) {
  const index = STEP_ORDER.indexOf(data.step);
  if (index < 0) return;
  setActiveIndex(index);
  setProgress(STEP_PERCENT[data.step]);
  // Req 7.8: a second round says so, with the attempt number.
  $("progress-message").textContent = data.recast
    ? `${MESSAGES.recast} Attempt ${data.attempt} of ${data.max_attempts}`
    : STEP_TEXT[data.step];
  if (data.step === "brewing") startRotation();
  else {
    stopRotation();
    $("progress-sub").hidden = true;
  }
}

// Fills the error screen. Chips are shown only when the server asks for them (Req 4.10).
function showFailure(message, showChips) {
  stopRotation();
  $("error-message").textContent = message || MESSAGES.genericError;
  const chipBox = $("error-chips");
  chipBox.replaceChildren();
  chipBox.hidden = !showChips;
  if (showChips) {
    for (const source of document.querySelectorAll("#chips .chip")) {
      const chip = source.cloneNode(true);
      chip.addEventListener("click", () => {
        // Same as the booth chips: fill the description, then go back to the booth.
        description.value = chip.dataset.text.slice(0, DESCRIPTION_MAX);
        trimmed.hidden = true;
        syncDescription();
        backToBooth();
      });
      chipBox.append(chip);
    }
  }
  showScreen("error");
  setBusy(false);
}

// All selections live in `state` and the form, so going back keeps them (Req 7.12).
function backToBooth() {
  if (summonAbort) summonAbort.abort();
  summonAbort = null;
  resetProgress();
  showScreen("booth");
  setBusy(false);
}

$("error-back").addEventListener("click", backToBooth);

async function startSummon() {
  // Build and send at once, so the request leaves well within 500 ms of the click (Req 3.6).
  const form = new FormData();
  form.append("pet_photo", state.petPrepared.blob, "pet.jpg");
  if (state.costumePrepared) {
    form.append("costume_photo", state.costumePrepared.blob, "costume.jpg");
  }
  form.append("description", state.description.trim());

  setBusy(true);
  resetProgress();
  showScreen("progress");
  summonAbort = new AbortController();
  const myAbort = summonAbort;
  let finished = false; // one terminal event (result or error) ends the run

  const onEvent = (type, data) => {
    if (finished) return;
    if (type === "step") handleStep(data);
    else if (type === "result") {
      finished = true;
      stopRotation();
      state.result = data;
      setActiveIndex(STEP_ORDER.length); // all three rows complete
      setProgress(100);
      $("progress-message").textContent = MESSAGES.ready;
      $("progress-sub").hidden = true;
      // Task 8.7 renders the result; here we only switch to its screen.
      readyTimer = setTimeout(() => {
        showScreen("result");
        setBusy(false);
      }, READY_PAUSE_MS);
    } else if (type === "error") {
      finished = true;
      showFailure(data.message, Boolean(data.show_chips));
    }
    // "heartbeat" needs no UI; api.js already reset the watchdog.
  };

  const outcome = await summon(form, state.judgePass, onEvent, myAbort.signal);
  if (outcome === "aborted" || finished) return;
  // Stream ended or died without a result or error: treat as a lost connection (Req 7.13).
  finished = true;
  showFailure(MESSAGES.connectionLost, false);
}

syncDescription();
showScreen("booth");
