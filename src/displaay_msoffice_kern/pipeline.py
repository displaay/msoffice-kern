"""High-level entry point: derive and write the reduced legacy kern table.

``apply_legacy_kern`` runs the whole steps-1..4 pipeline in memory
(read GPOS -> build candidates -> UPM-scaled prune -> frequency/atomic cap
reduction -> write one format-0 'kern' subtable) and returns a
:class:`LegacyKernResult`. GPOS is never touched. No metadata, name records,
STAT or DSIG handling happens here -- that is the responsibility of the caller
(the Builder/customizer apply their own Office-metadata pass around this).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from .candidates import build_legacy_kern_pairs
from .constants import (
    DEFAULT_MIN_ABS_VALUE,
    DEFAULT_PROFILE,
    MAX_LEGACY_PAIRS,
    REMOVED_REASON_BELOW_MIN_ABS_VALUE,
    REMOVED_REASON_OVER_MAX_PAIRS,
)
from .exceptions import LegacyKernError, NoGposKernError, ReservedPairsOverflowError
from .gpos import kern_lookups
from .reduce import reduce_legacy_kern_pairs
from .whitelist import unicode_glyph_map
from .write import replace_legacy_kern

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont


@dataclass
class LegacyKernResult:
    """Outcome of :func:`apply_legacy_kern`.

    Carries everything the desktop app and the web service need to build their
    own report objects (``PairReductionStats`` / ``MsOfficeKernResult``).
    ``removed_pairs`` entries are ``(left, right, value, reason)`` tuples whose
    reason is one of the ``REMOVED_REASON_*`` constants.
    """

    applied: bool
    reason: str | None = None
    profile: str = DEFAULT_PROFILE
    candidates: int = 0
    after_value_pruning: int = 0
    reserved: int = 0
    final: int = 0
    effective_min_abs_value: int = 0
    max_pairs: int = 0
    reduced_to_cap: bool = False
    removed_by_reason: dict[str, int] = field(default_factory=dict)
    removed_pairs: list[tuple[str, str, int, str]] = field(default_factory=list)

    def summary(self) -> str:
        if not self.applied:
            return f"applied=False reason={self.reason}"
        return (
            f"applied=True candidates={self.candidates} "
            f"after_pruning={self.after_value_pruning} final={self.final} "
            f"reserved={self.reserved} min_abs={self.effective_min_abs_value} "
            f"max_pairs={self.max_pairs} reduced_to_cap={self.reduced_to_cap}"
        )


def removed_pair_records(
    font: TTFont,
    candidate_pairs: dict[tuple[str, str], int],
    value_pruned_pairs: dict[tuple[str, str], int],
    final_pairs: dict[tuple[str, str], int],
) -> list[tuple[str, str, int, str]]:
    """Classify every dropped candidate as ``(left, right, value, reason)``.

    The reason is a ``REMOVED_REASON_*`` constant. The list is sorted by
    (reason, glyph order, glyph names) for reproducible reports.
    """
    glyph_order_index = {g: i for i, g in enumerate(font.getGlyphOrder())}
    removed: list[tuple[str, str, int, str]] = []
    for pair, value in candidate_pairs.items():
        if pair not in value_pruned_pairs:
            reason = REMOVED_REASON_BELOW_MIN_ABS_VALUE
        elif pair not in final_pairs:
            reason = REMOVED_REASON_OVER_MAX_PAIRS
        else:
            continue
        removed.append((pair[0], pair[1], value, reason))
    removed.sort(
        key=lambda r: (
            r[3],
            glyph_order_index.get(r[0], len(glyph_order_index)),
            glyph_order_index.get(r[1], len(glyph_order_index)),
            r[0],
            r[1],
        )
    )
    return removed


def apply_legacy_kern(
    font: TTFont,
    *,
    max_pairs: int = MAX_LEGACY_PAIRS,
    min_abs_value: int = DEFAULT_MIN_ABS_VALUE,
    profile: str = DEFAULT_PROFILE,
    strict: bool = False,
) -> LegacyKernResult:
    """Derive a reduced legacy kern table from GPOS and write it into ``font``.

    :param font: a compiled static :class:`~fontTools.ttLib.TTFont` (TTF or
        OTF/CFF). The font is mutated in place; GPOS is left untouched.
    :param max_pairs: hard cap for the single format-0 subtable.
    :param min_abs_value: value-pruning threshold at UPM 1000, scaled to the
        font's real unitsPerEm internally.
    :param profile: coverage profile (only ``"latin-extended-text"`` for now).
    :param strict: when False (default) a font without usable kerning yields a
        ``LegacyKernResult(applied=False, reason=...)`` instead of raising, so a
        batch never fails on one font. When True the typed exceptions propagate.
    :returns: :class:`LegacyKernResult`
    """
    try:
        lookups = kern_lookups(font)
    except NoGposKernError as exc:
        if strict:
            raise
        return LegacyKernResult(applied=False, reason=str(exc), profile=profile)

    unicode_map = unicode_glyph_map(font)
    pairs, pair_groups = build_legacy_kern_pairs(font, profile, lookups, unicode_map)
    if not pairs:
        reason = "no legacy kern candidates in the whitelist"
        if strict:
            raise LegacyKernError(reason)
        return LegacyKernResult(applied=False, reason=reason, profile=profile)

    try:
        reduction = reduce_legacy_kern_pairs(
            font, pairs, pair_groups, min_abs_value, max_pairs, unicode_map)
    except ReservedPairsOverflowError as exc:
        if strict:
            raise
        return LegacyKernResult(
            applied=False, reason=str(exc), profile=profile,
            candidates=len(pairs), max_pairs=max_pairs)

    final_pairs = reduction.final_pairs
    if not final_pairs:
        reason = (f"all {len(pairs)} candidate pairs below the min abs value "
                  f"{reduction.effective_min_abs_value}")
        if strict:
            raise LegacyKernError(reason)
        return LegacyKernResult(
            applied=False, reason=reason, profile=profile,
            candidates=len(pairs),
            effective_min_abs_value=reduction.effective_min_abs_value,
            max_pairs=max_pairs)

    removed = removed_pair_records(
        font, pairs, reduction.value_pruned_pairs, final_pairs)
    removed_by_reason = {
        REMOVED_REASON_BELOW_MIN_ABS_VALUE:
            len(pairs) - len(reduction.value_pruned_pairs),
        REMOVED_REASON_OVER_MAX_PAIRS:
            len(reduction.value_pruned_pairs) - len(final_pairs),
    }

    replace_legacy_kern(font, final_pairs)

    return LegacyKernResult(
        applied=True,
        profile=profile,
        candidates=len(pairs),
        after_value_pruning=len(reduction.value_pruned_pairs),
        reserved=reduction.reserved_count,
        final=len(final_pairs),
        effective_min_abs_value=reduction.effective_min_abs_value,
        max_pairs=max_pairs,
        reduced_to_cap=reduction.reduced_to_cap,
        removed_by_reason=removed_by_reason,
        removed_pairs=removed,
    )
