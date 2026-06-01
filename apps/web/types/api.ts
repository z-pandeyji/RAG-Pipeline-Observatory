// YouTube and image source types temporarily disabled
// export type SourceType = "pdf" | "youtube" | "image";
export type SourceType = "pdf";

export type DocumentStatus = "uploaded" | "queued" | "processing" | "indexed" | "failed";

export type Document = {
  id: string;
  workspace_id: string;
  user_id: string;
  filename: string;
  source_type: SourceType;
  status: DocumentStatus;
  page_count: number;
  error_message?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  chunk_count?: number;
};

export type DocumentChunk = {
  id: string;
  document_id: string;
  workspace_id: string;
  user_id: string;
  chunk_index: number;
  page_number?: number | null;
  source_type: SourceType;
  text: string;
  metadata: Record<string, unknown>;
};

export type ToolRunStatus = "queued" | "running" | "succeeded" | "failed";

export type ToolRun = {
  id: string;
  workspace_id: string;
  user_id: string;
  tool_name: string;
  status: ToolRunStatus;
  input: Record<string, unknown>;
  output: Record<string, unknown>;
  error?: string | null;
  created_at?: string;
  completed_at?: string | null;
};

export type Citation = {
  document_id: string;
  chunk_id: string;
  page_number?: number | null;
  // timestamp?: string | null;           // YouTube only
  // timestamp_start?: number | null;     // YouTube only
  // timestamp_end?: number | null;       // YouTube only
  // url?: string | null;                 // YouTube only
  // image_region?: Record<string, unknown> | null;  // Image only
  metadata?: Record<string, unknown>;
  source_type: SourceType;
  text_snippet: string;
};

export type GenerationResponse = {
  answer: string;
  citations: Citation[];
  tool_run_id: string;
  evidence_status: "grounded" | "insufficient_evidence";
};

export type QuizQuestion = {
  question_id: string;
  question: string;
  type: "mcq" | "short_answer" | "true_false";
  options: string[];
  citations: Citation[];
  answer_hidden: true;
};

export type Quiz = {
  quiz_id?: string | null;
  title: string;
  questions: QuizQuestion[];
  tool_run_id?: string | null;
  evidence_status: "grounded" | "insufficient_evidence";
};

export type QuizType = "mcq" | "short_answer" | "true_false" | "mixed";

export type QuizListItem = Quiz & {
  id?: string | null;
  quiz_id: string;
  document_id?: string | null;
  difficulty?: string | null;
  quiz_type?: QuizType | null;
  question_count?: number;
  created_at?: string | null;
  attempt_summary?: {
    attempted: number;
    correct: number;
  } | null;
};

export type QuizGenerationJob = {
  id: string;
  workspace_id: string;
  user_id: string;
  document_id?: string | null;
  query?: string | null;
  difficulty: string;
  quiz_type: string;
  requested_question_count: number;
  status: string;
  error_code?: string | null;
  error_message?: string | null;
  suggestion?: string | null;
  selected_chunk_ids: string[];
  source_count: number;
  created_quiz_id?: string | null;
  warning?: string | null;
  warnings?: string[];
  fallback_used?: boolean;
  created_at?: string | null;
  updated_at?: string | null;
  completed_at?: string | null;
};

export type QuizGenerationJobDebug = {
  job_id: string;
  status: string;
  difficulty: string;
  quiz_type: string;
  requested_question_count: number;
  selected_chunk_ids: string[];
  source_pack: Array<Record<string, unknown> & { text_preview?: string; text?: string }>;
  prompt_text?: string | null;
  raw_llm_response?: string | null;
  extracted_json?: string | null;
  repaired_llm_response?: string | null;
  validation_errors: unknown[];
  fallback_used: boolean;
  warnings: string[];
  timings: Record<string, unknown>;
};

export type ModelHarness = {
  provider: string;
  model: string;
  json_mode: boolean;
  temperature: number;
  embedding_provider: string;
  embedding_model: string;
  embedding_dimensions: number;
  vector_store: string;
  qdrant_collection: string;
  fallback: Record<string, unknown>;
};

export type SecurityChecks = {
  pdf_only: boolean;
  file_validation: string;
  workspace_user_filter: boolean;
  qdrant_filter: boolean;
  hidden_answer_key: boolean;
  attempt_grading: boolean;
  untrusted_pdf_text: boolean;
  local_model_no_db_access: boolean;
};

export type DocumentRagTrace = {
  document: Document;
  dataset_stats: {
    page_count: number;
    character_count: number;
    word_count: number;
    chunk_count: number;
    avg_chunk_size: number;
  };
  pages: Array<{
    page_number?: number | null;
    character_count: number;
    word_count: number;
    chunk_count: number;
  }>;
  chunks: DocumentChunk[];
  embedding_summary: {
    provider: string;
    model: string;
    dimensions: number;
    vector_count: number;
    chunk_target_chars: number;
    chunk_overlap_chars: number;
  };
  qdrant_summary: {
    collection: string;
    vector_store: string;
    vector_count: number;
    filter: Record<string, unknown>;
  };
  security_checks: SecurityChecks;
  tool_runs: ToolRun[];
};

export type QuizJobTrace = {
  job_id: string;
  source_pack: Array<Record<string, unknown> & { text?: string; text_preview?: string }>;
  prompts: {
    system?: string | null;
    user?: string | null;
    context?: string | null;
    final?: string | null;
    note?: string | null;
  };
  raw_llm_response?: string | null;
  extracted_json?: string | null;
  validation_errors: unknown[];
  fallback_used: boolean;
  warnings: string[];
  timings: Record<string, unknown>;
  model_harness: ModelHarness;
  security_checks: SecurityChecks;
};

export type EndpointTraceEntry = {
  id: string;
  method: string;
  path: string;
  status: number | "ERR";
  duration_ms: number;
  purpose: string;
  request_preview?: unknown;
  response_preview?: unknown;
  created_at: string;
};

export type QuizGenerateResponse = {
  quiz?: Quiz | null;
  job: QuizGenerationJob;
};

export type QuizAttemptResponse = {
  attempt_id: string;
  question_id: string;
  is_correct: boolean;
  score: number;
  correct_answer: string;
  explanation: string;
  citations: Citation[];
};

export type IngestionResponse = {
  document_id: string;
  status: string;
  tool_run_id: string;
  workspace_id?: string | null;
  user_id?: string | null;
  filename?: string | null;
  source_type?: SourceType | null;
};

export type DocumentListResponse = {
  documents: Document[];
};

export type QuizListResponse = {
  quizzes: QuizListItem[];
};

export type QuizGenerationJobListResponse = {
  jobs: QuizGenerationJob[];
};

export type DeleteResponse = {
  deleted: boolean;
  document_id?: string | null;
  quiz_id?: string | null;
  deleted_count?: number | null;
  message?: string;
};
