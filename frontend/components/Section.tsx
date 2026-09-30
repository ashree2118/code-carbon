import type { ReactNode } from "react";

type SectionProps = {
  step?: number;
  title: string;
  aside?: ReactNode;
  children: ReactNode;
};

export function Section({ step, title, aside, children }: SectionProps) {
  return (
    <section className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-100 pb-3">
        <h2 className="text-base font-semibold text-zinc-900">
          {step !== undefined && (
            <span className="mr-2 text-zinc-400">{step}.</span>
          )}
          {title}
        </h2>
        {aside}
      </div>
      {children}
    </section>
  );
}

type Tone = "green" | "red" | "amber" | "zinc";

const toneClasses: Record<Tone, string> = {
  green: "bg-emerald-100 text-emerald-800",
  red: "bg-red-100 text-red-800",
  amber: "bg-amber-100 text-amber-800",
  zinc: "bg-zinc-100 text-zinc-700",
};

export function Badge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${toneClasses[tone]}`}
    >
      {children}
    </span>
  );
}

export function Stat({ label, value, title }: { label: string; value: string; title?: string }) {
  return (
    <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3">
      <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">{label}</p>
      <p className="mt-1 text-lg font-semibold text-zinc-900" title={title}>
        {value}
      </p>
    </div>
  );
}
