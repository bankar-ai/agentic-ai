import { Navigate, Route, Routes } from "react-router-dom";
import { AboutPage } from "./pages/AboutPage";
import { LoginPage } from "./pages/LoginPage";
import { QueryPage } from "./pages/QueryPage";
import { useSession } from "./session";

export default function App() {
  const { session } = useSession();

  return (
    <Routes>
      <Route path="/" element={session ? <Navigate to="/query" replace /> : <LoginPage />} />
      <Route path="/about" element={<AboutPage />} />
      <Route path="/query" element={<QueryPage />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
