"""The station layer: one physical test station, built from a YAML profile.

- `StationProfile`: the facts (resources, drivers, addresses, expected identities,
  role names, simulator overrides).
- `Station`: the composition root that builds everything without I/O, resolves roles,
  and opens, makes safe and closes resources through the `ResourceManager`.

Examples:
    >>> from mastif.station import StationProfile
    >>> StationProfile.from_yaml("station: bench-01\\nresources: {}").station
    'bench-01'
"""

from mastif.station.errors import RoleError, StationError
from mastif.station.manager import ResourceEvent, ResourceHandle, ResourceManager
from mastif.station.profile import ChannelEntry, ResourceEntry, StationProfile
from mastif.station.station import Station

__all__ = [
    "ChannelEntry",
    "ResourceEntry",
    "ResourceEvent",
    "ResourceHandle",
    "ResourceManager",
    "RoleError",
    "Station",
    "StationError",
    "StationProfile",
]
