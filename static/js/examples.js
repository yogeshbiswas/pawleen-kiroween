// Haunted Hall of Fame: loads up to 3 example results from /static/examples/.
// Why load in JS: a missing file must show nothing (no broken-image icon).
const EXAMPLES = [
  { file: "example-1.png", caption: "Wizard pup, spell cast" },
  { file: "example-2.png", caption: "Gothic bird of the night" },
  { file: "example-3.png", caption: "Pumpkin pet on patrol" },
];

const panel = document.getElementById("hall-panel");
const list = document.getElementById("hall-list");

function loadExample(example) {
  return new Promise((resolve) => {
    const img = new Image();
    img.onload = () => resolve({ example, img });
    img.onerror = () => resolve(null); // missing file: skip it quietly
    img.alt = `Example result: ${example.caption}`;
    img.src = `/static/examples/${example.file}`;
  });
}

async function showExamples() {
  if (!panel || !list) return;
  const found = (await Promise.all(EXAMPLES.map(loadExample))).filter(Boolean);
  for (const { example, img } of found) {
    const item = document.createElement("li");
    const figure = document.createElement("figure");
    figure.className = "rounded-lg border border-witch/40 bg-black/40 p-2";
    img.className = "w-full rounded-md object-contain";
    const caption = document.createElement("figcaption");
    caption.className = "mt-1 text-sm text-witch-light";
    caption.textContent = example.caption;
    figure.append(img, caption);
    item.append(figure);
    list.append(item);
  }
  // Why: with no examples the whole panel stays hidden.
  panel.hidden = found.length === 0;
}

showExamples();
