import { useState } from "react";
import type { TraceStep } from "../api";

/** AGT-039: renders an agentic run's trace as a vertical stepper instead of raw JSON -- one node
 * per agent step, collapsed to a one-line summary by default, expandable for the full detail. A
 * retry loop (Verifier rejects, Research/Writer run again) gets a visible "Retry" divider rather
 * than reading as a continuation of the same flat list, since a two-rejection run was previously
 * indistinguishable from a single long trace at a glance.
 */

const AGENT_LABELS: Record<string, string> = {
  gatekeeper: "Gatekeeper",
  research: "Research",
  writer: "Writer",
  verifier: "Verifier",
};

const AGENT_ICONS: Record<string, string> = {
  gatekeeper: "\u{1F6AA}", // door
  research: "\u{1F50D}", // magnifying glass
  writer: "\u{1F4DD}", // memo
  verifier: "⚖️", // scales
};

function summarize(step: TraceStep): string {
  switch (step.agent) {
    case "gatekeeper":
      return `Routed to "${String(step.route ?? "?")}"`;
    case "research":
      return `Retrieved ${String(step.evidence_count ?? "?")} evidence chunk(s)`;
    case "writer": {
      const text = typeof step.text === "string" ? step.text : "";
      return text.length > 100 ? `${text.slice(0, 100)}...` : text || "Drafted an answer";
    }
    case "verifier":
      return step.grounded ? "Grounded ✓" : "Rejected ✗";
    default:
      return step.agent ?? "Step";
  }
}

function StepDetail({ step }: { step: TraceStep }) {
  switch (step.agent) {
    case "gatekeeper":
      return <p className="text-sm text-slate-600">{String(step.reasoning ?? "")}</p>;
    case "research":
      return (
        <p className="text-sm text-slate-600">
          {String(step.evidence_count ?? "?")} evidence chunk(s) pulled from your documents.
        </p>
      );
    case "writer":
      return <p className="text-sm whitespace-pre-wrap text-slate-600">{String(step.text ?? "")}</p>;
    case "verifier": {
      const claims = Array.isArray(step.unsupported_claims) ? (step.unsupported_claims as string[]) : [];
      return (
        <div className="space-y-2">
          <p className="text-sm text-slate-600">{String(step.reasoning ?? "")}</p>
          {claims.length > 0 && (
            <div>
              <p className="text-xs font-medium tracking-wide text-slate-400 uppercase">
                Unsupported claims
              </p>
              <ul className="mt-1 list-disc space-y-0.5 pl-5 text-sm text-red-700">
                {claims.map((claim, i) => (
                  <li key={i}>{claim}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      );
    }
    default:
      return <pre className="text-xs text-slate-500">{JSON.stringify(step, null, 2)}</pre>;
  }
}

export function TraceStepper({ trace }: { trace: TraceStep[] }) {
  const [openIndex, setOpenIndex] = useState<number | null>(null);

  return (
    <ol className="space-y-1">
      {trace.map((step, index) => {
        const agent = step.agent ?? "?";
        // A "research" step that isn't the trace's first step starts a new retry round.
        const isRetryStart = agent === "research" && index > 0;
        const isOpen = openIndex === index;
        return (
          <li key={index}>
            {isRetryStart && (
              <div className="my-2 flex items-center gap-2 text-xs font-medium text-amber-600">
                <span className="h-px flex-1 bg-amber-200" />
                Retry
                <span className="h-px flex-1 bg-amber-200" />
              </div>
            )}
            <button
              type="button"
              onClick={() => setOpenIndex(isOpen ? null : index)}
              className="flex w-full items-start gap-2 rounded-md px-2 py-1.5 text-left hover:bg-slate-100"
            >
              <span className="shrink-0 text-base leading-5">{AGENT_ICONS[agent] ?? "●"}</span>
              <span className="min-w-0 flex-1">
                <span className="font-medium text-slate-900">{AGENT_LABELS[agent] ?? agent}</span>
                <span className="ml-2 truncate text-sm text-slate-500">{summarize(step)}</span>
              </span>
              <span className="shrink-0 text-xs text-slate-400">{isOpen ? "▲" : "▼"}</span>
            </button>
            {isOpen && <div className="mt-1 ml-8 border-l border-slate-200 pl-3">
              <StepDetail step={step} />
            </div>}
          </li>
        );
      })}
    </ol>
  );
}
