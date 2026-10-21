"""Test helpers for mastif SDK authors: fakes, simulators and conformance checks.

Organisations that write their own drivers and DUT types install this package in
their test environment. It provides fake transports and conformance helpers, so
drivers can be tested without hardware, using fakes instead of mocks as `AGENTS.md`
asks.

Example:
    >>> from mastif_testing import FakeLineIO
    >>> from mastif.resources.transports import Scpi
    >>> Scpi(FakeLineIO({"*IDN?": "ACME,PSU-X,A123,1.4"})).identify().model
    'PSU-X'
"""

from mastif_testing.conformance import LifecycleReport, assert_satisfies, check_lifecycle
from mastif_testing.fakes import FakeDatagramPeer, FakeLineIO, FakeStream

__all__ = [
    "FakeDatagramPeer",
    "FakeLineIO",
    "FakeStream",
    "LifecycleReport",
    "assert_satisfies",
    "check_lifecycle",
]
