"""
warehouse_chatbot.py - Contextual warehouse assistant for the dashboard.
"""

from __future__ import annotations

import json
import os
import textwrap
import urllib.error
import urllib.request
from typing import Optional

from silo import NUM_AISLES, NUM_SIDES, NUM_X, NUM_Y, NUM_Z


DEFAULT_MODEL = os.getenv("WAREHOUSE_AI_MODEL", "gemini-2.5-flash")
API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


def load_local_env(path: str = ".env") -> None:
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


load_local_env()


ALGORITHM_EXPLANATIONS = {
    "Optimized (Parallel + Lookahead)": {
        "summary": "Modo paralelo con lookahead dinamico y coordinacion entre shuttles.",
        "storage": "Guarda las cajas cerca de la cabecera cuando conviene y reparte carga entre lineas.",
        "pallet": "Abre pallets segun prioridad de throughput y disponibilidad real de cajas.",
        "retrieval": "Coordina varios shuttles a la vez y penaliza bloqueos y recorridos caros.",
    },
    "Naive (Legacy)": {
        "summary": "Modo legacy mas secuencial, con decisiones locales y menos coordinacion global.",
        "storage": "Guarda de forma mas simple, priorizando coste local del shuttle.",
        "pallet": "Selecciona pallets con reglas mas directas y menos anticipacion.",
        "retrieval": "Extrae de forma mas conservadora y con menor paralelismo.",
    },
}


SIM_MODE_EXPLANATIONS = {
    "Concurrent (Finite)": (
        "Llega un lote finito de cajas y el sistema combina entrada y salida hasta completar el trabajo."
    ),
    "Continuous (Infinite Flow)": (
        "Las cajas siguen entrando durante la ventana simulada y el sistema opera en flujo continuo."
    ),
}


def get_algorithm_explanation(mode_name: str) -> dict:
    return ALGORITHM_EXPLANATIONS.get(
        mode_name,
        {
            "summary": "Configuracion sin descripcion registrada.",
            "storage": "Sin detalle.",
            "pallet": "Sin detalle.",
            "retrieval": "Sin detalle.",
        },
    )


def get_api_key() -> str:
    return os.getenv("MLH_GEMMA_API_KEY", os.getenv("GEMINI_API_KEY", ""))


def build_warehouse_context(
    result: dict,
    current_snapshot: dict,
    algorithm_mode: str,
    simulation_mode: str,
    focus_context: str = "",
) -> str:
    alg = get_algorithm_explanation(algorithm_mode)
    sim_summary = SIM_MODE_EXPLANATIONS.get(simulation_mode, simulation_mode)
    total_slots = NUM_AISLES * NUM_SIDES * NUM_X * NUM_Y * NUM_Z
    avg_time = result.get("avg_time_per_pallet", "N/A")

    lines = [
        "Warehouse physical context:",
        f"- Layout: {NUM_AISLES} aisles, {NUM_SIDES} sides per aisle, {NUM_X} X positions, {NUM_Y} shuttle levels, {NUM_Z} depth levels.",
        f"- Total storage capacity: {total_slots} slots.",
        f"- Total shuttles: {NUM_AISLES * NUM_Y}.",
        f"- Active pallet slots in operation: up to 8.",
        "",
        "Simulation mode:",
        f"- Current mode: {simulation_mode}",
        f"- Mode summary: {sim_summary}",
        "",
        "Algorithm mode:",
        f"- Current algorithm: {algorithm_mode}",
        f"- Summary: {alg['summary']}",
        f"- Storage policy: {alg['storage']}",
        f"- Pallet policy: {alg['pallet']}",
        f"- Retrieval policy: {alg['retrieval']}",
        "",
        "Current warehouse metrics:",
        f"- Simulated time: {current_snapshot.get('time_min', 0):.1f} min",
        f"- Boxes stored: {int(current_snapshot.get('boxes_stored', 0))}",
        f"- Boxes retrieved: {int(current_snapshot.get('boxes_retrieved', 0))}",
        f"- Pallets completed: {int(current_snapshot.get('pallets_completed', 0))}",
        f"- Occupancy: {current_snapshot.get('occupancy_pct', 0):.1f}%",
        f"- Pending input: {int(current_snapshot.get('pending_input', 0))}",
        f"- Relocations: {int(current_snapshot.get('relocations', 0))}",
        f"- Busy shuttles: {int(current_snapshot.get('shuttles_busy', 0))}",
        "",
        "Run summary:",
        f"- Boxes arrived: {result.get('boxes_arrived', 'N/A')}",
        f"- Boxes stored total: {result.get('boxes_stored', 'N/A')}",
        f"- Boxes retrieved total: {result.get('boxes_retrieved', 'N/A')}",
        f"- Pallets completed total: {result.get('pallets_completed', 'N/A')}",
        f"- Boxes per hour: {result.get('boxes_per_hour', 'N/A')}",
        f"- Pallets per hour: {result.get('pallets_per_hour', 'N/A')}",
        f"- Avg time per pallet: {avg_time}",
        f"- Remaining boxes in silo: {result.get('remaining_in_silo', 'N/A')}",
        f"- Peak occupancy: {result.get('peak_occupancy', 'N/A')}",
        f"- Final occupancy: {result.get('silo_occupancy', 'N/A')}",
    ]

    if focus_context:
        lines.extend([
            "",
            "Focused live context:",
            focus_context,
        ])

    return "\n".join(lines)


def build_system_prompt(context: str) -> str:
    return textwrap.dedent(
        f"""
        You are the voice of an automated warehouse silo for a hackathon demo.
        Always answer in Spanish.
        Be concrete, operational, and specific.
        If a shuttle is selected, explain first:
        1. which shuttle it is,
        2. what it is doing right now,
        3. which box it is handling or about to handle,
        4. where it is going,
        5. why the system chose that action.

        Do not answer in generic terms when live context is available.
        If the exact next box is unknown, say that clearly instead of inventing it.
        Prefer short paragraphs or bullet lists.
        Do not use code blocks, tables, or lines starting with four spaces.
        Keep the answer compact and directly readable in a chat UI.

        Use this warehouse context:

        {context}
        """
    ).strip()


def normalize_ai_response(text: str) -> str:
    """Normalize model text so Streamlit markdown does not render it as code blocks."""
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", "    ")
    text = textwrap.dedent(text).strip()

    normalized_lines = []
    blank_count = 0
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            blank_count += 1
            if blank_count <= 1:
                normalized_lines.append("")
            continue

        blank_count = 0
        normalized_lines.append(line.lstrip())

    return "\n".join(normalized_lines).strip()


def ask_gemini(question: str, context: str, api_key: Optional[str] = None, model: str = DEFAULT_MODEL) -> str:
    api_key = api_key or get_api_key()
    if not api_key:
        raise ValueError("Missing API key in .env")

    prompt = build_system_prompt(context)
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{prompt}\n\nPregunta del operador:\n{question}"}],
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 650,
        },
    }

    request = urllib.request.Request(
        url=f"{API_URL_TEMPLATE.format(model=model)}?key={api_key}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"AI API error {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"AI API connection error: {exc.reason}") from exc

    try:
        parts = payload["candidates"][0]["content"]["parts"]
        raw_response = "\n".join(part.get("text", "") for part in parts).strip()
        return normalize_ai_response(raw_response)
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected AI API response: {payload}") from exc


def fallback_answer(question: str, focus_summary: str = "", algorithm_mode: str = "") -> str:
    alg = get_algorithm_explanation(algorithm_mode)
    if focus_summary:
        return (
            "No he podido consultar la API ahora mismo, pero con el contexto en vivo te puedo resumir esto:\n\n"
            f"{focus_summary}\n\n"
            f"Ademas, la logica activa es `{algorithm_mode}`: {alg['summary']}"
        )

    return (
        "No he podido consultar la API ahora mismo. "
        f"La logica activa es `{algorithm_mode}` y su idea general es: {alg['summary']}"
    )
