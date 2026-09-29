"""Immutable CRAFT-owned report composition records.

The records in this module select and describe already calculated scientific
content.  They intentionally contain no crystallographic calculations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Literal

from craft.analysis.reporting.model import Availability, StructureReport


class FigureKind(StrEnum):
    STANDARD_OVERVIEW = "standard-overview"
    SUGGESTED_FEATURE = "suggested-feature"
    USER_SNAPSHOT = "user-snapshot"


class LabelMode(StrEnum):
    ATOM_ORBITS = "atom-orbits"
    POLYHEDRON_ORBITS = "polyhedron-orbits"


@dataclass(frozen=True, slots=True)
class CameraStateRecord:
    position: tuple[float, float, float]
    focal_offset: tuple[float, float, float]
    view_up: tuple[float, float, float]
    parallel_scale: float
    view_angle: float
    parallel_projection: bool


@dataclass(frozen=True, slots=True)
class SceneManifest:
    document_id: str
    structure_fingerprint: str
    content_identity: str
    representation: str
    camera: CameraStateRecord
    visible_object_refs: tuple[str, ...]
    selected_object_refs: tuple[str, ...]
    labelled_orbit_refs: tuple[str, ...]
    label_mode: LabelMode
    show_cell: bool
    show_axes: bool
    show_legend: bool
    visual_settings: tuple[tuple[str, object], ...] = ()
    diagnostics: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "visible_object_refs", tuple(self.visible_object_refs))
        object.__setattr__(self, "selected_object_refs", tuple(self.selected_object_refs))
        object.__setattr__(self, "labelled_orbit_refs", tuple(self.labelled_orbit_refs))
        object.__setattr__(
            self,
            "visual_settings",
            tuple((str(key), value) for key, value in self.visual_settings),
        )
        object.__setattr__(self, "diagnostics", tuple(map(str, self.diagnostics)))


@dataclass(frozen=True, slots=True)
class ReportFigure:
    id: str
    kind: FigureKind
    title: str
    caption: str
    recommendation_reason: str
    manifest: SceneManifest
    preview_png: bytes
    include: bool = True
    stale: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "preview_png", bytes(self.preview_png))


@dataclass(frozen=True, slots=True)
class ReportReference:
    kind: Literal["table", "figure", "figure_panel"]
    target_id: str
    panel: str | None = None


@dataclass(frozen=True, slots=True)
class NumberedItem:
    target_id: str
    number: int


@dataclass(frozen=True, slots=True)
class ResolvedReference:
    kind: str
    target_id: str
    label: str
    resolved: bool
    message: str = ""


@dataclass(frozen=True, slots=True)
class FigureRecommendation:
    kind: FigureKind
    capability: str
    title: str
    reason: str
    label_mode: LabelMode = LabelMode.ATOM_ORBITS


@dataclass(frozen=True, slots=True)
class ReportRecommendation:
    table_ids: tuple[str, ...]
    figure_requests: tuple[FigureRecommendation, ...]
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ReportDraft:
    structure_fingerprint: str
    available_table_ids: tuple[str, ...] = ()
    selected_table_ids: tuple[str, ...] = ()
    figures: tuple[ReportFigure, ...] = ()
    references: tuple[ReportReference, ...] = ()
    recommendation_applied: bool = False

    def __post_init__(self) -> None:
        available = tuple(dict.fromkeys(str(item) for item in self.available_table_ids))
        selected = tuple(
            item
            for item in dict.fromkeys(str(item) for item in self.selected_table_ids)
            if item in available
        )
        figures_by_id = {figure.id: figure for figure in self.figures}
        if len(figures_by_id) != len(self.figures):
            raise ValueError("Report figure IDs must be unique.")
        object.__setattr__(self, "available_table_ids", available)
        object.__setattr__(self, "selected_table_ids", selected)
        object.__setattr__(self, "figures", tuple(self.figures))
        object.__setattr__(self, "references", tuple(self.references))

    def with_tables(self, table_ids: tuple[str, ...]) -> ReportDraft:
        return replace(self, selected_table_ids=tuple(table_ids))

    def with_figure(self, figure: ReportFigure) -> ReportDraft:
        figures = list(self.figures)
        for index, existing in enumerate(figures):
            if existing.id == figure.id:
                figures[index] = figure
                break
        else:
            figures.append(figure)
        return replace(self, figures=tuple(figures))

    def without_figure(self, figure_id: str) -> ReportDraft:
        return replace(
            self,
            figures=tuple(figure for figure in self.figures if figure.id != figure_id),
        )

    def move_figure(self, figure_id: str, destination: int) -> ReportDraft:
        figures = list(self.figures)
        source = next(
            (index for index, figure in enumerate(figures) if figure.id == figure_id),
            None,
        )
        if source is None:
            return self
        figure = figures.pop(source)
        destination = max(0, min(int(destination), len(figures)))
        figures.insert(destination, figure)
        return replace(self, figures=tuple(figures))

    def with_reference(self, reference: ReportReference) -> ReportDraft:
        return replace(self, references=(*self.references, reference))


def numbered_tables(draft: ReportDraft) -> tuple[NumberedItem, ...]:
    return tuple(
        NumberedItem(table_id, number)
        for number, table_id in enumerate(draft.selected_table_ids, start=1)
    )


def numbered_figures(draft: ReportDraft) -> tuple[NumberedItem, ...]:
    return tuple(
        NumberedItem(figure.id, number)
        for number, figure in enumerate(
            (item for item in draft.figures if item.include),
            start=1,
        )
    )


def resolve_reference(
    draft: ReportDraft,
    reference: ReportReference,
) -> ResolvedReference:
    if reference.kind == "table":
        number = next(
            (
                item.number
                for item in numbered_tables(draft)
                if item.target_id == reference.target_id
            ),
            None,
        )
        if number is None:
            return ResolvedReference(
                reference.kind,
                reference.target_id,
                f"Unresolved table: {reference.target_id}",
                False,
                "Referenced table is not included in this report.",
            )
        return ResolvedReference(
            reference.kind,
            reference.target_id,
            f"Table {number}",
            True,
        )

    number = next(
        (
            item.number
            for item in numbered_figures(draft)
            if item.target_id == reference.target_id
        ),
        None,
    )
    if number is None:
        return ResolvedReference(
            reference.kind,
            reference.target_id,
            f"Unresolved figure: {reference.target_id}",
            False,
            "Referenced figure is not included in this report.",
        )
    if reference.kind == "figure_panel":
        panel = (reference.panel or "").strip()
        if not panel:
            return ResolvedReference(
                reference.kind,
                reference.target_id,
                f"Unresolved panel: {reference.target_id}",
                False,
                "Referenced figure panel is missing.",
            )
        label = f"Figure {number}{panel}"
    else:
        label = f"Figure {number}"
    return ResolvedReference(
        reference.kind,
        reference.target_id,
        label,
        True,
    )


def mark_stale_figures(draft: ReportDraft, content_identity: str) -> ReportDraft:
    return replace(
        draft,
        figures=tuple(
            replace(
                figure,
                stale=figure.stale
                or figure.manifest.content_identity != content_identity,
            )
            for figure in draft.figures
        ),
    )


def ensure_report_draft(document, report: StructureReport) -> ReportDraft:
    """Refresh presentation availability without changing scientific content."""

    available = tuple(
        table_id
        for table_id, table in report.tables.items()
        if table.availability is Availability.AVAILABLE
    )
    current = getattr(document, "report_draft", None)
    fingerprint = document.canonical_structure_identity()
    if current is None:
        return ReportDraft(
            structure_fingerprint=fingerprint,
            available_table_ids=available,
        )
    refreshed = replace(
        current,
        structure_fingerprint=fingerprint,
        available_table_ids=available,
    )
    return mark_stale_figures(refreshed, document.content_identity())


def recommend_report_content(
    report: StructureReport,
    *,
    has_polyhedra: bool,
    has_rings: bool,
    has_topology: bool,
    has_morphology: bool,
) -> ReportRecommendation:
    """Select present report capabilities without deriving new science."""

    table_ids = tuple(
        table_id
        for table_id, table in report.tables.items()
        if table.availability is Availability.AVAILABLE
    )
    figures = [
        FigureRecommendation(
            FigureKind.STANDARD_OVERVIEW,
            "standard-overview",
            "Standard crystallographic overview",
            "Required overview in the source crystallographic setting.",
        )
    ]
    candidates = (
        (
            has_polyhedra,
            FigureRecommendation(
                FigureKind.SUGGESTED_FEATURE,
                "polyhedra",
                "Representative coordination environment",
                "Coordination polyhedra are available for this structure.",
                LabelMode.POLYHEDRON_ORBITS,
            ),
        ),
        (
            has_rings,
            FigureRecommendation(
                FigureKind.SUGGESTED_FEATURE,
                "rings",
                "Representative structural ring",
                "Structural ring orbits are available for this structure.",
            ),
        ),
        (
            has_topology,
            FigureRecommendation(
                FigureKind.SUGGESTED_FEATURE,
                "topology",
                "Periodic topology",
                "A periodic topology result is available for this structure.",
            ),
        ),
        (
            has_morphology,
            FigureRecommendation(
                FigureKind.SUGGESTED_FEATURE,
                "morphology",
                "Crystal morphology",
                "A CRAFT morphology model is available for this structure.",
            ),
        ),
    )
    for available, candidate in candidates:
        if available and len(figures) < 4:
            figures.append(candidate)
    return ReportRecommendation(
        table_ids,
        tuple(figures),
        tuple(item.reason for item in figures),
    )


__all__ = [
    "CameraStateRecord",
    "FigureKind",
    "FigureRecommendation",
    "LabelMode",
    "NumberedItem",
    "ReportDraft",
    "ReportFigure",
    "ReportRecommendation",
    "ReportReference",
    "ResolvedReference",
    "SceneManifest",
    "mark_stale_figures",
    "ensure_report_draft",
    "numbered_figures",
    "numbered_tables",
    "resolve_reference",
    "recommend_report_content",
]
