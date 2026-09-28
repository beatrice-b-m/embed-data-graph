# Bea style assets (vendored)

`tokens.css`, `bea.css` and `bea.js` are an unmodified copy of the Bea
personal style system's web assets. The visualization tools inline them into
each generated page, so a page is self-contained and renders the same in
light and dark themes.

Do not edit these files here. To pick up a newer version of the style, rebuild
with `--bea-dir <bea-style>/assets --vendor`, which copies the three files over
these ones, and commit the result.

- Copied: 2026-09-28
- `tokens.css` is generated upstream from `tokens.json`; token names and their
  intended roles are documented there.
