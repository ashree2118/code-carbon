"use client";

import { useState } from "react";
import { searchPractices, type PracticeResult } from "@/lib/api";

export function PracticeSearch() {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<PracticeResult[] | null>(null);

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setError("");
    try {
      const data = await searchPractices(query);
      setResults(data.results);
    } catch (err) {
      setResults(null);
      setError(err instanceof Error ? err.message : "Search failed.");
    } finally {
      setIsSearching(false);
    }
  }

  return (
    <details className="rounded-lg border border-zinc-200 bg-white px-5 py-4 shadow-sm">
      <summary className="cursor-pointer text-sm font-semibold text-zinc-900">
        Search green coding practices
      </summary>
      <div className="mt-4 space-y-4">
        <form onSubmit={handleSearch} className="flex gap-2">
          <input
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. string concatenation in a loop"
            aria-label="Search query"
            className="min-w-0 flex-1 rounded-md border border-zinc-300 px-3.5 py-2 text-sm text-zinc-900 placeholder:text-zinc-400 focus:border-emerald-600 focus:outline-none"
          />
          <button
            type="submit"
            disabled={!query.trim() || isSearching}
            className="rounded-md bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-800 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {isSearching ? "Searching..." : "Search"}
          </button>
        </form>

        {error && <p className="text-sm text-red-700">{error}</p>}

        {results &&
          (results.length === 0 ? (
            <p className="text-sm text-zinc-500">No matching practices found.</p>
          ) : (
            <ul className="space-y-3">
              {results.map((item) => (
                <li key={item.id} className="space-y-1.5 rounded-lg border border-zinc-200 p-4">
                  <div className="flex items-center justify-between gap-2">
                    <span className="rounded-full bg-emerald-100 px-2 py-0.5 text-xs font-semibold text-emerald-800">
                      {item.category}
                    </span>
                    <span className="font-mono text-xs text-zinc-500">
                      Relevance {item.relevance_score.toFixed(2)}
                    </span>
                  </div>
                  <h3 className="text-sm font-semibold text-zinc-900">{item.title}</h3>
                  <p className="text-xs leading-relaxed text-zinc-600">{item.content}</p>
                </li>
              ))}
            </ul>
          ))}
      </div>
    </details>
  );
}
