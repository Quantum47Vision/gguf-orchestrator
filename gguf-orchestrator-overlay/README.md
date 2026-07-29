# ⬡ GGUF Orchestrator

A local-first AI coding assistant powered by your own GGUF models.
No data leaves your machine — everything runs on `localhost`.

## What it does

- **Routes** every request to the right model automatically (router → brain or code)
- **Understands your codebase** via RAG — semantic search with pgvector embeddings
- **Proposes diffs** for you to Accept/Reject before anything touches disk
- **Remembers** per-project conversation history in PostgreSQL
- **Dashboard UI** with file tree, chat panel, and diff viewer

## Model roles

| Role | Example model | Purpose |
|------|---------------|---------|
| ⚡ Router | Qwen3-1.7B (Q8) | Classifies intent in ~100 ms. Always loaded. |
| 🧠 Brain | Qwen2.5-3B-Instruct | Reasoning, explanation, Q&A |
| ⚙️ Code | Qwen2.5.1-Coder-7B (Q4) | Code generation, refactoring, diffs |

### VRAM strategy (built for an 8 GB GPU)

The router stays loaded permanently (~2 GB). Brain and Code hot-swap — only
one is in VRAM at a time, and `n_gpu_layers` lets overflow layers spill to
system RAM via llama-cpp-python. All tunable in `config.yaml`.

## Requirements

- Windows 10/11, Python 3.10+
- PostgreSQL 14+ with the **pgvector** extension
- NVIDIA GPU with CUDA (tested on a GTX 1070 / 8 GB) — CPU fallback available
- Your `.gguf` model files on disk

## Setup

```
1. copy config.example.yaml  →  config.yaml   (set your model paths)
2. copy .env.example         →  .env          (set POSTGRES_PASSWORD)
3. setup.bat                                   (installs dependencies)
4. python check_models.py                      (verifies model paths)
5. start.bat                                   (open http://127.0.0.1:8000)
```

Create the database once in psql/pgAdmin:

```sql
CREATE DATABASE gguf_orchestrator;
\c gguf_orchestrator
CREATE EXTENSION IF NOT EXISTS vector;
```

## How a request flows

`WebSocket message → router classifies → RAG retrieves top-k code chunks
from pgvector → brain/code model streams a response → any file changes
arrive as diffs → you Accept/Reject → accepted diffs are applied to disk.`

## Project structure

```
config.yaml          all settings (gitignored — copy from config.example.yaml)
.env                 secrets (gitignored — copy from .env.example)
main.py              entry point
api/app.py           FastAPI routes + WebSocket
orchestrator/        engine, router, model hot-swap manager
rag/                 indexing + semantic search
diff/                diff generation + apply
db/                  PostgreSQL + pgvector queries
frontend/            dashboard UI
```

## Troubleshooting

- **CUDA out of memory** → lower `n_gpu_layers` for brain/code in config.yaml.
- **Database connection failed** → PostgreSQL running? `.env` password correct?
- **Model not found** → run `python check_models.py`; use forward slashes in paths.

## Privacy

Zero telemetry, zero cloud calls. Inference via llama-cpp-python on your
GPU/CPU; embeddings and history in your local PostgreSQL; the server binds
to `127.0.0.1` only.
