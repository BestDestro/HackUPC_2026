"""
warehouse_chatbot.py - Explainable warehouse assistant for the dashboard.

Reads the API key from environment variables or a Streamlit input field.
"""

import json
import os
import textwrap
import urllib.error
import urllib.request


DEFAULT_MODEL = os.getenv("WAREHOUSE_AI_MODEL", "gemma-3-27b-it")
API_URL_TEMPLATE = (
    "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
)


def load_local_env(path: str = ".env"):
    """Load simple KEY=VALUE pairs from a local .env file if present."""
    if not os.path.exists(path):
        return

    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and value and key not in os.environ:
                os.environ[key] = value


load_local_env()


ALGORITHM_EXPLANATIONS = {
    "Optimized": {
        "summary": "Parallel shuttle scheduling with lookahead for active pallets.",
        "storage": "Intercala entrada y salida usando los shuttles libres con una heuristica orientada a throughput.",
        "pallet": "Abre pallets con lookahead dinamico para empezar salidas antes.",
        "retrieval": "Puede asignar varias recuperaciones en paralelo cuando hay lineas libres.",
    },
    "Naive": {
        "summary": "Legacy strategy with stricter gating and lower concurrency.",
        "storage": "Usa la logica base con menos agresividad en la asignacion simultanea.",
        "pallet": "Es mas conservador al abrir trabajo de salida.",
        "retrieval": "Prioriza una salida mas secuencial y con menos paralelismo efectivo.",
    },
}


def get_algorithm_explanation(config_name: str) -> dict:
    return ALGORITHM_EXPLANATIONS.get(config_name, ALGORITHM_EXPLANATIONS["Optimized"])


def build_warehouse_context(
    result: dict,
    current_snapshot: dict,
    algorithm_config: str,
    focus_context: str = "",
) -> str:
    alg = get_algorithm_explanation(algorithm_config)
    lines = [
        "Simulation context:",
        f"- Algorithm config: {algorithm_config}",
        f"- Algorithm summary: {alg['summary']}",
        f"- Storage logic: {alg['storage']}",
        f"- Pallet selection logic: {alg['pallet']}",
        f"- Retrieval logic: {alg['retrieval']}",
        f"- Simulated time now: {current_snapshot.get('time_min', 0):.1f} min",
        f"- Boxes stored now: {int(current_snapshot.get('boxes_stored', 0))}",
        f"- Boxes retrieved now: {int(current_snapshot.get('boxes_retrieved', 0))}",
        f"- Pallets completed now: {int(current_snapshot.get('pallets_completed', 0))}",
        f"- Active pallets now: {int(current_snapshot.get('active_pallets', 0))}",
        f"- Pending input now: {int(current_snapshot.get('pending_input', 0))}",
        f"- Occupancy now: {current_snapshot.get('occupancy_pct', 0):.1f}%",
        f"- Busy shuttles now: {int(current_snapshot.get('shuttles_busy', 0))}",
        f"- Total boxes arrived: {result.get('boxes_arrived', 'N/A')}",
        f"- Total boxes stored: {result.get('boxes_stored', 'N/A')}",
        f"- Total boxes retrieved: {result.get('boxes_retrieved', 'N/A')}",
        f"- Total pallets completed: {result.get('pallets_completed', 'N/A')}",
        f"- Full pallet percentage: {result.get('full_pallet_pct', 'N/A')}",
        f"- Avg time per pallet: {result.get('avg_time_per_pallet', 'N/A')}",
        f"- Total relocations: {result.get('total_relocations', 'N/A')}",
        f"- Remaining boxes in silo: {result.get('remaining_in_silo', 'N/A')}",
        f"- Final occupancy: {result.get('silo_occupancy', 'N/A')}",
    ]
    if focus_context:
        lines.extend([
            "",
            "Focused movement context:",
            focus_context,
        ])
    return "\n".join(lines)


def build_system_prompt(context: str) -> str:
    return textwrap.dedent(
        f"""
        You are the voice of an automated warehouse silo for a hackathon demo.
        Answer in Spanish, clearly and concretely, for warehouse operators.
        Use the simulation context below. Do not invent exact box IDs or exact
        positions if they are not present in the context. If asked why the
        system chooses one shuttle or one box over another, explain the decision
        criteria: shuttle availability, travel distance in X, active pallet
        priority, Z-depth blocking, relocations, and throughput.

        Keep answers practical. Prefer 3-6 short bullets when explaining a
        decision. Mention uncertainty when the dashboard only has aggregate
        metrics instead of a full candidate ranking.

        {context}
        """
    ).strip()


def ask_gemma(question: str, context: str, api_key: str, model: str = DEFAULT_MODEL) -> str:
    if not api_key:
        raise ValueError("Missing API key")

    prompt = build_system_prompt(context)
    body = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": f"{prompt}\n\nOperator question:\n{question}"
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
            "topP": 0.9,
            "maxOutputTokens": 650,
        },
    }

    url = API_URL_TEMPLATE.format(model=model)
    request = urllib.request.Request(
        url=f"{url}?key={api_key}",
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
        return "\n".join(part.get("text", "") for part in parts).strip()
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Unexpected AI API response: {payload}") from exc


def fallback_answer(question: str, context: str, algorithm_config: str) -> str:
    alg = get_algorithm_explanation(algorithm_config)
    lower_q = question.lower()

    if "shuttle" in lower_q or "caja" in lower_q or "box" in lower_q or "por que" in lower_q or "porque" in lower_q:
        return (
            "No tengo la lista completa de candidatas en bruto, pero con el contexto "
            "actual puedo resumir la decision asi:\n\n"
            f"- Estrategia: {algorithm_config}.\n"
            f"- Entrada: {alg['storage']}\n"
            f"- Pallets: {alg['pallet']}\n"
            f"- Salida: {alg['retrieval']}\n"
            "- Si has seleccionado un shuttle o una caja, el chat prioriza explicar "
            "ese movimiento, su recorrido y la razon operativa asociada."
        )

    return (
        f"Estoy funcionando con la estrategia `{algorithm_config}`. "
        f"{alg['summary']} Puedo explicar decisiones usando ocupacion, pallets activos, "
        "estado de shuttles y movimientos seleccionados."
    )
