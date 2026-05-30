export function ProgressBar({
  value,
  label,
  indeterminate = false
}: {
  value?: number;
  label?: string;
  indeterminate?: boolean;
}) {
  const safeValue = value !== undefined ? Math.max(0, Math.min(100, value)) : 0;
  return (
    <div
      aria-label={label}
      aria-valuemax={100}
      aria-valuemin={0}
      aria-valuenow={indeterminate ? undefined : safeValue}
      className="progress-wrap"
      role="progressbar"
    >
      <div className="progress-track">
        <div
          className={indeterminate ? "progress-fill progress-fill-indeterminate" : "progress-fill"}
          style={indeterminate ? undefined : { width: `${safeValue}%` }}
        />
      </div>
      {label ? <span className="progress-label">{label}</span> : null}
    </div>
  );
}
