"use client";

import { useEffect, useState } from "react";
import { AuditReport } from "@/components/AuditReport";
import { CodeChanges } from "@/components/CodeChanges";
import { Comparison } from "@/components/Comparison";
import { ExecutionResult } from "@/components/ExecutionResult";
import { Optimization, Verification } from "@/components/Optimization";
import { PracticeSearch } from "@/components/PracticeSearch";
import {
  analyzePython,
  executePython,
  getHealth,
  type AnalyzeResponse,
  type ExecuteResponse,
  type HealthResponse,
} from "@/lib/api";

type Health = { state: "checking" } | { state: "ok"; data: HealthResponse } | { state: "down" };
type Busy = "idle" | "running" | "analyzing";

export default function Home() {
  const [health, setHealth] = useState<Health>({ state: "checking" });
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState<Busy>("idle");
  const [error, setError] = useState("");
  const [runResult, setRunResult] = useState<ExecuteResponse | null>(null);
  const [analysis, setAnalysis] = useState<AnalyzeResponse | null>(null);

  useEffect(() => {
    getHealth()
      .then((data) => setHealth({ state: "ok", data }))
      .catch(() => setHealth({ state: "down" }));
  }, []);

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    setFile(event.target.files?.[0] ?? null);
    setRunResult(null);
    setAnalysis(null);
    setError("");
  }

  async function handle(kind: Exclude<Busy, "idle">) {
    if (!file) return;
    setBusy(kind);
    setError("");
    setRunResult(null);
    setAnalysis(null);
    try {
      if (kind === "running") {
        setRunResult(await executePython(file));
      } else {
        setAnalysis(await analyzePython(file));
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Something went wrong.");
    } finally {
      setBusy("idle");
    }
  }

  const llmReady = health.state === "ok" && health.data.llm_configured;

  return (
    <main className="mx-auto flex min-h-full w-full max-w-3xl flex-col gap-6 px-4 py-12 sm:px-6">
      <header className="space-y-3">
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
          Carbon Footprint Optimizer
        </h1>
        <p className="text-base leading-7 text-zinc-600">
          Upload a Python file. It is run and measured with CodeCarbon, audited for wasteful
          patterns, optimized, verified, and measured again so you can compare real numbers.
        </p>
        <HealthLine health={health} />
      </header>

      <section className="space-y-3 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <label htmlFor="python-file" className="text-sm font-medium text-zinc-900">
          Python file
        </label>
        <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50 px-4 py-5">
          <input
            id="python-file"
            type="file"
            accept=".py"
            onChange={handleFileChange}
            className="block w-full text-sm text-zinc-700 file:mr-3 file:rounded file:border-0 file:bg-emerald-700 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-emerald-800"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => handle("analyzing")}
            disabled={!file || busy !== "idle" || !llmReady}
            className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "analyzing" ? "Analyzing..." : "Analyze and optimize"}
          </button>
          <button
            type="button"
            onClick={() => handle("running")}
            disabled={!file || busy !== "idle"}
            className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "running" ? "Running..." : "Run and measure only"}
          </button>
        </div>
        {busy === "analyzing" && (
          <p className="text-sm text-zinc-600">
            Running the code, auditing, optimizing, verifying, and measuring both versions. This
            usually takes one to three minutes.
          </p>
        )}
        {error && <p className="text-sm text-red-700">{error}</p>}
      </section>

      {runResult && <ExecutionResult title="Execution and carbon report" result={runResult} />}
      {analysis && <AnalysisResults analysis={analysis} />}

      <PracticeSearch />
    </main>
  );
}

function HealthLine({ health }: { health: Health }) {
  if (health.state === "checking") {
    return <p className="text-sm text-zinc-500">Checking backend...</p>;
  }
  if (health.state === "down") {
    return (
      <p className="text-sm text-red-700">
        Backend is not reachable. Start the FastAPI server and reload the page.
      </p>
    );
  }
  if (!health.data.llm_configured) {
    return (
      <p className="text-sm text-amber-800">
        Backend is running, but the LLM is not configured. Set GROQ_API_KEY in backend/.env
        to enable analysis. Running and measuring still works.
      </p>
    );
  }
  return <p className="text-sm text-emerald-700">Backend and LLM are ready.</p>;
}

function AnalysisResults({ analysis }: { analysis: AnalyzeResponse }) {
  let step = 0;
  const next = () => ++step;

  return (
    <>
      {analysis.stopped_reason && (
        <p
          role="status"
          className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900"
        >
          {analysis.stopped_reason}
        </p>
      )}
      <ExecutionResult step={next()} title="Original run" result={analysis.original_execution} />
      {analysis.audit && <AuditReport step={next()} audit={analysis.audit} />}
      {analysis.optimization && (
        <Optimization step={next()} optimization={analysis.optimization} />
      )}
      {analysis.verification && (
        <Verification step={next()} verification={analysis.verification} />
      )}
      {analysis.optimization && analysis.diff !== null && (
        <CodeChanges
          step={next()}
          diff={analysis.diff}
          originalCode={analysis.original_code}
          optimizedCode={analysis.optimization.optimized_code}
        />
      )}
      {analysis.optimized_execution && (
        <ExecutionResult step={next()} title="Optimized run" result={analysis.optimized_execution} />
      )}
      {analysis.comparison && <Comparison step={next()} comparison={analysis.comparison} />}
    </>
  );
}
