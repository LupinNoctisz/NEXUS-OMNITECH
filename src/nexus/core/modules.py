"""Gerenciamento de módulos: manifesto, integridade, registro, ativação e carregamento.

Modelo de confiança (etapa 1):
  * um módulo só é carregado se (a) foi REGISTRADO por um administrador, (b) seu
    publicador está na lista de publicadores confiáveis, (c) o manifesto é idêntico
    ao fixado (pinned) no registro e (d) todos os arquivos conferem com os hashes
    SHA-256 do manifesto, sem arquivos executáveis extras;
  * o nome do publicador sozinho NÃO é prova de autoria. A assinatura criptográfica
    do manifesto (campo reservado ``signature``) é requisito da etapa de segurança
    e licenciamento. Até lá, a defesa é o registro explícito + hash fixado.
"""

from __future__ import annotations

import importlib.util
import json
import re
import types
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .errors import ConfirmationRequired, IntegrityError, ModuleError
from .permissions import Permission
from .util import canonical_json, sha256_bytes, sha256_file, utc_now

if TYPE_CHECKING:
    from .app import NexusCore

_ID = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
_VERSION = re.compile(r"^\d+\.\d+\.\d+$")
_ENTRY = re.compile(r"^[\w./-]+\.py:[A-Za-z_]\w*$")
_EXECUTABLE_SUFFIXES = {".py", ".pyd", ".dll", ".exe", ".ps1", ".bat", ".cmd", ".so", ".dylib", ".sh", ".msi"}
STATUSES = ("planned", "available")
# Categorias da aba "Manutenção" (módulo declara uma no manifesto: "maintenance_category").
MAINTENANCE_CATEGORIES = {"celular": "Celular", "computador": "Computador", "console": "Console", "notebook": "Notebook"}


def parse_version(text: str) -> tuple[int, int, int]:
    if not _VERSION.match(text):
        raise ModuleError(f"Versão inválida (use MAJOR.MINOR.PATCH): {text!r}")
    major, minor, patch = (int(p) for p in text.split("."))
    return major, minor, patch


@dataclass(frozen=True)
class Manifest:
    id: str
    name: str
    version: str
    publisher: str
    status: str
    entry: str | None
    min_core: str
    permissions: tuple[str, ...]
    files: dict[str, str]
    description: str
    root: Path
    manifest_sha256: str
    maintenance_category: str | None = None

    @classmethod
    def from_dir(cls, root: Path) -> "Manifest":
        root = Path(root)
        manifest_path = root / "manifest.json"
        try:
            data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ModuleError(f"Manifesto ilegível em {root}: {exc}") from exc
        if not isinstance(data, dict):
            raise ModuleError("Manifesto deve ser um objeto JSON.")
        for key in ("id", "name", "version", "publisher", "status"):
            if not isinstance(data.get(key), str) or not data[key].strip():
                raise ModuleError(f"Manifesto inválido: campo obrigatório ausente '{key}'.")
        if not _ID.match(data["id"]):
            raise ModuleError(f"ID de módulo inválido: {data['id']!r}")
        parse_version(data["version"])
        if data["status"] not in STATUSES:
            raise ModuleError(f"Status inválido: {data['status']!r}")
        entry = data.get("entry")
        if data["status"] == "available":
            if not entry or not _ENTRY.match(entry):
                raise ModuleError("Módulo 'available' exige 'entry' no formato 'arquivo.py:Classe'.")
            entry_file = entry.split(":")[0]
            if entry_file.startswith("/") or ".." in entry_file.split("/"):
                raise ModuleError("O 'entry' do módulo deve ficar dentro da pasta do próprio módulo.")
        files = data.get("files", {})
        if not isinstance(files, dict) or not all(isinstance(k, str) and isinstance(v, str) for k, v in files.items()):
            raise ModuleError("'files' deve mapear caminho -> sha256.")
        if data["status"] == "available" and entry.split(":")[0] not in files:
            raise ModuleError("O arquivo 'entry' precisa constar em 'files' (com SHA-256) para ser verificado antes de carregar.")
        category = data.get("maintenance_category")
        if category is not None and category not in MAINTENANCE_CATEGORIES:
            raise ModuleError(f"maintenance_category inválida: {category!r} (use {', '.join(MAINTENANCE_CATEGORIES)}).")
        min_core = data.get("min_core", "0.1.0")
        parse_version(min_core)
        signable = {k: v for k, v in data.items() if k != "signature"}
        return cls(
            id=data["id"], name=data["name"], version=data["version"], publisher=data["publisher"],
            status=data["status"], entry=entry, min_core=min_core,
            permissions=tuple(data.get("permissions", [])), files=dict(files),
            description=str(data.get("description", "")), root=root,
            manifest_sha256=sha256_bytes(canonical_json(signable).encode("utf-8")),
            maintenance_category=category,
        )


def seal_manifest(root: Path) -> dict[str, str]:
    """Ferramenta do DESENVOLVEDOR: grava no manifesto o SHA-256 de todos os arquivos do módulo."""
    root = Path(root)
    path = root / "manifest.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    files: dict[str, str] = {}
    for item in sorted(root.rglob("*")):
        if not item.is_file() or item.name == "manifest.json" or "__pycache__" in item.parts:
            continue
        files[item.relative_to(root).as_posix()] = sha256_file(item)
    data["files"] = files
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return files


@dataclass
class IntegrityReport:
    ok: bool
    problems: list[str] = field(default_factory=list)


@dataclass
class ModuleContext:
    """O que um módulo recebe do núcleo (superfície deliberadamente pequena)."""
    module_id: str
    logger: Any
    data_dir: Path
    devices: Any
    sessions: Any
    audit_record: Any  # callable(action, **kwargs) já vinculado ao módulo


class ModuleRegistry:
    def __init__(self, core: "NexusCore", search_dirs: list[Path], core_version: str):
        self._core = core
        self.search_dirs = [Path(p) for p in search_dirs]
        self.core_version = core_version
        self.loaded: dict[str, Any] = {}

    # -- descoberta --------------------------------------------------------
    def discover(self) -> dict[str, Manifest]:
        found: dict[str, Manifest] = {}
        for base in self.search_dirs:
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir()):
                if not (child / "manifest.json").is_file():
                    continue
                try:
                    manifest = Manifest.from_dir(child)
                except ModuleError as exc:
                    self._core.log.warning("manifesto ignorado", extra={"dir": str(child), "error": str(exc)})
                    continue
                found.setdefault(manifest.id, manifest)  # o primeiro diretório da lista tem prioridade
        return found

    def _row(self, module_id: str):
        return self._core.db.query_one("SELECT * FROM modules WHERE id = ?", (module_id,))

    def _manifest(self, module_id: str) -> Manifest:
        manifest = self.discover().get(module_id)
        if manifest is None:
            raise ModuleError(f"Módulo não encontrado: {module_id}")
        return manifest

    def _trusted(self, manifest: Manifest) -> bool:
        return manifest.publisher in self._core.settings.get("modules.trusted_publishers")

    # -- integridade -------------------------------------------------------
    def verify(self, module_id: str) -> IntegrityReport:
        manifest = self._manifest(module_id)
        problems: list[str] = []
        root = manifest.root.resolve()
        for rel, expected in manifest.files.items():
            target = (manifest.root / rel)
            try:
                resolved = target.resolve()
            except OSError:
                problems.append(f"{rel}: caminho inválido")
                continue
            if root not in resolved.parents:
                problems.append(f"{rel}: fora da pasta do módulo")
            elif not resolved.is_file():
                problems.append(f"{rel}: arquivo ausente")
            elif sha256_file(resolved) != expected:
                problems.append(f"{rel}: hash diverge do manifesto")
        declared = set(manifest.files)
        for item in manifest.root.rglob("*"):
            if not item.is_file() or "__pycache__" in item.parts or item.name == "manifest.json":
                continue
            rel = item.relative_to(manifest.root).as_posix()
            if item.suffix.lower() in _EXECUTABLE_SUFFIXES and rel not in declared:
                problems.append(f"{rel}: arquivo executável não declarado no manifesto")
        row = self._row(module_id)
        if row is not None and row["pinned_manifest_sha256"] != manifest.manifest_sha256:
            problems.append("manifesto alterado desde o registro")
        return IntegrityReport(ok=not problems, problems=problems)

    # -- ciclo de vida -----------------------------------------------------
    def register(self, module_id: str, *, confirmed: bool = False) -> None:
        self._core.require(Permission.MODULES_MANAGE)
        manifest = self._manifest(module_id)
        if not confirmed:
            raise ConfirmationRequired(f"Confirme o registro do módulo {module_id} (publicador: {manifest.publisher}).")
        if not self._trusted(manifest):
            raise ModuleError(f"Publicador não confiável: {manifest.publisher!r}. Módulos de terceiros não são executados.")
        if manifest.status != "available":
            raise ModuleError(f"Módulo {module_id} ainda não está disponível (status: {manifest.status}).")
        if parse_version(manifest.min_core) > parse_version(self.core_version):
            raise ModuleError(f"Módulo exige núcleo >= {manifest.min_core} (atual: {self.core_version}).")
        previous_row = self._row(module_id)
        report = self._verify_files_only(manifest)
        if not report.ok:
            raise IntegrityError(f"Integridade falhou: {'; '.join(report.problems)}")
        with self._core.db.transaction():
            self._core.db.execute(
                "INSERT INTO modules (id, version, enabled, pinned_manifest_sha256, registered_at, registered_by)"
                " VALUES (?,?,0,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version, enabled=0,"
                " pinned_manifest_sha256=excluded.pinned_manifest_sha256, registered_at=excluded.registered_at,"
                " registered_by=excluded.registered_by",
                (module_id, manifest.version, manifest.manifest_sha256, utc_now(), self._core.actor))
            self._core.audit.record("module.register", technician=self._core.actor, target=module_id,
                                    details={"version": manifest.version, "reregistered": previous_row is not None,
                                             "manifest_sha256": manifest.manifest_sha256})

    def _verify_files_only(self, manifest: Manifest) -> IntegrityReport:
        # verificação de arquivos antes do registro (ainda não há hash fixado)
        row = self._row(manifest.id)
        if row is None:
            return self.verify(manifest.id)
        report = self.verify(manifest.id)
        report.problems = [p for p in report.problems if p != "manifesto alterado desde o registro"]
        report.ok = not report.problems
        return report

    def enable(self, module_id: str) -> None:
        self._core.require(Permission.MODULES_MANAGE)
        row = self._row(module_id)
        if row is None:
            raise ModuleError(f"Módulo {module_id} não registrado. Registre-o antes de ativar.")
        manifest = self._manifest(module_id)
        if not self._trusted(manifest):
            raise ModuleError(f"Publicador não confiável: {manifest.publisher!r}.")
        report = self.verify(module_id)
        if not report.ok:
            self._core.audit.record("module.enable", technician=self._core.actor, target=module_id,
                                    outcome="integrity_failed", details={"problems": report.problems})
            raise IntegrityError(f"Integridade falhou: {'; '.join(report.problems)}")
        self._core.db.execute("UPDATE modules SET enabled = 1 WHERE id = ?", (module_id,))
        self._core.audit.record("module.enable", technician=self._core.actor, target=module_id)

    def disable(self, module_id: str) -> None:
        self._core.require(Permission.MODULES_MANAGE)
        if self._row(module_id) is None:
            raise ModuleError(f"Módulo {module_id} não registrado.")
        self.unload(module_id)
        self._core.db.execute("UPDATE modules SET enabled = 0 WHERE id = ?", (module_id,))
        self._core.audit.record("module.disable", technician=self._core.actor, target=module_id)

    # -- carregamento ------------------------------------------------------
    def load_enabled(self) -> dict[str, str]:
        """Carrega os módulos ativos e íntegros. Devolve {id: erro} dos que foram bloqueados."""
        blocked: dict[str, str] = {}
        for row in self._core.db.query_all("SELECT id FROM modules WHERE enabled = 1 ORDER BY id"):
            module_id = row["id"]
            if module_id in self.loaded:
                continue
            try:
                self._load(module_id)
            except Exception as exc:
                blocked[module_id] = f"{type(exc).__name__}: {exc}"
                self._core.log.error("módulo bloqueado", extra={"module_id": module_id, "error": str(exc)})
                self._core.audit.record("module.load", technician="system", target=module_id,
                                        outcome="blocked", details={"error": str(exc)})
        return blocked

    def _load(self, module_id: str) -> None:
        manifest = self._manifest(module_id)
        if not self._trusted(manifest):
            raise ModuleError("publicador não confiável")
        report = self.verify(module_id)
        if not report.ok:
            raise IntegrityError("; ".join(report.problems))
        assert manifest.entry  # garantido pela validação do manifesto 'available'
        file_part, class_name = manifest.entry.split(":")
        path = (manifest.root / file_part).resolve()
        spec = importlib.util.spec_from_file_location(f"nexus_ext_{module_id.replace('.', '_')}", path)
        if spec is None or spec.loader is None:
            raise ModuleError(f"Não foi possível importar {file_part}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        instance = getattr(module, class_name)()
        for attr in ("initialize", "shutdown"):
            if not callable(getattr(instance, attr, None)):
                raise ModuleError(f"Classe {class_name} deve implementar {attr}()")
        data_dir = self._core.paths.module_data / module_id
        data_dir.mkdir(parents=True, exist_ok=True)
        core = self._core
        # Fachadas mínimas: o módulo NÃO recebe o núcleo, os repositórios nem a trava de segurança.
        # (Não é um sandbox: código do módulo roda no mesmo processo e só é carregado se íntegro e
        # registrado por um administrador. Isolamento real por processo está previsto para a etapa 9.)
        devices = types.SimpleNamespace(
            list=lambda connection=None: core.devices.list(connection),
            get=lambda device_id: core.devices.get(device_id),
        )
        sessions = types.SimpleNamespace(
            start=lambda device_id, kind="general": core.sessions.start(device_id, kind),
            finish=lambda session_id, status="completed", summary=None: core.sessions.finish(
                session_id, status=status, summary=summary),
            get=lambda session_id: core.sessions.get(session_id),
            recent=lambda limit=10: core.sessions.recent(limit),
        )
        ctx = ModuleContext(
            module_id=module_id,
            logger=core.log.getChild(module_id),
            data_dir=data_dir,
            devices=devices,
            sessions=sessions,
            audit_record=lambda action, **kw: core.audit.record(
                f"{module_id}:{action}", technician=core.actor, **kw),
        )
        instance.initialize(ctx)
        self.loaded[module_id] = instance
        self._core.audit.record("module.load", technician="system", target=module_id,
                                details={"version": manifest.version})

    def unload(self, module_id: str) -> None:
        instance = self.loaded.pop(module_id, None)
        if instance is not None:
            try:
                instance.shutdown()
            except Exception as exc:
                self._core.log.error("falha ao encerrar módulo", extra={"module_id": module_id, "error": str(exc)})

    def unload_all(self) -> None:
        for module_id in list(self.loaded):
            self.unload(module_id)

    # -- consulta ----------------------------------------------------------
    def maintenance(self) -> list[dict[str, Any]]:
        """Módulos de manutenção agrupados por categoria (as quatro categorias sempre aparecem)."""
        manifests = self.discover()
        by_category: dict[str, list[dict[str, Any]]] = {key: [] for key in MAINTENANCE_CATEGORIES}
        for row in self.status():
            category = manifests[row["id"]].maintenance_category
            if category in by_category:
                by_category[category].append({**row, "description": manifests[row["id"]].description})
        return [{"key": key, "label": label, "modules": by_category[key]}
                for key, label in MAINTENANCE_CATEGORIES.items()]

    def status(self) -> list[dict[str, Any]]:
        result = []
        for module_id, manifest in sorted(self.discover().items()):
            row = self._row(module_id)
            integrity = self.verify(module_id) if manifest.status == "available" else None
            result.append({
                "id": module_id,
                "name": manifest.name,
                "version": manifest.version,
                "publisher": manifest.publisher,
                "status": manifest.status,
                "registered": row is not None,
                "enabled": bool(row["enabled"]) if row else False,
                "loaded": module_id in self.loaded,
                "integrity_ok": None if integrity is None else integrity.ok,
                "problems": [] if integrity is None else integrity.problems,
            })
        return result
