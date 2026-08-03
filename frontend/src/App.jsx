import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import ProjectDetail from "./pages/ProjectDetail";
import "./styles.css";

function App() {
  return (
    <BrowserRouter>
      <div className="layout">
        <header className="topbar">
          <span className="marca">Radar Legislativo Corfo</span>
          <span className="subtitulo">Seguimiento estratégico de proyectos de ley</span>
        </header>
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/proyectos/:id" element={<ProjectDetail />} />
          </Routes>
        </main>
      </div>
    </BrowserRouter>
  );
}

export default App;
