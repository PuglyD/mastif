"""Instruments and DUTs: contracts, drivers, transports and the errors they raise.

This layer defines how mastif talks to hardware, without knowing any specific
hardware:

- **Contracts** (`contracts`, `std`): plain Protocols describing what a test needs.
- **Drivers and DUTs** (`driver`): classes marked with ``@driver`` / ``@dut`` that
  implement contracts, with typed config and an optional lifecycle.
- **Transports** (`transports`): TCP, serial, VISA and UDP, injected into drivers.
- **Registry** (`registry`): finds org drivers through entry points, with no import side
  effects.

Example:
    >>> from mastif.resources import Identity
    >>> Identity(serial="A123").mismatches({"serial": "A123"})
    {}
"""

from mastif.resources.contracts import (
    ContractInfo,
    ContractProblem,
    ProblemKind,
    contract,
    contract_info,
    contract_problems,
    satisfies,
)
from mastif.resources.errors import (
    ContractMismatch,
    DriverDefinitionError,
    DriverNotFound,
    IdentityMismatch,
    ProtocolError,
    ResourceError,
    ResourceFault,
    TransportError,
    TransportTimeout,
)
from mastif.resources.identity import Health, Identity

__all__ = [
    "ContractInfo",
    "ContractMismatch",
    "ContractProblem",
    "DriverDefinitionError",
    "DriverNotFound",
    "Health",
    "Identity",
    "IdentityMismatch",
    "ProblemKind",
    "ProtocolError",
    "ResourceError",
    "ResourceFault",
    "TransportError",
    "TransportTimeout",
    "contract",
    "contract_info",
    "contract_problems",
    "satisfies",
]
