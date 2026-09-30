const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type HealthResponse = {
  status: string;
  message: string;
  llm_configured: boolean;
};

export type CarbonMetrics = {
  energy_kwh: number;
  co2_kg: number;
};

export type ExecuteResponse = {
  success: boolean;
  stdout: string;
  stderr: string;
  exit_code: number | null;
  execution_time_seconds: number;
  timed_out: boolean;
  carbon: CarbonMetrics | null;
  carbon_error: string | null;
};

export type PracticeResult = {
  id: string;
  title: string;
  content: string;
  category: string;
  relevance_score: number;
};

export type RAGSearchResponse = {
  query: string;
  results: PracticeResult[];
};

export type Severity = "low" | "medium" | "high";

export type DetectedPattern = {
  kind: string;
  line_start: number;
  line_end: number;
  description: string;
};

export type AuditFinding = {
  line_start: number;
  line_end: number;
  issue: string;
  explanation: string;
  severity: Severity;
  green_practice: string;
  suggestion: string;
};

export type AuditResponse = {
  summary: string;
  findings: AuditFinding[];
  detected_patterns: DetectedPattern[];
  practices: PracticeResult[];
};

export type OptimizationResult = {
  optimized_code: string;
  explanation: string;
  changes: { finding: string; description: string }[];
};

export type VerificationCheck = {
  name: string;
  status: "passed" | "failed" | "skipped";
  detail: string;
};

export type VerificationResult = {
  passed: boolean;
  checks: VerificationCheck[];
};

export type MeasurementSummary = {
  execution_time_seconds: number;
  energy_kwh: number | null;
  co2_kg: number | null;
};

export type MetricComparison = {
  original: number | null;
  optimized: number | null;
  change_percent: number | null;
  verdict: "lower" | "higher" | "no_clear_change" | "unavailable";
};

export type ComparisonResult = {
  runs_per_version: number;
  original: MeasurementSummary;
  optimized: MeasurementSummary;
  execution_time: MetricComparison;
  energy: MetricComparison;
  co2: MetricComparison;
  summary: string;
};

export type AnalyzeResponse = {
  original_code: string;
  original_execution: ExecuteResponse;
  audit: AuditResponse | null;
  optimization: OptimizationResult | null;
  verification: VerificationResult | null;
  optimized_execution: ExecuteResponse | null;
  comparison: ComparisonResult | null;
  diff: string | null;
  stopped_reason: string | null;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function readErrorMessage(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data.detail)) {
      return data.detail
        .map((item: { msg?: string }) => item.msg)
        .filter(Boolean)
        .join("; ");
    }
  } catch {
    // Fall back to a status-based message.
  }
  return `Request failed (${response.status})`;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, init);
  } catch {
    throw new ApiError(
      "Could not reach the backend. Check that FastAPI is running.",
      0,
    );
  }
  if (!response.ok) {
    throw new ApiError(await readErrorMessage(response), response.status);
  }
  return response.json();
}

function fileForm(file: File): FormData {
  const formData = new FormData();
  formData.append("file", file);
  return formData;
}

export function getHealth(): Promise<HealthResponse> {
  return request("/health");
}

export function executePython(file: File): Promise<ExecuteResponse> {
  return request("/execute", { method: "POST", body: fileForm(file) });
}

export function analyzePython(file: File): Promise<AnalyzeResponse> {
  return request("/analyze", { method: "POST", body: fileForm(file) });
}

export function searchPractices(
  query: string,
  topK = 3,
): Promise<RAGSearchResponse> {
  return request("/rag/search", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ query, top_k: topK }),
  });
}
