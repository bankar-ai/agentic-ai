import { Link } from "react-router-dom";

export function AboutPage() {
  return (
    <main className="flex min-h-screen items-center justify-center bg-slate-50 p-4">
      <div className="flex w-full max-w-xl flex-col gap-3 rounded-lg border border-slate-200 bg-white p-8 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900">About This App</h1>
        <p className="text-sm text-slate-600">
          This is an <strong>agentic RAG orchestration</strong> demo: a question you ask here runs
          through a graph of four agents --
        </p>
        <ol className="list-decimal space-y-1 pl-5 text-sm text-slate-600">
          <li>
            <strong>Gatekeeper</strong> -- decides whether to search the knowledge base, fall back
            to the web, or refuse
          </li>
          <li>
            <strong>Research</strong> -- retrieves evidence from your{" "}
            <code>enterprise-rag-platform</code> documents
          </li>
          <li>
            <strong>Writer</strong> -- drafts a cited answer from that evidence
          </li>
          <li>
            <strong>Verifier</strong> -- checks the draft against the evidence and rejects
            fabricated citations, looping back to Research if it fails
          </li>
        </ol>
        <p className="text-sm text-slate-600">
          <strong>Direct RAG mode</strong> (the toggle on the query page) skips all of that: one
          retrieval pass, the single top-ranked chunk shown exactly as stored, no synthesis, no
          verification. It's the baseline the agentic pipeline above is compared against -- ask the
          same question in both modes to see what the extra steps actually buy you.
        </p>
        <p className="text-sm text-slate-600">
          <strong>What you need:</strong> a real <code>enterprise-rag-platform</code> account with
          content already ingested on it. There is no shared demo account -- every query runs
          against your own documents, and an account with nothing ingested will have nothing to
          find.
        </p>
        <p className="text-sm text-slate-600">
          <strong>What this app does not do:</strong> it cannot upload or ingest documents for you.
          Do that directly on <code>enterprise-rag-platform</code> first, then come back here to
          ask questions about them.
        </p>
        <p className="text-sm text-slate-600">
          <strong>Query history</strong> shown here is stored only in this browser (not synced
          across devices) and you can delete it any time from the query page.
        </p>
        <Link to="/" className="text-sm text-blue-600 underline hover:text-blue-800">
          &larr; Back to login
        </Link>
      </div>
    </main>
  );
}
