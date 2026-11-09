"""Armazenamento local verificado de artefatos da E3 (fontes IFC/IDS e releases retidos).

Objetos são promovidos e verificados **antes** da transação que os referencia; não
há atomicidade conjunta entre disco e SQLite. Crash entre promoção e commit deixa só
objeto órfão, visível em ``inspect_orphans`` (somente leitura), nunca pin ou análise
aplicados. Nada é apagado automaticamente.
"""
