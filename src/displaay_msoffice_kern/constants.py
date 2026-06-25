"""Shared constants for the legacy-kern selection."""

import re

MAX_LEGACY_PAIRS = 10_900

DEFAULT_PROFILE = "latin-extended-text"

DEFAULT_MIN_ABS_VALUE = 5

REMOVED_REASON_BELOW_MIN_ABS_VALUE = "below_min_abs_value"

REMOVED_REASON_OVER_MAX_PAIRS = "over_max_pairs"

LATIN_EXTENDED_TEXT_RANGES = (
    (0x0100, 0x017F),  # Latin Extended-A
    (0x0180, 0x024F),  # Latin Extended-B
    (0x1E00, 0x1EFF),  # Latin Extended Additional
    (0x2C60, 0x2C7F),  # Latin Extended-C
    (0xA720, 0xA7FF),  # Latin Extended-D
    (0xAB30, 0xAB6F),  # Latin Extended-E
)

SAMPLE_PAIRS = (
    ("A", "T"),
    ("A", "V"),
    ("T", "A"),
    ("V", "A"),
    ("L", "T"),
    ("L", "V"),
    ("T", "o"),
    ("V", "o"),
)

BASIC_PUNCTUATION_CODEPOINTS = frozenset((
    0x0021,  # !
    0x0022,  # "
    0x0027,  # '
    0x0028,  # (
    0x0029,  # )
    0x002C,  # ,
    0x002D,  # -
    0x002E,  # .
    0x003A,  # :
    0x003B,  # ;
    0x003F,  # ?
    0x2013,  # en dash
    0x2018,  # left single quote
    0x2019,  # right single quote
    0x201C,  # left double quote
    0x201D,  # right double quote
))

LETTER_FREQUENCIES = {
    "a": 0.083, "b": 0.016, "c": 0.030, "d": 0.039, "e": 0.127,
    "f": 0.016, "g": 0.020, "h": 0.034, "i": 0.075, "j": 0.008,
    "k": 0.025, "l": 0.046, "m": 0.029, "n": 0.071, "o": 0.072,
    "p": 0.024, "q": 0.004, "r": 0.064, "s": 0.064, "t": 0.070,
    "u": 0.039, "v": 0.019, "w": 0.010, "x": 0.003, "y": 0.017,
    "z": 0.012,
}

PUNCTUATION_FREQUENCIES = {
    0x002E: 0.011,   # .
    0x002C: 0.012,   # ,
    0x003A: 0.0015,  # :
    0x003B: 0.0008,  # ;
    0x2019: 0.004,   # right single quote (apostrophe use)
    0x2018: 0.001,
    0x201C: 0.002,
    0x201D: 0.002,
    0x0022: 0.002,
    0x0027: 0.002,
    0x002D: 0.006,   # -
    0x2013: 0.001,
    0x0028: 0.001,
    0x0029: 0.001,
    0x0021: 0.001,
    0x003F: 0.001,
}

SPACE_FREQUENCY = 0.07

DIGIT_FREQUENCY = 0.004

DIACRITIC_FACTOR = 0.15

EPSILON_FREQUENCY = 0.0001

LOWER_TO_UPPER_FACTOR = 0.1

LATIN_LETTER_NAME_RE = re.compile(r"LATIN (?:CAPITAL|SMALL) LETTER ([A-Z])\b")
