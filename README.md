# HackUPC_2026
Repositorio para la HackUPC de 2026 (Reto de Inditex).

## Comparar algoritmos

Ejecuta todos los algoritmos contra el CSV inicial y estados generados al 25%, 45% y 70% de ocupacion:

```bash
python benchmark_algorithms.py --incoming 1000
```

Ejecuta solo algunos algoritmos:

```bash
python benchmark_algorithms.py --algorithms baseline nearest_head balanced_ready throughput
```

Los resultados se guardan en `benchmark_results/algorithm_benchmark.csv` y `benchmark_results/algorithm_benchmark.md`.

## Dashboard con chatbot

Ejecuta el dashboard:

```bash
streamlit run dashboard.py
```

Para activar el chatbot con Gemma/Gemini, define la clave en la terminal antes de abrir Streamlit:

```powershell
$env:MLH_GEMMA_API_KEY="tu_api_key"
$env:WAREHOUSE_AI_MODEL="gemma-3-27b-it"
streamlit run dashboard.py
```

Tambien puedes pegar la API key en el campo de password del sidebar. Si la API no esta disponible, el chat usa una explicacion local basada en las metricas y la configuracion del algoritmo.

El panel `Route Zoom` permite seguir una caja concreta o un shuttle:

- `Box`: muestra donde estaba una caja, si fue almacenada, recuperada o relocalizada.
- `Shuttle`: muestra los recorridos de una lanzadera concreta por X.
- `Live Shuttle Movement`: muestra los 32 shuttles moviendose en el tiempo del timeline.
- Click en un shuttle: pausa el playback, lo selecciona y muestra que caja mueve, destino, X y decision.
- Buscador: filtra por box id, destino o shuttle id en vez de depender de una lista larga.
- La linea vertical marca el instante seleccionado en el timeline.
- Si preguntas en el chat con una caja/shuttle seleccionado, esa ruta se usa como contexto para explicar por que va ahi o que decision tomo el sistema.
