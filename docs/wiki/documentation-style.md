# Writing documentation for mastif

Write for a capable engineer encountering this project for the first time. Assume
engineering knowledge, not familiarity with mastif's vocabulary or architecture.

## Voice

Technical, friendly, and first and foremost full of context. Write as a person who built
this and wants the reader to understand it, using "we" and "you". A reader should finish
a page knowing what was hard about the problem, not only which class solves it.

Every page in the Learn course follows the same arc:

1. **An introduction.** Open with where the reader is and a concrete situation, in plain
   prose. Never open with a status line or a definition.
2. **The principle.** Work out what the software must do from the problem, and state the
   rule that follows. Name the abstraction only after that.
3. **The technical substance.** Real code and real output, followed by what actually happens:
   ordering, failure behaviour, guarantees, and why the alternatives were rejected.
4. **The limits.** Say what the mechanism doesn't establish.
5. **A recap**, and a sentence that leads into the next chapter.

Short pages that restate facts as tables are the failure mode to watch for. A table can
summarise an explanation, but it can't replace one. Recipes may be shorter, and they open
with what the reader has and what they want.

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
first use and link to the [glossary](../learn/architecture/glossary.md) where useful.

## Give each page a job

| Section | Reader's question |
|---|---|
| Overview | What is this, and why should I explore it? |
| Getting Started | What is this, and how do I go from nothing to tests running on a station? |
| Learn | How does the system work, how was it built, and why? |
| Guides | How do I accomplish a specific integration task? |
| API reference | What exactly can I call, pass, receive, or catch? |
| Decisions | Why was this design chosen, and what are its trade-offs? |

Use only diagrams we made ourselves or have the right to publish, and redraw anything else in Mermaid. Keep images in `docs/assets/`.

Keep contributor setup separate from the user's first tutorial. Add a useful next
step rather than making the reader guess where to go.

Doing and understanding are separate. `docs/getting-started/` holds the intro and the tutorial, which takes a reader from nothing to tests deployed on a station. `docs/learn/` holds fundamental concepts, system design, the architecture as built, project status, station operation and recipes. Preserve the explicit chapter navigation and next-step links. The remaining direct-use guides stay in `docs/wiki/`.

For design-preview pages, open with one short notice, label code and terminals at the point
of use, and then write in the present tense as if the engine exists, because that's how to
find out whether a design reads well. Don't interrupt the explanation with disclaimers. Collect
genuinely undecided points in a collapsed "Still open in this design" block. A mock CLI transcript must never
look like a verified runnable command. Do not turn a preview into an accepted ADR
without an explicit design decision.

## Link explanations, code, and decisions

Use actual Markdown links for ADR references, both in related-decision lists and
where another decision affects the explanation. State the relationship: "uses the
identity model from ADR-0010" is more useful than a bare number.

Link public symbols with mkdocstrings cross-references, for example
``[`Identity`][mastif.resources.identity.Identity]``. Render each symbol in one
canonical reference location to avoid ambiguous targets.

## API reference layout

Organise API references as one file per layer at `docs/reference/<layer>/index.md`.
The left navigation lists each layer as a peer, including Kernel. Keep Material's
`navigation.indexes` feature disabled: it promotes the first `index.md` child to the
section link and removes that child's separate navigation entry.

Start every reference page with a quick orientation immediately below its title:

- Explain the layer's purpose and how it connects to the rest of mastif in one or two sentences.
- Add a short list of module responsibilities, linking module names to their canonical
  Python anchors. Combine related modules in one bullet to keep the summary scannable.
- Mention that the right-hand TOC expands modules and classes and includes public and
  private members. Link to the relevant concept pages for deeper explanations and ADRs.

Keep this summary before the first API directive, without a separate summary heading.
It provides orientation without adding another branch to the reference TOC.

The right-hand table of contents follows Python ownership: module, class, then its
methods and attributes. Render module roots with `show_root_heading: true` and
`heading_level: 2` beneath the page title. Use the generated Python names directly,
without descriptive module headings or extra editorial groups. Keep explanations
and design-decision links in the concept pages linked from each layer introduction.
Use canonical Python symbol anchors for links into the reference.

The reference includes public and private members, even without individual docstrings;
keep `filters: []` and `show_if_no_docstring: true` in the Python handler settings. Document
public constants and type aliases with a short string immediately after the declaration,
and annotate constants with their types. Declare exported constants individually:
tuple-unpacking assignments are not indexed as separate attributes by the current
Griffe parser. Check rendered symbol anchors as well as the build log; a clean build
does not prove that every public member was discovered.

Use this page shape:

```markdown
# Layer name

A short explanation of the layer's purpose and place in the system.

- [`module`](#package.layer.module) provides a specific capability.

Expand modules and classes in the right-hand TOC to browse public and private members.
For explanations and design decisions, see [Layer concepts](../../wiki/layer.md).

::: package.layer.module
```

When adding a module, add its directive to the existing layer page and update the
opening summary as needed. Render each symbol once; package-level references must
not duplicate classes already documented in their defining modules.

## Diagrams

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
their ancestor sections; without JavaScript, the full table remains visible. Verify
the generated TOC's parent-child relationships against Python symbol ownership.

## Review a documentation change

Run `uv run mkdocs build --strict`, execute changed runnable examples, and check
the generated pages in light and dark themes at desktop and narrow widths. Check
API links, code copying, terminal controls, and diagram zoom as well as the prose.
The strict build cannot validate interactive browser behaviour by itself.

Use [Resources](../learn/architecture/resources.md), [Identity and health](../reference/resources/index.md#mastif.resources.identity),
and [ADR-0022](../adr/0022-resource-manager.md) as the first examples of this style.
