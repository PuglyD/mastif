# Concurrency versus parallelism

These two words get used as if they mean the same thing, and for a lot of software you can get away with that. For software controlling hardware, you can't, as the difference shapes how you design things. This chapter explains the distinction in general, then applies it to a test station. It's the background to our [runtime concurrency chapter](../system-design/concurrency.md).

## Two different ideas

**Concurrency** is about *structure*: dealing with several things over overlapping periods of time.

**Parallelism** is about *execution*: actually doing several things at the same instant.

An analogy helps. One person cooking a meal is concurrent. They've got a pot simmering, something in the oven and a salad on the go, and all of those are in progress, though they only ever do one thing at any moment. Most of the time, each of these tasks is simply waiting. Now if two people are cooking, that's parallel: two things really are happening at once.

You can have one without the other. One cook juggling three dishes is concurrent, but not parallel.

## What's waiting, and what's working

The useful question for any operation is: is it **waiting** or **working**?

Most of what a test station does is waiting. A query takes 50 ms, and for nearly all of that, your computer is doing nothing except waiting for an instrument to reply. A two-second sweep is two seconds of waiting. Almost none of it is your CPU working.

So a station doesn't need more CPU power. It needs to not be stuck while waiting. Here's what Python offers for this:

| Tool | What it's good for | Notes |
|---|---|---|
| **`asyncio`** | Many operations that wait, on one thread | Everything must cooperate: one blocking call stops the lot |
| **Threads** | Blocking calls, side by side | They share memory, so you need care about who touches what |
| **Processes** | Isolation, and CPU-heavy work | Separate memory, with messages between them. One can crash alone |

## `async` doesn't make things non-blocking

This is the single most common misconception, so let's look at it directly.

```python title="this blocks everything"
async def read_instrument():
    return vendor_library.read()      # A blocking C call
```

Marking a function `async` doesn't change what the code inside it does. If `vendor_library.read()` blocks for two seconds, then for those two seconds the whole event loop is stuck: no other instrument can be serviced, no Stop button registers, and nothing gets published. `async` is a way of voluntarily giving up control, at points where you `await`, and a blocking C call never gives up control.

Likewise, putting a call in a thread doesn't make that call safe. It only moves the problem. If a vendor's library isn't thread-safe, then calling it from two threads may corrupt it.

So choosing a mechanism comes after you've understood the operation itself. Who owns this resource? Does this call block? Does it care which thread it's called from?

## A station has physical rules

Software concurrency has a physical counterpart on a bench, and that's the part that makes this domain distinctive.

**Two independent instruments can work in parallel.** A supply and an analyser don't care about each other. So there's no reason for one to wait for the other.

**Two commands to one instrument can't.** A connection to an instrument is a conversation. If two queries overlap, their replies may get crossed, and that gives you silently wrong data.

**Two names may be one thing.** Two children of one controller look like separate objects in Python, but they share a connection and perhaps a single command queue. The physics is what counts, not the object graph.

## Three different guarantees

Let's look at this from the point of view of what you might want to protect. These are different guarantees, and people often assume that one of them gives you another.

| Guarantee | Protects | Provided in mastif by |
|---|---|---|
| Calls to one resource don't overlap | One command | A per-resource worker |
| A sequence isn't interfered with | Configure, settle, measure | A control lease |
| Two things happen at the same moment | Timing | Hardware triggers |

The last one's worth a mention. Software can't give you precise simultaneity. Python's threads get scheduled by the operating system, so two "simultaneous" calls might be milliseconds apart, with no guarantees. If you truly need two instruments to measure at the same instant, wire up a shared trigger, and arm them both in advance. It's a hardware problem with a hardware solution.

## Stopping is cooperative

Finally, concurrency has a consequence for stopping things. Stopping *future* work is easy: just don't start it. Interrupting something that's *running* is hard:

- An `asyncio` task can be cancelled, but only at an `await`.
- A thread can't be safely killed at all, as it might be holding a lock.
- A process can be killed, and that's why it's the strongest boundary we've got. But the instrument it was talking to is unaffected.

Each one gives you a different boundary, and none of them proves that a physical output has reached a safe state. Hence the care we take over [cancellation](../system-design/cancellation.md).

## How mastif uses all this

With that background, the design choices should look less arbitrary:

- **Test authors write blocking code**, on a single thread, top to bottom, because that's the clearest way to describe a sequential procedure. They don't need to know any of what's in this chapter.
- **An asyncio loop coordinates**, because coordinating is nearly all waiting.
- **One thread per resource does the hardware**, because instruments are serial, independent and often blocking.
- **Child processes contain what's unreliable**, as that's the only boundary that can be enforced.

## Recap

- **Concurrency** is dealing with several things at once, and **parallelism** is doing several things at once.
- A station's work is **mostly waiting**, so what you need is not to be stuck.
- **`async` doesn't make a blocking call non-blocking**, and threads don't make a call safe.
- **Physical rules** decide what can overlap, not Python's object graph.
- **Stopping is cooperative**, and only a process can be forcibly ended.

With those ideas in hand, let's look at the design of the whole system. If something here was confusing or wrong, that's a bug in the documentation, and we'd like to know about it. You can also head back to the [start](../../getting-started/intro/route.md) to choose another path, or go and write a test.

**Next:** [System design, architecture, and platforms](../system-design/concepts.md)
