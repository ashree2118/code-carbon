# Carbon Footprint Optimizer for Code

Upload a Python file.
The app runs it, measures its energy and CO₂ with CodeCarbon, audits it for wasteful patterns, writes an optimized version, verifies that version, and measures it again.
You then compare real measurements, not guesses.

## How it works

```
Python file
  → run in a subprocess + CodeCarbon measurement
  → AST analysis (finds patterns such as nested loops or string += in a loop)
  → RAG: retrieve matching green coding practices (BM25 keyword search)
  → Auditor (LLM): structured findings, no code changes
  → Optimizer (LLM): targeted changes for those findings
  → Verifier: code changed, compiles, runs, prints the same output
  → run original and optimized alternately, measured the same way
  → comparison of medians (changes under 5% are reported as "no clear change")
```

## Repository layout

- `frontend/` - Next.js (TypeScript, App Router, Tailwind CSS)
- `backend/` - FastAPI
  - `app/api/` - thin HTTP routes
  - `app/services/script_runner.py` - runs code in a subprocess
  - `app/services/measurement_service.py` - wraps a run with CodeCarbon
  - `app/services/rag_service.py` - keyword search over the knowledge base
  - `app/services/ast_analyzer.py` - static pattern detection
  - `app/services/llm_service.py` - the only code that calls the LLM
  - `app/services/auditor.py`, `optimizer.py`, `verifier.py` - the three steps
  - `app/services/comparison_service.py`, `pipeline.py` - measurement comparison and the full flow
  - `app/knowledge_base/practices.json` - the green coding practices

## Prerequisites

- Node.js 20+
- Python 3.11+
- A Groq API key for the audit and optimize steps.
  Running and measuring works without one.
  No model runs on your machine: the LLM runs on Groq, and search is plain keyword matching.

## Run the backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # Windows: copy .env.example .env
# Set GROQ_API_KEY in .env
uvicorn app.main:app --reload --port 8000
```

The API runs at http://localhost:8000.
Interactive docs are at http://localhost:8000/docs.

## Run the frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Open http://localhost:3000.

## API

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | Backend status and whether the LLM is configured |
| POST | `/execute` | Run a `.py` file and measure it |
| POST | `/rag/search` | Search green coding practices: `{"query": "...", "top_k": 3}` |
| POST | `/audit` | Audit a `.py` file without running it |
| POST | `/analyze` | The full flow, returning every step and the comparison |

`/analyze` always returns what it finished.
If a step stops the flow (for example the verifier rejects the optimized code), `stopped_reason` says why.

## Tests and checks

```bash
cd backend && pytest
cd frontend && npm run lint && npm run typecheck
```

Backend tests use a fake LLM, so they need no API key.
RAG tests run the real keyword search against the real knowledge base.
Tests never check exact energy or CO₂ values.

## LLM

The auditor and optimizer call Groq through the official `groq` SDK, in `app/services/llm_service.py`.
Answers use Groq's strict JSON schema mode, so they always match the expected structure.
Only some models support strict mode: `openai/gpt-oss-120b` (default) and `openai/gpt-oss-20b`.
Set `LLM_MODEL` and `LLM_EFFORT` (`low`, `medium`, `high`) in `.env`.

## Measurement notes

- CodeCarbon estimates energy for the whole machine, not one process.
  Measurements are run one at a time so scripts do not count each other's energy.
- On machines without hardware power counters (for example macOS without `powermetrics`), CodeCarbon uses CPU load and a TDP estimate.
  Energy is then mostly proportional to run time.
- CO₂ uses the grid carbon intensity of `CODECARBON_COUNTRY_ISO_CODE`.
- Short scripts are noisy.
  Each version is measured `COMPARISON_RUNS` times, alternating, and medians are compared.

## Safety notes

Uploaded code runs in a separate process with a timeout, capped output, a temporary working directory, and no server secrets in its environment.
This is not a sandbox: the code can still read files the server user can read, and can use the network.
Do not expose this server to untrusted users without running it inside a container.
