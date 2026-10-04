import { useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { DocumentsError, fetchDocuments, runQuery, QueryError, type DocumentSummary, type QueryResult } from "../api";
import {
  appendHistory,
  clearHistory,
  deleteHistoryEntry,
  loadAndClearDraftQuery,
  loadHistory,
  saveDraftQuery,
  type HistoryEntry,
} from "../history";
import { decodeJwtExpiry } from "../jwt";
import { useSession } from "../session";

const EXPIRY_WARNING_WINDOW_MS = 5 * 60 * 1000; // AGT-026: warn 5 minutes before the token expires

export function QueryPage() {
  const { session, logout } = useSession();
  const navigate = useNavigate();
  const [query, setQuery] = useState(() => loadAndClearDraftQuery());
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [documents, setDocuments] = useState<DocumentSummary[] | null>(null);
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

  useEffect(() => {
    if (!session) return;
    fetchDocuments(session)
      .then(setDocuments)
      .catch((err) => setDocumentsError(err instanceof DocumentsError ? err.message : "Could not load documents."));
  }, [session]);

  if (!session) {
    navigate("/");
    return null;
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setResult(null);
    setLoading(true);
    try {
      // Narrowed by the early `if (!session) { navigate(...); return null; }` above -- TS
      // doesn't carry that narrowing into this closure on its own.
      const outcome = await runQuery(query, session as NonNullable<typeof session>);
      setResult(outcome);
      appendHistory({
        question: query,
        answer: outcome.refused || !outcome.finalAnswer ? "(refused)" : outcome.finalAnswer,
        refused: outcome.refused,
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

  function handleDeleteHistoryEntry(id: string) {
    deleteHistoryEntry(id);
    setHistory(loadHistory());
  }

  function handleClearHistory() {
    clearHistory();
    setHistory([]);
  }

  return (
    <main className="query-page">
      <header className="query-header">
        <span>Logged in as {session.email}</span>
        <button
          type="button"
          onClick={() => {
            logout();
            navigate("/");
          }}
        >
          Log out
        </button>
      </header>

      <p className="subtitle">
        Runs the full Gatekeeper -&gt; Research -&gt; Writer -&gt; Verifier agent graph against
        your own <code>enterprise-rag-platform</code> documents. <Link to="/about">What is this?</Link>
      </p>

      {expiryWarning && (
        <p className="warning">
          Your session will expire soon -- finish your question, or you'll need to log in again
          (your typed question will be saved for you).
        </p>
      )}

      <details className="documents-panel">
        <summary>Your documents {documents ? `(${documents.length})` : ""}</summary>
        {documentsError && <p className="error">{documentsError}</p>}
        {documents && documents.length === 0 && (
          <p className="subtitle">
            No documents yet -- ingest one on <code>enterprise-rag-platform</code> directly, then
            come back here.
          </p>
        )}
        {documents && documents.length > 0 && (
          <ul className="documents-list">
            {documents.map((doc) => (
              <li key={doc.documentId}>
                {doc.filename} <span className="subtitle">({new Date(doc.createdAt).toLocaleDateString()})</span>
              </li>
            ))}
          </ul>
        )}
      </details>

      <form onSubmit={handleSubmit} className="query-form">
        <input
          type="text"
          placeholder="Ask a question..."
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          required
        />
        <button type="submit" disabled={loading}>
          {loading ? "Thinking..." : "Ask"}
        </button>
      </form>

      {error && <p className="error">{error}</p>}

      {result && (
        <section className="result">
          {result.trace.length > 0 && (
            <details open>
              <summary>Agent trace</summary>
              <ol>
                {result.trace.map((step, index) => (
                  <li key={index}>
                    <strong>{step.agent ?? "?"}</strong>: {JSON.stringify(step)}
                  </li>
                ))}
              </ol>
            </details>
          )}
          <p className="answer">
            {result.refused || !result.finalAnswer
              ? "The system could not produce a grounded answer and refused to guess."
              : result.finalAnswer}
          </p>
        </section>
      )}

      <details className="history-panel">
        <summary>
          Past questions, this browser only ({history.length}){" "}
          {history.length > 0 && (
            <button
              type="button"
              className="link-button"
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
        {history.length === 0 && <p className="subtitle">No past questions yet.</p>}
        <ul className="history-list">
          {history.map((entry) => (
            <li key={entry.id}>
              <div>
                <strong>{entry.question}</strong>
                <p className="subtitle">{entry.answer}</p>
                <span className="subtitle">{new Date(entry.timestamp).toLocaleString()}</span>
              </div>
              <button type="button" className="link-button" onClick={() => handleDeleteHistoryEntry(entry.id)}>
                Delete
              </button>
            </li>
          ))}
        </ul>
      </details>
    </main>
  );
}
