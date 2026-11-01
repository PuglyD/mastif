# Diagnose an identity or health-check failure

**You have:** a station that refuses to open, with an `IdentityMismatch` or a `ResourceFault`.

**You want:** to find out what's actually wrong, without just making the error go away.

!!! success "Works today"
    Everything on this page runs against the current code.

First, let's remember what these errors mean. The station has done its job, and it's stopped because something didn't match. The tempting fix, deleting `expect:` or forcing `health()` to return good, removes the check and leaves the problem in place. So let's find the cause.

## An identity mismatch

```text title="Real output"
IdentityMismatch: bench_supply: serial is 'A124', expected 'A123'
```

The message tells you the resource, the field, and both values. There are several possibilities, so work through them in order.

**1. Is it the instrument you think it is?** Go and read the label on the instrument. Then check that the cable from the address you're using really goes to that instrument. Transposed cables and swapped instruments are the most common cause, and it's just what this check exists for.

**2. Is the profile out of date?** If this instrument has been deliberately replaced, say a spare came in while the usual one is out for calibration, then the bench is right and the file is wrong. Update `expect:` through your normal review process, so that there's a record of when it changed.

**3. Is the right profile loaded?** Maybe you're running `bench-01.yaml` on bench 2.

**4. Is simulation involved?** With `sim=True`, the entry that's used is the one in the `sim:` section, which has its own `expect:`. Look at what's selected:

```python title="excerpt"
for name, entry in profile.entries(sim=True).items():
    print(name, entry.driver, entry.expect)
```

**5. Is the driver parsing it correctly?** Sometimes a parser's to blame. A vendor might put the serial in a different position within `*IDN?`, or a firmware update could change the format. Ask the instrument directly, and compare:

```python title="excerpt: at a Python prompt"
print(station.resource("bench_supply").instance.io.query("*IDN?"))
```

Here's a variation you may see:

```text title="Real output"
IdentityMismatch: bench_supply: expect: is set but the driver can't identify()
```

This one means the profile asks for a check, and the driver has no `identify()` method. That's a problem with the driver. Silently skipping the check would be worse.

## A health failure

```text title="Real output, from a simulated fault"
ResourceFault: psu: unhealthy: simulated fault
```

`health()` ran and reported a problem, and the text after `unhealthy:` is whatever the driver put in `detail`.

**1. Believe it first.** The device says that something's wrong. A latched over-temperature or a failed self-test is probably real. Look at the instrument's front panel.

**2. Is it just warming up?** Some instruments report not ready for some time after power-on. If this is expected, the driver could wait for a bounded time in `open()`, or you might power things up earlier in the day.

**3. Is it a stale error?** Many drivers treat any entry in the SCPI error queue as unhealthy. An old error, left over from yesterday, can fail today's check. Clearing the queue in `open()` is reasonable, provided that you're happy to discard what's there. Read it into a log first.

**4. Be careful about retrying.** Reading an error queue empties it. So if you run the check a second time and it passes, you can't conclude that the problem has gone. All you've learned is that the queue's now empty. Hold on to the first report.

## See it for yourself

You can reproduce both failures safely, with no hardware. Take the [station example](../../examples/learn_station.py), and change `expect` to a different serial:

```yaml title="in the example's profile"
expect: {serial: SOMETHING-ELSE}
```

Opening now fails before the measurement starts:

```text title="Real output"
IdentityMismatch: bench_supply: serial is 'SIM-001', expected 'SOMETHING-ELSE'
```

## Why identity is checked when it is

Identity gets checked after the connection is made and the driver's `open()` has run, because many devices can't answer until then. That means that it prevents normal use of the wrong device. It can't undo anything that `open()` has already done. If an `open()` hook applies stimulus to the wrong device, the check comes too late, which is why [hooks must stay conservative](../../getting-started/tutorial/hardware-integration/identity.md#why-its-checked-after-open).

Passing doesn't prove everything, either. A matching serial tells you that you're talking to the right instrument. It says nothing about whether the wiring is right, or whether its calibration is current. If your calibration date matters, you could put it into `Identity.extra`, and have the task check it.

## See also

- [Identity, health, and safe state](../../getting-started/tutorial/hardware-integration/identity.md).
- [Troubleshooting](../operations/troubleshooting.md).
- [ADR-0010](../../adr/0010-identity-and-health.md) and [ADR-0022](../../adr/0022-resource-manager.md).
