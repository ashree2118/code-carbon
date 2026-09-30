import type { ExecuteResponse } from "@/lib/api";
import { formatCo2, formatEnergy, formatSeconds } from "@/lib/format";
import { Badge, Section, Stat } from "./Section";

type ExecutionResultProps = {
  step?: number;
  title: string;
  result: ExecuteResponse;
};

export function ExecutionResult({ step, title, result }: ExecutionResultProps) {
  const status = result.timed_out
    ? { tone: "amber" as const, label: "Timed out" }
    : result.success
      ? { tone: "green" as const, label: "Succeeded" }
      : { tone: "red" as const, label: "Failed" };

  return (
    <Section step={step} title={title} aside={<Badge tone={status.tone}>{status.label}</Badge>}>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <Stat label="Execution time" value={formatSeconds(result.execution_time_seconds)} />
        <Stat
          label="Energy"
          value={formatEnergy(result.carbon?.energy_kwh ?? null)}
          title={result.carbon ? `${result.carbon.energy_kwh} kWh` : undefined}
        />
        <Stat
          label="CO₂"
          value={formatCo2(result.carbon?.co2_kg ?? null)}
          title={result.carbon ? `${result.carbon.co2_kg} kg` : undefined}
        />
      </div>
      {result.carbon_error && (
        <p className="text-sm text-amber-800">Carbon data unavailable: {result.carbon_error}</p>
      )}

      <p className="text-xs font-medium text-zinc-600">
        Exit code:{" "}
        <span className="font-mono text-zinc-900">{result.exit_code ?? "n/a"}</span>
      </p>
      <Output label="stdout" text={result.stdout || "(empty)"} />
      {result.stderr && <Output label="stderr" text={result.stderr} error />}
    </Section>
  );
}

function Output({ label, text, error = false }: { label: string; text: string; error?: boolean }) {
  return (
    <div>
      <h3
        className={`text-xs font-medium uppercase tracking-wider ${error ? "text-red-700" : "text-zinc-700"}`}
      >
        {label}
      </h3>
      <pre
        className={`mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded p-3 font-mono text-xs ${
          error ? "border border-red-200 bg-red-50 text-red-800" : "bg-zinc-950 text-zinc-100"
        }`}
      >
        {text}
      </pre>
    </div>
  );
}
