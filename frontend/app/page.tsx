"use client";

import { useState } from "react";
import {
  executePython,
  getHealth,
  searchRAGPractices,
  type ExecuteResponse,
  type PracticeResult,
} from "@/lib/api";

type BackendStatus = "idle" | "checking" | "ok" | "error";

export default function Home() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("idle");
  const [backendMessage, setBackendMessage] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executeError, setExecuteError] = useState("");
  const [result, setResult] = useState<ExecuteResponse | null>(null);

  // RAG Search State
  const [ragQuery, setRagQuery] = useState("");
  const [isSearchingRag, setIsSearchingRag] = useState(false);
  const [ragError, setRagError] = useState("");
  const [ragResults, setRagResults] = useState<PracticeResult[] | null>(null);

  async function handleCheckBackend() {
    setBackendStatus("checking");
    setBackendMessage("");

    try {
      const data = await getHealth();
      setBackendStatus("ok");
      setBackendMessage(data.message);
    } catch {
      setBackendStatus("error");
      setBackendMessage("Backend is not reachable. Start the FastAPI server and try again.");
    }
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    setSelectedFile(file);
    setResult(null);
    setExecuteError("");
  }

  async function handleExecute() {
    if (!selectedFile) {
      return;
    }

    setIsExecuting(true);
    setExecuteError("");
    setResult(null);

    try {
      const data = await executePython(selectedFile);
      setResult(data);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "Could not reach the backend. Check that FastAPI is running.";
      setExecuteError(message);
    } finally {
      setIsExecuting(false);
    }
  }

  async function handleRagSearch(e?: React.FormEvent) {
    if (e) e.preventDefault();
    if (!ragQuery.trim()) return;

    setIsSearchingRag(true);
    setRagError("");
    setRagResults(null);

    try {
      const data = await searchRAGPractices(ragQuery);
      setRagResults(data.results);
    } catch (error) {
      const message =
        error instanceof Error
          ? error.message
          : "RAG search failed. Ensure backend and vector store are active.";
      setRagError(message);
    } finally {
      setIsSearchingRag(false);
    }
  }

  const statusLabel = result
    ? result.timed_out
      ? "Timed out"
      : result.success
        ? "Succeeded"
        : "Failed"
    : null;

  return (
    <main className="mx-auto flex min-h-full w-full max-w-2xl flex-col gap-8 px-6 py-16">
      <header className="space-y-3">
        <p className="text-sm font-medium uppercase tracking-wide text-emerald-700">
          Phase 4
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
          Carbon Footprint Optimizer
        </h1>
        <p className="text-base leading-7 text-zinc-600">
          This system analyzes Python code for energy and carbon efficiency, and retrieves green coding practices using ChromaDB RAG.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-zinc-900">Upload Python file</h2>
        <div className="rounded-lg border border-dashed border-zinc-300 bg-zinc-50 px-4 py-6">
          <input
            type="file"
            accept=".py"
            onChange={handleFileChange}
            className="block w-full text-sm text-zinc-700 file:mr-3 file:rounded file:border-0 file:bg-emerald-700 file:px-3 file:py-1.5 file:text-sm file:font-medium file:text-white hover:file:bg-emerald-800"
          />
          <p className="mt-3 text-sm text-zinc-600">
            {selectedFile ? `Selected: ${selectedFile.name}` : "No file selected."}
          </p>
        </div>
        <button
          type="button"
          onClick={handleExecute}
          disabled={!selectedFile || isExecuting}
          className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isExecuting ? "Executing..." : "Execute Python"}
        </button>
        {executeError && <p className="text-sm text-red-700">{executeError}</p>}
      </section>

      {result && (
        <section className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
          <div className="flex items-center justify-between border-b border-zinc-100 pb-3">
            <h2 className="text-base font-semibold text-zinc-900">Carbon Report</h2>
            <span
              className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                result.timed_out
                  ? "bg-amber-100 text-amber-800"
                  : result.success
                    ? "bg-emerald-100 text-emerald-800"
                    : "bg-red-100 text-red-800"
              }`}
            >
              Status: {statusLabel}
            </span>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3">
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Energy Consumed
              </p>
              <p className="mt-1 text-lg font-semibold text-zinc-900">
                {result.carbon && result.carbon.energy_kwh !== null
                  ? `${result.carbon.energy_kwh.toExponential(4)} kWh`
                  : "Unavailable"}
              </p>
            </div>

            <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3">
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                CO₂ Emissions
              </p>
              <p className="mt-1 text-lg font-semibold text-zinc-900">
                {result.carbon && result.carbon.co2_kg !== null
                  ? `${result.carbon.co2_kg.toExponential(4)} kg`
                  : "Unavailable"}
              </p>
            </div>

            <div className="rounded-lg border border-zinc-100 bg-zinc-50 p-3">
              <p className="text-xs font-medium uppercase tracking-wider text-zinc-500">
                Execution Time
              </p>
              <p className="mt-1 text-lg font-semibold text-zinc-900">
                {result.execution_time_seconds} s
              </p>
            </div>
          </div>

          <div className="space-y-3 pt-2 border-t border-zinc-100">
            <p className="text-xs font-medium text-zinc-600">
              Exit Code:{" "}
              <span className="font-mono text-zinc-900">
                {result.exit_code === null ? "n/a" : result.exit_code}
              </span>
            </p>

            <div>
              <h3 className="text-xs font-medium uppercase tracking-wider text-zinc-700">stdout</h3>
              <pre className="mt-1 max-h-48 overflow-auto rounded bg-zinc-950 p-3 text-xs font-mono text-zinc-100">
                {result.stdout || "(empty)"}
              </pre>
            </div>

            {result.stderr && (
              <div>
                <h3 className="text-xs font-medium uppercase tracking-wider text-red-700">stderr</h3>
                <pre className="mt-1 max-h-48 overflow-auto rounded border border-red-200 bg-red-950/5 p-3 text-xs font-mono text-red-800">
                  {result.stderr}
                </pre>
              </div>
            )}
          </div>
        </section>
      )}

      {/* RAG Knowledge Base Search Section */}
      <section className="space-y-4 rounded-lg border border-zinc-200 bg-white p-5 shadow-sm">
        <h2 className="text-base font-semibold text-zinc-900">
          Green Coding Knowledge Base (RAG)
        </h2>
        <p className="text-sm text-zinc-600">
          Search the vector database for green coding recommendations relevant to code patterns or efficiency queries.
        </p>

        <form onSubmit={handleRagSearch} className="flex gap-2">
          <input
            type="text"
            value={ragQuery}
            onChange={(e) => setRagQuery(e.target.value)}
            placeholder="e.g. nested loops and repeated calculations"
            className="flex-1 rounded-md border border-zinc-300 px-3.5 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-emerald-600 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!ragQuery.trim() || isSearchingRag}
            className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSearchingRag ? "Searching..." : "Search RAG"}
          </button>
        </form>

        {ragError && <p className="text-sm text-red-700">{ragError}</p>}

        {ragResults && (
          <div className="space-y-3 pt-3 border-t border-zinc-100">
            <h3 className="text-sm font-medium text-zinc-900">
              Top Relevant Practices ({ragResults.length})
            </h3>
            {ragResults.length === 0 ? (
              <p className="text-sm text-zinc-500">No matching practices found.</p>
            ) : (
              <div className="space-y-3">
                {ragResults.map((item, idx) => (
                  <div
                    key={idx}
                    className="rounded-lg border border-zinc-200 bg-zinc-50/50 p-4 space-y-1.5"
                  >
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-emerald-800 bg-emerald-100 px-2 py-0.5 rounded-full">
                        {item.category}
                      </span>
                      <span className="text-xs font-mono text-zinc-500">
                        Score: {item.relevance_score}
                      </span>
                    </div>
                    <h4 className="text-sm font-semibold text-zinc-900">
                      {item.title}
                    </h4>
                    <p className="text-xs leading-relaxed text-zinc-600">
                      {item.content}
                    </p>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="text-sm font-medium text-zinc-900">Backend connection</h2>
        <button
          type="button"
          onClick={handleCheckBackend}
          disabled={backendStatus === "checking"}
          className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium text-zinc-800 hover:bg-zinc-50 disabled:cursor-wait disabled:opacity-70"
        >
          {backendStatus === "checking" ? "Checking..." : "Check Backend"}
        </button>
        {backendStatus === "ok" && (
          <p className="text-sm text-emerald-700">Backend reachable: {backendMessage}</p>
        )}
        {backendStatus === "error" && (
          <p className="text-sm text-red-700">{backendMessage}</p>
        )}
      </section>
    </main>
  );
}

