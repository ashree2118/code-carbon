"use client";

import { useState } from "react";
import { executePython, getHealth, type ExecuteResponse } from "@/lib/api";

type BackendStatus = "idle" | "checking" | "ok" | "error";

export default function Home() {
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("idle");
  const [backendMessage, setBackendMessage] = useState("");
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [isExecuting, setIsExecuting] = useState(false);
  const [executeError, setExecuteError] = useState("");
  const [result, setResult] = useState<ExecuteResponse | null>(null);

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
          Phase 2
        </p>
        <h1 className="text-3xl font-semibold tracking-tight text-zinc-900">
          Carbon Footprint Optimizer
        </h1>
        <p className="text-base leading-7 text-zinc-600">
          This system analyzes Python code for energy and carbon efficiency.
          Upload a <code className="rounded bg-zinc-100 px-1 py-0.5 text-sm">.py</code> file
          to run it on the backend. Energy measurement and optimization come in later phases.
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
        <section className="space-y-3 rounded-lg border border-zinc-200 p-4">
          <h2 className="text-sm font-medium text-zinc-900">Execution result</h2>
          <p className={`text-sm ${result.success ? "text-emerald-700" : "text-red-700"}`}>
            Status: {statusLabel}
          </p>
          <p className="text-sm text-zinc-700">
            Exit code: {result.exit_code === null ? "n/a" : result.exit_code}
          </p>
          <p className="text-sm text-zinc-700">
            Execution time: {result.execution_time_seconds} seconds
          </p>
          <div>
            <h3 className="text-sm font-medium text-zinc-900">stdout</h3>
            <pre className="mt-1 overflow-x-auto rounded bg-zinc-100 p-3 text-xs text-zinc-800">
              {result.stdout || "(empty)"}
            </pre>
          </div>
          {result.stderr && (
            <div>
              <h3 className="text-sm font-medium text-zinc-900">stderr</h3>
              <pre className="mt-1 overflow-x-auto rounded bg-zinc-100 p-3 text-xs text-zinc-800">
                {result.stderr}
              </pre>
            </div>
          )}
        </section>
      )}

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
