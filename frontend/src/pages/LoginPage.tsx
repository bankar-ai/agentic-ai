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
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <form
        className="flex w-full max-w-sm flex-col gap-3 rounded-lg border border-slate-200 bg-white p-8 shadow-sm"
        onSubmit={handleSubmit}
      >
        <h1 className="text-xl font-semibold text-slate-900">Agentic RAG Orchestration</h1>
        <p className="text-sm text-slate-500">
          Log in with your own <code>enterprise-rag-platform</code> account. There is no shared
          demo account -- every query runs against your own documents.{" "}
          <Link to="/about" className="text-blue-600 underline hover:text-blue-800">
            What is this?
          </Link>
        </p>
        <label htmlFor="email" className="text-sm font-medium text-slate-700">
          Email
        </label>
        <input
          id="email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        <label htmlFor="password" className="text-sm font-medium text-slate-700">
          Password
        </label>
        <input
          id="password"
          type="password"
          required
          value={password}
          onChange={(event) => setPassword(event.target.value)}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />
        {error && <p className="text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={submitting}
          className="mt-2 rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-60"
        >
          {submitting ? "Logging in..." : "Log in"}
        </button>
      </form>
    </main>
  );
}
