"""Portão da condição de ablação de grounding — sem GPU, ~2 min.

Implementa os critérios de aceitação de
``docs/condicao-ablacao-bsdd-2026-08-18.md`` §6. Roda ANTES de gastar máquina:
se qualquer critério falhar, a rodada é inválida por construção e não deve
ser executada.

Critérios verificados aqui:

1. os dois braços produzem prompts DIFERENTES em 100% dos estímulos — se algum
   for idêntico, o kill-switch não funcionou (foi o defeito da ablação
   abandonada em jun/26, que produzia execuções idênticas rotuladas como
   condições diferentes);
2. o TEMPLATE BASE é o mesmo nos dois braços: removido o bloco ``BSDD_CONTEXT``
   e normalizada a instrução de grounding do system prompt, os prompts têm de
   coincidir byte a byte. Qualquer estímulo que sobre invalida a rodada — seria
   tratamento confundido com roteamento;
3. ``prompt_sha256`` não muda (o arquivo de templates não é tocado) e o campo
   ``grounding_bsdd`` de fato altera ``canonical_identity_sha256``.

O critério de telemetria (``grounding_sources`` vazio no braço off) está
travado por teste unitário em ``tests/test_ablacao_bsdd.py``.

Uso:
    python scripts/dump_prompts_spy.py on.json
    python scripts/dump_prompts_spy.py off.json --no-bsdd
    python scripts/verifica_ablacao_bsdd.py on.json off.json
"""

# ruff: noqa: E402 — o sys.path.insert precisa vir antes dos imports de src/.

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from src.suggestion_engine.prompt_templates import (
    _GROUNDING_INSTRUCTION,
    SYSTEM_PROMPT,
)

_BSDD_HEADER = "BSDD_CONTEXT:"


def _strip_bsdd_block(user_prompt: str) -> str:
    """Remove APENAS o bloco BSDD_CONTEXT, preservando o resto do prompt.

    ``_inject_grounding`` anexa o bloco ao prompt que recebe, mas ``build_prompt``
    ainda acrescenta CRITERIO DE ENGENHARIA e REGRAS DE SAIDA **depois** — logo o
    bloco fica no MEIO, não no fim. Cortar do cabeçalho até o fim removeria
    também o rodapé do template e produziria divergência falsa.

    O bloco vai do cabeçalho até a primeira linha em branco que o sucede; a
    linha em branco que o precede vem do ``\\n\\n`` do injetor e sai junto.
    """
    linhas = user_prompt.splitlines()
    if _BSDD_HEADER not in linhas:
        return user_prompt.strip()
    inicio = linhas.index(_BSDD_HEADER)
    fim = inicio + 1
    while fim < len(linhas) and linhas[fim].strip() != "":
        fim += 1
    while inicio > 0 and linhas[inicio - 1].strip() == "":
        inicio -= 1
    return "\n".join(linhas[:inicio] + linhas[fim:]).strip()


def _normalize_system(system_prompt: str) -> str:
    """Neutraliza a instrução de grounding, que é parte declarada do tratamento."""
    return system_prompt.replace(_GROUNDING_INSTRUCTION, "").replace(
        SYSTEM_PROMPT, ""
    ).strip()


def main() -> int:
    """Executa os três critérios e devolve 0 apenas se todos passarem."""
    if len(sys.argv) < 3:
        print("uso: python scripts/verifica_ablacao_bsdd.py <on.json> <off.json>")
        return 2

    on = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    off = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    on1 = [c for c in on if c["attempt"] == 1]
    off1 = [c for c in off if c["attempt"] == 1]

    falhas: list[str] = []
    print(f"estimulos: on={len(on1)} off={len(off1)}")
    if len(on1) != len(off1):
        print("FALHA: numero de estimulos divergiu — o diagnose mudou entre os bracos")
        return 1

    # --- criterio 1: o tratamento chega a todo estimulo -------------------
    identicos = [
        b["issue_id"]
        for b, p in zip(on1, off1, strict=True)
        if b["system"] == p["system"] and b["user"] == p["user"]
    ]
    print(f"\n[1] prompts diferentes: {len(on1) - len(identicos)}/{len(on1)}")
    if identicos:
        falhas.append(
            f"criterio 1: {len(identicos)} estimulo(s) identicos nos dois bracos "
            f"(ex.: {identicos[:3]}) — kill-switch nao teve efeito"
        )

    # --- criterio 2: o roteamento NAO mudou -------------------------------
    residuo: list[tuple[str, str]] = []
    por_estrato_ok = Counter()
    for b, p in zip(on1, off1, strict=True):
        base_on = _strip_bsdd_block(b["user"])
        base_off = _strip_bsdd_block(p["user"])
        sys_on = _normalize_system(b["system"])
        sys_off = _normalize_system(p["system"])
        estrato = (
            f"{b['issue_type']}/{b['check_property']}"
            if b["check_property"]
            else b["issue_type"]
        )
        if base_on == base_off and sys_on == sys_off:
            por_estrato_ok[estrato] += 1
        else:
            residuo.append((b["issue_id"], estrato))

    print(f"[2] template base identico apos remover o bloco bSDD: "
          f"{len(on1) - len(residuo)}/{len(on1)}")
    for estrato, n in sorted(por_estrato_ok.items()):
        print(f"      {estrato}: {n}")
    if residuo:
        falhas.append(
            f"criterio 2: {len(residuo)} estimulo(s) com template base divergente "
            f"(ex.: {residuo[:3]}) — a familia de prompt mudou junto com o tratamento"
        )

    # --- criterio 3: identidade ------------------------------------------
    from dataclasses import replace as _replace

    sys.path.insert(0, str(PROJECT_ROOT / "tests"))
    from src.experiment.execution_identity import canonical_identity_sha256
    from tests.test_run_benchmark import official_identity

    com = official_identity()
    sem = _replace(com, grounding_bsdd=False)
    muda = canonical_identity_sha256(com) != canonical_identity_sha256(sem)
    print(f"[3] grounding_bsdd altera a identidade canonica: {muda}")
    if not muda:
        falhas.append("criterio 3: identidade nao distingue os bracos")

    prompt_file = PROJECT_ROOT / "src" / "suggestion_engine" / "prompt_templates.py"
    import hashlib

    sha = hashlib.sha256(prompt_file.read_bytes()).hexdigest()
    print(f"    prompt_templates.py sha256: {sha}")
    print("    (deve ser IGUAL ao prompt_sha256 da identidade da baseline)")

    print()
    if falhas:
        for falha in falhas:
            print(f"FALHA: {falha}")
        print("\n=> RODADA INVALIDA — nao gaste GPU antes de corrigir")
        return 1
    print("=> TODOS OS CRITERIOS PASSARAM — a ablacao mede o que declara medir")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
