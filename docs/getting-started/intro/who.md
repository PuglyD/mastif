# Who is this for

mastif is for engineers and organisations whose test software has outgrown a folder of scripts, or who can see that coming.

We assume you're a capable engineer who knows Python. We don't assume you know automated test equipment: when a term of art such as *DUT* or *SCPI* appears, we explain it the first time and link to the [glossary](../../learn/architecture/glossary.md).

## Which of these are you?

Different people touch a test system in different ways, and mastif keeps those jobs apart on purpose. Here's where each of them should begin.

| You are | You want to | Start with |
|---|---|---|
| **A test author** | Express what to check, and judge a product | [Your first test run](../tutorial/writing-tests/first-run.md) |
| **A driver or SDK author** | Make instruments available to every test | [Your first driver](../tutorial/hardware-integration/first-driver.md) |
| **Responsible for benches** | Keep stations configured and running | [Station profiles](../tutorial/deploying/profiles.md), then [Operate a station](../../learn/operations/bootstrap.md) |
| **Evaluating the architecture** | Decide whether this design suits you | [System design](../../learn/fundamentals/index.md) |
| **Building a UI** | Put an operator interface on top | [Connecting an operator interface](../../learn/operations/operator-ui.md) |

## When it's a good fit

- You have, or expect to have, more than one bench, product or team.
- Instruments get replaced, and you'd like that not to mean rewriting tests.
- Someone may ask you to prove what was tested, with what, long afterwards.
- A long run failing near the end is expensive.

## When it isn't

If you have one board and one bench, and you just need an answer today, a short script is a perfectly good choice. mastif starts to pay for itself about when the second bench arrives.

It's also in early development. The foundation works, but the test engine isn't built yet, so it isn't ready to run a production line today. [What exists today](../../learn/status.md) has the details.

**Next:** [How to learn mastif](how-to-learn.md)
