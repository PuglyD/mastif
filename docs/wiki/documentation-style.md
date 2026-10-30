# Writing documentation for mastif

Write for a capable engineer encountering this project for the first time. Assume
engineering knowledge, not familiarity with mastif's vocabulary or architecture.

## Explain from the problem outward

Start with a concrete situation: a replacement instrument, a missing reply, a value
whose unit matters. Explain the responsibility it creates before introducing the
class or configuration field that fulfils it.

A concept page should answer, in order:

1. What problem does this solve?
2. Where does it sit in the system, and who owns the responsibility?
3. What is the smallest useful example?
4. What happens on success and on failure?
5. Which API reference, guide, and decisions explain the next level of detail?

Use precise, friendly language. Avoid slogans and promises such as "always safe" when
the actual guarantee is an attempted action with reported failures. Define a term on
first use and link to the [glossary](glossary.md) where useful.

## Give each page a job

| Section | Reader's question |
|---|---|
| Overview | What is this, and why should I explore it? |
| Learn | How do I get my first result, step by step? |
| Guides | How do I accomplish a specific integration task? |
| Architecture | How do responsibilities and data fit together? |
| API reference | What exactly can I call, pass, receive, or catch? |
| Decisions | Why was this design chosen, and what are its trade-offs? |

Keep contributor setup separate from the user's first tutorial. Add a useful next
step rather than making the reader guess where to go.

## Link explanations, code, and decisions

Use actual Markdown links for ADR references, both in related-decision lists and
where another decision affects the explanation. State the relationship: "uses the
identity model from ADR-0010" is more useful than a bare number.

Link public symbols with mkdocstrings cross-references, for example
``[`Identity`][mastif.resources.identity.Identity]``. Render each symbol in one
canonical reference location to avoid ambiguous targets.

Organise API reference sections as `docs/reference/<section>/index.md`, with focused
module pages alongside the index. Keep this layout consistent across all sections.
Each module gets its own entry in the left navigation. Section indexes are short
orientation pages, not concatenated API dumps. Group resource transports and channels
in their own nested sections, with matching folders and index pages.

The reference includes public and private members, even without individual docstrings;
keep `filters: []` and `show_if_no_docstring: true` in the Python handler settings. Document
public constants and type aliases with a short string immediately after the declaration,
and annotate constants with their types. Declare exported constants individually:
tuple-unpacking assignments are not indexed as separate attributes by the current
Griffe parser. Check rendered symbol anchors as well as the build log; a clean build
does not prove that every public member was discovered.

Diagrams need a short explanation of what their arrows mean and ordinary links to
the concepts they introduce. This also gives readers a route onward without using
the diagram viewer. Direct diagram-node links need verification against the custom
Mermaid renderer before use.

## Keep examples honest and repeatable

- In Google-style docstrings, use `Examples:` (plural) with indented `>>>` sessions.
  The singular `Example:` is treated as a generic admonition, so its prompts become
  Markdown blockquotes instead of highlighted Python. Keep prose and sessions
  separated by blank lines; use fenced `python` blocks for illustrative code that
  is not a doctest.
- Use fictional organisations and simulated devices.
- Separate runnable code from illustrative fragments; label missing setup explicitly.
- Store downloadable tutorial scripts under `docs/examples/` and include them with
  snippets so the tutorial and file share one source.
- Use the Termynal plugin for recorded command/output playback. Include a copyable
  command and explain that playback does not execute code in the browser.
- Label proposed behaviour as planned. Do not present a future API as implemented.
- Distinguish an accepted design decision from implementation status.

The current terminal enhancement leaves the transcript visible until playback is
requested and retains static output for reduced-motion users. Keep `terminals.js`
before the plugin's `termynal.js` in the built page; it disables automatic playback.
Instant navigation is not enabled: custom diagram and terminal lifecycles must be
verified before introducing it.

The desktop table of contents collapses nested sections using `toc.js`. Heading
links remain separate from keyboard-accessible disclosure buttons. Deep links expand
their ancestor sections; without JavaScript, the full table remains visible. Keep
heading nesting meaningful so readers can expand modules, classes, and members.

## Review a documentation change

Run `uv run mkdocs build --strict`, execute changed runnable examples, and check
the generated pages in light and dark themes at desktop and narrow widths. Check
API links, code copying, terminal controls, and diagram zoom as well as the prose.
The strict build cannot validate interactive browser behaviour by itself.

Use [Resources](resources.md), [Identity and health](../reference/resources/identity.md),
and [ADR-0022](../adr/0022-resource-manager.md) as the first examples of this style.
