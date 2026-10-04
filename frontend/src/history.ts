/** Client-side-only query history (AGT-027): browser `localStorage`, capped at 20 entries,
 * per-device -- deliberately not server-side (agentic-ai has no database of its own, and adding
 * one just for this is a real infra decision not worth making for a "see my past few queries"
 * ask). Every read/write is wrapped in try/catch: a private window, cleared/blocked site data,
 * or any other storage failure must degrade to "no history", never break the query flow itself.
 */

const STORAGE_KEY = "agentic-ai.history";
const MAX_ENTRIES = 20;

export interface HistoryEntry {
  id: string;
  question: string;
  answer: string;
  refused: boolean;
  timestamp: number;
}

export function loadHistory(): HistoryEntry[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

export function appendHistory(entry: Omit<HistoryEntry, "id" | "timestamp">): void {
  try {
    const existing = loadHistory();
    const next: HistoryEntry = { ...entry, id: crypto.randomUUID(), timestamp: Date.now() };
    const trimmed = [next, ...existing].slice(0, MAX_ENTRIES);
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
