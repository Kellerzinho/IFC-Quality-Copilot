"""Autoridade operacional local mínima da E3 (M6 mínimo; integração opt-in).

Um banco SQLite por instalação (``operations.sqlite3``) guarda atores locais,
projetos, fontes retidas, pares IFC–IDS, pins de catálogo, análises, diagnósticos,
enriquecimentos, cache de contexto, comandos e eventos na mesma transação. Não é o
M6 inteiro: não há contas, autenticação, daemon, backup nem distribuição. Importar
este pacote não abre banco nem recupera análises.
"""
