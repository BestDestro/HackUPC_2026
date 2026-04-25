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
