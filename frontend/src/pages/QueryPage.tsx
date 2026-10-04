import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  DocumentsError,
  fetchDocuments,
  runDirectQuery,
  runQuery,
  QueryError,
  type DocumentSummary,
} from "../api";
import { ResultPanel, formatDuration, type DisplayResult } from "../components/ResultPanel";
import { loadCachedDocuments, saveCachedDocuments, subscribeToDocumentsCacheChanges } from "../documentsCache";
import {
  appendHistory,
  clearHistory,
  deleteHistoryEntry,
  loadAndClearDraftQuery,
  loadHistory,
  saveDraftQuery,
  subscribeToHistoryChanges,
  MAX_ENTRIES_SHOWN,
  type HistoryEntry,
} from "../history";
import { decodeJwtExpiry } from "../jwt";
import { useSession } from "../session";

const EXPIRY_WARNING_WINDOW_MS = 5 * 60 * 1000; // AGT-026: warn 5 minutes before the token expires

type Mode = "agentic" | "direct";

function entryToDisplayResult(entry: HistoryEntry): DisplayResult {
  return {
    mode: entry.mode,
    trace: entry.trace,
    answer: entry.answer,
    refused: entry.refused,
    sourceFilename: entry.sourceFilename,
    durationSeconds: entry.durationSeconds,
  };
}

export function QueryPage() {
  const { session, logout } = useSession();
  const navigate = useNavigate();
  const [mode, setMode] = useState<Mode>("agentic");
  const [query, setQuery] = useState(() => loadAndClearDraftQuery());
  const [result, setResult] = useState<DisplayResult | null>(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(() =>
    session ? loadCachedDocuments(session.email) : null
  );
  const [documentsError, setDocumentsError] = useState<string | null>(null);
  const [history, setHistory] = useState<HistoryEntry[]>(() => loadHistory());
  const [expiryWarning, setExpiryWarning] = useState(false);

  // AGT-026: re-checked every 30s rather than once, so the warning appears partway through a
  // long-lived page visit, not only right after login.
  useEffect(() => {
    if (!session) return;
    const check = () => {
      const expiresAt = decodeJwtExpiry(session.accessToken);
      setExpiryWarning(expiresAt !== null && expiresAt - Date.now() < EXPIRY_WARNING_WINDOW_MS);
    };
    check();
    const interval = setInterval(check, 30_000);
    return () => clearInterval(interval);
  }, [session]);

  // AGT-038: the cached list (if any) already rendered synchronously above -- this silently
  // revalidates against the live endpoint and updates the cache, without ever clearing existing
  // content back to empty while the request is in flight.
  useEffect(() => {
    if (!session) return;
    fetchDocuments(session)
      .then((docs) => {
        setDocuments(docs);
        saveCachedDocuments(session.email, docs);
      })
      .catch((err) => setDocumentsError(err instanceof DocumentsError ? err.message : "Could not load documents."));
  }, [session]);

  // AGT-044: another tab of the same browser refreshing its own documents cache (or this user
  // logging in on a second tab) updates this tab's view live, no manual reload needed.
  useEffect(() => {
    if (!session) return;
    return subscribeToDocumentsCacheChanges(session.email, () => {
      setDocuments(loadCachedDocuments(session.email));
    });
  }, [session]);

  // AGT-044: a query appended/deleted/cleared from another tab of the same browser updates this
  // tab's history list live.
  useEffect(() => subscribeToHistoryChanges(() => setHistory(loadHistory())), []);

  if (!session) {
    navigate("/");
    return null;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setSelectedHistoryId(null);
    setLoading(true);
    // Narrowed by the early `if (!session) { navigate(...); return null; }` above -- TS doesn't
    // carry that narrowing into this closure on its own.
    const activeSession = session as NonNullable<typeof session>;
    try {
      let display: DisplayResult;
      if (mode === "direct") {
        const outcome = await runDirectQuery(query, activeSession);
        display = {
          mode: "direct",
          trace: [],
          answer: outcome.text ?? "No matching results found in the knowledge base.",
          refused: outcome.text === null,
          sourceFilename: outcome.sourceFilename,
          durationSeconds: outcome.durationSeconds,
        };
      } else {
        const outcome = await runQuery(query, activeSession);
        display = {
          mode: "agentic",
          trace: outcome.trace,
          answer:
            outcome.refused || !outcome.finalAnswer
              ? "The system could not produce a grounded answer and refused to guess."
              : outcome.finalAnswer,
          refused: outcome.refused,
          sourceFilename: null,
          durationSeconds: outcome.durationSeconds,
        };
      }
      setResult(display);
      appendHistory({
        question: query,
        answer: display.answer,
        refused: display.refused,
        mode: display.mode,
        durationSeconds: display.durationSeconds,
        trace: display.trace,
        sourceFilename: display.sourceFilename,
      });
      setHistory(loadHistory());
    } catch (err) {
      if (err instanceof QueryError && err.message.includes("expired")) {
        saveDraftQuery(query);
        logout();
        navigate("/");
        return;
      }
      setError(err instanceof QueryError ? err.message : "Query failed -- please try again.");
    } finally {
      setLoading(false);
    }
  }

  function handleOpenHistoryEntry(entry: HistoryEntry) {
    setError(null);
    setResult(entryToDisplayResult(entry));
    setSelectedHistoryId(entry.id);
  }

  function handleDeleteHistoryEntry(id: string) {
    deleteHistoryEntry(id);
    setHistory(loadHistory());
    if (selectedHistoryId === id) {
      setSelectedHistoryId(null);
      setResult(null);
    }
  }

  function handleClearHistory() {
    clearHistory();
    setHistory([]);
    setSelectedHistoryId(null);
  }

  const shownHistory = history.slice(0, MAX_ENTRIES_SHOWN);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white px-6 py-3">
        <div className="mx-auto flex max-w-3xl flex-wrap items-center justify-between gap-3">
          <span className="text-lg font-semibold text-slate-900">Agentic RAG Orchestration</span>
          <nav className="flex items-center gap-1" role="tablist" aria-label="Query mode">
            {(["agentic", "direct"] as Mode[]).map((m) => (
              <button
                key={m}
                type="button"
                role="tab"
                aria-selected={mode === m}
                onClick={() => setMode(m)}
                className={`border-b-2 px-3 py-1.5 text-sm font-medium transition-colors ${
                  mode === m
                    ? "border-slate-900 text-slate-900"
                    : "border-transparent text-slate-500 hover:text-slate-900"
                }`}
              >
                {m === "agentic" ? "Agentic RAG" : "Direct RAG"}
              </button>
            ))}
          </nav>
          <div className="flex items-center gap-3">
            <Link
              to="/about"
              title="What is this?"
              className="flex h-6 w-6 items-center justify-center rounded-full border border-slate-300 text-xs font-semibold text-slate-500 hover:bg-slate-100"
            >
              ?
            </Link>
            <span className="truncate text-sm text-slate-500" title={session.email}>
              {session.email}
            </span>
            <button
              type="button"
              onClick={() => {
                logout();
                navigate("/");
              }}
              className="rounded-md bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-700 hover:bg-slate-200"
            >
              Log out
            </button>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl space-y-4 px-6 py-6">
        <p className="text-sm text-slate-500">
          {mode === "agentic"
            ? "Full pipeline: routes, retrieves, drafts, and verifies before answering."
            : "Baseline: one retrieval pass, the top result shown as-is, no synthesis or verification."}
        </p>

        {expiryWarning && (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
            Your session will expire soon -- finish your question, or you'll need to log in again
            (your typed question will be saved for you).
          </p>
        )}

        <details className="rounded-lg border border-slate-200 bg-white px-4 py-3">
          <summary className="cursor-pointer text-sm font-medium text-slate-900">
            Your documents {documents ? `(${documents.length})` : ""}
          </summary>
          {documentsError && <p className="mt-2 text-sm text-red-600">{documentsError}</p>}
          {documents && documents.length === 0 && (
            <p className="mt-2 text-sm text-slate-500">
              No documents yet -- ingest one on <code>enterprise-rag-platform</code> directly, then
              come back here.
            </p>
          )}
          {documents && documents.length > 0 && (
            <ul className="mt-2 divide-y divide-slate-100">
              {documents.map((doc) => (
                <li key={doc.documentId} className="flex items-center gap-2 py-1.5 text-sm">
                  <span className="shrink-0">{"\u{1F4C4}"}</span>
                  <span className="min-w-0 flex-1 truncate text-slate-700">{doc.filename}</span>
                  <span className="shrink-0 text-xs text-slate-400">
                    {new Date(doc.createdAt).toLocaleDateString()}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </details>

        <form onSubmit={handleSubmit} className="flex gap-2">
          <input
            type="text"
            placeholder="Ask a question..."
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            required
            className="flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
          />
          <button
            type="submit"
            disabled={loading}
            className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
          >
            {loading ? "Thinking..." : "Ask"}
          </button>
        </form>

        {error && <p className="text-sm text-red-600">{error}</p>}

        {result && <ResultPanel result={result} />}

        <details className="rounded-lg border border-slate-200 bg-white px-4 py-3" open>
          <summary className="flex cursor-pointer items-center justify-between text-sm font-medium text-slate-900">
            <span>
              Past questions, this browser only ({shownHistory.length}
              {history.length > shownHistory.length ? ` of ${history.length} stored` : ""})
            </span>
            {history.length > 0 && (
              <button
                type="button"
                className="text-xs font-normal text-blue-600 underline hover:text-blue-800"
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  handleClearHistory();
                }}
              >
                Clear all
              </button>
            )}
          </summary>
          {shownHistory.length === 0 && <p className="mt-2 text-sm text-slate-500">No past questions yet.</p>}
          <ul className="mt-2 divide-y divide-slate-100">
            {shownHistory.map((entry) => (
              <li key={entry.id}>
                <div
                  className={`flex items-start justify-between gap-3 rounded-md px-2 py-2 ${
                    selectedHistoryId === entry.id ? "bg-slate-100" : "hover:bg-slate-50"
                  }`}
                >
                  <button
                    type="button"
                    onClick={() => handleOpenHistoryEntry(entry)}
                    className="min-w-0 flex-1 text-left"
                  >
                    <div className="flex flex-wrap items-center gap-1.5">
                      <strong className="truncate text-sm text-slate-900">{entry.question}</strong>
                      <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-600">
                        {entry.mode === "direct" ? "Direct" : "Agentic"}
                      </span>
                      {entry.durationSeconds !== null && (
                        <span className="text-xs text-slate-400">{formatDuration(entry.durationSeconds)}</span>
                      )}
                    </div>
                    <p className="mt-0.5 truncate text-xs text-slate-500">{entry.answer}</p>
                    <span className="text-xs text-slate-400">{new Date(entry.timestamp).toLocaleString()}</span>
                  </button>
                  <button
                    type="button"
                    className="shrink-0 text-xs text-blue-600 underline hover:text-blue-800"
                    onClick={() => handleDeleteHistoryEntry(entry.id)}
                  >
                    Delete
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </details>
      </main>
    </div>
  );
}
