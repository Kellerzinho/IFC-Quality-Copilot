.PHONY: install test test-cov lint format run-ui run-mcp clean

install:
	pip install -e ".[dev]"

test:
	pytest -v --tb=short

test-cov:
	pytest --cov=src --cov-report=html

lint:
	ruff check src/ tests/ && mypy src/

format:
	ruff format src/ tests/

run-ui:
	streamlit run src/ui/app.py

run-mcp:
	python -m src.mcp_server.server

clean:
	rm -rf __pycache__ .pytest_cache htmlcov/
