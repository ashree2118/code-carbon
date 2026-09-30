import type { ReactNode } from "react";
import type { ComparisonResult, MetricComparison } from "@/lib/api";
import { formatCo2, formatEnergy, formatSeconds } from "@/lib/format";
import { Badge, Section } from "./Section";

const verdictStyle = {
  lower: { tone: "green", label: "Lower" },
  higher: { tone: "red", label: "Higher" },
  no_clear_change: { tone: "zinc", label: "No clear change" },
  unavailable: { tone: "zinc", label: "Unavailable" },
} as const;

const gridClass = "grid grid-cols-3 gap-x-4 gap-y-1 sm:grid-cols-[1.2fr_1fr_1fr_1.4fr]";

function Cell({ caption, children }: { caption: string; children: ReactNode }) {
  return (
    <div className="min-w-0">
      <p className="text-[11px] uppercase tracking-wider text-zinc-500 sm:hidden">{caption}</p>
      {children}
    </div>
  );
}

function Row({
  label,
  metric,
  format,
}: {
  label: string;
  metric: MetricComparison;
  format: (value: number | null) => string;
}) {
  const verdict = verdictStyle[metric.verdict];
  const change =
    metric.change_percent === null
      ? ""
      : `${metric.change_percent > 0 ? "+" : ""}${metric.change_percent}%`;
  return (
    <div className={`${gridClass} items-start border-t sm:items-center border-zinc-100 py-2.5 text-sm`}>
      <p className="col-span-3 font-medium text-zinc-900 sm:col-span-1">{label}</p>
      <Cell caption="Original">
        <p className="font-mono text-zinc-700">{format(metric.original)}</p>
      </Cell>
      <Cell caption="Optimized">
        <p className="font-mono text-zinc-700">{format(metric.optimized)}</p>
      </Cell>
      <Cell caption="Change">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <Badge tone={verdict.tone}>{verdict.label}</Badge>
          <span className="font-mono text-xs text-zinc-500">{change}</span>
        </div>
      </Cell>
    </div>
  );
}

export function Comparison({ step, comparison }: { step: number; comparison: ComparisonResult }) {
  return (
    <Section step={step} title="Original vs optimized">
      <div>
        <div
          className={`${gridClass} hidden pb-2 text-xs font-medium uppercase tracking-wider text-zinc-500 sm:grid`}
        >
          <p>Metric</p>
          <p>Original</p>
          <p>Optimized</p>
          <p>Change</p>
        </div>
        <Row label="Execution time" metric={comparison.execution_time} format={formatSeconds} />
        <Row label="Energy" metric={comparison.energy} format={formatEnergy} />
        <Row label="CO₂ emissions" metric={comparison.co2} format={formatCo2} />
      </div>
      <p className="text-sm leading-6 text-zinc-700">{comparison.summary}</p>
      <p className="text-xs leading-5 text-zinc-500">
        Values are medians of {comparison.runs_per_version} alternating runs per version, measured
        with CodeCarbon. CodeCarbon estimates energy for the whole machine, so short scripts are
        noisy. Changes under 5% are shown as &ldquo;no clear change&rdquo;.
      </p>
    </Section>
  );
}
