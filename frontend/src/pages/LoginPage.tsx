import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { login, LoginError } from "../api";
import { useSession } from "../session";

export function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const { login: setSession } = useSession();
  const navigate = useNavigate();

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      const result = await login(email, password);
      setSession({ accessToken: result.accessToken, csrfToken: result.csrfToken, email });
      navigate("/query");
    } catch (err) {
      setError(err instanceof LoginError ? err.message : "Login failed -- please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <main className="centered">
      <form className="card" onSubmit={handleSubmit}>
        <h1>Agentic RAG Orchestration</h1>
        <p className="subtitle">
          Log in with your own <code>enterprise-rag-platform</code> account. There is no shared
          demo account -- every query runs against your own documents.{" "}
          <Link to="/about">What is this?</Link>
        </p>
        <label htmlFor="email">Email</label>
        <input
          id="email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
        />
        <label htmlFor="password">Password</label>
        <input
          id="password"
          type="password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
        />
        {error && <p className="error">{error}</p>}
        <button type="submit" disabled={submitting}>
          {submitting ? "Logging in..." : "Log in"}
        </button>
      </form>
    </main>
  );
}
