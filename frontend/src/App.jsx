import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import Login from "./pages/Login.jsx";
import NotebookList from "./pages/NotebookList.jsx";
import NotebookView from "./pages/NotebookView.jsx";

export default function App() {
  const [loggedIn, setLoggedIn] = useState(
    () => sessionStorage.getItem("rag_logged_in") === "true"
  );

  const handleLogin = () => {
    sessionStorage.setItem("rag_logged_in", "true");
    setLoggedIn(true);
  };

  const handleLogout = () => {
    sessionStorage.removeItem("rag_logged_in");
    setLoggedIn(false);
  };

  if (!loggedIn) {
    return <Login onLogin={handleLogin} />;
  }

  return (
    <Routes>
      <Route path="/" element={<NotebookList onLogout={handleLogout} />} />
      <Route path="/notebooks/:notebookId" element={<NotebookView onLogout={handleLogout} />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
