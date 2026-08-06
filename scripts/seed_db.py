# -*- coding: utf-8 -*-
"""
scripts/seed_db.py
=====================
Carga inicial de los 10 proyectos de la base de Ambar, con datos reales ya
validados en etapas anteriores del trabajo (no se inventa ningún campo).
Los prmID vienen de la columna "Link seguimiento" de su Excel original.
Ejecutar una sola vez: python scripts/seed_db.py
"""
import sys
import os
import datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.database import init_db, SessionLocal, Proyecto, Evento  # noqa: E402

HOY = datetime.datetime(2026, 7, 22)

PROYECTOS = [
    dict(
        boletin="16889-05",
        nombre="PdL Afide",
        anio_ingreso=2024,
        camara_origen="Cámara de Diputados",
        estado_actual="Segundo trámite constitucional",
        descripcion=(
            "Proyecto que crea una nueva institucionalidad de banca de desarrollo (AFIDE), con "
            "instrumentos de financiamiento de segundo piso y garantías estatales orientados al "
            "desarrollo productivo."
        ),
        comentario_estrategico=(
            "Este proyecto nos involucra totalmente y es de interés estratégico para Corfo: debe "
            "iniciar su discusión próximamente y en las semanas siguientes vendrán las audiencias."
        ),
        prioridad_monitoreo="Crítica",
        prm_id=17500,
    ),
    dict(
        boletin="16441-19",
        nombre="PdL Institucionalidad Futuro y Desarrollo",
        anio_ingreso=2023,
        camara_origen="Cámara de Diputados",
        estado_actual="Primer trámite constitucional",
        descripcion=(
            "Proyecto que crea una institucionalidad permanente para el desarrollo sostenible, "
            "incluyendo un Comité Interministerial y una Política de Desarrollo Productivo Sostenible (DPS)."
        ),
        comentario_estrategico=(
            "Corfo participó en el diseño y en los equipos que hoy tramitan la ley, junto a Minecon. "
            "Nos interesa sobre todo que no se desvirtúe el rol del Consejo."
        ),
        prioridad_monitoreo="Alta",
        prm_id=17011,
    ),
    dict(
        boletin="16686-19",
        nombre="PdL Transferencia Tecnólogica",
        anio_ingreso=2024,
        camara_origen="Cámara de Diputados",
        # Sincronizado con el último evento migrado de este mismo proyecto (ver EVENTOS
        # más abajo: estado_nuevo="Aprobado por el Congreso", 09 Jun. 2026) — antes quedaba
        # en "Segundo trámite constitucional", una etapa anterior incluso al estado_anterior
        # de ese evento ("Tercer trámite constitucional"), porque este campo se cargaba sin
        # reconciliarlo contra el historial que se migraba en el mismo script.
        estado_actual="Aprobado por el Congreso",
        descripcion=(
            "Proyecto que dicta normas sobre transferencia de tecnología y conocimiento, con foco en "
            "empresas de base científico-tecnológica (EBCT) y propiedad intelectual."
        ),
        comentario_estrategico=(
            "Senadores plantearon que falta la dimensión privada-empresarial en el debate; monitorear "
            "cómo evoluciona ese punto — no queremos que impacte lo que hacemos desde Corfo en I+D "
            "privada y propiedad intelectual."
        ),
        prioridad_monitoreo="Alta",
        prm_id=17258,
    ),
    dict(
        boletin="17064-08",
        nombre="PdL Amplía subsidio eléctrico",
        anio_ingreso=2024,
        camara_origen="Cámara de Diputados",
        estado_actual="Segundo trámite constitucional",
        descripcion=(
            "Proyecto que amplía el subsidio eléctrico a hogares vulnerables y modifica aspectos "
            "relacionados con Pequeños y Medianos Generadores Distribuidos (PMGD)."
        ),
        comentario_estrategico=(
            "Puede tener impacto en instrumentos que desde Corfo operamos, e incluso algunos fondos "
            "de capital de riesgo."
        ),
        prioridad_monitoreo="Alta",
        prm_id=17680,
    ),
    dict(
        boletin="16799-05",
        nombre="PdL Agencia de Calidad de las PP",
        anio_ingreso=2024,
        camara_origen="Cámara de Diputados",
        estado_actual="Segundo trámite constitucional",
        descripcion=(
            "Proyecto que crea la Agencia de Calidad de las Políticas Públicas y la Productividad."
        ),
        comentario_estrategico="Estar al tanto del alcance que tendrá la nueva agencia.",
        prioridad_monitoreo="Alta",
        prm_id=17413,
    ),
    dict(
        boletin="16817-05",
        nombre="PdL Turismo y Audiovisual",
        anio_ingreso=2024,
        camara_origen="Cámara de Diputados",
        estado_actual="Segundo trámite constitucional",
        descripcion=(
            "Proyecto que establece incentivos para el turismo y la producción audiovisual."
        ),
        comentario_estrategico=(
            "Conocer su alcance y efectos sobre programas o iniciativas de Corfo que puedan ser "
            "impactadas o requieran de ajustes."
        ),
        prioridad_monitoreo="Alta",
        prm_id=17428,
    ),
    dict(
        boletin="17169-04",
        nombre=("PdL Instrumento de Financiamiento Público para Estudios de Nivel Superior y un Plan de "
                "Reorganización y Condonación de Deudas Educativas"),
        anio_ingreso=2024,
        camara_origen="Cámara de Diputados",
        estado_actual="Segundo trámite constitucional",
        descripcion=(
            "Proyecto sobre financiamiento estudiantil, condonación de deuda educativa y reorganización "
            "de aportes contingentes al ingreso."
        ),
        comentario_estrategico=None,
        prioridad_monitoreo="Alta",
        prm_id=17792,
    ),
    dict(
        boletin="11608-09",
        nombre="PdL Sobre el uso de agua de mar para desalinización",
        anio_ingreso=2018,
        camara_origen="Senado",
        # Sincronizado con el último evento migrado de este mismo proyecto (ver EVENTOS
        # más abajo: estado_nuevo="Tramitación terminada — Ley N° 21.813", 12 May. 2026,
        # anterior a HOY) — antes quedaba en "Trámite de aprobación presidencial", una
        # etapa anterior a la promulgación que el propio historial migrado ya registraba.
        estado_actual="Tramitación terminada — Ley N° 21.813",
        descripcion=(
            "Proyecto que crea un marco institucional para el desarrollo de plantas desalinizadoras y "
            "el uso de agua de mar, incluyendo la Estrategia Nacional de Desalinización."
        ),
        comentario_estrategico=None,
        prioridad_monitoreo="Media",
        prm_id=12126,
        # Ley N° 21.813 ya publicada — verificado en LeyChile (BCN).
        url_ley_publicada="https://www.bcn.cl/leychile/navegar?idNorma=1223983",
        fecha_vigencia=datetime.datetime(2027, 11, 13),
    ),
    dict(
        boletin="16182-12",
        nombre=("PdL Promueve la valorización de los residuos orgánicos y fortalece la gestión de los "
                "residuos a nivel territorial"),
        anio_ingreso=2023,
        camara_origen="Cámara de Diputados",
        estado_actual="Primer trámite constitucional",
        descripcion=(
            "Proyecto sobre economía circular y gestión territorial de residuos orgánicos. NOTA: la "
            "descripción original en la base fuente mezclaba texto de otro proyecto — pendiente de "
            "validación humana."
        ),
        comentario_estrategico=None,
        prioridad_monitoreo="Media",
        prm_id=16745,
    ),
    dict(
        boletin="17777-05",
        nombre="PdL que establece Incentivos Tributarios a la Producción de Hidrógeno Verde y sus Derivados",
        anio_ingreso=2025,
        camara_origen="Cámara de Diputados",
        estado_actual="Segundo trámite constitucional",
        descripcion=(
            "Proyecto que establece créditos fiscales y un régimen especial (incluyendo Magallanes) "
            "para incentivar la producción de hidrógeno verde y sus derivados."
        ),
        comentario_estrategico=None,
        prioridad_monitoreo="Crítica",
        prm_id=18426,
    ),
]

for p in PROYECTOS:
    p["link_seguimiento"] = (
        f"https://www.camara.cl/legislacion/ProyectosDeLey/tramitacion.aspx"
        f"?prmID={p['prm_id']}&prmBOLETIN={p['boletin']}"
        if p["prm_id"] else None
    )

EVENTOS = {
    "16889-05": [
        dict(fecha_evento="31 May. 2024", tipo_evento="Ingreso de proyecto",
             descripcion="Ingreso del proyecto en Primer trámite constitucional / C. Diputados. Incluye IF N° 145/31.05.2024.",
             estado_anterior=None, estado_nuevo="Primer trámite constitucional",
             fuente="Hoja histórica migrada (Etapa 2)", nivel_alerta="Informativa"),
        dict(fecha_evento="10 Dic. 2025", tipo_evento="Votación en comisión",
             descripcion=("La Comisión de Hacienda del Senado tomó la votación del proyecto: "
                          "Rechazado en general. Pasa a la Sala."),
             estado_anterior="Segundo trámite constitucional", estado_nuevo="Segundo trámite constitucional",
             fuente="senado.cl/actividad-legislativa/comisiones (verificado en etapa de validación)",
             nivel_alerta="Crítica"),
    ],
    "16686-19": [
        dict(fecha_evento="09 Jun. 2026", tipo_evento="Aprobación",
             descripcion="El Congreso Nacional aprobó el proyecto.",
             estado_anterior="Tercer trámite constitucional", estado_nuevo="Aprobado por el Congreso",
             fuente="Carey Abogados (carey.cl), verificado por búsqueda web", nivel_alerta="Crítica"),
    ],
    "11608-09": [
        dict(fecha_evento="25 Ene. 2018", tipo_evento="Ingreso de proyecto",
             descripcion="Ingreso del proyecto en Primer trámite constitucional / Senado.",
             estado_anterior=None, estado_nuevo="Primer trámite constitucional",
             fuente="Hoja histórica migrada (Etapa 2)", nivel_alerta="Informativa"),
        dict(fecha_evento="12 May. 2026", tipo_evento="Promulgación y Publicación",
             descripcion="El proyecto fue promulgado y publicado como Ley N° 21.813 (Diario Oficial 12/05/2026).",
             estado_anterior="Tercer trámite constitucional", estado_nuevo="Tramitación terminada — Ley N° 21.813",
             fuente="camara.cl (ficha de tramitación, verificada por Ambar con captura de pantalla)",
             nivel_alerta="Crítica"),
    ],
}


def _verificar_consistencia_estado_actual():
    """Guarda-raíl contra el bug detectado en auditoría: estado_actual se cargaba
    manualmente en PROYECTOS sin reconciliarlo contra el propio historial migrado en
    EVENTOS, y podía quedar desincronizado con el último cambio de trámite real ya
    conocido (ej. boletín 16686-19 quedaba en "Segundo trámite constitucional" pese a
    que su evento migrado decía "Aprobado por el Congreso"). Los eventos de cada
    boletín en EVENTOS están en orden cronológico ascendente, así que el último de la
    lista es el estado más reciente conocido por el historial; si no coincide con
    estado_actual, se detiene el seed en vez de sembrar el dato inconsistente."""
    proyectos_por_boletin = {p["boletin"]: p for p in PROYECTOS}
    for boletin, eventos in EVENTOS.items():
        if not eventos:
            continue
        estado_segun_historial = eventos[-1]["estado_nuevo"]
        estado_actual = proyectos_por_boletin[boletin]["estado_actual"]
        if estado_segun_historial != estado_actual:
            raise ValueError(
                f"Inconsistencia en PROYECTOS/EVENTOS para boletín {boletin}: "
                f"estado_actual={estado_actual!r} pero el último evento migrado indica "
                f"estado_nuevo={estado_segun_historial!r}. Corrige estado_actual en PROYECTOS "
                f"antes de sembrar."
            )


def seed():
    _verificar_consistencia_estado_actual()
    init_db()
    db = SessionLocal()
    try:
        if db.query(Proyecto).count() > 0:
            print("La base de datos ya tiene proyectos cargados — no se vuelve a sembrar.")
            return

        for p in PROYECTOS:
            proyecto = Proyecto(**p, fecha_ultima_revision=HOY, ultimo_analisis_ia=None)
            db.add(proyecto)
            db.flush()  # para obtener proyecto.id

            for ev in EVENTOS.get(p["boletin"], []):
                evento = Evento(proyecto_id=proyecto.id, fecha_deteccion=HOY,
                                 estado_revision_humana="Pendiente", **ev)
                db.add(evento)

        db.commit()
        print(f"Se cargaron {len(PROYECTOS)} proyectos y "
              f"{sum(len(v) for v in EVENTOS.values())} eventos históricos.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
