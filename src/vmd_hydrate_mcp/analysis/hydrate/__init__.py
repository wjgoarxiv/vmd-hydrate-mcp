"""Pure-NumPy clathrate-hydrate analysis, ported 1:1 from the validated
reference methods. Units are **nanometers** throughout.

Nothing here imports VMD or MDAnalysis — it operates on plain NumPy arrays so it
can be validated in CI against hard numeric goldens (e.g. F4(222_S2 first-10)
== 0.926698).
"""

from .geometry import Cell
from .order_params import order_parameters, OrderParamResult
from .hbond import hbond_network, HBondResult
from .cage import identify_cages, CageResult, Cage

__all__ = [
    "Cell",
    "order_parameters",
    "OrderParamResult",
    "hbond_network",
    "HBondResult",
    "identify_cages",
    "CageResult",
    "Cage",
]
