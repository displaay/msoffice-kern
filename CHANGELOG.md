# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-09

Initial release.

- `apply_legacy_kern`: derive a PowerPoint/MS Office-safe format-0 `kern`
  table from a static font's GPOS kerning, leaving GPOS untouched.
- Frequency-weighted, class-pair-atomic pair selection with UPM-relative
  value pruning and a Latin Extended text whitelist; capped at 10 900 pairs
  (`MAX_LEGACY_PAIRS`), validated against the 10 920-pair format-0 hard limit
  (`MAX_FORMAT0_PAIRS`).
- `strict=False` (default) turns recoverable per-font failures (no GPOS kern,
  no cmap, malformed GPOS, variable font) into
  `LegacyKernResult(applied=False, reason=...)` so a batch never fails on one
  font; `strict=True` raises the typed exceptions (`NoGposKernError`,
  `VariableFontError`, `ReservedPairsOverflowError`, `LegacyKernError`).
- Deterministic output locked by golden byte tests; CI runs them across the
  supported fonttools range (`>=4.61,<5`) on Python 3.10-3.14.
