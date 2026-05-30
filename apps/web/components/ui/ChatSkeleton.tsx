export function ChatSkeleton() {
  return (
    <div className="chat-skeleton" aria-label="Generating answer…" role="status">
      <div className="chat-skeleton-line" style={{ width: "88%" }} />
      <div className="chat-skeleton-line" style={{ width: "72%" }} />
      <div className="chat-skeleton-line" style={{ width: "54%" }} />
    </div>
  );
}
