"use client";

import { useState } from "react";

import { ProgressBar } from "@/components/ui/ProgressBar";
import { SectionCard } from "@/components/ui/SectionCard";
import { apiClient } from "@/lib/api-client";
import type { Document } from "@/types/api";

// YouTube and Image upload disabled — see commented code below
// YouTube upload: apiClient.createYoutubeDocument (commented in api-client.ts)
// Image upload: apiClient.uploadImageDocument (commented in api-client.ts)

export function SourceUploadPanel({
  workspaceId,
  userId,
  onUploaded,
  onIngest,
  isIngesting
}: {
  workspaceId: string;
  userId: string;
  onUploaded: (document: Pick<Document, "id" | "filename" | "source_type" | "status">) => void;
  onIngest: (documentId: string) => void;
  isIngesting: boolean;
}) {
  const [selectedPdf, setSelectedPdf] = useState<string | null>(null);
  const [lastDocumentId, setLastDocumentId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  async function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0] ?? null;
    if (!file) return;
    setSelectedPdf(file.name);
    setLastDocumentId(null);
    setError(null);
    setUploading(true);
    try {
      const response = await apiClient.uploadPdfDocument({
        file,
        user_id: userId,
        workspace_id: workspaceId
      });
      setLastDocumentId(response.document_id);
      onUploaded({
        filename: response.filename ?? file.name,
        id: response.document_id,
        source_type: "pdf",
        status: "uploaded"
      });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  const isStaged = !!lastDocumentId && !uploading;

  return (
    <SectionCard className="upload-panel" eyebrow="Upload sources" title="Add a PDF">
      <label className={`pdf-drop-zone${isStaged ? " pdf-drop-zone-filled" : ""}`}>
        <input accept="application/pdf" onChange={handleFileChange} type="file" />
        <span className="pdf-drop-icon">PDF</span>
        <div className="pdf-drop-copy">
          {selectedPdf ? (
            <>
              <strong>{selectedPdf}</strong>
              <span>Click to choose a different file</span>
            </>
          ) : (
            <>
              <strong>Drop a PDF or click to browse</strong>
              <span>Lecture notes, reports, and study material</span>
            </>
          )}
        </div>
      </label>

      {uploading ? <ProgressBar label="Uploading PDF…" value={38} /> : null}

      {isStaged ? (
        <div className="staged-source">
          <div className="staged-source-meta">
            <span className="small-label">Staged — ready to index</span>
            <span className="status-badge status-badge-info">uploaded</span>
          </div>
          {isIngesting ? <ProgressBar label="Indexing…" value={68} /> : null}
          <button
            className="button-primary"
            disabled={isIngesting}
            onClick={() => onIngest(lastDocumentId)}
          >
            {isIngesting ? "Indexing…" : "Index PDF"}
          </button>
        </div>
      ) : null}

      {error ? <p className="error-text">{error}</p> : null}
    </SectionCard>
  );
}
