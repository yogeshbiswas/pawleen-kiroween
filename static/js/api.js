// Talks to the backend. Only the summon stream lives here for now.

export const WATCHDOG_MS = 30000; // Req 7.13: no event for 30 s means the link is dead

// Turns one SSE frame ("event: x\ndata: {...}") into { event, data }.
// Returns null for comment-only or empty frames, or when the data is not JSON.
export function parseFrame(frame) {
  let event = "message";
  const dataLines = [];
  for (const line of frame.split(/\r?\n/)) {
    if (line.startsWith(":")) continue; // SSE comment
    if (line.startsWith("event:")) event = line.slice(6).trim();
    else if (line.startsWith("data:")) dataLines.push(line.slice(5).replace(/^ /, ""));
  }
  if (dataLines.length === 0) return null;
  try {
    return { event, data: JSON.parse(dataLines.join("\n")) };
  } catch {
    return null;
  }
}

// Splits a text buffer into complete frames plus the unfinished rest.
export function splitFrames(buffer) {
  const parts = buffer.split(/\r?\n\r?\n/);
  const rest = parts.pop(); // last piece may be half a frame
  return { frames: parts, rest };
}

// Sends the form and reads the event stream.
// onEvent(type, data) is called for step, heartbeat, result and error.
// Resolves with how it ended: "done", "timeout" (watchdog), "aborted" or "network".
export async function summon(formData, judgePass, onEvent, signal) {
  const controller = new AbortController();
  let timedOut = false;
  let timer = null;

  // Why reset on every event: a heartbeat proves the server is still alive.
  const resetWatchdog = () => {
    clearTimeout(timer);
    timer = setTimeout(() => {
      timedOut = true;
      controller.abort();
    }, WATCHDOG_MS);
  };
  // The caller's signal (back button) also stops the request.
  const onCallerAbort = () => controller.abort();
  if (signal) {
    if (signal.aborted) return "aborted";
    signal.addEventListener("abort", onCallerAbort);
  }

  const headers = {};
  if (judgePass) headers["X-Judge-Pass"] = judgePass; // header only, never the URL

  resetWatchdog();
  try {
    const response = await fetch("/api/summon", {
      method: "POST",
      body: formData,
      headers,
      signal: controller.signal,
    });

    if (!response.ok || !response.body) {
      // Pre-stream errors are plain JSON: {error: {code, message, retry_after_seconds}}
      let info = {};
      try {
        info = (await response.json()).error || {};
      } catch {
        info = {};
      }
      onEvent("error", {
        code: info.code || "temporary_failure",
        message: info.message || "",
        show_chips: false,
        retry_after_seconds: info.retry_after_seconds ?? null,
      });
      return "done";
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      resetWatchdog();
      buffer += decoder.decode(value, { stream: true });
      const { frames, rest } = splitFrames(buffer);
      buffer = rest;
      for (const frame of frames) {
        const parsed = parseFrame(frame);
        if (parsed) onEvent(parsed.event, parsed.data);
      }
    }
    return "done";
  } catch (err) {
    if (timedOut) return "timeout";
    if (err && err.name === "AbortError") return "aborted";
    return "network";
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", onCallerAbort);
  }
}

// ---- Usage and judge pass (task 10.2) ----

export const JUDGE_TIMEOUT_MS = 10000; // Req 11.11

// fetch with a time limit. Why: a silent server must not hang the judge box.
async function fetchWithTimeout(url, options) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), JUDGE_TIMEOUT_MS);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

// Returns { remaining, limit, is_judge, reset_in_seconds }, or null if it failed.
export async function getUsage(judgePass) {
  const headers = {};
  if (judgePass) headers["X-Judge-Pass"] = judgePass;
  try {
    const response = await fetchWithTimeout("/api/usage", { headers });
    if (!response.ok) return null;
    return await response.json();
  } catch {
    return null;
  }
}

// Asks the server if the pass is right. The pass goes in the body, never in a URL.
// Returns one of:
//   { status: "valid", remaining }
//   { status: "invalid" }
//   { status: "locked", retryAfter }   (5 wrong tries, Req 11.10)
//   { status: "failed" }               (timeout or server error, Req 11.11)
export async function checkJudge(pass) {
  try {
    const response = await fetchWithTimeout("/api/judge", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pass }),
    });
    if (response.status === 429) {
      const info = (await response.json()).error || {};
      if (info.code === "judge_locked") {
        return { status: "locked", retryAfter: info.retry_after_seconds ?? 3600 };
      }
      return { status: "failed" };
    }
    if (!response.ok) return { status: "failed" };
    const data = await response.json();
    if (data.valid === true) return { status: "valid", remaining: data.remaining };
    if (data.valid === false) return { status: "invalid" };
    return { status: "failed" };
  } catch {
    return { status: "failed" };
  }
}
