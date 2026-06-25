"""Two-stage reduction of candidate pairs to the legacy-table cap."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from .constants import SAMPLE_PAIRS
from .exceptions import ReservedPairsOverflowError
from .scoring import build_glyph_score_data, pair_score
from .whitelist import latin_extended_letter_glyphs

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

    from .gpos import PairGroup

# Sortable, hashable identifier used to bucket pairs into atomic groups. Class
# pairs key on their GPOS record; explicit/standalone pairs are singletons.
# Heterogeneous by construction (a "class"/"single" tag plus ints and names),
# so it is only ever compared, not introspected.
GroupId = tuple[Any, ...]


@dataclass
class ReductionResult:
    """Outcome of :func:`reduce_legacy_kern_pairs`."""
    final_pairs: dict[tuple[str, str], int]
    value_pruned_pairs: dict[tuple[str, str], int]
    reserved_count: int
    reduced_to_cap: bool
    effective_min_abs_value: int


def effective_min_abs_value(font: TTFont, min_abs_value: int) -> int:
    """Scale the threshold (defined at UPM 1000) to the font's unitsPerEm,
    so it cuts the same fraction of an em in every font.
    """
    upm = font["head"].unitsPerEm or 1000
    return int(round(min_abs_value * upm / 1000.0))


def prune_pairs_by_min_abs_value(
    pairs: dict[tuple[str, str], int],
    min_abs_value: int,
    protected_pairs: tuple[tuple[str, str], ...] = SAMPLE_PAIRS,
) -> dict[tuple[str, str], int]:
    if min_abs_value < 0:
        raise ValueError("--min-abs-value must be non-negative.")

    protected = set(protected_pairs)
    return {
        pair: value
        for pair, value in pairs.items()
        if abs(value) >= min_abs_value or pair in protected
    }


def pair_strength_key(
    pair: tuple[str, str], value: int, glyph_order_index: dict[str, int]
) -> tuple[int, int, int, str, str]:
    return (
        -abs(value),
        glyph_order_index.get(pair[0], len(glyph_order_index)),
        glyph_order_index.get(pair[1], len(glyph_order_index)),
        pair[0],
        pair[1],
    )


def strongest_pair(
    candidates: list[tuple[tuple[str, str], int]],
    glyph_order_index: dict[str, int],
) -> tuple[str, str] | None:
    if not candidates:
        return None
    return min(
        candidates,
        key=lambda item: pair_strength_key(item[0], item[1], glyph_order_index),
    )[0]


def reserved_balanced_pairs(
    font: TTFont,
    pairs: dict[tuple[str, str], int],
    unicode_map: dict[str, set[int]] | None = None,
) -> set[tuple[str, str]]:
    glyph_order: list[str] = font.getGlyphOrder()
    glyph_order_index = {
        glyph_name: index for index, glyph_name in enumerate(glyph_order)
    }
    extended_glyphs = latin_extended_letter_glyphs(font, unicode_map)
    reserved = {pair for pair in SAMPLE_PAIRS if pair in pairs}
    pairs_by_left: dict[str, list[tuple[tuple[str, str], int]]] = {}
    pairs_by_right: dict[str, list[tuple[tuple[str, str], int]]] = {}

    for pair, value in pairs.items():
        pairs_by_left.setdefault(pair[0], []).append((pair, value))
        pairs_by_right.setdefault(pair[1], []).append((pair, value))

    for glyph_name in glyph_order:
        if glyph_name not in extended_glyphs:
            continue
        left_pair = strongest_pair(
            pairs_by_left.get(glyph_name, []), glyph_order_index
        )
        right_pair = strongest_pair(
            pairs_by_right.get(glyph_name, []), glyph_order_index
        )
        if left_pair is not None:
            reserved.add(left_pair)
        if right_pair is not None:
            reserved.add(right_pair)

    return reserved


def _group_id(
    pair: tuple[str, str],
    group: PairGroup | None,
    glyph_order_index: dict[str, int],
) -> GroupId:
    """Sortable, deterministic group identifier. Class pairs group by their
    GPOS (lookup, subtable, class1, class2); explicit pairs are singletons.
    """
    if group is not None:
        return ("class", *group)
    return (
        "single",
        glyph_order_index.get(pair[0], len(glyph_order_index)),
        glyph_order_index.get(pair[1], len(glyph_order_index)),
        pair[0],
        pair[1],
    )


def reduce_pairs_to_max_count(
    font: TTFont,
    pairs: dict[tuple[str, str], int],
    pair_groups: dict[tuple[str, str], PairGroup | None],
    max_pairs: int,
    unicode_map: dict[str, set[int]] | None = None,
) -> tuple[dict[tuple[str, str], int], int, bool]:
    """Cap reduction with frequency-weighted, class-pair-atomic selection.

    Reserved pairs (diagnostics + strongest per extended letter) are always
    included. The rest of the capacity is filled greedily by whole class-pair
    groups ordered by score density (group score / group size); a group that
    does not fit is skipped in favor of smaller ones, so either all expansions
    of a class pair kern, or none of them do.

    The returned count is always the size of the full reserved set, whether or
    not the cap was hit, so callers can report a consistent "protected pairs"
    figure.
    """
    reserved = reserved_balanced_pairs(font, pairs, unicode_map)
    if len(pairs) <= max_pairs:
        return pairs, len(reserved), False

    if len(reserved) > max_pairs:
        raise ReservedPairsOverflowError(
            f"Protected/reserved legacy kern pairs require {len(reserved)} pairs; "
            f"max is {max_pairs}."
        )

    glyph_order_index = {
        glyph_name: index for index, glyph_name in enumerate(font.getGlyphOrder())
    }
    glyph_frequency, glyph_case = build_glyph_score_data(font, unicode_map)

    groups: dict[GroupId, list[tuple[tuple[str, str], int]]] = {}
    for pair, value in pairs.items():
        gid = _group_id(pair, pair_groups.get(pair), glyph_order_index)
        groups.setdefault(gid, []).append((pair, value))

    scored_groups: list[
        tuple[float, float, GroupId, list[tuple[tuple[str, str], int]]]
    ] = []
    for gid, members in groups.items():
        outside_reserved = [(p, v) for (p, v) in members if p not in reserved]
        if not outside_reserved:
            continue
        total_score = sum(
            pair_score(p, v, glyph_frequency, glyph_case)
            for (p, v) in outside_reserved
        )
        density = total_score / len(outside_reserved)
        scored_groups.append((-density, -total_score, gid, outside_reserved))
    scored_groups.sort(key=lambda item: item[:3])

    final_pairs = {pair: pairs[pair] for pair in reserved}
    capacity = max_pairs - len(final_pairs)
    for _density, _score, _gid, members in scored_groups:
        if capacity <= 0:
            break
        if len(members) > capacity:
            # atomic selection: skip the whole group, smaller ones may fit
            continue
        final_pairs.update(dict(members))
        capacity -= len(members)

    return final_pairs, len(reserved), True


def reduce_legacy_kern_pairs(
    font: TTFont,
    pairs: dict[tuple[str, str], int],
    pair_groups: dict[tuple[str, str], PairGroup | None],
    min_abs_value: int,
    max_pairs: int,
    unicode_map: dict[str, set[int]] | None = None,
) -> ReductionResult:
    """Two-stage reduction: UPM-relative value pruning, then cap reduction.

    ``min_abs_value`` is the raw threshold at UPM 1000; it is scaled to the
    font's real unitsPerEm here (exactly once). Returns a ReductionResult.
    """
    scaled = effective_min_abs_value(font, min_abs_value)
    value_pruned_pairs = prune_pairs_by_min_abs_value(pairs, scaled)
    final_pairs, reserved_count, reduced_to_cap = reduce_pairs_to_max_count(
        font, value_pruned_pairs, pair_groups, max_pairs, unicode_map
    )
    return ReductionResult(
        final_pairs=final_pairs,
        value_pruned_pairs=value_pruned_pairs,
        reserved_count=reserved_count,
        reduced_to_cap=reduced_to_cap,
        effective_min_abs_value=scaled,
    )
