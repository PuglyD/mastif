"""mastif: a domain-neutral framework for automated test equipment (ATE).

mastif provides the parts every test station needs, regardless of what it tests:
units and results (`mastif.kernel`), instrument and DUT primitives, and a test
execution engine. Organisations build their own SDK (contracts, drivers, DUT types)
and UI on top.

Examples:
    >>> import mastif
    >>> mastif.__version__
    '0.1.0.dev0'
"""

__version__ = "0.1.0.dev0"
