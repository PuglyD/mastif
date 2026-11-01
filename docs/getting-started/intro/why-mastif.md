# Why mastif?

There are other ways to write test software, and some of them are very good. This page explains the thinking that makes mastif what it is: the principles we hold it to, where they came from, and what you should get out of them.

## Five principles

The rest of this course keeps coming back to these. They're worth reading now, even
if some only make full sense later.

### 1. Separate what a test needs from what provides it

A test needs *a power supply*. It doesn't need an ACME PSU-X at `10.0.0.5`. We keep
those facts apart, in three separate places:

| The fact | Who owns it | Where it lives |
|---|---|---|
| "Idle current must be at most 250 mA" | The test author | A test package |
| "`MEAS:CURR?` returns amperes" | The driver author | An SDK |
| "This bench's supply is at `10.0.0.5`" | Whoever runs the bench | A station profile |

Replacing the instrument changes the second and third rows. The test doesn't change.

This does have a limit, and we'd rather you hear it from us. Two supplies with the same
interface are not necessarily interchangeable for your measurement: range, accuracy
and settling time are physics, and an interface can't check physics.

### 2. Evidence is a first-class thing

A test's real output is not a green light. It's a record someone can check later:
what was measured, under what conditions, against which limit, with which equipment.
So values carry their units, and a verdict is *computed* from the evidence rather than
stated beside it. You cannot record 300 mA against a 250 mA limit and mark it as
passed; there is no way to pass the verdict in.

### 3. "The unit failed" and "the test broke" are different facts

A board drawing 300 mA is bad news about the board. An instrument that doesn't answer
tells you nothing about the board at all. mastif keeps these apart all the way up:
the first is a **FAIL**, the second is an **ERROR**. Confusing them means scrapping
good hardware, or shipping bad hardware after a silent zero reading.

### 4. Hardware cleanup is not an afterthought

An exception in ordinary software loses you a request. An exception in test software
can leave a supply energised. Getting a station into a known state, in the right order,
even when parts of it have failed, is treated as a core responsibility of the
framework, not something each test remembers to do.

### 5. Keep the simple case simple

A senior ATE engineer with more than twenty years of experience looked at an early
design for mastif, with its background process constantly polling every instrument, and
gave some advice worth repeating: *his tests open the connection, make the measurement
and close it. Sequential, simple, and it runs anywhere.*

He was right, for the cases he described, and it changed the design. By default a test
process simply owns its station. That runs on a laptop, in CI and on a bench, with no
service to deploy and a single stack trace when something breaks.

We also believe the longer-term answer for a real production floor is a shared process
that owns the bench, because the moment a control GUI needs to sit beside a running test,
"open, measure, close" runs out of road. So mastif supports both behind the same
contracts, and a task doesn't know which one it's running under. You'll find the full
argument in [Direct execution and a persistent station
runtime](../../learn/system-design/execution-modes.md), and the
[field notes](../../learn/architecture/field-notes.md) record the advice itself.

## Where the ideas come from

We didn't invent this domain, and we've learned from people who came before us.

[OpenHTF](https://www.openhtf.com/), Google's open hardware test framework, showed how
much clarity you gain by treating measurements and test records as the main output.
[OpenTAP](https://opentap.io/) models test plans as structured trees over instrument and
DUT resources. [HardPy](https://everypinio.github.io/hardpy/) showed how pleasant it is
when tests live in an ordinary Python package that you build and ship as a wheel.

One influence comes from outside test engineering altogether:
[OpenTofu](https://opentofu.org/), the infrastructure-as-code tool. Before it changes
anything, it computes a **plan** you can read, then it applies that plan, and it keeps a
**state** file so it knows where things stand. That turns out to fit test execution very
well. A four-hour run should show you exactly what it's about to do before it powers
anything, and should know exactly where it had got to when it restarts.

mastif is written from scratch, but its shape owes a lot to all of them.

## What this looks like when it's working

Here's the aim, in practical terms. A new product needs a test. An engineer starts from a template, writes tasks against existing contracts, and tests them on a laptop. A new instrument means one new driver, usable by everyone from then on. A fix to a driver reaches every station through a version bump. An operator on any bench sees the same kind of screen. And when somebody asks about a unit from last year, the answer's a query, not an archaeological dig.

## Recap

Five principles run through everything: separate what a test needs from what provides it, treat evidence as a first-class thing, keep unit failures and broken tests apart, take hardware cleanup seriously, and keep the simple case simple.

The next question is whether all of this is meant for you.

**Next:** [Who is this for](who.md)
