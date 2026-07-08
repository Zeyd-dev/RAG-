import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api } from "../api/client.js";
import ChatPanel from "../components/ChatPanel.jsx";
import Logo from "../components/Logo.jsx";
import UploadPanel from "../components/UploadPanel.jsx";

/**
 * Downloads a one-notebook Word summary via POST /report -- separate from
 * ChatPanel's per-answer ExportButton, this one summarizes every document
 * in the notebook at once rather than a single chat answer, so it lives at
 * the notebook level instead of attached to a message.
 */
function ReportButton({ notebookId }) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  const handleClick = async () => {
    if (generating) return;
    setGenerating(true);
    setError("");
    try {
      await api.generateReport(notebookId);
    } catch (err) {
      setError(err.message);
    } finally {
      setGenerating(false);
    }
  };

  return (
    <div className="flex flex-col items-end gap-1">
      <button
        onClick={handleClick}
        disabled={generating}
        className="inline-flex items-center gap-1.5 bg-brand-600 text-white rounded-lg px-3.5 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors shrink-0"
      >
        <svg viewBox="0 0 20 20" fill="currentColor" className="h-4 w-4">
          <path d="M4 2.5A1.5 1.5 0 0 1 5.5 1h5.379a1.5 1.5 0 0 1 1.06.44l3.122 3.12A1.5 1.5 0 0 1 15.5 5.62V17.5A1.5 1.5 0 0 1 14 19H5.5A1.5 1.5 0 0 1 4 17.5v-15Z" />
        </svg>
        {generating ? "Generating report..." : "Generate report"}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}

export default function NotebookView({ onLogout }) {
  const { notebookId } = useParams();
  const [notebook, setNotebook] = useState(null);

  useEffect(() => {
    setNotebook(null);
    api.getNotebook(notebookId).then(setNotebook).catch(() => {});
  }, [notebookId]);

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between">
          <Logo className="h-7 w-auto" />
          <button onClick={onLogout} className="text-sm text-slate-500 hover:text-slate-800">
            Sign out
          </button>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-8">
        <Link
          to="/"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-brand-600 transition-colors"
        >
          ← All notebooks
        </Link>

        <div className="flex items-start justify-between gap-4 mt-3 mb-1">
          <div className="min-w-0">
            <h1 className="text-2xl font-semibold text-slate-900 truncate">
              {notebook ? notebook.name : " "}
            </h1>
            {notebook?.description && (
              <p className="text-sm text-slate-500 mt-0.5">{notebook.description}</p>
            )}
          </div>
          {notebook && <ReportButton notebookId={notebookId} />}
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-5">
          <div className="md:col-span-1">
            <UploadPanel notebookId={notebookId} />
          </div>
          <div className="md:col-span-2">
            <ChatPanel notebookId={notebookId} />
          </div>
        </div>
      </div>
    </div>
  );
}
