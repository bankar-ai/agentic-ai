# Frontend

Vite + React + TypeScript SPA for the Agentic RAG Orchestration project (`AGT-017`). A real login
page, separate from the Gradio demo (which is kept as-is, side by side, for its original
Direct-vs-Agentic comparison purpose).

Two routes: `/` (login) and `/query` (ask a question, see the agent trace and final answer). The
session (`{access_token, csrf_token}`) lives in memory only (React state) -- never
`localStorage`/`sessionStorage` -- so it's lost on refresh, same stance as the Gradio UI.

## Local development

```
cp .env.example .env.local   # set VITE_API_BASE_URL to your local backend, e.g. http://localhost:8000
npm install
npm run dev
```

Type-check with `npx tsc -b`, lint with `npm run lint`.

## Deployment (Vercel)

Import this repo into Vercel, set the project root to `frontend/`, and set the
`VITE_API_BASE_URL` environment variable to the live backend's URL (the Cloud Run service, see
`gcp-deployment-tracker.md`). Vercel auto-detects the Vite framework preset.

The backend must also have this frontend's deployed Vercel origin in its `CORS_ALLOWED_ORIGINS`
env var (see `app/core/cors.py`), or every request will be blocked by the browser regardless of
what the API itself would allow.

## Why login goes through the backend, not `enterprise-rag-platform` directly

`enterprise-rag-platform`'s own `POST /auth/login` delivers tokens as httpOnly cookies
(`ERP-116`) -- unreadable by this SPA's own JS. This frontend instead calls `agentic-ai`'s own
`POST /auth/login` (`AGT-016`), which does that cookie-jar read server-side and hands back a
plain `{access_token, csrf_token}` JSON body this SPA can use directly as
`Authorization`/`X-RAG-CSRF-Token` headers on `POST /query`.
