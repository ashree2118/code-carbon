import type { OptimizationResult, VerificationResult } from "@/lib/api";
import { Badge, Section } from "./Section";

export function Optimization({
  step,
  optimization,
}: {
  step: number;
  optimization: OptimizationResult;
}) {
  return (
    <Section step={step} title="Optimization">
      <p className="text-sm leading-6 text-zinc-700">{optimization.explanation}</p>
      {optimization.changes.length > 0 && (
        <ul className="list-disc space-y-1 pl-5 text-sm leading-6 text-zinc-700">
          {optimization.changes.map((change, index) => (
            <li key={index}>
              <span className="font-medium text-zinc-900">{change.finding}:</span>{" "}
              {change.description}
            </li>
          ))}
        </ul>
      )}
    </Section>
  );
}

const statusTone = { passed: "green", failed: "red", skipped: "zinc" } as const;

const checkLabels: Record<string, string> = {
  changed: "Code changed",
  syntax: "Valid syntax",
  runs: "Runs without errors",
  output_matches: "Same output as original",
};

export function Verification({
  step,
  verification,
}: {
  step: number;
  verification: VerificationResult;
}) {
  return (
    <Section
      step={step}
      title="Verification"
      aside={
        <Badge tone={verification.passed ? "green" : "red"}>
          {verification.passed ? "Accepted" : "Rejected"}
        </Badge>
      }
    >
      <ul className="divide-y divide-zinc-100">
        {verification.checks.map((check) => (
          <li key={check.name} className="flex flex-col gap-1 py-2 sm:flex-row sm:gap-4">
            <div className="flex w-56 shrink-0 items-center gap-2">
              <Badge tone={statusTone[check.status]}>{check.status}</Badge>
              <span className="text-sm font-medium text-zinc-900">
                {checkLabels[check.name] ?? check.name}
              </span>
            </div>
            <p className="whitespace-pre-wrap break-words text-sm text-zinc-600">
              {check.detail}
            </p>
          </li>
        ))}
      </ul>
    </Section>
  );
}
