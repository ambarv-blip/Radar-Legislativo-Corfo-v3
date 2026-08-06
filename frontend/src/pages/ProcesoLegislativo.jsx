// -----------------------------------------------------------------------------
// Página independiente (pestaña 2) — explica el proceso legislativo chileno.
// No comparte estado ni lógica con Home.jsx; es puramente informativa.
//
// Cada <Etapa> recibe la MISMA clase que ya usan las cápsulas de estado del
// Dashboard (estado-inicial, estado-intermedio, etc. — ver estiloEstado() en
// Home.jsx) para que, en una futura iteración, se pueda resaltar automáticamente
// la etapa en la que se encuentra un proyecto específico: bastaría con pasarle
// una prop `activo` calculada a partir de estiloEstado(proyecto.estado_actual).
// Hoy esa prop existe (ver <Etapa>) pero ningún <Etapa> la usa — solo queda la
// estructura preparada, tal como se pidió.
// -----------------------------------------------------------------------------

function Paso({ children }) {
  return <div className="flujo-paso">{children}</div>;
}

function Flecha() {
  return <div className="flujo-flecha" aria-hidden="true" />;
}

function Etapa({ estadoClase, titulo, activo = false, children }) {
  return (
    <section className={`flujo-etapa ${estadoClase}${activo ? " flujo-etapa--activa" : ""}`}>
      <h3 className="flujo-etapa-titulo">{titulo}</h3>
      <div className="flujo-etapa-contenido">{children}</div>
    </section>
  );
}

function Decision({ children }) {
  return <div className="flujo-decision">{children}</div>;
}

function Bifurcacion({ children }) {
  return <div className="flujo-bifurcacion">{children}</div>;
}

function Rama({ etiqueta, tono = "neutra", children }) {
  return (
    <div className={`flujo-rama flujo-rama--${tono}`}>
      <span className="flujo-rama-chip">{etiqueta}</span>
      <div className="flujo-rama-contenido">{children}</div>
    </div>
  );
}

function Terminal({ tono, children }) {
  return <div className={`flujo-terminal${tono ? ` flujo-terminal--${tono}` : ""}`}>{children}</div>;
}

export default function ProcesoLegislativo() {
  return (
    <>
      <div className="panel proceso-encabezado">
        <h1>¿Cómo se tramita un proyecto de ley?</h1>
        <p className="proceso-subtitulo">
          Conoce las principales etapas del proceso legislativo chileno desde la presentación de una
          iniciativa hasta su publicación como ley.
        </p>
      </div>

      <div className="panel">
        <div className="flujo">
          <Terminal tono="inicio">Inicio</Terminal>
          <Flecha />

          <Etapa estadoClase="estado-sin-info" titulo="Origen del proyecto">
            <Paso>
              Presentación del Proyecto de Ley
              <br />
              <small>(Mensaje Presidencial o Moción Parlamentaria)</small>
            </Paso>
            <Flecha />
            <Paso>
              Ingreso a la Cámara de Origen
              <br />
              <small>(Cámara de Diputadas y Diputados o Senado)</small>
            </Paso>
            <Flecha />
            <Paso>Asignación de Boletín</Paso>
            <Flecha />
            <Paso>Asignación de Comisión(es)</Paso>
          </Etapa>
          <Flecha />

          <Etapa estadoClase="estado-inicial" titulo="Primer trámite constitucional">
            <Paso>Comisión</Paso>
            <Flecha />
            <Paso>Sala</Paso>
            <Flecha />
            <Paso>Votación</Paso>
            <Flecha />
            <Decision>¿Se aprueba?</Decision>
          </Etapa>

          <Bifurcacion>
            <Rama etiqueta="NO" tono="negativa">
              <Flecha />
              <Paso>Se rechaza o se archiva</Paso>
              <Flecha />
              <Terminal tono="fin">Fin</Terminal>
            </Rama>
            <Rama etiqueta="SÍ" tono="positiva">
              <Flecha />
              <Paso>Continúa a Segundo Trámite Constitucional</Paso>
            </Rama>
          </Bifurcacion>
          <Flecha />

          <Etapa estadoClase="estado-intermedio" titulo="Segundo trámite constitucional">
            <Paso>Comisión</Paso>
            <Flecha />
            <Paso>Sala</Paso>
            <Flecha />
            <Paso>Votación</Paso>
            <Flecha />
            <Decision>¿La Cámara Revisora introduce cambios?</Decision>
          </Etapa>

          <Bifurcacion>
            <Rama etiqueta="NO" tono="positiva">
              <Flecha />
              <Paso>
                Pasa al Presidente de la República
                <br />
                <small>(continúa en Trámite de aprobación presidencial ↓)</small>
              </Paso>
            </Rama>
            <Rama etiqueta="SÍ" tono="neutra">
              <Flecha />
              <Paso>Regresa a la Cámara de Origen</Paso>
            </Rama>
          </Bifurcacion>

          <Etapa estadoClase="estado-avanzado" titulo="Tercer trámite constitucional">
            <Decision>¿Acepta los cambios?</Decision>
          </Etapa>

          <Bifurcacion>
            <Rama etiqueta="SÍ" tono="positiva">
              <Flecha />
              <Paso>
                Pasa al Presidente
                <br />
                <small>(continúa en Trámite de aprobación presidencial ↓)</small>
              </Paso>
            </Rama>
            <Rama etiqueta="NO" tono="neutra">
              <Flecha />
              <Paso>Comisión Mixta</Paso>
              <Flecha />
              <Paso>Informe Comisión Mixta</Paso>
              <Flecha />
              <Paso>Votación en ambas Cámaras</Paso>
            </Rama>
          </Bifurcacion>
          <Flecha />

          <Etapa estadoClase="estado-presidencial" titulo="Trámite de aprobación presidencial">
            <Paso>Presidente de la República</Paso>
            <Flecha />
            <Paso>Promulgación</Paso>
            <Flecha />
            <Paso>Toma de razón (cuando corresponda)</Paso>
            <Flecha />
            <Paso>Publicación en el Diario Oficial</Paso>
          </Etapa>
          <Flecha />

          <Terminal tono="ley">Ley vigente</Terminal>
        </div>
      </div>
    </>
  );
}
