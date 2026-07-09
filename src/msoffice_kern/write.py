"""Writing the reduced pairs into a single format-0 'kern' subtable."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fontTools.ttLib import newTable
from fontTools.ttLib.tables._k_e_r_n import KernTable_format_0

from .constants import MAX_FORMAT0_PAIRS

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont


def replace_legacy_kern(font: TTFont, pairs: dict[tuple[str, str], int]) -> None:
    if len(pairs) > MAX_FORMAT0_PAIRS:
        # Beyond this, the subtable's 16-bit length field cannot hold the
        # data; fontTools would truncate it with only a warning and GDI would
        # misread the table.
        raise ValueError(
            f"{len(pairs)} pairs exceed the format-0 'kern' subtable capacity "
            f"of {MAX_FORMAT0_PAIRS} pairs."
        )
    if "kern" in font:
        del font["kern"]

    kern_table = newTable("kern")
    kern_table.version = 0

    subtable = KernTable_format_0()
    subtable.coverage = 1
    # KernTable_format_0.compile re-sorts the pairs by glyph ID, so the dict
    # insertion order here does not affect the output bytes.
    subtable.kernTable = dict(pairs)

    kern_table.kernTables = [subtable]
    font["kern"] = kern_table
