import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api/client.js";

const CITATION_TOKEN = /\s*\[S\d+\]/g;

/**
 * The model writes citations as plain "[S1]" tokens in its answer text.
 * Clickable inline citation chips + the source viewer were removed (the
 * "open source document" link intermittently opened a login/auth tab
 * instead of the actual passage, and wasn't reliable enough to keep) --
 * so these tokens are now just stripped out before rendering rather than
 * turned into links. The underlying citation data still flows through to
 * the Word/PDF export, which lists sources as plain text.
 */
function stripCitationTokens(content) {
  return content.replace(CITATION_TOKEN, "");
}

function mdComponents() {
  return {
    a: ({ href, children }) => (
      <a href={href} target="_blank" rel="noreferrer" className="underline text-brand-700 hover:text-brand-800">
        {children}
      </a>
    ),
    p: ({ children }) => <p className="mb-2 last:mb-0 leading-relaxed">{children}</p>,
    strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
    ul: ({ children }) => <ul className="list-disc list-outside pl-5 mb-2 space-y-1 last:mb-0">{children}</ul>,
    ol: ({ children }) => <ol className="list-decimal list-outside pl-5 mb-2 space-y-1 last:mb-0">{children}</ol>,
    li: ({ children }) => <li className="leading-relaxed">{children}</li>,
    h1: ({ children }) => <h1 className="text-base font-bold mb-1.5 mt-1 first:mt-0">{children}</h1>,
    h2: ({ children }) => <h2 className="text-sm font-bold mb-1.5 mt-1 first:mt-0">{children}</h2>,
    h3: ({ children }) => <h3 className="text-sm font-semibold mb-1 mt-1 first:mt-0">{children}</h3>,
    blockquote: ({ children }) => (
      <blockquote className="border-l-2 border-slate-300 pl-2 italic text-slate-600 mb-2 last:mb-0">
        {children}
      </blockquote>
    ),
    pre: ({ children }) => (
      <pre className="bg-slate-200/70 rounded-lg p-2 text-xs overflow-x-auto mb-2 last:mb-0 font-mono">
        {children}
      </pre>
    ),
    code: ({ children }) => (
      <code className="bg-slate-200/70 rounded px-1 py-0.5 text-[0.85em] font-mono">{children}</code>
    ),
    table: ({ children }) => (
      <div className="overflow-x-auto mb-2 last:mb-0">
        <table className="min-w-full border-collapse text-xs">{children}</table>
      </div>
    ),
    thead: ({ children }) => <thead className="bg-slate-200/70">{children}</thead>,
    th: ({ children }) => (
      <th className="border border-slate-300 px-2 py-1 text-left font-semibold">{children}</th>
    ),
    td: ({ children }) => <td className="border border-slate-300 px-2 py-1 align-top">{children}</td>,
  };
}

function renderAnswer(content) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents()}>
      {stripCitationTokens(content)}
    </ReactMarkdown>
  );
}

/**
 * Turns one assistant answer into a downloadable .docx -- the "generate a
 * report file" feature: same Markdown content as the chat bubble (tables,
 * bold, headings), plus a Sources list, saved as an actual Word document
 * instead of being stuck as chat text.
 */
function ExportButton({ notebookId, content, citations }) {
  const [exporting, setExporting] = useState(false);
  const [error, setError] = useState("");

  const handleExport = async () => {
    if (exporting) return;
    setExporting(true);
    setError("");
    try {
      await api.exportChat(notebookId, content, citations);
    } catch (err) {
      setError(err.message);
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="mt-1.5 flex items-center gap-2">
      <button
        onClick={handleExport}
        disabled={exporting}
        className="text-xs text-slate-500 hover:text-brand-700 underline disabled:opacity-50 transition-colors"
      >
        {exporting ? "Exporting..." : "Export as Word"}
      </button>
      {error && <span className="text-xs text-red-600">{error}</span>}
    </div>
  );
}

export default function ChatPanel({ notebookId }) {
  const [messages, setMessages] = useState([]);
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const scrollRef = useRef(null);

  useEffect(() => {
    setMessages([]);
  }, [notebookId]);

  useEffect(() => {
    scrollRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async (e) => {
    e.preventDefault();
    const q = question.trim();
    if (!q || loading) return;
    setError("");
    setMessages((prev) => [...prev, { role: "user", content: q }]);
    setQuestion("");
    setLoading(true);
    try {
      const res = await api.chat(notebookId, q);
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.answer, citations: res.citations },
      ]);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white border border-slate-200 rounded-xl p-4 flex flex-col h-[70vh] shadow-sm">
      <h2 className="text-sm font-semibold text-slate-900 mb-3">Ask this notebook</h2>

      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        {messages.length === 0 && (
          <p className="text-xs text-slate-400">
            Ask a question about the documents in this notebook.
          </p>
        )}
        {messages.map((m, i) => (
          <div key={i} className={m.role === "user" ? "text-right" : "text-left"}>
            <div
              className={`inline-block max-w-full rounded-2xl px-3.5 py-2 text-sm ${
                m.role === "user"
                  ? "bg-brand-600 text-white"
                  : "bg-slate-100 text-slate-800 text-left"
              }`}
            >
              {m.role === "assistant" ? renderAnswer(m.content) : m.content}
            </div>
            {m.role === "assistant" && (
              <ExportButton notebookId={notebookId} content={m.content} citations={m.citations || []} />
            )}
          </div>
        ))}
        {loading && <div className="text-xs text-slate-400">Thinking...</div>}
        <div ref={scrollRef} />
      </div>

      {error && <div className="text-xs text-red-600 mt-2">{error}</div>}

      <form onSubmit={handleSend} className="flex gap-2 mt-3">
        <input
          className="flex-1 rounded-lg border border-slate-300 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-brand-200 focus:border-brand-400"
          placeholder="Ask a question..."
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
        />
        <button
          disabled={loading}
          className="bg-brand-600 text-white rounded-lg px-4 py-2 text-sm font-medium hover:bg-brand-700 disabled:opacity-50 transition-colors"
        >
          Send
        </button>
      </form>
    </div>
  );
}
