import type { SourceType } from "@/types/api";

const LABELS: Record<SourceType, string> = {
  // image: "Image",    // Image disabled
  pdf: "PDF",
  // youtube: "YouTube" // YouTube disabled
};

export function SourceTypeBadge({ sourceType }: { sourceType: SourceType }) {
  return <span className={`source-type-badge source-type-${sourceType}`}>{LABELS[sourceType]}</span>;
}
