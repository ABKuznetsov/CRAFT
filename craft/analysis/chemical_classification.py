"""Native CrIStMa classification with explicit CRAFT contact-request policy.

The native result is retained intact. CRAFT selects calculator requests and
presentation routes; it does not infer another composition classification.
"""

from __future__ import annotations

from dataclasses import dataclass

from cristma.chemistry import ChemistryAnalyzer, ChemistryResult, Composition, CompositionGrammar

from craft.analysis.chemical_rules import chemical_rules_config


@dataclass(frozen=True, slots=True)
class CompositionAnalysis:
    native_result: ChemistryResult
    grammar: CompositionGrammar
    rules_configuration: tuple[tuple[str, str], ...]
    tool_id: str = "cristma.chemistry"
    tool_version: str = "2"

    @property
    def composition(self):
        return self.native_result.composition

    @property
    def classification(self):
        return self.native_result.classification

    @property
    def diagnostics(self):
        return self.classification.diagnostics + self.grammar.diagnostics

    def get_config(self) -> dict[str, str]:
        return dict(self.rules_configuration)


def analyze_composition(composition: Composition) -> CompositionAnalysis:
    from craft.analysis.interaction_requests import build_interaction_requests

    native = ChemistryAnalyzer().analyze(composition)
    return CompositionAnalysis(
        native,
        build_interaction_requests(native.composition, native.classification),
        tuple(sorted(chemical_rules_config().items())),
        tool_version=native.classification.method_version,
    )
