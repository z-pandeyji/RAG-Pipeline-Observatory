import type {
  Document,
  DocumentChunk,
  DocumentRagTrace,
  DocumentListResponse,
  DeleteResponse,
  EndpointTraceEntry,
  GenerationResponse,
  IngestionResponse,
  ModelHarness,
  Quiz,
  QuizAttemptResponse,
  QuizGenerateResponse,
  QuizGenerationJobDebug,
  QuizGenerationJob,
  QuizGenerationJobListResponse,
  QuizJobTrace,
  QuizListResponse,
  ToolRun
} from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000";
const DEBUG_API = process.env.NEXT_PUBLIC_DEBUG_API === "true";
export const isApiDebugEnabled = DEBUG_API;
// Contract strings kept visible for API route tests:
// `${API_BASE_URL}/api/quizzes?${query
// `${API_BASE_URL}/api/quizzes/generate`
const endpointTrace: EndpointTraceEntry[] = [];
const endpointTraceListeners = new Set<() => void>();

export class ApiClientError extends Error {
  errorCode?: string;
  suggestion?: string;

  constructor(message: string, errorCode?: string, suggestion?: string) {
    super(message);
    this.name = "ApiClientError";
    this.errorCode = errorCode;
    this.suggestion = suggestion;
  }
}

function debugApi(label: string, data: unknown): void {
  if (DEBUG_API) {
    console.log(`[API_DEBUG] ${label}`, data);
  }
}

async function readJson<T>(response: Response, debugLabel?: string): Promise<T> {
  const payload = await response.json().catch(() => ({}));
  if (debugLabel) {
    debugApi(`${debugLabel} response status`, response.status);
    debugApi(
      response.ok ? `${debugLabel} response body` : `${debugLabel} error body`,
      payload
    );
  }
  if (!response.ok) {
    const message =
      typeof payload.detail === "string"
        ? payload.detail
        : typeof payload.detail?.message === "string"
          ? payload.detail.message
          : "Request failed";
    throw new ApiClientError(message, payload.error_code, payload.suggestion);
  }
  return payload as T;
}

function preview(value: unknown): unknown {
  if (value instanceof FormData) {
    return Array.from(value.keys()).reduce<Record<string, string>>((acc, key) => {
      acc[key] = key === "file" ? "[file]" : String(value.get(key));
      return acc;
    }, {});
  }
  if (typeof value === "string") return value.slice(0, 900);
  if (!value || typeof value !== "object") return value;
  try {
    return JSON.parse(JSON.stringify(value).slice(0, 1800));
  } catch {
    return "[unserializable]";
  }
}

function recordTrace(entry: EndpointTraceEntry): void {
  endpointTrace.unshift(entry);
  endpointTrace.splice(80);
  endpointTraceListeners.forEach((listener) => listener());
}

async function tracedFetch<T>(
  path: string,
  init: RequestInit | undefined,
  purpose: string,
  requestPreview?: unknown,
  debugLabel?: string
): Promise<T> {
  const started = performance.now();
  const method = init?.method ?? "GET";
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, init);
    const clone = response.clone();
    const payload = await readJson<T>(response, debugLabel);
    const responsePreview = await clone.json().catch(() => payload);
    recordTrace({
      created_at: new Date().toISOString(),
      duration_ms: Math.round(performance.now() - started),
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      method,
      path,
      purpose,
      request_preview: preview(requestPreview),
      response_preview: preview(responsePreview),
      status: clone.status
    });
    return payload;
  } catch (caught) {
    recordTrace({
      created_at: new Date().toISOString(),
      duration_ms: Math.round(performance.now() - started),
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      method,
      path,
      purpose,
      request_preview: preview(requestPreview),
      response_preview: caught instanceof Error ? caught.message : "Request failed",
      status: "ERR"
    });
    throw caught;
  }
}

function query(params: Record<string, string>): string {
  return new URLSearchParams(params).toString();
}

export const apiClient = {
  // YouTube ingestion disabled
  // async createYoutubeDocument(input: {
  //   workspace_id: string;
  //   user_id: string;
  //   youtube_url: string;
  //   title?: string;
  // }): Promise<IngestionResponse> {
  //   const response = await fetch(`${API_BASE_URL}/api/documents/youtube`, {
  //     body: JSON.stringify(input),
  //     headers: { "Content-Type": "application/json" },
  //     method: "POST"
  //   });
  //   return readJson<IngestionResponse>(response);
  // },

  async listDocuments(workspaceId: string, userId: string): Promise<DocumentListResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/documents?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`
    );
    return readJson<DocumentListResponse>(response);
  },

  // Image ingestion disabled
  // async uploadImageDocument(input: {
  //   workspace_id: string;
  //   user_id: string;
  //   title?: string;
  //   file: File;
  // }): Promise<IngestionResponse> {
  //   const form = new FormData();
  //   form.append("workspace_id", input.workspace_id);
  //   form.append("user_id", input.user_id);
  //   if (input.title) form.append("title", input.title);
  //   form.append("file", input.file);
  //   const response = await fetch(`${API_BASE_URL}/api/documents/image`, {
  //     body: form,
  //     method: "POST"
  //   });
  //   return readJson<IngestionResponse>(response);
  // },

  async uploadPdfDocument(input: {
    workspace_id: string;
    user_id: string;
    file: File;
  }): Promise<IngestionResponse> {
    const form = new FormData();
    form.append("workspace_id", input.workspace_id);
    form.append("user_id", input.user_id);
    form.append("file", input.file);
    return tracedFetch<IngestionResponse>(
      "/api/ingestion/documents/pdf",
      { body: form, method: "POST" },
      "Upload PDF",
      form
    );
  },

  async ingestDocument(documentId: string, workspaceId: string, userId: string): Promise<IngestionResponse> {
    const path = `/api/documents/${documentId}/ingest?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<IngestionResponse>(path, { method: "POST" }, "Index PDF");
  },

  async getDocumentStatus(documentId: string, workspaceId: string, userId: string): Promise<Document> {
    const path = `/api/documents/${documentId}/status?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<Document>(path, undefined, "Document status");
  },

  async deleteDocument(documentId: string, workspaceId: string, userId: string): Promise<DeleteResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/documents/${documentId}?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`,
      { method: "DELETE" }
    );
    return readJson<DeleteResponse>(response);
  },

  async clearFailedDocuments(workspaceId: string, userId: string): Promise<DeleteResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/documents/failed?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`,
      { method: "DELETE" }
    );
    return readJson<DeleteResponse>(response);
  },

  async getDocumentChunks(documentId: string, workspaceId: string, userId: string): Promise<DocumentChunk[]> {
    const path = `/api/documents/${documentId}/chunks?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<DocumentChunk[]>(path, undefined, "Document chunks");
  },

  async getDocumentRagTrace(documentId: string, workspaceId: string, userId: string): Promise<DocumentRagTrace> {
    const path = `/api/documents/${documentId}/rag-trace?${query({
      workspace_id: workspaceId,
      user_id: userId
    })}`;
    return tracedFetch<DocumentRagTrace>(path, undefined, "RAG trace");
  },

  async getDocumentToolRuns(documentId: string, workspaceId: string, userId: string): Promise<ToolRun[]> {
    const path = `/api/documents/${documentId}/tool-runs?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<ToolRun[]>(path, undefined, "Document tool runs");
  },

  async generateQuiz(input: {
    workspace_id: string;
    user_id: string;
    document_id?: string;
    query?: string;
    question_count: number;
    difficulty: "easy" | "medium" | "hard";
    quiz_type: "mcq" | "short_answer" | "true_false" | "mixed";
  }): Promise<QuizGenerateResponse> {
    debugApi("generateQuiz request payload", input);
    return tracedFetch<QuizGenerateResponse>("/api/quizzes/generate", {
      body: JSON.stringify(input),
      headers: { "Content-Type": "application/json" },
      method: "POST"
    }, "Generate quiz", input, "generateQuiz");
  },

  async getQuizGenerationJob(jobId: string, workspaceId: string, userId: string): Promise<QuizGenerationJob> {
    const path = `/api/quizzes/jobs/${jobId}?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<QuizGenerationJob>(path, undefined, "Quiz job");
  },

  async getQuizGenerationJobDebug(jobId: string, workspaceId: string, userId: string): Promise<QuizGenerationJobDebug> {
    const path = `/api/quizzes/jobs/${jobId}/debug?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<QuizGenerationJobDebug>(path, undefined, "Quiz debug", undefined, "getQuizGenerationJobDebug");
  },

  async getQuizGenerationJobTrace(jobId: string, workspaceId: string, userId: string): Promise<QuizJobTrace> {
    const path = `/api/quizzes/jobs/${jobId}/trace?${query({
      workspace_id: workspaceId,
      user_id: userId
    })}`;
    return tracedFetch<QuizJobTrace>(path, undefined, "Prompt trace");
  },

  async listQuizGenerationJobs(workspaceId: string, userId: string): Promise<QuizGenerationJobListResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/quizzes/jobs?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`
    );
    return readJson<QuizGenerationJobListResponse>(response);
  },

  async listQuizzes(workspaceId: string, userId: string): Promise<QuizListResponse> {
    const path = `/api/quizzes?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<QuizListResponse>(path, undefined, "List quizzes");
  },

  async getQuiz(quizId: string, workspaceId: string, userId: string): Promise<Quiz> {
    const path = `/api/quizzes/${quizId}?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`;
    return tracedFetch<Quiz>(path, undefined, "Load quiz");
  },

  async deleteQuiz(quizId: string, workspaceId: string, userId: string): Promise<DeleteResponse> {
    const response = await fetch(
      `${API_BASE_URL}/api/quizzes/${quizId}?${query({
        workspace_id: workspaceId,
        user_id: userId
      })}`,
      { method: "DELETE" }
    );
    return readJson<DeleteResponse>(response);
  },

  async submitQuizAttempt(input: {
    quiz_id: string;
    workspace_id: string;
    user_id: string;
    question_id: string;
    user_answer: string;
  }): Promise<QuizAttemptResponse> {
    const payload = {
      question_id: input.question_id,
      user_answer: input.user_answer,
      user_id: input.user_id,
      workspace_id: input.workspace_id
    };
    debugApi("submitQuizAttempt request payload", {
      quiz_id: input.quiz_id,
      ...payload
    });
    return tracedFetch<QuizAttemptResponse>(`/api/quizzes/${input.quiz_id}/attempt`, {
      body: JSON.stringify(payload),
      headers: { "Content-Type": "application/json" },
      method: "POST"
    }, "Submit attempt", payload, "submitQuizAttempt");
  },

  async askGroundedQuestion(input: {
    workspace_id: string;
    user_id: string;
    query: string;
    document_ids?: string[];
  }): Promise<GenerationResponse> {
    const payload = { ...input, document_ids: input.document_ids ?? [] };
    debugApi("askGroundedQuestion request payload", payload);
    return tracedFetch<GenerationResponse>("/api/generation/answer", {
      body: JSON.stringify(payload),
      headers: { "Content-Type": "application/json" },
      method: "POST"
    }, "Ask grounded question", payload, "askGroundedQuestion");
  },

  async listToolRuns(workspaceId: string, userId: string): Promise<ToolRun[]> {
    const path = `/api/tool-runs?${query({
      workspace_id: workspaceId,
      user_id: userId
    })}`;
    return tracedFetch<ToolRun[]>(path, undefined, "Backend timeline");
  },

  async getModelHarness(): Promise<ModelHarness> {
    return tracedFetch<ModelHarness>("/api/system/model-harness", undefined, "Model harness");
  }
};

export function getEndpointTrace(): EndpointTraceEntry[] {
  return [...endpointTrace];
}

export function subscribeEndpointTrace(listener: () => void): () => void {
  endpointTraceListeners.add(listener);
  return () => endpointTraceListeners.delete(listener);
}
