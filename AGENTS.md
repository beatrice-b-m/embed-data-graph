# EMBED Data Model

A Python object model for Emory Breast Imaging Dataset (EMBED) clinical and
mammography data. The distribution is `embed-data-graph`; import
`embed_data_graph`. The Python project lives at the repository root. See
`README.md` for researcher entry points and `CONTRIBUTING.md` for development
and compatibility expectations.


## Inline API documentation

- Update docstrings and type annotations alongside every public API change,
  including root exports, supported specialist modules, public members, and
  returned objects. Bring touched public interfaces into compliance.
- Use NumPy-style docstrings for purpose, parameters and defaults, returns,
  relevant exceptions, and useful examples. Document exported entry points,
  including wrappers, rather than only their implementation helpers.
- Explain applicable missing-value, unit, ordering, mutation, ownership,
  side-effect, limit, and serialization contracts. Keep essential usage in
  docstrings and consistent with `docs/api.md`, `docs/contract.md`, and the
  runnable examples in `docs/user-guide.md` and `examples/`.
- Provide precise public types and statically discoverable signatures,
  including decorator controls and forwarded options. Keep private arguments
  out of supported interfaces and preserve Python 3.9 compatibility.
- Execute changed examples and run the applicable checks in `CONTRIBUTING.md`.
  For interface changes, check editor signatures, completions, and navigation
  through returned objects; report runtime introspection separately from actual
  editor verification. Verify typing metadata in distribution artifacts.

## Git Commit Policy

Every completed task must be tracked in a descriptive, granular git commit.
This requirement is critical and must be followed under all
circumstances - no exceptions.

**Rules:**

- Commit after every distinct logical unit of work, not at the end of a session.
- Each commit covers exactly one coherent change (one module, one component, one
  test suite, one docs section). Do not batch unrelated changes into a single
  commit.
- Commit messages must be informative: use `type(scope): subject` format,
  include a blank line, then a body describing *what* changed and *why*.
  - Types: `feat`, `fix`, `test`, `docs`, `refactor`, `chore`
  - Scope: the module, file, or subsystem affected, such as `backend`,
    `frontend`, `pixels`, `server`, `types`, or `tests`
  - Subject: imperative mood, 72 characters or fewer
  - Body: explain the design decision, the invariant being established, or the
    behavior being changed, not a restatement of the diff
- Stage files selectively (`git add <file>`) rather than `git add -A`. Only
  commit files that belong to the current logical unit.
- Never amend or force-push commits that have been logged here.

**Verification:** After each task, run `git log --oneline -3` to confirm the
commit was recorded before moving to the next task.
