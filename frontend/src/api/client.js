/**
 * Thin fetch wrapper for the backend API. Uses cookie-based sessions
 * (credentials: "include") so no token handling is needed client-side.
 */
const BASE = "/api";

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: options.body instanceof FormData ? {} : { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  if (res.status === 204) return null;
  return res.json();
}

// Same idea as request(), but for endpoints that return a binary file
// (currently just the .docx export) instead of JSON.
async function requestBlob(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* ignore */
    }
    throw new Error(detail);
  }
  const blob = await res.blob();
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = disposition.match(/filename="?([^"]+)"?/);
  return { blob, filename: match ? match[1] : "report.docx" };
}

export const api = {
  login: (username, password) =>
    request("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/auth/logout", { method: "POST" }),

  listNotebooks: () => request("/notebooks"),
  getNotebook: (id) => request(`/notebooks/${id}`),
  createNotebook: (name, description) =>
    request("/notebooks", { method: "POST", body: JSON.stringify({ name, description }) }),
  deleteNotebook: (id) => request(`/notebooks/${id}`, { method: "DELETE" }),

  listDocuments: (notebookId) => request(`/notebooks/${notebookId}/documents`),
  uploadDocument: (notebookId, file) => {
    const form = new FormData();
    form.append("file", file);
    return request(`/notebooks/${notebookId}/documents`, { method: "POST", body: form });
  },
  deleteDocument: (notebookId, documentId) =>
    request(`/notebooks/${notebookId}/documents/${documentId}`, { method: "DELETE" }),
  importFromDrive: (notebookId, driveUrl) =>
    request(`/notebooks/${notebookId}/documents/import-drive`, {
      method: "POST",
      body: JSON.stringify({ drive_url: driveUrl }),
    }),
  getChunk: (notebookId, documentId, chunkId) =>
    request(`/notebooks/${notebookId}/documents/${documentId}/chunks/${chunkId}`),
  documentFileUrl: (notebookId, documentId) =>
    `${BASE}/notebooks/${notebookId}/documents/${documentId}/file`,

  chat: (notebookId, question) =>
    request(`/notebooks/${notebookId}/chat`, {
      method: "POST",
      body: JSON.stringify({ notebook_id: notebookId, question }),
    }),
  chatHistory: (notebookId) => request(`/notebooks/${notebookId}/chat/history`),

  // Exports one assistant answer as a .docx and triggers a browser download --
  // this is the "generate a report file" feature: the same Markdown answer
  // shown in the chat bubble, rendered as a real Word document with a
  // Sources section, instead of being stuck as chat text.
  exportChat: async (notebookId, content, citations, title) => {
    const { blob, filename } = await requestBlob(`/notebooks/${notebookId}/chat/export`, {
      method: "POST",
      body: JSON.stringify({ content, citations: citations || [], title }),
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },

  // Summarizes every ready document in the notebook into one Word report
  // (one section per document plus a cross-document themes section) and
  // triggers a browser download -- same download mechanics as exportChat,
  // just backed by /report instead of /chat/export.
  generateReport: async (notebookId) => {
    const { blob, filename } = await requestBlob(`/notebooks/${notebookId}/report`, {
      method: "POST",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  },
};
