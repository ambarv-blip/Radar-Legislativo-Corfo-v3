# -*- coding: utf-8 -*-
"""
ai/analysis.py
=================
Placeholder del módulo de análisis IA. En un ciclo posterior, esta función
llamará a la API de Claude para generar el análisis estructurado (qué
cambió, por qué importa para Corfo, regla activada, nivel de alerta,
acción recomendada) sobre cada evento nuevo detectado por el monitor.

Por ahora solo devuelve un mensaje placeholder explícito, para que la
interfaz pueda mostrar el campo sin fingir que ya existe un análisis real.
"""


def generar_analisis_placeholder(proyecto_nombre: str, evento_descripcion: str | None) -> str:
    return (
        "Análisis generado por IA: pendiente de integrar (placeholder). "
        f"Cuando se conecte el modelo, aquí aparecerá el análisis estructurado del evento "
        f"más reciente de \"{proyecto_nombre}\"."
    )
