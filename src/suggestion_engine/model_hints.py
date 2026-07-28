"""Direcionamento de prompt por família de modelo (v6).

Calibrado pela análise de erros do benchmark 2026-07-28 (matriz top-10 ×
2 datasets, nível de estímulo). Cada família de LLM local falha de um jeito
próprio e reprodutível — colapso de moda no falcon3/lfm2.5, eco do CONTEXTO no
phi4-mini, classe de uma letra no mistral, nome hiperespecífico no qwen3.5 —
e o direcionamento aqui mira o MECANISMO da falha, nunca o conteúdo esperado.

Regra de ouro (mesma do guardrail de templates): os textos ensinam PROCESSO
(como usar a evidência dada, disciplina de formato, diversidade de hipóteses)
e jamais citam valores, faixas ou nomes presentes no ground truth. O teste
``tests/test_model_hints_nao_vaza_gabarito.py`` varre todos os textos deste
módulo contra os GTs congelados e falha em caso de vazamento.

O bloco é anexado ao final do prompt do usuário em
``SuggestionGenerator.generate`` — vale para os quatro caminhos de prompt —
e entra no ``prompt_hash`` registrado por sugestão.
"""

from __future__ import annotations

from src.models import Issue

_HINT_HEADER = "DIRECIONAMENTO DE PROCESSO (calibrado para esta família de modelo):"

# ---------------------------------------------------------------------------
# Textos reutilizáveis — processo e formato, sem conteúdo de gabarito
# ---------------------------------------------------------------------------

_EVIDENCIA_ESPECIFICA = (
    "Cada opção deve citar na justificativa a evidência DESTE espaço que a sustenta "
    "(elemento contido, área ou dimensão); ordene as opções pela força dessa evidência, "
    "não pela frequência do tipo de ambiente em edifícios em geral."
)

_NOME_DE_PROJETO = (
    "As classes de função da seção INFERÊNCIA são etapa intermediária de raciocínio; o "
    "campo de resposta recebe o nome usual de projeto — curto, como um projetista "
    "rotularia a planta. Qualificações técnicas adicionais pertencem à justificativa."
)

_ESCOPO_RECINTO = (
    "O nome pedido é o do RECINTO específico desta issue, derivado exclusivamente do "
    "mobiliário, da área e das dimensões em DADOS; a linha CONTEXTO descreve a "
    "edificação inteira e serve apenas de pano de fundo."
)

_FOGO_LETRA = (
    "Monte a classe em duas decisões declaradas na justificativa: o elemento fecha ou "
    "separa ambientes? Então E e I aparecem JUNTOS na classe. Sustenta carga além do "
    "peso próprio (inclui escadas e lajes estruturais)? Então R entra. Pilar e viga "
    "isolados ficam só com R."
)

_FOGO_MINUTOS = (
    "Escolha os minutos a partir do TRRF que a NBR 14432 (Tab. A.1) atribui ao uso e "
    "porte do CONTEXTO, declarando essa referência na justificativa; as 3 opções devem "
    "representar hipóteses distintas, cada uma dizendo o que a diferencia das demais."
)

_TERMICO_MEMORIA = (
    "O campo valor é exatamente 1/R_total da memória de cálculo montada com as camadas "
    "informadas — escreva a soma numérica na justificativa. Limite normativo é critério "
    "de aprovação, não estimativa: o resultado calculado pode reprovar no limite."
)

_TERMICO_ORDEM_DE_GRANDEZA = (
    "Antes de responder, confira a ordem de grandeza: λ é propriedade do material e "
    "nunca é a resposta; como Rsi+Rse já entram na soma, elemento sem camada isolante "
    "resulta em U na ordem de unidades. Conta em décimos indica resistência inventada; "
    "em dezenas ou mais, erro de unidade de espessura — refaça a soma."
)

_TERMICO_SEM_EXTRAS = (
    "R_total é somente Rsi + Σ(e/λ) das camadas LISTADAS + Rse, com os Rsi/Rse do fluxo "
    "indicado e os λ da tabela do prompt; nenhuma resistência adicional entra na soma."
)

_SISTEMA_ROTULO_LITERAL = (
    "O campo sistema recebe um rótulo copiado literalmente da lista do VOCABULÁRIO "
    "FECHADO. O nome/tipo do objeto no modelo e termos iniciados em 'Ifc' são dados de "
    "partida; a resposta é o rótulo da lista que melhor os traduz. Escolha a 1ª opção "
    "pelo núcleo estrutural das camadas informadas; revestimento é opção secundária."
)

_CATEGORY_TOKEN_TEXTUAL = (
    "O campo valor recebe um token TEXTUAL copiado da lista de CATEGORIAS VÁLIDAS, com "
    "o sublinhado fazendo parte do token. Números presentes em DADOS (área, nome "
    "numérico do recinto) são medidas e identificadores; a categoria vem do LongName e "
    "dos elementos contidos."
)

# ---------------------------------------------------------------------------
# Mapa família → estrato → hints
# ---------------------------------------------------------------------------

_FIRE = "pset_missing/FireRating"
_THERMAL = "pset_missing/ThermalTransmittance"
_CATEGORY = "pset_missing/Category"
_SPACE = "space_unnamed"
_SYSTEM = "system_unclassified"

# Chave: tag exata do Ollama ("qwen3.5:4b") ou família (antes do ":").
# A tag exata tem precedência por estrato — qwen3.5:4b e :9b, por exemplo,
# compartilham a patologia de nome hiperespecífico mas divergem no fogo.
_HINTS: dict[str, dict[str, tuple[str, ...]]] = {
    # Colapso de moda no espaço/Category (escada fixa de ambientes; OFFICE/KITCHEN),
    # eco de números do contexto no térmico (valores absurdos), escada fixa no fogo.
    "falcon3": {
        _SPACE: (_EVIDENCIA_ESPECIFICA,),
        _CATEGORY: (_EVIDENCIA_ESPECIFICA,),
        _FIRE: (_FOGO_LETRA, _FOGO_MINUTOS),
        _THERMAL: (_TERMICO_MEMORIA, _TERMICO_ORDEM_DE_GRANDEZA),
        _SYSTEM: (_SISTEMA_ROTULO_LITERAL,),
    },
    # Colapso de moda extremo (Category quase toda numa única classe; espaço na
    # escada fixa) e eco do nome do objeto como sistema.
    "lfm2.5": {
        _CATEGORY: (_EVIDENCIA_ESPECIFICA, _CATEGORY_TOKEN_TEXTUAL),
        _SPACE: (_EVIDENCIA_ESPECIFICA,),
        _SYSTEM: (_SISTEMA_ROTULO_LITERAL,),
        _FIRE: (_FOGO_LETRA,),
        _THERMAL: (_TERMICO_MEMORIA,),
    },
    # Nomeia o espaço com a linha CONTEXTO da edificação; R em tudo no fogo;
    # subestimativa profunda no térmico; eco do nome do objeto como sistema.
    "phi4-mini": {
        _SPACE: (_ESCOPO_RECINTO, _EVIDENCIA_ESPECIFICA),
        _CATEGORY: (_EVIDENCIA_ESPECIFICA,),
        _FIRE: (_FOGO_LETRA, _FOGO_MINUTOS),
        _THERMAL: (_TERMICO_MEMORIA, _TERMICO_ORDEM_DE_GRANDEZA),
        _SYSTEM: (_SISTEMA_ROTULO_LITERAL,),
    },
    # Classes de uma letra (E/R) no fogo; classes Ifc inventadas como sistema;
    # grandezas caóticas no térmico (duas ordens de grandeza para os dois lados).
    "mistral": {
        _FIRE: (_FOGO_LETRA, _FOGO_MINUTOS),
        _SYSTEM: (_SISTEMA_ROTULO_LITERAL,),
        _THERMAL: (_TERMICO_MEMORIA, _TERMICO_ORDEM_DE_GRANDEZA),
        _CATEGORY: (_CATEGORY_TOKEN_TEXTUAL,),
        _SPACE: (_EVIDENCIA_ESPECIFICA,),
    },
    # Subestimativa sistemática de 10-20% no térmico (resistências a mais na
    # soma); escada R 30/60/90 no fogo; SERVICE_AREA como categoria coringa.
    "granite4": {
        _THERMAL: (_TERMICO_MEMORIA, _TERMICO_SEM_EXTRAS),
        _FIRE: (_FOGO_LETRA, _FOGO_MINUTOS),
        _CATEGORY: (_EVIDENCIA_ESPECIFICA,),
        _SPACE: (_EVIDENCIA_ESPECIFICA,),
    },
    # EI em escada portante e E isolado; metade do térmico em subestimativa
    # profunda; LIVING_ROOM/TECHNICAL_AREA como categorias coringa.
    "llama3.1": {
        _FIRE: (_FOGO_LETRA, _FOGO_MINUTOS),
        _THERMAL: (_TERMICO_MEMORIA,),
        _CATEGORY: (_EVIDENCIA_ESPECIFICA,),
        _SPACE: (_EVIDENCIA_ESPECIFICA,),
    },
    # Escada EI 60/90/120 fixa no fogo; no espaço devolve a classe de função da
    # INFERÊNCIA como nome final; térmico ancorado no limite normativo.
    "qwen2.5": {
        _FIRE: (_FOGO_LETRA, _FOGO_MINUTOS),
        _SPACE: (_NOME_DE_PROJETO, _EVIDENCIA_ESPECIFICA),
        _CATEGORY: (_EVIDENCIA_ESPECIFICA,),
        _THERMAL: (_TERMICO_MEMORIA,),
    },
    # Família qwen3.5: nome hiperespecífico no espaço (qualificação técnica no
    # campo de nome). O 4b é o melhor do fogo (sem hint lá); o 9b colapsa em EI
    # e ecoa números do contexto como Category — cobertos na tag exata.
    "qwen3.5": {
        _SPACE: (_NOME_DE_PROJETO,),
        _CATEGORY: (_EVIDENCIA_ESPECIFICA,),
        _THERMAL: (_TERMICO_MEMORIA,),
    },
    "qwen3.5:9b": {
        _FIRE: (_FOGO_LETRA, _FOGO_MINUTOS),
        _CATEGORY: (_CATEGORY_TOKEN_TEXTUAL,),
    },
    # Melhor modelo geral: só disciplina leve onde ainda erra (grafia do token
    # de Category; térmico ancorado no limite; minutos do fogo).
    "gemma2": {
        _CATEGORY: (_CATEGORY_TOKEN_TEXTUAL,),
        _THERMAL: (_TERMICO_MEMORIA,),
        _FIRE: (_FOGO_MINUTOS,),
    },
}


def _stratum_key(issue: Issue) -> str:
    """Chave de estrato da issue: ``issue_type/check_property`` ou ``issue_type``."""
    check_property = str(issue.context.get("check_property") or "").strip()
    if check_property:
        return f"{issue.issue_type}/{check_property}"
    return issue.issue_type


def _lookup_keys(model_name: str) -> tuple[str, str]:
    """Retorna (tag exata, família) normalizadas para busca no mapa."""
    tag = (model_name or "").strip().casefold()
    family = tag.split(":", 1)[0]
    return tag, family


def hints_for(model_name: str, issue: Issue) -> str | None:
    """Bloco de direcionamento para (modelo, issue), ou None se não houver.

    A tag exata do modelo tem precedência sobre a família no mesmo estrato;
    quando só a família define o estrato, vale a família. Modelos fora do mapa
    não recebem bloco algum — o prompt fica idêntico ao dos templates.
    """
    tag, family = _lookup_keys(model_name)
    stratum = _stratum_key(issue)

    textos = (
        _HINTS.get(tag, {}).get(stratum)
        or _HINTS.get(family, {}).get(stratum)
    )
    if not textos:
        return None

    linhas = "\n".join(f"- {texto}" for texto in textos)
    return f"{_HINT_HEADER}\n{linhas}"


def all_hint_texts() -> list[str]:
    """Todos os textos de hint (para o guardrail de vazamento de gabarito)."""
    textos: list[str] = [_HINT_HEADER]
    for strata in _HINTS.values():
        for hints in strata.values():
            textos.extend(hints)
    return textos
