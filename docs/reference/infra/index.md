# Infrastructure

Infrastructure sets up application-wide services explicitly, so each application
can control its settings and diagnostics and pass them to the components that need them.

- [`config`](#mastif.infra.config) loads settings;
  [`logs`](#mastif.infra.logs) configures logging and diagnostic output.
- [`version`](#mastif.infra.version) reports software versions;
  [`bootstrap`](#mastif.infra.bootstrap) assembles application services.
- [`errors`](#mastif.infra.errors) describes configuration and infrastructure failures.

Expand modules and classes in the right-hand TOC to browse public and private members.
For explanations and design decisions, see [Infrastructure concepts](../../learn/architecture/infra.md).

::: mastif.infra.config

::: mastif.infra.logs

::: mastif.infra.version

::: mastif.infra.bootstrap

::: mastif.infra.errors
