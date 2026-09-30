"use client";

import { useState } from "react";
import { Section } from "./Section";

type View = "diff" | "optimized" | "original";

function lineClass(line: string): string {
  if (line.startsWith("+++") || line.startsWith("---")) return "text-zinc-500";
  if (line.startsWith("@@")) return "text-sky-700";
  if (line.startsWith("+")) return "bg-emerald-50 text-emerald-900";
  if (line.startsWith("-")) return "bg-red-50 text-red-900";
  return "text-zinc-700";
}

export function CodeChanges({
  step,
  diff,
  originalCode,
  optimizedCode,
}: {
  step: number;
  diff: string;
  originalCode: string;
  optimizedCode: string;
}) {
  const [view, setView] = useState<View>("diff");
  const [copied, setCopied] = useState(false);

  async function copyOptimized() {
    await navigator.clipboard.writeText(optimizedCode);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }

  const tabs: { id: View; label: string }[] = [
    { id: "diff", label: "Diff" },
    { id: "optimized", label: "Optimized" },
    { id: "original", label: "Original" },
  ];

  return (
    <Section
      step={step}
      title="Code changes"
      aside={
        <button
          type="button"
          onClick={copyOptimized}
          className="rounded-md border border-zinc-300 px-3 py-1 text-xs font-medium text-zinc-700 hover:bg-zinc-50"
        >
          {copied ? "Copied" : "Copy optimized code"}
        </button>
      }
    >
      <div className="flex gap-1 rounded-md bg-zinc-100 p-1 text-sm" role="tablist">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={view === tab.id}
            onClick={() => setView(tab.id)}
            className={`flex-1 rounded px-3 py-1.5 font-medium ${
              view === tab.id ? "bg-white text-zinc-900 shadow-sm" : "text-zinc-600 hover:text-zinc-900"
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <pre className="max-h-[32rem] overflow-auto rounded border border-zinc-200 bg-white py-2 font-mono text-xs leading-5">
        <div className="w-max min-w-full">
          {view === "diff"
            ? diff.replace(/\n$/, "").split("\n").map((line, index) => (
                <div key={index} className={`px-3 ${lineClass(line)}`}>
                  {line || " "}
                </div>
              ))
            : (view === "optimized" ? optimizedCode : originalCode).replace(/\n$/, "").split("\n").map((line, index) => (
                <div key={index} className="flex px-3 text-zinc-800">
                  <span className="mr-4 w-8 shrink-0 select-none text-right text-zinc-400">
                    {index + 1}
                  </span>
                  <span>{line || " "}</span>
                </div>
              ))}
        </div>
      </pre>
    </Section>
  );
}
