// Entry point. Holds the shared state and the screen switcher.

import { prepareImage, PrepError } from "/static/js/image-prep.js";
import { MESSAGES } from "/static/js/messages.js";

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

// The real request is sent by the summon code in task 8.6, which listens for this event.
$("booth-form").addEventListener("submit", (event) => {
  event.preventDefault();
  if (state.busy || !canSummon()) return;
  document.dispatchEvent(new CustomEvent("booth:summon"));
});

syncDescription();
showScreen("booth");
