# Carbon Footprint Optimizer for Code

Upload a Python file.
The app runs it, measures its energy and CO₂ with CodeCarbon, audits it for wasteful patterns, writes an optimized version, verifies that version, and measures it again.
You then compare real measurements, not guesses.

## How it works

```
Python file
  → run in a fresh Docker container + CodeCarbon measurement
  → AST analysis (finds patterns such as nested loops or string += in a loop)
  → RAG: retrieve matching green coding practices
        (Sentence Transformers embeddings in ChromaDB, queried through LangChain)
  → Auditor (LLM): structured findings, no code changes
  → Optimizer (LLM): targeted changes for those findings
  → Verifier: code changed, compiles, runs, prints the same output
  → run original and optimized alternately, measured the same way
  → comparison of medians (changes under 5% are reported as "no clear change")
```

The steps after the first measurement run as a LangGraph state graph (`app/services/pipeline.py`).
A step that cannot continue sets `stopped_reason` and the graph routes straight to the end.

## Repository layout

- `frontend/` - Next.js (TypeScript, App Router, Tailwind CSS)
- `backend/` - FastAPI
  - `app/api/` - thin HTTP routes
  - `app/services/script_runner.py` - runs code (Docker or subprocess backend)
  - `app/services/docker_sandbox.py` - single-use, locked-down containers
  - `app/services/measurement_service.py` - wraps a run with CodeCarbon
  - `app/services/rag_service.py` - retrieval: `vector_retriever.py` (ChromaDB + LangChain), `keyword_retriever.py` (BM25 fallback)
  - `app/services/ast_analyzer.py` - static pattern detection
  - `app/services/llm_service.py` - the only code that calls the LLM
  - `app/services/auditor.py`, `optimizer.py`, `verifier.py` - the three steps
  - `app/services/comparison_service.py` - measurement comparison
  - `app/services/pipeline.py` - the full flow as a LangGraph graph
  - `app/knowledge_base/practices.json` - the green coding practices

## Prerequisites

- Node.js 20+
- Python 3.11+
- Docker (running). Uploaded code runs in containers from `python:3.12-slim`, pulled on first use.
  For local development without Docker, set `EXECUTION_SANDBOX=subprocess` (not a security sandbox).
- A Groq API key for the audit and optimize steps.
  Running and measuring works without one.
- The embedding model (`all-MiniLM-L6-v2`, about 90 MB) downloads on first start.
  If it cannot load, retrieval falls back to BM25 keyword search and responses say so (`retriever: "keyword"`).

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
RAG tests run both real retrievers (vector and keyword) against the real knowledge base.
Docker tests in `tests/test_docker_sandbox.py` are skipped when Docker is not running; other tests use the subprocess backend.
Tests never check exact energy or CO₂ values.

## LLM

The auditor and optimizer call Groq through the official `groq` SDK, in `app/services/llm_service.py`.
Answers use Groq's strict JSON schema mode, so they always match the expected structure.
Only some models support strict mode: `openai/gpt-oss-120b` (default) and `openai/gpt-oss-20b`.
Set `LLM_MODEL` and `LLM_EFFORT` (`low`, `medium`, `high`) in `.env`.

## Measurement notes

- CodeCarbon estimates energy for the whole machine, not one process.
  Only one script runs at a time (measured or not), so scripts do not count each other's energy.
- Container startup is never measured: each container is started before tracking begins, and the script is sent to a worker already waiting inside it.
- On Windows, CodeCarbon reads the Windows Energy Meter Interface for CPU energy. RAM energy is an estimate proportional to run time.
- Very short scripts (well under a second) are dominated by interpreter startup and measurement noise; small differences between them are not meaningful.
- On machines without hardware power counters (for example macOS without `powermetrics`), CodeCarbon uses CPU load and a TDP estimate.
  Energy is then mostly proportional to run time.
- CO₂ uses the grid carbon intensity of `CODECARBON_COUNTRY_ISO_CODE`.
- Short scripts are noisy.
  Each version is measured `COMPARISON_RUNS` times, alternating, and medians are compared.

## Safety notes

With `EXECUTION_SANDBOX=docker` (the default), every script runs in its own new container that is removed afterwards.
The container has no network, a read-only root filesystem, memory, CPU and process limits, and runs the script as `nobody` with no capabilities.
Server environment variables and files are not visible to it.

With `EXECUTION_SANDBOX=subprocess`, the script runs as a host process with a timeout, capped output, a temporary working directory and no server secrets in its environment.
That is not a sandbox: the code can read files the server user can read and can use the network. Use it only for local development.
