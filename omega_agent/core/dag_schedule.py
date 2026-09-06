"""Compute execution waves for parallel DAG scheduling."""

from typing import Dict, List, Set

from omega_agent.core.types import TaskNode


def compute_execution_waves(dag: List[TaskNode]) -> List[List[TaskNode]]:
    """
    Topological levelization: tasks in the same wave have no mutual dependencies
    and all deps satisfied by prior waves — safe to run in parallel.
    """
    if not dag:
        return []

    by_id: Dict[str, TaskNode] = {t.id: t for t in dag}
    completed: Set[str] = set()
    remaining = list(dag)
    waves: List[List[TaskNode]] = []

    while remaining:
        ready = [
            t for t in remaining
            if all(dep in completed or dep not in by_id for dep in t.dependencies)
        ]
        if not ready:
            waves.append(list(remaining))
            break

        waves.append(ready)
        for task in ready:
            completed.add(task.id)
            remaining.remove(task)

    return waves
