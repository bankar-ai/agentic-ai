/** AGT-038: a `localStorage` cache of the last-fetched documents list, so the panel can render
 * immediately on mount/refresh instead of showing an empty "(0)" flash while `GET /documents` is
 * in flight -- mirrors `enterprise-rag-platform`'s `AuthContext.tsx` pattern of lazy-initializing
 * React state from a synchronously available cached value, then only updating on a successful
 * refetch. Per-user: keyed by email, so switching accounts in the same browser doesn't show the
 * previous account's cached documents.
 */
import type { DocumentSummary } from "./api";
import { subscribeToStorageKey } from "./storageSync";

function storageKey(email: string): string {
  return `agentic-ai.documents-cache.${email}`;
}

export function loadCachedDocuments(email: string): DocumentSummary[] | null {
  try {
    const raw = localStorage.getItem(storageKey(email));
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function saveCachedDocuments(email: string, documents: DocumentSummary[]): void {
  try {
    localStorage.setItem(storageKey(email), JSON.stringify(documents));
  } catch {
    // Best-effort only -- the panel still works from the live fetch, just without the cache.
  }
}

/** AGT-044: a document ingested from another tab/device becomes visible here once that tab's
 * own successful `GET /documents` refresh writes the new cache -- this tab picks it up live
 * rather than only on its next manual reload. */
export function subscribeToDocumentsCacheChanges(email: string, onChange: () => void): () => void {
  return subscribeToStorageKey(storageKey(email), onChange);
}
