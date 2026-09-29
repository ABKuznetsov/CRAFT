from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from cristma.diagnostics import Severity
from cristma.chemistry import ChemicalDomain
from cristma.structure import Structure

from craft.analysis.hierarchy import HierarchyLevel, HierarchyReport
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
)
from craft.analysis.structural_motifs import StructuralMotifPresentation
from craft.analysis.reporting.composer import ReportDraft
from craft.core.model import CrystalStructure
from craft.core.scientific_cache import (
    ScientificExecutionState,
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


@dataclass(slots=True)
class VisualizationState:
    level: HierarchyLevel = HierarchyLevel.SITES
    organic_active_view: str | None = None
    organic_active_object_id: str | None = None
    organic_view_user_selected: bool = False
    hidden_atom_indices: set[int] = field(default_factory=set)
    hidden_atom_orbit_ids: set[str] = field(default_factory=set)
    hidden_atom_instance_keys: set[tuple[str, tuple[int, int, int]]] = field(
        default_factory=set
    )
    hidden_bond_orbits: set[str] = field(default_factory=set)
    hidden_bond_families: set[tuple[str, str]] = field(default_factory=set)
    hidden_contact_orbit_ids: set[str] = field(default_factory=set)
    contact_orbit_colors: dict[str, str] = field(default_factory=dict)
    contact_defaults_applied: set[str] = field(default_factory=set)
    hidden_polyhedron_ids: set[str] = field(default_factory=set)
    hidden_polyhedron_orbit_ids: set[str] = field(default_factory=set)
    hidden_unit_ids: set[str] = field(default_factory=set)
    hidden_block_ids: set[str] = field(default_factory=set)
    hidden_connector_ids: set[str] = field(default_factory=set)
    hidden_topology_family_ids: set[str] = field(default_factory=set)
    atom_orbit_colors: dict[str, str] = field(default_factory=dict)
    polyhedron_orbit_colors: dict[str, str] = field(default_factory=dict)
    shown_unit_ids: set[str] = field(default_factory=set)
    unit_auto_hidden_atoms: dict[str, set[int]] = field(default_factory=dict)
    unit_auto_hidden_polyhedra: dict[str, set[str]] = field(default_factory=dict)
    block_auto_hidden_atom_ids: dict[str, frozenset[str]] = field(default_factory=dict)
    block_auto_hidden_polyhedron_orbit_ids: dict[str, frozenset[str]] = field(
        default_factory=dict
    )
    shown_ring_ids: set[str] = field(default_factory=set)
    shown_block_ids: set[str] = field(default_factory=set)
    unit_colors: dict[str, str] = field(default_factory=dict)
    block_colors: dict[str, str] = field(default_factory=dict)
    ring_scope_colors: dict[str, str] = field(default_factory=dict)


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

        payload = (self.source.source_identity, self.structure)
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()

    def inorganic_presentation(self) -> InorganicPresentation:
        """Return a cached, calculation-free view of installed CrIStMa results."""
        from craft.presentation.inorganic_builder import (
            build_inorganic_presentation,
        )

        result_ids = tuple(
            id(getattr(slot, "result", None))
            for slot in (
                self.scientific.chemistry,
                self.scientific.crystal_chemistry,
                self.scientific.polyhedra,
                self.scientific.units,
                self.scientific.unit_graph,
                self.scientific.representation,
                self.scientific.connectivity,
                self.scientific.blocks,
                self.scientific.rings,
            )
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
            for slot in (
                "molecular",
                "intermolecular",
                "pi_systems",
                "pi_stacking",
                "ch_pi",
                "packing",
                "reticular_precursor",
                "sbu",
                "reticular_net",
            )
        )
        key = (self.canonical_structure_identity(), self.analysis_stage, *result_ids)
        cached = self._organic_presentation_cache
        if cached is not None and cached[0] == key:
            return cached[1]
        presentation = build_organic_presentation(self)
        self._organic_presentation_cache = (key, presentation)
        return presentation

    def begin_scientific_request(
        self,
        slot: str,
        request_key: ScientificRequestKey,
    ) -> None:
        self.scientific = self.scientific.with_result(
            slot,
            ScientificResultSlot(
                request_key=request_key,
                execution=ScientificExecutionState.RUNNING,
            ),
        )

    def install_scientific_result(
        self,
        slot: str,
        request_key: ScientificRequestKey,
        result: object,
        *,
        provenance: ScientificResultProvenance | None = None,
    ) -> bool:
        current = getattr(self.scientific, slot, None)
        if not isinstance(current, ScientificResultSlot) or current.request_key != request_key:
            return False
        self.scientific = self.scientific.with_result(
            slot,
            ScientificResultSlot(
                request_key=request_key,
                execution=ScientificExecutionState.READY,
                result=result,
                provenance=provenance,
            ),
        )
        self._inorganic_presentation_cache = None
        return True

    def fail_scientific_request(
        self,
        slot: str,
        request_key: ScientificRequestKey,
        error_message: str,
    ) -> bool:
        current = getattr(self.scientific, slot, None)
        if not isinstance(current, ScientificResultSlot) or current.request_key != request_key:
            return False
        self.scientific = self.scientific.with_result(
            slot,
            ScientificResultSlot(
                request_key=request_key,
                execution=ScientificExecutionState.FAILED,
                error_message=str(error_message),
            ),
        )
        return True

    def content_identity(self) -> str:
        """Return a deterministic identity for the current analysis snapshot."""
        payload = (
            self.source.source_identity,
            self.structure,
            self.scientific,
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
        return hashlib.sha256(repr(payload).encode("utf-8")).hexdigest()

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

    def install_native_inorganic_snapshot(
        self,
        snapshot: NativeInorganicSnapshot,
    ) -> None:
        """Store exact CRiStMa results without projecting new scientific facts."""

        self.install_contact_snapshot(snapshot)

        identity = self.canonical_structure_identity()

        def install(slot: str, value: object | None) -> None:
            if value is None:
                return
            request_key = ScientificRequestKey.from_mapping(
                structure_fingerprint=identity,
                tool_id=snapshot.tool_id,
                tool_version=snapshot.tool_version,
                configuration=snapshot.settings.get_config(),
            )
            provenance = ScientificResultProvenance.from_mapping(
                structure_identity=identity,
                tool_id=snapshot.tool_id,
                tool_version=snapshot.tool_version,
                configuration=snapshot.settings.get_config(),
                result_provenance=getattr(value, "provenance", None),
            )
            ready = ScientificResultSlot(
                request_key=request_key,
                execution=ScientificExecutionState.READY,
                result=value,
                provenance=provenance,
            )
            self.scientific = self.scientific.with_result(slot, ready)

        install("polyhedra", snapshot.polyhedra)
        install("units", snapshot.units)
        install("unit_graph", snapshot.unit_graph)
        install("representation", snapshot.representation)
        install("connectivity", snapshot.connectivity)
        install("blocks", snapshot.blocks)
        install("rings", snapshot.rings)

        self.analysis_stage = snapshot.stage.value
        self._inorganic_presentation_cache = None
        presentation = self.inorganic_presentation()
        by_code = {item.code: item for item in self.warnings}
        for index, diagnostic in enumerate(presentation.diagnostics):
            code = str(getattr(diagnostic, "code", f"cristma.diagnostic.{index}"))
            message = str(getattr(diagnostic, "message", diagnostic))
            by_code[code] = DocumentWarning(code, message)
        self.warnings = tuple(by_code.values())
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

        def install(slot: str, value: object | None) -> None:
            if value is None:
                return
            provenance = ScientificResultProvenance.from_mapping(
                structure_identity=identity,
                tool_id=snapshot.tool_id,
                tool_version=snapshot.tool_version,
                configuration=snapshot.settings.get_config(),
                result_provenance=getattr(value, "provenance", None),
            )
            self.scientific = self.scientific.with_result(
                slot,
                ScientificResultSlot(
                    request_key=request_key,
                    execution=ScientificExecutionState.READY,
                    result=value,
                    provenance=provenance,
                ),
            )

        install("chemistry", snapshot.chemistry)
        install("crystal_chemistry", snapshot.contact_result)
        classification = snapshot.chemistry.classification
        automatic = {
            ChemicalDomain.ORGANIC: ResolvedProfile.MOLECULAR,
            ChemicalDomain.METAL_ORGANIC: ResolvedProfile.RETICULAR,
        }.get(classification.domain, ResolvedProfile.INORGANIC)
        resolved = automatic
        if self.requested_profile is RequestedProfile.INORGANIC:
            resolved = ResolvedProfile.INORGANIC
        elif self.requested_profile is RequestedProfile.ORGANIC_METAL_ORGANIC:
            resolved = (
                automatic
                if automatic is ResolvedProfile.RETICULAR
                else ResolvedProfile.MOLECULAR
            )
        reasons = tuple(
            str(getattr(item, "message", item))
            for item in classification.evidence
        ) or (f"CrIStMa family: {classification.primary_family}",)
        warning_messages = tuple(
            str(getattr(item, "message", item))
            for item in classification.diagnostics
        )
        self.profile_decision = ProfileDecision(
            resolved,
            float(classification.confidence),
            reasons,
            warning_messages,
            method_version=(
                f"{classification.method_id}:{classification.method_version}"
            ),
        )
        self._inorganic_presentation_cache = None
        if snapshot.contact_result is None:
            return

        from craft.adapters.cristma_contacts_presentation import project_contacts

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
        """Install one exact b10 stage only for the active scientific request."""

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

        def install(slot: str, value: object | None) -> None:
            if value is None:
                return
            provenance = ScientificResultProvenance.from_mapping(
                structure_identity=request_key.structure_fingerprint,
                tool_id=snapshot.tool_id,
                tool_version=snapshot.tool_version,
                configuration=snapshot.settings.get_config(),
                result_provenance=getattr(value, "provenance", None),
            )
            self.scientific = self.scientific.with_result(
                slot,
                ScientificResultSlot(
                    request_key=request_key,
                    execution=ScientificExecutionState.READY,
                    result=value,
                    provenance=provenance,
                ),
            )

        install("molecular", snapshot.molecular)
        install("intermolecular", snapshot.intermolecular)
        install("pi_systems", snapshot.pi_systems)
        install("pi_stacking", snapshot.pi_stacking)
        install("ch_pi", snapshot.ch_pi)
        install("packing", snapshot.packing)
        install("reticular_precursor", snapshot.reticular_precursor)
        install("sbu", snapshot.sbu)
        install("reticular_net", snapshot.reticular_net)

        self.analysis_stage = snapshot.stage.value
        self._organic_presentation_cache = None
        self.scene_cache.clear()
        self.descriptor_cache.clear()
        self.comparison_cache.clear()
        self.report_draft = None
        return True

    def begin_reanalysis(self, requested: RequestedProfile) -> None:
        """Return to the responsive atom preview before another profile branch."""
        self.requested_profile = requested
        self.hierarchy = HierarchyReport()
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

        self.structure = loaded.structure
        self.source = loaded.source
        self.legacy_projection = build_legacy_projection(loaded)
        self.id = hashlib.sha1(
            loaded.source.source_identity.encode("utf-8")
        ).hexdigest()[:12]
        self.scientific = self.scientific.invalidate_all()
        self.contact_presentation = None
        self.hierarchy = HierarchyReport()
        self.inorganic_topology = None
        self.profile_decision = None
        self.analysis_stage = "parsed"
        self._inorganic_presentation_cache = None
        self._organic_presentation_cache = None
        self.scene_cache.clear()
        self.descriptor_cache.clear()
        self.comparison_cache.clear()
        self.morphology_cache.clear()

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
        fatal = tuple(
            diagnostic
            for diagnostic in source.diagnostics
            if diagnostic.severity is Severity.ERROR
        )
        if fatal:
            codes = ", ".join(item.code for item in fatal)
            raise ValueError(f"Cannot create a document from a fatal source diagnostic: {codes}")
        source_warnings: list[DocumentWarning] = []
        seen: set[tuple[str, str, str]] = set()
        for diagnostic in source.diagnostics:
            key = (diagnostic.code, diagnostic.message, diagnostic.severity.value)
            if key in seen:
                continue
            seen.add(key)
            source_warnings.append(
                DocumentWarning(
                    diagnostic.code,
                    diagnostic.message,
                    diagnostic.severity.value,
                )
            )
        local_warnings = tuple(
            DocumentWarning(
                "occupancy-out-of-range",
                f"{site.label}: reported occupancy {site.reported_occupancy:g} is outside 0–1.",
            )
            for site in structure.asymmetric_sites
            if site.occupancy_warning
        )
        warnings = (*source_warnings, *local_warnings)
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
    """Load one structure and install the native CRiStMa inorganic results."""
    from cristma.structure import CrystalStructure as CanonicalCrystalStructure

    from craft.analysis.cristma_inorganic import iter_analyze_inorganic
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
    for snapshot in iter_analyze_inorganic(loaded.structure):
        document.install_native_inorganic_snapshot(snapshot)
    return document
