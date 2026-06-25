"""Golden byte tests: the compiled format-0 'kern' table must stay byte-stable.

These lock the actual output bytes, so any drift in the selection logic -- or a
serialiser change in a fontTools upgrade -- is caught loudly. The bytes depend
on the installed fontTools version; CI runs them across the supported range, and
``GOLDEN_FONTTOOLS_MINOR`` records the version they were generated against.

To regenerate after an *intended* change:
    python tests/regen_golden.py
"""
import os
import warnings

import pytest
from fontTools import __version__ as fonttools_version
from fontTools.ttLib import TTFont  # noqa: F401  (kept for parity / debugging)
from test_kern_selection import build_test_font, roundtrip

import displaay_msoffice_kern as dmk

GOLDEN_DIR = os.path.join(os.path.dirname(__file__), "golden")

# major.minor the golden bytes were generated against (the pinned dev env).
GOLDEN_FONTTOOLS_MINOR = "4.62"

# name -> (build_test_font kwargs, apply_legacy_kern kwargs)
CASES = {
    "ttf_upm1000": (dict(upm=1000), dict(max_pairs=10900, min_abs_value=5)),
    "cff_upm1000": (dict(upm=1000, cff=True), dict(max_pairs=10900, min_abs_value=5)),
    "ttf_upm2048": (dict(upm=2048), dict(max_pairs=10900, min_abs_value=5)),
    "ttf_cap11": (dict(upm=1000), dict(max_pairs=11, min_abs_value=5)),
}


def _running_fonttools_minor():
    return ".".join(fonttools_version.split(".")[:2])


def test_golden_fonttools_version_marker():
    """Visibility, not a gate: warn (do not fail) when the running fontTools
    minor differs from the one the goldens were generated against, so a byte
    drift reads as a serialiser change rather than a logic bug.
    """
    if _running_fonttools_minor() != GOLDEN_FONTTOOLS_MINOR:
        warnings.warn(
            f"golden 'kern' bytes were generated against fontTools "
            f"{GOLDEN_FONTTOOLS_MINOR}.x; running {fonttools_version}.",
            stacklevel=2,
        )


def produce_kern_bytes(name):
    font_kwargs, params = CASES[name]
    font = roundtrip(build_test_font(**font_kwargs))
    result = dmk.apply_legacy_kern(font, **params)
    assert result.applied, result.reason
    return font["kern"].compile(font)


@pytest.mark.parametrize("name", list(CASES))
def test_golden_kern_bytes(name):
    produced = produce_kern_bytes(name)
    golden_path = os.path.join(GOLDEN_DIR, name + ".kern.bin")
    with open(golden_path, "rb") as fh:
        expected = fh.read()
    assert produced == expected, (
        f"compiled 'kern' bytes drifted for {name} (running fontTools "
        f"{fonttools_version}, goldens from {GOLDEN_FONTTOOLS_MINOR}.x). "
        f"If this change is intended, regenerate with tests/regen_golden.py.")
