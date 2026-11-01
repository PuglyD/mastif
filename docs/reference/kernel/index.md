# Kernel

The kernel gives the rest of mastif a shared vocabulary for values, acceptance
criteria, and outcomes. Its operations are pure: they do not communicate with hardware.

- [`units`](#mastif.kernel.units) keeps units attached to values;
  [`limits`](#mastif.kernel.limits) evaluates readings against acceptance criteria.
- [`verdict`](#mastif.kernel.verdict) combines outcomes;
  [`results`](#mastif.kernel.results) records measurements, checks, and tables.
- [`ids`](#mastif.kernel.ids) identifies runs and plan positions;
  [`errors`](#mastif.kernel.errors) defines the shared error hierarchy.

Expand modules and classes in the right-hand TOC to browse public and private members.
For explanations and design decisions, see [Kernel concepts](../../learn/architecture/kernel.md).

::: mastif.kernel.units

::: mastif.kernel.limits

::: mastif.kernel.verdict

::: mastif.kernel.results

::: mastif.kernel.ids

::: mastif.kernel.errors
