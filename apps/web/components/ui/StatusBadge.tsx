type StatusTone = "success" | "warning" | "error" | "info" | "neutral" | "locked";

export function StatusBadge({
  tone = "neutral",
  children
}: {
  tone?: StatusTone;
  children: React.ReactNode;
}) {
  return <span className={`status-badge status-badge-${tone}`}>{children}</span>;
}
