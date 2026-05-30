"use client";

import { useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { StatusBadge } from "@/components/ui/StatusBadge";
import type { Document, ToolRun, ToolRunStatus } from "@/types/api";

const TOOL_EXPLANATIONS: Record<string, string> = {
  chunk_hydration: "Loads full source chunks from the database.",
  embedding_generation: "Creates vectors so the content can be searched semantically.",
  grounded_generation: "Creates an answer using only retrieved evidence.",
  image_ocr_extraction: "Extracts readable text from the uploaded image.",
  image_validation: "Checks file type, extension, and magic bytes.",
  pdf_text_extraction: "Extracts readable text from PDF pages.",
  qdrant_upsert: "Stores searchable vectors with secure workspace/user metadata.",
  query_embedding: "Converts your question into a search vector.",
  quiz_attempt_grading: "Grades the user attempt and then reveals the answer.",
  quiz_generation: "Creates quiz questions from retrieved evidence.",
  quiz_persistence: "Stores quiz safely while keeping answers locked.",
  quiz_validation: "Checks generated quiz structure and citations.",
  reranking: "Sorts retrieved chunks by relevance.",
  semantic_chunking: "Splits extracted content into searchable learning units.",
  vector_retrieval: "Finds relevant chunks from your uploaded content.",
  youtube_transcript_extraction: "Extracts timestamped transcript segments from the video.",
  youtube_url_validation: "Checks that the submitted link is a valid YouTube URL.",
  youtube_audio_download: "Downloads safe best-audio from the validated YouTube URL.",
  youtube_audio_transcription: "Transcribes downloaded audio into timestamped learning segments."
};

const STAGES: Array<{ title: string; tools: string[] }> = [
  { title: "Upload", tools: ["pdf_text_extraction", "youtube_url_validation", "image_validation"] },
  {
    title: "Extraction",
    tools: [
      "youtube_transcript_extraction",
      "youtube_audio_download",
      "youtube_audio_transcription",
      "image_ocr_extraction"
    ]
  },
  { title: "Chunking", tools: ["semantic_chunking"] },
  { title: "Embeddings", tools: ["embedding_generation"] },
  { title: "Indexing", tools: ["qdrant_upsert"] },
  { title: "Retrieval", tools: ["query_embedding", "vector_retrieval", "chunk_hydration", "reranking"] },
  { title: "Quiz", tools: ["quiz_generation", "quiz_validation", "quiz_persistence", "quiz_attempt_grading"] }
];

function toneForStatus(status: ToolRunStatus): "success" | "warning" | "error" | "info" | "neutral" {
  if (status === "succeeded") return "success";
  if (status === "failed") return "error";
  if (status === "running") return "warning";
  if (status === "queued") return "info";
  return "neutral";
}

function summarize(value: Record<string, unknown> | undefined): string {
  if (!value || Object.keys(value).length === 0) return "No output yet.";
  return Object.entries(value)
    .slice(0, 4)
    .map(([key, item]) => `${key}: ${String(item)}`)
    .join(" · ");
}

function duration(run: ToolRun): string {
  if (!run.created_at || !run.completed_at) return run.status === "running" ? "Running" : run.status;
  const elapsed = Math.max(0, new Date(run.completed_at).getTime() - new Date(run.created_at).getTime());
  return `${Math.round(elapsed / 100) / 10}s`;
}

function startedLabel(run: ToolRun): string {
  return run.created_at ? new Date(run.created_at).toLocaleString() : "-";
}

function completedLabel(run: ToolRun): string {
  if (run.completed_at) return new Date(run.completed_at).toLocaleString();
  if (run.status === "running") return "In progress";
  if (run.status === "queued") return "Not started";
  if (run.status === "failed") return "Failed";
  if (run.status === "succeeded") return "Completed";
  return "-";
}

function friendlyError(error: string): string {
  if (error.includes("Public transcript") || error.includes("No public transcript")) {
    return "Transcript unavailable. Audio fallback not configured.";
  }
  return error;
}

export function ProcessingTimeline({
  document,
  toolRuns
}: {
  document: Document | null;
  toolRuns: ToolRun[];
}) {
  const [showPrevious, setShowPrevious] = useState(false);
  if (!document) {
    return (
      <EmptyState
        icon="SEC"
        title="No active source"
        subtitle="Upload a source to watch extraction, chunking, embedding, and indexing."
      />
    );
  }

  if (toolRuns.length === 0) {
    return (
      <EmptyState
        icon="RUN"
        title="No tool runs yet"
        subtitle="Start ingestion to see each processing step as a secure timeline."
      />
    );
  }

  const sortedRuns = [...toolRuns].sort((left, right) => {
    if (left.status === "running" && right.status !== "running") return -1;
    if (right.status === "running" && left.status !== "running") return 1;
    return new Date(right.created_at ?? 0).getTime() - new Date(left.created_at ?? 0).getTime();
  });
  const latestByTool = new Set<string>();
  const latestRuns = sortedRuns.filter((run) => {
    if (latestByTool.has(run.tool_name)) return false;
    latestByTool.add(run.tool_name);
    return true;
  });
  const displayRuns = showPrevious ? sortedRuns : latestRuns;
  const hiddenCount = sortedRuns.length - latestRuns.length;
  const runsByStage = STAGES.map((stage) => ({
    ...stage,
    runs: displayRuns.filter((run) => stage.tools.includes(run.tool_name))
  })).filter((stage) => stage.runs.length > 0);

  return (
    <div className="processing-timeline">
      {runsByStage.map((stage) => (
        <section className="timeline-stage" key={stage.title}>
          <div className="timeline-stage-title">{stage.title}</div>
          {stage.runs.map((run) => (
            <details className={`timeline-item timeline-${run.status}`} key={run.id} open={run.status === "failed"}>
              <summary>
                <span className="timeline-dot" />
                <span className="timeline-copy">
                  <strong>{run.tool_name}</strong>
                  <small>{TOOL_EXPLANATIONS[run.tool_name] ?? "Runs a backend processing step."}</small>
                </span>
                <span className="timeline-meta">
                  <StatusBadge tone={toneForStatus(run.status)}>{run.status}</StatusBadge>
                  <small>{duration(run)}</small>
                </span>
              </summary>
              <div className="timeline-details">
                <p>
                  Started: {startedLabel(run)}
                </p>
                <p>
                  Completed: {completedLabel(run)}
                </p>
                {run.error ? (
                  <p className="error-text">Error: {friendlyError(run.error)}</p>
                ) : (
                  <p>Output: {summarize(run.output)}</p>
                )}
              </div>
            </details>
          ))}
        </section>
      ))}
      {hiddenCount > 0 ? (
        <button className="button-secondary" onClick={() => setShowPrevious((current) => !current)} type="button">
          {showPrevious ? "Hide previous runs" : `Show previous runs (${hiddenCount})`}
        </button>
      ) : null}
    </div>
  );
}
