import { useEffect, useRef, useState } from "react";
import { api } from "../api/client.js";

const STATUS_STYLES = {
  processing: { pill: "bg-amber-50 text-amber-700 border-amber-200", dot: "bg-amber-500 animate-pulse" },
  ready: { pill: "bg-emerald-50 text-emerald-700 border-emerald-200", dot: "bg-emerald-500" },
  failed: { pill: "bg-red-50 text-red-700 border-red-200", dot: "bg-red-500" },
};

export default function UploadPanel({ notebookId }) {
  const [documents, setDocuments] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [error, setError] = useState("");
  const fileInputRef = useRef(null);

  const [driveUrl, setDriveUrl] = useState("");
  const [importing, setImporting] = useState(false);
  const [importNote, setImportNote] = useState("");
  const [showDriveForm, setShowDriveForm] = useState(false);

  const load = async () => {
    try {
      setDocuments(await api.listDocuments(notebookId));
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
    const interval = setInterval(load, 3000); // poll for processing -> ready status
    return () => clearInterval(interval);
  }, [notebookId]);

  const handleFileChange = async (e) => {
    // FileList isn't a real array -- Array.from() it so multi-select
    // (the "multiple" attribute on the input below) works the same way
    // whether the user picks one file or several.
    const files = Array.from(e.target.files || []);
    if (files.length === 0) return;
    setUploading(true);
    setError("");
    let failed = 0;
    for (let i = 0; i < files.length; i++) {
      if (files.length > 1) setUploadStatus(`Uploading ${i + 1}/${files.length}...`);
      try {
        // Uploaded one at a time (not Promise.all) so a slow or failing
        // file doesn't block/skew the others, and so the progress label
        // above reflects real sequential progress instead of jumping.
        await api.uploadDocument(notebookId, files[i]);
      } catch (err) {
        failed += 1;
      }
    }
    await load();
    setUploading(false);
    setUploadStatus("");
    if (failed > 0) {
      setError(`${failed} of ${files.length} file(s) failed to upload.`);
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDelete = async (documentId) => {
    await api.deleteDocument(notebookId, documentId);
    load();
  };

  const handleDriveImport = async (e) => {
    e.preventDefault();
    const url = driveUrl.trim();
    if (!url || importing) return;
    setImporting(true);
    setError("");
    setImportNote("");
    try {
      const res = await api.importFromDrive(notebookId, url);
      const count = res.imported.length;
      setImportNote(
        count === 0
          ? "No supported files were imported."
          : `Importing ${count} file${count === 1 ? "" : "s"} from Drive — they'll show as "processing" below, then "ready".` +
              (res.skipped ? ` (${res.skipped} file(s) skipped — unsupported type.)` : "")
      );
      setDriveUrl("");
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setImporting(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-sm font-semibold text-slate-900">Documents</h2>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowDriveForm((v) => !v)}
            className="text-xs border border-slate-300 text-slate-600 rounded-lg px-3 py-1.5 hover:border-brand-300 hover:text-brand-700 transition-colors"
          >
            From Drive
          </button>
          <label className="text-xs bg-brand-600 text-white rounded-lg px-3 py-1.5 cursor-pointer hover:bg-brand-700 transition-colors">
            {uploading ? uploadStatus || "Uploading..." : "Upload"}
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf,.docx,.txt,.md,.markdown"
              className="hidden"
              onChange={handleFileChange}
              disabled={uploading}
              multiple
            />
          </label>
        </div>
      </div>

      {showDriveForm && (
        <form onSubmit={handleDriveImport} className="mb-3 flex gap-2">
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400"
            placeholder="Paste a Google Drive folder link..."
            value={driveUrl}
            onChange={(e) => setDriveUrl(e.target.value)}
          />
          <button
            disabled={importing}
            className="text-xs bg-brand-600 text-white rounded-lg px-3 py-1.5 hover:bg-brand-700 disabled:opacity-50 transition-colors shrink-0"
          >
            {importing ? "Importing..." : "Import"}
          </button>
        </form>
      )}

      {importNote && <div className="text-xs text-slate-500 mb-2">{importNote}</div>}
      {error && <div className="text-xs text-red-600 mb-2">{error}</div>}

      <div className="space-y-2">
        {documents.map((doc) => (
          <div
            key={doc.id}
            className="flex items-center justify-between text-sm border border-slate-100 rounded-lg px-3 py-2 hover:border-brand-200 transition-colors"
          >
            <div className="min-w-0">
              <div className="truncate text-slate-800">{doc.filename}</div>
              <div className="text-xs text-slate-400">
                {doc.page_count ? `${doc.page_count} page(s)` : "—"}
              </div>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              <span
                className={`inline-flex items-center gap-1.5 text-xs border rounded-full px-2 py-0.5 ${STATUS_STYLES[doc.status]?.pill || ""}`}
              >
                <span className={`h-1.5 w-1.5 rounded-full ${STATUS_STYLES[doc.status]?.dot || "bg-slate-400"}`} />
                {doc.status}
              </span>
              <button
                onClick={() => handleDelete(doc.id)}
                className="text-slate-400 hover:text-red-600 text-xs"
              >
                Remove
              </button>
            </div>
          </div>
        ))}
        {documents.length === 0 && (
          <p className="text-xs text-slate-400">
            No documents yet. Upload a PDF, DOCX, TXT, or Markdown file, or import a Google
            Drive folder.
          </p>
        )}
      </div>
    </div>
  );
}
