"""Lissara Core - Optimization: Rendering-based refinement and adaptive scene revision."""
from typing import List, Dict, Any


def _to_float(val) -> float:
    """Convert a value to float."""
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(val)
    except (TypeError, ValueError):
        return 0.0


class OptimizationResult:
    """Result of scene optimization pass."""
    def __init__(self, improved: bool, loss_reduction: float,
                 iterations: int, converged: bool,
                 optimized_params: Dict[str, Any] = None):
        self.improved = improved
        self.loss_reduction = loss_reduction
        self.iterations = iterations
        self.converged = converged
        self.optimized_params = optimized_params or {}


def compute_pixel_loss(rendered: List[List[float]], source: List[List[float]]) -> float:
    """Compute mean absolute error between rendered and source images."""
    if not rendered or not source:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(rendered)):
        for j in range(len(rendered[0])):
            total += abs(rendered[i][j] - source[i][j])
            count += 1
    if count == 0:
        return 0.0
    return total / count


def compute_edge_loss(rendered_edges: List[List[float]], source_edges: List[List[float]]) -> float:
    """Compute edge displacement loss."""
    if not rendered_edges or not source_edges:
        return 0.0
    total = 0.0
    count = 0
    for i in range(len(rendered_edges)):
        for j in range(len(rendered_edges[0])):
            total += abs(rendered_edges[i][j] - source_edges[i][j])
            count += 1
    if count == 0:
        return 0.0
    return total / count


def compute_regularization_loss(paths: List[Any], lambda_reg: float = 0.1) -> float:
    """Compute regularization loss to discourage unnecessary complexity.

    Penalizes the total number of segments; a single path (rather than a list
    of them) is accepted for convenience.
    """
    if not paths:
        return 0.0
    if hasattr(paths, 'segments'):
        paths = [paths]
    total_pts = 0
    for p in paths:
        if hasattr(p, 'segments'):
            total_pts += len(p.segments)
    return lambda_reg * total_pts