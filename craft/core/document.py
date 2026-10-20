from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass, field, fields, is_dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from cristma.diagnostics import Severity
from cristma.structure import CrystalStructure as CanonicalCrystalStructure, MolecularStructure, Structure

from craft.analysis.hierarchy import HierarchyReport
from craft.analysis.inorganic_topology import (
    InorganicTopologyReport,
)
from craft.analysis.cristma_inorganic import (
    NativeInorganicSettings,
    NativeInorganicSnapshot,
)
from craft.analysis.cristma_organic import (
    NativeOrganicSettings,
    NativeOrganicSnapshot,
)
from craft.analysis.structure_profile import (
    ProfileDecision,
    RequestedProfile,
    ResolvedProfile,
    resolve_structure_profile,
)
from craft.analysis.structural_motifs import StructuralMotifPresentation
from craft.analysis.reporting.composer import ReportDraft
from craft.core.model import CrystalStructure
from craft.core.visualization import VisualizationState
from craft.core.scientific_cache import (
    INORGANIC_RESULT_SLOTS,
    ORGANIC_RESULT_SLOTS,
    ScientificRequestKey,
    ScientificResultSlot,
    ScientificResultProvenance,
    ScientificResultSlots,
)
from craft.core.structure_source import LoadedStructure, StructureSourceContext

if TYPE_CHECKING:
    from craft.presentation.inorganic import InorganicPresentation
    from craft.presentation.organic import OrganicPresentation


@dataclass(frozen=True, slots=True)
class DocumentWarning:
    code: str
    message: str
    severity: str = "warning"


def _diagnostic_warning(diagnostic: object) -> DocumentWarning:
    severity = getattr(diagnostic, "severity", "warning")
    return DocumentWarning(
        str(getattr(diagnostic, "code", "")),
        str(getattr(diagnostic, "message", diagnostic)),
        str(getattr(severity, "value", severity)),
    )


def _source_warnings(
    source: StructureSourceContext, projection: CrystalStructure,
) -> tuple[DocumentWarning, ...]:
    fatal = tuple(item for item in source.diagnostics if item.severity is Severity.ERROR)
    if fatal:
        codes = ", ".join(item.code for item in fatal)
        raise ValueError(f"Cannot create a document from a fatal source diagnostic: {codes}")
    source_warnings = tuple(_diagnostic_warning(item) for item in source.diagnostics)
    occupancy_warnings = tuple(
        DocumentWarning(
            "occupancy-out-of-range",
            f"{site.label}: reported occupancy {site.reported_occupancy:g} is outside 0–1.",
        )
        for site in projection.asymmetric_sites
        if site.occupancy_warning
    )
    return tuple(dict.fromkeys((*source_warnings, *occupancy_warnings)))


def _identity_data(value: object) -> object:
    """Normalize public data, preserving values and removing container order."""
    kind = f"{type(value).__module__}.{type(value).__qualname__}"
    if is_dataclass(value):
        return (kind, tuple(
            (item.name, _identity_data(getattr(value, item.name)))
            for item in fields(value) if item.repr
        ))
    if isinstance(value, Mapping):
        items = ((_identity_data(key), _identity_data(item)) for key, item in value.items())
        return (kind, tuple(sorted(items, key=lambda pair: repr(pair[0]))))
    if isinstance(value, np.ndarray):
        return (kind, value.dtype.str, value.shape, _identity_data(value.tolist()))
    if isinstance(value, np.generic):
        return _identity_data(value.item())
    if isinstance(value, (set, frozenset)):
        return (kind, tuple(sorted((_identity_data(item) for item in value), key=repr)))
    if isinstance(value, (list, tuple)):
        return (kind, tuple(_identity_data(item) for item in value))
    return value


@dataclass(slots=True)
class StructureDocument:
    id: str
    structure: Structure
    source: StructureSourceContext
    legacy_projection: CrystalStructure
    hierarchy: HierarchyReport = field(default_factory=HierarchyReport)
    warnings: tuple[DocumentWarning, ...] = ()
    scientific: ScientificResultSlots = field(default_factory=ScientificResultSlots)
    contact_presentation: object | None = None
    native_settings: NativeInorganicSettings = field(default_factory=NativeInorganicSettings)
    native_organic_settings: NativeOrganicSettings = field(
        default_factory=NativeOrganicSettings
    )
    inorganic_topology: InorganicTopologyReport | None = None
    requested_profile: RequestedProfile = RequestedProfile.AUTO
    profile_decision: ProfileDecision | None = None
    analysis_stage: str = "topology"
    visual: VisualizationState = field(default_factory=VisualizationState)
    descriptor_cache: dict[tuple[object, ...], object] = field(default_factory=dict)
    comparison_cache: dict[tuple[object, ...], object] = field(default_factory=dict)
    morphology_cache: dict[tuple[object, ...], object] = field(default_factory=dict)
    morphology_state: object | None = None
    knowledge_state: object | None = None
    scene_cache: dict[tuple[object, ...], object] = field(default_factory=dict)
    ring_motifs: StructuralMotifPresentation | None = None
    report_draft: ReportDraft | None = None
    _inorganic_presentation_cache: tuple[
        tuple[object, ...], InorganicPresentation
    ] | None = field(default=None, init=False, repr=False)
    _organic_presentation_cache: tuple[
        tuple[object, ...], OrganicPresentation
    ] | None = field(default=None, init=False, repr=False)
    _canonical_identity_cache: tuple[str, Structure, str] | None = field(
        default=None, init=False, repr=False, compare=False,
    )
    _scientific_identity_cache: tuple[ScientificResultSlots, str] | None = field(
        default=None, init=False, repr=False, compare=False,
    )
    _input_warnings: tuple[DocumentWarning, ...] = field(
        default=(), init=False, repr=False,
    )

    def __post_init__(self) -> None:
        self._input_warnings = tuple(self.warnings)
        self._refresh_warnings()

    def _refresh_warnings(self) -> None:
        """Keep source notices and only the currently installed diagnostics."""
        diagnostics = self.scientific.diagnostics(INORGANIC_RESULT_SLOTS + ORGANIC_RESULT_SLOTS)
        self.warnings = tuple(dict.fromkeys((
            *self._input_warnings,
            *(_diagnostic_warning(item) for item in diagnostics),
        )))

    @property
    def display_name(self) -> str:
        """Return the CRAFT-owned label without consulting the legacy projection."""

        override = str(getattr(self.source, "display_name_override", "") or "").strip()
        if override:
            return override
        metadata = getattr(self.structure, "metadata", {})
        for key in ("mineral_name", "common_name", "systematic_name"):
            value = metadata.get(key) if hasattr(metadata, "get") else None
            if isinstance(value, str) and value.strip() not in {"", ".", "?"}:
                return value.strip()
        canonical_name = str(getattr(self.structure, "name", "")).strip()
        source_format = getattr(self.source, "source_format", None)
        if source_format not in {None, "cif"}:
            if canonical_name and canonical_name not in {".", "?"}:
                return canonical_name
        source_path = getattr(self.source, "source_path", None)
        stem = Path(source_path).stem.strip() if source_path else ""
        return stem or canonical_name

    def canonical_structure_identity(self) -> str:
        """Identify the canonical input independently of calculated results."""

        # Canonical CrIStMa structures are immutable; the compatibility display
        # model is mutable and must still be fingerprinted on every call.
        cached = self._canonical_identity_cache
        if (
            cached is not None
            and cached[0] == self.source.source_identity
            and cached[1] is self.structure
        ):
            return cached[2]
        payload = _identity_data(("craft.structure-input:2", self.source.source_identity, self.structure))
        identity = hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()
        if isinstance(self.structure, (CanonicalCrystalStructure, MolecularStructure)):
            self._canonical_identity_cache = (
                self.source.source_identity, self.structure, identity,
            )
        return identity

    def inorganic_presentation(self) -> InorganicPresentation:
        """Return a cached, calculation-free view of installed CrIStMa results."""
        from craft.presentation.inorganic_builder import (
            build_inorganic_presentation,
        )

        result_ids = tuple(
            id(getattr(getattr(self.scientific, name), "result", None))
            for name in INORGANIC_RESULT_SLOTS
        )
        key = (self.canonical_structure_identity(), self.analysis_stage, *result_ids)
        cached = self._inorganic_presentation_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        presentation = build_inorganic_presentation(self)
        self._inorganic_presentation_cache = (key, presentation)
        return presentation

    def organic_presentation(self) -> OrganicPresentation:
        """Return a cached, calculation-free view of installed CrIStMa results."""
        from craft.presentation.organic_builder import (
            build_organic_presentation,
        )

        result_ids = tuple(
            id(getattr(getattr(self.scientific, slot), "result", None))
            for slot in ORGANIC_RESULT_SLOTS
        )
        key = (self.canonical_structure_identity(), self.analysis_stage, *result_ids)
        cached = self._organic_presentation_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        presentation = build_organic_presentation(self)
        self._organic_presentation_cache = (key, presentation)
        return presentation

    def content_identity(self) -> str:
        """Return a deterministic identity for the current analysis snapshot."""
        payload = (
            "craft.analysis-content:2",
            self.source.source_identity,
            self.canonical_structure_identity(),
            self._scientific_identity(),
            tuple(self.hierarchy.polyhedra),
            tuple(self.hierarchy.polyhedron_connections),
            tuple(self.hierarchy.structural_units),
            tuple(self.hierarchy.structural_domains),
            tuple(self.hierarchy.nomenclature),
            tuple(self.hierarchy.blocks),
            tuple(self.hierarchy.connectors),
            self.inorganic_topology,
            self.profile_decision,
        )
        return hashlib.sha256(repr(_identity_data(payload)).encode("utf-8")).hexdigest()

    def _scientific_identity(self) -> str:
        cached = self._scientific_identity_cache
        if cached is not None and cached[0] is self.scientific:
            return cached[1]
        identity = hashlib.sha256(repr(_identity_data(self.scientific)).encode("utf-8")).hexdigest()
        immutable = all(
            slot is None or (
                is_dataclass(slot.result) and type(slot.result).__dataclass_params__.frozen
            )
            for item in fields(self.scientific)
            for slot in (getattr(self.scientific, item.name),)
        )
        self._scientific_identity_cache = (self.scientific, identity) if immutable else None
        return identity

    def scene_data(
        self,
        repeat: tuple[int, int, int] = (1, 1, 1),
        bounds: tuple[tuple[float, float], tuple[float, float], tuple[float, float]] | None = None,
        include_bonds: bool = True,
        complete_boundary: bool = True,
    ):
        """Return cached immutable display geometry for these render settings."""
        from craft.core.scene import build_scene

        normalized_repeat = tuple(int(value) for value in repeat)
        normalized_bounds = (
            tuple((round(float(pair[0]), 6), round(float(pair[1]), 6)) for pair in bounds)
            if bounds is not None
            else tuple((0.0, float(value)) for value in normalized_repeat)
        )
        key = (
            normalized_repeat,
            normalized_bounds,
            bool(include_bonds),
            bool(complete_boundary),
            id(self.contact_presentation),
        )
        cached = self.scene_cache.get(key)
        if cached is not None:
            return cached
        scene = build_scene(
            self.legacy_projection,
            repeat=key[0],
            bounds=key[1],
            include_bonds=key[2],
            complete_boundary=key[3],
            contact_presentation=self.contact_presentation,
        )
        self.scene_cache[key] = scene
        while len(self.scene_cache) > 8:
            self.scene_cache.pop(next(iter(self.scene_cache)))
        return scene

    def inorganic_scene_data(
        self,
        bounds: tuple[
            tuple[float, float], tuple[float, float], tuple[float, float]
        ],
        include_contacts: bool = True,
        complete_boundary: bool = True,
        *,
        include_expanded_grid: bool = False,
    ):
        """Return cached display geometry materialized from native results."""
        from craft.presentation.inorganic_scene import build_inorganic_scene

        normalized_bounds = tuple(
            (round(float(low), 6), round(float(high), 6))
            for low, high in bounds
        )
        key = (
            "native-inorganic",
            normalized_bounds,
            bool(include_contacts),
            bool(complete_boundary),
            bool(include_expanded_grid),
            id(self.inorganic_presentation()),
            tuple(sorted(self.visual.crystal_layers)),
        )
        cached = self.scene_cache.get(key)
        if cached is not None:
            return cached
        scene = build_inorganic_scene(
            self,
            normalized_bounds,
            include_contacts,
            complete_boundary,
            include_expanded_grid=include_expanded_grid,
        )
        from craft.presentation.crystal_layers import build_crystal_layers
        scene = replace(scene, crystal_layers=build_crystal_layers(self, scene))
        self.scene_cache[key] = scene
        while len(self.scene_cache) > 8:
            self.scene_cache.pop(next(iter(self.scene_cache)))
        return scene

    @classmethod
    def from_preview(
        cls,
        loaded: LoadedStructure,
        *,
        legacy_projection: CrystalStructure | None = None,
    ) -> StructureDocument:
        """Create the stable atom-only document used during background analysis."""
        document = cls.from_structure(
            loaded,
            HierarchyReport(),
            legacy_projection=legacy_projection,
        )
        document.inorganic_topology = None
        document.analysis_stage = "parsed"
        return document

    def _install_snapshot_results(
        self,
        request_key: ScientificRequestKey,
        **results: object | None,
    ) -> None:
        """Publish one snapshot atomically, reusing its normalized request key."""

        ready = {}
        for slot, value in results.items():
            if value is None:
                continue
            current = getattr(self.scientific, slot)
            if current is not None and current.result is value and current.request_key == request_key:
                continue
            ready[slot] = ScientificResultSlot(
                request_key=request_key,
                result=value,
                provenance=ScientificResultProvenance(
                    structure_identity=request_key.structure_fingerprint,
                    tool_id=request_key.tool_id,
                    tool_version=request_key.tool_version,
                    configuration=request_key.configuration,
                    result_provenance=getattr(value, "provenance", None),
                ),
            )
        if ready:
            self.scientific = replace(self.scientific, **ready)
            self._refresh_warnings()

    def install_native_inorganic_snapshot(
        self,
        snapshot: NativeInorganicSnapshot,
    ) -> None:
        """Store exact CRiStMa results without projecting new scientific facts."""

        self.install_contact_snapshot(snapshot)

        request_key = ScientificRequestKey.from_mapping(
            structure_fingerprint=self.canonical_structure_identity(),
            tool_id=snapshot.tool_id,
            tool_version=snapshot.tool_version,
            configuration=snapshot.settings.get_config(),
        )
        self._install_snapshot_results(
            request_key,
            polyhedra=snapshot.polyhedra,
            units=snapshot.units,
            unit_graph=snapshot.unit_graph,
            representation=snapshot.representation,
            connectivity=snapshot.connectivity,
            blocks=snapshot.blocks,
            rings=snapshot.rings,
        )

        if snapshot.classification is not None:
            classification_key = ScientificRequestKey.from_mapping(
                structure_fingerprint=self.canonical_structure_identity(),
                tool_id=snapshot.classification.method_id,
                tool_version=snapshot.classification.method_version,
                configuration=snapshot.settings.get_config(),
            )
            self._install_snapshot_results(
                classification_key, inorganic_classification=snapshot.classification,
            )

        self.analysis_stage = snapshot.stage.value
        self._inorganic_presentation_cache = None
        self.scene_cache.clear()
        self.descriptor_cache.clear()
        self.comparison_cache.clear()

    def install_contact_snapshot(self, snapshot: NativeInorganicSnapshot) -> None:
        """Install exact chemistry/contact results without inorganic higher layers."""

        identity = self.canonical_structure_identity()
        self.native_settings = snapshot.settings
        request_key = ScientificRequestKey.from_mapping(
            structure_fingerprint=identity,
            tool_id=snapshot.tool_id,
            tool_version=snapshot.tool_version,
            configuration=snapshot.settings.get_config(),
        )

        chemistry = snapshot.chemistry
        chemistry_key = ScientificRequestKey.from_mapping(
            structure_fingerprint=identity,
            tool_id=chemistry.tool_id,
            tool_version=chemistry.tool_version,
            configuration=chemistry.get_config(),
        )
        self._install_snapshot_results(chemistry_key, chemistry=chemistry)
        self._install_snapshot_results(
            request_key,
            crystal_chemistry=snapshot.contact_result,
        )
        self.profile_decision = resolve_structure_profile(chemistry.classification, self.requested_profile)
        self._inorganic_presentation_cache = None
        if snapshot.contact_result is None:
            return

        from craft.adapters.cristma_contacts_presentation import project_contacts

        if (
            self.contact_presentation is not None
            and self.contact_presentation.scientific_result is snapshot.contact_result
        ):
            return
        self.contact_presentation = project_contacts(snapshot.contact_result)
        for row in self.contact_presentation.rows:
            if row.contact_orbit_id in self.visual.contact_defaults_applied:
                continue
            self.visual.contact_defaults_applied.add(row.contact_orbit_id)
            if not row.initially_visible:
                self.visual.hidden_contact_orbit_ids.add(row.contact_orbit_id)
        self.scene_cache.clear()

    def install_native_organic_snapshot(
        self,
        snapshot: NativeOrganicSnapshot,
        request_key: ScientificRequestKey,
    ) -> bool:
        """Install one exact native stage only for the active scientific request."""

        expected_key = ScientificRequestKey.from_mapping(
            structure_fingerprint=self.canonical_structure_identity(),
            tool_id=snapshot.tool_id,
            tool_version=snapshot.tool_version,
            configuration=snapshot.settings.get_config(),
        )
        if request_key != expected_key:
            return False
        contact_slot = self.scientific.crystal_chemistry
        if (
            not isinstance(contact_slot, ScientificResultSlot)
            or contact_slot.result is not snapshot.contact_result
        ):
            return False

        self.native_organic_settings = snapshot.settings

        self._install_snapshot_results(
            request_key,
            molecular=snapshot.molecular,
            intermolecular=snapshot.intermolecular,
            pi_systems=snapshot.pi_systems,
            pi_stacking=snapshot.pi_stacking,
            ch_pi=snapshot.ch_pi,
            packing=snapshot.packing,
            reticular_precursor=snapshot.reticular_precursor,
            sbu=snapshot.sbu,
            reticular_net=snapshot.reticular_net,
        )

        self.analysis_stage = snapshot.stage.value
        self._organic_presentation_cache = None
        self.scene_cache.clear()
        self.descriptor_cache.clear()
        self.comparison_cache.clear()
        return True

    def begin_reanalysis(self, requested: RequestedProfile) -> None:
        """Return to the responsive atom preview before another profile branch."""
        self.requested_profile = requested
        self.visual.discard_analysis_objects()
        self.knowledge_state = None
        self._discard_analysis()

    def _discard_analysis(self) -> None:
        """Invalidate every view and result derived from the analysis snapshot."""
        self.scientific = self.scientific.invalidate_all()
        self._scientific_identity_cache = None
        self._refresh_warnings()
        self.hierarchy = HierarchyReport()
        self.ring_motifs = None
        self.inorganic_topology = None
        self.contact_presentation = None
        self.profile_decision = None
        self.analysis_stage = "parsed"
        self._inorganic_presentation_cache = None
        self._organic_presentation_cache = None
        self.scene_cache.clear()
        self.descriptor_cache.clear()
        self.comparison_cache.clear()

    def replace_structure(self, loaded: LoadedStructure) -> None:
        """Install a new canonical snapshot and discard results for the old one."""

        from craft.adapters.cristma import build_legacy_projection

        projection = build_legacy_projection(loaded)
        input_warnings = _source_warnings(loaded.source, projection)
        self.visual = VisualizationState()
        self.structure = loaded.structure
        self.source = loaded.source
        self._canonical_identity_cache = None
        self.legacy_projection = projection
        self.id = hashlib.sha1(
            loaded.source.source_identity.encode("utf-8")
        ).hexdigest()[:12]
        self._input_warnings = input_warnings
        self._discard_analysis()
        self.morphology_cache.clear()
        self.morphology_state = None
        self.knowledge_state = None
        self.report_draft = None

    @classmethod
    def from_structure(
        cls,
        loaded: LoadedStructure | CrystalStructure,
        hierarchy: HierarchyReport,
        *,
        legacy_projection: CrystalStructure | None = None,
    ) -> StructureDocument:
        from craft.adapters.cristma import build_legacy_projection

        if isinstance(loaded, CrystalStructure):
            structure = legacy_projection or loaded
            source = StructureSourceContext(
                source_path=Path(loaded.source_path or Path.cwd() / loaded.name).resolve(),
                source_identity=str(loaded.source_path or loaded.name),
                source_format="legacy",
                diagnostics=(),
                source_document=None,
            )
            scientific_structure = loaded
        else:
            structure = legacy_projection or build_legacy_projection(loaded)
            source = loaded.source
            scientific_structure = loaded.structure
        warnings = _source_warnings(source, structure)
        identity = source.source_identity
        document_id = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:12]
        return cls(
            id=document_id,
            structure=scientific_structure,
            source=source,
            legacy_projection=structure,
            hierarchy=hierarchy,
            warnings=warnings,
            inorganic_topology=None,
        )


def load_document(path: str | Path) -> StructureDocument:
    """Load one structure through the same profile route as the UI."""
    from cristma.structure import CrystalStructure as CanonicalCrystalStructure

    from craft.core.structure_io import load_structure_files

    structures = load_structure_files(Path(path))
    if len(structures) != 1:
        raise ValueError(
            f"Expected one structure in {Path(path).name}, found {len(structures)}."
        )
    loaded = structures[0]
    if not isinstance(loaded.structure, CanonicalCrystalStructure):
        raise TypeError("CRiStMa did not return a canonical CrystalStructure")
    document = StructureDocument.from_preview(loaded)
    return analyze_document(document)


def analyze_document(document: StructureDocument) -> StructureDocument:
    """Complete the native analysis using the document's saved request policies."""
    from craft.core.progressive_load import iter_reanalysis_updates

    for update in iter_reanalysis_updates(document, document.requested_profile):
        if update.native_snapshot is not None:
            document.install_native_inorganic_snapshot(update.native_snapshot)
        elif update.native_organic_snapshot is not None:
            snapshot = update.native_organic_snapshot
            key = ScientificRequestKey.from_mapping(
                structure_fingerprint=document.canonical_structure_identity(),
                tool_id=snapshot.tool_id,
                tool_version=snapshot.tool_version,
                configuration=snapshot.settings.get_config(),
            )
            document.install_native_organic_snapshot(snapshot, key)
    return document
