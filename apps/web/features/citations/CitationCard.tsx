import { SourceTypeBadge } from "@/components/ui/SourceTypeBadge";
import type { Citation } from "@/types/api";

function titleForCitation(citation: Citation): string {
  void citation;
  // if (citation.source_type === "youtube") return "Transcript evidence";   // YouTube disabled
  // if (citation.source_type === "image") return String(citation.metadata?.filename ?? "Image OCR evidence"); // Image disabled
  return "Document evidence";
}

function locationForCitation(citation: Citation): string {
  return citation.page_number ? `Page ${citation.page_number}` : "PDF source";
  // YouTube disabled:
  // if (citation.source_type === "youtube") {
  //   const start = citation.timestamp_start ?? "?";
  //   const end = citation.timestamp_end ?? "?";
  //   return `${start}s to ${end}s`;
  // }
  // Image disabled:
  // if (citation.image_region) return `Region ${JSON.stringify(citation.image_region)}`;
  // return "OCR text";
}

export function CitationCard({ citation }: { citation: Citation }) {
  return (
    <article className="citation-card evidence-receipt">
      <div className="citation-title">
        <div>
          <strong>{titleForCitation(citation)}</strong>
          <p className="citation-meta">{locationForCitation(citation)}</p>
        </div>
        <SourceTypeBadge sourceType={citation.source_type} />
      </div>
      <blockquote>{citation.text_snippet}</blockquote>
      <div className="citation-footer">
        <span>Evidence receipt</span>
        {/* YouTube URL link disabled */}
        {/* {citation.url ? (
          <a href={citation.url} rel="noreferrer" target="_blank">
            View source
          </a>
        ) : ( */}
          <button className="button-ghost" disabled>
            View source
          </button>
        {/* )} */}
      </div>
    </article>
  );
}
