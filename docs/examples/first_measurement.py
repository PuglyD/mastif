"""Compare simulated current readings without opening hardware connections."""

from mastif.kernel.limits import Limits
from mastif.kernel.results import Measurement
from mastif.kernel.units import mA

limit = Limits.at_most(250 * mA)

for current in (180, 300):
    result = Measurement("idle_current", current * mA, limit)
    print(f"{result.name}: {result.value:g} {result.unit} -> {result.verdict.value.upper()}")
