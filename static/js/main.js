// Entry point. Holds the shared state and the screen switcher.

import { prepareImage, PrepError } from "/static/js/image-prep.js";
import { MESSAGES, judgeText, limitText } from "/static/js/messages.js";
import { summon, getUsage, checkJudge } from "/static/js/api.js";
import { initSound, playSubmit, playStepComplete, playResult } from "/static/js/sound.js";
import { costumeNameFor, saveSpell, listSpells, deleteSpell, clearAll } from "/static/js/gallery.js";

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
  updateNavButton();
  window.scrollTo(0, 0);
}

// Exposed so it can be called from the browser console: showScreen('result')
window.showScreen = showScreen;

// The nav button flips between the booth and the gallery.
const navButton = document.getElementById("nav-toggle");

// Why one function: label and disabled state always follow state, even when
// showScreen() or setBusy() is called from code instead of a click.
function updateNavButton() {
  if (!navButton) return;
  navButton.textContent = state.screen === "gallery" ? "🎃 Booth" : "🖼️ Gallery";
  // Why disabled while busy: leaving the progress screen mid-spell is confusing.
  navButton.disabled = state.busy;
}

navButton?.addEventListener("click", () => {
  if (state.busy) return;
  if (state.screen === "gallery") {
    showScreen("booth");
  } else {
    showScreen("gallery");
    openGalleryList();
  }
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
  updateNavButton();
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

// Why try/catch: sessionStorage can throw when the browser blocks storage.
function readStoredPass() {
  try {
    return sessionStorage.getItem(JUDGE_KEY) || null;
  } catch {
    return null;
  }
}
const JUDGE_KEY = "pawleenJudgePass";
state.judgePass = readStoredPass(); // sent only as the X-Judge-Pass header
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
  // A later step starting means the one before it finished.
  if (index > 0) playStepComplete();
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

// Sound_Toggle lives in the top bar, so it is reachable on every screen.
initSound($("sound-toggle"));

async function startSummon() {
  // Build and send at once, so the request leaves well within 500 ms of the click (Req 3.6).
  const form = new FormData();
  form.append("pet_photo", state.petPrepared.blob, "pet.jpg");
  if (state.costumePrepared) {
    form.append("costume_photo", state.costumePrepared.blob, "costume.jpg");
  }
  form.append("description", state.description.trim());

  setBusy(true);
  playSubmit();
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
      playResult();
      state.result = data;
      saveToGallery(data); // right away, well inside the 2 seconds (Req 9.1)
      setActiveIndex(STEP_ORDER.length); // all three rows complete
      setProgress(100);
      $("progress-message").textContent = MESSAGES.ready;
      $("progress-sub").hidden = true;
      readyTimer = setTimeout(() => {
        renderResult(data);
        showScreen("result");
        setBusy(false);
      }, READY_PAUSE_MS);
    } else if (type === "error") {
      finished = true;
      // Limit messages are built here from retry_after_seconds, so the time is always relative.
      const text = limitText(data.code, data.retry_after_seconds) || data.message;
      showFailure(text, Boolean(data.show_chips));
    }
    // "heartbeat" needs no UI; api.js already reset the watchdog.
  };

  const outcome = await summon(form, state.judgePass, onEvent, myAbort.signal);
  if (outcome === "aborted" || finished) return;
  // Stream ended or died without a result or error: treat as a lost connection (Req 7.13).
  finished = true;
  showFailure(MESSAGES.connectionLost, false);
}

// ---- Result_View (task 8.7) ----

let resultBlob = null; // full-resolution image as returned by the server
let resultUrl = null; // object URLs must be revoked, or the memory stays used
let beforeUrl = null;

// Turns the base64 text from the server into a Blob (no re-encoding, so full resolution).
function base64ToBlob(b64, mime) {
  const bytes = Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));
  return new Blob([bytes], { type: mime });
}

// Req 8.11: "2 spells left tonight", "1 spell left tonight", "0 spells left tonight".
export function spellsText(n) {
  return `🕯️ ${n} ${n === 1 ? "spell" : "spells"} left tonight`;
}

function resultFile() {
  const ext = resultBlob.type === "image/jpeg" ? "jpg" : "png";
  return new File([resultBlob], `pawleen-spooky-pet.${ext}`, { type: resultBlob.type });
}

export function renderResult(data) {
  if (resultUrl) URL.revokeObjectURL(resultUrl);
  if (beforeUrl) URL.revokeObjectURL(beforeUrl);
  resultBlob = base64ToBlob(data.image_b64, data.mime || "image/png");
  resultUrl = URL.createObjectURL(resultBlob);
  $("result-image").src = resultUrl;

  // The original pet photo goes next to the result (Req 8.2).
  beforeUrl = state.petPrepared ? URL.createObjectURL(state.petPrepared.blob) : null;
  if (beforeUrl) $("result-before").src = beforeUrl;

  const notice = $("result-notice");
  const noticeText = data.message || MESSAGES[data.notice === "not_verified" ? "notVerified" : "wonky"];
  notice.hidden = !data.notice;
  if (data.notice) notice.textContent = noticeText;

  $("result-spells").textContent = spellsText(data.remaining);
  $("result-error").hidden = true;

  // Why check canShare with a real file: some browsers have share() but not for files.
  const share = $("result-share");
  share.hidden = !(navigator.canShare && navigator.canShare({ files: [resultFile()] }));

  // Restart the fog animation each time a new result is shown.
  const box = $("result-image").parentElement;
  box.classList.remove("fog-reveal");
  void box.offsetWidth; // forces a reflow so the animation can start again
  box.classList.add("fog-reveal");
}

// Saves through a temporary link. On failure the button stays, so the visitor can retry (Req 8.5).
function downloadResult() {
  try {
    const link = document.createElement("a");
    link.href = resultUrl;
    link.download = resultFile().name;
    document.body.append(link);
    link.click();
    link.remove();
    $("result-error").hidden = true;
  } catch (err) {
    show($("result-error"), MESSAGES.downloadFailed);
  }
}

async function shareResult() {
  try {
    await navigator.share({ files: [resultFile()], title: "My spooky pet" });
  } catch (err) {
    // The visitor closing the share sheet is not a failure; anything else falls back to download (Req 8.7).
    if (err && err.name === "AbortError") return;
    downloadResult();
  }
}

$("result-download").addEventListener("click", downloadResult);
$("result-share").addEventListener("click", shareResult);

// Req 8.9: keep the pet, clear the costume photo and the description.
$("result-another").addEventListener("click", () => {
  $("costume-remove").click();
  description.value = "";
  trimmed.hidden = true;
  syncDescription();
  showScreen("booth");
});

// Req 8.10: clear everything.
$("result-new-pet").addEventListener("click", () => {
  $("costume-remove").click();
  $("pet-remove").click();
  description.value = "";
  trimmed.hidden = true;
  syncDescription();
  state.result = null;
  showScreen("booth");
});

// ---- Haunted_Gallery view (task 10.1) ----

// Saves the new result. A failure only shows a message: the image stays on the
// result screen and can still be downloaded (Req 9.15).
async function saveToGallery(data) {
  $("result-save-error").hidden = true;
  try {
    const name = costumeNameFor(state.description, data.costume_name);
    await saveSpell({ blob: base64ToBlob(data.image_b64, data.mime || "image/png"), costumeName: name });
  } catch (err) {
    show($("result-save-error"), MESSAGES.notSaved);
  }
}

// Shared confirm dialog. Resolves true for "Banish", false for "Keep it" or Escape.
// Focus stays inside the dialog and goes back to where it was afterwards (Req 9.8).
function confirmBanish() {
  return new Promise((resolve) => {
    const overlay = $("confirm-overlay");
    const yes = $("confirm-yes");
    const no = $("confirm-no");
    const opener = document.activeElement;

    function close(answer) {
      overlay.hidden = true;
      document.removeEventListener("keydown", onKey, true);
      yes.removeEventListener("click", onYes);
      no.removeEventListener("click", onNo);
      // If the opener was removed from the page meanwhile, fall back to the gallery title.
      const target = opener && document.contains(opener) ? opener : $("gallery-title");
      target.focus();
      resolve(answer);
    }
    const onYes = () => close(true);
    const onNo = () => close(false);
    function onKey(event) {
      if (event.key === "Escape") {
        event.preventDefault();
        close(false);
      } else if (event.key === "Tab") {
        // Two buttons only: wrap around so focus never leaves the dialog.
        event.preventDefault();
        (document.activeElement === no ? yes : no).focus();
      }
    }

    yes.addEventListener("click", onYes);
    no.addEventListener("click", onNo);
    document.addEventListener("keydown", onKey, true);
    overlay.hidden = false;
    no.focus(); // the safe choice gets the focus first
  });
}

const galleryGrid = $("gallery-grid");
let thumbUrls = []; // revoked on each redraw so memory is freed
let detailUrl = null;
let current = null; // the spell open in the detail view

function formatDate(ms) {
  // Why: toLocaleString uses the visitor's own time zone, e.g. "Nov 22, 4:30 PM".
  return new Date(ms).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function showListView() {
  $("gallery-list-view").hidden = false;
  $("gallery-detail-view").hidden = true;
  if (detailUrl) URL.revokeObjectURL(detailUrl);
  detailUrl = null;
  current = null;
}

// Reads the store and redraws the list. Returns false when the read failed.
async function refreshGallery() {
  let spells;
  try {
    spells = await listSpells();
  } catch (err) {
    // Read failed: say so and touch nothing in storage (Req 9.16).
    show($("gallery-load-error"), MESSAGES.galleryLoadFailed);
    galleryGrid.replaceChildren();
    $("gallery-empty").hidden = true;
    $("gallery-clear").hidden = true;
    return false;
  }
  $("gallery-load-error").hidden = true;
  thumbUrls.forEach((u) => URL.revokeObjectURL(u));
  thumbUrls = [];
  galleryGrid.replaceChildren(...spells.map(renderThumb));
  $("gallery-empty").hidden = spells.length > 0;
  $("gallery-clear").hidden = spells.length === 0;
  return true;
}

function renderThumb(spell) {
  const url = URL.createObjectURL(spell.blob);
  thumbUrls.push(url);
  const li = document.createElement("li");
  li.className = "min-w-0";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "flex w-full min-w-0 flex-col gap-1 rounded-xl border border-witch/60 p-2 text-left hover:bg-witch/20";
  const img = document.createElement("img");
  img.src = url;
  img.alt = "";
  img.className = "aspect-[2/3] w-full rounded-lg object-cover";
  const name = document.createElement("span");
  name.className = "break-words text-sm text-pumpkin";
  name.textContent = spell.costumeName;
  const date = document.createElement("span");
  date.className = "text-xs text-witch-light";
  date.textContent = formatDate(spell.savedAt);
  button.append(img, name, date);
  button.setAttribute("aria-label", `${spell.costumeName}, ${formatDate(spell.savedAt)}`);
  button.addEventListener("click", () => openDetail(spell));
  li.append(button);
  return li;
}

function openDetail(spell) {
  current = spell;
  if (detailUrl) URL.revokeObjectURL(detailUrl);
  detailUrl = URL.createObjectURL(spell.blob);
  $("gallery-detail-image").src = detailUrl;
  $("gallery-detail-name").textContent = spell.costumeName;
  $("gallery-detail-date").textContent = formatDate(spell.savedAt);
  $("gallery-detail-error").hidden = true;
  const file = spellFile(spell);
  $("gallery-share").hidden = !(navigator.canShare && navigator.canShare({ files: [file] }));
  $("gallery-list-view").hidden = true;
  $("gallery-detail-view").hidden = false;
  window.scrollTo(0, 0);
}

function spellFile(spell) {
  const ext = spell.blob.type === "image/jpeg" ? "jpg" : "png";
  return new File([spell.blob], `pawleen-spooky-pet-${spell.id}.${ext}`, { type: spell.blob.type });
}

async function openGalleryList() {
  showListView();
  $("gallery-error").hidden = true;
  await refreshGallery();
}

// Original resolution: the stored Blob is saved as is (Req 9.5).
$("gallery-download").addEventListener("click", () => {
  if (!current) return;
  try {
    const link = document.createElement("a");
    link.href = detailUrl;
    link.download = spellFile(current).name;
    document.body.append(link);
    link.click();
    link.remove();
    $("gallery-detail-error").hidden = true;
  } catch (err) {
    show($("gallery-detail-error"), MESSAGES.downloadFailed);
  }
});

$("gallery-share").addEventListener("click", async () => {
  if (!current) return;
  try {
    await navigator.share({ files: [spellFile(current)], title: "My spooky pet" });
  } catch (err) {
    if (err && err.name === "AbortError") return; // closing the share sheet is fine
    $("gallery-download").click(); // Req 8.7: fall back to a download
  }
});

$("gallery-back").addEventListener("click", () => {
  showListView();
  $("gallery-title").focus();
});

$("gallery-delete").addEventListener("click", async () => {
  if (!current || !(await confirmBanish())) return;
  const id = current.id;
  try {
    await deleteSpell(id); // only this record (Req 9.9)
  } catch (err) {
    show($("gallery-detail-error"), MESSAGES.galleryDeleteFailed);
    return;
  }
  showListView();
  await refreshGallery();
  $("gallery-title").focus();
});

$("gallery-clear").addEventListener("click", async () => {
  if (!(await confirmBanish())) return;
  try {
    await clearAll();
  } catch (err) {
    show($("gallery-error"), MESSAGES.galleryDeleteFailed);
    return;
  }
  await refreshGallery();
  $("gallery-title").focus();
});

// ---- Judge pass and usage (task 10.2) ----

const judgeForm = $("judge-form");
const judgeInput = $("judge-input");
const judgeMessage = $("judge-message");
const judgeSubmit = $("judge-submit");

// Swaps the pass box for a small badge while a pass is stored; the box returns without one.
function showJudgeBadge(remaining) {
  const badge = $("judge-badge");
  if (!state.judgePass) {
    badge.hidden = true;
    judgeForm.hidden = false;
    return;
  }
  if (typeof remaining === "number") {
    badge.textContent = `🔑 Judge mode: ${remaining} ${remaining === 1 ? "spell" : "spells"} tonight`;
  } else if (!badge.textContent) {
    badge.textContent = "🔑 Judge mode";
  }
  badge.hidden = false;
  judgeForm.hidden = true;
}
async function refreshUsage() {
  const usage = await getUsage(state.judgePass);
  const line = $("usage-line");
  if (!usage) {
    line.hidden = true; // Why hide: no guess is better than a wrong number
    return;
  }
  line.textContent = spellsText(usage.remaining);
  line.hidden = false;
  showJudgeBadge(usage.remaining);
}

// Checks a pass and shows the right message. Returns true when it was accepted.
async function submitJudgePass(pass) {
  judgeSubmit.disabled = true; // Why: one check at a time
  judgeMessage.textContent = "🕯️ Checking your key...";
  judgeMessage.hidden = false;
  const result = pass.length >= 1 && pass.length <= 128 ? await checkJudge(pass) : { status: "invalid" };
  judgeSubmit.disabled = false;

  if (result.status === "valid") {
    try {
      sessionStorage.setItem(JUDGE_KEY, pass); // lasts until the tab session ends (Req 11.14)
    } catch {
      // Storage blocked: the pass still works until the page is reloaded.
    }
    state.judgePass = pass;
    judgeInput.value = "";
    judgeMessage.textContent = judgeText.welcome(result.remaining);
    showJudgeBadge(result.remaining);
    refreshUsage();
    return true;
  }
  // Every other outcome leaves the stored pass untouched (Req 11.9).
  if (result.status === "invalid") judgeMessage.textContent = judgeText.invalid;
  else if (result.status === "locked") judgeMessage.textContent = judgeText.sealed(result.retryAfter);
  else judgeMessage.textContent = judgeText.failed;
  return false;
}

judgeForm.addEventListener("submit", (event) => {
  event.preventDefault();
  const pass = judgeInput.value;
  if (pass === "" || judgeSubmit.disabled) return;
  submitJudgePass(pass);
});

// ?pass=... in the address: submit at once (within 1 s), then hide it from the bar on success.
async function handlePassParameter() {
  const url = new URL(window.location.href);
  const pass = url.searchParams.get("pass");
  if (!pass) return;
  const ok = await submitJudgePass(pass);
  if (ok) {
    url.searchParams.delete("pass");
    history.replaceState(null, "", url.pathname + url.search + url.hash);
  }
}

// Read the gallery once at page load so a broken store is reported early (Req 9.16).
refreshGallery();
showJudgeBadge();
refreshUsage();
handlePassParameter();

syncDescription();
showScreen("booth");
