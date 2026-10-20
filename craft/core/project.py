"""Portable CRAFT projects: embedded input and presentation, without result caches."""

from __future__ import annotations

from dataclasses import dataclass, field, fields, is_dataclass
from enum import Enum
import json
import os
from base64 import b64encode, b64decode
from pathlib import Path
from tempfile import NamedTemporaryFile, TemporaryDirectory

import cristma
from cristma.io.cif.document import CifDocument

from craft.analysis.cristma_inorganic import NativeInorganicSettings
from craft.analysis.cristma_organic import NativeOrganicSettings
from craft.analysis.morphology_state import load_morphology_state, save_morphology_state
from craft.analysis.structure_profile import RequestedProfile
from craft.core.collection import StructureCollection
from craft.core.document import StructureDocument, analyze_document
from craft.core.reference_data_warmup import ensure_cristma_reference_data
from craft.core.structure_source import LoadedStructure, StructureSourceContext
from craft.core.visualization import CrystalLayerStyle, VisualizationState
from craft.analysis.reporting.composer import (
    CameraStateRecord, FigureKind, FigureNarrative, LabelMode, ReportDraft,
    ReportFigure, ReportReference, SceneManifest,
)


PROJECT_SUFFIX = ".craft"
_FORMAT = "craft.project"
_VERSION = 1
_MAX_BYTES = 64 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class LoadedProject:
    collection: StructureCollection
    active_document_id: str
    view_settings: dict = field(default_factory=dict)


def _type_name(cls):
    return f"{cls.__module__}.{cls.__qualname__}"


def _state_types():
    """Only application-declared state types can be constructed from a project."""
    allowed = {}

    def visit(value):
        if isinstance(value, Enum):
            allowed[_type_name(type(value))] = type(value)
        elif is_dataclass(value):
            allowed[_type_name(type(value))] = type(value)
            for item in fields(value):
                visit(getattr(value, item.name))
        elif isinstance(value, (tuple, set, frozenset)):
            for item in value:
                visit(item)

    for value in (VisualizationState(), CrystalLayerStyle("#000000"),
                  NativeInorganicSettings(), NativeOrganicSettings()):
        visit(value)
    for cls in (CameraStateRecord, FigureKind, FigureNarrative, LabelMode, ReportDraft,
                ReportFigure, ReportReference, SceneManifest):
        allowed[_type_name(cls)] = cls
    return allowed


_STATE_TYPES = _state_types()


def _encode(value):
    if isinstance(value, bytes):
        return {"$bytes": b64encode(value).decode("ascii")}
    if isinstance(value, Enum):
        return {"$enum": _type_name(type(value)), "value": value.value}
    if is_dataclass(value):
        return {"$record": _type_name(type(value)), "fields": {
            item.name: _encode(getattr(value, item.name)) for item in fields(value)
        }}
    for kind, cls in (("tuple", tuple), ("set", set), ("frozenset", frozenset)):
        if isinstance(value, cls):
            items = sorted(value, key=repr) if kind != "tuple" else value
            return {"$" + kind: [_encode(item) for item in items]}
    if isinstance(value, dict):
        if not all(isinstance(key, str) and not key.startswith("$") for key in value):
            raise ValueError("Project state requires string dictionary keys.")
        return {key: _encode(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ValueError(f"Unsupported project value: {type(value).__name__}")


def _decode(value):
    if not isinstance(value, dict):
        if isinstance(value, list):
            raise ValueError("Unmarked sequence in project state.")
        return value
    if "$bytes" in value:
        if set(value) != {"$bytes"}:
            raise ValueError("Invalid project byte record.")
        return b64decode(value["$bytes"], validate=True)
    for kind, cls in (("tuple", tuple), ("set", set), ("frozenset", frozenset)):
        if "$" + kind in value:
            return cls(_decode(item) for item in value["$" + kind])
    if "$enum" in value or "$record" in value:
        name = value.get("$enum", value.get("$record"))
        cls = _STATE_TYPES.get(name)
        if cls is None:
            raise ValueError(f"Unknown project state type: {name}")
        if "$enum" in value:
            return cls(value["value"])
        raw = value["fields"]
        if not set(raw) <= {item.name for item in fields(cls)}:
            raise ValueError(f"Unknown fields for project state: {name}")
        decoded = {key: _decode(item) for key, item in raw.items()}
        if cls is NativeInorganicSettings and "class_subsystem_revision" not in decoded:
            # Earlier projects identify display layers by the original native
            # quotient. Keep that method so reopening does not orphan colours
            # and visibility when the current default topology improves.
            decoded["class_subsystem_revision"] = 2
        return cls(**decoded)
    return {key: _decode(item) for key, item in value.items()}


def _document_payload(document):
    source = document.source
    original = source.source_document
    text = (cristma.write_cif_document(original) if isinstance(original, CifDocument)
            else getattr(original, "raw_source", None))
    if not isinstance(text, str):
        raise ValueError(f"{document.display_name}: original structural input is unavailable.")
    morphology = None
    if document.morphology_state is not None:
        with TemporaryDirectory(prefix="craft-project-") as folder:
            path = Path(folder) / "morphology.json"
            save_morphology_state(path, document.legacy_projection, document.morphology_state)
            morphology = json.loads(path.read_text(encoding="utf-8"))
    return {
        "id": document.id, "name": document.display_name,
        "structure_id": document.structure.id,
        "source": {"path": str(source.source_path), "identity": source.source_identity,
                   "format": source.source_format, "text": text,
                   "parser_name": getattr(original, "source_name", str(source.source_path))},
        "requested_profile": document.requested_profile.value,
        "inorganic_settings": _encode(document.native_settings),
        "organic_settings": _encode(document.native_organic_settings),
        "visual": _encode(document.visual), "morphology": morphology,
        "report_draft": _encode(document.report_draft),
    }


def save_project(path, collection: StructureCollection, active_document_id: str, *, view_settings=None) -> None:
    if not collection.order or active_document_id not in collection.documents:
        raise ValueError("Open a structure before saving a project.")
    payload = {
        "format": _FORMAT, "version": _VERSION,
        "active_document_id": active_document_id,
        "documents": [_document_payload(collection.documents[key]) for key in collection.order],
        "max_compared": collection.max_compared, "compared_ids": collection.compared_ids,
        "visual_slots": collection.visual_slots,
        "view_settings": view_settings or {},
    }
    text = json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2) + "\n"
    if len(text.encode("utf-8")) > _MAX_BYTES:
        raise ValueError("Project exceeds the 64 MiB size limit.")
    target = Path(path)
    temporary = None
    try:
        with NamedTemporaryFile(mode="w", encoding="utf-8", dir=target.parent,
                                prefix=".craft-project-", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def load_project(path) -> LoadedProject:
    source_path = Path(path)
    if source_path.stat().st_size > _MAX_BYTES:
        raise ValueError("Project exceeds the 64 MiB size limit.")
    payload = json.loads(source_path.read_text(encoding="utf-8"))
    if payload.get("format") != _FORMAT or payload.get("version") != _VERSION:
        raise ValueError("Unsupported CRAFT project format or version.")
    collection = StructureCollection(max_compared=int(payload.get("max_compared", 2)))
    ensure_cristma_reference_data()
    for raw in payload["documents"]:
        source = raw["source"]
        result = cristma.read_text(source["text"], format=source["format"],
                                   source_name=source["parser_name"])
        if not result.ok:
            raise ValueError(f"Cannot read embedded structure: {raw['name']}")
        matches = [item for item in result.structures if item.id == raw["structure_id"]]
        if len(matches) != 1:
            raise ValueError(f"Embedded structure identity has changed: {raw['name']}")
        context = StructureSourceContext(Path(source["path"]), source["identity"], source["format"],
                                         tuple(result.diagnostics), result.document, raw["name"])
        document = StructureDocument.from_preview(LoadedStructure(matches[0], context))
        document.id = raw["id"]
        if document.id in collection.documents:
            raise ValueError("Duplicate document identity in CRAFT project.")
        for key, cls, attribute in (
            ("inorganic_settings", NativeInorganicSettings, "native_settings"),
            ("organic_settings", NativeOrganicSettings, "native_organic_settings"),
            ("visual", VisualizationState, "visual"),
        ):
            value = _decode(raw[key])
            if not isinstance(value, cls):
                raise ValueError(f"Invalid project {key}.")
            setattr(document, attribute, value)
        document.requested_profile = RequestedProfile(raw["requested_profile"])
        # Installing progressive results resets analysis-dependent visibility;
        # restore the saved presentation only after the native analysis finishes.
        visual = document.visual
        document.visual = VisualizationState()
        analyze_document(document)
        document.visual = visual
        draft = _decode(raw.get("report_draft"))
        if draft is not None and not isinstance(draft, ReportDraft):
            raise ValueError("Invalid project report draft.")
        document.report_draft = draft
        if raw.get("morphology") is not None:
            with TemporaryDirectory(prefix="craft-project-") as folder:
                morphology = Path(folder) / "morphology.json"
                morphology.write_text(json.dumps(raw["morphology"]), encoding="utf-8")
                loaded = load_morphology_state(morphology, document.legacy_projection)
                if not loaded.compatible:
                    raise ValueError(loaded.message)
                document.morphology_state = loaded.state
        collection.add(document)
    active = payload["active_document_id"]
    if active not in collection.documents:
        raise ValueError("Project has no active structure.")
    for key in payload.get("compared_ids", ()):
        collection.set_compared(key, True)
    for slot, key in payload.get("visual_slots", {}).items():
        if slot not in {"A", "B"}:
            raise ValueError("Invalid comparison slot in project.")
        collection.assign_visual(slot, key)
    return LoadedProject(collection, active, payload.get("view_settings", {}))
