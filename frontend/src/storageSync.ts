/** AGT-044: live-sync `localStorage`-backed state across tabs of the same browser. The browser's
 * `storage` event fires in *other* tabs whenever `localStorage` changes (never in the tab that
 * made the change), so a query run in one tab can push an update into every other open tab
 * without requiring a manual reload. Cross-device sync is a separate, larger piece (AGT-041) --
 * this only ever reaches other tabs of the same browser.
 */
export function subscribeToStorageKey(key: string, onChange: () => void): () => void {
  function handler(event: StorageEvent) {
    if (event.key === key || event.key === null) onChange();
  }
  window.addEventListener("storage", handler);
  return () => window.removeEventListener("storage", handler);
}
