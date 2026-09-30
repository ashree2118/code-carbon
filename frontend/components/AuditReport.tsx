import type { AuditResponse, Severity } from "@/lib/api";
import { Badge, Section } from "./Section";

const severityTone = { high: "red", medium: "amber", low: "zinc" } as const satisfies Record<
  Severity,
  "red" | "amber" | "zinc"
>;

function lines(start: number, end: number): string {
  return start === end ? `Line ${start}` : `Lines ${start}–${end}`;
}

export function AuditReport({ step, audit }: { step: number; audit: AuditResponse }) {
  return (
    <Section
      step={step}
      title="Code audit"
      aside={<Badge tone="zinc">{audit.findings.length} findings</Badge>}
    >
      <p className="text-sm leading-6 text-zinc-700">{audit.summary}</p>

      {audit.findings.length > 0 && (
        <ul className="space-y-3">
          {audit.findings.map((finding, index) => (
            <li key={index} className="space-y-2 rounded-lg border border-zinc-200 p-4">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={severityTone[finding.severity]}>{finding.severity}</Badge>
                <span className="font-mono text-xs text-zinc-500">
                  {lines(finding.line_start, finding.line_end)}
                </span>
              </div>
              <h3 className="text-sm font-semibold text-zinc-900">{finding.issue}</h3>
              <p className="text-sm leading-6 text-zinc-600">{finding.explanation}</p>
              <p className="text-sm leading-6 text-zinc-800">
                <span className="font-medium">Suggestion:</span> {finding.suggestion}
              </p>
              <p className="text-xs text-emerald-800">Practice: {finding.green_practice}</p>
            </li>
          ))}
        </ul>
      )}

      <details className="group rounded-lg border border-zinc-100 bg-zinc-50 px-4 py-3">
        <summary className="cursor-pointer text-sm font-medium text-zinc-700">
          Static analysis ({audit.detected_patterns.length} patterns) and retrieved practices (
          {audit.practices.length})
        </summary>
        <div className="mt-3 space-y-4">
          <div>
            <h4 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              AST patterns
            </h4>
            {audit.detected_patterns.length === 0 ? (
              <p className="mt-1 text-sm text-zinc-500">None found.</p>
            ) : (
              <ul className="mt-1 space-y-1 text-sm text-zinc-700">
                {audit.detected_patterns.map((pattern, index) => (
                  <li key={index}>
                    <span className="font-mono text-xs text-zinc-500">
                      {lines(pattern.line_start, pattern.line_end)}
                    </span>{" "}
                    {pattern.description}
                  </li>
                ))}
              </ul>
            )}
          </div>
          <div>
            <h4 className="text-xs font-medium uppercase tracking-wider text-zinc-500">
              Green coding practices
            </h4>
            <ul className="mt-1 space-y-1 text-sm text-zinc-700">
              {audit.practices.map((practice) => (
                <li key={practice.id}>
                  {practice.title}{" "}
                  <span className="font-mono text-xs text-zinc-500">
                    ({practice.relevance_score.toFixed(2)})
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </details>
    </Section>
  );
}
