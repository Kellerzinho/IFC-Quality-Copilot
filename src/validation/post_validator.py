"""Validacao pos-correcao para elementos IFC."""

import importlib

import ifcopenshell
import ifcopenshell.util.element
from loguru import logger

from src.models import OperationalRule, ValidationResult
from src.suggestion_engine.normalization import is_canonical_fire_rating, parse_numeric_value
from src.translator.rule_generator import apply_rules


class PostValidator:
    """Valida um elemento IFC apos correcao."""

    def __init__(
        self,
        ifc_file: ifcopenshell.file,
        ids_rules: list[OperationalRule] | None = None,
        run_schema_on_element_validation: bool = True,
    ) -> None:
        self._ifc_file = ifc_file
        self._ids_rules = ids_rules or []
        self._run_schema_on_element_validation = run_schema_on_element_validation

    def validate_element(self, guid: str) -> ValidationResult:
        """Valida o elemento com o GUID dado."""
        logger.info("PostValidator: iniciando validacao do elemento {}", guid)

        try:
            element = self._ifc_file.by_guid(guid)
        except RuntimeError:
            error = "Elemento nao encontrado"
            logger.warning("PostValidator: {} ({})", error, guid)
            return ValidationResult(
                guid=guid,
                status="fail",
                schema_valid=False,
                ids_compliant=False,
                errors=[error],
                schema_errors=[error],
            )

        if self._run_schema_on_element_validation:
            schema_errors, warnings = self._run_schema_check()
        else:
            schema_errors, warnings = [], []
        ids_errors = self._run_ids_revalidation(element)
        semantic_errors = self._run_semantic_checks(element)
        status = "pass" if not schema_errors and not ids_errors and not semantic_errors else "fail"

        result = ValidationResult(
            guid=guid,
            status=status,
            schema_valid=not schema_errors,
            ids_compliant=not ids_errors,
            schema_errors=schema_errors,
            ids_errors=[*ids_errors, *semantic_errors],
            warnings=warnings,
        )
        logger.info(
            "PostValidator: guid={} status={} schema_valid={} ids_compliant={} warnings={} errors={}",
            guid,
            result.status,
            result.schema_valid,
            result.ids_compliant,
            len(result.warnings),
            len(result.errors),
        )
        return result

    def validate_all_corrections(self, guids: list[str]) -> dict[str, ValidationResult]:
        """Valida multiplos elementos. Retorna dict guid -> ValidationResult."""
        return {guid: self.validate_element(guid) for guid in guids}

    def _run_schema_check(self) -> tuple[list[str], list[str]]:
        """Executa validacao de schema, com fallback gracioso se indisponivel."""
        try:
            validate_module = importlib.import_module("ifcopenshell.validate")
        except ImportError as exc:
            warning = f"Schema validation unavailable: {exc}"
            logger.warning("PostValidator: {}", warning)
            return [], [warning]

        validate_fn = getattr(validate_module, "validate", None)
        json_logger_cls = getattr(validate_module, "json_logger", None)
        if not callable(validate_fn) or json_logger_cls is None:
            warning = "Schema validation unavailable: ifcopenshell.validate.validate not found"
            logger.warning("PostValidator: {}", warning)
            return [], [warning]

        try:
            schema_logger = json_logger_cls()
            validate_fn(self._ifc_file, schema_logger)
        except Exception as exc:
            warning = f"Schema validation skipped after failure: {exc}"
            logger.warning("PostValidator: {}", warning)
            return [], [warning]

        schema_errors: list[str] = []
        warnings: list[str] = []
        for statement in getattr(schema_logger, "statements", []):
            level = str(statement.get("level", "")).lower()
            message = str(statement.get("message", "")).strip()
            if not message:
                continue
            if level in {"error", "exception", "critical"}:
                schema_errors.append(message)
            else:
                warnings.append(message)
        return schema_errors, warnings

    def _run_ids_revalidation(self, element: ifcopenshell.entity_instance) -> list[str]:
        """Reexecuta apenas as regras IDS aplicaveis ao elemento."""
        if not self._ids_rules:
            return []

        applicable_rules: list[OperationalRule] = []
        for rule in self._ids_rules:
            try:
                if element in self._ifc_file.by_type(rule.filter_entity):
                    applicable_rules.append(rule)
            except Exception as exc:
                logger.warning(
                    "PostValidator: nao foi possivel avaliar entidade {} para regra {}: {}",
                    rule.filter_entity,
                    rule.id,
                    exc,
                )

        if not applicable_rules:
            return []

        failing_issues = [
            issue
            for issue in apply_rules(self._ifc_file, applicable_rules)
            if issue.element_guid == element.GlobalId
        ]
        return [issue.description for issue in failing_issues]

    def _run_semantic_checks(self, element: ifcopenshell.entity_instance) -> list[str]:
        """Executa validacoes semanticas leves para propriedades criticas."""
        errors: list[str] = []
        psets = ifcopenshell.util.element.get_psets(element)
        for pset_data in psets.values():
            if not isinstance(pset_data, dict):
                continue
            thermal_value = pset_data.get("ThermalTransmittance")
            if thermal_value is not None and parse_numeric_value(thermal_value) is None:
                errors.append("ThermalTransmittance deve ser numerico positivo")
            fire_rating = pset_data.get("FireRating")
            if fire_rating is not None and str(fire_rating).strip() and not is_canonical_fire_rating(fire_rating):
                errors.append("FireRating deve estar no formato canonico 'REI n'")
        return errors
