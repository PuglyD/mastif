# mastif architecture map

An editable tlDiagram map of the implemented codebase, with a separate drill-down
for planned work. Created with tlDiagram 2.6.0 from the source tree and ADRs.

## Explore

Start at the workspace overview, then use an element's zoom-in control to open its
internal view. Select an element for its description and source link; select a
connector for the evidence behind the relationship.

| View ref | Question it answers |
|---|---|
| `root` | How do applications, the four implemented layers, SDKs, testing, and hardware connect? |
| `station` | How does a profile become a bench, and how are opening, verification, and cleanup coordinated? |
| `resources` | How are contracts, driver definitions, discovery, and dependency injection connected? |
| `transports` | How does requested I/O become a concrete transport or protocol helper? |
| `kernel` | How do quantities, limits, verdicts, results, identifiers, and errors relate? |
| `infra` | How are settings, logging, and version information composed explicitly? |
| `testing` | How do fake I/O and conformance checks exercise the real integration boundaries? |
| `planned` | What engine, API, CLI, and station-runtime boundaries are design-only? |

**Reading the arrows:** follow the verb on each connector. They represent calls,
construction, validation, data use, discovery, or inheritance—not a uniform import
graph. The `planned` relationship and element tags mark design-only edges and nodes.
The dependency rule remains `station → resources → infra → kernel`; higher layers
may also depend directly on lower ones.

The overview is a responsibility map, not a claim that each box is a separate
process. Current use is direct Python composition. `infra.bootstrap.Runtime` is a
small returned settings/version object, not the proposed persistent station service.

## Terminology and layering

Elements use Python vocabulary: `package`, `subpackage`, `module`, `class`, `function`,
`method`, `property`, `attribute`, `global`, and `type-alias`. Non-code boundaries keep
`client`, `service`, `external`, and `planned`.

Every implemented layer expands the same way. Drill down:

    package -> subpackage/module -> class/function/global/type alias -> method/property/attribute

Containment is shown by the drill-down itself, so there are no separate "owns" arrows.
Connectors state what the source demonstrates: `imports`, `re-exports`, `inherits`,
`overrides`, `decorated by`, `typed as`, `parameter x`, `returns`, `calls`, `instantiates`,
`raises`, `catches`, `checks isinstance`, `reads`, `writes`, and `references`. Class
connectors in a module view summarise their members' connectors. Descriptions cite source
lines or imported names. Module `__all__` lists appear in the description, not as arrows.

Each element is placed only where it is defined. tlDiagram draws connectors that leave a
view itself, as faded neighbour nodes around its edge. Clicking one opens the original
element, and distant targets are grouped under their package or module with a count. It
caps these at 50 connectors per view, in at most 32 groups. A connector into another class
points at that class and names the member, such as `reads name, is_open`.

## Regenerate

`.tld/generate_architecture.py` reads the source with `ast` without importing mastif, and
merges `.tld/curated.yaml`, which holds non-code elements, overview positions, and
hand-written connector wording. Hand-written wording replaces the generated label on the
same pair, and the generated detail stays in the description.

```powershell
python .tld/generate_architecture.py          # writes architecture.import.yaml
python .tld/generate_architecture.py --apply  # also rebuilds the live diagram
```

`--apply` stops the server, keeps one copy of the database as `tld.db.bak`, and rebuilds
from an empty database in a few seconds; restart `tld serve` afterwards. It assumes the
database holds only this map. It discards edits made in the UI, and view IDs can change.

Edges are a lower bound: dynamic dispatch and values with no inferable type are not
resolved.

Nodes cannot be resized in tlDiagram 2.6.0: the UI has no resize control and the schema
has no size field. Node size follows the content, and long names are trimmed in the middle,
so names lead with the member. The Python icon comes from `logo_url: /icons/python.svg`.

## Open locally

From the repository root, with `tld` on PATH:

```powershell
tld context --workspace . --target local --data-dir "$env:USERPROFILE\.local\share\tldiagram" --format json
tld serve --open --host 127.0.0.1 --port 7337 --workspace . --target local --data-dir "$env:USERPROFILE\.local\share\tldiagram"
```

The current preview is at <http://127.0.0.1:7337>. On this Windows installation the
executable is also available as `& "$env:LOCALAPPDATA\tld\bin\tld.exe"` if the shell
has not picked up the updated PATH.

## Maintain

- `elements.yaml` and `connectors.yaml` are the workspace's YAML cache, maintained
  by CLI operations. Keep stable refs when changing the map.
- `architecture.import.yaml` is generated, so edit the generator or `curated.yaml`.
- `.tld.lock` binds cached IDs to the current local database; it is machine-local
  and ignored by Git.
- Preview changes with `--dry-run`. Pin the same workspace, local target, and data
  directory for writes, reads, validation, and rendering.
- Change code-derived elements through the generator. Use `tld add`, `connect`, `update`,
  and `view` only for one-off experiments, because `--apply` removes what it did not
  generate. For UI edits, review `tld pull --dry-run` before refreshing the YAML cache.
- Keep Python source anchors (`path.py#Class.method`) and connector evidence current.
  External and planned concepts link to the relevant guide or ADR instead of a
  nonexistent implementation.

Example validation and export commands:

```powershell
tld validate --source live --workspace . --target local --data-dir "$env:USERPROFILE\.local\share\tldiagram" --format json
tld render station --source live --workspace . --target local --data-dir "$env:USERPROFILE\.local\share\tldiagram" --format json
```

## Verification and deliberate exceptions

The map has **910 elements, 1579 relationships, and 130 views**; 766 of the generated connectors cross views. Live validation passes
structural checks. Source paths and Python symbol anchors come from the AST.

These architectural warnings are expected:

- `ARC001` High Density and `ARC005` Low Insight Ratio: views show every member of a real
  Python object, and plain data classes have fields with no internal behaviour.
- `ARC002` Isolated Element: leaf members nothing else in their view touches, such as
  dataclass fields, and methods only called from outside. They are listed for completeness.
- `ARC102`: the external hardware boundary has no single software technology;
  its device protocols and vendor implementations vary by bench.

Hand-written connectors with no matching static link at that exact pair are kept, with no
source evidence in their description. Three were dropped because one end now contains the
other: `build_resource` to `driver`, and `ResourceManager` to `_emit` and `_verify_identity`.

Mermaid exports include only directly placed endpoints, so they omit cross-view connectors.

Planned work
is described from ADRs and the roadmap, not presented as executable code.
