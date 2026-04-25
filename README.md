# 📦 Hack the Flow - 3D Logistics Simulator

![HackUPC 2026](https://img.shields.io/badge/Event-HackUPC%_2026-blueviolet)
![Status](https://img.shields.io/badge/Status-Steady_State_Reached-success)
![Throughput](https://img.shields.io/badge/Throughput-%3E1500_boxes%2Fhr-brightgreen)

Este repositorio contiene la solución algorítmica para el reto **Hack the Flow**, que consiste en la simulación y optimización del tráfico de un silo logístico automatizado 3D con capacidad para 7.680 cajas, gestionado por 32 shuttles robóticos.

## 🧠 Evolución Algorítmica: Del Caos al Steady-State

Durante el desarrollo, nos dimos cuenta de que la dificultad del reto no era solo almacenar cajas, sino **sostener un flujo continuo (1000 cajas/hora) sin colapsar**. Por ello, desarrollamos y enfrentamos dos estrategias distintas:

### 1. El Enfoque "Naive" (Por qué empezamos por aquí)
Todo sistema logístico parte de la intuición humana básica. Inicialmente, nuestro algoritmo se basaba en las reglas más obvias:
*   **Esperar al pallet perfecto:** No preparar un pallet de salida hasta tener *exactamente* 12 cajas del mismo destino en el almacén.
*   **Extracción secuencial:** Un shuttle saca una caja. Cuando termina, otro shuttle saca la siguiente.
*   **Prioridad a la entrada:** Solo se vacía el almacén cuando este supera el 50% de ocupación.

**El Problema:** Este modelo es un cuello de botella letal. Al simular un flujo continuo de 1000 cajas/hora, el sistema es incapaz de dar salida al mismo ritmo. La ocupación se dispara por encima del 85% y el almacén revienta.

### 2. El Enfoque Optimizado (La Solución Final)
Para alcanzar un *Steady-State* (equilibrio perfecto donde Salidas ≥ Entradas), rediseñamos el motor con cuatro pilares:

1.  **State Management O(1):** Sustituimos las búsquedas matriciales por *Hash Maps* (`dict` y `set` en Python) para ubicar cualquier caja en tiempo $O(1)$, bajando el tiempo de cómputo de 14 minutos a **2.7 segundos**.
2.  **Lookahead Dinámico (Anticipación):** En lugar de esperar a tener 12 cajas, el sistema "activa" pallets en los docks de salida en cuanto un destino alcanza **8 cajas**. Esto permite que los shuttles empiecen a extraer cajas *mientras* el resto siguen llegando, solapando tiempos muertos.
3.  **Paralelización Masiva (Multi-Shuttle):** Implementamos un planificador *Round-Robin* que asigna tareas a los **32 shuttles simultáneamente**. Si hay trabajo por hacer, ningún robot se queda inactivo (Idle).
4.  **Prioridad Competitiva:** Eliminamos el bloqueo por ocupación. Ahora, la extracción compite en igualdad de condiciones con el almacenamiento.

### 📊 Comparativa de Rendimiento (Test de Estrés 2 Horas)

| Métrica | Naive (Legacy) | Optimized (Nuestro Algoritmo) |
| :--- | :--- | :--- |
| **Throughput (Salida)** | ~450 cajas/h | **>1.500 cajas/h** 🚀 |
| **Ocupación Pico** | >85% (Colapso) | **<12%** |
| **Tiempo medio / Pallet** | >120s | **~39s** |
| **Estado del Silo** | Saturado | **Vaciado fluido** |

---

## 🛠️ Guía de Uso del Sistema

El proyecto cuenta con dos modos de ejecución: uno para pura potencia de cálculo y otro visual e interactivo para presentaciones.

### Instalación
Asegúrate de tener instaladas las dependencias gráficas y de datos:
```bash
pip install streamlit pandas plotly
```

### 🖥️ 1. Live Dashboard (Recomendado para la demo)
Hemos construido un panel de control en tiempo real con **Streamlit** que permite viajar en el tiempo a lo largo de la simulación y comparar algoritmos visualmente.

Para arrancarlo:
```bash
python -m streamlit run dashboard.py
```
*(Se abrirá automáticamente en `http://localhost:8502`)*

**Cómo probarlo:**
1. En el panel izquierdo, selecciona **Operation Mode -> Continuous**.
2. En **Algorithm Strategy**, elige `Naive` para ver cómo el sistema colapsa, o `Optimized` para ver la solución perfecta.
3. Pon una duración de **0.5 a 2.0 horas**.
4. Haz clic en **Run Simulation** y usa la barra de *Timeline* inferior para reproducir los eventos.

### 💻 2. Ejecución desde Terminal (CLI)
Para pruebas masivas (por ejemplo, simular un turno de 8 horas) sin cargar la interfaz gráfica, puedes usar el CLI del simulador directamente:

```bash
# Sintaxis: python main.py continuous <archivo.csv> <horas> <tasa_llegada>
python main.py continuous silo-semi-empty.csv 8.0 1000
```
Verás un volcado en directo de las métricas (`arrived`, `stored`, `pending`, `occ%`) y un reporte final ultrarrápido al concluir.

---
*Desarrollado para HackUPC 2026.* 🚀
