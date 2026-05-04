"""Script manual para inspecionar cobertura e formato da API bSDD."""

from pathlib import Path
import sys

from loguru import logger


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.bsdd.client import BSDDClient


TARGET_CLASSES = ["IfcWall", "IfcSpace", "IfcSlab"]


def _truncate(value: str, width: int) -> str:
    """Trunca texto longo para manter a tabela legivel."""
    if len(value) <= width:
        return value
    return value[: width - 3] + "..."


def _print_header() -> None:
    """Imprime o cabecalho da tabela."""
    print("=" * 140)
    print(f"{'Consulta':<12} {'Classe':<32} {'URI':<60} {'Props':>5}  Primeiras 5 propriedades")
    print("=" * 140)


def _print_row(query: str, class_name: str, uri: str, property_count: int, preview: str) -> None:
    """Imprime uma linha da tabela."""
    print(
        f"{query:<12} "
        f"{_truncate(class_name or '-', 32):<32} "
        f"{_truncate(uri or '-', 60):<60} "
        f"{property_count:>5}  "
        f"{preview or '-'}"
    )


def main() -> None:
    """Executa consultas reais ao bSDD e imprime um resumo legivel no terminal."""
    logger.remove()
    logger.add(sys.stderr, level="CRITICAL")
    client = BSDDClient()
    any_result = False

    try:
        print("Consultando a API publica do bSDD para entidades-alvo do projeto...\n")
        _print_header()

        for query in TARGET_CLASSES:
            class_results = client.search_class(query)
            if not class_results:
                _print_row(query, "sem resultados", "-", 0, "API offline, sem cobertura ou formato inesperado")
                continue

            any_result = True
            for item in class_results:
                class_name = str(item.get("name") or "-")
                class_uri = str(item.get("uri") or "-")
                properties = client.get_class_properties(class_uri) if class_uri != "-" else []
                property_names = [prop.name for prop in properties[:5]]
                preview = ", ".join(property_names) if property_names else "-"
                _print_row(query, class_name, class_uri, len(properties), preview)

        print("=" * 140)
        if not any_result:
            print("Nenhum resultado retornou do bSDD. A API pode estar offline ou indisponivel no momento.")
    finally:
        client.close()


if __name__ == "__main__":
    main()
