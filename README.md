# Carbon Footprint Optimizer for Code

Web application for analyzing Python files for energy and carbon efficiency. Phase 2 adds Python file upload and sandboxed-enough local execution via FastAPI (without Docker).

## Repository layout

- `frontend/` — Next.js (TypeScript, App Router, Tailwind CSS)
- `backend/` — FastAPI API

## Prerequisites

- Node.js 20+
- Python 3.11+

## Run the backend

```bash
cd backend
python -m venv .venv
```

On Windows, if `python` is not on PATH, use `py -3 -m venv .venv`.

Windows:

```bash
.venv\Scripts\activate
```

macOS / Linux:

```bash
source .venv/bin/activate
```

```bash
pip install -r requirements.txt
copy .env.example .env
uvicorn app.main:app --reload --port 8000
```

On macOS / Linux, use `cp .env.example .env` instead of `copy`.

The API is available at [http://localhost:8000](http://localhost:8000). Health check: [http://localhost:8000/health](http://localhost:8000/health).

## Run the frontend

In a second terminal:

```bash
cd frontend
copy .env.example .env.local
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000). Select a `.py` file and click **Execute Python**, or use **Check Backend** to confirm the API is reachable.

## Run backend tests

```bash
cd backend
.venv\Scripts\activate
pytest
```

## What Phase 2 includes

- Upload a Python `.py` file from the homepage
- FastAPI `POST /execute` validates, saves a temporary copy, runs it in a subprocess, and returns stdout, stderr, exit code, and runtime
- Execution timeout (default 5 seconds) and 1 MB upload limit
- Backend tests for success, validation, errors, timeout, and temp-file cleanup

## Intentionally left for later phases

CodeCarbon energy measurement, RAG / green coding practices, AI agent code suggestions, databases, Docker sandboxing, and authentication.
