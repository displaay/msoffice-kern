"""Unit tests of the legacy-kern derivation.

Adapted from the Displaay Customizer's ``test_ms_office_kern.py`` (the kern
half). They build a small synthetic font in memory with fontTools.fontBuilder,
so they are fast and need no font generation. The Office-metadata tests stay in
the consuming apps -- this package only does the kern table.
"""
import io

import pytest
from fontTools.fontBuilder import FontBuilder
from fontTools.pens.t2CharStringPen import T2CharStringPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont

import msoffice_kern as dmk
from msoffice_kern import (
    REMOVED_REASON_BELOW_MIN_ABS_VALUE,
    REMOVED_REASON_OVER_MAX_PAIRS,
    NoGposKernError,
    apply_legacy_kern,
)

GLYPH_CODEPOINTS = {
    "space": 0x0020,
    "A": 0x0041,
    "Aacute": 0x00C1,
    "Amacron": 0x0100,   # Latin Extended-A
    "L": 0x004C,
    "T": 0x0054,
    "Tbar": 0x0166,      # Latin Extended-A
    "V": 0x0056,
    "e": 0x0065,
    "n": 0x006E,
    "o": 0x006F,
    "oacute": 0x00F3,
    "v": 0x0076,
    "period": 0x002E,
    "quoteright": 0x2019,
    "at": 0x0040,        # NOT whitelisted (symbol)
}

GLYPH_ORDER = [".notdef"] + list(GLYPH_CODEPOINTS)

FEA_KERN = """
@A_GRP = [A Aacute Amacron];
@T_GRP = [T Tbar];

feature kern {
    pos @A_GRP @T_GRP -100;
    pos A V -80;
    pos V A -85;
    pos T A -90;
    pos L T -70;
    pos L V -55;
    pos T o -60;
    pos V o -40;
    pos T period -120;
    pos quoteright A -110;
    pos o oacute -3;
    pos e n -8;
    pos at A -150;
} kern;
"""

# all candidate pairs the whitelist x whitelist evaluation must find
EXPECTED_CANDIDATES = 17


def build_test_font(upm=1000, cff=False, features=FEA_KERN):
    fb = FontBuilder(upm, isTTF=not cff)
    fb.setupGlyphOrder(GLYPH_ORDER)
    fb.setupCharacterMap({cp: name for (name, cp) in GLYPH_CODEPOINTS.items()})

    advance = int(upm / 2)
    if cff:
        def draw():
            pen = T2CharStringPen(advance, None)
            pen.moveTo((50, 0))
            pen.lineTo((advance - 50, 0))
            pen.lineTo((advance - 50, int(upm * 0.7)))
            pen.lineTo((50, int(upm * 0.7)))
            pen.closePath()
            return pen.getCharString()
        charstrings = {name: draw() for name in GLYPH_ORDER}
        fb.setupCFF("KernTest-Regular", {}, charstrings, {})
    else:
        def draw():
            pen = TTGlyphPen(None)
            pen.moveTo((50, 0))
            pen.lineTo((advance - 50, 0))
            pen.lineTo((advance - 50, int(upm * 0.7)))
            pen.lineTo((50, int(upm * 0.7)))
            pen.closePath()
            return pen.glyph()
        fb.setupGlyf({name: draw() for name in GLYPH_ORDER})

    fb.setupHorizontalMetrics({name: (advance, 50) for name in GLYPH_ORDER})
    fb.setupHorizontalHeader(ascent=int(upm * 0.8), descent=-int(upm * 0.2))
    fb.setupNameTable({"familyName": "KernTest", "styleName": "Regular"},
                      mac=False)
    fb.setupOS2()
    fb.setupPost()
    if features:
        fb.addOpenTypeFeatures(features)
    return fb.font


def roundtrip(font):
    """Save + reload, so all tables come from a binary reader."""
    buf = io.BytesIO()
    font.save(buf)
    buf.seek(0)
    return TTFont(buf)


def kern_subtable(font):
    assert "kern" in font, "kern table missing"
    kern = font["kern"]
    assert len(kern.kernTables) == 1, "expected exactly 1 kern subtable"
    subtable = kern.kernTables[0]
    assert subtable.format == 0
    assert subtable.coverage == 1
    return subtable


def test_apply_basic_ttf():
    font = roundtrip(build_test_font())
    result = apply_legacy_kern(font)

    assert result.applied is True
    assert result.candidates == EXPECTED_CANDIDATES
    # (o, oacute) = -3 is below the threshold 5 (UPM 1000)
    assert result.after_value_pruning == EXPECTED_CANDIDATES - 1
    assert result.final == EXPECTED_CANDIDATES - 1
    assert result.reduced_to_cap is False
    assert result.effective_min_abs_value == 5

    table = kern_subtable(font).kernTable
    # the non-whitelisted glyph never enters the candidates
    assert ("at", "A") not in table
    assert ("o", "oacute") not in table

    # diagnostic pairs match the GPOS values defined in FEA_KERN
    assert table[("A", "T")] == -100      # from the class pair
    assert table[("Amacron", "Tbar")] == -100
    assert table[("A", "V")] == -80
    assert table[("V", "A")] == -85
    assert table[("T", "A")] == -90
    assert table[("L", "T")] == -70
    assert table[("L", "V")] == -55
    assert table[("T", "o")] == -60
    assert table[("V", "o")] == -40

    # punctuation is whitelisted
    assert table[("T", "period")] == -120
    assert table[("quoteright", "A")] == -110

    assert result.removed_by_reason == {
        REMOVED_REASON_BELOW_MIN_ABS_VALUE: 1,
        REMOVED_REASON_OVER_MAX_PAIRS: 0,
    }
    assert result.removed_pairs == [
        ("o", "oacute", -3, REMOVED_REASON_BELOW_MIN_ABS_VALUE)]


def test_apply_does_not_touch_protected_tables():
    font = roundtrip(build_test_font())
    protected = ("GPOS", "cmap", "glyf", "loca", "hmtx")
    before = {tag: font[tag].compile(font) for tag in protected}
    glyph_order_before = list(font.getGlyphOrder())

    result = apply_legacy_kern(font)
    assert result.applied is True

    for tag in protected:
        assert font[tag].compile(font) == before[tag], \
            f"{tag} table changed by apply_legacy_kern"
    assert list(font.getGlyphOrder()) == glyph_order_before
    roundtrip(font)


def test_apply_otf_cff():
    font = roundtrip(build_test_font(cff=True))
    cff_before = font["CFF "].compile(font)

    result = apply_legacy_kern(font)
    assert result.applied is True
    assert result.final == EXPECTED_CANDIDATES - 1
    kern_subtable(font)
    assert font["CFF "].compile(font) == cff_before


def test_apply_no_gpos_kern_not_strict():
    font = roundtrip(build_test_font(features=None))
    result = apply_legacy_kern(font)
    assert result.applied is False
    assert "GPOS" in result.reason
    assert "kern" not in font


def test_apply_no_gpos_kern_strict_raises():
    font = roundtrip(build_test_font(features=None))
    with pytest.raises(NoGposKernError):
        apply_legacy_kern(font, strict=True)


def test_apply_all_pairs_pruned():
    fea = "feature kern { pos e n -8; pos n o -3; } kern;"
    font = roundtrip(build_test_font(features=fea))
    result = apply_legacy_kern(font, min_abs_value=1000)
    assert result.applied is False
    assert "below the min abs value" in result.reason
    assert "kern" not in font


def test_min_abs_value_scales_with_upm():
    font_1000 = roundtrip(build_test_font(upm=1000))
    result_1000 = apply_legacy_kern(font_1000)
    assert result_1000.effective_min_abs_value == 5
    assert ("e", "n") in kern_subtable(font_1000).kernTable

    font_2048 = roundtrip(build_test_font(upm=2048))
    result_2048 = apply_legacy_kern(font_2048)
    assert result_2048.effective_min_abs_value == 10
    assert ("e", "n") not in kern_subtable(font_2048).kernTable
    assert ("o", "oacute") not in kern_subtable(font_2048).kernTable
    assert result_2048.removed_by_reason[REMOVED_REASON_BELOW_MIN_ABS_VALUE] == 2


def test_cap_reduction_atomic_and_frequency():
    font = roundtrip(build_test_font())
    # reserved: 8 sample pairs + (Amacron, T) + (A, Tbar) = 10
    result = apply_legacy_kern(font, max_pairs=11)
    assert result.applied is True
    assert result.reduced_to_cap is True
    assert result.reserved == 10
    assert result.final == 11

    table = kern_subtable(font).kernTable
    assert len(table) == 11
    # the frequency-weighted top scorer took the one leftover slot
    assert ("T", "period") in table
    # the residual class members (cost 3) were skipped as a whole
    assert ("Aacute", "T") not in table
    assert ("Aacute", "Tbar") not in table
    assert result.removed_by_reason[REMOVED_REASON_OVER_MAX_PAIRS] == 5

    cap_removed = [r for r in result.removed_pairs
                   if r[3] == REMOVED_REASON_OVER_MAX_PAIRS]
    assert len(cap_removed) == 5


def test_reserved_overflow_returns_not_applied():
    font = roundtrip(build_test_font())
    result = apply_legacy_kern(font, max_pairs=9)
    assert result.applied is False
    assert "reserved" in result.reason
    assert "kern" not in font


def test_selection_prefers_frequent_pairs():
    font = roundtrip(build_test_font())
    pairs = {("n", "o"): -40, ("quoteright", "Aacute"): -200}
    final, _reserved, capped = dmk.reduce_pairs_to_max_count(font, pairs, {}, 1)
    assert capped is True
    assert final == {("n", "o"): -40}


def test_selection_penalizes_lower_to_upper():
    font = roundtrip(build_test_font())
    pairs = {("o", "V"): -100, ("o", "v"): -100}
    final, _reserved, _capped = dmk.reduce_pairs_to_max_count(font, pairs, {}, 1)
    assert final == {("o", "v"): -100}


def test_selection_class_pairs_are_atomic():
    font = roundtrip(build_test_font())
    pairs = {
        ("A", "o"): -200,
        ("Aacute", "o"): -200,
        ("e", "n"): -44,
        ("n", "o"): -45,
        ("o", "n"): -43,
    }
    groups = {("A", "o"): (0, 0, 1, 1), ("Aacute", "o"): (0, 0, 1, 1)}

    final, _reserved, _capped = dmk.reduce_pairs_to_max_count(
        font, pairs, groups, 3)
    assert ("A", "o") in final and ("Aacute", "o") in final, \
        "class pair members must be selected together"
    assert ("e", "n") in final
    assert len(final) == 3

    final, _reserved, _capped = dmk.reduce_pairs_to_max_count(
        font, pairs, groups, 1)
    assert final == {("e", "n"): -44}, \
        "a class group over the leftover capacity must be skipped whole"
