"""
warehouse_chatbot.py - Explainable warehouse assistant for the dashboard.

The API key is intentionally read from environment variables or Streamlit input.
Do not hard-code hackathon keys in this file.
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
    "baseline": {
        "summary": "Greedy storage, cheapest pallet first, cheapest box first.",
        "storage": "Guarda cerca de la cabecera y agrupa ligeramente por destino en cada pasillo.",
        "pallet": "Abre los 8 slots activos con los destinos de menor coste estimado.",
        "retrieval": "Extrae la caja de pallet activo con menor coste de shuttle.",
    },
    "least_blocked": {
        "summary": "Baseline storage plus pallet selection that avoids blocked rear boxes.",
        "storage": "Guarda cerca de la cabecera y agrupa ligeramente por destino en cada pasillo.",
        "pallet": "Prioriza destinos cuyas siguientes 12 cajas tienen menos bloqueos en Z=2.",
        "retrieval": "Extrae la caja de pallet activo con menor coste de shuttle.",
    },
    "grouped": {
        "summary": "Destination-grouped storage plus cheapest pallet and box selection.",
        "storage": "Intenta mantener cajas del mismo destino en el mismo pasillo.",
        "pallet": "Abre slots de pallet segun coste estimado de recuperacion.",
        "retrieval": "Extrae la caja de pallet activo con menor coste de shuttle.",
    },
    "grouped_blocked": {
        "summary": "Destination grouping plus low-blockage pallet selection.",
        "storage": "Agrupa destinos por pasillo para simplificar oleadas de salida.",
        "pallet": "Evita destinos con muchas cajas traseras bloqueadas.",
        "retrieval": "Extrae la caja de pallet activo con menor coste de shuttle.",
    },
    "balanced": {
        "summary": "Balances shuttle load and favors finishing pallets.",
        "storage": "Penaliza shuttles ocupados para repartir trabajo entre las 32 lineas.",
        "pallet": "Evita destinos con bloqueos.",
        "retrieval": "Da mas prioridad a pallets que estan cerca de completarse.",
    },
    "most_boxes": {
        "summary": "Prioritizes destinations with the most boxes available.",
        "storage": "Guarda cerca de la cabecera y agrupa ligeramente por destino en cada pasillo.",
        "pallet": "Elige primero destinos con mas inventario disponible.",
        "retrieval": "Extrae la caja de pallet activo con menor coste de shuttle.",
    },
    "nearest_head": {
        "summary": "Fast, low-latency strategy that keeps new work close to the head.",
        "storage": "Favorece mucho huecos libres con X baja y shuttle disponible.",
        "pallet": "Elige destinos con buen coste total de throughput.",
        "retrieval": "Prioriza cajas cuyo shuttle esta libre y cuyo recorrido es barato.",
    },
    "spread_unblocked": {
        "summary": "Spreads load across aisles and strongly avoids blocked retrievals.",
        "storage": "Balancea ocupacion entre pasillos manteniendo afinidad de destino.",
        "pallet": "Selecciona pallets con bajo riesgo de relocalizacion.",
        "retrieval": "Prefiere mucho las cajas desbloqueadas en Z=1.",
    },
    "retrieval_friendly": {
        "summary": "Stores boxes in a way that reduces future retrieval pain.",
        "storage": "Prefiere Z=1, huecos cercanos, lineas balanceadas y afinidad de destino.",
        "pallet": "Selecciona pallets con bajo riesgo de relocalizacion.",
        "retrieval": "Penaliza cajas traseras y bloqueadas salvo que compense.",
    },
    "dense_batch": {
        "summary": "Clusters destinations and retrieves pallet batches aggressively.",
        "storage": "Concentra cajas del mismo destino en la misma linea de shuttle.",
        "pallet": "Selecciona destinos densos concentrados por pasillo/linea.",
        "retrieval": "Favorece continuar pallets que ya tienen progreso.",
    },
    "balanced_ready": {
        "summary": "Balances shuttles and chooses work from ready lanes.",
        "storage": "Evita sobrecargar una sola linea de shuttle.",
        "pallet": "Selecciona pallets repartidos entre varias lineas.",
        "retrieval": "Prioriza cajas cuyos shuttles estan libres o casi libres.",
    },
    "opportunistic": {
        "summary": "Uses relocations opportunistically when blockers are useful too.",
        "storage": "Agrupa destinos por pasillo.",
        "pallet": "Selecciona destinos densos.",
        "retrieval": "Acepta un bloqueo si la caja bloqueante tambien sirve para un pallet activo.",
    },
    "scarcity_depth": {
        "summary": "Finishes scarce pallets while staying depth-aware.",
        "storage": "Usa colocacion pensada para recuperar facil despues.",
        "pallet": "Prefiere destinos con cajas justas para completar un pallet.",
        "retrieval": "Penaliza cajas traseras y bloqueadas.",
    },
    "throughput": {
        "summary": "Optimizes for global throughput with balanced storage and cheap pallets.",
        "storage": "Reparte carga por pasillo y mantiene cajas relativamente cerca.",
        "pallet": "Selecciona pallets por coste total estimado de throughput.",
        "retrieval": "Extrae la caja de pallet activo con menor coste de shuttle.",
    },
}


def get_algorithm_explanation(config_name: str) -> dict:
    return ALGORITHM_EXPLANATIONS.get(config_name, ALGORITHM_EXPLANATIONS["baseline"])


def build_warehouse_context(
    result: dict,
    current_snapshot: dict,
    algorithm_config: str,
    focus_context: str = "",
) -> str:
    alg = get_algorithm_explanation(algorithm_config)
    avg_time = result.get("avg_time_per_pallet", "N/A")
    if avg_time == "0.0s" and result.get("pallets_completed"):
        sim_time = float(result.get("sim_time", 0))
        pallets = max(int(result.get("pallets_completed", 0)), 1)
        avg_time = f"{sim_time / pallets:.1f}s"

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
        f"- Avg time per pallet: {avg_time}",
        f"- Total relocations: {result.get('total_relocations', 'N/A')}",
        f"- Remaining boxes in silo: {result.get('remaining_in_silo', 'N/A')}",
        f"- Final occupancy: {result.get('silo_occupancy', 'N/A')}",
    ]
    if focus_context:
        lines.extend([
            "",
            "Focused route context:",
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
        system chooses one box over another, explain the decision criteria:
        shuttle availability, travel distance in X, active pallet priority,
        Z-depth blocking, relocations, and throughput.

        Keep answers practical. Prefer 3-6 short bullets when explaining a
        decision. Mention uncertainty when the dashboard only has aggregate
        metrics instead of the individual candidate list.

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
                        "text": (
                            f"{prompt}\n\n"
                            f"Operator question:\n{question}"
                        )
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

    if "caja" in lower_q or "box" in lower_q or "por que" in lower_q or "porque" in lower_q:
        return (
            "Ahora mismo no tengo acceso a la lista exacta de candidatas de esa decision, "
            "pero la logica de esta configuracion es:\n\n"
            f"- Configuracion: {algorithm_config}.\n"
            f"- Almacenaje: {alg['storage']}\n"
            f"- Pallets: {alg['pallet']}\n"
            f"- Recuperacion: {alg['retrieval']}\n"
            "- En la practica, gana la caja que reduce espera de shuttle, recorrido en X "
            "y riesgo de bloqueo Z=2, sin romper la prioridad de los 8 pallets activos."
        )

    return (
        f"Estoy funcionando con la configuracion `{algorithm_config}`. "
        f"{alg['summary']} Segun el estado actual del dashboard, puedo explicar "
        "decisiones por coste de shuttle, ocupacion, pallets activos, relocalizaciones "
        "y profundidad Z. Si tienes una caja o shuttle seleccionado en Route Zoom, "
        "esa ruta se manda tambien como contexto al chat."
    )
