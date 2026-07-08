import { useState } from "react";
import { api } from "../api/client.js";
import Logo from "../components/Logo.jsx";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.login(username, password);
      onLogin();
    } catch (err) {
      setError(err.message || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen relative flex items-center justify-center bg-slate-50 overflow-hidden">
      {/* Subtle brand motif -- echoes the logo's dot, kept soft so it never
          competes with the form. */}
      <div
        aria-hidden="true"
        className="absolute -top-40 -right-40 h-96 w-96 rounded-full bg-brand-100 opacity-60"
      />
      <div
        aria-hidden="true"
        className="absolute -bottom-52 -left-32 h-80 w-80 rounded-full bg-brand-50 opacity-70"
      />

      <form
        onSubmit={handleSubmit}
        className="relative bg-white shadow-sm border border-slate-200 rounded-2xl p-8 w-full max-w-sm"
      >
        <Logo className="h-8 w-auto mb-5" />
        <h1 className="text-xl font-semibold text-slate-900 mb-1">RAG NoteBook</h1>
        <p className="text-sm text-slate-500 mb-6">Internal document Q&A, powered by your own files</p>

        {error && (
          <div className="mb-4 text-sm text-red-600 bg-red-50 border border-red-200 rounded-md px-3 py-2">
            {error}
          </div>
        )}

        <label className="block text-sm font-medium text-slate-700 mb-1">Username</label>
        <input
          className="w-full mb-4 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoFocus
        />

        <label className="block text-sm font-medium text-slate-700 mb-1">Password</label>
        <input
          type="password"
          className="w-full mb-6 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
        />

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-brand-600 text-white rounded-lg py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Signing in..." : "Sign in"}
        </button>
      </form>
    </div>
  );
}
