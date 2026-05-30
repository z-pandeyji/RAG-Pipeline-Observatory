# Senior RAG Quiz Lab

Local-first RAG quiz generator for PDF ingestion, structured as the first slice of a security-aware enterprise RAG system. The backend never calls a hosted model provider; generation goes to an LM Studio OpenAI-compatible endpoint running Gemma locally.

## What Works Now

- Upload one small PDF.
- Validate the file as a real PDF before parsing.
- Extract text page by page.
- Chunk, index, and retrieve locally.
- Send only selected context chunks to LM Studio for quiz generation.
- Show a frontend trace of each RAG step: extraction, chunking, retrieval, prompt preview, and model timing.

## Quick Start

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -e .
cp .env.example .env
uvicorn app.main:app --reload --port 4101
```

Open `http://127.0.0.1:4101`.

LM Studio should be running with a Gemma model loaded and the local server enabled. Default URL:

```text
http://127.0.0.1:1234/v1/chat/completions
```

## Security Shape

- Files are content-addressed by a server-side UUID, not by user-controlled names.
- Uploads are size-limited.
- PDF magic bytes are checked before parsing.
- Path traversal is avoided by never using the uploaded filename for storage.
- Extracted content is kept local in memory for this first slice.
- The model receives only top retrieved chunks, not the whole document.
- The generation prompt instructs the model to refuse unsupported quiz questions.
- The trace shown to the user is redacted and bounded.

## Architecture

Detailed architecture docs:

- [RAG System Architecture](docs/architecture.md)
- [ADR-0001: Secure Local-First RAG Pipeline](docs/adr/0001-secure-rag-pipeline.md)
- [ADR-0002: Local-First Storage And Indexing](docs/adr/0002-storage-and-indexing.md)
- [ADR-0003: RAG Testing Strategy](docs/adr/0003-testing-strategy.md)
- [Testing Strategy](docs/testing-strategy.md)

Target project structure:

```text
User
  -> API Gateway + Auth + Rate Limits
  -> Query Security Layer
     - prompt-injection detection
     - PII / secrets filtering
     - tenant permission check
  -> Query Understanding
     - rewrite query
     - detect intent
     - route to correct knowledge source
  -> Hybrid Retrieval
     - BM25 keyword search
     - vector search
     - metadata filters
     - tenant / role filters
  -> Reranking
     - cross-encoder / LLM reranker
     - keep top 5-10 chunks only
  -> Context Builder
     - deduplicate chunks
     - compress/summarize if needed
     - attach citations
  -> LLM Answer Generation
     - grounded-only prompt
     - cite sources
     - refuse if evidence is insufficient
  -> Output Guardrails
     - hallucination check
     - sensitive data check
     - unsafe output check
  -> Observability + Evaluation
     - retrieval metrics
     - answer quality
     - latency/cost
     - security events
```

Current implemented slice:

```text
Browser
  -> FastAPI API boundary
  -> PDF validator
  -> PDF text extractor
  -> overlapping chunker
  -> in-memory document store
  -> local BM25-style retriever
  -> bounded prompt compiler
  -> LM Studio Gemma endpoint
  -> quiz JSON parser
  -> trace projection
```

The current retriever is a local BM25-style scorer to keep the initial project dependency-light and stable. PostgreSQL plus pgvector is the selected persistence and vector-search target; the current in-memory store will be replaced once repository tests are in place.

## Project Layout

```text
app/
  main.py          FastAPI app setup and static frontend mount.
  routes.py        Upload and quiz API endpoints.
  security.py      Upload size checks, PDF magic-byte validation, document IDs.
  pdf_pipeline.py  PDF text extraction and overlapping chunking.
  retrieval.py     Local BM25-style lexical retrieval.
  generator.py     Grounded prompt construction, LM Studio call, JSON parsing.
  store.py         Current in-memory document storage and per-document index.
  storage/         PostgreSQL and pgvector schema artifacts.
  models.py        Pydantic request, response, trace, and chunk models.
  config.py        Environment-backed runtime settings.
web/
  index.html       Browser UI.
  main.js          Upload, quiz generation, and trace rendering.
  styles.css       UI styling.
pyproject.toml     Python package metadata and dependencies.
README.md          Project overview and operating guide.
```

## Testing

Run the current deterministic test suite with:

```bash
python3 -m unittest discover -s tests
```

The test strategy and future coverage plan are documented in [Testing Strategy](docs/testing-strategy.md).

## Next Slices

1. Add repository tests and harden PostgreSQL metadata, pgvector embeddings, and content-addressed blobs.
2. Add image OCR through a local model or Tesseract sandbox.
3. Add video ingestion with audio extraction, transcript segmentation, and frame OCR.
4. Add multi-tenant isolation, auth, and per-document authorization checks.
5. Replace lexical retrieval with hybrid retrieval: pgvector embeddings plus BM25 plus reranking.
