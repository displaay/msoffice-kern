"""Reading kern data out of a font's GPOS table."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from .exceptions import LegacyKernError, NoGposKernError

if TYPE_CHECKING:
    from fontTools.ttLib import TTFont

# Identifier of a GPOS format-2 class x class record:
# (lookup_index, subtable_index, class1, class2). Every glyph pair that expands
# from the same record shares this group, so the cap reducer can keep or drop
# the whole expansion atomically.
PairGroup = tuple[int, int, int, int]


def x_advance(value_record: Any) -> int:
    if value_record is None:
        return 0
    return int(getattr(value_record, "XAdvance", 0) or 0)


class PairPosSubtable:
    def __init__(self, subtable: Any) -> None:
        self.subtable = subtable
        self.format: int | None = getattr(subtable, "Format", None)
        self.coverage: set[str] = set(
            getattr(getattr(subtable, "Coverage", None), "glyphs", [])
        )
        self.pair_sets: dict[str, dict[str, int]] = {}
        self.class_defs_1: dict[str, int] = {}
        self.class_defs_2: dict[str, int] = {}
        if self.format == 1:
            coverage_glyphs = list(
                getattr(getattr(subtable, "Coverage", None), "glyphs", None) or []
            )
            pair_sets = getattr(subtable, "PairSet", None) or []
            if len(coverage_glyphs) != len(pair_sets):
                raise LegacyKernError(
                    "Malformed GPOS PairPos format-1 subtable: coverage lists "
                    f"{len(coverage_glyphs)} glyphs but there are "
                    f"{len(pair_sets)} pair sets."
                )
            for first, pair_set in zip(coverage_glyphs, pair_sets, strict=True):
                second_values: dict[str, int] = {}
                records = getattr(pair_set, "PairValueRecord", None) or []
                for pair_record in records:
                    # Legacy kern is the gap *between* the pair, i.e. only the
                    # advance of the left glyph (Value1.XAdvance). Value2 moves
                    # the pen after the right glyph and must not be added in.
                    second_values[pair_record.SecondGlyph] = x_advance(
                        pair_record.Value1
                    )
                if second_values:
                    self.pair_sets[first] = second_values
        elif self.format == 2:
            # NULL ClassDef offsets decompile to None; treat them as "all
            # glyphs in class 0" instead of crashing on attribute access.
            self.class_defs_1 = (
                getattr(getattr(subtable, "ClassDef1", None), "classDefs", None) or {}
            )
            self.class_defs_2 = (
                getattr(getattr(subtable, "ClassDef2", None), "classDefs", None) or {}
            )

    def value_and_classes(
        self, left: str, right: str
    ) -> tuple[int | None, tuple[int, int] | None]:
        """Return ``(adjustment, class_pair)`` for the pair.

        ``adjustment`` is this subtable's legacy kern contribution, or ``None``
        when the subtable does not cover the pair. A subtable that *covers* the
        pair but adjusts it by 0 returns ``0`` (not ``None``): GPOS applies the
        first subtable whose coverage includes the left glyph and stops there,
        even when that value is 0, so a later subtable must not leak through.
        ``class_pair`` is the (class1, class2) tuple for format 2 (driving
        atomic class-pair selection) or ``None`` for format 1.
        """
        if self.format == 1:
            second_values = self.pair_sets.get(left)
            if second_values is None or right not in second_values:
                return None, None
            return second_values[right], None
        if self.format == 2:
            if left not in self.coverage:
                return None, None
            class_1 = self.class_defs_1.get(left, 0)
            class_2 = self.class_defs_2.get(right, 0)
            try:
                record = self.subtable.Class1Record[class_1].Class2Record[class_2]
                # Value1.XAdvance only (see __init__); the cell may
                # legitimately cover the pair with a 0 adjustment.
                value = x_advance(record.Value1)
            except (AttributeError, IndexError, TypeError):
                # out-of-range class index or a NULL record in malformed data
                return None, None
            return value, (class_1, class_2)
        return None, None

    def value(self, left: str, right: str) -> int | None:
        return self.value_and_classes(left, right)[0]


def pairpos_subtables_for_lookup(lookup: Any) -> list[PairPosSubtable]:
    subtables: list[PairPosSubtable] = []
    for subtable in lookup.SubTable:
        lookup_type = lookup.LookupType
        actual_subtable = subtable
        if lookup_type == 9:
            lookup_type = subtable.ExtensionLookupType
            actual_subtable = subtable.ExtSubTable
        if lookup_type == 2:
            subtables.append(PairPosSubtable(actual_subtable))
    return subtables


def kern_lookups(font: TTFont) -> list[list[PairPosSubtable]]:
    if "GPOS" not in font:
        raise NoGposKernError("Input font has no GPOS table.")

    gpos = font["GPOS"].table
    # Subset or minimal fonts may carry a GPOS whose FeatureList/LookupList
    # decompiled to None; treat those as "no usable kern", not a crash.
    feature_list = getattr(gpos, "FeatureList", None)
    if feature_list is None:
        raise NoGposKernError("Input font has GPOS, but no feature list.")

    lookup_indices: list[int] = []
    for feature_record in getattr(feature_list, "FeatureRecord", None) or []:
        if feature_record.FeatureTag != "kern":
            continue
        feature = feature_record.Feature
        if feature is None:
            continue
        for lookup_index in feature.LookupListIndex or []:
            if lookup_index not in lookup_indices:
                lookup_indices.append(lookup_index)

    if not lookup_indices:
        raise NoGposKernError("Input font has GPOS, but no kern feature.")

    lookup_list = getattr(gpos, "LookupList", None)
    all_lookups = getattr(lookup_list, "Lookup", None) or []
    if not all_lookups:
        raise LegacyKernError(
            "Malformed GPOS: kern feature present, but the lookup list is missing."
        )

    lookups: list[list[PairPosSubtable]] = []
    for lookup_index in lookup_indices:
        if lookup_index >= len(all_lookups):
            raise LegacyKernError(
                f"Malformed GPOS: kern feature references lookup {lookup_index}, "
                f"but the lookup list has only {len(all_lookups)} entries."
            )
        lookup = all_lookups[lookup_index]
        subtables = pairpos_subtables_for_lookup(lookup)
        if subtables:
            lookups.append(subtables)
    if not lookups:
        raise NoGposKernError("Input font has a kern feature, but no PairPos lookups.")
    return lookups


def accumulate_pair_value(
    lookups: list[list[PairPosSubtable]], left: str, right: str
) -> tuple[int, PairGroup | None]:
    """Sum the GPOS kern contributions for one pair across all kern lookups.

    Within a lookup the first subtable that covers the pair wins (subtables are
    ordered fallbacks); contributions are summed across lookups. Returns
    ``(total, group)``. ``group`` is the class-pair group only when the value
    comes from a single GPOS class x class record; it is ``None`` for an
    explicit pair, and is also dropped to ``None`` when more than one lookup
    contributes -- an explicit exception living in its own lookup must not stay
    atomically bound to the class siblings of the record it overrides.

    This is the single accumulation path: both :func:`gpos_kern_value` and the
    candidate builder go through it, so a kern-reading change lives in one place.
    """
    total = 0
    group: PairGroup | None = None
    contributors = 0
    for lookup_index, lookup in enumerate(lookups):
        for subtable_index, subtable in enumerate(lookup):
            adjustment, class_pair = subtable.value_and_classes(left, right)
            if adjustment is not None:
                total += adjustment
                contributors += 1
                if group is None and class_pair is not None:
                    group = (lookup_index, subtable_index, *class_pair)
                break
    if contributors > 1:
        group = None
    return total, group


def gpos_kern_value(
    lookups: list[list[PairPosSubtable]], left: str, right: str
) -> int:
    return accumulate_pair_value(lookups, left, right)[0]
