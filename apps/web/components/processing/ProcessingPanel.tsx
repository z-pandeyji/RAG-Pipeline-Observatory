import type { Document, ToolRun } from "@/types/api";

import { StatusBadge } from "@/components/ui/StatusBadge";
import { ProcessingTimeline } from "@/features/processing-panel/ProcessingTimeline";

export function ProcessingPanel({
  document,
  toolRuns
}: {
  document: Document | null;
  toolRuns: ToolRun[];
}) {
  return (
    <aside className="panel processing-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">Processing</p>
          <h2>Learning pipeline</h2>
        </div>
        <StatusBadge tone={document?.status === "failed" ? "error" : document?.status === "indexed" ? "success" : "neutral"}>
          {document?.status ?? "No document"}
        </StatusBadge>
      </div>
      <ProcessingTimeline document={document} toolRuns={toolRuns} />
    </aside>
  );
}
