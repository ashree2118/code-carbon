"use client";

import { useState } from "react";
import { searchPractices, type RAGSearchResponse } from "@/lib/api";
import { describeRetriever, PracticeCard } from "./AuditReport";

export function PracticeSearch() {
  const [query, setQuery] = useState("");
  const [isSearching, setIsSearching] = useState(false);
  const [error, setError] = useState("");
  const [results, setResults] = useState<RAGSearchResponse | null>(null);

  async function handleSearch(event: React.FormEvent) {
    event.preventDefault();
    if (!query.trim()) return;

    setIsSearching(true);
    setError("");
    try {
      const data = await searchPractices(query);
      setResults(data);
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
          (results.results.length === 0 ? (
            <p className="text-sm text-zinc-500">No matching practices found.</p>
          ) : (
            <>
              <p className="text-xs text-zinc-500">Found by {describeRetriever(results.retriever)}.</p>
              <ul className="space-y-3">
                {results.results.map((item) => (
                  <PracticeCard key={item.id} practice={item} />
                ))}
              </ul>
            </>
          ))}
      </div>
    </details>
  );
}
