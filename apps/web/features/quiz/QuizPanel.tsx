"use client";

import { useCallback, useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SectionCard } from "@/components/ui/SectionCard";
import { ApiClientError, apiClient, isApiDebugEnabled } from "@/lib/api-client";
import { QuizCard } from "@/features/quiz/QuizCard";
import type { Document, Quiz, QuizAttemptResponse, QuizGenerationJob, QuizGenerationJobDebug, QuizListItem, QuizType } from "@/types/api";

type AttemptsByQuestion = Record<string, QuizAttemptResponse>;

const GENERATION_STEPS = [
  "Retrieving evidence",
  "Building context",
  "Generating questions",
  "Validating citations",
  "Saving quiz"
];

export function QuizPanel({
  workspaceId,
  userId,
  documents,
  onChanged
}: {
  workspaceId: string;
  userId: string;
  documents: Document[];
  onChanged?: () => void | Promise<void>;
}) {
  const [documentId, setDocumentId] = useState("");
  const [questionCount, setQuestionCount] = useState(3);
  const [difficulty, setDifficulty] = useState<"easy" | "medium" | "hard">("medium");
  const [quizType, setQuizType] = useState<QuizType>("mcq");
  const [quiz, setQuiz] = useState<Quiz | null>(null);
  const [savedQuizzes, setSavedQuizzes] = useState<QuizListItem[]>([]);
  const [selectedQuizId, setSelectedQuizId] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [attempts, setAttempts] = useState<AttemptsByQuestion>({});
  const [isGenerating, setIsGenerating] = useState(false);
  const [submittingQuestionId, setSubmittingQuestionId] = useState<string | null>(null);
  const [generationJob, setGenerationJob] = useState<QuizGenerationJob | null>(null);
  const [generationDebug, setGenerationDebug] = useState<QuizGenerationJobDebug | null>(null);
  const [generationJobs, setGenerationJobs] = useState<QuizGenerationJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [errorCode, setErrorCode] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const selectedDocument = useMemo(
    () => documents.find((document) => document.id === documentId) ?? null,
    [documentId, documents]
  );
  const answersKey = selectedQuizId ? `quiz_answers_${selectedQuizId}` : null;
  const attemptsKey = selectedQuizId ? `quiz_attempts_${selectedQuizId}` : null;

  const loadSavedQuizzes = useCallback(async () => {
    try {
      const response = await apiClient.listQuizzes(workspaceId, userId);
      const jobsResponse = await apiClient.listQuizGenerationJobs(workspaceId, userId);
      setSavedQuizzes(response.quizzes);
      setGenerationJobs(jobsResponse.jobs);
      const storedQuizId = window.localStorage.getItem("selectedQuizId");
      const selected =
        response.quizzes.find((item) => item.quiz_id === storedQuizId) ??
        response.quizzes[0] ??
        null;
      if (selected) {
        setSelectedQuizId(selected.quiz_id);
        window.localStorage.setItem("selectedQuizId", selected.quiz_id);
        const fullQuiz = await apiClient.getQuiz(selected.quiz_id, workspaceId, userId);
        setQuiz(fullQuiz);
      } else {
        setSelectedQuizId(null);
        setQuiz(null);
      }
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load saved quizzes");
    }
  }, [userId, workspaceId]);

  useEffect(() => {
    void loadSavedQuizzes();
  }, [loadSavedQuizzes]);

  useEffect(() => {
    if (!documentId && documents.length > 0) {
      setDocumentId(documents[0].id);
    }
  }, [documentId, documents]);

  // Restore answers + attempts from localStorage when quiz changes
  useEffect(() => {
    if (!answersKey || !attemptsKey) return;
    try {
      const savedAnswers = window.localStorage.getItem(answersKey);
      if (savedAnswers) setAnswers(JSON.parse(savedAnswers) as Record<string, string>);

      const savedAttempts = window.localStorage.getItem(attemptsKey);
      if (savedAttempts) setAttempts(JSON.parse(savedAttempts) as AttemptsByQuestion);
    } catch {
      // Corrupt data — ignore
    }
  }, [answersKey, attemptsKey]);

  // Persist answers on every change
  useEffect(() => {
    if (!answersKey || Object.keys(answers).length === 0) return;
    try {
      window.localStorage.setItem(answersKey, JSON.stringify(answers));
    } catch { /* quota exceeded — silent */ }
  }, [answers, answersKey]);

  // Persist attempts on every change
  useEffect(() => {
    if (!attemptsKey || Object.keys(attempts).length === 0) return;
    try {
      window.localStorage.setItem(attemptsKey, JSON.stringify(attempts));
    } catch { /* quota exceeded — silent */ }
  }, [attempts, attemptsKey]);

  useEffect(() => {
    if (!isGenerating) {
      setCurrentStep(0);
      return;
    }
    if (currentStep >= GENERATION_STEPS.length - 1) return;
    const timer = window.setTimeout(() => setCurrentStep((s) => s + 1), 1500);
    return () => window.clearTimeout(timer);
  }, [isGenerating, currentStep]);

  async function generateQuiz() {
    setIsGenerating(true);
    setError(null);
    setErrorCode(null);
    setAnswers({});
    setAttempts({});
    try {
      const response = await apiClient.generateQuiz({
        difficulty,
        document_id: documentId || undefined,
        question_count: questionCount,
        quiz_type: quizType,
        user_id: userId,
        workspace_id: workspaceId
      });
      setGenerationJob(response.job);
      if (isApiDebugEnabled) {
        const debug = await apiClient.getQuizGenerationJobDebug(response.job.id, workspaceId, userId);
        setGenerationDebug(debug);
      }
      if (response.quiz) {
        setQuiz(response.quiz);
      }
      if (response.quiz?.quiz_id) {
        setSelectedQuizId(response.quiz.quiz_id);
        window.localStorage.setItem("selectedQuizId", response.quiz.quiz_id);
      }
      await loadSavedQuizzes();
    } catch (caught) {
      const message = caught instanceof Error ? caught.message : "Quiz generation failed";
      setErrorCode(caught instanceof ApiClientError ? caught.errorCode ?? null : null);
      setError(message);
    } finally {
      setIsGenerating(false);
    }
  }

  async function selectSavedQuiz(quizId: string) {
    setError(null);
    setSelectedQuizId(quizId);
    window.localStorage.setItem("selectedQuizId", quizId);
    setAttempts({});
    setAnswers({});
    try {
      const response = await apiClient.getQuiz(quizId, workspaceId, userId);
      setQuiz(response);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not load quiz");
    }
  }

  async function deleteSavedQuiz(quizId: string) {
    const confirmed = window.confirm("Delete this saved quiz?");
    if (!confirmed) return;
    setError(null);
    try {
      await apiClient.deleteQuiz(quizId, workspaceId, userId);
      if (selectedQuizId === quizId) {
        setSelectedQuizId(null);
        setQuiz(null);
        window.localStorage.removeItem("selectedQuizId");
        window.localStorage.removeItem(`quiz_answers_${quizId}`);
        window.localStorage.removeItem(`quiz_attempts_${quizId}`);
      }
      await loadSavedQuizzes();
      await onChanged?.();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not delete quiz");
    }
  }

  async function submitAttempt(questionId: string) {
    if (!quiz?.quiz_id || !answers[questionId]) return;
    setSubmittingQuestionId(questionId);
    setError(null);
    try {
      const response = await apiClient.submitQuizAttempt({
        question_id: questionId,
        quiz_id: quiz.quiz_id,
        user_answer: answers[questionId],
        user_id: userId,
        workspace_id: workspaceId
      });
      setAttempts((current) => ({ ...current, [questionId]: response }));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Attempt submission failed");
    } finally {
      setSubmittingQuestionId(null);
    }
  }

  return (
    <SectionCard className="quiz-panel" eyebrow="Generated quizzes" title="Practice from evidence">

      <div className="quiz-controls">
        <div className="quiz-source-row">
          <label>
            Source
            <select onChange={(event) => setDocumentId(event.target.value)} value={documentId}>
              <option value="">All documents</option>
              {documents.map((document) => (
                <option key={document.id} value={document.id}>
                  {document.filename}
                </option>
              ))}
            </select>
          </label>
        </div>
        <div className="quiz-params-row">
          <label>
            Difficulty
            <select onChange={(event) => setDifficulty(event.target.value as typeof difficulty)} value={difficulty}>
              <option value="easy">Easy</option>
              <option value="medium">Medium</option>
              <option value="hard">Hard</option>
            </select>
          </label>
          <label>
            Type
            <select onChange={(event) => setQuizType(event.target.value as QuizType)} value={quizType}>
              <option value="mcq">MCQ</option>
              <option value="short_answer">Short answer</option>
              <option value="true_false">True / False</option>
              <option value="mixed">Mixed</option>
            </select>
          </label>
          <label>
            Questions
            <input
              max={10}
              min={1}
              onChange={(event) => setQuestionCount(Number(event.target.value))}
              type="number"
              value={questionCount}
            />
          </label>
        </div>
        <button className="button-primary quiz-generate-btn" disabled={isGenerating || documents.length === 0} onClick={generateQuiz}>
          {isGenerating ? "Generating..." : "Generate quiz"}
        </button>
      </div>

      {selectedDocument ? (
        <div className="selected-source-summary">
          <div>
            <span className="small-label">Selected source</span>
            <strong>{selectedDocument.filename}</strong>
          </div>
          <div className="document-meta-row">
            <span className="small-label">{selectedDocument.source_type.toUpperCase()}</span>
            <span className="small-label">{selectedDocument.chunk_count ?? 0} chunks</span>
            <span className="status-badge status-badge-success">Ready for quiz</span>
          </div>
        </div>
      ) : documents.length === 0 ? (
        <EmptyState
          icon="SRC"
          title="Upload and index a source"
          subtitle="A saved, indexed source is required before quiz generation."
        />
      ) : null}

      {savedQuizzes.length > 0 ? (
        <div className="saved-quiz-panel">
          <div className="quiz-title-row">
            <h3>Saved quizzes</h3>
            <span className="status-badge status-badge-success">Synced</span>
          </div>
          <div className="document-list">
            {savedQuizzes.map((item) => (
              <button
                className={selectedQuizId === item.quiz_id ? "document-row active" : "document-row"}
                key={item.quiz_id}
                onClick={() => void selectSavedQuiz(item.quiz_id)}
                type="button"
              >
                <span className="document-title-line">
                  <span>{item.title}</span>
                  <span
                    className="delete-action"
                    onClick={(event) => {
                      event.stopPropagation();
                      void deleteSavedQuiz(item.quiz_id);
                    }}
                    role="button"
                    tabIndex={0}
                  >
                    Delete
                  </span>
                </span>
                <div className="document-meta-row">
                  <span className="small-label">{item.difficulty ?? "saved"}</span>
                  <span className="small-label">{item.quiz_type ?? "quiz"}</span>
                  <span className="small-label">{item.question_count ?? item.questions.length} questions</span>
                  {item.created_at ? <span className="small-label">{new Date(item.created_at).toLocaleDateString()}</span> : null}
                  <span className="status-badge status-badge-locked">Answers hidden</span>
                </div>
              </button>
            ))}
          </div>
        </div>
      ) : null}

      {isGenerating ? (
        <div className="generation-stepper">
          {GENERATION_STEPS.map((step, index) => (
            <div
              className={
                index === currentStep
                  ? "generation-step generation-step-active"
                  : index < currentStep
                    ? "generation-step generation-step-done"
                    : "generation-step generation-step-pending"
              }
              key={step}
            >
              <span>{index + 1}</span>
              <p>{step}</p>
            </div>
          ))}
          <ProgressBar indeterminate label="Generating quiz…" />
          {generationJob ? (
            <p className="small-label">Job: {generationJob.status} · using {generationJob.source_count} evidence chunks</p>
          ) : null}
        </div>
      ) : null}

      {!isGenerating && generationJob?.status === "succeeded" ? (
        <div className={`quiz-evidence-summary${generationJob.source_count < 3 ? " quiz-evidence-warning" : ""}`}>
          <span>
            Generated from <strong>{generationJob.source_count}</strong> evidence chunk{generationJob.source_count !== 1 ? "s" : ""}
          </span>
          {generationJob.source_count < 3 ? (
            <span className="status-badge status-badge-warning">Low evidence — index more material for better results</span>
          ) : (
            <span className="status-badge status-badge-success">Evidence grounded</span>
          )}
        </div>
      ) : null}

      {generationJobs.some((job) => job.status === "failed") ? (
        <details className="generation-history">
          <summary>Generation history</summary>
          {generationJobs
            .filter((job) => job.status === "failed")
            .slice(0, 4)
            .map((job) => (
              <p key={job.id}>
                {job.error_code ?? "FAILED"}: {job.suggestion ?? job.error_message ?? "Generation failed"}
              </p>
            ))}
        </details>
      ) : null}

      {isApiDebugEnabled && generationDebug ? (
        <details className="generation-debug-panel">
          <summary>Quiz generation debug</summary>
          <p className="debug-warning">
            Debug data may include hidden answer information. Do not show this in production.
          </p>
          <div className="debug-grid">
            <DebugBlock title="Job status" value={JSON.stringify({
              status: generationDebug.status,
              fallback_used: generationDebug.fallback_used,
              warnings: generationDebug.warnings,
              timings: generationDebug.timings
            }, null, 2)} />
            <DebugBlock title="DB chunks selected" value={generationDebug.selected_chunk_ids.join("\n")} />
            <DebugBlock title="Source pack sent to model" value={JSON.stringify(generationDebug.source_pack, null, 2)} />
            <DebugBlock title="Prompt sent to model" value={generationDebug.prompt_text ?? ""} collapsed />
            <DebugBlock title="Model response" value={generationDebug.raw_llm_response ?? ""} collapsed />
            <DebugBlock title="Extracted JSON" value={generationDebug.extracted_json ?? ""} collapsed />
            <DebugBlock title="Repaired response" value={generationDebug.repaired_llm_response ?? ""} collapsed />
            <DebugBlock title="Validation errors" value={JSON.stringify(generationDebug.validation_errors, null, 2)} />
          </div>
        </details>
      ) : null}

      {error ? (
        <div className="quiz-error-card">
          <strong>Quiz generation needs another try</strong>
          <p>
            {errorCode === "QUIZ_INVALID_JSON"
              ? "The local model returned malformed JSON. Try again or reduce question count."
              : errorCode === "QUIZ_VALIDATION_FAILED" || errorCode === "QUIZ_SCHEMA_VALIDATION_FAILED" || errorCode === "QUIZ_MCQ_INVALID_OPTIONS"
                ? "The model generated a quiz that failed validation. Try another difficulty."
                : errorCode === "INSUFFICIENT_EVIDENCE"
                  ? "Not enough source content was retrieved for a quiz."
                  : error}
          </p>
          <div className="quiz-actions">
            <button className="button-secondary" onClick={generateQuiz} type="button">Retry</button>
            <button className="button-secondary" onClick={() => setQuestionCount(3)} type="button">Try 3 questions</button>
            <button className="button-secondary" onClick={() => setDifficulty("easy")} type="button">Switch to Easy</button>
          </div>
        </div>
      ) : null}
      {quiz?.evidence_status === "insufficient_evidence" ? (
        <EmptyState
          icon="EV"
          title="Insufficient evidence"
          subtitle="Index more source material or choose a different document before generating a quiz."
        />
      ) : quiz ? (
        <div className="quiz-list">
          <div className="quiz-title-row">
            <h3>{quiz.title}</h3>
            <span className="status-badge status-badge-locked">Answers locked</span>
          </div>
          {quiz.questions.map((question, index) => (
            <QuizCard
              answer={answers[question.question_id] ?? ""}
              attempt={attempts[question.question_id]}
              index={index}
              isSubmitting={submittingQuestionId === question.question_id}
              key={question.question_id}
              onAnswer={(value) =>
                setAnswers((current) => ({
                  ...current,
                  [question.question_id]: value
                }))
              }
              onSubmit={() => submitAttempt(question.question_id)}
              question={question}
              total={quiz.questions.length}
            />
          ))}
        </div>
      ) : (
        <EmptyState
          action={<button className="button-secondary" disabled={documents.length === 0} onClick={generateQuiz}>Generate quiz</button>}
          icon="QUIZ"
          title="No quiz generated"
          subtitle="Generate practice questions after at least one source is indexed."
        />
      )}
    </SectionCard>
  );
}

function DebugBlock({ title, value, collapsed = false }: { title: string; value: string; collapsed?: boolean }) {
  const content = value || "-";
  return (
    <details className="debug-block" open={!collapsed}>
      <summary>{title}</summary>
      <button
        className="button-ghost"
        onClick={() => void navigator.clipboard?.writeText(content)}
        type="button"
      >
        Copy
      </button>
      <pre>{content}</pre>
    </details>
  );
}
