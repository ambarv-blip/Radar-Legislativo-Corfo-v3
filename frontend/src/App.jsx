import { BrowserRouter, Routes, Route } from "react-router-dom";
import Home from "./pages/Home";
import ProjectDetail from "./pages/ProjectDetail";
import "./styles.css";

// Ícono de radar dibujado como SVG propio — no es la imagen de referencia insertada como
// logo, es una reconstrucción del mismo motivo visual (anillos concéntricos, un arco de
// barrido y un indicador apuntando a una detección) como gráfico vectorial nativo: se
// integra al layout del encabezado, escala sin perder nitidez a ningún tamaño, y no
// depende de un archivo de imagen externo.
function IconoRadar() {
  return (
    <svg viewBox="0 0 200 200" role="img" aria-label="Radar" className="icono-radar">
      <circle cx="100" cy="100" r="90" className="radar-anillo" />
      <path d="M 84.4 11.4 A 90 90 0 0 1 188.6 84.4" className="radar-barrido" />
      <circle cx="100" cy="100" r="62" className="radar-anillo" />
      <circle cx="100" cy="100" r="34" className="radar-anillo" />
      <line x1="100" y1="100" x2="163.6" y2="36.4" className="radar-linea" />
      <circle cx="100" cy="100" r="9" className="radar-punto" />
      <circle cx="163.6" cy="36.4" r="8" className="radar-punto" />
      <circle cx="89.2" cy="161.1" r="7" className="radar-punto" />
    </svg>
  );
}

function App() {
  return (
    <BrowserRouter>
      <div className="layout">
        <header className="topbar">
          <div className="topbar-inner">
            <IconoRadar />
            <div className="topbar-texto">
              <span className="marca">Radar Legislativo Corfo</span>
              <span className="subtitulo">Seguimiento estratégico de proyectos de ley</span>
            </div>
          </div>
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
