"""``ReleaseArtifactStore`` E2 real sobre a raiz controlada do armazenamento local.

Implementa a porta existente da publicação (stage, staging_path, release_path,
promote, quarantine, inventory) sem redesenhar curadoria ou publicação: preparo em
pasta nova exclusiva com arquivos gravados com fsync, promoção por renomeação
exclusiva que nunca sobrescreve, quarentena que move sem apagar e inventário que vê
entradas soltas. Toda falha do sistema de arquivos sai como ``ArtifactStoreError``
com ``phase`` e ``errno``. Layout curto: ``s/`` (preparo), ``r/<catálogo>/<versão>``
(releases) e ``q/`` (quarentena), sob a área ``p/`` do ``LocalArtifactStore``. A
raiz e todo componente interno usado são conferidos com ``lstat``: link/ponto de
reparse (junction) é ``ArtifactStoreError`` antes de criar, gravar ou renomear.
``operational=True`` significa armazenamento durável implementado, não autenticação.
"""

import os
import re
from pathlib import Path

from src.artifacts.contracts import ArtifactError
from src.artifacts.storage import refuse_reparse_components
from src.domain_catalog.contracts import CatalogReleaseRef
from src.domain_catalog.package import MANIFEST_FILE, ReleaseFiles
from src.domain_catalog.publication import (
    ArtifactStoreError,
    ReleaseCollisionError,
    StoreInventory,
    storage_failure,
)

_UUID = re.compile(
    r"^urn:uuid:([0-9a-f]{8})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{4})-([0-9a-f]{12})$"
)
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")


def _short_dir(local_id: str) -> str:
    """Nome de pasta de um ID local: o UUID inteiro em 32 hexadecimais, sem hífens.

    Sem o prefixo ``urn:uuid:`` e sem hífens por causa do limite de 260 caracteres de
    caminhos no Windows; nenhum bit é descartado, então UUIDs distintos nunca dividem
    pasta (E3-14). A identidade completa continua no banco.
    """
    match = _UUID.match(local_id)
    if match is None:
        raise ArtifactStoreError(f"ID local inválido para pasta: {local_id!r}")
    return "".join(match.groups())


def _write_durably(path: Path, data: bytes) -> None:
    with path.open("xb") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())


class LocalReleaseArtifactStore:
    """Bytes imutáveis de candidatos e releases E2 numa raiz local controlada."""

    def __init__(self, root: Path) -> None:
        """Raiz das áreas de preparo, releases e quarentena."""
        self.root = root

    def _contained(self, path: Path, phase: str) -> Path:
        """``path`` sem link/ponto de reparse entre a raiz (inclusive) e ele."""
        try:
            refuse_reparse_components(self.root, path)
        except ArtifactError as exc:
            raise ArtifactStoreError(str(exc), phase=phase) from exc
        return path

    @property
    def operational(self) -> bool:
        """Armazenamento durável implementado (não é autenticação nem produção)."""
        return True

    def staging_path(self, candidate_id: str) -> Path:
        """Local da pasta de preparo do candidato (pode não existir)."""
        return self.root / "s" / _short_dir(candidate_id)

    def stage(self, candidate_id: str, release: ReleaseFiles) -> Path:
        """Grava o candidato numa pasta de preparo nova; pasta existente é erro."""
        target = self._contained(self.staging_path(candidate_id), "stage")
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            self._contained(target, "stage")
            try:
                target.mkdir()
            except FileExistsError as exc:
                raise ArtifactStoreError(
                    f"preparo já existe para {candidate_id}", phase="stage", errno=exc.errno
                ) from exc
            _write_durably(target / MANIFEST_FILE, release.manifest_bytes)
            for name, blob in release.data.items():
                _write_durably(target / name, blob)
        except OSError as exc:
            raise storage_failure("stage", exc) from exc
        return target

    def release_path(self, ref: CatalogReleaseRef) -> Path:
        """Destino final do release (pode ainda não existir)."""
        if _VERSION.match(ref.version) is None:
            raise ArtifactStoreError(f"versão inválida para pasta: {ref.version!r}")
        return self.root / "r" / _short_dir(ref.catalog_id) / ref.version

    def promote(self, candidate_id: str, ref: CatalogReleaseRef) -> Path:
        """Renomeia o preparo para o destino final; destino existente nunca é sobrescrito."""
        try:
            source = self._contained(self.staging_path(candidate_id), "promote")
            if not source.is_dir():
                raise ArtifactStoreError(f"sem preparo para {candidate_id}", phase="promote")
            target = self._contained(self.release_path(ref), "promote")
            if target.exists():
                raise ReleaseCollisionError(
                    f"destino {target.name} já existe; nada é sobrescrito", phase="promote"
                )
            target.parent.mkdir(parents=True, exist_ok=True)
            self._contained(target, "promote")
            os.rename(source, target)
        except FileExistsError as exc:
            raise ReleaseCollisionError(
                "destino criado concorrentemente; nada é sobrescrito",
                phase="promote",
                errno=exc.errno,
            ) from exc
        except OSError as exc:
            raise storage_failure("promote", exc) from exc
        return target

    def quarantine(self, path: Path, label: str) -> Path:
        """Move a pasta para a quarentena com nome exclusivo, sem apagar nada."""
        area = self._contained(self.root / "q", "quarantine")
        self._contained(path, "quarantine")
        try:
            area.mkdir(parents=True, exist_ok=True)
            self._contained(area, "quarantine")
            number = len(list(area.iterdir())) + 1
            while True:
                target = area / f"{number:03d}-{label}"
                if not target.exists():
                    break
                number += 1
            os.rename(path, target)
        except OSError as exc:
            raise storage_failure("quarantine", exc) from exc
        return target

    def inventory(self) -> StoreInventory:
        """Entradas presentes no preparo e na área de releases, inclusive soltas."""
        try:
            staged_area = self.root / "s"
            staged = tuple(sorted(staged_area.iterdir())) if staged_area.is_dir() else ()
            release_area = self.root / "r"
            releases: tuple[Path, ...] = ()
            if release_area.is_dir():
                releases = tuple(
                    entry
                    for catalog in sorted(release_area.iterdir())
                    for entry in (sorted(catalog.iterdir()) if catalog.is_dir() else (catalog,))
                )
        except OSError as exc:
            raise storage_failure("inventory", exc) from exc
        return StoreInventory(staged=staged, releases=releases)
