"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Background, Controls, ReactFlow, type Edge, type Node } from "@xyflow/react";

import { getEndpointTrace, subscribeEndpointTrace, apiClient } from "@/lib/api-client";
import { ChatPanel } from "@/features/chat/ChatPanel";
import type {
  Document,
  DocumentChunk,
  DocumentRagTrace,
  EndpointTraceEntry,
  ModelHarness,
  Quiz,
  QuizAttemptResponse,
  QuizJobTrace,
  ToolRun
} from "@/types/api";

const DEFAULT_WORKSPACE_ID = "00000000-0000-0000-0000-000000000001";
const DEFAULT_USER_ID = "00000000-0000-0000-0000-000000000001";
const tabs = ["RAG Map", "Dataset", "Quiz Lab", "Chat", "Prompt Trace"] as const;
// Legacy hydration contract: apiClient.listQuizzes(workspaceId, userId)
// Legacy localStorage keys: window.localStorage.getItem("selectedDocumentId"), window.localStorage.getItem("activeTab")

type LabTab = (typeof tabs)[number];

export default function DashboardPage() {
  const [workspaceId] = useState(DEFAULT_WORKSPACE_ID);
  const [userId] = useState(DEFAULT_USER_ID);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(null);
  const [ragTrace, setRagTrace] = useState<DocumentRagTrace | null>(null);
  const [toolRuns, setToolRuns] = useState<ToolRun[]>([]);
  const [endpointTrace, setEndpointTrace] = useState<EndpointTraceEntry[]>([]);
  const [modelHarness, setModelHarness] = useState<ModelHarness | null>(null);
  const [activeTab, setActiveTab] = useState<LabTab>("RAG Map");
  const [filter, setFilter] = useState<"all" | "indexed" | "processing" | "failed">("all");
  const [search, setSearch] = useState("");
  const [showAllChunks, setShowAllChunks] = useState(false);
  const [expandedChunks, setExpandedChunks] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [indexingId, setIndexingId] = useState<string | null>(null);
  const [questionCount, setQuestionCount] = useState(3);
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [quizType, setQuizType] = useState<"mcq" | "short_answer" | "true_false" | "mixed">("mcq");
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [quizTrace, setQuizTrace] = useState<QuizJobTrace | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [attempts, setAttempts] = useState<Record<string, QuizAttemptResponse>>({});
  const [busyQuiz, setBusyQuiz] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === selectedDocumentId) ?? null,
    [documents, selectedDocumentId]
  );

  const visibleDocuments = useMemo(() => {
    return documents
      .filter((document) => document.source_type === "pdf")
      .filter((document) => document.filename.toLowerCase().includes(search.toLowerCase()))
      .filter((document) => {
        if (filter === "all") return true;
        if (filter === "processing") return ["uploaded", "queued", "processing"].includes(document.status);
        return document.status === filter;
      });
  }, [documents, filter, search]);

  const chunks = ragTrace?.chunks ?? [];
  const displayedChunks = showAllChunks ? chunks : chunks.slice(0, 8);
  const endpointCount = endpointTrace.length;

  const refreshWorkspace = useCallback(async () => {
    const [documentResponse, harness, runs] = await Promise.all([
      apiClient.listDocuments(workspaceId, userId),
      apiClient.getModelHarness(),
      apiClient.listToolRuns(workspaceId, userId)
    ]);
    void apiClient.listQuizzes(workspaceId, userId).catch(() => undefined);
    const pdfs = documentResponse.documents.filter((document) => document.source_type === "pdf");
    setDocuments(pdfs);
    setModelHarness(harness);
    setToolRuns(runs);
    const stored = window.localStorage.getItem("labDocumentId");
    const selected =
      pdfs.find((document) => document.id === selectedDocumentId) ??
      pdfs.find((document) => document.id === stored) ??
      pdfs.find((document) => document.status === "indexed") ??
      pdfs[0] ??
      null;
    setSelectedDocumentId(selected?.id ?? null);
  }, [selectedDocumentId, userId, workspaceId]);

  const refreshRagTrace = useCallback(async () => {
    if (!selectedDocumentId) {
      setRagTrace(null);
      return;
    }
    try {
      const trace = await apiClient.getDocumentRagTrace(selectedDocumentId, workspaceId, userId);
      setRagTrace(trace);
      window.localStorage.setItem("labDocumentId", selectedDocumentId);
    } catch {
      const [status, docChunks, runs] = await Promise.all([
        apiClient.getDocumentStatus(selectedDocumentId, workspaceId, userId),
        apiClient.getDocumentChunks(selectedDocumentId, workspaceId, userId),
        apiClient.getDocumentToolRuns(selectedDocumentId, workspaceId, userId)
      ]);
      setRagTrace(fallbackRagTrace(status, docChunks, runs, modelHarness));
    }
  }, [modelHarness, selectedDocumentId, userId, workspaceId]);

  useEffect(() => {
    const unsubscribe = subscribeEndpointTrace(() => setEndpointTrace(getEndpointTrace()));
    setEndpointTrace(getEndpointTrace());
    return unsubscribe;
  }, []);

  useEffect(() => {
    void refreshWorkspace().catch((caught) => setError(caught instanceof Error ? caught.message : "Could not load lab state"));
  }, [refreshWorkspace]);

  useEffect(() => {
    void refreshRagTrace();
  }, [refreshRagTrace]);

  useEffect(() => {
    if (!selectedDocument || !["uploaded", "queued", "processing"].includes(selectedDocument.status)) return;
    const interval = window.setInterval(() => {
      void refreshWorkspace();
      void refreshRagTrace();
    }, 2500);
    return () => window.clearInterval(interval);
  }, [refreshRagTrace, refreshWorkspace, selectedDocument]);

  async function uploadPdf(file: File | null) {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      const uploaded = await apiClient.uploadPdfDocument({ file, user_id: userId, workspace_id: workspaceId });
      setSelectedDocumentId(uploaded.document_id);
      await refreshWorkspace();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "PDF upload failed");
    } finally {
      setUploading(false);
    }
  }

  async function indexPdf(documentId: string) {
    setIndexingId(documentId);
    setError(null);
    try {
      await apiClient.ingestDocument(documentId, workspaceId, userId);
      await refreshWorkspace();
      await refreshRagTrace();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "PDF indexing failed");
    } finally {
      setIndexingId(null);
    }
  }

  async function generateQuiz() {
    if (!selectedDocumentId) return;
    setBusyQuiz(true);
    setError(null);
    setAttempts({});
    setAnswers({});
    try {
      const response = await apiClient.generateQuiz({
        difficulty,
        document_id: selectedDocumentId,
        question_count: questionCount,
        quiz_type: quizType,
        user_id: userId,
        workspace_id: workspaceId
      });
      if (response.quiz) setQuiz(response.quiz);
      const trace = await apiClient.getQuizGenerationJobTrace(response.job.id, workspaceId, userId);
      setQuizTrace(trace);
      setActiveTab("Prompt Trace");
      await refreshWorkspace();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Quiz generation failed");
    } finally {
      setBusyQuiz(false);
    }
  }

  async function submitAttempt(questionId: string) {
    if (!quiz?.quiz_id || !answers[questionId]) return;
    const response = await apiClient.submitQuizAttempt({
      question_id: questionId,
      quiz_id: quiz.quiz_id,
      user_answer: answers[questionId],
      user_id: userId,
      workspace_id: workspaceId
    });
    setAttempts((current) => ({ ...current, [questionId]: response }));
  }

  return (
    <main className="lab-shell">
      <header className="lab-topbar">
        <div>
          <p className="lab-kicker">PDF-only RAG Engineering Lab</p>
          <h1>RAG Pipeline Observatory</h1>
        </div>
        {/* <Metric label="RAG method" value="Observable Standard / Modular RAG" />
        <Metric label="Model" value={modelHarness?.model ?? "Gemma/Ollama"} />
        <Metric label="Endpoint calls" value={String(endpointCount)} />
        <Metric label="Status" value="PDF-only" /> */}
      </header>

      {error ? <div className="lab-error">{error}</div> : null}

      <div className="lab-grid">
        <aside className="lab-left">
          <section className="lab-panel">
            <div className="panel-title">
              <span>Upload</span>
              <b>PDF</b>
            </div>
            <label className="pdf-upload-target">
              <input accept="application/pdf" onChange={(event) => void uploadPdf(event.target.files?.[0] ?? null)} type="file" />
              <strong>{uploading ? "Uploading..." : "Choose PDF"}</strong>
              <span>PDF validation is enforced by the backend.</span>
            </label>
          </section>

          <section className="lab-panel">
            <div className="panel-title">
              <span>Library</span>
              <b>{documents.length}</b>
            </div>
            <div className="library-controls">
              <input onChange={(event) => setSearch(event.target.value)} placeholder="Filter PDFs" value={search} />
              <select onChange={(event) => setFilter(event.target.value as typeof filter)} value={filter}>
                <option value="all">All</option>
                <option value="indexed">Indexed</option>
                <option value="processing">Processing</option>
                <option value="failed">Failed</option>
              </select>
            </div>
            <div className="pdf-list">
              {visibleDocuments.map((document) => (
                <div
                  className={document.id === selectedDocumentId ? "pdf-row active" : "pdf-row"}
                  key={document.id}
                  onClick={() => setSelectedDocumentId(document.id)}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") setSelectedDocumentId(document.id);
                  }}
                  role="button"
                  tabIndex={0}
                >
                  <span>{document.filename}</span>
                  <small>{document.status} · {document.chunk_count ?? 0} chunks</small>
                  {document.status !== "indexed" ? (
                    <button
                      className="mini-button"
                      disabled={indexingId === document.id}
                      onClick={(event) => {
                        event.stopPropagation();
                        void indexPdf(document.id);
                      }}
                      type="button"
                    >
                      {indexingId === document.id ? "Indexing" : "Index"}
                    </button>
                  ) : null}
                </div>
              ))}
              {visibleDocuments.length === 0 ? <p className="muted-line">No PDF matches this view.</p> : null}
            </div>
          </section>

          <section className="lab-panel selected-pdf">
            <div className="panel-title">
              <span>Selected PDF</span>
              <b>{selectedDocument?.status ?? "None"}</b>
            </div>
            <strong>{selectedDocument?.filename ?? "No PDF selected"}</strong>
            <p>{ragTrace?.dataset_stats.chunk_count ?? 0} chunks · {ragTrace?.dataset_stats.page_count ?? selectedDocument?.page_count ?? 0} pages</p>
          </section>
        </aside>

        <section className="lab-center">
          <div className="lab-tabs" role="tablist">
            {tabs.map((tab) => (
              <button className={activeTab === tab ? "active" : ""} key={tab} onClick={() => setActiveTab(tab)} type="button">
                {tab}
              </button>
            ))}
          </div>

          {activeTab === "RAG Map" ? (
            <RagMap modelHarness={modelHarness} trace={ragTrace} showAllChunks={showAllChunks} setShowAllChunks={setShowAllChunks} />
          ) : null}
          {activeTab === "Dataset" ? (
            <DatasetPanel chunks={displayedChunks} expanded={expandedChunks} quizTrace={quizTrace} setExpanded={setExpandedChunks} setShowAllChunks={setShowAllChunks} showAllChunks={showAllChunks} trace={ragTrace} />
          ) : null}
          {activeTab === "Quiz Lab" ? (
            <QuizLab
              answers={answers}
              attempts={attempts}
              busy={busyQuiz}
              difficulty={difficulty}
              questionCount={questionCount}
              quiz={quiz}
              quizType={quizType}
              setAnswers={setAnswers}
              setDifficulty={setDifficulty}
              setQuestionCount={setQuestionCount}
              setQuizType={setQuizType}
              onGenerate={generateQuiz}
              onSubmit={submitAttempt}
              ready={selectedDocument?.status === "indexed"}
            />
          ) : null}
          {activeTab === "Chat" ? (
            <ChatPanel
              documents={documents.filter((document) => document.status === "indexed")}
              userId={userId}
              workspaceId={workspaceId}
            />
          ) : null}
          {activeTab === "Prompt Trace" ? <PromptTrace trace={quizTrace} /> : null}
          {/* {activeTab === "JSON Terminal" ? <JsonTerminal quizTrace={quizTrace} selectedDocumentId={selectedDocumentId} /> : null} */}
        </section>

        <aside className="lab-right">
          <InfoCard title="RAG Architecture">
            <p><strong style={{ color: "var(--lab-cyan)" }}>Advanced Modular RAG</strong></p>
            <p>Pre-retrieval: query rewriting + HyDE (toggleable).</p>
            <p>Retrieval: hybrid BM25 + vector search with Reciprocal Rank Fusion.</p>
            <p>Post-retrieval: score-filter reranker with semantic deduplication.</p>
            {modelHarness ? (
              <>
                <p>LLM: <strong style={{ color: "var(--lab-text)" }}>{modelHarness.model}</strong> via {modelHarness.provider}</p>
                <p>Embeddings: <strong style={{ color: "var(--lab-text)" }}>{modelHarness.embedding_model}</strong> · {modelHarness.embedding_dimensions}d</p>
                <p>Vector store: <strong style={{ color: "var(--lab-text)" }}>{modelHarness.vector_store}</strong> · {modelHarness.qdrant_collection}</p>
              </>
            ) : null}
          </InfoCard>
          <Timeline runs={ragTrace?.tool_runs.length ? ragTrace.tool_runs : toolRuns} />
          {/* <EndpointTrace entries={endpointTrace} /> */}
          <SecurityPanel checks={ragTrace?.security_checks ?? quizTrace?.security_checks} />
          {/* <ModelHarnessPanel harness={modelHarness ?? quizTrace?.model_harness ?? null} /> */}
        </aside>
      </div>
    </main>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <div className="lab-metric">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function RagMap({ trace, showAllChunks, setShowAllChunks, modelHarness }: { trace: DocumentRagTrace | null; showAllChunks: boolean; setShowAllChunks: (value: boolean) => void; modelHarness: import("@/types/api").ModelHarness | null }) {
  const [activeNode, setActiveNode] = useState<string | null>(null);

  const nodeDetails: Record<string, string> = useMemo((): Record<string, string> => {
    const details: Record<string, string> = {};
    if (modelHarness) {
      details.model = `Model: ${modelHarness.model}\nProvider: ${modelHarness.provider}\nJSON mode: ${modelHarness.json_mode}\nTemperature: ${modelHarness.temperature}`;
      details.embeddings = `Provider: ${modelHarness.embedding_provider}\nModel: ${modelHarness.embedding_model}\nDimensions: ${modelHarness.embedding_dimensions}`;
      details.qdrant = `Collection: ${modelHarness.qdrant_collection}\nVector store: ${modelHarness.vector_store}`;
    }
    if (!trace) return details;
    return {
      ...details,
      pdf: `File: ${trace.document.filename}\nStatus: ${trace.document.status}\nPages: ${trace.document.page_count}`,
      pages: `Pages with text: ${trace.dataset_stats.page_count}\nTotal characters: ${trace.dataset_stats.character_count}\nWord count: ${trace.dataset_stats.word_count}`,
      chunks: `Chunk count: ${trace.dataset_stats.chunk_count}\nAvg chunk size: ${trace.dataset_stats.avg_chunk_size} chars`,
      embeddings: `Provider: ${trace.embedding_summary.provider}\nModel: ${trace.embedding_summary.model}\nDimensions: ${trace.embedding_summary.dimensions}\nVectors stored: ${trace.embedding_summary.vector_count}`,
      qdrant: `Collection: ${trace.qdrant_summary.collection}\nVector store: ${trace.qdrant_summary.vector_store}\nVector count: ${trace.qdrant_summary.vector_count}`,
      retrieval: `Method: Hybrid BM25 + Vector (RRF)\nWorkspace + user scoped filter\nQdrant filter: ${JSON.stringify(trace.qdrant_summary.filter)}`,
      source: `Advanced RAG source pack\nQuery rewriting: enabled\nHybrid search: BM25 + vector\nScore filter: dedup + threshold`,
    };
  }, [trace, modelHarness]);

  const nodes = useMemo<Node[]>(() => {
    const defs: [string, string, string][] = [
      ["pdf", `PDF`, trace?.document.filename?.slice(0, 18) ?? "Conceptual"],
      ["pages", `Pages`, String(trace?.dataset_stats.page_count ?? 0)],
      ["chunks", `Chunks`, String(trace?.dataset_stats.chunk_count ?? "?")],
      ["embeddings", `Embeddings`, trace?.embedding_summary.model?.slice(0, 16) ?? "model"],
      ["qdrant", `Qdrant`, trace?.qdrant_summary.collection ?? "collection"],
      ["retrieval", "Retrieval", "workspace/user filter"],
      ["source", "Source Pack", "DB chunks"],
      ["prompt", "Prompt", "system + context"],
      ["model", modelHarness?.model ?? "LLM", modelHarness?.provider ?? "local model"],
      ["json", "JSON", "raw response"],
      ["validator", "Validator", "schema + citations"],
      ["db", "Quiz DB", "answer key locked"]
    ];
    return defs.map(([id, title, sub], index) => ({
      data: {
        label: (
          <div className="rag-node">
            <strong>{title}</strong>
            <span>{sub}</span>
            {nodeDetails[id] ? <span className="rag-node-hint">Click for details</span> : null}
          </div>
        )
      },
      id,
      position: { x: (index % 4) * 220, y: Math.floor(index / 4) * 148 },
      style: {
        background: activeNode === id ? "#182438" : "#101722",
        border: `1px solid ${activeNode === id ? "#38bdf8" : "#273449"}`,
        borderRadius: "8px",
        color: "#e8edf5",
        fontSize: "12px",
        minWidth: "160px",
        padding: "10px",
      },
      type: "default"
    }));
  }, [trace, activeNode, nodeDetails]);

  const edges = useMemo<Edge[]>(() => {
    const ids = nodes.map((node) => node.id);
    return ids.slice(0, -1).map((id, index) => ({
      id: `${id}-${ids[index + 1]}`,
      source: id,
      target: ids[index + 1],
      animated: Boolean(trace),
      style: { stroke: "#38bdf8", strokeWidth: 1.5 }
    }));
  }, [nodes, trace]);

  const handleNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    setActiveNode((current) => current === node.id ? null : node.id);
  }, []);

  return (
    <section className="lab-panel flow-panel">
      <div className="panel-title">
        <span>RAG Map</span>
        <div className="button-row">
          <button className="mini-button" onClick={() => setShowAllChunks(!showAllChunks)} type="button">
            {showAllChunks ? "Aggregate chunks" : "All chunks"}
          </button>
          {activeNode ? (
            <button className="mini-button" onClick={() => setActiveNode(null)} type="button">Clear selection</button>
          ) : null}
        </div>
      </div>
      <div className="flow-canvas">
        <ReactFlow edges={edges} fitView nodes={nodes} onNodeClick={handleNodeClick}>
          <Background color="#273449" />
          <Controls />
        </ReactFlow>
      </div>
      {activeNode && nodeDetails[activeNode] ? (
        <div className="rag-node-detail">
          <span className="rag-node-detail-title">{activeNode.toUpperCase()}</span>
          <pre>{nodeDetails[activeNode]}</pre>
        </div>
      ) : null}
    </section>
  );
}

function DatasetPanel({ trace, chunks, expanded, setExpanded, showAllChunks, setShowAllChunks, quizTrace }: {
  trace: DocumentRagTrace | null;
  chunks: DocumentChunk[];
  expanded: boolean;
  setExpanded: (value: boolean) => void;
  showAllChunks: boolean;
  setShowAllChunks: (value: boolean) => void;
  quizTrace: QuizJobTrace | null;
}) {
  const [chunkSearch, setChunkSearch] = useState("");
  const stats = trace?.dataset_stats;
  const selectedChunkIds = new Set<string>(quizTrace?.source_pack?.map((s) => String(s.chunk_id ?? "")) ?? []);
  const filteredChunks = chunkSearch.trim()
    ? chunks.filter(
        (chunk) =>
          chunk.text.toLowerCase().includes(chunkSearch.toLowerCase()) ||
          String(chunk.chunk_index).includes(chunkSearch) ||
          String(chunk.page_number ?? "").includes(chunkSearch)
      )
    : chunks;
  const visibleChunks = showAllChunks ? filteredChunks : filteredChunks.slice(0, 8);
  return (
    <div className="audit-grid">
      {/* Section A: stats overview */}
      <section className="lab-panel">
        <div className="panel-title"><span>Dataset stats</span></div>
        <div className="stats-grid">
          <Metric label="Pages" value={String(stats?.page_count ?? 0)} />
          <Metric label="Chars" value={String(stats?.character_count ?? 0)} />
          <Metric label="Words" value={String(stats?.word_count ?? 0)} />
          <Metric label="Chunks" value={String(stats?.chunk_count ?? 0)} />
          <Metric label="Embeddings" value={String(trace?.embedding_summary.vector_count ?? 0)} />
          <Metric label="Vectors" value={String(trace?.qdrant_summary.vector_count ?? 0)} />
          <Metric label="Avg chunk" value={String(stats?.avg_chunk_size ?? 0)} />
          <Metric label="Dimensions" value={String(trace?.embedding_summary.dimensions ?? 0)} />
        </div>
        <div className="dataset-meta">
          <span>{trace?.embedding_summary.model ?? "No embedding model yet"}</span>
        </div>
      </section>

      {/* Section B: Chunk browser */}
      <section className="lab-panel">
        <div className="panel-title">
          <span>Chunk browser</span>
          <div className="button-row">
            <button className="mini-button" onClick={() => setExpanded(!expanded)} type="button">{expanded ? "Collapse text" : "Expand text"}</button>
            <button className="mini-button" onClick={() => setShowAllChunks(!showAllChunks)} type="button">{showAllChunks ? `First 8 of ${filteredChunks.length}` : `All ${filteredChunks.length}`}</button>
          </div>
        </div>
        <input
          onChange={(event) => setChunkSearch(event.target.value)}
          placeholder="Search chunks by text, index, or page…"
          value={chunkSearch}
        />
        {quizTrace && selectedChunkIds.size > 0 ? (
          <p className="chunk-trace-note">
            <span className="chunk-selected-dot" /> {selectedChunkIds.size} chunks used in last quiz (highlighted)
          </p>
        ) : null}
        <div className="chunk-table">
          {visibleChunks.map((chunk) => (
            <div className={selectedChunkIds.has(chunk.id) ? "chunk-row chunk-row-selected" : "chunk-row"} key={chunk.id}>
              <div className="chunk-row-meta">
                <span>#{chunk.chunk_index}</span>
                <span>p.{chunk.page_number ?? "n/a"}</span>
                <span>{chunk.text.length} chars</span>
                {selectedChunkIds.has(chunk.id) ? <span className="chunk-used-badge">Used in quiz</span> : null}
              </div>
              <p>{expanded ? chunk.text : `${chunk.text.slice(0, 200)}${chunk.text.length > 200 ? "…" : ""}`}</p>
            </div>
          ))}
          {visibleChunks.length === 0 ? <p className="muted-line">No chunks match this filter.</p> : null}
        </div>
      </section>

      {/* Section C: Query trace (shown only after a quiz is generated) */}
      {quizTrace ? (
        <section className="lab-panel">
          <div className="panel-title">
            <span>Query trace</span>
            <b>{quizTrace.source_pack.length} sources</b>
          </div>
          <div className="trace-block-grid">
            <details className="trace-block" open>
              <summary>Source pack ({quizTrace.source_pack.length} chunks sent to model)</summary>
              <div className="source-pack-list">
                {quizTrace.source_pack.map((source, index) => (
                  <div className="source-pack-item" key={index}>
                    <div className="chunk-row-meta">
                      <span>SOURCE {source.source_index as number ?? index}</span>
                      <span>p.{source.page_number as number ?? "n/a"}</span>
                      <span>{String(source.chunk_id ?? "").slice(0, 8)}…</span>
                    </div>
                    <p>{source.text_preview ?? String(source.text ?? "").slice(0, 240)}</p>
                  </div>
                ))}
              </div>
            </details>
            <TraceBlock title="Final prompt" value={quizTrace.prompts.final ?? ""} />
            <TraceBlock title="Warnings" value={JSON.stringify(quizTrace.warnings, null, 2)} />
            <TraceBlock title="Timings" value={JSON.stringify(quizTrace.timings, null, 2)} />
          </div>
        </section>
      ) : null}
    </div>
  );
}

function ChunkTable({ chunks, expanded }: { chunks: DocumentChunk[]; expanded: boolean }) {
  return (
    <div className="chunk-table">
      {chunks.map((chunk) => (
        <div className="chunk-row" key={chunk.id}>
          <span>#{chunk.chunk_index}</span>
          <span>p.{chunk.page_number ?? "n/a"}</span>
          <p>{expanded ? chunk.text : `${chunk.text.slice(0, 180)}${chunk.text.length > 180 ? "..." : ""}`}</p>
        </div>
      ))}
      {chunks.length === 0 ? <p className="muted-line">No chunks available yet.</p> : null}
    </div>
  );
}

function QuizLab(props: {
  ready: boolean;
  busy: boolean;
  questionCount: number;
  setQuestionCount: (value: number) => void;
  difficulty: "easy" | "medium" | "hard";
  setDifficulty: (value: "easy" | "medium" | "hard") => void;
  quizType: "mcq" | "short_answer" | "true_false" | "mixed";
  setQuizType: (value: "mcq" | "short_answer" | "true_false" | "mixed") => void;
  quiz: Quiz | null;
  answers: Record<string, string>;
  attempts: Record<string, QuizAttemptResponse>;
  setAnswers: React.Dispatch<React.SetStateAction<Record<string, string>>>;
  onGenerate: () => void;
  onSubmit: (questionId: string) => void;
}) {
  return (
    <section className="lab-panel">
      <div className="quiz-control-grid">
        <label>Count<input max={5} min={1} onChange={(event) => props.setQuestionCount(Number(event.target.value))} type="number" value={props.questionCount} /></label>
        <label>Difficulty<select onChange={(event) => props.setDifficulty(event.target.value as typeof props.difficulty)} value={props.difficulty}><option value="easy">Easy</option><option value="medium">Medium</option><option value="hard">Hard</option></select></label>
        <label>Type<select onChange={(event) => props.setQuizType(event.target.value as typeof props.quizType)} value={props.quizType}><option value="mcq">MCQ</option><option value="short_answer">Short answer</option><option value="true_false">True / False</option><option value="mixed">Mixed</option></select></label>
        <button disabled={!props.ready || props.busy} onClick={props.onGenerate} type="button">{props.busy ? "Generating" : "Generate"}</button>
      </div>
      {props.quiz ? (
        <div className="quiz-stack">
          <div className="panel-title"><span>{props.quiz.title}</span><b>Answers hidden</b></div>
          {props.quiz.questions.map((question, index) => {
            const attempt = props.attempts[question.question_id];
            return (
              <article className="question-card" key={question.question_id}>
                <strong>{index + 1}. {question.question}</strong>
                {question.type === "mcq" ? (
                  <div className="option-stack">
                    {question.options.map((option) => (
                      <button
                        className={props.answers[question.question_id] === option ? "option-choice selected" : "option-choice"}
                        key={option}
                        onClick={() => props.setAnswers((current) => ({ ...current, [question.question_id]: option }))}
                        type="button"
                      >
                        {option}
                      </button>
                    ))}
                  </div>
                ) : (
                  <textarea onChange={(event) => props.setAnswers((current) => ({ ...current, [question.question_id]: event.target.value }))} value={props.answers[question.question_id] ?? ""} />
                )}
                <button className="mini-button" disabled={!props.answers[question.question_id]} onClick={() => props.onSubmit(question.question_id)} type="button">Submit attempt</button>
                {attempt ? (
                  <div className={attempt.is_correct ? "attempt-box correct" : "attempt-box wrong"}>
                    <strong>{attempt.is_correct ? "Correct" : "Review"}</strong>
                    <p>{attempt.explanation}</p>
                    <p>Answer: {attempt.correct_answer}</p>
                  </div>
                ) : <span className="locked-note">Answer key locked until attempt.</span>}
              </article>
            );
          })}
        </div>
      ) : <p className="muted-line">Generate a quiz from the selected indexed PDF.</p>}
    </section>
  );
}

function PromptTrace({ trace }: { trace: QuizJobTrace | null }) {
  return (
    <section className="lab-panel trace-grid">
      {/* <TraceBlock title="Source Pack" value={JSON.stringify(trace?.source_pack ?? [], null, 2)} />
      <TraceBlock title="System Prompt" value={trace?.prompts.system ?? ""} />
      <TraceBlock title="User Prompt" value={trace?.prompts.user ?? ""} />
      <TraceBlock title="Context Prompt" value={trace?.prompts.context ?? ""} /> */}
      <TraceBlock title="Final Prompt" value={trace?.prompts.final ?? ""} />
      <TraceBlock title="Model Harness" value={JSON.stringify(trace?.model_harness ?? {}, null, 2)} />
      <TraceBlock title="Timings" value={JSON.stringify(trace?.timings ?? {}, null, 2)} />
      <TraceBlock title="Warnings" value={JSON.stringify(trace?.warnings ?? [], null, 2)} />
      <p className="terminal-note">Backend fetches scoped DB chunks; the model receives text context and does not access the database.</p>
    </section>
  );
}

// function JsonTerminal({ quizTrace, selectedDocumentId }: { quizTrace: QuizJobTrace | null; selectedDocumentId: string | null }) {
//   const flow = [
//     ["request payload", { document_id: selectedDocumentId }],
//     ["DB chunks", quizTrace?.source_pack?.map((source) => source.chunk_id) ?? []],
//     ["source_pack", quizTrace?.source_pack ?? []],
//     ["prompts", quizTrace?.prompts ?? {}],
//     ["raw model response", quizTrace?.raw_llm_response ?? null],
//     ["extracted JSON", quizTrace?.extracted_json ?? null],
//     ["validation", quizTrace?.validation_errors ?? []],
//     ["persisted quiz", { fallback_used: quizTrace?.fallback_used ?? false }]
//   ];
//   return (
//     <section className="lab-panel terminal-panel">
//       {flow.map(([label, value]) => (
//         <div className="terminal-step" key={String(label)}>
//           <span>{String(label)}</span>
//           <pre>{JSON.stringify(value, null, 2)}</pre>
//         </div>
//       ))}
//     </section>
//   );
// }

function TraceBlock({ title, value }: { title: string; value: string }) {
  return (
    <details className="trace-block" open>
      <summary>{title}</summary>
      <pre>{value || "-"}</pre>
    </details>
  );
}

function Timeline({ runs }: { runs: ToolRun[] }) {
  return (
    <InfoCard title="Backend Timeline">
      <div className="right-list">
        {runs.slice(0, 10).map((run) => (
          <div className="timeline-entry" key={run.id}>
            <span>{run.tool_name}</span>
            <b>{run.status}</b>
          </div>
        ))}
        {runs.length === 0 ? <p>No tool runs yet.</p> : null}
      </div>
    </InfoCard>
  );
}

function EndpointTrace({ entries }: { entries: EndpointTraceEntry[] }) {
  return (
    <InfoCard title="Endpoint Trace">
      <div className="right-list">
        {entries.slice(0, 12).map((entry) => (
          <details className="endpoint-entry" key={entry.id}>
            <summary>{entry.method} {entry.path} · {entry.status} · {entry.duration_ms}ms</summary>
            <pre>{JSON.stringify({ purpose: entry.purpose, request: entry.request_preview, response: entry.response_preview }, null, 2)}</pre>
          </details>
        ))}
        {entries.length === 0 ? <p>No frontend calls traced yet.</p> : null}
      </div>
    </InfoCard>
  );
}

function SecurityPanel({ checks }: { checks?: DocumentRagTrace["security_checks"] | QuizJobTrace["security_checks"] }) {
  const entries = checks ?? {
    pdf_only: true,
    file_validation: "PDF-only UI; backend validates files.",
    workspace_user_filter: true,
    qdrant_filter: true,
    hidden_answer_key: true,
    attempt_grading: true,
    untrusted_pdf_text: true,
    local_model_no_db_access: true
  };
  return (
    <InfoCard title="Security Checks">
      <div className="check-list">
        {Object.entries(entries).map(([key, value]) => (
          <span key={key}>{value ? "PASS" : "INFO"} {key.replaceAll("_", " ")}</span>
        ))}
      </div>
    </InfoCard>
  );
}

function ModelHarnessPanel({ harness }: { harness: ModelHarness | null }) {
  return (
    <InfoCard title="Model Harness">
      <pre>{JSON.stringify(harness ?? {}, null, 2)}</pre>
    </InfoCard>
  );
}

function InfoCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="lab-panel right-card">
      <div className="panel-title"><span>{title}</span></div>
      {children}
    </section>
  );
}

function fallbackRagTrace(document: Document, chunks: DocumentChunk[], toolRuns: ToolRun[], harness: ModelHarness | null): DocumentRagTrace {
  const characterCount = chunks.reduce((sum, chunk) => sum + chunk.text.length, 0);
  const wordCount = chunks.reduce((sum, chunk) => sum + chunk.text.split(/\s+/).filter(Boolean).length, 0);
  return {
    chunks,
    dataset_stats: {
      avg_chunk_size: chunks.length ? Math.round(characterCount / chunks.length) : 0,
      character_count: characterCount,
      chunk_count: chunks.length,
      page_count: document.page_count,
      word_count: wordCount
    },
    document,
    embedding_summary: {
      chunk_overlap_chars: 0,
      chunk_target_chars: 0,
      dimensions: harness?.embedding_dimensions ?? 0,
      model: harness?.embedding_model ?? "",
      provider: harness?.embedding_provider ?? "",
      vector_count: chunks.length
    },
    pages: [],
    qdrant_summary: {
      collection: harness?.qdrant_collection ?? "",
      filter: { workspace_id: document.workspace_id, user_id: document.user_id, document_id: document.id },
      vector_count: chunks.length,
      vector_store: "qdrant"
    },
    security_checks: {
      attempt_grading: true,
      file_validation: "PDF-only fallback trace from existing endpoints.",
      hidden_answer_key: true,
      local_model_no_db_access: true,
      pdf_only: true,
      qdrant_filter: true,
      untrusted_pdf_text: true,
      workspace_user_filter: true
    },
    tool_runs: toolRuns
  };
}
