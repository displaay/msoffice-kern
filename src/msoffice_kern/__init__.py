"""msoffice-kern -- derive a PowerPoint/MS Office-safe legacy ``kern``
table from a font's GPOS kerning.

PowerPoint and the GDI text paths in MS Office do not read GPOS kerning; they
only kern by the legacy format-0 ``kern`` table. This package reads the full
GPOS kerning of a compiled static TTF/OTF, selects a reduced set of pairs
(frequency-weighted, atomic per GPOS class pair, UPM-relative threshold,
capped at ~10 900), and writes a single format-0 subtable -- leaving GPOS
untouched so modern applications keep the complete kerning.

It is a single, deterministic implementation of that conversion: golden byte
tests lock the produced ``kern`` table, so the same input always yields the same
bytes.

High-level use::

    from msoffice_kern import apply_legacy_kern
    result = apply_legacy_kern(font)          # mutates `font` in place
    if result.applied:
        ...                                    # font now has the kern table
"""

from .candidates import build_legacy_kern_pairs
from .constants import (
    BASIC_PUNCTUATION_CODEPOINTS,
    DEFAULT_MIN_ABS_VALUE,
    DEFAULT_PROFILE,
    DIACRITIC_FACTOR,
    DIGIT_FREQUENCY,
    EPSILON_FREQUENCY,
    LATIN_EXTENDED_TEXT_RANGES,
    LETTER_FREQUENCIES,
    LOWER_TO_UPPER_FACTOR,
    MAX_FORMAT0_PAIRS,
    MAX_LEGACY_PAIRS,
    PUNCTUATION_FREQUENCIES,
    REMOVED_REASON_BELOW_MIN_ABS_VALUE,
    REMOVED_REASON_OVER_MAX_PAIRS,
    SAMPLE_PAIRS,
    SPACE_FREQUENCY,
)
from .exceptions import (
    LegacyKernError,
    NoGposKernError,
    ReservedPairsOverflowError,
    VariableFontError,
)
from .gpos import (
    PairPosSubtable,
    gpos_kern_value,
    kern_lookups,
    pairpos_subtables_for_lookup,
    x_advance,
)
from .pipeline import LegacyKernResult, apply_legacy_kern, removed_pair_records
from .reduce import (
    ReductionResult,
    effective_min_abs_value,
    pair_strength_key,
    prune_pairs_by_min_abs_value,
    reduce_legacy_kern_pairs,
    reduce_pairs_to_max_count,
    reserved_balanced_pairs,
    strongest_pair,
)
from .scoring import (
    build_glyph_score_data,
    codepoint_frequency,
    pair_score,
)
from .whitelist import (
    is_covered_codepoint,
    is_latin_extended_letter_codepoint,
    is_latin_extended_text_codepoint,
    latin_extended_letter_glyphs,
    unicode_glyph_map,
    whitelisted_glyphs,
)
from .write import replace_legacy_kern

__version__ = "0.1.0"

# Public API, split into two stability tiers. Everything here is importable;
# the tiers document intent, not access:
#
#   * Tier 1 -- the supported, stable surface most callers need.
#   * Tier 2 -- lower-level building blocks (GPOS readers, scoring, the
#     reduction primitives, whitelist predicates and frequency tables). They are
#     exported for advanced use and are equally reachable from their submodules,
#     e.g. ``from msoffice_kern.reduce import reduce_pairs_to_max_count``.
#     Narrowing Tier 2 out of the top level is deferred until the depending
#     applications are confirmed not to import these names from the top level.
__all__ = [
    # --- Tier 1: stable public API ---
    "__version__",
    "apply_legacy_kern",
    "LegacyKernResult",
    "LegacyKernError",
    "NoGposKernError",
    "ReservedPairsOverflowError",
    "VariableFontError",
    "MAX_FORMAT0_PAIRS",
    "MAX_LEGACY_PAIRS",
    "DEFAULT_MIN_ABS_VALUE",
    "DEFAULT_PROFILE",
    "REMOVED_REASON_BELOW_MIN_ABS_VALUE",
    "REMOVED_REASON_OVER_MAX_PAIRS",
    # --- Tier 2: advanced / low-level primitives (also on submodules) ---
    # GPOS reading
    "PairPosSubtable",
    "kern_lookups",
    "pairpos_subtables_for_lookup",
    "gpos_kern_value",
    "x_advance",
    # candidates / whitelist
    "build_legacy_kern_pairs",
    "whitelisted_glyphs",
    "unicode_glyph_map",
    "latin_extended_letter_glyphs",
    "is_covered_codepoint",
    "is_latin_extended_text_codepoint",
    "is_latin_extended_letter_codepoint",
    # scoring
    "codepoint_frequency",
    "build_glyph_score_data",
    "pair_score",
    # reduction
    "reduce_legacy_kern_pairs",
    "reduce_pairs_to_max_count",
    "ReductionResult",
    "prune_pairs_by_min_abs_value",
    "reserved_balanced_pairs",
    "strongest_pair",
    "pair_strength_key",
    "effective_min_abs_value",
    # writing / reporting
    "replace_legacy_kern",
    "removed_pair_records",
    # frequency / coverage constants
    "SAMPLE_PAIRS",
    "LETTER_FREQUENCIES",
    "PUNCTUATION_FREQUENCIES",
    "BASIC_PUNCTUATION_CODEPOINTS",
    "LATIN_EXTENDED_TEXT_RANGES",
    "SPACE_FREQUENCY",
    "DIGIT_FREQUENCY",
    "DIACRITIC_FACTOR",
    "EPSILON_FREQUENCY",
    "LOWER_TO_UPPER_FACTOR",
]
