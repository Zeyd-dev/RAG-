import { useEffect, useState } from "react";
import { api } from "../api/client.js";

/**
 * Modal shown when a citation chip is clicked. Fetches the exact chunk
 * text (source of truth for the citation) and highlights it, with a
 * link to open the original file for full context.
 */
export default function SourceViewer({ notebookId, citation, onClose }) {
  const [chunk, setChunk] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    if (!citation) return;
    setChunk(null);
    setError("");
    api
      .getChunk(notebookId, citation.document_id, citation.chunk_id)
      .then(setChunk)
      .catch((err) => setError(err.message));
  }, [citation, notebookId]);

  if (!citation) return null;

  return (
    <div
      className="fixed inset-0 bg-black/40 flex items-center justify-center z-50 px-4"
      onClick={onClose}
    >
      <div
        className="bg-white rounded-xl shadow-lg max-w-2xl w-full max-h-[80vh] overflow-y-auto p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start justify-between mb-4">
          <div>
            <h3 className="font-semibold text-slate-900">{citation.filename}</h3>
            {citation.page != null && (
              <p className="text-xs text-slate-400">Page {citation.page}</p>
            )}
          </div>
          <button onClick={onClose} className="text-slate-400 hover:text-slate-700 text-sm">
            Close
          </button>
        </div>

        {error && <div className="text-sm text-red-600 mb-3">{error}</div>}

        <div className="bg-brand-50 border border-brand-100 rounded-lg p-4 text-sm text-slate-800 leading-relaxed whitespace-pre-wrap">
          {chunk ? chunk.text : "Loading passage..."}
        </div>

        <a
          href={api.documentFileUrl(notebookId, citation.document_id)}
          target="_blank"
          rel="noreferrer"
          className="inline-block mt-4 text-sm text-brand-600 underline hover:text-brand-800"
        >
          Open original document
        </a>
      </div>
    </div>
  );
}
