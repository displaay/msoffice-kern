"""Typed exceptions for the legacy-kern derivation.

The high-level :func:`displaay_msoffice_kern.apply_legacy_kern` catches these
when ``strict=False`` (the desktop/service default: one font without usable
kerning must not abort a batch). Pass ``strict=True`` to let them propagate as
a hard error (CLI / single-font use).
"""


class LegacyKernError(ValueError):
    """Base class for all recoverable legacy-kern derivation errors."""


class NoGposKernError(LegacyKernError):
    """The font has no usable GPOS kern feature to derive the table from."""


class ReservedPairsOverflowError(LegacyKernError):
    """The reserved/protected pairs alone exceed the pair cap."""
