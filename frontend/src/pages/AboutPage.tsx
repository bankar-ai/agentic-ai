import { Link } from "react-router-dom";

export function AboutPage() {
  return (
    <main className="centered">
      <div className="card about-card">
        <h1>About This App</h1>
        <p>
          This is an <strong>agentic RAG orchestration</strong> demo: a question you ask here runs
          through a graph of four agents --
        </p>
        <ol>
          <li><strong>Gatekeeper</strong> -- decides whether to search the knowledge base, fall back to the web, or refuse</li>
          <li><strong>Research</strong> -- retrieves evidence from your <code>enterprise-rag-platform</code> documents</li>
          <li><strong>Writer</strong> -- drafts a cited answer from that evidence</li>
          <li><strong>Verifier</strong> -- checks the draft against the evidence and rejects fabricated citations, looping back to Research if it fails</li>
        </ol>
        <p>
          <strong>What you need:</strong> a real <code>enterprise-rag-platform</code> account with
          content already ingested on it. There is no shared demo account -- every query runs
          against your own documents, and an account with nothing ingested will have nothing to
          find.
        </p>
        <p>
          <strong>What this app does not do:</strong> it cannot upload or ingest documents for
          you. Do that directly on <code>enterprise-rag-platform</code> first, then come back here
          to ask questions about them.
        </p>
        <p>
          <strong>Query history</strong> shown here is stored only in this browser (not synced
          across devices) and you can delete it any time from the query page.
        </p>
        <Link to="/">&larr; Back to login</Link>
      </div>
    </main>
  );
}
