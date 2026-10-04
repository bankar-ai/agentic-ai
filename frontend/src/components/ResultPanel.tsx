import type { TraceStep } from "../api";
import { TraceStepper } from "./TraceStepper";

export interface DisplayResult {
  mode: "agentic" | "direct";
  trace: TraceStep[];
  answer: string;
  refused: boolean;
  sourceFilename: string | null;
  durationSeconds: number | null;
}

export function formatDuration(seconds: number | null): string {
  if (seconds === null) return "";
  return seconds < 1 ? `${Math.round(seconds * 1000)}ms` : `${seconds.toFixed(1)}s`;
}

/** AGT-039: the final answer is the visual headline (a Grounded/Refused verdict badge for
 * Agentic mode, same prominence for Direct's answer), with the trace as supporting detail below
 * it -- previously the answer was a plain paragraph with no more visual weight than the trace.
 * Shared between a live query's result and a reopened history entry (AGT-040), since both render
 * the exact same shape.
 */
export function ResultPanel({ result }: { result: DisplayResult }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-semibold text-slate-700">
          {result.mode === "agentic" ? "Agentic RAG" : "Direct RAG"}
        </span>
        {result.mode === "agentic" && (
          <span
            className={`rounded-full px-2.5 py-0.5 text-xs font-semibold ${
              result.refused ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"
            }`}
          >
            {result.refused ? "Refused ✗" : "Grounded ✓"}
          </span>
        )}
        {result.durationSeconds !== null && (
          <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
            {formatDuration(result.durationSeconds)}
          </span>
        )}
      </div>

      <p className="text-base leading-relaxed text-slate-900">{result.answer}</p>
      {result.sourceFilename && (
        <p className="mt-1 text-xs text-slate-400">source: {result.sourceFilename}</p>
      )}

      {result.trace.length > 0 && (
        <details className="mt-4 border-t border-slate-100 pt-3" open>
          <summary className="cursor-pointer text-xs font-medium tracking-wide text-slate-400 uppercase">
            Agent trace
          </summary>
          <div className="mt-2">
            <TraceStepper trace={result.trace} />
          </div>
        </details>
      )}
    </section>
  );
}
