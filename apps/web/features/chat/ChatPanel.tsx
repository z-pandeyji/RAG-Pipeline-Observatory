"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { ChatSkeleton } from "@/components/ui/ChatSkeleton";
import { EmptyState } from "@/components/ui/EmptyState";
import { SectionCard } from "@/components/ui/SectionCard";
import { CitationCards } from "@/features/chat/CitationCards";
import { apiClient } from "@/lib/api-client";
import type { Citation, Document } from "@/types/api";

type Message = {
  id: string;
  role: "user" | "assistant";
  text: string;
  citations?: Citation[];
  evidenceStatus?: "grounded" | "insufficient_evidence";
};

export function ChatPanel({
  workspaceId,
  userId,
  documents
}: {
  workspaceId: string;
  userId: string;
  documents: Document[];
}) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Persist messages to localStorage, scoped per workspace+user
  const storageKey = `chat_messages_${workspaceId}_${userId}`;

  // Hydrate from localStorage on mount
  useEffect(() => {
    try {
      const saved = window.localStorage.getItem(storageKey);
      if (saved) {
        const parsed = JSON.parse(saved) as Message[];
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
        }
      }
    } catch {
      // Corrupt data — ignore and start fresh
      window.localStorage.removeItem(storageKey);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);

  // Persist on every change
  useEffect(() => {
    if (messages.length === 0) return;
    try {
      window.localStorage.setItem(storageKey, JSON.stringify(messages));
    } catch {
      // Quota exceeded or private mode — silent fail
    }
  }, [messages, storageKey]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  async function sendMessage() {
    const query = input.trim();
    if (!query || isLoading) return;

    const userMessage: Message = {
      id: crypto.randomUUID(),
      role: "user",
      text: query
    };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setIsLoading(true);
    setError(null);

    try {
      const response = await apiClient.askGroundedQuestion({
        document_ids: documents.map((doc) => doc.id),
        query,
        user_id: userId,
        workspace_id: workspaceId
      });

      const assistantMessage: Message = {
        id: crypto.randomUUID(),
        role: "assistant",
        text: response.answer,
        citations: response.citations,
        evidenceStatus: response.evidence_status
      };
      setMessages((prev) => [...prev, assistantMessage]);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Request failed");
      setMessages((prev) => prev.filter((m) => m.id !== userMessage.id));
    } finally {
      setIsLoading(false);
    }
  }

  function handleKeyDown(event: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void sendMessage();
    }
  }

  function clearChat() {
    setMessages([]);
    window.localStorage.removeItem(storageKey);
  }

  const hasDocuments = documents.length > 0;

  return (
    <SectionCard
      action={messages.length > 0 ? (
        <button className="button-ghost" onClick={clearChat} type="button">
          Clear chat
        </button>
      ) : undefined}
      className="chat-panel"
      eyebrow="Ask your sources"
      title="Chat"
    >
      {!hasDocuments ? (
        <EmptyState
          icon="SRC"
          title="No indexed sources"
          subtitle="Index at least one PDF before starting a conversation."
        />
      ) : (
        <>
          <div className="chat-messages">
            {messages.length === 0 ? (
              <div className="chat-empty">
                <EmptyState
                  icon="ASK"
                  title="Ask a question"
                  subtitle="Ask anything about your indexed sources. Answers are grounded in retrieved evidence."
                />
              </div>
            ) : (
              messages.map((message) => (
                <div
                  className={`chat-message chat-message-${message.role}`}
                  key={message.id}
                >
                  <div className={`chat-bubble${message.role === "assistant" ? " chat-bubble-markdown" : ""}`}>
                    {message.role === "assistant" ? (
                      <ReactMarkdown remarkPlugins={[remarkGfm]}>
                        {message.text}
                      </ReactMarkdown>
                    ) : (
                      <p>{message.text}</p>
                    )}
                  </div>
                  {message.role === "assistant" ? (
                    <div className="chat-message-meta">
                      {message.evidenceStatus === "insufficient_evidence" ? (
                        <span className="status-badge status-badge-warning">
                          Insufficient evidence — answer may be incomplete
                        </span>
                      ) : message.citations && message.citations.length > 0 ? (
                        <details className="chat-citations">
                          <summary>
                            {message.citations.length} evidence citation{message.citations.length !== 1 ? "s" : ""}
                          </summary>
                          <CitationCards citations={message.citations} />
                        </details>
                      ) : null}
                    </div>
                  ) : null}
                </div>
              ))
            )}

            {isLoading ? (
              <div className="chat-message chat-message-assistant">
                <div className="chat-bubble chat-bubble-loading">
                  <ChatSkeleton />
                </div>
              </div>
            ) : null}

            <div ref={messagesEndRef} />
          </div>

          {error ? <p className="error-text">{error}</p> : null}

          <div className="chat-input-row">
            <textarea
              disabled={isLoading}
              onChange={(event) => setInput(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Ask a question about your sources… (Enter to send)"
              rows={2}
              value={input}
            />
            <button
              className="button-primary"
              disabled={isLoading || !input.trim()}
              onClick={() => void sendMessage()}
            >
              {isLoading ? "…" : "Send"}
            </button>
          </div>
        </>
      )}
    </SectionCard>
  );
}
