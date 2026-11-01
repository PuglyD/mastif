# Python types and protocols

mastif makes heavier use of type annotations than a lot of Python code does, and it uses them in more than one way. If you've mostly written untyped Python, this might look like a lot of ceremony. This chapter explains what's really going on, and why it's worth it for this kind of software.

## Three kinds of checking

Annotations are often talked about as if there's one thing that "checks types". In mastif, there are three separate mechanisms, and it's worth keeping them apart, since they run at different times, and catch different things.

| Mechanism | When it runs | What it does | Example |
|---|---|---|---|
| **A static type checker** | In your editor and CI | Reads code without running it | Spots `supply.set_voltage("5")` |
| **Pydantic** | When a model is created | Validates real data | Rejects `port: banana` from a profile |
| **mastif's contract check** | When a driver is imported | Compares a class with a contract | Spots a missing `output` method |

Here's the thing that surprises people coming from other languages. **By themselves, Python annotations don't do anything at run time:**

```python
def double(value: int) -> int:
    return value * 2


print(double("ab"))  # abab: no error
```

So where the data comes from outside your program, as in a YAML file or an operator's input, you need real validation at that boundary. That's what Pydantic's for:

```python
from pydantic import BaseModel, ValidationError


class Config(BaseModel):
    port: int


try:
    Config(port="banana")
except ValidationError as error:
    print(error.errors()[0]["msg"])
```

## Structural typing

Now let's look at the idea that's central to mastif. In many languages, a class implements an interface by saying so, through inheritance. Python's `Protocol` works differently: a class satisfies a protocol if it has the right methods. Nothing else is needed.

```python
from typing import Protocol


class Greeter(Protocol):
    def greet(self) -> str: ...


class English:                 # Doesn't mention Greeter at all
    def greet(self) -> str:
        return "hello"


def welcome(someone: Greeter) -> str:
    return someone.greet()


print(welcome(English()))  # hello
```

`English` never mentions `Greeter`. It simply has a `greet` method. This is called **structural typing**, because what matters is the structure and not the family tree. You might also know it as duck typing, with a checker to back it up.

Why does this matter so much for us? Because it's what lets drivers avoid any dependency on tests, and it means that a contract can be defined after a driver was written. Your SDK can define a small `CurrentReader` contract, and it'll be satisfied by an existing driver from some other package, without anybody changing that driver.

The other benefit is that test doubles are trivially easy. Any object with the right methods will do, with no base class to inherit from, and no mocking library needed.

## What mastif adds

Python can check a protocol at run time, through `isinstance` with `@runtime_checkable`, but this only checks that the method names exist. It would accept a method with entirely the wrong parameters. So mastif has its own stricter check, which looks at how the methods can be called:

```python
from typing import Protocol

from mastif.resources.contracts import contract_problems


class Reader(Protocol):
    def read(self, channel: int) -> float: ...


class WrongParameters:
    def read(self) -> float:
        return 0.0


print(contract_problems(WrongParameters, Reader))
```

That's what `@driver` runs when your module is imported.

## Annotations that do work

There's one more use you'll see in mastif, and it's unusual. Some annotations are actually read at run time, to decide what to do. A driver's constructor is the main case:

```python title="excerpt"
def __init__(self, cfg: Config, io: Scpi, log: logging.Logger) -> None:
    ...
```

The station reads these annotations, and it uses them to decide what to pass in. Remember this if you're tempted to remove an annotation from a constructor because it seems redundant: it isn't redundant, and the decorator will tell you so.

## What about units?

You'll see `Volts` and `Amps` in signatures. These are aliases for documentation, and they tell a reader which dimension is intended. They aren't different classes, so a type checker won't stop you from passing amps where volts are wanted:

```python
from mastif.kernel.units import Quantity, Volts

print(Volts.__value__ is Quantity)  # True: an alias
```

The real checking happens at run time, in the `Quantity` itself, when values get compared or converted. So the annotation documents intent, and the value enforces it. There's more in [Units and dimensional correctness](units.md).

## What types can't tell you

A matching signature doesn't prove that a reading is fresh, that its unit is the right one, or that an instrument's range suits your test. Types describe the shape of things. Their meaning needs documentation, behaviour tests and, in the end, time on a bench.

## Recap

- **Static checkers, Pydantic and contract checks** are separate, and they run at different times.
- **Annotations alone do nothing at run time**, so validate data that comes from outside.
- **Protocols are structural.** A class satisfies one by having the right methods, which is what keeps drivers and tests independent.
- **Constructor annotations** on a driver are read at run time, to decide what to inject.

**Next:** [Dependency injection and composition](injection.md)
