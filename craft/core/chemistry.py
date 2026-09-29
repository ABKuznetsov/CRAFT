from __future__ import annotations

import colorsys
import math
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cristma.reference_data import ReferenceData

if TYPE_CHECKING:
    from craft.core.model import AtomSite


@dataclass(frozen=True, slots=True)
class RadiusEstimate:
    value: float
    method: str
    estimated: bool = False


def _all_element_radii() -> tuple[dict[str, float], frozenset[str]]:
    reference = ReferenceData.default()
    defaults = {
        record.symbol: float(record.value)
        for record in reference.covalent_radii.records
        if record.is_default and float(record.value) > 0.0
    }
    radii: dict[str, float] = {}
    estimated: set[str] = set()
    for element in reference.elements.records:
        radius = defaults.get(element.symbol)
        if radius is None:
            radius = 1.0
            estimated.add(element.symbol)
        radii[element.symbol] = radius
    radii["Al/Si"] = (radii["Al"] + radii["Si"]) / 2.0
    return radii, frozenset(estimated)


COVALENT_RADII, ESTIMATED_RADIUS_ELEMENTS = _all_element_radii()


def site_elements(site: "AtomSite") -> tuple[str, ...]:
    """Return occupied component symbols in their crystallographic order."""
    return tuple(
        dict.fromkeys(
            component.element
            for component in site.components
            if math.isfinite(float(component.occupancy)) and component.occupancy > 0.0
        )
    )


def site_radius(site: "AtomSite") -> RadiusEstimate:
    """Return a component-aware fallback radius without treating `Na/Li` as an element."""
    occupied = [
        component
        for component in site.components
        if math.isfinite(float(component.occupancy)) and component.occupancy > 0.0
    ]
    total = math.fsum(float(component.occupancy) for component in occupied)
    if total <= 0.0:
        value = float(COVALENT_RADII.get(site.element, 1.0))
        return RadiusEstimate(value, "empty-site-fallback", site.element not in COVALENT_RADII)
    value = math.fsum(
        COVALENT_RADII.get(component.element, 1.0) * float(component.occupancy)
        for component in occupied
    ) / total
    estimated = any(
        component.element in ESTIMATED_RADIUS_ELEMENTS or component.element not in COVALENT_RADII
        for component in occupied
    )
    method = "occupancy-weighted-covalent" if len(occupied) > 1 else "covalent"
    return RadiusEstimate(float(value), method, estimated)


def _generated_colour(atomic_number: int) -> str:
    hue = ((atomic_number * 137.507764) % 360.0) / 360.0
    saturation = 0.52 + 0.08 * (atomic_number % 3)
    lightness = 0.55 + 0.04 * (atomic_number % 2)
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return f"#{round(red * 255):02x}{round(green * 255):02x}{round(blue * 255):02x}"


ELEMENT_COLORS = {
    record.symbol: _generated_colour(record.atomic_number)
    for record in ReferenceData.default().elements.records
}
ELEMENT_COLORS.update(
    {
        "H": "#e8edf2", "Li": "#cc80ff", "B": "#39bd2f", "C": "#4c5561",
        "N": "#4169e1", "O": "#f52218", "F": "#66d17a", "Na": "#9c6ade",
        "Mg": "#62c370", "Al": "#aeb8c4", "Si": "#e6b655", "P": "#ff8a3d",
        "S": "#f4df4e", "Cl": "#4bd36b", "K": "#6940df", "Ca": "#55b7e8",
        "Ti": "#9da7b5", "Cr": "#8f66ad", "Mn": "#b175c8", "Fe": "#c96b3b",
        "Co": "#e17076", "Ni": "#6ab07c", "Cu": "#c57d38", "Zn": "#8297ce",
        "Zr": "#63c7c3", "Mo": "#6d9bc3", "Sr": "#5bdc32", "Y": "#f0642e",
        "Tb": "#f05a28", "Dy": "#f05a28", "Ag": "#c7d0da", "Ba": "#45b39d",
        "W": "#547aa5", "Au": "#e5c14f", "Pb": "#7e8997",
    }
)
ELEMENT_COLORS["Al/Si"] = "#c9b788"


def site_colour(site: "AtomSite") -> str:
    """Blend occupied component colours without interpreting `Na/Li` as an element."""
    occupied = [
        component
        for component in site.components
        if math.isfinite(float(component.occupancy)) and component.occupancy > 0.0
    ]
    total = math.fsum(float(component.occupancy) for component in occupied)
    if total <= 0.0:
        return ELEMENT_COLORS.get(site.element, "#aab4c0")
    channels = []
    for offset in (1, 3, 5):
        value = math.fsum(
            int(ELEMENT_COLORS.get(component.element, "#aab4c0")[offset : offset + 2], 16)
            * float(component.occupancy)
            for component in occupied
        ) / total
        channels.append(round(value))
    return "#" + "".join(f"{value:02x}" for value in channels)


__all__ = [
    "COVALENT_RADII",
    "ELEMENT_COLORS",
    "ESTIMATED_RADIUS_ELEMENTS",
    "RadiusEstimate",
    "site_elements",
    "site_colour",
    "site_radius",
]
