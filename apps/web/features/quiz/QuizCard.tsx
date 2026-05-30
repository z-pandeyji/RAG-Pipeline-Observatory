import { EmptyState } from "@/components/ui/EmptyState";
import { ProgressBar } from "@/components/ui/ProgressBar";
import { SourceTypeBadge } from "@/components/ui/SourceTypeBadge";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { CitationCards } from "@/features/chat/CitationCards";
import { useState } from "react";
import type { QuizAttemptResponse, QuizQuestion } from "@/types/api";

export function QuizCard({
  question,
  index,
  total,
  answer,
  attempt,
  isSubmitting,
  onAnswer,
  onSubmit
}: {
  question: QuizQuestion;
  index: number;
  total: number;
  answer: string;
  attempt?: QuizAttemptResponse;
  isSubmitting: boolean;
  onAnswer: (value: string) => void;
  onSubmit: () => void;
}) {
  const progress = total > 0 ? ((index + 1) / total) * 100 : 0;
  const [showEvidence, setShowEvidence] = useState(false);
  const primaryCitation = question.citations[0] ?? attempt?.citations[0];

  return (
    <article className="quiz-question learning-card">
      <div className="question-top">
        <div>
          <span className="small-label">Question {index + 1} of {total}</span>
          <h3>{question.question}</h3>
        </div>
        <StatusBadge tone={attempt ? (attempt.is_correct ? "success" : "error") : "locked"}>
          {attempt ? (attempt.is_correct ? "Correct" : "Review") : "Answer hidden"}
        </StatusBadge>
      </div>
      <ProgressBar label="Quiz progress" value={progress} />

      {question.options.length > 0 ? (
        <div className="options-list">
          {question.options.map((option) => {
            const selected = answer === option;
            const isCorrect = attempt?.correct_answer === option;
            const isWrongSelection = Boolean(attempt && selected && !attempt.is_correct);
            const className = [
              "option-card",
              selected ? "option-card-selected" : "",
              isCorrect ? "option-card-correct" : "",
              isWrongSelection ? "option-card-wrong" : ""
            ]
              .filter(Boolean)
              .join(" ");
            return (
              <button className={className} key={option} onClick={() => onAnswer(option)} type="button">
                <span className="radio-dot" />
                <span>{option}</span>
              </button>
            );
          })}
        </div>
      ) : (
        <input onChange={(event) => onAnswer(event.target.value)} placeholder="Your answer" value={answer} />
      )}

      <div className="quiz-actions">
        <button className="button-primary" disabled={isSubmitting || !answer} onClick={onSubmit}>
          {isSubmitting ? "Submitting..." : "Submit attempt"}
        </button>
        <StatusBadge tone="info">{question.citations.length} evidence source{question.citations.length === 1 ? "" : "s"}</StatusBadge>
      </div>

      {attempt ? (
        <div className={attempt.is_correct ? "attempt correct" : "attempt incorrect"}>
          <div className="attempt-heading">
            <strong>{attempt.is_correct ? "Mastered" : "Review with evidence"}</strong>
            <span>Score {attempt.score}</span>
          </div>
          <p>
            <span className="small-label">Correct answer</span>
            <strong>{attempt.correct_answer}</strong>
          </p>
          <p>{attempt.explanation}</p>
          <button className="button-secondary" onClick={() => setShowEvidence((current) => !current)} type="button">
            {showEvidence ? "Hide evidence" : "Expand evidence"}
          </button>
          {showEvidence ? <CitationCards citations={attempt.citations} /> : null}
        </div>
      ) : question.citations.length > 0 ? (
        <div className="compact-evidence">
          <StatusBadge tone="info">
            {question.citations.length} evidence source{question.citations.length === 1 ? "" : "s"}
          </StatusBadge>
          {primaryCitation ? (
            <>
              <SourceTypeBadge sourceType={primaryCitation.source_type} />
              <span className="small-label">
                {primaryCitation.page_number
                  ? `Page ${primaryCitation.page_number}`
                  // : primaryCitation.timestamp_start != null  // YouTube timestamp disabled
                  //   ? `${primaryCitation.timestamp_start}s`
                  : "Source"}
              </span>
            </>
          ) : null}
          <button className="button-ghost" onClick={() => setShowEvidence((current) => !current)} type="button">
            {showEvidence ? "Hide evidence" : "View evidence"}
          </button>
          {showEvidence ? <CitationCards citations={question.citations} /> : null}
        </div>
      ) : (
        <EmptyState icon="EV" title="Evidence pending" subtitle="Citations will appear with this question." />
      )}
    </article>
  );
}
