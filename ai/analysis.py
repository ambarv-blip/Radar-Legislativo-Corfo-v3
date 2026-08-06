# -*- coding: utf-8 -*-
"""
ai/analysis.py
=================
Análisis Ejecutivo IA: genera, mediante una llamada real a un modelo de
Claude (Anthropic), un análisis ejecutivo estructurado en 6 bloques para
apoyar la toma de decisiones de Corfo sobre un proyecto de ley.

Restricción central (por diseño, no negociable): el modelo analiza
EXCLUSIVAMENTE la información oficial que el propio Observatorio ya
recopiló desde la plataforma del Congreso — descripción, estado actual,
historial de eventos/tramitación — nunca navega a Internet ni usa fuentes
externas ni su conocimiento general. `comentario_estrategico` (nota interna
de Corfo) se excluye deliberadamente del contexto: no es información oficial
del Congreso, es una anotación propia del Observatorio.

Si la llamada al modelo falla por cualquier motivo (sin API key, sin red,
error del proveedor, respuesta no parseable), la función degrada con
gracia: no lanza excepción y devuelve un payload neutro que la interfaz
puede mostrar sin fingir que el análisis existe.
"""
import json
import os

import anthropic

MODELO = "claude-opus-5"

CAMPOS_ANALISIS = [
    "objetivo",
    "problema",
    "aspectos_principales",
    "implicancias_corfo",
    "estado_debate",
    "conclusion",
]

SIN_INFORMACION = "No se encontró información suficiente para este apartado."

SYSTEM_PROMPT = (
    "Actúa como un analista legislativo especializado en políticas públicas, "
    "innovación y desarrollo productivo. Analiza exclusivamente la información "
    "oficial disponible para este proyecto de ley. No inventes antecedentes. "
    "No utilices conocimiento externo. No hagas suposiciones que no puedan "
    "justificarse con la información disponible. Cuando una sección no cuente "
    "con información suficiente, indícalo explícitamente escribiendo "
    f"\"{SIN_INFORMACION}\". Elabora un análisis ejecutivo breve, objetivo y "
    "orientado a apoyar la toma de decisiones dentro de Corfo."
)

ESQUEMA_ANALISIS = {
    "name": "analisis_ejecutivo",
    "schema": {
        "type": "object",
        "properties": {
            "objetivo": {
                "type": "string",
                "description": "Objetivo del proyecto: ¿para qué se presenta esta iniciativa? Máximo 2 párrafos breves.",
            },
            "problema": {
                "type": "string",
                "description": "Qué problema busca resolver, según autores/Mensaje Presidencial cuando exista. Máximo 2 párrafos breves.",
            },
            "aspectos_principales": {
                "type": "array",
                "items": {"type": "string"},
                "description": "3 a 5 viñetas breves (ej. 'Crea...', 'Modifica...', 'Incorpora...', 'Elimina...', 'Fortalece...').",
            },
            "implicancias_corfo": {
                "type": "string",
                "description": "Posibles implicancias para Corfo: conexión con programas, instrumentos, innovación, emprendimiento, desarrollo productivo, financiamiento, transferencia tecnológica o desarrollo territorial.",
            },
            "estado_debate": {
                "type": "string",
                "description": "Estado del debate legislativo: resumen breve de la tramitación (discusión en comisión, observaciones, indicaciones, acuerdos, diferencias).",
            },
            "conclusion": {
                "type": "string",
                "description": "Conclusión ejecutiva: por qué vale la pena seguir este proyecto de ley. Máximo 3 párrafos muy breves.",
            },
        },
        "required": CAMPOS_ANALISIS,
        "additionalProperties": False,
    },
}


def _construir_contexto_oficial(proyecto) -> str:
    """Arma el bloque de contexto a partir exclusivamente de datos oficiales
    ya recopilados por el Observatorio desde la plataforma del Congreso.
    Deliberadamente NO incluye `comentario_estrategico` (nota interna de
    Corfo, no es información oficial del Congreso)."""
    partes = [
        f"Nombre del proyecto: {proyecto.nombre}",
        f"Boletín: {proyecto.boletin}",
        f"Año de ingreso: {proyecto.anio_ingreso or 'No disponible'}",
        f"Cámara de origen: {proyecto.camara_origen or 'No disponible'}",
        f"Estado actual: {proyecto.estado_actual or 'No disponible'}",
        f"Descripción oficial: {proyecto.descripcion or 'No disponible'}",
    ]

    eventos = list(proyecto.eventos or [])
    if eventos:
        partes.append("\nHistorial de tramitación (eventos detectados desde la fuente oficial):")
        for ev in eventos:
            linea = f"- Fecha: {ev.fecha_evento or 'sin fecha'} | Tipo: {ev.tipo_evento or 'sin tipo'}"
            if ev.estado_anterior or ev.estado_nuevo:
                linea += f" | Estado: {ev.estado_anterior or '?'} → {ev.estado_nuevo or '?'}"
            if ev.descripcion:
                linea += f" | Detalle: {ev.descripcion}"
            if ev.fuente:
                linea += f" | Fuente: {ev.fuente}"
            partes.append(linea)
    else:
        partes.append("\nHistorial de tramitación: sin eventos registrados por el Observatorio todavía.")

    return "\n".join(partes)


def _respuesta_vacia() -> dict:
    return {campo: (SIN_INFORMACION if campo != "aspectos_principales" else []) for campo in CAMPOS_ANALISIS}


def generar_analisis_ejecutivo(proyecto) -> str:
    """Genera el Análisis Ejecutivo IA de un `Proyecto` mediante una llamada
    real a la API de Claude, restringida exclusivamente al contexto oficial
    ya recopilado por el Observatorio. Devuelve un string JSON con los 6
    bloques (ver `CAMPOS_ANALISIS`), listo para guardarse en
    `Proyecto.ultimo_analisis_ia`.

    Nunca lanza excepción: ante cualquier falla (sin API key, sin red, error
    del proveedor, respuesta no parseable) devuelve un payload neutro con
    "No se encontró información suficiente para este apartado." en cada
    bloque, para que la interfaz lo muestre sin fingir que el análisis existe."""
    contexto = _construir_contexto_oficial(proyecto)
    resultado = _respuesta_vacia()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        return json.dumps(resultado, ensure_ascii=False)

    try:
        client = anthropic.Anthropic()
        respuesta = client.messages.create(
            model=MODELO,
            max_tokens=1500,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "Información oficial disponible sobre este proyecto de ley "
                        "(única fuente permitida para tu análisis):\n\n" + contexto
                    ),
                }
            ],
            output_config={"format": {"type": "json_schema", "schema": ESQUEMA_ANALISIS["schema"]}},
        )
        bloque_texto = "".join(
            bloque.text for bloque in respuesta.content if getattr(bloque, "type", None) == "text"
        )
        datos = json.loads(bloque_texto)
        for campo in CAMPOS_ANALISIS:
            if campo in datos:
                resultado[campo] = datos[campo]
    except (
        anthropic.APIStatusError,
        anthropic.APIConnectionError,
        anthropic.AnthropicError,
        json.JSONDecodeError,
        KeyError,
        ValueError,
    ):
        return json.dumps(_respuesta_vacia(), ensure_ascii=False)
    except Exception:
        return json.dumps(_respuesta_vacia(), ensure_ascii=False)

    return json.dumps(resultado, ensure_ascii=False)
