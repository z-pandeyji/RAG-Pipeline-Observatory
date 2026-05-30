import type { Citation } from "@/types/api";

import { CitationCard } from "@/features/citations/CitationCard";

export function CitationCards({ citations }: { citations: Citation[] }) {
  if (citations.length === 0) return null;

  return (
    <div className="citation-list">
      {citations.map((citation) => (
        <CitationCard citation={citation} key={`${citation.document_id}-${citation.chunk_id}`} />
      ))}
    </div>
  );
}
