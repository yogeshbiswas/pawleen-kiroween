// Haunted_Gallery storage. Everything stays in this browser (IndexedDB);
// nothing here talks to the backend (Req 9.14).
//
// Manual check (no JS test runner):
//  1. Make two spells. Open the gallery: newest first, with name and date.
//  2. Reload the page: same images, same order.
//  3. Open one, press Delete, choose "Keep it": nothing changes.
//  4. Delete again, choose "Banish": only that one disappears.
//  5. "Clear my whole gallery" + "Banish": the empty message appears.
//  6. Console: costumeNameFor("", "  ") must return "Mystery costume".

const DB_NAME = "pawleen";
const STORE = "spells";
const DB_VERSION = 1;
const FALLBACK_NAME = "Mystery costume";

// Name rule (Req 9.1, 4.16): typed description, else the Gatekeeper's name, else the fallback.
export function costumeNameFor(description, gatekeeperName) {
  const typed = (description || "").trim();
  if (typed) return typed;
  const fromGatekeeper = (gatekeeperName || "").trim();
  return fromGatekeeper || FALLBACK_NAME;
}

// Opens the database. Rejects when IndexedDB is missing or blocked (e.g. private mode).
function openDb() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") {
      reject(new Error("IndexedDB is unavailable"));
      return;
    }
    let request;
    try {
      request = indexedDB.open(DB_NAME, DB_VERSION);
    } catch (err) {
      reject(err);
      return;
    }
    request.onupgradeneeded = () => {
      const db = request.result;
      if (!db.objectStoreNames.contains(STORE)) {
        const store = db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
        store.createIndex("savedAt", "savedAt");
      }
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
    request.onblocked = () => reject(new Error("IndexedDB is blocked"));
  });
}

// Runs one transaction and resolves when it has fully committed.
// Why wait for "complete": a quota error can show up at commit time, not on the request.
async function withStore(mode, work) {
  const db = await openDb();
  try {
    return await new Promise((resolve, reject) => {
      const tx = db.transaction(STORE, mode);
      let result;
      tx.oncomplete = () => resolve(result);
      tx.onerror = () => reject(tx.error);
      tx.onabort = () => reject(tx.error || new Error("Transaction aborted"));
      result = work(tx.objectStore(STORE), (value) => {
        result = value;
      });
    });
  } finally {
    db.close();
  }
}

// Saves one spell and returns its id.
export function saveSpell({ blob, costumeName }) {
  const record = { blob, costumeName: costumeNameFor("", costumeName), savedAt: Date.now() };
  return withStore("readwrite", (store, setResult) => {
    const request = store.add(record);
    request.onsuccess = () => setResult(request.result);
  });
}

// All spells, newest first. Same-millisecond saves fall back to the higher id.
export async function listSpells() {
  const all = await withStore("readonly", (store, setResult) => {
    const request = store.getAll();
    request.onsuccess = () => setResult(request.result);
  });
  return all.sort((a, b) => b.savedAt - a.savedAt || b.id - a.id);
}

export function deleteSpell(id) {
  return withStore("readwrite", (store) => {
    store.delete(id);
  });
}

export function clearAll() {
  return withStore("readwrite", (store) => {
    store.clear();
  });
}
