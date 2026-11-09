"""Porta de persistência transacional da curadoria (E2, M1-08; autoridade do M6).

O catálogo não mantém banco próprio. Solicitações, revisões de rascunho, decisões,
candidatos, intenções, recibos, comandos e eventos dependem de uma autoridade
transacional única, que no produto será o banco operacional do M6 (proposta do M1 em
``docs/catalogo/integracoes-pendentes.md``, ainda não acordada). Enquanto o M6 não
existir há somente o adaptador de teste ``tests/domain_catalog/curation_adapters.py``,
explicitamente não operacional; nenhuma integração de produção é declarada.

Contrato da porta, verificado por ``tests/domain_catalog/test_curation_store_contract.py``:

- registros são documentos JSON identificados por tipo e chave, com versão inteira;
- ``insert`` cria a versão 1 e recusa chave existente; ``replace`` exige a versão
  esperada (compare-and-swap) e recusa registro ausente;
- leituras devolvem cópias: alterar o documento lido não altera o armazenado;
- tudo o que uma transação grava, registros e eventos, só vale no commit; qualquer
  exceção desfaz a transação inteira, sem sucesso parcial;
- transações são serializáveis: o resultado equivale a executá-las uma de cada vez, e
  uma transação que lê e depois grava nunca se intercala com outra que grava (o banco
  do M6 previsto tem um escritor por vez). A reserva da linha de publicação do
  catálogo depende disso; armazenamento que não consiga garantir precisa recusar a
  segunda transação com conflito, nunca gravar as duas;
- eventos recebem sequência crescente na ordem de commit e nunca são alterados;
- dados confirmados sobrevivem à reabertura.
"""

from collections.abc import Mapping
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Any, Literal, Protocol, TypeVar

from pydantic import BaseModel, ValidationError

from src.domain_catalog.curation_errors import CurationError, CurationNotFoundError

RecordKind = Literal[
    "request", "draft", "revision", "review", "candidate", "intent", "publication", "command"
]
"""Tipos de registro da curadoria; cada um com chave própria."""


class StoreError(CurationError):
    """Falha da autoridade de persistência; o comando não teve efeito."""

    code = "store_error"


class StoreConflictError(StoreError):
    """Chave já existente ou versão esperada diferente da armazenada."""

    code = "store_conflict"


class StoreUnavailableError(StoreError):
    """Armazenamento indisponível ou falha de E/S durante a transação."""

    code = "store_unavailable"


@dataclass(frozen=True)
class StoredRecord:
    """Registro lido: tipo, chave, versão e uma cópia do documento JSON."""

    kind: RecordKind
    key: str
    version: int
    document: dict[str, Any]


class CurationTransaction(Protocol):
    """Unidade de trabalho: leitura consistente e escrita que só vale no commit."""

    def get(self, kind: RecordKind, key: str) -> StoredRecord | None:
        """Registro pela chave, ou ``None``."""
        ...

    def scan(self, kind: RecordKind) -> tuple[StoredRecord, ...]:
        """Registros de um tipo, em ordem de chave."""
        ...

    def insert(self, kind: RecordKind, key: str, document: Mapping[str, Any]) -> StoredRecord:
        """Cria o registro na versão 1; chave existente é ``StoreConflictError``."""
        ...

    def replace(
        self, kind: RecordKind, key: str, expected_version: int, document: Mapping[str, Any]
    ) -> StoredRecord:
        """Troca o documento se a versão armazenada for a esperada; senão, conflito."""
        ...

    def append_event(self, document: Mapping[str, Any]) -> int:
        """Acrescenta um evento e devolve sua sequência."""
        ...

    def events(self, after_seq: int = 0) -> tuple[tuple[int, dict[str, Any]], ...]:
        """Eventos confirmados depois da sequência dada, em ordem."""
        ...


class CurationStore(Protocol):
    """Autoridade transacional da curadoria (o banco operacional do M6, no produto)."""

    @property
    def operational(self) -> bool:
        """Se o adaptador é a integração operacional; adaptador de teste diz ``False``."""
        ...

    def transaction(self) -> AbstractContextManager[CurationTransaction]:
        """Abre uma transação: commit na saída normal, desfaz tudo em exceção."""
        ...


Model = TypeVar("Model", bound=BaseModel)


def _decode(stored: StoredRecord, model: type[Model]) -> Model:
    try:
        return model.model_validate(stored.document)
    except ValidationError as exc:
        raise StoreError(
            f"registro {stored.kind} {stored.key} não corresponde a {model.__name__}: {exc}"
        ) from exc


def read_model(
    tx: CurationTransaction, kind: RecordKind, key: str, model: type[Model]
) -> tuple[Model, int] | None:
    """Registro tipado e sua versão, ou ``None``; documento incoerente é ``StoreError``."""
    stored = tx.get(kind, key)
    if stored is None:
        return None
    return _decode(stored, model), stored.version


def require_model(
    tx: CurationTransaction, kind: RecordKind, key: str, model: type[Model], what: str
) -> tuple[Model, int]:
    """Registro tipado que precisa existir; ausência é ``CurationNotFoundError``."""
    found = read_model(tx, kind, key, model)
    if found is None:
        raise CurationNotFoundError(f"{what} {key} não existe")
    return found


def scan_models(
    tx: CurationTransaction, kind: RecordKind, model: type[Model]
) -> tuple[tuple[Model, int], ...]:
    """Todos os registros tipados de um tipo, em ordem de chave."""
    return tuple((_decode(stored, model), stored.version) for stored in tx.scan(kind))


def insert_model(tx: CurationTransaction, kind: RecordKind, key: str, record: BaseModel) -> int:
    """Grava um registro novo a partir do modelo; devolve a versão (1)."""
    return tx.insert(kind, key, record.model_dump(mode="json")).version


def replace_model(
    tx: CurationTransaction, kind: RecordKind, key: str, expected_version: int, record: BaseModel
) -> int:
    """Troca o registro com versão esperada; devolve a nova versão."""
    return tx.replace(kind, key, expected_version, record.model_dump(mode="json")).version
