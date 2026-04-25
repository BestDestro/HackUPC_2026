# Hack the Flow — Requisitos del Problema

## 1. Contexto general

El sistema modela un **centro de distribución automatizado** con silos que gestionan el almacenamiento temporal de cajas. Los silos sirven a miles de tiendas físicas y plataformas de e-commerce. El reto consiste en diseñar los **algoritmos de entrada y salida** para minimizar los tiempos de respuesta y maximizar la agilidad del sistema.

---

## 2. Arquitectura física del silo

### Dimensiones de la cuadrícula
| Dimensión | Rango | Descripción |
|---|---|---|
| **Aisle** (Pasillo) | 1–4 | 4 pasillos independientes |
| **Side** (Lado) | 1–2 | 2 lados por pasillo |
| **X** (Posición horizontal) | 1–60 | 60 posiciones por lado (indexado en base 1) |
| **Y** (Nivel vertical) | 1–8 | 8 niveles por posición |
| **Z** (Profundidad) | 1–2 | 2 posiciones de profundidad por hueco |

- **Total de slots**: 4 × 2 × 60 × 8 × 2 = **7.680 posiciones**

---

## 3. Shuttles (lanzaderas)

- **32 shuttles independientes** operando en paralelo.
- Cada shuttle opera en una única combinación fija de **(Aisle, Y-level)**.
  - 4 aisles × 8 niveles = 32 shuttles en total.
- **Capacidad**: 1 caja por viaje (una sola caja a la vez).
- **Posición inicial**: todos los shuttles arrancan en X=1.
- **Fórmula de tiempo de desplazamiento**:
  ```
  t = 10 + d
  ```
  donde `t` es el tiempo en segundos y `d` es la distancia recorrida en X.
- Los shuttles son **recursos compartidos** entre operaciones de entrada (STORE) y salida (RETRIEVE).

---

## 4. Restricción de profundidad Z

- **Z=1** es la posición frontal (accesible directamente por el shuttle).
- **Z=2** es la posición trasera (solo accesible si Z=1 está vacío).
- Si se necesita extraer una caja en Z=2 y Z=1 está ocupada → hay que **reubicar** la caja de Z=1 primero (operación de relocalización con coste de tiempo adicional).
- Al **cargar el estado inicial desde CSV**: puede existir Z=2 ocupado con Z=1 vacío (estado heredado de extracciones previas). Este estado es válido y no debe rechazarse.

---

## 5. Identificador de caja (Box ID)

- Cada caja tiene un código de **20 dígitos**.
- El código contiene información codificada:
  - Bytes 7–15 (posiciones 7 a 14): **destino** de la caja.

---

## 6. Formato CSV de estado inicial

- Archivo: `silo-semi-empty.csv`
- Cabecera: `posicion,etiqueta`
- **Formato de posición**: cadena de 11 dígitos sin separadores: `AASSSXXXYYYZZ`
  - `AA`: Aisle (01–04)
  - `SSS` (o `SS`): Side (01–02)
  - `XXX`: posición X (001–060), base 1
  - `YY`: nivel Y (01–08)
  - `ZZ`: profundidad Z (01–02)
- `etiqueta`: box ID de 20 dígitos (vacío si el slot está libre).

---

## 7. Destinos y pallets

- La simulación debe funcionar para **3 escenarios** de número de destinos:
  - **20 destinos**
  - **40 destinos**
  - **80 destinos**
- Cada **pallet** agrupa **12 cajas** del mismo destino.
- Hay un máximo de **8 pallets activos** simultáneamente en la zona de palletización (robots).
- Al aumentar los destinos (especialmente a 80), el sistema debe gestionar activamente qué 8 destinos tienen prioridad de palletización para evitar deadlocks.

---

## 8. Flujo de operación

### Modo batch / sintético
- Se generan N cajas para los escenarios de 20/40/80 destinos.
- Se ejecuta primero la **fase de entrada** (llenar el silo) y luego la **fase de salida** (extraer pallets completos).

### Modo CSV (estado inicial real)
- El silo se precarga desde `silo-semi-empty.csv`.
- Se ejecuta directamente la **fase de salida** extrayendo los pallets que se puedan completar.

### Modo concurrente (entrada + salida simultánea)
- **1.000 cajas por hora** llegan al silo (intervalo ~3,6 s entre caja y caja).
- Las operaciones de **almacenamiento** (STORE) y **extracción** (RETRIEVE) ocurren simultáneamente, compitiendo por los mismos 32 shuttles.
- Los shuttles tienen un timestamp `busy_until`: solo se les asignan tareas cuando están libres.
- N cajas entrantes definido previamente; al terminar de llegar, el sistema pasa a modo solo-salida.

### Modo continuo (flujo real, estado estacionario)
- **Input indefinido**: cajas llegan a 1.000/hora **sin parar** durante X horas.
- Las cajas se generan **on-the-fly** conforme avanza el tiempo simulado (no pre-generadas).
- El sistema **debe mantenerse en equilibrio** (output ≈ input) para que el silo no se sature.
- Condición de fin: se han simulado X horas de operación real.
- Si la ocupación supera el **85%**, el sistema emite alerta de sobrecarga.
- Si la ocupación supera el **60%**, el planificador cambia prioridad hacia output.
- Escenario objetivo: **turno de trabajo de 8 horas** (8.000 cajas por hora-turno).

---

## 9. Algoritmos requeridos

### Algoritmo de entrada (STORE / Chaotic Storage)
- **Almacenamiento caótico** con heurística de distribución de carga entre los 4 pasillos.
- **Greedy con consciencia del shuttle**: para cada shuttle libre, seleccionar la mejor posición candidata (minimizar tiempo de viaje y maximizar agrupación por destino).
- Scoring de posición basado en:
  1. Distancia al shuttle (minimizar `d`).
  2. Agrupación de destinos por pasillo (maximizar).
  3. Preferencia por Z=1 (evitar tener que relocalizar después).
- Optimización: evaluar 1 candidato por shuttle (32) en lugar de los 7.680 slots completos.

### Algoritmo de salida (RETRIEVE / Greedy Extraction)
- Extraer cajas priorizando los destinos con más cajas acumuladas.
- Gestión dinámica de la prioridad de los 8 slots de palletización.
- Completar un pallet de 12 cajas antes de abrir uno nuevo del mismo destino.

### Algoritmo de relocalización (Z-Constraint Relocation)
- Detectar bloqueo: Z=1 ocupado cuando se necesita Z=2.
- Mover la caja bloqueante a otra posición libre (oportunísticamente en la misma pasillo/nivel si es posible).
- Aprovechar la relocalización para palletizar si la caja bloqueante es del destino activo.

---

## 10. Métricas de evaluación

| Métrica | Descripción |
|---|---|
| Pallets completados | Total de pallets de 12 cajas cerrados |
| % pallets completos | (pallets_completados × 12) / cajas_totales |
| Tiempo medio por pallet | Suma de tiempos de extracción / pallets |
| Relocalizaciones | Número de movimientos extra por restricción Z |
| Ocupación máxima | % máximo de slots ocupados durante la simulación |
| Cajas/hora procesadas | Throughput efectivo del sistema |
| Eventos de sobrecarga >85% | Número de veces que se superó el umbral crítico |
| Cajas en espera (pending) | Backlog de cajas pendientes de almacenar |

---

## 11. Stack tecnológico

- **Lenguaje principal**: Python
- **Visualización / Dashboard**: Streamlit + Plotly (gráficos interactivos en tiempo real)
- **Estructuras de datos**: Hash maps (dict) para lookups O(1) del estado del grid, ubicación de cajas e inventario por destino.
- **Repositorio**: https://github.com/BestDestro/HackUPC_2026.git

---

## 12. Ficheros del proyecto

| Fichero | Rol |
|---|---|
| `models.py` | Data classes: `Box`, `Position`, `Task`, `Pallet` |
| `silo.py` | Estado del grid con hash maps (7.680 slots) |
| `shuttle.py` | 32 shuttles, movimiento y cola de tareas |
| `logistics_manager.py` | Cerebro: almacenamiento caótico, extracción greedy, relocalización Z |
| `simulation.py` | Motor de simulación: escenarios sintéticos 20/40/80 destinos |
| `concurrent_sim.py` | Motor concurrente: entrada + salida simultánea, modo continuo |
| `csv_loader.py` | Carga del estado inicial desde `silo-semi-empty.csv` |
| `main.py` | Punto de entrada CLI: modos `csv`, `concurrent`, `continuous`, `20/40/80` |
| `dashboard.py` | Dashboard Streamlit con playback temporal y 6 gráficos Plotly |
