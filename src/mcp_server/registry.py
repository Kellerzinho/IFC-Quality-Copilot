"""Registro dinâmico de tools MCP, filtrável por perfil de readiness."""

from collections.abc import Callable
from typing import Any

from loguru import logger


class ToolRegistry:
    """Registro dinâmico de tools MCP, filtrável por perfil de readiness."""

    def __init__(self) -> None:
        self._tools: dict[str, dict[str, Any]] = {}

    def register(
        self,
        name: str,
        handler: Callable,
        schema: dict,
        profiles: list[str] | None = None,
        category: str = "general",
        description: str = "",
    ) -> None:
        """Registra uma tool.

        Parâmetros:
            name: identificador único da tool (mesmo nome usado no protocolo MCP).
            handler: corrotina async que implementa a tool.
            schema: JSON Schema do inputSchema da tool.
            profiles: lista de profile_ids onde esta tool é relevante.
                      None significa disponível em todos os perfis.
            category: "read" | "write" | "diagnostic" | "readiness" | "general".
            description: descrição legível para o protocolo MCP.
        """
        if name in self._tools:
            logger.warning("ToolRegistry: tool '{}' re-registrada — sobrescrevendo.", name)
        self._tools[name] = {
            "name": name,
            "handler": handler,
            "schema": schema,
            "profiles": profiles,
            "category": category,
            "description": description,
        }
        logger.debug(
            "ToolRegistry: tool '{}' registrada (profiles={}, category='{}')",
            name,
            profiles,
            category,
        )

    def get_tools_for_profile(self, profile_id: str | None = None) -> list[dict]:
        """Retorna tools relevantes para o perfil, ou todas se profile_id=None.

        Uma tool é incluída quando:
        - profiles é None (disponível em todos os perfis), OU
        - profile_id é None (sem filtro ativo), OU
        - profile_id está contido em profiles.
        """
        result: list[dict] = []
        for entry in self._tools.values():
            tool_profiles: list[str] | None = entry["profiles"]
            if profile_id is None or tool_profiles is None or profile_id in tool_profiles:
                result.append(entry)
        return result

    def get_tool(self, name: str) -> dict | None:
        """Busca tool pelo nome. Retorna None se não registrada."""
        return self._tools.get(name)

    def list_all(self) -> list[str]:
        """Lista nomes de todas as tools registradas."""
        return list(self._tools.keys())
