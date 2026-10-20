"""Translate CRAFT interpretation policies into explicit CrIStMa inputs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from cristma.chemistry import (
    CandidateInteraction, ChemicalEvidence, Composition, CompositionGrammar,
    DecompositionMode, GrammarOperation, InteractionLayer, InteractionPriority,
)
from cristma.reference_data import ReferenceData

from craft.analysis.chemical_rules import chemical_rules

if TYPE_CHECKING:
    from cristma.chemistry import ChemicalClassification


def build_interaction_requests(
    composition: Composition, classification: ChemicalClassification,
) -> CompositionGrammar:
    """Select pairs and roles in CRAFT; leave periodic geometry to CrIStMa."""
    rules = chemical_rules()
    elements = frozenset(composition.elements)
    family = classification.primary_family
    evidence = (ChemicalEvidence(
        "craft.chemistry.interaction_requests",
        f"CRAFT contact search for {family or 'unresolved composition'}.",
        tuple(sorted(elements)), (rules["id"],),
    ),)
    template_id = rules["family_templates"].get(family)
    if family == "inorganic.carbide":
        others = elements - {"C"}
        if others and others <= frozenset(rules["interaction_elements"]["covalent_carbide_formers"]):
            template_id = "covalent_network"
    template = rules["templates"].get(template_id)
    records = template["interactions"] if template is not None else ()
    element_sets = rules["interaction_elements"]
    selector_names = {record[key] for record in records for key in ("first", "second", "centres", "ligands")}
    fixed = {name: elements & frozenset(element_sets[name]) for name in selector_names if name in element_sets}
    if "oxyanion_class_formers" in selector_names:
        from craft.analysis.native_group_rules import class_rules
        fixed["oxyanion_class_formers"] = elements & frozenset(rule.centre for rule in class_rules())
    explicitly_selected = frozenset().union(*fixed.values())
    explicit_centres = frozenset().union(*(
        fixed.get(record["centres"], frozenset()) for record in records
    ))
    reference = ReferenceData.default()
    # A halogen can be a terminal anion or an oxo-centre. Request both roles;
    # its presence in a formula alone must not remove halide coordination.
    explicit_centres -= reference.chemical.element_set("halogens")
    metals = frozenset(symbol for symbol in elements if reference.elements.by_symbol(symbol).is_metal)

    def select(name: str) -> frozenset[str]:
        if name == "all_elements":
            return elements
        if name == "remaining_elements":
            return elements - explicitly_selected
        if name == "remaining_electropositive_elements":
            return (elements - explicitly_selected) & (metals | {"H"})
        if name == "remaining_anion_elements":
            # Elements already assigned as oxyanion centres are not additional
            # ligands of the surrounding cations. Oxygen and terminal anions
            # remain available; molecular nonmetals use their own selector.
            return elements - metals - explicit_centres
        if name == "nonmetal_elements":
            return elements - metals
        if name == "metal_elements":
            return metals
        return fixed[name]

    interactions = []
    for record in records:
        first, second, centres, ligands = (
            tuple(sorted(select(record[key]))) for key in ("first", "second", "centres", "ligands")
        )
        if not first or not second or not centres or not ligands:
            continue
        operation = GrammarOperation(record["operation"])
        layer = InteractionLayer(record["layer"])
        priority = InteractionPriority(record["priority"])
        if record.get("expand") == "distinct_unordered_pairs":
            symbols = sorted(set(first) | set(second))
            for index, left in enumerate(symbols):
                for right in symbols[index + 1:]:
                    interactions.append(CandidateInteraction(
                        (left,), (right,), operation, layer, priority, (left,), (right,), evidence,
                    ))
        else:
            interactions.append(CandidateInteraction(
                first, second, operation, layer, priority, centres, ligands, evidence,
            ))
    return CompositionGrammar(
        mode=DecompositionMode(template["mode"]) if template is not None else DecompositionMode.UNRESOLVED,
        candidate_interactions=tuple(interactions), confidence=classification.confidence,
        evidence=evidence, diagnostics=classification.diagnostics,
        reference_version=f"{rules['id']}:{rules['version']}:{rules['sha256']}",
        method_id="craft.interaction_requests", method_version="1",
    )
