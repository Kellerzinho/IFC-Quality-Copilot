"""Diff estruturado entre dois dumps de prompt do espião (scripts/dump_prompts_spy.py).

Compara só a 1ª tentativa de cada estímulo, alinhando por ordem de diagnose
(determinística), e reporta: estímulos idênticos/mudados, mudanças por estrato,
linhas adicionadas/removidas agregadas e um exemplo por estrato. É a prova
empírica de "o instrumento mudou/não mudou" sem gastar GPU.

Uso:
    python scripts/diff_prompts.py <baseline.json> <pos.json>
"""

import difflib
import json
import sys
from collections import Counter
from pathlib import Path

# Os prompts têm λ, ², acentos; o console do Windows é cp1252 por padrão e
# quebraria a impressão do diff.
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

base_path, pos_path = sys.argv[1], sys.argv[2]
base = json.loads(Path(base_path).read_text(encoding="utf-8"))
pos = json.loads(Path(pos_path).read_text(encoding="utf-8"))

# Só a 1ª tentativa de cada estímulo (retries repetem o prompt com corretivo)
base1 = [c for c in base if c["attempt"] == 1]
pos1 = [c for c in pos if c["attempt"] == 1]
print(f"estimulos: baseline={len(base1)} pos={len(pos1)}")

assert len(base1) == len(pos1), "n de estimulos divergiu — diagnose mudou!"

iguais = 0
mudados = []
for b, p in zip(base1, pos1, strict=True):
    assert b["issue_id"] == p["issue_id"], f"ordem divergiu em {b['issue_id']}"
    if b["system"] == p["system"] and b["user"] == p["user"]:
        iguais += 1
    else:
        mudados.append((b, p))

print(f"identicos: {iguais}/{len(base1)}  mudados: {len(mudados)}")

por_estrato = Counter(
    f"{b['issue_type']}/{b['check_property']}" if b["check_property"] else b["issue_type"]
    for b, _ in mudados
)
print("\nmudancas por estrato:")
for estrato, n in por_estrato.most_common():
    print(f"  {estrato}: {n}")

# Linhas adicionadas/removidas agregadas (o que exatamente entrou no prompt)
added = Counter()
removed = Counter()
for b, p in mudados:
    for campo in ("system", "user"):
        diff = difflib.unified_diff(
            b[campo].splitlines(), p[campo].splitlines(), lineterm="", n=0
        )
        for line in diff:
            if line.startswith("+") and not line.startswith("+++"):
                added[line[1:].strip()] += 1
            elif line.startswith("-") and not line.startswith("---"):
                removed[line[1:].strip()] += 1

print("\nlinhas ADICIONADAS (agregado):")
for line, n in added.most_common(20):
    print(f"  {n:4d}x | {line[:110]}")
print("\nlinhas REMOVIDAS (agregado):")
for line, n in removed.most_common(20):
    print(f"  {n:4d}x | {line[:110]}")

# Exemplo completo de um estimulo mudado (primeiro de cada estrato)
vistos = set()
print("\n=== exemplos (1 por estrato) ===")
for b, p in mudados:
    estrato = f"{b['issue_type']}/{b['check_property']}"
    if estrato in vistos:
        continue
    vistos.add(estrato)
    print(f"\n--- {estrato} ({b['issue_id']}) ---")
    for campo in ("system", "user"):
        diff = list(
            difflib.unified_diff(
                b[campo].splitlines(), p[campo].splitlines(), lineterm="", n=1
            )
        )
        if diff:
            print(f"[{campo}]")
            print("\n".join(diff[:25]))
