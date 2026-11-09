"""Contexto de ator local declarado: porta do catálogo para o M6 (E2).

O MVP não tem login nem contas (D6-01; decisão do curador responsável de 13/10/2026). O catálogo
não cria identidade nem autentica ninguém: depende de um contexto criado e resgatado
pelo backend (M6), que os comandos referenciam por ``actor_context_id``, nunca por um
objeto de ator vindo da interface. A forma estrutural abaixo é a **proposta do M1**
para alinhamento com o M6 (``docs/catalogo/integracoes-pendentes.md``), ainda não
acordada; o ``LocalActorContext`` do plano M6 a satisfaria sem DTO concorrente.

Nome declarado é "identificação informada": não é controle de acesso nem prova de
autoria. O tipo de ator (pessoa, assistente, serviço) é atribuído pelo backend e
sustenta as regras desta etapa: assistente e serviço nunca aprovam nem publicam, e
decisões curatoriais exigem responsável declarado. A separação de funções entre
pessoas diferentes não é aplicada, porque não foi acordada (plano M1 §4.1).
"""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Annotated, Literal, Protocol, runtime_checkable

from pydantic import StringConstraints, ValidationError

from src.domain_catalog.contracts import ContractModel
from src.domain_catalog.curation_errors import ActorContextError, ActorNotAllowedError
from src.domain_catalog.models import NonEmptyText
from src.domain_catalog.package import UtcTimestamp

ActorKind = Literal["human", "assistant", "service"]
"""Origem do comando, atribuída pelo backend: pessoa, assistente (LLM) ou serviço."""

IdentityAssurance = Literal["unverified_local"]
"""Única garantia do MVP: identificação local informada, sem verificação."""

DeclaredName = Annotated[str, StringConstraints(pattern=r"\S")]
"""Nome informado; texto só com espaços não é declaração."""


@runtime_checkable
class ActorContext(Protocol):
    """Forma estrutural do contexto de ator local (proposta M1 → M6, somente leitura)."""

    @property
    def actor_context_id(self) -> str:
        """ID do contexto, gerado pelo backend."""
        ...

    @property
    def installation_id(self) -> str:
        """Instalação local que registrou o contexto."""
        ...

    @property
    def session_id(self) -> str:
        """Sessão da aplicação em que o contexto foi registrado."""
        ...

    @property
    def actor_kind(self) -> str:
        """``human``, ``assistant`` ou ``service``, atribuído pelo backend."""
        ...

    @property
    def declared_name(self) -> str | None:
        """Identificação informada; ``None`` quando ninguém se identificou."""
        ...

    @property
    def identity_assurance(self) -> str:
        """Sempre ``unverified_local`` no MVP."""
        ...

    @property
    def registered_at_utc(self) -> str:
        """Instante UTC do registro do contexto."""
        ...


class ActorContextResolver(Protocol):
    """Resgata no backend o contexto referenciado por um comando (porta para o M6)."""

    def resolve(self, actor_context_id: str) -> ActorContext | None:
        """Contexto registrado com esse ID, ou ``None`` se não existir."""
        ...


class ActorSnapshot(ContractModel):
    """Cópia validada do contexto, gravada em eventos, revisões e recibos."""

    actor_context_id: NonEmptyText
    installation_id: NonEmptyText
    session_id: NonEmptyText
    actor_kind: ActorKind
    declared_name: DeclaredName | None
    identity_assurance: IdentityAssurance
    registered_at_utc: UtcTimestamp

    @property
    def responsible_label(self) -> str:
        """Texto para relatórios: sempre diz que a identificação não é autenticada."""
        if self.declared_name is None:
            return "operador local não identificado (não autenticado)"
        return f"identificação informada: {self.declared_name} (não autenticada)"


_CONTEXT_FIELDS: tuple[str, ...] = tuple(ActorSnapshot.model_fields)


def snapshot_actor(context: ActorContext) -> ActorSnapshot:
    """Copia e valida o contexto; recusa garantia, tipo ou instante fora do contrato.

    O catálogo nunca promove a garantia: qualquer valor diferente de
    ``unverified_local`` é recusado, inclusive ``authenticated``.
    """
    data: dict[str, object] = {}
    for name in _CONTEXT_FIELDS:
        try:
            data[name] = getattr(context, name)
        except AttributeError as exc:
            raise ActorContextError(f"contexto de ator sem o campo {name}") from exc
    try:
        return ActorSnapshot.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
            for error in exc.errors()
        )
        raise ActorContextError(f"contexto de ator inválido: {problems}") from exc


@dataclass(frozen=True)
class ActorRule:
    """Quem pode executar uma operação de curadoria."""

    kinds: frozenset[str]
    declared_name_required: bool


_HUMAN = frozenset({"human"})

ACTOR_RULES: Mapping[str, ActorRule] = MappingProxyType(
    {
        "request_change": ActorRule(frozenset({"human", "assistant"}), False),
        "triage_request": ActorRule(_HUMAN, False),
        "reject_request": ActorRule(_HUMAN, True),
        "cancel_request": ActorRule(_HUMAN, False),
        "create_draft": ActorRule(frozenset({"human", "assistant"}), False),
        "import_draft": ActorRule(frozenset({"human", "service"}), False),
        "edit_draft": ActorRule(frozenset({"human", "assistant"}), False),
        "submit_for_review": ActorRule(_HUMAN, False),
        "review_draft": ActorRule(_HUMAN, True),
        "cancel_draft": ActorRule(_HUMAN, False),
        "prepare_release": ActorRule(_HUMAN, True),
        "publish": ActorRule(_HUMAN, True),
        "resume_publication": ActorRule(_HUMAN, True),
        "abandon_publication": ActorRule(_HUMAN, True),
    }
)
"""Regras por operação. Assistente propõe; serviço importa; só pessoa decide e publica."""


def authorize(operation: str, actor: ActorSnapshot) -> None:
    """Recusa a operação quando o tipo de ator ou o responsável declarado não bastam.

    É a barreira do serviço: um botão escondido na interface não a substitui. Não é
    autenticação: o nome declarado continua sendo identificação informada.
    """
    rule = ACTOR_RULES.get(operation)
    if rule is None:
        raise ActorNotAllowedError(f"operação desconhecida: {operation}")
    if actor.actor_kind not in rule.kinds:
        raise ActorNotAllowedError(
            f"{operation} não é permitida a ator {actor.actor_kind}; "
            f"permitida a {sorted(rule.kinds)}"
        )
    if rule.declared_name_required and actor.declared_name is None:
        raise ActorNotAllowedError(
            f"{operation} exige responsável declarado (identificação informada, não autenticada)"
        )
