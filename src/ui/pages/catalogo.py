"""Página «catalogo» do shell Streamlit: curadoria do catálogo de domínio (M1-14, E5).

Descoberta automaticamente pelo Streamlit (pasta ``pages/`` ao lado de ``app.py``); não
altera a página principal. Toda a lógica está em ``src.ui.components.catalog_*`` e na
fachada ``src.domain_catalog.workspace``.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from src.ui.components.catalog_workspace import render_catalog_workspace  # noqa: E402

st.set_page_config(page_title="Catálogo — curadoria", layout="wide")
render_catalog_workspace()
