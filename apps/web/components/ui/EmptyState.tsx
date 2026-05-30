export function EmptyState({
  icon,
  title,
  subtitle,
  action
}: {
  icon: string;
  title: string;
  subtitle: string;
  action?: React.ReactNode;
}) {
  return (
    <div className="empty-state">
      <div className="empty-icon">{icon}</div>
      <div>
        <strong>{title}</strong>
        <p>{subtitle}</p>
      </div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}
