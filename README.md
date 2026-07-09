# msoffice-kern

Derive a **PowerPoint / MS Office–safe legacy `kern` table** from a font's GPOS
kerning, without touching GPOS.

PowerPoint and the GDI text paths in MS Office do not read GPOS kerning — they
only kern by the old format-0 `kern` table. This package reads the full GPOS
kerning of a compiled **static** TTF or OTF/CFF, selects a reduced set of pairs,
and writes a single format-0 `kern` subtable. Modern applications keep using the
untouched GPOS; Office gets a working fallback.

It is a single, well-tested, deterministic implementation of that conversion:
golden byte tests lock the produced `kern` table, so the same input always
yields the same bytes.

## Installation

```bash
pip install msoffice-kern
```

## Usage

```python
from fontTools.ttLib import TTFont
from msoffice_kern import apply_legacy_kern

font = TTFont("Family-Regular.ttf")      # a compiled static TTF/OTF
result = apply_legacy_kern(font)         # mutates font in place; GPOS untouched
if result.applied:
    font.save("Family-Regular.ttf")
print(result.summary())
```

`apply_legacy_kern(font, *, max_pairs=10900, min_abs_value=5,
profile="latin-extended-text", strict=False)` returns a `LegacyKernResult`.
With `strict=False` (default) a font whose kerning cannot be derived — no
usable GPOS kern, no cmap, malformed GPOS, or a variable font — yields
`applied=False` instead of raising, so a batch never fails on one font; with
`strict=True` the typed exceptions propagate. Variable fonts are always
refused (`VariableFontError`): the legacy table could only encode the default
instance, so derive it from exported static instances instead. `max_pairs` is
validated against the format-0 hard limit of 10 920 pairs
(`MAX_FORMAT0_PAIRS`, the subtable's 16-bit length capacity). The low-level
primitives (`kern_lookups`, `build_legacy_kern_pairs`,
`reduce_pairs_to_max_count`, `replace_legacy_kern`, …) are exported too.

## Selection algorithm

When the candidate count exceeds the `MAX_LEGACY_PAIRS` (10 900) cap, pairs are
chosen by:

- **Frequency-weighted score** — `abs(value) × P(left) × P(right) × case_factor`
  (European-language letter/punctuation frequencies; lowercase→UPPERCASE
  transitions penalised).
- **Atomic class-pair selection** — all expansions of one GPOS class×class
  record (`A/Á/Â × T`) are kept or dropped together. Whole groups are filled by
  score density (group score / group size); this is a heuristic, not a global
  optimum (selecting variable-size groups under a cap is a 0/1 knapsack).
- **UPM-relative pruning** — tiny pairs below `round(min_abs_value × upm / 1000)`
  are dropped first.
- **Whitelist** — Latin Extended *text* letters plus basic punctuation; symbols,
  currency and unencoded alternates stay out.

Diagnostic pairs (`AT AV TA VA LT LV To Vo`) and the strongest left/right pair
per Latin Extended letter are always reserved.

## Scope

This package does **only** the legacy `kern` derivation. Font naming/STAT/WWS
metadata, autohinting, subsetting, WOFF and verification are out of scope.

## Determinism

`fontTools` serialises the final `kern` table, so its version affects the byte
output. The golden tests lock the produced bytes, and CI runs them on a matrix
of `fonttools` versions across the supported range (`>=4.61,<5`) so the output
stays byte-stable for the whole range.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src tests
mypy
```
