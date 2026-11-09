"""``LocalArtifactStore``: retenção exata de IFC/IDS por hash e de releases por identidade.

Layout sob a raiz controlada: ``s/<papel>/<sha256>`` (fontes), ``r/<chave>`` (releases
retidos), ``t/`` (preparo exclusivo) e ``p/`` (área da porta E2 de publicação). Toda
cópia é feita para um preparo exclusivo, com hash calculado durante a cópia, flush e
fsync; o preparo é reaberto e conferido, promovido **sem sobrescrever** e conferido de
novo no destino. Destino ocupado por bytes idênticos é reutilizado depois da
verificação; por bytes distintos é ``storage_collision``. Entradas que são link
simbólico/ponto de reparse ou não são arquivo regular são recusadas, e nenhum
componente interno entre a raiz e o caminho usado (áreas ``t``/``s``/``r``/``p`` e
subpastas) pode ser link/ponto de reparse: é conferido com ``lstat`` antes de criar,
abrir ou resolver, inclusive junction para dentro da própria raiz. Chaves internas
seguem padrões fechados; nenhum caminho livre, URL ou ``..`` é aceito. O arquivo
atual de mesmo nome nunca substitui um objeto retido ausente ou adulterado.
"""

import hashlib
import os
import shutil
import stat
import uuid
from collections.abc import Collection
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import ValidationError

from src.artifacts.contracts import (
    ArtifactError,
    ArtifactErrorReason,
    OrphanReport,
    RetainedCatalogRef,
    RetainedFile,
    RetainedSourceObject,
)
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.errors import CatalogPackageError
from src.domain_catalog.operations import DEFAULT_OPERATION_REGISTRY, OperationRegistry
from src.domain_catalog.package import MANIFEST_FILE, PackageLimits
from src.domain_catalog.reader import CatalogReader, open_catalog
from src.operations.contracts import SourceArtifactRef, SourceRole

MiB: Final = 1024 * 1024
_REPARSE_POINT: Final = 0x400
_NAME_SURROGATE: Final = 0x20000000
_CHUNK: Final = 1 << 20


@dataclass(frozen=True)
class SourceLimits:
    """Tamanho máximo retido por papel; igualdade é aceita, um byte a mais é recusado."""

    max_ifc_bytes: int = 256 * MiB
    max_ids_bytes: int = 8 * MiB

    def limit(self, role: SourceRole) -> int:
        """Limite do papel."""
        return self.max_ifc_bytes if role == "ifc" else self.max_ids_bytes


def _failure(action: str, exc: OSError) -> ArtifactError:
    reason = exc.strerror or type(exc).__name__
    return ArtifactError("storage_failure", f"falha ao {action}: {reason}")


def _is_link(info: os.stat_result) -> bool:
    """Link simbólico ou ponto de reparse *name surrogate* (junction, symlink, mount point).

    Reparse sem redirecionamento de nome (nuvem, deduplicação) não é link; atributo de
    reparse sem tag conhecida é tratado como link (recusa conservadora).
    """
    if stat.S_ISLNK(info.st_mode):
        return True
    if not getattr(info, "st_file_attributes", 0) & _REPARSE_POINT:
        return False
    tag = getattr(info, "st_reparse_tag", 0)
    return not tag or bool(tag & _NAME_SURROGATE)


def refuse_reparse_components(base: Path, path: Path) -> None:
    """Recusa ``base`` ou componente existente até ``path`` que seja link/ponto de reparse.

    Conferência lexical com ``lstat``, antes de qualquer ``resolve``/criação/abertura;
    componentes ainda inexistentes encerram a verificação.
    """
    current = base
    for part in (None, *path.relative_to(base).parts):
        if part is not None:
            current = current / part
        try:
            info = os.lstat(current)
        except FileNotFoundError:
            return
        except OSError as exc:
            raise _failure(f"conferir {current.name}", exc) from exc
        if _is_link(info):
            raise ArtifactError(
                "unsafe_source", f"componente interno {current} é link/ponto de reparse"
            )


def _hash_file(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(_CHUNK), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _write_durably(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


def catalog_storage_key(ref: CatalogReleaseRef) -> str:
    """Chave curta e determinística do release retido (a identidade completa fica no banco)."""
    text = f"{ref.catalog_id}\n{ref.version}\n{ref.manifest_sha256}".encode()
    return "r/" + hashlib.sha256(text).hexdigest()[:32]


class LocalArtifactStore:
    """Retenção verificada sob uma raiz local controlada; nada é apagado automaticamente."""

    def __init__(self, root: Path, *, limits: SourceLimits | None = None) -> None:
        """Raiz absoluta das áreas; não cria nada até a primeira retenção."""
        self.root = root.resolve()
        self.limits = limits or SourceLimits()

    # --- caminhos fechados --------------------------------------------------------------

    def _inside(self, relative: str) -> Path:
        lexical = self.root / relative
        if not lexical.resolve().is_relative_to(self.root):
            raise ArtifactError("unsafe_source", f"caminho fora da raiz: {relative}")
        refuse_reparse_components(self.root, lexical)
        path = lexical.resolve()
        if not path.is_relative_to(self.root):
            raise ArtifactError("unsafe_source", f"caminho fora da raiz: {relative}")
        return path

    def source_path(self, storage_key: str) -> Path:
        """Caminho do objeto de fonte; só chaves ``s/<ifc|ids>/<sha256>`` são aceitas."""
        parts = storage_key.split("/")
        if (
            len(parts) != 3
            or parts[0] != "s"
            or parts[1] not in ("ifc", "ids")
            or len(parts[2]) != 64
            or any(c not in "0123456789abcdef" for c in parts[2])
        ):
            raise ArtifactError("unsafe_source", f"chave de fonte inválida: {storage_key!r}")
        return self._inside(storage_key)

    def catalog_dir(self, retained: RetainedCatalogRef) -> Path:
        """Pasta do release retido, derivada da chave validada."""
        if retained.storage_key != catalog_storage_key(retained.catalog):
            raise ArtifactError("unsafe_source", "chave do release não corresponde à identidade")
        return self._inside(retained.storage_key)

    def publication_root(self) -> Path:
        """Área da porta de artefatos da publicação E2, sob a mesma raiz."""
        area = self.root / "p"
        refuse_reparse_components(self.root, area)
        return area

    def _new_staging(self) -> Path:
        area = self.root / "t"
        refuse_reparse_components(self.root, area)
        try:
            area.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise _failure("criar área de preparo", exc) from exc
        refuse_reparse_components(self.root, area)
        return area / uuid.uuid4().hex[:16]

    # --- fontes ---------------------------------------------------------------------------

    def _regular_input(self, path: Path) -> os.stat_result:
        try:
            info = os.lstat(path)
        except FileNotFoundError as exc:
            raise ArtifactError("artifact_unavailable", f"{path.name} não existe") from exc
        except OSError as exc:
            raise _failure(f"ler {path.name}", exc) from exc
        if _is_link(info) or not stat.S_ISREG(info.st_mode):
            raise ArtifactError(
                "unsafe_source", f"{path.name} não é arquivo regular (link/pasta recusados)"
            )
        return info

    def _copy_to_staging(self, source: Path, info: os.stat_result, limit: int) -> tuple[Path, str]:
        staging = self._new_staging()
        digest = hashlib.sha256()
        size = 0
        try:
            with source.open("rb") as reader, staging.open("xb") as writer:
                opened = os.fstat(reader.fileno())
                if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
                    raise ArtifactError("unsafe_source", f"{source.name} mudou durante a leitura")
                for chunk in iter(lambda: reader.read(_CHUNK), b""):
                    size += len(chunk)
                    if size > limit:
                        raise ArtifactError(
                            "resource_limit_exceeded", f"{source.name} excede {limit} bytes"
                        )
                    digest.update(chunk)
                    writer.write(chunk)
                writer.flush()
                os.fsync(writer.fileno())
        except ArtifactError:
            staging.unlink(missing_ok=True)
            raise
        except OSError as exc:
            staging.unlink(missing_ok=True)
            raise _failure(f"copiar {source.name}", exc) from exc
        sha = digest.hexdigest()
        if _hash_file(staging) != (sha, size):
            raise ArtifactError("artifact_integrity_error", "preparo difere dos bytes copiados")
        return staging, sha

    def _promote_file(self, staging: Path, destination: Path, sha: str) -> None:
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            if os.name == "nt":
                os.rename(staging, destination)
            else:
                os.link(staging, destination)
                staging.unlink()
        except FileExistsError:
            same = _hash_file(destination)[0] == sha
            staging.unlink(missing_ok=True)
            if not same:
                raise ArtifactError(
                    "storage_collision", f"destino {destination.name} ocupado por outros bytes"
                ) from None
        except OSError as exc:
            raise _failure("promover fonte", exc) from exc

    def retain_source(self, path: Path, role: SourceRole) -> RetainedSourceObject:
        """Copia, verifica e promove a fonte exata; não cria identidade lógica nem revisão."""
        info = self._regular_input(path)
        limit = self.limits.limit(role)
        if info.st_size > limit:
            raise ArtifactError("resource_limit_exceeded", f"{path.name} excede {limit} bytes")
        staging, sha = self._copy_to_staging(path, info, limit)
        try:
            retained = RetainedSourceObject(
                role=role,
                sha256=sha,
                size_bytes=_hash_file(staging)[1],
                storage_key=f"s/{role}/{sha}",
                display_name=path.name,
            )
        except ValidationError as exc:
            staging.unlink(missing_ok=True)
            raise ArtifactError(
                "unsafe_source", f"nome de arquivo inválido: {path.name!r}"
            ) from exc
        destination = self.source_path(retained.storage_key)
        self._promote_file(staging, destination, sha)
        if _hash_file(destination) != (sha, retained.size_bytes):
            raise ArtifactError("artifact_integrity_error", "objeto promovido difere do preparo")
        return retained

    def read_verified_source(self, ref: SourceArtifactRef) -> Path:
        """Caminho do objeto retido depois de conferir tamanho e hash com a referência."""
        path = self.source_path(ref.storage_key)
        try:
            info = os.lstat(path)
        except FileNotFoundError as exc:
            raise ArtifactError(
                "artifact_unavailable", f"fonte {ref.source_id} r{ref.revision} ausente"
            ) from exc
        except OSError as exc:
            raise _failure("ler fonte retida", exc) from exc
        if _is_link(info) or not stat.S_ISREG(info.st_mode):
            raise ArtifactError("artifact_integrity_error", "objeto retido não é arquivo regular")
        if _hash_file(path) != (ref.sha256, ref.size_bytes):
            raise ArtifactError(
                "artifact_integrity_error",
                f"fonte {ref.source_id} r{ref.revision} difere do hash registrado",
            )
        return path

    # --- releases -------------------------------------------------------------------------

    def retain_catalog(
        self,
        ref: CatalogReleaseRef,
        package_dir: Path,
        *,
        limits: PackageLimits | None = None,
        registry: OperationRegistry = DEFAULT_OPERATION_REGISTRY,
    ) -> RetainedCatalogRef:
        """Abre o pacote real, copia todos os arquivos, promove exclusivamente e reabre.

        Erro de pacote sai como ``CatalogPackageError`` com o motivo original.
        """
        limits = limits or PackageLimits()
        manifest = open_catalog(ref, package_dir, limits=limits, registry=registry).describe()
        names = [MANIFEST_FILE, *(item.path for item in manifest.files)]
        staging = self._new_staging()
        try:
            staging.mkdir()
            total = 0
            for name in names:
                source = package_dir / name
                self._regular_input(source)
                with source.open("rb") as handle:
                    data = handle.read(limits.max_file_bytes + 1)
                total += len(data)
                if len(data) > limits.max_file_bytes or total > limits.max_total_bytes:
                    raise ArtifactError(
                        "resource_limit_exceeded", f"pacote excede limites ({name})"
                    )
                _write_durably(staging / name, data)
            open_catalog(ref, staging, limits=limits, registry=registry)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        key = catalog_storage_key(ref)
        destination = self._inside(key)
        try:
            destination.parent.mkdir(parents=True, exist_ok=True)
            os.rename(staging, destination)
        except OSError as exc:
            if not destination.exists():
                shutil.rmtree(staging, ignore_errors=True)
                raise _failure("promover release", exc) from exc
            shutil.rmtree(staging, ignore_errors=True)
            try:
                open_catalog(ref, destination, limits=limits, registry=registry)
            except CatalogPackageError as collision:
                raise ArtifactError(
                    "storage_collision",
                    f"destino do release {ref.version} ocupado por outro pacote",
                ) from collision
        open_catalog(ref, destination, limits=limits, registry=registry)
        files = (
            RetainedFile(
                path=MANIFEST_FILE,
                bytes=len((destination / MANIFEST_FILE).read_bytes()),
                sha256=ref.manifest_sha256,
            ),
            *(
                RetainedFile(path=item.path, bytes=item.bytes, sha256=item.sha256)
                for item in manifest.files
            ),
        )
        return RetainedCatalogRef(
            catalog=ref, storage_key=key, content_origin=manifest.content_origin, files=files
        )

    def open_retained_catalog(
        self,
        retained: RetainedCatalogRef,
        *,
        limits: PackageLimits | None = None,
        registry: OperationRegistry = DEFAULT_OPERATION_REGISTRY,
    ) -> CatalogReader:
        """Reabre e revalida o release retido; ausência ou adulteração é erro de artefato."""
        directory = self.catalog_dir(retained)
        if not directory.is_dir():
            raise ArtifactError(
                "artifact_unavailable", f"release retido {retained.catalog.version} ausente"
            )
        try:
            return open_catalog(retained.catalog, directory, limits=limits, registry=registry)
        except CatalogPackageError as exc:
            reason: ArtifactErrorReason = (
                "artifact_unavailable" if exc.reason == "not_found" else "artifact_integrity_error"
            )
            raise ArtifactError(
                reason, f"release retido {retained.catalog.version}: {exc}"
            ) from exc

    # --- inspeção ------------------------------------------------------------------------

    def inspect_orphans(self, referenced: Collection[str]) -> OrphanReport:
        """Lista objetos sem referência e restos de preparo, sem mover nem apagar nada."""
        wanted = set(referenced)

        def entries(*parts: str) -> list[Path]:
            area = self.root.joinpath(*parts)
            return sorted(area.iterdir()) if area.is_dir() else []

        try:
            sources = [
                f"s/{role.name}/{item.name}"
                for role in entries("s")
                for item in (entries("s", role.name) if role.is_dir() else [])
            ]
            releases = [f"r/{item.name}" for item in entries("r")]
            staging = [f"t/{item.name}" for item in entries("t")]
        except OSError as exc:
            raise _failure("inspecionar artefatos", exc) from exc
        return OrphanReport(
            sources=tuple(key for key in sources if key not in wanted),
            releases=tuple(key for key in releases if key not in wanted),
            staging=tuple(staging),
        )
