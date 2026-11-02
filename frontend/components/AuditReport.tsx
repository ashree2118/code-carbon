import type { AuditResponse, PracticeResult, Severity } from "@/lib/api";
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
          Static analysis (AST): {audit.detected_patterns.length} patterns
        </summary>
        {audit.detected_patterns.length === 0 ? (
          <p className="mt-2 text-sm text-zinc-500">None found.</p>
        ) : (
          <ul className="mt-2 space-y-1 text-sm text-zinc-700">
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
      </details>
    </Section>
  );
}

const retrieverLabel: Record<string, string> = {
  vector: "semantic search (Sentence Transformers + ChromaDB)",
  keyword: "keyword search (BM25 fallback)",
};

export function describeRetriever(retriever: string): string {
  return retrieverLabel[retriever] ?? retriever;
}

export function PracticeCard({ practice }: { practice: PracticeResult }) {
  return (
    <li className="space-y-1.5 rounded-lg border border-zinc-200 p-4">
      <div className="flex items-center justify-between gap-2">
        <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
          {practice.category}
        </span>
        <span className="font-mono text-xs text-zinc-500">
          Relevance {practice.relevance_score.toFixed(2)}
        </span>
      </div>
      <h3 className="text-sm font-semibold text-zinc-900">{practice.title}</h3>
      <p className="text-xs leading-relaxed text-zinc-600">{practice.content}</p>
    </li>
  );
}

export function GreenPractices({ step, audit }: { step: number; audit: AuditResponse }) {
  return (
    <Section
      step={step}
      title="Relevant green coding practices"
      aside={<Badge tone="zinc">{audit.practices.length} retrieved</Badge>}
    >
      <p className="text-xs text-zinc-500">
        Retrieved from the knowledge base by {describeRetriever(audit.retriever)} and given to the
        auditor and optimizer.
      </p>
      {audit.practices.length === 0 ? (
        <p className="text-sm text-zinc-500">No practice matched the detected patterns.</p>
      ) : (
        <ul className="space-y-3">
          {audit.practices.map((practice) => (
            <PracticeCard key={practice.id} practice={practice} />
          ))}
        </ul>
      )}
    </Section>
  );
}
