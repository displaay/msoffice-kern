"""Coverage profile: which glyphs are candidates for the legacy table."""

from __future__ import annotations

import unicodedata
from typing import TYPE_CHECKING

from .constants import BASIC_PUNCTUATION_CODEPOINTS, LATIN_EXTENDED_TEXT_RANGES

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont


def is_latin_extended_text_codepoint(codepoint: int) -> bool:
    return (
        codepoint == 0x0020
        or 0x0030 <= codepoint <= 0x0039
        or 0x0041 <= codepoint <= 0x005A
        or 0x0061 <= codepoint <= 0x007A
        or (
            0x00A0 <= codepoint <= 0x00FF
            and unicodedata.category(chr(codepoint)).startswith("L")
        )
        or (
            any(
                start <= codepoint <= end
                for start, end in LATIN_EXTENDED_TEXT_RANGES
            )
            and unicodedata.category(chr(codepoint)).startswith("L")
        )
    )


def is_covered_codepoint(codepoint: int, profile: str) -> bool:
    if profile == "latin-extended-text":
        return (
            is_latin_extended_text_codepoint(codepoint)
            or codepoint in BASIC_PUNCTUATION_CODEPOINTS
        )
    raise ValueError(f"Unknown coverage profile: {profile}")


def is_latin_extended_letter_codepoint(codepoint: int) -> bool:
    return (
        any(start <= codepoint <= end for start, end in LATIN_EXTENDED_TEXT_RANGES)
        and unicodedata.category(chr(codepoint)).startswith("L")
    )


def unicode_glyph_map(font: TTFont) -> dict[str, set[int]]:
    glyph_to_codepoints: dict[str, set[int]] = {}
    for cmap in font["cmap"].tables:
        if not cmap.isUnicode():
            continue
        for codepoint, glyph_name in cmap.cmap.items():
            glyph_to_codepoints.setdefault(glyph_name, set()).add(codepoint)
    return glyph_to_codepoints


def whitelisted_glyphs(
    font: TTFont, profile: str, unicode_map: dict[str, set[int]] | None = None
) -> list[str]:
    glyph_to_codepoints = unicode_map if unicode_map is not None else unicode_glyph_map(font)
    glyph_order: list[str] = font.getGlyphOrder()
    keep = {
        glyph_name
        for glyph_name, codepoints in glyph_to_codepoints.items()
        if any(is_covered_codepoint(codepoint, profile) for codepoint in codepoints)
    }
    return [glyph_name for glyph_name in glyph_order if glyph_name in keep]


def latin_extended_letter_glyphs(
    font: TTFont, unicode_map: dict[str, set[int]] | None = None
) -> set[str]:
    glyph_to_codepoints = unicode_map if unicode_map is not None else unicode_glyph_map(font)
    return {
        glyph_name
        for glyph_name, codepoints in glyph_to_codepoints.items()
        if any(is_latin_extended_letter_codepoint(codepoint) for codepoint in codepoints)
    }
