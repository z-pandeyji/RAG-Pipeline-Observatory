# RAG Pipeline Observatory

A full-stack, local-first Retrieval-Augmented Generation platform for building private AI learning workspaces. Upload PDFs, index them into a vector store, generate evidence-grounded quizzes, and chat with your documents — all running locally with no hosted model providers.

---

## Features

### 🔬 Advanced RAG Pipeline
- **Hybrid retrieval** — BM25 lexical search fused with Qdrant vector search via Reciprocal Rank Fusion (RRF)
- **Pre-retrieval** — query rewriting (LLM reformulates the query for better recall) and HyDE (Hypothetical Document Embeddings, toggleable)
- **Post-retrieval** — score-filter reranker with semantic deduplication; filters low-signal chunks before generation
- **Observability** — every pipeline stage (ingest, chunk, embed, retrieve, rerank, generate) logged as a tool run; visible in the Pipeline Observatory

### 📄 PDF Ingestion
- Upload PDFs up to 12 MB
- Semantic chunking with paragraph-aware overlap
- Embeddings generated locally via Ollama or LM Studio
- Chunks stored in PostgreSQL, vectors stored in Qdrant

### 🧠 Quiz Generation
- Multiple choice (MCQ), True/False, short answer, and mixed modes
- Difficulty levels: easy, medium, hard
- Answers locked until the user submits an attempt
- Retry/repair logic for malformed LLM output
- Quiz history persisted to the backend; answers and attempts persist in localStorage

### 💬 Chat
- Grounded Q&A over indexed PDFs
- Markdown rendered responses (headings, tables, code, lists)
- Evidence citations shown per answer
- Message history persists in localStorage per workspace

### 🗺 RAG Map & Pipeline Observatory
- Interactive visual graph of the RAG pipeline stages with live node status
- Backend Timeline shows every tool run with status, duration, and expandable output
- RAG Architecture card shows live model, embedding model, dimensions, and vector store config

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 15, React 19, TypeScript |
| Backend | FastAPI, Python 3.11, SQLAlchemy (async) |
| Vector DB | Qdrant |
| Relational DB | PostgreSQL |
| Embeddings | Ollama (`bge-m3`) or LM Studio |
| LLM | Ollama (`gemma4:latest`) or LM Studio |
| Chunking | Semantic paragraph-aware sliding window |

---

## Quick Start

### 1. Prerequisites

- [Ollama](https://ollama.ai) running locally with models pulled:
  ```bash
  ollama pull gemma4
  ollama pull bge-m3
  ```
- Docker (for PostgreSQL + Qdrant):
  ```bash
  cd infra && docker compose up -d
  ```

### 2. Backend

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
cp .env.example .env
# Edit .env — set LLM_PROVIDER=ollama, EMBEDDING_PROVIDER=ollama
cd apps/api
uvicorn app.main:app --reload --port 8000
```

### 3. Frontend

```bash
cd apps/web
npm install
cp .env.example .env.local
# .env.local: NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## Environment Reference

Key variables in `.env.example`:

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_PROVIDER` | `ollama` | `ollama` or `lmstudio` |
| `LLM_MODEL` | `gemma4:latest` | Model name for chat/generation |
| `EMBEDDING_PROVIDER` | `ollama` | `ollama` or `lmstudio` |
| `EMBEDDING_MODEL` | `bge-m3:latest` | Model name for embeddings |
| `QDRANT_URL` | `http://127.0.0.1:6333` | Qdrant instance URL |
| `DATABASE_URL` | `postgresql+asyncpg://...` | PostgreSQL connection string |
| `QUIZ_TOP_K` | `8` | Chunks retrieved per quiz generation |
| `QUERY_REWRITING_ENABLED` | `true` | Enable LLM query rewriting pre-retrieval |
| `HYBRID_SEARCH_ENABLED` | `true` | Enable BM25 + vector RRF fusion |
| `RERANK_MIN_SCORE` | `0.05` | Cosine similarity cutoff for post-retrieval filter |

---

## Project Layout

```
apps/
  api/                  FastAPI backend
    app/
      core/             Config (Pydantic Settings)
      db/               SQLAlchemy models + session
      repositories/     Data access layer (documents, chunks, quizzes, citations)
      routers/          API endpoints (ingestion, generation, quizzes, retrieval)
      schemas/          Pydantic request/response models
      services/
        ingestion.py    PDF → extract → chunk → embed → upsert
        retrieval.py    Query embed → Qdrant search → hybrid BM25 fusion → rerank
        generation.py   Context build → LLM call → citation store
        quizzes.py      Quiz generation with validation + repair
        query_rewriting.py  Pre-retrieval LLM query reformulation
        hyde.py         Hypothetical Document Embeddings
        bm25_index.py   In-memory BM25 + RRF fusion
        reranking/      Pluggable reranker (score_filter, vector_order)
        embeddings/     Ollama + LM Studio embedding providers
        llm/            Ollama + LM Studio chat providers
  web/                  Next.js 15 frontend
    app/
      page.tsx          RAG Pipeline Observatory (main lab page)
      globals.css       Design system + lab dark theme
    features/
      chat/             Chat panel with markdown rendering + localStorage
      quiz/             Quiz lab with animated generation stepper
      citations/        Evidence citation cards
      audit/            Full RAG audit view (pipeline + chunk browser + trace)
    components/ui/      Shared UI: ProgressBar, ChatSkeleton, StatusBadge, etc.
    lib/api-client.ts   Typed API client
    types/api.ts        Shared TypeScript types
app/                    Simple legacy PDF quiz backend (prototype)
web/                    Simple legacy vanilla JS frontend (prototype)
infra/
  docker-compose.yml    PostgreSQL + Qdrant local stack
tests/                  Python test suite
pyproject.toml          Python package metadata
```

---

## Running Tests

```bash
source .venv/bin/activate
python3 -m pytest tests/ -v
```

---

## Architecture

```
PDF Upload
  → Validate (size + magic bytes)
  → Semantic Chunking (paragraph-aware, overlapping)
  → Embedding Generation (Ollama bge-m3 / LM Studio)
  → Qdrant Vector Upsert + PostgreSQL chunk store

Query / Generate
  → Query Rewriting (LLM reformulates for recall)  [pre-retrieval]
  → HyDE (optional hypothetical passage embedding)  [pre-retrieval]
  → Qdrant Dense Vector Search
  → BM25 Lexical Search (in-memory, document-scoped)
  → RRF Score Fusion (Reciprocal Rank Fusion)
  → Score-Filter Reranker (cosine threshold + dedup) [post-retrieval]
  → Context Builder (token budget, citations)
  → LLM Generation (Ollama gemma4 / LM Studio)
  → Output + Citation Storage
```

---

## License

MIT
