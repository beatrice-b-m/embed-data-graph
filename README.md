# EMBED Data Model

EMBED Data Model is a small Python library for representing clinical and
mammography data as mutable objects. It can load any supported subset of EMBED
tables, retain the relationships that the rows actually establish, and leave
project-specific analysis to downstream code.

The package is version `0.2.1`. Its distribution name is `embed-data-model` and
its Python namespace is `embed_data_model`. The source repository is
[beatrice-b-m/embed-data-model](https://github.com/beatrice-b-m/embed-data-model).

## Install from the checkout

The current source release is tagged `v0.2.1`. From a clone, install the
development environment at the repository root:

```bash
git clone https://github.com/beatrice-b-m/embed-data-model.git
cd embed-data-model
git checkout v0.2.1
uv sync --frozen
uv run --frozen python -m examples.researcher_journeys
```

For a local consumer that needs an editable install, use:

```bash
python -m pip install -e /path/to/embed-data-model
```

To install the tagged source release into a downstream environment:

```bash
python -m pip install \
  "git+https://github.com/beatrice-b-m/embed-data-model.git@v0.2.1"
```

For a reproducible source install from another revision, pin the exact commit
you qualified:

```bash
python -m pip install \
  "git+https://github.com/beatrice-b-m/embed-data-model.git@<commit-sha>"
```

Replace `<commit-sha>` with the qualified revision and record it in the downstream
lockfile. See [CONTRIBUTING.md](CONTRIBUTING.md) for development and versioning
expectations and [LICENSE](LICENSE) for the MIT license.

## Quickstart

This complete synthetic example uses only the public root facade. It creates a
graph from one MagView-like row, edits the live exam, and makes an independent
partition for a downstream analysis. It does not require private EMBED data.

```python
from embed_data_model import DatasetGraph, Laterality, load_embed, validate


graph = DatasetGraph()
report = load_embed(
    magview=[
        {
            "empi_anon": "P-001",
            "acc_anon": "A-001",
            "numfind": 1,
            "side": "L",
            "desc": "screening",
            "asses": "S",
            "recc": "B",
            "location": "W",
            "depth": "P",
        }
    ],
    into=graph,
)

patient = graph.patient("P-001")
exam = graph.exam("A-001")
finding = graph.finding("A-001", "1")
assert patient is not None and exam is not None and finding is not None
assert finding.laterality is Laterality.LEFT
assert finding.interpretation.assessment.code == "S"
assert finding.interpretation.assessment.meaning == "Suspicious"
assert not finding.normalization_warnings
assert not report.issues

exam.update(description="reviewed")
assert graph.exam("A-001") is exam
assert validate(exam).valid

partitions = graph.partition(level="exam", key=lambda item: item.description)
reviewed_graph = partitions["reviewed"]
assert reviewed_graph.exam("A-001") is not exam
assert reviewed_graph.exam("A-001").description == "reviewed"
```

The [researcher journeys](examples/researcher_journeys.py) file contains a
small command-line runnable version of the same public surface. The longer
[user guide](docs/user-guide.md) covers source mappings, relationships,
images, ROIs, validation, and movement. The [documentation index](docs/README.md)
points to the contracts and downstream integration guide.

## What the library owns

The object graph is intentionally narrow:

```text
Patient -> Exam -> Finding -> Procedure -> Pathology
                  Exam -> Image -> ROI
                  Exam <-> linked Exam
                  Exam -> patient-scoped registry entry
```

`DatasetGraph` owns membership and indexes. `Patient`, `Exam`, `Finding`,
`Procedure`, `Pathology`, `CancerRegistryEntry`, `MammogramImage`, and
`RegionOfInterest` are mutable entities that can also be constructed without a
graph. `load_embed` accepts mappings, generators, or DataFrame-like tables and
returns a `LoadReport` containing the graph and issues from that invocation.

The loader groups rows by semantic identity before applying them. Patient,
exam, and finding IDs come from their mapped source fields; image identity is
separate from source SOP identity and source paths; ROI identity is scoped to
an image and an explicit collection key. DataFrame indexes and row order are
diagnostic details, never fallback clinical identity.

Refresh is the default load mode. For each addressed grain it replaces the
bound fields whose columns the rows supply, including an explicitly supplied
null. A column absent from the rows leaves its field unchanged, so tables and
extracts with different columns can be loaded one after another. It keeps object references, subclasses,
consumer-added attributes and metadata, unbound fields, and child grains that
were not supplied. `mode="merge"` fills gaps with supplied non-null scalar values. A value that
contradicts another supplied value, or a populated value already in the graph,
becomes unknown and is reported as an issue. A single invocation is one
snapshot, so callers assembling streamed data must group complete semantic
objects before calling refresh.

Validation is explicit and read-only. `validate(entity)` returns a
`ValidationResult`; errors make it invalid, while warnings remain usable unless
`warnings_invalid=True` is requested. Selection views are non-owning. Graph
partitions are independent owning copies with copied ancestor context, so a
partition can be handed to a consumer without sharing mutable objects with the
source graph.

## Scope boundaries

The core translates source rows and preserves supplied relationships. It does
not read pixel files, infer clinical diagnoses, choose a cohort definition, or
provide a mandatory validation pipeline. Finding localization, finding-to-ROI
matching, ROI transfer, patch extraction, and visualization policy belong in
downstream repositories or consumer code. Synthetic checks establish object
behavior; private-data, real-pixel, and scientific qualification require their
own evidence.

Start with the [documentation index](docs/README.md). The [data model
contract](docs/contract.md) and [API reference](docs/api.md) define supported
behavior.
