# Visualization tools

Development scripts that produce figures and pages about the library. They are
not part of the `embed_data_model` package and are not installed with it.

## Graph assembly page

`graph_assembly.py` shows the library building a sparse clinical graph one
table at a time. It loads synthetic MagView rows, partitions to the exams
flagged for workup, then loads the whole image table and the registry into
that subset with `parents="existing"`. The page steps through the four calls.
Each step shows the patient-lane graph, the call made, what changed, which
tables are loaded and the entity counts. The page also has an object-identity
ledger and an at-scale run, 5,000 synthetic patients by default.

```bash
uv run --frozen python -m tools.visualization.graph_assembly
```

This writes `build/visualization/graph-assembly.html` (gitignored). Options:

| Option | Effect |
|---|---|
| `--out PATH` | Write the page somewhere else |
| `--scale-patients N` | Size of the at-scale run; `0` omits that section |
| `--trace-json PATH` | Also write the recorded trace as JSON |
| `--bea-dir DIR` | Read the Bea assets from `DIR` instead of the vendored copy |
| `--vendor` | With `--bea-dir`, also replace the vendored copy in `bea/` |

Everything on the page comes from running the library. Node states, edges,
unresolved keys, skip counts and Python object ids are read from the graph
after each call, and the build fails if a later load replaces a tracked object
or adds an exam to the subset. The at-scale timing is one measurement on the
machine that builds the page. No EMBED data is read.

`graph_assembly.html` is the page template. It is styled with Bea: Inter and
JetBrains Mono, ink outlines, and color only for status. In the graph, orange
with a half-filled circle marks context ancestors, and a dashed outline with
"?" marks a key whose target is not loaded. A strong outline marks what
arrived in the current step, and a faded node with a "not in subset" note is
one left in the source graph. The page follows the viewer's light or dark
theme. The build inlines `bea/tokens.css`, `bea/bea.css` and `bea/bea.js` and
the trace, so the output is a single self-contained file that loads only its
fonts from Google Fonts.
