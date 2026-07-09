"""Frequency-weighted scoring (sequential analysis) of kern pairs."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from .constants import (
    DIACRITIC_FACTOR,
    DIGIT_FREQUENCY,
    EPSILON_FREQUENCY,
    LATIN_LETTER_NAME_RE,
    LETTER_FREQUENCIES,
    LOWER_TO_UPPER_FACTOR,
    PUNCTUATION_FREQUENCIES,
    SPACE_FREQUENCY,
)
from .whitelist import unicode_glyph_map

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont


def codepoint_frequency(codepoint: int) -> float:
    """Relative frequency of the codepoint in a European language mix."""
    if codepoint == 0x0020:
        return SPACE_FREQUENCY
    if codepoint in PUNCTUATION_FREQUENCIES:
        return PUNCTUATION_FREQUENCIES[codepoint]
    ch = chr(codepoint)
    category = unicodedata.category(ch)
    if category == "Nd":
        return DIGIT_FREQUENCY
    if category.startswith("L"):
        base, has_diacritic = _base_letter(ch)
        if base is None:
            return EPSILON_FREQUENCY
        frequency = LETTER_FREQUENCIES[base]
        if has_diacritic:
            frequency *= DIACRITIC_FACTOR
        return frequency
    return EPSILON_FREQUENCY


def _base_letter(ch: str) -> tuple[str | None, bool]:
    """Return (base_letter_a_to_z_or_None, has_diacritic).

    Decomposes via NFD; for non-decomposing letters (dstroke, lslash,
    oslash...) falls back to the unicode name.
    """
    decomposed = unicodedata.normalize("NFD", ch)
    base = decomposed[0].lower()
    if base in LETTER_FREQUENCIES:
        return base, len(decomposed) > 1
    match = LATIN_LETTER_NAME_RE.match(unicodedata.name(ch, ""))
    if match:
        return match.group(1).lower(), True
    return None, False


def _glyph_case(codepoints: set[int]) -> str:
    categories = {unicodedata.category(chr(cp)) for cp in codepoints}
    if "Lu" in categories:
        return "upper"
    if "Ll" in categories:
        return "lower"
    return "other"


def build_glyph_score_data(
    font: TTFont, unicode_map: dict[str, set[int]] | None = None
) -> tuple[dict[str, float], dict[str, str]]:
    """Precompute per-glyph frequency and case category from the cmap.

    Returns (glyph_frequency, glyph_case) keyed by glyph name. Glyphs without
    a unicode mapping are absent (the whitelist excludes them anyway).
    """
    glyph_frequency: dict[str, float] = {}
    glyph_case: dict[str, str] = {}
    glyph_to_codepoints = unicode_map if unicode_map is not None else unicode_glyph_map(font)
    for glyph_name, codepoints in glyph_to_codepoints.items():
        glyph_frequency[glyph_name] = max(
            (codepoint_frequency(cp) for cp in codepoints),
            default=EPSILON_FREQUENCY,
        )
        glyph_case[glyph_name] = _glyph_case(codepoints)
    return glyph_frequency, glyph_case


def pair_score(
    pair: tuple[str, str],
    value: int,
    glyph_frequency: dict[str, float],
    glyph_case: dict[str, str],
) -> float:
    """Selection score: ``abs(value) * P(left) * P(right) * case factor``.

    Each pair costs one slot, so for singleton pairs greedy top-score
    selection is optimal. Atomic class-pair groups span several slots, so the
    cap reducer orders whole groups by score density (score / size) -- a
    heuristic, not a global optimum (group selection is a 0/1 knapsack). The
    quality rests on this function.
    """
    left, right = pair
    factor = 1.0
    if glyph_case.get(left) == "lower" and glyph_case.get(right) == "upper":
        factor = LOWER_TO_UPPER_FACTOR
    return (
        abs(value)
        * glyph_frequency.get(left, EPSILON_FREQUENCY)
        * glyph_frequency.get(right, EPSILON_FREQUENCY)
        * factor
    )
