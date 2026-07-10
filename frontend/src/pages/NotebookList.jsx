import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client.js";
import Logo from "../components/Logo.jsx";

export default function NotebookList({ onLogout }) {
  const [notebooks, setNotebooks] = useState([]);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [error, setError] = useState("");

  const load = async () => {
    try {
      setNotebooks(await api.listNotebooks());
    } catch (err) {
      setError(err.message);
    }
  };

  useEffect(() => {
    load();
  }, []);

  const handleCreate = async (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      await api.createNotebook(name.trim(), description.trim() || null);
      setName("");
      setDescription("");
      load();
    } catch (err) {
      setError(err.message);
    }
  };

  const handleDelete = async (id) => {
    if (!confirm("Delete this notebook and all its documents?")) return;
    await api.deleteNotebook(id);
    load();
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="max-w-3xl mx-auto px-6 py-4 flex items-center justify-between">
          <Logo className="h-7 w-auto" />
          <button onClick={onLogout} className="text-sm text-slate-500 hover:text-slate-800">
            Sign out
          </button>
        </div>
      </header>

      <div className="max-w-3xl mx-auto px-6 py-10">
        <h1 className="text-2xl font-semibold text-slate-900">Your notebooks</h1>
        <p className="text-sm text-slate-500 mt-1 mb-8">
          Group related documents together, then ask questions scoped to that set.
        </p>

        {error && <div className="mb-4 text-sm text-red-600">{error}</div>}

        <form
          onSubmit={handleCreate}
          className="flex flex-col sm:flex-row gap-2 mb-8 bg-white border border-slate-200 rounded-xl p-3 shadow-sm"
        >
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400"
            placeholder="New notebook name"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
          <input
            className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400"
            placeholder="Description (optional)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
          <button className="bg-brand-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-brand-700 transition-colors shrink-0">
            Create
          </button>
        </form>

        <div className="space-y-3">
          {notebooks.map((nb) => (
            <div
              key={nb.id}
              className="group flex items-center gap-4 bg-white border border-slate-200 rounded-xl px-4 py-3 hover:border-brand-300 hover:shadow-md transition-all shadow-sm"
            >
              <div className="h-9 w-9 shrink-0 rounded-lg bg-brand-50 text-brand-600 flex items-center justify-center">
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                  <path d="M4 2.5A1.5 1.5 0 0 1 5.5 1h5.379a1.5 1.5 0 0 1 1.06.44l3.122 3.12A1.5 1.5 0 0 1 15.5 5.62V17.5A1.5 1.5 0 0 1 14 19H5.5A1.5 1.5 0 0 1 4 17.5v-15Z" />
                </svg>
              </div>
              <Link to={`/notebooks/${nb.id}`} className="flex-1 min-w-0">
                <div className="font-medium text-slate-900 truncate">{nb.name}</div>
                {nb.description && (
                  <div className="text-sm text-slate-500 truncate">{nb.description}</div>
                )}
              </Link>
              <svg
                viewBox="0 0 20 20"
                fill="currentColor"
                className="h-4 w-4 text-slate-300 group-hover:text-brand-400 transition-colors shrink-0"
              >
                <path
                  fillRule="evenodd"
                  d="M7.21 14.77a.75.75 0 0 1 0-1.06L11.94 8l-4.73-4.71a.75.75 0 1 1 1.06-1.06l5.25 5.25a.75.75 0 0 1 0 1.06l-5.25 5.25a.75.75 0 0 1-1.06 0Z"
                  clipRule="evenodd"
                />
              </svg>
              <button
                onClick={() => handleDelete(nb.id)}
                aria-label={`Delete ${nb.name}`}
                title="Delete notebook"
                className="shrink-0 text-slate-400 hover:text-red-600 transition-colors opacity-60 group-hover:opacity-100"
              >
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-4.5 w-4.5">
                  <path
                    fillRule="evenodd"
                    d="M8.75 1A2.75 2.75 0 0 0 6 3.75v.443c-.795.077-1.584.176-2.365.298a.75.75 0 1 0 .23 1.482l.149-.022.841 10.518A2.75 2.75 0 0 0 7.596 19h4.807a2.75 2.75 0 0 0 2.742-2.53l.841-10.52.149.023a.75.75 0 0 0 .23-1.482 41.03 41.03 0 0 0-2.365-.298V3.75A2.75 2.75 0 0 0 11.25 1h-2.5ZM10 4c.84 0 1.673.025 2.5.075V3.75c0-.69-.56-1.25-1.25-1.25h-2.5c-.69 0-1.25.56-1.25 1.25v.325C8.327 4.025 9.16 4 10 4Z"
                    clipRule="evenodd"
                  />
                </svg>
              </button>
            </div>
          ))}
          {notebooks.length === 0 && (
            <div className="text-center border border-dashed border-slate-300 rounded-xl py-12 px-6">
              <div className="mx-auto h-10 w-10 rounded-lg bg-brand-50 text-brand-500 flex items-center justify-center mb-3">
                <svg viewBox="0 0 20 20" fill="currentColor" className="h-5 w-5">
                  <path d="M4 2.5A1.5 1.5 0 0 1 5.5 1h5.379a1.5 1.5 0 0 1 1.06.44l3.122 3.12A1.5 1.5 0 0 1 15.5 5.62V17.5A1.5 1.5 0 0 1 14 19H5.5A1.5 1.5 0 0 1 4 17.5v-15Z" />
                </svg>
              </div>
              <p className="text-sm text-slate-500">No notebooks yet — create one above to get started.</p>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
