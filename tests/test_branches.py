"""Targeted branch tests for the font-domain fixes and untested code paths.

These accompany the C1-C4 / D1 fixes: each asserts the corrected behaviour and,
where relevant, would have failed against the pre-fix code. They build on the
synthetic-font helpers from ``test_kern_selection``.
"""
from types import SimpleNamespace

import pytest
from test_kern_selection import build_test_font, roundtrip

from displaay_msoffice_kern import (
    LegacyKernError,
    NoGposKernError,
    ReservedPairsOverflowError,
    apply_legacy_kern,
)
from displaay_msoffice_kern.candidates import build_legacy_kern_pairs
from displaay_msoffice_kern.constants import (
    DEFAULT_PROFILE,
    DIACRITIC_FACTOR,
    DIGIT_FREQUENCY,
    EPSILON_FREQUENCY,
    LETTER_FREQUENCIES,
    PUNCTUATION_FREQUENCIES,
    SPACE_FREQUENCY,
)
from displaay_msoffice_kern.gpos import (
    PairPosSubtable,
    accumulate_pair_value,
    gpos_kern_value,
    kern_lookups,
    x_advance,
)
from displaay_msoffice_kern.reduce import prune_pairs_by_min_abs_value
from displaay_msoffice_kern.scoring import build_glyph_score_data, codepoint_frequency
from displaay_msoffice_kern.whitelist import is_covered_codepoint


class _FakeSubtable:
    """Minimal stand-in exposing ``value_and_classes`` for the loop tests."""

    def __init__(self, results):
        self._results = results

    def value_and_classes(self, left, right):
        return self._results.get((left, right), (None, None))


# --- C1: Value2.XAdvance must not be added to the legacy value ---------------

def _first_pair_value_records(font):
    subtable = font["GPOS"].table.LookupList.Lookup[0].SubTable[0]
    record = subtable.PairSet[0].PairValueRecord[0]
    return record.Value1, record.Value2


def test_value2_xadvance_is_not_added():
    fea = "feature kern { pos V <-30 0 -30 0> A <0 0 -20 0>; } kern;"
    font = roundtrip(build_test_font(features=fea))
    value1, value2 = _first_pair_value_records(font)
    assert x_advance(value1) == -30
    assert x_advance(value2) == -20  # present and non-zero -> the test is real

    lookups = kern_lookups(font)
    pairs, _groups = build_legacy_kern_pairs(font, DEFAULT_PROFILE, lookups)
    assert pairs[("V", "A")] == -30  # only Value1.XAdvance (C1), not -50
    assert gpos_kern_value(lookups, "V", "A") == -30


# --- C2: a covered cell with value 0 masks later subtables -------------------

def test_format2_covers_zero_cell_returns_zero_not_none():
    font = roundtrip(build_test_font())
    lookups = kern_lookups(font)
    fmt2 = [st for lk in lookups for st in lk if st.format == 2]
    assert fmt2, "expected a format-2 class subtable in the fixture"
    subtable = fmt2[0]

    # A is in the class coverage; V has no right-class -> class-0 cell, value 0.
    adjustment, class_pair = subtable.value_and_classes("A", "V")
    assert adjustment == 0  # covered (not None) even at value 0 (C2)
    assert class_pair is not None

    # V is not in the subtable coverage at all -> genuinely not covered.
    assert subtable.value_and_classes("V", "A") == (None, None)


def test_zero_value_subtable_masks_later_subtable():
    early_zero = _FakeSubtable({("X", "Y"): (0, (1, 1))})
    later_nonzero = _FakeSubtable({("X", "Y"): (-50, (2, 2))})

    total, _group = accumulate_pair_value([[early_zero, later_nonzero]], "X", "Y")
    assert total == 0  # first covering subtable wins, even at 0 (C2)

    # sanity: that later subtable alone really would apply -50
    total_alone, _ = accumulate_pair_value([[later_nonzero]], "X", "Y")
    assert total_alone == -50


# --- C3 + multi-lookup accumulation -----------------------------------------

_FEA_MULTILOOKUP = """
@A_GRP = [A Aacute Amacron];
@T_GRP = [T Tbar];
feature kern {
    lookup k1 { pos @A_GRP @T_GRP -50; } k1;
    lookup k2 { pos A T -30; } k2;
} kern;
"""


def test_multilookup_sums_and_degrades_atomic_group():
    font = roundtrip(build_test_font(features=_FEA_MULTILOOKUP))
    lookups = kern_lookups(font)
    assert len(lookups) == 2

    pairs, groups = build_legacy_kern_pairs(font, DEFAULT_PROFILE, lookups)

    # value sums across both lookups
    assert pairs[("A", "T")] == -80
    assert gpos_kern_value(lookups, "A", "T") == -80

    # C3: a pair fed by >1 lookup is no longer atomically bound to a class group
    assert groups[("A", "T")] is None
    # a pure class member (single contributor) keeps its class group
    assert pairs[("Aacute", "T")] == -50
    assert groups[("Aacute", "T")] is not None
    assert groups[("A", "T")] != groups[("Aacute", "T")]


# --- C4: reserved count means the same under and over the cap ----------------

def test_reserved_count_consistent_under_and_over_cap():
    result_under = apply_legacy_kern(roundtrip(build_test_font()))
    result_over = apply_legacy_kern(roundtrip(build_test_font()), max_pairs=11)
    assert result_under.reduced_to_cap is False
    assert result_over.reduced_to_cap is True
    assert result_under.reserved == result_over.reserved == 10


def test_reserved_overflow_strict_raises_with_message():
    font = roundtrip(build_test_font())
    with pytest.raises(ReservedPairsOverflowError) as exc_info:
        apply_legacy_kern(font, max_pairs=9, strict=True)
    assert "reserved" in str(exc_info.value).lower()


# --- Extension (type 9) lookups ---------------------------------------------

def test_extension_pos_lookup_is_unwrapped():
    fea = "feature kern { lookup ext useExtension { pos A V -77; } ext; } kern;"
    font = roundtrip(build_test_font(features=fea))
    assert font["GPOS"].table.LookupList.Lookup[0].LookupType == 9

    lookups = kern_lookups(font)
    pairs, _groups = build_legacy_kern_pairs(font, DEFAULT_PROFILE, lookups)
    assert pairs[("A", "V")] == -77


# --- format-2 IndexError / unknown-format fall-throughs ----------------------

def test_format2_out_of_range_class_is_not_covered():
    fake = SimpleNamespace(
        Format=2,
        Coverage=SimpleNamespace(glyphs=["A"]),
        ClassDef1=SimpleNamespace(classDefs={"A": 5}),  # class index out of range
        ClassDef2=SimpleNamespace(classDefs={"B": 0}),
        Class1Record=[SimpleNamespace(Class2Record=[SimpleNamespace(Value1=None)])],
    )
    subtable = PairPosSubtable(fake)
    assert subtable.value_and_classes("A", "B") == (None, None)


def test_unknown_format_subtable_is_not_covered():
    fake = SimpleNamespace(Format=3, Coverage=SimpleNamespace(glyphs=["A"]))
    subtable = PairPosSubtable(fake)
    assert subtable.value_and_classes("A", "B") == (None, None)
    assert subtable.value("A", "B") is None


# --- a lookup referenced more than once is deduplicated ----------------------

def test_duplicate_lookup_reference_is_deduped():
    font = roundtrip(build_test_font(features="feature kern { pos A V -50; } kern;"))
    gpos = font["GPOS"].table
    kern_record = next(
        fr for fr in gpos.FeatureList.FeatureRecord if fr.FeatureTag == "kern"
    )
    indices = list(kern_record.Feature.LookupListIndex)
    kern_record.Feature.LookupListIndex = indices + indices  # referenced twice

    lookups = kern_lookups(font)
    assert sum(len(lk) for lk in lookups) == 1  # deduped to a single subtable

    pairs, _groups = build_legacy_kern_pairs(font, DEFAULT_PROFILE, lookups)
    assert pairs[("A", "V")] == -50  # not -100 (would be doubled without dedup)


# --- scoring helpers ---------------------------------------------------------

def test_codepoint_frequency_space():
    assert codepoint_frequency(0x0020) == SPACE_FREQUENCY


def test_codepoint_frequency_punctuation():
    assert codepoint_frequency(0x002E) == PUNCTUATION_FREQUENCIES[0x002E]


def test_codepoint_frequency_digit():
    assert codepoint_frequency(ord("5")) == DIGIT_FREQUENCY


def test_codepoint_frequency_plain_letter():
    assert codepoint_frequency(ord("a")) == LETTER_FREQUENCIES["a"]


def test_codepoint_frequency_diacritic_letter():
    # a-acute = 'a' + combining acute (NFD-decomposes)
    assert codepoint_frequency(0x00E1) == LETTER_FREQUENCIES["a"] * DIACRITIC_FACTOR


def test_codepoint_frequency_nondecomposing_letter_uses_name():
    # d-with-stroke does not NFD-decompose; the name regex recovers base 'd'
    assert codepoint_frequency(0x0111) == LETTER_FREQUENCIES["d"] * DIACRITIC_FACTOR


def test_codepoint_frequency_symbol_is_epsilon():
    assert codepoint_frequency(0x00A9) == EPSILON_FREQUENCY  # (c) sign, category So


def test_codepoint_frequency_non_latin_letter_is_epsilon():
    assert codepoint_frequency(0x03B1) == EPSILON_FREQUENCY  # Greek alpha, no base


def test_build_glyph_score_data_case_and_frequency():
    font = roundtrip(build_test_font())
    glyph_frequency, glyph_case = build_glyph_score_data(font)
    assert glyph_case["A"] == "upper"
    assert glyph_case["e"] == "lower"
    assert glyph_case["period"] == "other"
    assert glyph_frequency["A"] > 0
    assert glyph_frequency["e"] > 0


# --- validation paths --------------------------------------------------------

def test_prune_negative_threshold_raises():
    with pytest.raises(ValueError):
        prune_pairs_by_min_abs_value({("A", "B"): -10}, -1)


def test_is_covered_codepoint_unknown_profile_raises():
    with pytest.raises(ValueError):
        is_covered_codepoint(ord("A"), "not-a-profile")


# --- remaining guard / entry-point paths ------------------------------------

def test_x_advance_of_none_is_zero():
    assert x_advance(None) == 0


def test_build_legacy_kern_pairs_fetches_lookups_when_omitted():
    font = roundtrip(build_test_font())
    pairs, _groups = build_legacy_kern_pairs(font, DEFAULT_PROFILE)
    assert pairs[("A", "V")] == -80


def test_gpos_without_kern_feature_raises():
    font = roundtrip(build_test_font())
    for record in font["GPOS"].table.FeatureList.FeatureRecord:
        record.FeatureTag = "liga"  # no kern feature remains
    with pytest.raises(NoGposKernError):
        kern_lookups(font)


def test_kern_feature_without_pairpos_raises():
    # a single-positioning (type 1) lookup in the kern feature -> no PairPos
    fea = "feature kern { pos A <0 0 10 0>; } kern;"
    font = roundtrip(build_test_font(features=fea))
    with pytest.raises(NoGposKernError):
        kern_lookups(font)


def test_no_whitelisted_candidates_not_strict_then_strict():
    fea = "feature kern { pos at at -50; } kern;"  # 'at' is not whitelisted
    result = apply_legacy_kern(roundtrip(build_test_font(features=fea)))
    assert result.applied is False
    assert "whitelist" in result.reason
    assert "kern" not in roundtrip(build_test_font(features=fea))

    with pytest.raises(LegacyKernError):
        apply_legacy_kern(roundtrip(build_test_font(features=fea)), strict=True)


def test_all_pruned_strict_raises():
    fea = "feature kern { pos e n -8; pos n o -3; } kern;"
    with pytest.raises(LegacyKernError):
        apply_legacy_kern(
            roundtrip(build_test_font(features=fea)), min_abs_value=1000, strict=True
        )


def test_summary_for_applied_and_not_applied():
    applied = apply_legacy_kern(roundtrip(build_test_font()))
    text = applied.summary()
    assert text.startswith("applied=True")
    assert "final=" in text and "reserved=" in text

    not_applied = apply_legacy_kern(roundtrip(build_test_font(features=None)))
    assert not_applied.summary().startswith("applied=False")


def test_apply_twice_replaces_existing_kern():
    font = roundtrip(build_test_font())
    assert apply_legacy_kern(font).applied
    first_bytes = font["kern"].compile(font)
    # the second run must delete the existing 'kern' and rebuild it identically
    assert apply_legacy_kern(font).applied
    assert font["kern"].compile(font) == first_bytes
