"""VMD-Hydrate-MCP — an MCP server for VMD-driven GROMACS/LAMMPS analysis and
clathrate-hydrate cage science.

The `analysis.hydrate` subpackage is pure-NumPy (no VMD, no MDAnalysis) so the
scientific core is unit-testable in CI without a display or a VMD install.
"""

__version__ = "0.2.0"
