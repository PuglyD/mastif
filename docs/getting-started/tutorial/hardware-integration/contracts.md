# Defining a capability contract

Of everything in your SDK, contracts will outlive the rest. Instruments get replaced and drivers get rewritten, but the capability that your tests depend on tends to stay the same for years. That makes this
the part of your SDK most worth taking time over, and in this chapter we'll talk about what makes a good one.

!!! success "Works today"
    Everything on this page runs against the current code, with no hardware.

## A contract is written from the caller's side

There's a mistake that's very natural to make here: opening the instrument's manual and turning its command list into a `Protocol`. You end up with a contract that's really a description of one vendor's product,
with `set_avg_count` and `set_rbw_filter_shape`, and the next instrument you buy doesn't match it.

Start from the other end. **What does a test need?** A contract is defined by the people calling it. Suppose a test only needs to read a current. Then this is a complete contract:

```python
from typing import Protocol

from mastif.kernel.units import Amps


class CurrentReader(Protocol):
    """Something that returns a fresh current observation."""

    def measure_current(self) -> Amps:
        """Measure the current now, and raise if a valid reading can't be obtained."""
        ...
```

A supply can provide that, and so can a standalone meter, or a current probe on a scope. A test written against `CurrentReader` works with all of them. If it had asked for a full `PowerSupply`, it'd be demanding output control it never
uses, and you couldn't run it on a bench with only a meter.

The rule of thumb is that **a task should use everything in the contract it asks for.** If it doesn't, the contract's too big.

You can also compose them, because they're ordinary protocols:

```python
from typing import Protocol

from mastif.kernel.units import Volts
from mastif.resources.std import PowerSupply


class ProtectedSupply(PowerSupply, Protocol):
    """A supply with over-voltage protection."""

    def set_ovp(self, voltage: Volts) -> None:
        """Set the voltage at which the output trips."""
        ...
```

## The signature is the small part

A `Protocol` tells you the names and the types. But a type can't express most of what really matters about a measurement, so a good contract's docstring has work to do. Here are the questions it should answer.

**Is the value fresh?** Does `measure_current` make a measurement now, or does it return whatever's on the front panel? Should a test set a voltage and read immediately, that's the difference between a real result and a stale one. We'd go so far as
to say that a method whose name starts with `measure` must perform a measurement. If it's cached, call it something else.

**What are the units and range?** A `Volts` annotation documents the dimension, but what about limits? If it can't accept what it's given, what does it do: clamp, or raise?

**Does it block, and for how long?** A sweep that takes thirty seconds needs a different timeout from a register read.

**What are the side effects?** This is the question that people forget, and it turns out to matter. Does reading this change anything? On many instruments, reading the error queue clears it. Some measurements restart an average. As we explain in [the system design chapters](../../../learn/system-design/events-state.md), this determines whether a reading can safely be monitored in the background.

**How does it fail?** Which exceptions, and what do they mean?

Here's what that looks like in practice:

```python
from typing import Protocol

from mastif.kernel.units import Hertz, Quantity


class SpectrumMarker(Protocol):
    """A spectrum analyser's peak marker."""

    def measure_peak(self, centre: Hertz, span: Hertz) -> Quantity:
        """Sweep around ``centre`` and return the peak level, in dBm.

        This triggers a new sweep and blocks until it's complete, typically for
        100 ms to 2 s depending on the span. The value is always fresh.

        Changes the instrument's centre and span, which stay changed afterwards.

        Raises:
            TransportTimeout: If the sweep doesn't complete in time.
            ProtocolError: If the instrument reports an overload.
        """
        ...
```

A newcomer can write a correct driver from that docstring, or a correct test.

## Telling the framework how to be safe

There's one thing that a contract can tell the framework directly. `@contract` attaches the safe-state action:

```python
from typing import Protocol

from mastif.kernel.units import Hertz
from mastif.resources.contracts import contract


@contract(safe_state=lambda source: source.output(False))
class Oscillator(Protocol):
    """A signal source. Safe state: output off."""

    def set_frequency(self, frequency: Hertz) -> None: ...
    def output(self, enabled: bool) -> None: ...
```

From now on, **every driver providing `Oscillator` is made safe automatically**, without its author writing anything, and that includes drivers written years from now. You can give it a function, as above, or the name of a method
with no arguments, like `safe_state="open_all"`. Should a specific instrument need more, a driver's own `safe_state()` method takes priority.

The decorator is entirely optional. A plain `Protocol` is a perfectly valid contract, and it's what you'd want for something with no safe state, like a meter that doesn't output anything.

## Checking conformance

You've seen that `@driver` checks a class against its contract when it's imported. Here's the same check, used directly:

```python
from typing import Protocol

from mastif.resources.contracts import contract_problems, satisfies


class Reader(Protocol):
    def read(self, channel: int) -> float: ...


class Good:
    def read(self, channel: int) -> float:
        return 0.0


class Bad:
    def read(self) -> float:
        return 0.0


print(satisfies(Good, Reader))         # True
print(contract_problems(Bad, Reader))
```

It compares method names and how they can be called. So a method with the wrong parameters is caught, even though it has the right name. Python's own `isinstance` check for protocols only compares the names, which isn't enough here.

Be clear about what this check can't see, though. It knows the *shape* of a contract. It doesn't check whether your implementation is correct, or whether its unit is right, or if the reading is fresh. These things need [behaviour tests](fake-io.md).

## Keep it serialisable

Here's a constraint you should follow from day one, even if you never plan to use the station runtime. **Arguments and return values should be things that can cross a process boundary**: `Quantity`, Pydantic models, enums, numbers, strings,
booleans, `bytes`, and lists or dicts of those.

Why? Because when a station is [shared between processes](../../../learn/system-design/execution-modes.md), a test holds a proxy object, and each call to it is a message sent to another process. A contract that passes a live socket or a vendor's C pointer can't make that
journey. If you keep to data, then your tests and drivers will work unchanged in both modes, without any extra effort. If you don't, you'll discover that the day you want to add a control GUI.

Callbacks are the one common exception. `MessageChannel.subscribe` takes one, and proxies have to adapt these specially. It's fine to have them where they're really needed, but it's worth thinking twice.

## Share them carefully

Since contracts are depended upon by everyone, they should live in their own module of your SDK, and they should change rarely. Adding a method is a breaking change for each driver that provides that contract, and changing a method's meaning is worse,
because nothing will warn you. When you need to change a capability significantly, consider defining a new contract, and let the old one retire gracefully.

## Recap

- Write a contract from the **caller's point of view**, and keep it small enough that a task uses all of it.
- The docstring carries the real contract: **freshness, units, blocking, side effects and failures**.
- `@contract(safe_state=...)` makes every future driver safe by default.
- Keep its values **serialisable**, so that it can cross a process boundary later.

So, a driver provides a contract and takes a connection. Let's see how that connection gets to it.

**Next:** [Driver configuration and injected dependencies](configuration.md)
