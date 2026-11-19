"""Quantities for sampled convex hulls, not true printer gamut measurements."""
import numpy as np
from scipy.optimize import linprog
from scipy.spatial import ConvexHull, HalfspaceIntersection


def hull_metrics(primary, comparison=None):
    first = primary.get('hull') if primary else None
    second = comparison.get('hull') if comparison else None
    result = {'primary_volume': float(first.volume) if first is not None else None,
              'comparison_volume': float(second.volume) if second is not None else None,
              'overlap_volume': None, 'volume_ratio': None}
    if first is None or second is None:
        return result
    result['volume_ratio'] = float(second.volume / first.volume) if first.volume else None
    # Find a strictly interior point by maximizing the inscribed ball radius.
    planes = np.vstack((first.equations, second.equations))
    planes = np.unique(np.round(planes, 12), axis=0)
    radii = np.linalg.norm(planes[:, :3], axis=1)
    solution = linprog([0, 0, 0, -1], A_ub=np.column_stack((planes[:, :3], radii)),
                       b_ub=-planes[:, 3], bounds=[(None, None)]*3+[(0, None)], method='highs')
    if solution.status == 2 or (solution.success and solution.x[3] <= 1e-8):
        result['overlap_volume'] = 0.0  # Disjoint or touching in lower dimensions.
        return result
    if not solution.success:
        raise ValueError('Convex-hull intersection could not be solved: '+solution.message)
    vertices = HalfspaceIntersection(planes, solution.x[:3]).intersections
    result['overlap_volume'] = min(float(ConvexHull(vertices).volume), float(first.volume), float(second.volume))
    return result
