"""Proveniência de um release retido, obtida pelo serviço a partir da cadeia E2 (plano §3.2).

``CatalogProvenance`` nunca é aceito como flag do chamador: o serviço de adoção o
calcula conferindo recibo de publicação, candidato, intenção, revisão, aprovação e
validação na mesma autoridade. ``unverified_package`` é o padrão de um pacote íntegro
sem cadeia; ``published_local`` exige cadeia completa e conteúdo ``curated``;
``synthetic_test_published`` exige cadeia completa, conteúdo ``synthetic_fixture`` e
banco de propósito ``synthetic_test``. A identidade dos atores continua
``unverified_local``: a cadeia comprova o que a instalação gravou, não quem agiu.
"""

from typing import Literal, Self

from pydantic import Field, StrictInt, model_validator

from src.domain_catalog.contracts import CatalogReleaseRef, ContractModel
from src.domain_catalog.models import LocalId, Sha256Hex
from src.domain_catalog.package import ContentOrigin

ProvenanceState = Literal["unverified_package", "published_local", "synthetic_test_published"]
PUBLISHED_STATES: frozenset[str] = frozenset({"published_local", "synthetic_test_published"})


class CatalogProvenance(ContractModel):
    """Estatuto verificado do release e a cadeia histórica exata que o sustenta."""

    schema_version: Literal[1] = 1
    state: ProvenanceState
    catalog: CatalogReleaseRef
    content_origin: ContentOrigin
    store_purpose: Literal["operational", "synthetic_test"]
    receipt_id: LocalId | None = None
    receipt_sha256: Sha256Hex | None = None
    candidate_id: LocalId | None = None
    intent_id: LocalId | None = None
    draft_id: LocalId | None = None
    revision: StrictInt | None = Field(default=None, ge=1)
    content_sha256: Sha256Hex | None = None
    approval_id: LocalId | None = None
    identity_assurance: Literal["unverified_local"] = "unverified_local"

    @model_validator(mode="after")
    def _coherent(self) -> Self:
        """Estado publicado exige a cadeia inteira; pacote sem cadeia não carrega elos."""
        chain = (
            self.receipt_id,
            self.receipt_sha256,
            self.candidate_id,
            self.intent_id,
            self.draft_id,
            self.revision,
            self.content_sha256,
            self.approval_id,
        )
        if self.state == "unverified_package":
            if any(item is not None for item in chain):
                raise ValueError("pacote não verificado não carrega elos de publicação")
            return self
        if any(item is None for item in chain):
            raise ValueError(f"{self.state} exige a cadeia de publicação completa")
        if self.state == "published_local" and self.content_origin != "curated":
            raise ValueError("published_local exige conteúdo curated")
        if self.state == "synthetic_test_published" and (
            self.content_origin != "synthetic_fixture" or self.store_purpose != "synthetic_test"
        ):
            raise ValueError(
                "synthetic_test_published exige fixture sintética em banco synthetic_test"
            )
        return self

    @property
    def published(self) -> bool:
        """Se a cadeia E2 foi conferida (local ou sintética de teste)."""
        return self.state in PUBLISHED_STATES
