"""Sobe a API local: ``uv run python -m src.review_api [--port 8765]``.

O bind é sempre 127.0.0.1; não há opção de host.
"""

import argparse
from pathlib import Path

import uvicorn
from loguru import logger

from src.review_api.app import DEFAULT_PORT, create_app, default_data_root
from src.review_api.local_access import LOOPBACK_HOST


def main() -> None:
    """Lê argumentos e inicia o Uvicorn em loopback."""
    parser = argparse.ArgumentParser(description="API local de revisão M4 (127.0.0.1)")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--data-dir", type=Path, default=default_data_root())
    args = parser.parse_args()
    logger.info("API M4 em http://{}:{} — dados em {}", LOOPBACK_HOST, args.port, args.data_dir)
    uvicorn.run(
        create_app(args.data_dir, args.port),
        host=LOOPBACK_HOST,
        port=args.port,
        proxy_headers=False,
        server_header=False,
    )


if __name__ == "__main__":
    main()
