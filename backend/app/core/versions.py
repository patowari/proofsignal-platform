"""Version stamps for everything that can change a verification result.

Every completed verification records these so a past result stays reproducible
and explainable after the system moves on. Bumping any of these is a deliberate
act: see docs/SCORING.md and docs/ROADMAP.md.
"""

from __future__ import annotations

from typing import Final

#: Pipeline stage sequence and orchestration semantics.
PIPELINE_VERSION: Final[str] = "1.0.0"

#: Deterministic scoring formula. Documented in docs/SCORING.md.
SCORING_VERSION: Final[str] = "1.0.0"

#: Retrieval strategy: providers, hybrid merge, ranking, clustering.
RETRIEVAL_VERSION: Final[str] = "1.0.0"

#: Prompt templates used for claim extraction and evidence interpretation.
PROMPT_VERSION: Final[str] = "1.0.0"

#: Claim-extraction contract (schema + decomposition rules).
CLAIM_EXTRACTION_VERSION: Final[str] = "1.0.0"

#: Evidence-classification contract.
CLASSIFIER_VERSION: Final[str] = "1.0.0"

#: API surface version, exposed in health output.
API_VERSION: Final[str] = "1.0.0"
