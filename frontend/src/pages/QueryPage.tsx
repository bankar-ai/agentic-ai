import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { runQuery, QueryError, type QueryResult } from "../api";
import { useSession } from "../session";

export function QueryPage() {
  const { session, logout } = useSession();
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [result, setResult] = useState<QueryResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

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
    } catch (err) {
      if (err instanceof QueryError && err.message.includes("expired")) {
        logout();
        navigate("/");
        return;
      }
      setError(err instanceof QueryError ? err.message : "Query failed -- please try again.");
    } finally {
      setLoading(false);
    }
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
        your own <code>enterprise-rag-platform</code> documents.
      </p>

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
    </main>
  );
}
