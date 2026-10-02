/** Client for agentic-ai's own API. Base URL comes from `VITE_API_BASE_URL` (no trailing slash,
 * see `.env.example`), defaulting to the local dev backend.
 */
const API_BASE_URL: string = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export class LoginError extends Error {}
export class QueryError extends Error {}

export interface LoginResult {
  accessToken: string;
  csrfToken: string;
}

/** `POST /auth/login` (AGT-016): proxies a login against `enterprise-rag-platform` and hands
 * back a token pair this SPA can use directly, sidestepping that platform's httpOnly session
 * cookies, which browser JS can never read.
 */
export async function login(email: string, password: string): Promise<LoginResult> {
  const response = await fetch(`${API_BASE_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  });
  if (!response.ok) {
    throw new LoginError("Invalid email or password.");
  }
  const body = await response.json();
  return { accessToken: body.access_token, csrfToken: body.csrf_token };
}

export interface TraceStep {
  agent?: string;
  [key: string]: unknown;
}

export interface QueryResult {
  trace: TraceStep[];
  finalAnswer: string | null;
  refused: boolean;
}

/** `POST /query`: runs the agent graph and returns its full trace + result, delivered as one
 * SSE response once the graph finishes (not incrementally -- see AGT-008). Parsed here as a
 * whole response rather than streamed, since there is nothing to show incrementally yet.
 */
export async function runQuery(query: string, session: LoginResult): Promise<QueryResult> {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${session.accessToken}`,
      "X-RAG-CSRF-Token": session.csrfToken,
    },
    body: JSON.stringify({ query }),
  });
  if (response.status === 401) {
    throw new QueryError("Your session has expired -- please log in again.");
  }
  if (!response.ok) {
    throw new QueryError(`Query failed (${response.status}).`);
  }

  const text = await response.text();
  const trace: TraceStep[] = [];
  let finalAnswer: string | null = null;
  let refused = false;

  for (const block of text.split("\n\n")) {
    if (!block.trim()) continue;
    const eventMatch = block.match(/^event: (.+)$/m);
    const dataMatch = block.match(/^data: (.+)$/m);
    if (!eventMatch || !dataMatch) continue;
    const event = eventMatch[1];
    const data = JSON.parse(dataMatch[1]);
    if (event === "step") {
      trace.push(data);
    } else if (event === "result") {
      finalAnswer = data.final_answer;
      refused = data.refused;
    } else if (event === "error") {
      throw new QueryError(data.message ?? "Query failed.");
    }
  }

  return { trace, finalAnswer, refused };
}
