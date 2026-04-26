# 📊 Reporte de Benchmarks: Continuous Flow

Este documento presenta una batería de pruebas de estrés realizadas al sistema logístico utilizando el modo de flujo continuo (1000 cajas/h de llegada incesante).

Se han variado los parámetros de fragmentación de destinos, estado inicial del almacén y tolerancia a fallos mecánicos para demostrar la robustez del algoritmo Optimizado (Hash Maps O(1) + Dynamic Lookahead + Parallel Output).

---

## 1. Baseline (Flujo Ideal)
- **Estado Inicial:** `silo-semi-empty.csv`
- **Destinos Concurrentes:** 20
- **Duración Simulación:** 2.0 horas (Carga total: 2000 cajas)
- **Fallos Mecánicos Activados:** No

### Resultados
| Métrica | Resultado |
|---------|-----------|
| Pallets Completados | 233 |
| Eficiencia de Llenado | 96.3% |
| Ocupación Final | 0.7% |
| Tareas de Desatasco (Z=2) | 460 |
| Tiempo de Ejecución Script | 2.02s |

---

## 2. Alta Fragmentación (Demasiados destinos)
- **Estado Inicial:** `silo-half-full.csv`
- **Destinos Concurrentes:** 80
- **Duración Simulación:** 2.0 horas (Carga total: 2000 cajas)
- **Fallos Mecánicos Activados:** No

### Resultados
| Métrica | Resultado |
|---------|-----------|
| Pallets Completados | 451 |
| Eficiencia de Llenado | 92.7% |
| Ocupación Final | 4.6% |
| Tareas de Desatasco (Z=2) | 1401 |
| Tiempo de Ejecución Script | 2.35s |

---

## 3. Stress Test (Almacén al límite)
- **Estado Inicial:** `silo-almost-full.csv`
- **Destinos Concurrentes:** 40
- **Duración Simulación:** 4.0 horas (Carga total: 4000 cajas)
- **Fallos Mecánicos Activados:** No

### Resultados
| Métrica | Resultado |
|---------|-----------|
| Pallets Completados | 873 |
| Eficiencia de Llenado | 96.0% |
| Ocupación Final | 4.7% |
| Tareas de Desatasco (Z=2) | 3256 |
| Tiempo de Ejecución Script | 99.17s |

---

## 4. Caos Mecánico (Tolerancia a fallos)
- **Estado Inicial:** `silo-half-full.csv`
- **Destinos Concurrentes:** 40
- **Duración Simulación:** 2.0 horas (Carga total: 2000 cajas)
- **Fallos Mecánicos Activados:** Sí (5%)

### Resultados
| Métrica | Resultado |
|---------|-----------|
| Pallets Completados | 460 |
| Eficiencia de Llenado | 94.5% |
| Ocupación Final | 3.2% |
| Tareas de Desatasco (Z=2) | 1268 |
| Atascos Mecánicos Sufridos | **336** |
| Tiempo de Ejecución Script | 3.42s |

---

