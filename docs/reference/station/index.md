# Station

The station layer turns a configuration profile into a working bench. It connects
resource names and requested capabilities to driver instances and coordinates their lifecycle.

- [`profile`](#mastif.station.profile) describes resources, role mappings, and simulation settings.
- [`station`](#mastif.station.station) composes the bench and resolves requested capabilities.
- [`manager`](#mastif.station.manager) coordinates opening, verification, safe-state attempts,
  and closing; [`errors`](#mastif.station.errors) describes composition and resolution failures.

Expand modules and classes in the right-hand TOC to browse public and private members.
For explanations and design decisions, see [Station concepts](../../learn/architecture/station.md).

::: mastif.station.profile

::: mastif.station.station

::: mastif.station.manager

::: mastif.station.errors
