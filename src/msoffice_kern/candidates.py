"""Build candidate legacy kern pairs from GPOS over the whitelist."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .gpos import accumulate_pair_value, kern_lookups
from .whitelist import whitelisted_glyphs

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

    from .gpos import PairGroup, PairPosSubtable


def build_legacy_kern_pairs(
    font: TTFont,
    profile: str,
    lookups: list[list[PairPosSubtable]] | None = None,
    unicode_map: dict[str, set[int]] | None = None,
) -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], PairGroup | None]]:
    """Evaluate whitelist x whitelist over GPOS.

    Returns a tuple ``(pairs, pair_groups)`` where ``pairs`` maps
    (left, right) -> kern value and ``pair_groups`` maps (left, right) to the
    GPOS class-pair group it expands from -- (lookup_index, subtable_index,
    class1, class2) -- or None when the value comes from an explicit format-1
    pair (or spans more than one lookup). The groups drive atomic class-pair
    selection at the cap.
    """
    glyphs = whitelisted_glyphs(font, profile, unicode_map)
    if lookups is None:
        lookups = kern_lookups(font)
    pairs: dict[tuple[str, str], int] = {}
    pair_groups: dict[tuple[str, str], PairGroup | None] = {}

    for left in glyphs:
        for right in glyphs:
            total, group = accumulate_pair_value(lookups, left, right)
            if total:
                pairs[(left, right)] = total
                pair_groups[(left, right)] = group

    return pairs, pair_groups
