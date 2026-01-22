import { Routes, Route, Navigate } from "react-router-dom";
import LoginPage from "./pages/LoginPage";
import HomePage from "./pages/HomePage";

export default function App() {
  const token = localStorage.getItem("chat_jwt");

  return (
    <Routes>
      <Route path="/" element={<LoginPage />} />
      <Route
        path="/home"
        // if token exists, render HomePage, else navigate to LoginPage
        element={token ? <HomePage /> : <Navigate to="/" />}
      />
    </Routes>
  );
}
