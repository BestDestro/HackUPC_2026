import random
from concurrent_sim import ConcurrentManager
from models import Box, Position

class FaultyConcurrentManager(ConcurrentManager):
    """
    Módulo extra para simular fallos mecánicos (Shuttle Mechanical Failures).
    
    Hereda de ConcurrentManager para no "ensuciar" el algoritmo principal.
    Simplemente intercepta las órdenes de ejecución (store y retrieve) reales
    (una vez la heurística y el planificador ya han tomado la decisión)
    y añade una probabilidad de fallo al intentar agarrar/dejar la caja.
    
    Si hay fallo, el shuttle sufre una penalización de tiempo (retry) antes de continuar.
    """
    def __init__(self, silo, shuttle_mgr, failure_rate=0.05, retry_penalty=12.0):
        super().__init__(silo, shuttle_mgr)
        self.failure_rate = failure_rate
        self.retry_penalty = retry_penalty
        self.total_mechanical_failures = 0

    def _execute_store(self, box: Box, pos: Position, t: float) -> float:
        key = (pos.aisle, pos.y)
        # Tirada de dados para fallo mecánico
        if random.random() < self.failure_rate:
            self.total_mechanical_failures += 1
            # Añadimos el tiempo de penalización por atasco/reintento
            self.shuttle_free_at[key] = max(t, self.shuttle_free_at[key]) + self.retry_penalty
            
        return super()._execute_store(box, pos, t)

    def _execute_retrieve(self, box: Box, t: float) -> float:
        pos = box.position
        if pos:
            key = (pos.aisle, pos.y)
            if random.random() < self.failure_rate:
                self.total_mechanical_failures += 1
                self.shuttle_free_at[key] = max(t, self.shuttle_free_at[key]) + self.retry_penalty
                
        return super()._execute_retrieve(box, t)
    
    def _build_metrics(self, incoming_boxes, pending_input) -> dict:
        metrics = super()._build_metrics(incoming_boxes, pending_input)
        metrics["mechanical_failures"] = self.total_mechanical_failures
        return metrics
