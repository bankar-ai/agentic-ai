/** Client-side-only query history (AGT-027): browser `localStorage`, capped at 20 entries stored,
 * per-device -- deliberately not server-side (agentic-ai has no database of its own, and adding
 * one just for this is a real infra decision not worth making for a "see my past few queries"
 * ask -- see AGT-041 for that piece, once it exists). Every read/write is wrapped in try/catch: a
 * private window, cleared/blocked site data, or any other storage failure must degrade to "no
 * history", never break the query flow itself.
 */
import type { TraceStep } from "./api";
import { subscribeToStorageKey } from "./storageSync";

const STORAGE_KEY = "agentic-ai.history";
const MAX_ENTRIES_STORED = 20;
/** AGT-040: the UI only ever shows the most recent entries -- older ones stay in storage
 * (useful once AGT-041's server-side history exists to reconcile against) but aren't rendered. */
export const MAX_ENTRIES_SHOWN = 5;

export interface HistoryEntry {
  id: string;
  question: string;
  answer: string;
  refused: boolean;
  timestamp: number;
  /** AGT-034/036: which mode produced this entry, and how long it took -- lets the history panel
   * itself double as a Direct-vs-Agentic comparison view. `durationSeconds` is server-reported,
   * not a client-side timer. */
  mode: "agentic" | "direct";
  durationSeconds: number | null;
  /** AGT-040: the full agent trace (agentic mode) so a history entry can be reopened and
   * re-rendered exactly as it looked live, with no network round trip. Empty for direct mode. */
  trace: TraceStep[];
  /** AGT-040: Direct mode's source filename, so a reopened direct-mode entry can show it too. */
  sourceFilename: string | null;
}

export function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    // Entries written before AGT-040 have no `trace`/`sourceFilename` -- default them so older
    // stored history doesn't crash a reopen attempt.
    return parsed.map((entry) => ({
      trace: [],
      sourceFilename: null,
      ...entry,
    }));
  } catch {
    return [];
  }
}

export function appendHistory(entry: Omit<HistoryEntry, "id" | "timestamp">): void {
  try {
    const existing = loadHistory();
    const next: HistoryEntry = { ...entry, id: crypto.randomUUID(), timestamp: Date.now() };
    const trimmed = [next, ...existing].slice(0, MAX_ENTRIES_STORED);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(trimmed));
  } catch {
    // Storage unavailable (private window, blocked site data, quota) -- history is best-effort.
  }
}

export function deleteHistoryEntry(id: string): void {
  try {
    const next = loadHistory().filter((entry) => entry.id !== id);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Same as above -- nothing to recover into.
  }
}

export function clearHistory(): void {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Same as above.
  }
}

/** AGT-044: notifies `onChange` whenever another tab of the same browser appends/deletes/clears
 * history, so this tab's in-memory state doesn't go stale until its next full reload. */
export function subscribeToHistoryChanges(onChange: () => void): () => void {
  return subscribeToStorageKey(STORAGE_KEY, onChange);
}

const DRAFT_KEY = "agentic-ai.draft-query";

/** Preserves an in-progress typed question across a forced logout (AGT-026), so an expired
 * session doesn't silently discard what the user was asking. */
export function saveDraftQuery(query: string): void {
  try {
    if (query) localStorage.setItem(DRAFT_KEY, query);
  } catch {
    // Best-effort only.
  }
}

export function loadAndClearDraftQuery(): string {
  try {
    const draft = localStorage.getItem(DRAFT_KEY) ?? "";
    localStorage.removeItem(DRAFT_KEY);
    return draft;
  } catch {
    return "";
  }
}
