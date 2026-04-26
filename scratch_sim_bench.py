from concurrent_sim import run_continuous
import time

scenarios = [
    {
        "name": "1. Baseline (Flujo Ideal)",
        "csv": "silo-semi-empty.csv",
        "dests": 20,
        "hours": 2.0,
        "failures": False
    },
    {
        "name": "2. Alta Fragmentación (Demasiados destinos)",
        "csv": "silo-half-full.csv",
        "dests": 80,
        "hours": 2.0,
        "failures": False
    },
    {
        "name": "3. Stress Test (Almacén al límite)",
        "csv": "silo-almost-full.csv",
        "dests": 40,
        "hours": 4.0,
        "failures": False
    },
    {
        "name": "4. Caos Mecánico (Tolerancia a fallos)",
        "csv": "silo-half-full.csv",
        "dests": 40,
        "hours": 2.0,
        "failures": True
    }
]

md_output = """# 📊 Reporte de Benchmarks: Continuous Flow

Este documento presenta una batería de pruebas de estrés realizadas al sistema logístico utilizando el modo de flujo continuo (1000 cajas/h de llegada incesante).

Se han variado los parámetros de fragmentación de destinos, estado inicial del almacén y tolerancia a fallos mecánicos para demostrar la robustez del algoritmo Optimizado (Hash Maps O(1) + Dynamic Lookahead + Parallel Output).

---

"""

for s in scenarios:
    print(f"Running scenario: {s['name']}...")
    try:
        t0 = time.time()
        metrics = run_continuous(
            csv_path=s["csv"],
            duration_hours=s["hours"],
            num_destinations=s["dests"],
            arrival_rate=1000,
            verbose=False,
            algo_mode="Optimized",
            simulate_failures=s["failures"]
        )
        t1 = time.time()
        
        comp_pallets = metrics.get('pallets_completed', 0)
        full_pct = metrics.get('full_pallet_pct', '0%')
        occ = metrics.get('final_occupancy_pct', 0)
        mech = metrics.get('mechanical_failures', 0)
        reloc = metrics.get('total_relocations', 0)
        
        md_output += f"## {s['name']}\n"
        md_output += f"- **Estado Inicial:** `{s['csv']}`\n"
        md_output += f"- **Destinos Concurrentes:** {s['dests']}\n"
        md_output += f"- **Duración Simulación:** {s['hours']} horas (Carga total: {int(1000 * s['hours'])} cajas)\n"
        md_output += f"- **Fallos Mecánicos Activados:** {'Sí (5%)' if s['failures'] else 'No'}\n\n"
        
        md_output += "### Resultados\n"
        md_output += "| Métrica | Resultado |\n"
        md_output += "|---------|-----------|\n"
        md_output += f"| Pallets Completados | {comp_pallets} |\n"
        md_output += f"| Eficiencia de Llenado | {full_pct} |\n"
        md_output += f"| Ocupación Final | {occ:.1f}% |\n"
        md_output += f"| Tareas de Desatasco (Z=2) | {reloc} |\n"
        if s["failures"]:
            md_output += f"| Atascos Mecánicos Sufridos | **{mech}** |\n"
        md_output += f"| Tiempo de Ejecución Script | {t1-t0:.2f}s |\n\n"
        
        md_output += "---\n\n"
    except Exception as e:
        print(f"Failed {s['name']}: {e}")

with open("benchmark_results.md", "w", encoding="utf-8") as f:
    f.write(md_output)

print("Generated benchmark_results.md")
