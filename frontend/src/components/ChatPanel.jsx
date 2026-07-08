import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../api/client.js";
import CitationChip from "./CitationChip.jsx";
import SourceViewer from "./SourceViewer.jsx";

const CITATION_TOKEN = /\[S(\d+)\]/g;

/**
 * The model writes citations as plain "[S1]" tokens in its answer text.
 * Before handing the text to the Markdown renderer, rewrite each token into
 * a Markdown link with a fake "citation:" scheme -- e.g. "[S2]" becomes
 * "[2](citation:2)". Markdown parses that into a normal link node, and the
 * custom `a` renderer below (see mdComponents) intercepts anything with a
 * "citation:" href and swaps in a <CitationChip> instead of a real link.
 * This lets citation chips and Markdown formatting (tables, bold, lists)
 * coexist without hand-rolling a second parser: one pass of standard
 * Markdown parsing handles both.
 */
function injectCitationLinks(content) {
  return content.replace(CITATION_TOKEN, (_match, num) => `[${num}](citation:${num})`);
}

function mdComponents(citations, onCitationClick) {
  return {
    a: ({ href, children }) => {
      if (href && href.startsWith("citation:")) {
        const idx = Number(href.slice("citation:".length));
        const citation = citations[idx - 1];
        if (citation) {
          return <CitationChip index={idx} citation={citation} onClick={onCitationClick} />;
        }
        // Model cited a source number that doesn't exist among what was
        // retrieved (a real LLM failure mode) -- fall back to showing the
        // literal text rather than breaking the render.
        return <span>[S{idx}]</span>;
      }
      return (
        <a href={href} target="_blank" rel="noreferrer" className="underline text-brand-700 hover:text-brand-800">
          {children}
        </a>
      );
    },
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

function renderAnswer(content, citations, onCitationClick) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents(citations, onCitationClick)}>
      {injectCitationLinks(content)}
    </ReactMarkdown>
  );
}

/**
 * Shows every chunk that was actually retrieved and sent to the LLM for
 * this answer -- not just the ones the model chose to cite inline. Useful
 * for evaluating retrieval quality separately from generation quality: a
 * wrong or incomplete answer might still have retrieved the right chunk
 * (a generation problem), or the right chunk might never have been
 * retrieved at all (a retrieval problem) -- this panel is how you tell
 * the two apart.
 */
function RetrievedSources({ citations, onSelect }) {
  if (!citations || citations.length === 0) return null;
  return (
    <details className="mt-1.5 text-xs text-slate-500 w-full">
      <summary className="cursor-pointer select-none hover:text-slate-700">
        Retrieved sources ({citations.length})
      </summary>
      <ul className="mt-2 space-y-1.5">
        {citations.map((c, i) => (
          <li key={c.chunk_id}>
            <button
              onClick={() => onSelect(c)}
              className="w-full text-left bg-white border border-slate-200 rounded-md px-2 py-1.5 hover:border-brand-300 transition-colors"
            >
              <div className="flex justify-between gap-2">
                <span className="font-medium text-slate-700 truncate">
                  {i + 1}. {c.filename}
                  {c.page != null ? ` · p.${c.page}` : ""}
                </span>
                <span className="text-slate-400 shrink-0">
                  ~{Math.max(0, Math.round(c.score * 100))}% relevance
                </span>
              </div>
              <div className="text-slate-500 truncate">{c.text}</div>
            </button>
          </li>
        ))}
      </ul>
    </details>
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
  const [activeCitation, setActiveCitation] = useState(null);
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
            Ask a question about the documents in this notebook. Sources are linked
            automatically — hover or click a marker to see exactly where an answer came from.
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
              {m.role === "assistant"
                ? renderAnswer(m.content, m.citations || [], setActiveCitation)
                : m.content}
            </div>
            {m.role === "assistant" && (
              <>
                <ExportButton notebookId={notebookId} content={m.content} citations={m.citations || []} />
                <RetrievedSources citations={m.citations} onSelect={setActiveCitation} />
              </>
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

      <SourceViewer
        notebookId={notebookId}
        citation={activeCitation}
        onClose={() => setActiveCitation(null)}
      />
    </div>
  );
}
