// Bats: each crossing follows 4-7 random waypoints, drawn frame by frame with
// requestAnimationFrame so the flight looks erratic instead of a regular wave.
// The wing flap itself is CSS (styles.css); this file sets its speed.

const MAX_BATS = 4; // Why: more than 4 would crowd the screen.
const MIN_FLAP = 0.25; // seconds per flap, fastest (swoops)
const MAX_FLAP = 0.4; // seconds per flap, slowest (hovering, drifting)
const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");

function random(min, max) {
  return min + Math.random() * (max - min);
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function easeInOut(t) {
  return 0.5 - 0.5 * Math.cos(Math.PI * t);
}

// How far past the screen edge a bat starts and ends, so none of it shows.
const EDGE_MARGIN = 20;

// Why: the booth sits in the middle of the page, so a crossing stays in one
// band: the top third (most of the time) or low down. Never mid height, and the
// whole bat (top y + its height) stays above the bottom 15% of the screen.
function pickBand(batHeight) {
  const h = window.innerHeight;
  if (Math.random() < 0.7) return [h * 0.04, h * 0.3];
  const lowest = h * 0.85 - batHeight;
  return [Math.min(h * 0.78, lowest - 20), lowest];
}

function makeWaypoints(startX, endX, band) {
  const count = Math.floor(random(4, 8)); // 4 to 7
  const step = (endX - startX) / (count - 1);
  const points = [];
  for (let i = 0; i < count; i++) {
    // Small sideways jitter, but never more than half a step, so the bat keeps moving forward.
    const jitter = i === 0 || i === count - 1 ? 0 : random(-0.4, 0.4) * step;
    points.push({ x: startX + step * i + jitter, y: random(band[0], band[1]) });
  }
  return points;
}

function startCrossing(bat) {
  // Check again each crossing, in case the user changed the setting.
  if (motionQuery.matches) {
    bat.el.style.visibility = "hidden";
    bat.active = false;
    return;
  }
  const size = random(40, 64);
  const leftToRight = Math.random() < 0.5;
  // Why: first and last waypoints are fully off-screen (beyond the bat's width).
  const startX = leftToRight ? -size - EDGE_MARGIN : window.innerWidth + EDGE_MARGIN;
  const endX = leftToRight ? window.innerWidth + EDGE_MARGIN : -size - EDGE_MARGIN;

  bat.size = size;
  bat.leftToRight = leftToRight;
  bat.band = pickBand(size / 2);
  bat.points = makeWaypoints(startX, endX, bat.band);
  bat.index = 0;
  bat.eventChance = random(0.2, 0.3); // share of segments with something special
  // Normal cruising speed in px per second: the whole trip takes 12-24 s.
  bat.speed = Math.abs(endX - startX) / random(12, 24);
  bat.flip = leftToRight ? "1 1" : "-1 1";

  const el = bat.el;
  el.style.width = `${size}px`;
  el.style.height = `${size / 2}px`;
  // Flip the bat so it faces the way it flies.
  el.style.scale = bat.flip;
  // Why: put the bat at its off-screen start BEFORE showing it. Otherwise it
  // would flash for one frame at its old position or at the top-left corner.
  el.style.transform = `translate(${bat.points[0].x}px, ${bat.points[0].y}px)`;
  el.style.visibility = "visible";
  bat.active = true;
  startSegment(bat);
}

function startSegment(bat) {
  const from = bat.points[bat.index];
  const to = bat.points[bat.index + 1];
  const distance = Math.hypot(to.x - from.x, to.y - from.y);
  let duration = (distance / bat.speed) * 1000;
  bat.swoop = 0;
  bat.pause = 0;

  // Why: no random event on the final segment (to the off-screen exit). A dash or swoop
  // there makes the bat shoot out of view in a blink, and it looks like it vanished.
  const isFinalSegment = bat.index === bat.points.length - 2;
  if (!isFinalSegment && Math.random() < bat.eventChance) {
    const kind = Math.floor(random(0, 3));
    if (kind === 0) {
      // Quick swoop: dips down or up on the way, and gets there faster.
      bat.swoop = (Math.random() < 0.5 ? -1 : 1) * random(30, 80);
      duration *= 0.7;
    } else if (kind === 1) {
      // Short hover at the end of the segment.
      bat.pause = random(200, 500);
    } else {
      // Speed change: a dash or a slow drift.
      duration *= Math.random() < 0.5 ? random(0.4, 0.6) : random(1.6, 2.2);
    }
  }
  bat.duration = Math.max(duration, 300);
  bat.elapsed = 0;
  bat.pausing = false;

  // Why: faster flight means faster flapping (shorter time per flap).
  const ratio = (distance / (bat.duration / 1000)) / bat.speed;
  const flap = bat.pause > 0 ? MAX_FLAP : clamp(0.32 / ratio, MIN_FLAP, MAX_FLAP);
  bat.el.style.setProperty("--bat-flap-time", `${flap.toFixed(2)}s`);
}

function updateBat(bat, dt) {
  if (!bat.active) return;
  bat.elapsed += dt;

  if (bat.pausing) {
    if (bat.elapsed >= bat.pause) nextSegment(bat);
    return;
  }
  const t = Math.min(bat.elapsed / bat.duration, 1);
  const from = bat.points[bat.index];
  const to = bat.points[bat.index + 1];
  const e = easeInOut(t);
  const swoop = bat.swoop * Math.sin(Math.PI * t);
  const x = from.x + (to.x - from.x) * e;
  const y = clamp(from.y + (to.y - from.y) * e + swoop, bat.band[0], bat.band[1]);
  bat.el.style.transform = `translate(${x.toFixed(1)}px, ${y.toFixed(1)}px)`;

  if (t >= 1) {
    if (bat.pause > 0) {
      bat.pausing = true;
      bat.elapsed = 0;
    } else {
      nextSegment(bat);
    }
  }
}

function nextSegment(bat) {
  bat.index += 1;
  if (bat.index >= bat.points.length - 1) {
    // Why: if the window was resized wider, the last waypoint can be on screen.
    // Fly on to the edge instead of respawning while the bat is visible.
    const last = bat.points[bat.points.length - 1];
    const gone = bat.leftToRight
      ? last.x >= window.innerWidth
      : last.x + bat.size <= 0;
    if (gone) {
      startCrossing(bat); // fully off-screen: safe to start a new random path
      return;
    }
    const exitX = bat.leftToRight ? window.innerWidth + EDGE_MARGIN : -bat.size - EDGE_MARGIN;
    bat.points.push({ x: exitX, y: last.y });
    startSegment(bat);
  } else {
    startSegment(bat);
  }
}

let bats = [];
let frameId = null;
let lastTime = 0;

function frame(now) {
  // Why: cap dt so a slow frame never makes a bat jump across the screen.
  const dt = Math.min(now - lastTime, 50);
  lastTime = now;
  bats.forEach((bat) => updateBat(bat, dt));
  frameId = requestAnimationFrame(frame);
}

function run() {
  if (frameId !== null) return;
  lastTime = performance.now();
  bats.forEach((bat) => bat.el.querySelectorAll(".bat-wing").forEach((w) => { w.style.animationPlayState = "running"; }));
  frameId = requestAnimationFrame(frame);
}

function stop() {
  if (frameId !== null) cancelAnimationFrame(frameId);
  frameId = null;
  bats.forEach((bat) => bat.el.querySelectorAll(".bat-wing").forEach((w) => { w.style.animationPlayState = "paused"; }));
}

function init() {
  if (motionQuery.matches) return;
  bats = Array.from(document.querySelectorAll(".fx-bat"))
    .slice(0, MAX_BATS)
    .map((el) => ({ el, active: false }));
  // Why: staggered starts, so the bats do not all appear together.
  bats.forEach((bat) => setTimeout(() => startCrossing(bat), random(0, 6000)));
  run();

  // Pause when the tab is hidden to save battery.
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) stop();
    else if (!motionQuery.matches) run();
  });
  // If the user turns reduced motion on later, stop everything and hide the bats.
  motionQuery.addEventListener("change", () => {
    if (motionQuery.matches) {
      stop();
      bats.forEach((bat) => { bat.active = false; bat.el.style.visibility = "hidden"; });
    }
  });
}

init();
