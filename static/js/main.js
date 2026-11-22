// Entry point. Holds the shared state and the screen switcher.

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

showScreen("booth");
