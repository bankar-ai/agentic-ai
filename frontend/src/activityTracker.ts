// AGT-055: idle-timeout tracking, mirroring enterprise-rag-platform's own
// (frontend/src/lib/activityTracker.ts) -- that platform's silent-refresh-on-401 flow already
// checks this before refreshing, closing the "no timed logout" gap a 30-day refresh-token
// lifetime otherwise leaves open; agentic-ai's own backend calls /auth/refresh directly,
// server-to-server, and never runs that platform's frontend JS, so it never inherited this
// protection automatically once AGT-051 made token expiry invisible to this frontend.

const LAST_ACTIVITY_KEY = "agentic-ai.last-activity";
// Matches enterprise-rag-platform's own threshold (and its access_token_expire_minutes) -- no
// reason for agentic-ai's idle cutoff to differ from the platform whose session this actually is.
export const IDLE_TIMEOUT_MS = 30 * 60 * 1000;

/** Reads/writes are best-effort -- a private-browsing/storage-blocked browser just falls back to
 * never idle-timing-out, same degrade-gracefully pattern used throughout this project's other
 * localStorage helpers (history.ts, documentsCache.ts). */
export function recordActivity(): void {
  try {
    localStorage.setItem(LAST_ACTIVITY_KEY, String(Date.now()));
  } catch {
    // best-effort only
  }
}

function getLastActivityAt(): number | null {
  try {
    const raw = localStorage.getItem(LAST_ACTIVITY_KEY);
    return raw ? Number(raw) : null;
  } catch {
    return null;
  }
}

/** `false` (never idle-timed-out) if no activity has been recorded yet -- a page that never
 * calls `startActivityTracking` must not accidentally look idle. */
export function isIdleTimedOut(): boolean {
  const lastActivityAt = getLastActivityAt();
  if (lastActivityAt === null) return false;
  return Date.now() - lastActivityAt > IDLE_TIMEOUT_MS;
}

let tracking = false;

/** Registers a one-time, throttled global listener for real user interaction (click/keydown) --
 * safe to call multiple times (e.g. on every QueryPage mount); only attaches once per page load.
 * Also records activity immediately, so a fresh login never starts "idle". */
export function startActivityTracking(): void {
  recordActivity();
  if (tracking) return;
  tracking = true;
  const listener = () => recordActivity();
  window.addEventListener("click", listener);
  window.addEventListener("keydown", listener);
}
