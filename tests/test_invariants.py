"""Structural invariants that must hold for any input.

These complement the value-specific unit tests and the golden byte tests: they
catch regressions that a hand-picked example would not reach -- especially in
the atomic cap reducer, where the subtlest bugs hide.
"""
import pytest
from test_kern_selection import build_test_font, roundtrip

from displaay_msoffice_kern import (
    DEFAULT_MIN_ABS_VALUE,
    DEFAULT_PROFILE,
    REMOVED_REASON_BELOW_MIN_ABS_VALUE,
    REMOVED_REASON_OVER_MAX_PAIRS,
    apply_legacy_kern,
)
from displaay_msoffice_kern.candidates import build_legacy_kern_pairs
from displaay_msoffice_kern.gpos import kern_lookups
from displaay_msoffice_kern.reduce import (
    effective_min_abs_value,
    reduce_legacy_kern_pairs,
    reserved_balanced_pairs,
)


@pytest.mark.parametrize("max_pairs", [11, 12, 13, 16, 10900])
def test_final_never_exceeds_cap(max_pairs):
    font = roundtrip(build_test_font())
    result = apply_legacy_kern(font, max_pairs=max_pairs)
    assert result.applied
    assert result.final <= max_pairs
    assert len(font["kern"].kernTables[0].kernTable) == result.final


def test_subset_chain_and_reserved_subset():
    font = roundtrip(build_test_font())
    lookups = kern_lookups(font)
    pairs, groups = build_legacy_kern_pairs(font, DEFAULT_PROFILE, lookups)
    reduction = reduce_legacy_kern_pairs(
        font, pairs, groups, DEFAULT_MIN_ABS_VALUE, 11
    )

    candidate = set(pairs)
    value_pruned = set(reduction.value_pruned_pairs)
    final = set(reduction.final_pairs)
    assert final <= value_pruned <= candidate

    reserved = reserved_balanced_pairs(font, reduction.value_pruned_pairs)
    assert reserved <= final  # reserved pairs are always kept


def test_output_sorted_by_glyph_id():
    font = roundtrip(build_test_font())
    apply_legacy_kern(font)
    # round-trip through binary so the subtable is re-read in on-disk order
    reloaded = roundtrip(font)
    glyph_id = {name: i for i, name in enumerate(reloaded.getGlyphOrder())}
    subtable = reloaded["kern"].kernTables[0]
    encoded = [(glyph_id[left], glyph_id[right]) for (left, right) in subtable.kernTable]
    assert encoded == sorted(encoded)


def test_removed_by_reason_sums_to_dropped_count():
    font = roundtrip(build_test_font())
    result = apply_legacy_kern(font, max_pairs=11)
    below = result.removed_by_reason[REMOVED_REASON_BELOW_MIN_ABS_VALUE]
    over = result.removed_by_reason[REMOVED_REASON_OVER_MAX_PAIRS]
    assert below + over == result.candidates - result.final
    assert len(result.removed_pairs) == below + over


def test_apply_is_deterministic():
    font_a = roundtrip(build_test_font())
    font_b = roundtrip(build_test_font())
    apply_legacy_kern(font_a, max_pairs=11)
    apply_legacy_kern(font_b, max_pairs=11)
    assert font_a["kern"].compile(font_a) == font_b["kern"].compile(font_b)


def test_effective_min_abs_value_scales_monotonically_with_upm():
    previous = -1
    for upm in (1000, 2048, 4096):
        font = roundtrip(build_test_font(upm=upm))
        value = effective_min_abs_value(font, DEFAULT_MIN_ABS_VALUE)
        assert value >= previous
        previous = value
