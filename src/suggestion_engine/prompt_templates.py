"""Templates de prompt e parser de resposta LLM para o SuggestionGenerator."""

import json
import re
from collections import defaultdict
from typing import Any, TYPE_CHECKING

from loguru import logger

from src.models import BSDDContext, IDSContext, Issue, Suggestion
from src.semantic.property_match import properties_match

if TYPE_CHECKING:
    from src.suggestion_engine.grounding import GroundedIssueContext

# v4: contrato genérico não é mais anexado ao template de space_unnamed
# (só o prompt de nomeação muda entre v3 e v4; demais tarefas são idênticas).
# v6: evidência de LongName no Category, procedimento TRRF no fogo, memória de
# cálculo obrigatória no térmico e desambiguação de mobiliário na nomeação —
# evidência + direcionamento GENÉRICO, idêntico para todos os modelos (a
# diferença entre LLMs é o objeto de medição; ver análise do run 2026-07-28).
# v6.1: correção do matcher de propriedades bSDD (revisão 2026-08-04) — o nome
# humano do bSDD ("Fire Rating") passou a casar com check_property, então
# tipo/unidade do dicionário podem alcançar prompt e assinatura de cache, e a
# validação pós-LLM contra o vocabulário deixou de ser no-op. NÃO altera os
# blocos de TRRF nem a memória de cálculo; condição não medida em benchmark.
# v7 (2026-08-04, CONDIÇÃO DECLARADA — escolhida DEPOIS de ver a matriz v6):
# mantém a evidência que pagou (+31,2 pp no Category) e desfaz os dois blocos de
# PROCEDIMENTO que custaram (−12,5 pp no fogo, −8,4 pp no térmico). No térmico a
# instrução de calcular é substituída pelo contrato de memória ESTRUTURADA: o LLM
# declara camadas e λ, e a aritmética passa a ser executada por
# src/suggestion_engine/thermal_recompute.py. Ver docs/condicao-v7-2026-08-04.md.
# v7.1 (2026-08-04, tarde): duas correções abertas pelo smoke do v7, ambas do
# tipo "o prompt estava entregando errado", nenhuma mudança de método.
#   P0 — contrato único: os 20 templates já declaram o próprio formato JSON e o
#        bloco anexado no fim declarava um schema DIFERENTE; o modelo seguia o
#        último e devolvia prosa no lugar do número (11 rejeições × 0 no v6).
#        Agora o bloco traz REGRAS, que não nomeiam campos.
#   P1 — montante metálico como evidência: a camada interna de metal chega ao
#        prompt anotada como câmara de ar (R = 0,17), em vez de depender da
#        instrução em prosa que o modelo ignorava em favor da tabela de λ.
# Atribuição no dataset: P1 só toca estímulos de parede com camada metálica
# interna (1 estímulo, 222 issues); qualquer outro movimento é P0.
# v7.2 (2026-08-04): desambigua a RESTRICAO do template de fogo. Correcao de
# FORMATO, nao de raciocinio — o defeito sempre existiu e so ficou visivel
# quando o P0 tirou o ruido do schema duplicado.
# v7.3 (2026-08-09): remove limites numericos do template termico que passaram
# a colidir com hipoteses congeladas no ground truth integral. O criterio
# normativo permanece descrito, sem entregar ao modelo um valor de referencia.
# v7.4 (2026-08-10): duas correcoes do que o v7.3 deixou pela metade. (1) A
# edicao do template de laje amputou o objeto do verbo e o estimulo passou a
# dizer "a NBR 15575-5 exige Os limites normativos dependem..." em 18 estimulos;
# frase reescrita. (2) O exemplar JSON do template solar trazia "valor": 0.87,
# que e o valor esperado em 100% dos 134 itens de SolarHeatGainCoefficient —
# trocado por placeholder, como ja faziam os demais templates. A tabela
# tipologica de vidros FICA: e a unica evidencia do estimulo (o IFC nao declara
# o vidro). Ver docs/condicao-v7-4-2026-08-10.md.
# v7.5 (2026-08-10): o template acustico ensinava a letra da classe de
# desempenho ("'D' ou '35 dB'") e o ground truth so pontua "Rw NN dB" — o
# gemma2 respondeu 'D' em 18/18 estimulos e o estrato zerou por incompatibilidade
# de contrato, nao por erro de decisao. O prompt passa a cobrar a notacao que o
# GT pontua, com a classe D/M/S explicitamente marcada como raciocinio e nao
# resposta. Do outro lado, o GT ganhou banda de equivalencia de +/-5 dB.
# Ver docs/condicao-gt-equivalencias-2026-08-10.md.
# v7.6 (2026-08-12): fechamento do instrumento apos a rodada oficial v7.5. Todas
# as mudancas sao de EVIDENCIA (dado que ja estava no IFC e nao chegava ao
# modelo), VOCABULARIO GENERICO (tipologia de literatura ou classe de schema,
# independente do elemento avaliado) ou FORMATO. Nenhuma entrega resposta.
#   (1) Acustico: o estrato media "desafiar a tabela injetada". As 3 linhas
#       cobriam so parede macica, e porta — 214 itens — nao tinha nenhuma linha:
#       o menor valor ofertado era Rw 35 e a banda do GT para porta termina em
#       30, entao acertar exigia contrariar o estimulo. Entram duas linhas
#       tipologicas de literatura (porta de madeira, drywall simples) e a
#       evidencia que faltava (camadas e PredefinedType) — era o template mais
#       pobre em dado de arquivo do conjunto.
#   (2) relation_broken: os dois templates pediam ACOES DE CORRECAO em prosa
#       enquanto o GT pontua o nome da classe de relacao; o de porta ainda
#       semeava a resposta no exemplar, e o ramo de space boundary afirmava o
#       nome ERRADO da relacao ausente. 0,00 em 10/10 modelos era artefato de
#       contrato. Passa a haver um template unico que descreve o sintoma e cobra
#       a classe, com vocabulario fechado do schema IFC.
#   (3) HasNonSkidSurface saiu do template de funcao portante — recebia a tabela
#       de LoadBearing (FLOOR->True, ROOF->False) numa pergunta sobre piso
#       antiderrapante. Ganha template proprio, sem mapa de escada->valor.
#   (4) IsLoadBearing/LoadBearing e system_unclassified recebem evidencia
#       agregada do modelo (quantos pilares e vigas o arquivo declara): permite
#       distinguir portico de alvenaria portante sem expor o alias do elemento,
#       que e a resposta. O template de sistema tambem passa a receber a funcao
#       estrutural que os demais ja recebiam — a omissao explica o erro de
#       vedacao->estrutural em 262 itens.
#   (5) Formato: espessura de camada era arredondada para centimetro inteiro
#       (1,5 cm virava "2cm"), o que contradizia a espessura total no mesmo
#       prompt e consumia a banda de 10% do termico antes de qualquer erro do
#       modelo; floats crus de espessura e area chegavam com ruido binario.
# Ver docs/condicao-v7-6-2026-08-12.md.
# v7.8 (2026-08-19): correcoes de EMPACOTAMENTO de grounding medidas pela ablacao
# de bSDD (docs/resultado-ablacao-bsdd-2026-08-19.md). O braco sem bSDD ganhou
# +2,34 pp por classe (McNemar p=0,00022) e +50 pp em relation_broken; a causa
# nao era o conteudo do dicionario, era como o bloco era montado e anunciado.
# Nenhum template foi tocado — o estimulo por issue nao muda de conteudo.
#   (1) Escopo: sem check_property, a lista de propriedades da classe nao entra
#       no bloco. Em relation_broken ela era o catalogo inteiro do IfcDoor
#       (42.473 chars contra 434 do bloco mediano), estourava a janela e o
#       servidor cortava o INICIO — onde esta a pergunta. Os dez modelos
#       respondiam tokens colhidos do proprio bloco (BARREL, TEU, PASSENGER).
#   (2) Instrucao de obediencia condicionada a existir vocabulario fechado.
#       "Use apenas o vocabulario fornecido" sobre um bloco que imprime "livre"
#       encolhia a resposta para o literal (EI 30 no lugar da banda EI/REI 60).
#   (3) Teto declarado de propriedades no bloco, como defesa em profundidade.
# Ver docs/condicao-v7-8-2026-08-19.md.
PROMPT_VERSION = "v7.8"

_MEMORIA_ESTRUTURADA_BR = (
    "MEMÓRIA ESTRUTURADA (obrigatória): declare no campo memoria_calculo as camadas "
    "que você identificou, com espessura_m e λ de cada uma, mais rsi e rse.\n"
    "  A SOMA e a divisão são feitas pelo sistema: você NÃO precisa fechar a conta, "
    "e o valor final vem dos termos que você declarar.\n"
    "  Camada sem espessura definida (câmara de ar não ventilada) entra com "
    "\"resistencia\" em vez de espessura_m/λ.\n"
    "  λ é propriedade do material, nunca a resposta.\n"
)

# Anexado ao contrato genérico SÓ em ThermalTransmittance (condição v7): o
# contrato é a última coisa que o LLM lê e precisa repetir o pedido da memória.
_MEMORIA_CONTRACT_SUFFIX = (
    ' Inclua tambem "memoria_calculo": {"rsi":<numero>,"camadas":'
    '[{"material":"...","espessura_m":<numero>,"lambda":<numero>}],"rse":<numero>}'
    " em cada opcao: a soma e feita pelo sistema a partir desses termos."
)

SYSTEM_PROMPT_COMPACT = (
    "Voce e um engenheiro BIM/IFC criterioso. Analise as evidencias fornecidas, "
    "nao corrija valores por suposicao e responda APENAS com JSON valido."
)

SYSTEM_PROMPT = (
    "Você é um engenheiro civil brasileiro especialista em BIM, IFC e desempenho "
    "de edificações conforme a NBR 15575. Responda sempre em JSON válido, sem markdown, "
    "sem explicações fora do JSON."
)

_COMPACT_OUTPUT_CONTRACT = (
    'Retorne JSON: {"opcoes":[{"issue_id":"...","action":"suggest_value|review_required|abstain",'
    '"suggested_value":...,"canonical_term":"...","semantic_hint":"...",'
    '"confidence":"alta|media|baixa","justification":"<=120 chars","review_required":true|false}]}.'
    " Retorne 3 opcoes distintas sempre que houver candidatos plausiveis (minimo 1). Nao retorne URI."
    " Nunca retorne lista de opcoes vazia nem suggested_value vazio: se nenhum candidato for"
    " confiavel, proponha o melhor valor disponivel e marque review_required=true."
    " Ordene opcoes por confianca decrescente. Nao trate diferenca de espessura, material ou dimensao como erro de digitacao."
)

# Nomear ambiente nao e escolher termo de vocabulario: pedir canonical_term /
# semantic_hint desviava o LLM para pseudo-classes IFC ("IfcKitchen") e zerou a
# acuracia top-1 da tarefa de nomeacao no benchmark. O contrato abaixo vale em
# TODOS os caminhos de prompt (legacy, compacto, grounded e router).
_SPACE_NAME_OUTPUT_CONTRACT = (
    'Retorne JSON: {"opcoes":[{"issue_id":"...","nome":"...",'
    '"confidence":"alta|media|baixa","justification":"<=120 chars","review_required":true|false}]}.'
    " Retorne exatamente 3 opcoes distintas, ordenadas por confianca decrescente. Nao retorne URI."
    " IMPORTANTE: o campo 'nome' deve ser o nome funcional do ambiente em portugues"
    " (ex.: 'Sala de Estar', 'Banheiro Social'), nunca classe IFC, termo tecnico ou identificador."
    " Nunca deixe 'nome' vazio e nunca use placeholders como 'Review Required', 'N/A' ou"
    " 'Desconhecido': mesmo com pouca evidencia, proponha os nomes mais plausiveis e sinalize"
    " a incerteza com review_required=true e confidence=baixa."
)


def output_contract_for(issue_type: str, *, include_calc_memory: bool = False) -> str:
    """Retorna o contrato de saida da tarefa, unico para todos os prompts.

    Centralizar aqui evita que um caminho de prompt peca um contrato e outro
    peca outro para a mesma tarefa — divergencia que muda o comportamento do
    LLM sem aparecer em nenhum teste.

    ``include_calc_memory`` existe por causa do contrato v7 do termico: o
    contrato generico e anexado DEPOIS do template e e o que o LLM le por
    ultimo; se ele nao citar ``memoria_calculo``, o campo tende a nao voltar e a
    camada deterministica fica sem o que recomputar. Quem decide e o chamador,
    via ``uses_layered_thermal_template`` — nao basta ser ThermalTransmittance.
    """
    if issue_type == "space_unnamed":
        return _SPACE_NAME_OUTPUT_CONTRACT
    if include_calc_memory:
        return _COMPACT_OUTPUT_CONTRACT + _MEMORIA_CONTRACT_SUFFIX
    return _COMPACT_OUTPUT_CONTRACT


def uses_layered_thermal_template(issue: Issue) -> bool:
    """True quando a issue calcula U somando camadas (parede, laje, cobertura).

    Esquadria fica de FORA de proposito: seu U vem de valor de REFERENCIA
    (vidro + caixilho), nao de soma de camadas — o template de esquadria nunca
    pediu memoria de calculo, e no run v6 esse estrato ja acertava dentro de
    3,5%. Pedir memoria ali seria alargar a condicao v7 para uma tarefa que ela
    nao mira.
    """
    if issue.issue_type != "pset_missing":
        return False
    return _specialized_pset_template_key(issue) in {
        "pset_missing_thermal",
        "pset_missing_u_value_slab",
    }


def build_compact_prompt(grounded: "GroundedIssueContext") -> tuple[str, str]:
    """Monta prompt mínimo a partir de GroundedIssueContext.

    Retorna (system_prompt, user_prompt). Sem texto normativo extenso,
    sem few-shot, sem pedido de URI oficial.
    """
    lines: list[str] = [
        f"issue_id: {grounded.issue_id}",
        f"tipo: {grounded.issue_type}",
        f"classe: {grounded.ifc_class}",
        f"guid: {grounded.global_id[:8]}",
    ]
    if grounded.element_name:
        lines.append(f"elemento: {grounded.element_name}")
    if grounded.canonical_pset:
        lines.append(f"pset_alvo: {grounded.canonical_pset}")
    if grounded.canonical_property:
        lines.append(f"propriedade: {grounded.canonical_property}")
    if grounded.expected_datatype:
        lines.append(f"tipo_dado: {grounded.expected_datatype}")
    if grounded.expected_unit:
        lines.append(f"unidade: {grounded.expected_unit}")
    if grounded.expected_value is not None:
        lines.append(f"valor_esperado: {grounded.expected_value}")
    if grounded.current_value is not None:
        lines.append(f"valor_atual: {grounded.current_value}")
    if grounded.requirement_summary:
        lines.append(f"requisito: {grounded.requirement_summary}")
    # A classe oficial resolvida no bSDD e grounding por si so: comunica-la ao LLM
    # importa mesmo quando nao ha lista de candidatos (caso de space_unnamed, cujos
    # candidatos viriam de classificacoes que o dicionario pode nao ter).
    if grounded.official_class:
        linha_classe = f"classe_bsdd: {grounded.official_class}"
        if grounded.official_class_uri:
            linha_classe += f" ({grounded.official_class_uri})"
        lines.append(linha_classe)
    if grounded.official_candidates:
        cand = ", ".join(grounded.official_candidates[:12])
        lines.append(f"candidatos: {cand}")
        lines.append("instrucao: escolha entre os candidatos acima quando aplicavel.")
    else:
        lines.append("candidatos: (nenhum oficial; use review_required=true se incerto)")
    if grounded.relevant_constraints:
        lines.append("restricoes: " + "; ".join(grounded.relevant_constraints))

    lines.append(
        "criterio: nao presuma que diferencas de espessura, material, dimensao ou tipo "
        "sejam erro de digitacao; use esses dados para diferenciar elementos."
    )
    lines.append("")
    lines.append(output_contract_for(grounded.issue_type))
    return SYSTEM_PROMPT_COMPACT, "\n".join(lines)


def _element_context_lines(grounded: "GroundedIssueContext") -> list[str]:
    """Formata o contexto rico do elemento (Fase A.1) para o prompt grounded."""
    lines: list[str] = []
    if grounded.material_layers:
        lines.append(f"camadas_material: {_format_material_layers(grounded.material_layers)}")
    elif grounded.material_name:
        lines.append(f"material: {grounded.material_name}")
    if grounded.thickness_m is not None:
        lines.append(f"espessura_total_m: {grounded.thickness_m}")
    if grounded.predefined_type:
        lines.append(f"predefined_type: {grounded.predefined_type}")
    if grounded.is_external is not None:
        lines.append(f"is_external: {grounded.is_external}")
    if grounded.floor:
        lines.append(f"pavimento: {grounded.floor}")
    if grounded.existing_psets:
        lines.append(f"psets_existentes: {', '.join(grounded.existing_psets[:8])}")
    return lines


def build_pset_grounded_prompt(grounded: "GroundedIssueContext") -> tuple[str, str]:
    """Template ``pset_missing_generic_grounded`` (Fase A.1).

    Prompt para issues ``pset_missing`` sem template especializado, COM grounding.
    Injeta vocabulário fechado do bSDD (allowed_values, data_type, unit), contexto
    rico do elemento (material, espessura, PredefinedType, IsExternal, pavimento),
    requisito IDS e contrato JSON compacto. Comportamento por cenário:

    - bSDD com allowed_values → vocabulário fechado ("escolha APENAS entre os
      valores permitidos"); sugestão fora do vocabulário é rebaixada/descartada
      na validação (``_validate_against_bsdd``).
    - bSDD só com data_type/unit → valor tipado + justificativa técnica;
      ``review_required=true`` se a confiança não for alta.
    - bSDD vazio/offline → abstenção preferível a chute: justificativa
      obrigatória e ``review_required=true`` por padrão.

    Retorna (system_prompt, user_prompt).
    """
    lines: list[str] = [
        f"issue_id: {grounded.issue_id}",
        "tipo: pset_missing",
        f"classe: {grounded.ifc_class}",
        f"guid: {grounded.global_id[:8]}",
    ]
    if grounded.element_name:
        lines.append(f"elemento: {grounded.element_name}")

    lines.extend(_element_context_lines(grounded))

    lines.append("")
    lines.append("REQUISITO IDS:")
    if grounded.canonical_pset:
        lines.append(f"pset_alvo: {grounded.canonical_pset}")
    if grounded.canonical_property:
        lines.append(f"propriedade: {grounded.canonical_property}")
    if grounded.expected_datatype:
        lines.append(f"tipo_dado: {grounded.expected_datatype}")
    if grounded.expected_unit:
        lines.append(f"unidade: {grounded.expected_unit}")
    if grounded.expected_value is not None:
        lines.append(f"valor_esperado: {grounded.expected_value}")
    if grounded.current_value is not None:
        lines.append(f"valor_atual: {grounded.current_value}")
    if grounded.relevant_constraints:
        lines.append("restricoes: " + "; ".join(grounded.relevant_constraints))
    if grounded.requirement_summary:
        lines.append(f"requisito: {grounded.requirement_summary}")

    lines.append("")
    if grounded.official_candidates:
        # Cenário 1: vocabulário fechado do bSDD
        lines.append("VALORES PERMITIDOS (bSDD): " + ", ".join(grounded.official_candidates[:12]))
        lines.append(
            "instrucao: escolha suggested_value APENAS entre os valores permitidos acima. "
            "Valor fora do vocabulario sera descartado. Se nenhum valor permitido couber, "
            "use review_required=true e explique na justification."
        )
    elif grounded.expected_datatype or grounded.expected_unit:
        # Cenário 2: sem vocabulário, mas com tipo/unidade
        tipo = grounded.expected_datatype or "definido pelo IDS"
        unidade = f" em {grounded.expected_unit}" if grounded.expected_unit else ""
        lines.append(
            f"instrucao: sugira valor TIPADO ({tipo}{unidade}) com justificativa tecnica "
            "baseada no material, espessura e classe do elemento. "
            "Use review_required=true sempre que a confianca nao for alta."
        )
    else:
        # Cenário 3: bSDD vazio/offline — abstenção preferível a chute
        lines.append(
            "instrucao: NAO ha vocabulario oficial disponivel (bSDD vazio/offline). "
            "Prefira abster-se: use review_required=true por padrao em toda opcao, "
            "justifique tecnicamente qualquer valor proposto e nunca invente valores "
            "sem base no material/espessura/classe informados."
        )

    lines.append(
        "criterio: nao presuma que diferencas de espessura, material, dimensao ou tipo "
        "sejam erro de digitacao; use esses dados para diferenciar elementos."
    )
    lines.append("")
    lines.append(output_contract_for(grounded.issue_type))
    return SYSTEM_PROMPT_COMPACT, "\n".join(lines)

_GROUNDING_INSTRUCTION = (
    "Se houver contexto IDS ou bSDD, use apenas o vocabulário e os requisitos fornecidos. "
    "Nunca invente URI, código de classificação ou valor fora do vocabulário permitido."
)

_LLM_OUTPUT_CONTRACT = (
    'Responda APENAS em JSON no formato { "opcoes": [ { '
    '"label": "...", "canonical_term": "...", "semantic_hint": "...", '
    '"source_candidates": ["..."], "confidence": "alta"|"media"|"baixa", '
    '"justification": "...", "review_required": true|false, '
    '"value": ... | null, "normative_ref": ... | null } ] }. '
    "Nunca retorne URI final como verdade semantica."
)
"""Schema completo — só para caminhos cujo prompt NÃO declara formato próprio."""

# Os 20 templates ricos ja declaram o proprio formato JSON. Colar um schema
# DIFERENTE no fim do prompt fazia o modelo seguir o ultimo que leu: medido no
# smoke do v7, 11 rejeicoes de parse contra 0 no v6, com a resposta vindo em
# "label"/"canonical_term" e prosa no lugar do numero. Aqui vao so as REGRAS,
# que nao nomeiam campos e portanto nao competem com o template.
_LLM_OUTPUT_RULES = (
    "Responda APENAS com o JSON no formato ja indicado acima — sem markdown, "
    "sem texto fora do JSON e sem repetir o enunciado. "
    'Acrescente "review_required": true quando a evidencia nao sustentar a '
    "sugestao. Nunca retorne URI como verdade semantica."
)

_HEADER_BR = "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"

# Sintoma observado no arquivo, por ramo de relation_broken. Descreve o que a
# verificacao encontrou — nunca o nome da relacao ausente, que e a resposta.
# O fallback cobre ramos futuros do diagnostico sem nomear relacao nenhuma.
_RELATION_SINTOMAS: dict[str, str] = {
    "IfcRelFillsElement": (
        "o elemento é um componente de esquadria, mas não está vinculado a nenhuma "
        "abertura de elemento hospedeiro — está posicionado no modelo sem preencher vão"
    ),
    "IfcRelContainedInSpatialStructure": (
        "o elemento não está ancorado em nenhum pavimento ou espaço da hierarquia "
        "espacial do modelo"
    ),
    "IfcRelSpaceBoundary": (
        "varrendo o modelo inteiro, praticamente nenhum espaço declara fronteira com os "
        "elementos construtivos que o delimitam; a issue está ancorada no elemento raiz "
        "porque a lacuna é do arquivo como um todo, não de um elemento isolado"
    ),
}

_RELATION_SINTOMA_FALLBACK = (
    "uma entidade de relacionamento exigida para este elemento não foi encontrada no arquivo"
)

TEMPLATES: dict[str, str] = {
    "space_unnamed": (
        _HEADER_BR +
        "ISSUE: IfcSpace #{guid}, nome atual \"{current_name}\"\n"
        "DADOS:\n"
        "- Área: {area_m2} m²\n"
        "- Pé-direito: {height_m} m\n"
        "- Dimensões em planta: {dimensoes}\n"
        "- Pavimento: {floor}\n"
        "- Fronteira com exterior: {is_on_exterior}\n"
        "- Elementos presentes: {contained_elements}\n"
        "- Espaços adjacentes: {adjacent_spaces}\n"
        "INTERPRETAÇÃO DOS ELEMENTOS:\n"
        "  sofá/poltrona/cadeira → sala de estar | cama/berço → dormitório\n"
        "  mesa de jantar/cadeiras de jantar → sala de jantar\n"
        "  fogão/cooktop/forno → cozinha | pia de cozinha/bancada → cozinha\n"
        "  armário de cozinha/geladeira → cozinha\n"
        "  vaso sanitário (louça hidráulica) → banheiro/lavabo; vaso de planta/decorativo\n"
        "    acompanha ambientes sociais ou externos, sem indicar banheiro\n"
        "  pia/cuba/lavatório: decida pelo CONJUNTO — com vaso sanitário ou chuveiro → banheiro;\n"
        "    com fogão/geladeira/armários → cozinha; com tanque → área de serviço\n"
        "  chuveiro/box → banheiro | banheira → banheiro\n"
        "  tanque/máquina de lavar → área de serviço\n"
        "  TV/televisão → sala de estar | estante de livros → escritório/quarto\n"
        "  bancada de laboratório/equipamento científico → laboratório\n"
        "  mesa de escritório/computador → escritório\n"
        "INFERÊNCIA DE FUNÇÃO (vale para qualquer tipologia de edificação):\n"
        "  Pergunte PARA QUE SERVE cada elemento contido e derive daí a função do ambiente:\n"
        "  - equipamento de medição, distribuição ou bombeamento predial → ambiente técnico,\n"
        "    de acesso restrito e não habitável\n"
        "  - recipiente de coleta ou estocagem → armazenagem\n"
        "  - equipamento de esporte ou de recreação → lazer ativo, de uso coletivo\n"
        "  - equipamento de preparo de alimentos em área aberta → lazer social\n"
        "  - degraus, patamar, corrimão ou guarda-corpo → passagem vertical\n"
        "  - guichê, catraca ou bancada junto ao acesso → controle de acesso\n"
        "  - equipamento de combate a incêndio (extintor, mangueira, abrigo de mangueira) →\n"
        "    área de circulação de uso comum: fica na rota de fuga, e sua presença\n"
        "    caracteriza passagem, não ambiente técnico\n"
        "  - o MESMO equipamento repetido em série (N unidades idênticas de medição,\n"
        "    estocagem ou distribuição) → ambiente dedicado a abrigá-lo: o termo usual de\n"
        "    planta nomeia o CONTEÚDO abrigado, não uma classe genérica de armazenagem\n"
        "  Depois de identificar a função, nomeie o ambiente com o termo usual de projeto.\n"
        "ATENÇÃO:\n"
        "  - Laboratório tem bancadas de trabalho e equipamentos específicos, NÃO é quarto\n"
        "  - Sala de estar tem sofá e/ou TV, NÃO é área de circulação\n"
        "  - Sala de jantar tem mesa e cadeiras de jantar, NÃO é circulação\n"
        "  - Quarto tem cama; armazenamento tem prateleiras/caixas\n"
        "  - Espaço ESTREITO (menor dimensão < 1,5 m) e sem mobiliário é de passagem;\n"
        "    se contiver equipamento predial, é ambiente técnico\n"
        "  - Espaço SEM nenhum mobiliário raramente é ambiente de permanência prolongada:\n"
        "    considere passagem, ambiente técnico, armazenagem ou área externa\n"
        "  - Área grande com pé-direito alto e poucos elementos indica uso COLETIVO,\n"
        "    não privativo\n"
        "  - Mobiliário em quantidade muito acima do doméstico (dezenas de cadeiras ou\n"
        "    mesas juntas) também indica uso COLETIVO de condomínio, não uma unidade\n"
        "TAREFA: Identifique o ambiente com base nos elementos presentes e adjacências. "
        "Sugira 3 nomes funcionais ordenados por probabilidade.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"nome": "...", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_thermal": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid}, propriedade ThermalTransmittance ausente\n"
        "DADOS:\n"
        "- Material: {material_name}\n"
        "- Camadas de material: {material_layers}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Externo: {is_external}\n"
        "- Função estrutural (LoadBearing): {load_bearing}\n"
        "NORMA: NBR 15220-2 — método de cálculo de U a partir das camadas\n"
        "MÉTODO: U = 1 / R_total, com R_total = Rsi + Σ(espessura/λ) + Rse.\n"
        "  Rsi = 0,13 e Rse = 0,04 (parede, fluxo horizontal).\n"
        "  λ [W/(m·K)]: concreto 1,75 | argamassa/reboco 1,15 | bloco cerâmico 0,90\n"
        "               gesso acartonado 0,35 | madeira 0,15 | vidro 1,00\n"
        "               aço/metal 55 (CONDUZ calor; metal NÃO isola)\n"
        "MONTANTE METÁLICO E CÂMARA DE AR: numa parede de drywall/steel frame a camada\n"
        "  central de 'Metal' é o montante, e o espaço entre montantes é ar. Trate essa\n"
        "  camada como CÂMARA DE AR NÃO VENTILADA de R ≈ 0,17 m²K/W — um valor fixo,\n"
        "  independente da espessura. NUNCA divida a espessura do metal por um λ baixo:\n"
        "  isso produz resistência inexistente e derruba o U para valores irreais.\n"
        "  Só há isolamento térmico se as camadas citarem lã (de vidro/rocha), EPS, XPS,\n"
        "  poliuretano ou similar — nomes desses materiais, não 'Metal'.\n"
        "ATENÇÃO: parede de vedação brasileira típica fica entre 1,5 e 3,5 W/(m²·K). "
        "Valor calculado abaixo de 1,0 exige camada isolante explícita nas camadas acima.\n" +
        # v7: a "VERIFICAÇÃO OBRIGATÓRIA" que cobrava a conta do LLM saiu (−8,4 pp
        # no estrato térmico). O modelo declara a ESTRUTURA; a aritmética é feita
        # por src/suggestion_engine/thermal_recompute.py.
        _MEMORIA_ESTRUTURADA_BR +
        "TAREFA: identifique as camadas e o λ de cada uma, e sugira 3 hipóteses "
        "ordenadas por probabilidade, cada uma com sua memória estruturada.\n"
        "Formato JSON (os números abaixo são PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": <numero>, "memoria_calculo": {{"rsi": <numero>, '
        '"camadas": [{{"material": "...", "espessura_m": <numero>, "lambda": <numero>}}], '
        '"rse": <numero>}}, "justificativa": "...", "ref": "NBR 15220-2", '
        '"confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_u_value_window": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade ThermalTransmittance ausente\n"
        "DADOS:\n"
        "- Esquadria: {element_name}\n"
        "- Material/composição: {material_name}\n"
        "- Camadas: {material_layers}\n"
        "- Externo: {is_external}\n"
        "NORMA: NBR 15575-4 — desempenho de esquadrias; ISO 10077 para U de janelas\n"
        "IMPORTANTE: esquadria NÃO é parede. O U de um componente envidraçado é dominado "
        "pelo vidro e pelo caixilho, não pela espessura da folha.\n"
        "REFERÊNCIAS DE U [W/(m²·K)] PARA ESQUADRIAS:\n"
        "  Vidro simples 3–6 mm, caixilho de alumínio sem ruptura térmica: 5,5 a 6,0\n"
        "  Vidro simples, caixilho de madeira ou PVC: 4,5 a 5,0\n"
        "  Vidro duplo (insulado) comum: 2,7 a 3,2\n"
        "  Vidro duplo Low-E: 1,8 a 2,4\n"
        "  Porta opaca de madeira maciça: 2,0 a 3,0\n"
        "  Porta metálica sem isolamento: 5,0 a 6,0\n"
        "ATENÇÃO: na ausência de indicação de vidro duplo, insulado ou Low-E no nome/composição, "
        "trate como VIDRO SIMPLES — é o caso usual em edificação residencial brasileira.\n"
        "TAREFA: sugira 3 valores de ThermalTransmittance para esta esquadria, ordenados por "
        "probabilidade. Retorne valor numérico puro, sem unidade no campo valor.\n"
        "Formato JSON (o valor abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": <numero>, "justificativa": "...", '
        '"ref": "NBR 15575-4", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_fire": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade FireRating ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class} (PredefinedType: {predefined_type})\n"
        "- Nome: {element_name}\n"
        "- Material: {material_name}\n"
        "- Camadas de material: {material_layers}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Função estrutural (LoadBearing): {load_bearing}\n"
        "- Externo: {is_external}\n"
        "NORMA: ABNT NBR 14432 — Exigências de resistência ao fogo de elementos construtivos\n"
        "CRITÉRIOS (a letra depende da FUNÇÃO do elemento, não do material):\n"
        "  R  = resistência mecânica — SÓ para elemento com função estrutural (portante)\n"
        "  E  = estanqueidade a chamas e gases | I = isolamento térmico\n"
        "  REI = portante + compartimenta (ex.: parede estrutural, laje entre pavimentos)\n"
        "  EI  = NÃO portante, só compartimenta (ex.: divisória leve, drywall)\n"
        "  R   = portante sem função de compartimentação (ex.: pilar, viga isolada)\n"
        "A flag LoadBearing do modelo é indício, não veredito: pese também o material, a\n"
        "  espessura e a função do elemento no projeto de compartimentação.\n"
        # v7: o bloco PROCEDIMENTO (TRRF → letra → hipóteses) foi REMOVIDO. Medido
        # em −12,5 pp no estrato de fogo (matriz v6): a instrução fez os modelos
        # fracos raciocinarem sobre a letra e INVERTEREM a atribuição — falcon3
        # chegou a responder EI num pilar. Os critérios abaixo ficam; o roteiro
        # de como raciocinar sai.
        "TAREFA: determine a classe de resistência ao fogo deste elemento e sugira 3 valores "
        "ordenados por probabilidade, considerando a função estrutural, as camadas e a espessura.\n"
        # v7.2: a redacao anterior — "letras R/E/I seguidas do tempo" — foi lida
        # como "escolha UMA destas" e produziu classe de uma letra (E 30, E 60)
        # no smoke do v7.1. Enumerar as COMBINACOES resolve a ambiguidade sem
        # dizer qual delas se aplica: essa decisao continua no bloco CRITERIOS.
        "RESTRICAO: o campo valor e uma classe seguida do tempo em minutos. As classes "
        "validas sao as combinacoes R, RE, REI, EI e E — as letras aparecem JUNTAS na "
        "mesma classe quando o elemento cumpre mais de uma funcao. "
        "Duracoes usuais: 30, 60, 90 ou 120 minutos. "
        "Nao use A1, N/A, NC, FireRating, nomes de propriedade, descricoes ou texto explicativo.\n"
        "Formato JSON (o valor abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": "<classe> <minutos>", "justificativa": "...", '
        '"ref": "NBR 14432", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_generic": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Nome: {element_name}\n"
        "- Pset alvo: {pset_name}\n"
        "TAREFA: Sugira 3 valores possíveis para a propriedade IFC \"{check_property}\" "
        "do Pset \"{pset_name}\", do mais provável ao menos provável. "
        "Considere o tipo de elemento e o contexto construtivo brasileiro.\n"
        "ABSTENÇÃO: não há vocabulário oficial (IDS/bSDD) disponível para esta propriedade. "
        "Prefira abster-se a chutar: use review_required=true em toda opção cuja confiança "
        "não seja alta e justifique tecnicamente cada valor proposto.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "...", "justificativa": "...", '
        '"review_required": true, "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_space_category": (
        _HEADER_BR +
        "ISSUE: IfcSpace #{guid} (\"{element_name}\"), propriedade Category ausente no Pset_SpaceCommon\n"
        "DADOS:\n"
        "- Nome atual do espaço: {element_name}\n"
        "- Uso declarado no modelo (LongName): {long_name}\n"
        "- Área: {area_m2} m²\n"
        "- Contém: {contained_elements}\n"
        "- Adjacente a: {adjacent_spaces}\n"
        "EVIDÊNCIA PRIMÁRIA: quando o LongName declarar o uso do ambiente, escolha o token "
        "da lista que corresponde a esse uso; os elementos contidos confirmam. Nome numérico "
        "é apenas identificador do recinto, não descreve função.\n"
        "CATEGORIAS VÁLIDAS (IFC): BEDROOM, LIVING_ROOM, KITCHEN, BATHROOM, WC, CIRCULATION, "
        "SERVICE_AREA, OFFICE, MEETING_ROOM, LOBBY, STORAGE, BALCONY, GARAGE, TECHNICAL_AREA\n"
        "VOCABULÁRIO FECHADO: o campo valor é EXATAMENTE um dos tokens da lista acima, "
        "escrito em INGLÊS e em MAIÚSCULAS, com sublinhado onde houver, copiado caractere "
        "por caractere. Qualquer texto que não seja idêntico a um item da lista é descartado. "
        "O idioma e a caixa fazem parte do formato exigido pelo IFC, não da sua análise: "
        "raciocine no idioma que quiser e devolva o token na forma acima.\n"
        "PISTAS DE ÁREA TÉCNICA: medidor, hidrômetro, quadro elétrico, central de gás/GLP, "
        "bomba, cisterna, casa de máquinas, barrilete → TECHNICAL_AREA (não CIRCULATION).\n"
        "TAREFA: Identifique a Category IFC mais provável para este espaço com base no nome, "
        "área e elementos contidos. Retorne 3 opções ordenadas por probabilidade.\n"
        "Formato JSON (o token abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": "<TOKEN_DA_LISTA>", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "system_unclassified": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), sistema construtivo não classificado\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Camadas de material: {material_layers}\n"
        # v7.6: os templates de pset ja recebiam a funcao estrutural do elemento;
        # este nao, e o rotulo "vedacao" vs "estrutural" e exatamente o que ela
        # decide. Sem ela, 3 modelos erraram os 262 itens da maior classe.
        "- Função estrutural declarada (LoadBearing): {load_bearing}\n"
        "- Sistema estrutural declarado no modelo: {structural_inventory}\n"
        "SISTEMAS CONSTRUTIVOS COMUNS DE PAREDE (Brasil): "
        "Alvenaria de vedação em bloco cerâmico, "
        "Alvenaria estrutural em bloco cerâmico, Concreto armado moldado in loco, "
        "Concreto pré-moldado, Drywall / Steel frame, Alvenaria em bloco de concreto, "
        "Estrutura metálica, Painel de EPS\n"
        # v7.7: o paragrafo "VEDACAO OU ESTRUTURAL" saiu. Era roteiro de
        # raciocinio (regra de inferencia portico->vedacao), a natureza medida
        # em -12,5 pp na matriz v6 — e na rodada v7.6 o priming lexical
        # ("estrutural" 3x no paragrafo) coincidiu com "Alvenaria estrutural"
        # saltando de 953 para 2145 itens no pool de modelos. A evidencia
        # ({load_bearing}, {structural_inventory}) fica: ler o que ela significa
        # e trabalho do modelo. So a primeira oracao sobrevive, porque define a
        # SEMANTICA do rotulo, nao o caminho ate ele.
        "O RÓTULO declara a função da parede no sistema construtivo, não só o material.\n"
        "TAREFA: Classifique o sistema construtivo desta parede com 3 opções "
        "ordenadas por probabilidade, considerando o material e espessura informados.\n"
        "VOCABULÁRIO FECHADO: o campo sistema deve reproduzir EXATAMENTE um dos rótulos "
        "listados acima, com a mesma grafia e acentuação. Não abrevie, não use snake_case, "
        "não prefixe com 'Ifc' e não invente rótulo novo.\n"
        "Formato JSON (o rótulo abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"sistema": "<ROTULO_DA_LISTA>", '
        '"justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "system_unclassified_slab": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), sistema construtivo não classificado\n"
        "DADOS:\n"
        "- Tipo IFC (PredefinedType): {predefined_type}\n"
        "- Nome/tipo do objeto: {object_type}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Camadas de material: {material_layers}\n"
        "INTERPRETAÇÃO DO TIPO IFC:\n"
        "  FLOOR → laje de piso (entre pavimentos ou sobre solo)\n"
        "  ROOF → laje de cobertura (terraço, telhado plano)\n"
        "  BASESLAB → radier ou laje de fundação sobre solo\n"
        "  LANDING → patamar de escada\n"
        "  NOTDEFINED / None → verificar nome do objeto para pistas\n"
        "SISTEMAS ESTRUTURAIS DE LAJE comuns no Brasil:\n"
        "  Laje maciça de concreto armado, Laje nervurada (vigotas + EPS/cerâmica),\n"
        "  Laje pré-moldada treliçada, Laje alveolar pré-moldada,\n"
        "  Laje de madeira (estrutura em madeira), Laje steel frame\n"
        "ACABAMENTOS/REVESTIMENTOS DE PISO comuns no Brasil:\n"
        "  Piso cerâmico / porcelanato, Piso de madeira (parquet / taco / deck),\n"
        "  Piso de pedra (mármore / granito / ardósia), Piso de concreto polido,\n"
        "  Grama natural ou artificial, Piso de cimento queimado,\n"
        "  Deck de madeira externo, Carpete, Piso vinílico / laminado\n"
        "ATENÇÃO:\n"
        "  - Se o nome/material mencionar 'grama', 'grass', 'lawn' → classifique como revestimento de grama\n"
        "  - Se mencionar 'madeira', 'wood', 'parquet', 'taco' → piso de madeira\n"
        "  - Se mencionar 'cerâmica', 'porcelanato', 'tile' → piso cerâmico/porcelanato\n"
        "  - Se mencionar 'concreto', 'concrete' com espessura > 8cm → laje estrutural\n"
        "  - Se mencionar 'terra', 'soil', 'ground' → radier ou laje sobre solo\n"
        "TAREFA: Identifique o sistema construtivo/revestimento desta laje com 3 opções "
        "ordenadas por probabilidade. Use o nome do objeto e camadas de material como pistas principais.\n"
        "VOCABULÁRIO FECHADO: o campo sistema deve reproduzir EXATAMENTE um dos rótulos "
        "listados acima, com a mesma grafia e acentuação. Não abrevie, não use snake_case, "
        "não prefixe com 'Ifc' e não invente rótulo novo.\n"
        "Formato JSON (o rótulo abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"sistema": "<ROTULO_DA_LISTA>", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    # v7.6: um unico template para relation_broken. Os dois anteriores pediam
    # "3 acoes de diagnostico e correcao" em prosa, enquanto o ground truth
    # pontua o NOME da classe de relacao ausente — 0,00 em 10/10 modelos era
    # incompatibilidade de contrato, nao erro de decisao. O sintoma varia por
    # ramo ({sintoma}, montado em build_prompt a partir de expected_relation) e
    # NUNCA nomeia a relacao esperada; o vocabulario e a lista de classes de
    # relacionamento do schema, que existe independentemente deste modelo.
    "relation_missing": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\") — relacionamento ausente no modelo IFC.\n"
        "DADOS:\n"
        "- Elemento: {element_class} \"{element_name}\"\n"
        "- Espaços no mesmo pavimento: {nearby_spaces}\n"
        "SINTOMA VERIFICADO NO ARQUIVO: {sintoma}\n"
        "NORMA: ISO 16739-1 — o schema IFC representa vínculos entre elementos por "
        "entidades de relacionamento objetivadas (subtipos de IfcRelationship).\n"
        "CLASSES DE RELACIONAMENTO DO SCHEMA (vocabulário fechado):\n"
        "  IfcRelFillsElement — preenche uma abertura (porta/janela na abertura da parede)\n"
        "  IfcRelVoidsElement — abre um vão no elemento hospedeiro\n"
        "  IfcRelContainedInSpatialStructure — ancora o elemento num pavimento ou espaço\n"
        "  IfcRelSpaceBoundary — fronteira entre um espaço e o elemento que o delimita\n"
        "  IfcRelAggregates — composição todo/parte na hierarquia espacial\n"
        "  IfcRelConnectsElements — conexão física entre dois elementos\n"
        "  IfcRelDefinesByProperties — associa conjunto de propriedades ao elemento\n"
        "  IfcRelAssociatesMaterial — associa material ao elemento\n"
        "TAREFA: identifique QUAL classe de relacionamento está ausente neste caso e "
        "retorne 3 opções ordenadas por probabilidade.\n"
        "VOCABULÁRIO FECHADO: o campo valor é EXATAMENTE o nome de uma das classes "
        "listadas acima, copiado caractere por caractere, com o prefixo Ifc e a mesma "
        "caixa. Não descreva a correção, não cite software BIM, não invente nome de "
        "classe e não devolva URI.\n"
        "Formato JSON (o token abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": "<NOME_DA_CLASSE_DA_LISTA>", '
        '"justificativa": "...", "ref": "ISO 16739-1", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_acoustic": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class} (PredefinedType: {predefined_type})\n"
        "- Material: {material_name}\n"
        "- Camadas de material: {material_layers}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Externo: {is_external}\n"
        "NORMA: NBR 15575-4/5 — Desempenho acústico de vedações e lajes\n"
        # v7.6: a tabela cobria apenas vedação maciça de parede. Componente de
        # esquadria (porta/janela) e vedação leve de chapa única não tinham
        # nenhuma linha, e o menor valor ofertado era Rw 35 — acima de qualquer
        # valor plausível para porta. As duas linhas novas são tipologia de
        # literatura, na mesma natureza das três originais: descrevem a
        # construção, não o elemento avaliado.
        "REFERÊNCIAS TÍPICAS de índice de redução sonora ponderado (Rw):\n"
        "  - Porta interna de madeira (folha leve, sem vedação de fresta): Rw 20 a 25 dB\n"
        "  - Drywall simples (uma chapa por face): Rw 35 a 40 dB\n"
        "  - Alvenaria 14cm: Rw 35 dB\n"
        "  - Concreto 12cm: Rw 42 dB\n"
        "  - Drywall duplo: Rw 50 dB\n"
        "A tabela descreve TIPOLOGIAS construtivas: escolha a linha pela composição do\n"
        "  elemento (classe IFC, camadas e espessura acima), não pela primeira da lista.\n"
        "  Componente de esquadria isola muito menos que a vedação em que se insere.\n"
        "FORMATO OBRIGATÓRIO DO VALOR: exatamente \"Rw NN dB\" (índice em decibéis). "
        "A classe de desempenho da NBR 15575 (D mínimo / M intermediário / S superior) "
        "serve para raciocinar, mas NÃO é resposta válida aqui: devolva o Rw.\n"
        "TAREFA: Sugira 3 valores de {check_property} para este elemento, "
        "do mais provável ao menos provável, cada um no formato \"Rw NN dB\".\n"
        # v7.6: o exemplar trazia literalmente "Rw NN dB" e um modelo o devolveu
        # como resposta na rodada v7.5. Placeholder explicito remove a ambiguidade.
        "Formato JSON (o valor abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": "Rw <numero> dB", "justificativa": "...", '
        '"ref": "NBR 15575", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_u_value_slab": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade ThermalTransmittance ausente\n"
        "DADOS:\n"
        "- Tipo IFC: {element_class}\n"
        "- Material: {material_name}\n"
        "- Espessura total: {thickness_m} m\n"
        "- É externo/cobertura: {is_external}\n"
        "- Camadas de material: {material_layers}\n"
        "NORMA: NBR 15220-2 — método de cálculo de U a partir das camadas\n"
        "MÉTODO: U = 1 / R_total, com R_total = Rsi + Σ(espessura/λ) + Rse.\n"
        "  Fluxo descendente (laje de piso): Rsi = 0,17 e Rse = 0,04.\n"
        "  Fluxo ascendente (cobertura): Rsi = 0,10 e Rse = 0,04.\n"
        "  λ [W/(m·K)]: concreto 1,75 | argamassa/regularização 1,15 | cerâmica/porcelanato 1,05\n"
        "               fibrocimento 0,95 | madeira 0,15 | EPS 0,04 | lã de vidro 0,045\n"
        "               aço/metal 55 (CONDUZ calor; metal NÃO isola)\n"
        "  Vazio de laje nervurada ou entre perfis: câmara de ar não ventilada, R ≈ 0,16.\n"
        "  Só há isolamento se as camadas citarem EPS, XPS, lã ou poliuretano.\n"
        "ATENÇÃO — LIMITE NORMATIVO NÃO É O VALOR DO ELEMENTO: a NBR 15575-5 fixa "
        "limites de transmitância que dependem do tipo de elemento e das condições de "
        "aplicação, mas esses limites são critérios de APROVAÇÃO, não estimativas do "
        "valor. Um elemento pode perfeitamente REPROVAR no limite — apontar essa "
        "não-conformidade é a finalidade da análise. Calcule o valor a partir das "
        "camadas e devolva o resultado do cálculo, seja ele conforme ou não.\n" +
        # v7: idem ao template de parede — a estrutura é do LLM, a soma é do código.
        _MEMORIA_ESTRUTURADA_BR +
        "TAREFA: identifique as camadas e o λ de cada uma, e sugira 3 hipóteses "
        "ordenadas por probabilidade, cada uma com sua memória estruturada.\n"
        "Formato JSON (os números abaixo são PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": <numero>, "memoria_calculo": {{"rsi": <numero>, '
        '"camadas": [{{"material": "...", "espessura_m": <numero>, "lambda": <numero>}}], '
        '"rse": <numero>}}, "justificativa": "...", "ref": "NBR 15220-2", '
        '"confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_solar": (
        _HEADER_BR +
        "ISSUE: IfcWindow #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Material/tipo de vidro: {material_name}\n"
        "- Camadas de material: {material_layers}\n"
        "- Externo: {is_external}\n"
        # v7.6: a linha dizia "ThermalTransmittance (U)" e renderizava o resumo
        # de Psets do elemento — um dict cru, com rotulo que nao descrevia o
        # conteudo. Rotulo corrigido; o dado permanece.
        "- Conjuntos de propriedades já presentes no elemento: {existing_psets}\n"
        "REFERÊNCIAS TÍPICAS:\n"
        "  SolarHeatGainCoefficient (SHGC / Fator Solar):\n"
        "    Vidro simples incolor 6mm: 0,87\n"
        "    Vidro duplo Low-E: 0,35–0,55\n"
        "    Vidro laminado fumê: 0,45–0,65\n"
        "    Vidro reflexivo: 0,20–0,35\n"
        "  VisibleTransmittance:\n"
        "    Incolor: 0,85–0,90 | Fumê: 0,45–0,65 | Reflexivo: 0,20–0,45\n"
        "NORMA: NBR 15575-4, RTQ-C, ASHRAE 90.1\n"
        "TAREFA: Sugira 3 valores para {check_property} (adimensional, 0–1), "
        "do mais provável ao menos provável, com base no tipo de vidro.\n"
        "Formato JSON (os números abaixo são PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": <numero>, "justificativa": "...", '
        '"ref": "NBR 15575-4", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_structural": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class} (PredefinedType: {predefined_type})\n"
        "- Nome: {element_name}\n"
        "- Material: {material_name}\n"
        "- Camadas de material: {material_layers}\n"
        "- Espessura/seção: {thickness_m} m\n"
        "- Externo: {is_external}\n"
        # v7.6: o arquivo declara quantos pilares e vigas existem; sem esse
        # agregado o modelo nao consegue distinguir edificio em portico (onde a
        # parede e vedacao) de alvenaria portante. E evidencia do arquivo, e nao
        # o alias LoadBearing do proprio elemento, que seria a resposta.
        "- Sistema estrutural declarado no modelo: {structural_inventory}\n"
        "INTERPRETAÇÃO (o PredefinedType manda mais que a classe):\n"
        "  IfcBeam/IfcColumn em concreto armado → normalmente True\n"
        "  IfcSlab PredefinedType=FLOOR (laje entre pavimentos) → normalmente True\n"
        "  IfcSlab PredefinedType=BASESLAB (radier/fundação) → normalmente True\n"
        "  IfcSlab PredefinedType=ROOF → é COBERTURA: telha de fibrocimento, metálica ou\n"
        "    cerâmica é APOIADA sobre a estrutura e NÃO é portante → False\n"
        "  IfcSlab PredefinedType=LANDING (patamar de escada) → normalmente True\n"
        "  IfcWall fina (< 10 cm), drywall ou divisória de vedação → False\n"
        "REGRA: telha, forro, revestimento e elemento apoiado não sustentam carga de "
        "outros elementos — respondem False mesmo quando a classe IFC é IfcSlab.\n"
        # v7.7: o paragrafo "PAREDE EM EDIFICACAO COM PORTICO" saiu. Era regra de
        # inferencia (portico declarado -> parede e vedacao) somada a diretiva
        # ("Decida pelo inventario acima") — roteiro, nao evidencia. Na rodada
        # v7.6, True em IsLoadBearing subiu de 334 para 858 itens no pool, com
        # falcon3 -39,0 pp e mistral -62,6 pp no estrato: modelos-eco reagiram
        # ao vocabulario do paragrafo, nao ao dado. O inventario ({structural_
        # inventory}) permanece na secao DADOS: e evidencia do arquivo, e le-la
        # e a tarefa que o estrato mede.
        "TAREFA: determine {check_property} para este elemento e sugira 3 valores booleanos "
        "(true/false) ordenados por probabilidade, com justificativa baseada no "
        "PredefinedType, no material e na espessura.\n"
        "Formato JSON (o valor abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": <true|false>, "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    # v7.6: HasNonSkidSurface saiu de pset_missing_structural. Recebia a tabela
    # de interpretacao de funcao portante (FLOOR->True, ROOF->False), que nao
    # tem relacao com superficie antiderrapante — 7 de 10 modelos responderam
    # False. Aqui nao ha mapa de classe->valor: so a evidencia do arquivo e o
    # criterio normativo de onde a norma exige a superficie.
    "pset_missing_nonskid": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class} (PredefinedType: {predefined_type})\n"
        "- Nome: {element_name}\n"
        "- Material: {material_name}\n"
        "- Camadas de material (a última é a face de uso): {material_layers}\n"
        "- Externo: {is_external}\n"
        "NORMA: ABNT NBR 9050 (acessibilidade) e NBR 15575-3 (pisos) — a propriedade "
        "declara se a superfície de uso do elemento é antiderrapante.\n"
        # v7.7: a diretiva "Decida pelo acabamento declarado nas camadas e pela
        # exposicao do elemento" saiu — era roteiro que elegia UM eixo de
        # decisao, e na rodada v7.6 empurrou 9/10 modelos para False num
        # gabarito True (escadas). Ficam os dois blocos de conhecimento
        # genericos: o escopo normativo (onde a norma exige a superficie) e a
        # tipologia de acabamento (o que nao e antiderrapante por si). Pesa-los
        # e a decisao que o estrato mede — concordancia com a convencao do
        # gabarito, como o SHGC.
        "CRITÉRIO: a exigência decorre do RISCO DE ESCORREGAMENTO da superfície onde se "
        "pisa — piso sujeito a molhamento, rampa e degrau são as situações que a norma "
        "trata. Acabamento liso (concreto desempenado, pedra polida, porcelanato "
        "esmaltado comum) não é antiderrapante por si.\n"
        "TAREFA: determine {check_property} para este elemento e sugira 3 valores booleanos "
        "(true/false) ordenados por probabilidade.\n"
        "Formato JSON (o valor abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"valor": <true|false>, "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "system_unclassified_structural": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), sistema estrutural não classificado\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Nome: {element_name}\n"
        "- Espessura/seção: {thickness_m} m\n"
        "- Camadas de material: {material_layers}\n"
        "SISTEMAS ESTRUTURAIS COMUNS (Brasil):\n"
        "  IfcBeam: Viga de concreto armado moldada in loco, Viga pré-moldada protendida, "
        "Viga metálica perfil I/H, Viga de madeira laminada colada (MLC), Vigota treliçada\n"
        "  IfcColumn: Pilar de concreto armado moldado in loco, Pilar pré-moldado de concreto, "
        "Pilar metálico tubular, Pilar metálico perfil I/H, Pilar de madeira\n"
        "TAREFA: Classifique o sistema estrutural deste elemento com 3 opções "
        "ordenadas por probabilidade.\n"
        # v7.6: era o unico dos tres templates de sistema sem o bloco de
        # vocabulario fechado, e o exemplar trazia um rotulo concreto no lugar
        # do placeholder — ancorava a resposta.
        "VOCABULÁRIO FECHADO: o campo sistema deve reproduzir EXATAMENTE um dos rótulos "
        "listados acima para a classe deste elemento, com a mesma grafia e acentuação. "
        "Não abrevie, não use snake_case, não prefixe com 'Ifc' e não invente rótulo novo.\n"
        "Formato JSON (o rótulo abaixo é PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"sistema": "<ROTULO_DA_LISTA>", '
        '"justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "quantity_missing": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), quantidade base ausente\n"
        "DADOS GEOMÉTRICOS DISPONÍVEIS:\n"
        "- Bounding box / dimensões: {geometry_data}\n"
        "- Material: {material_name}\n"
        "- Espessura: {thickness_m} m\n"
        "- Pset existente: {existing_psets}\n"
        "QUANTIDADE FALTANTE: {check_property}\n"
        "MÉTODO DE CÁLCULO:\n"
        "  NetSideArea = comprimento × altura líquida\n"
        "  Volume = área × espessura\n"
        "  NetFloorArea = área interna do espaço\n"
        "  Perimeter = soma dos lados do espaço\n"
        "TAREFA: Calcule ou estime {check_property} com base nos dados disponíveis. "
        "Se o cálculo for direto, dê o valor exato. Se for estimativa, justifique o método.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": ..., "unidade": "m²/m³/m", '
        '"metodo": "calculo_direto|estimativa", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "classification_missing": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), referência de classificação ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Nome: {element_name}\n"
        "- Material: {material_name}\n"
        "- Sistema construtivo: {existing_psets}\n"
        "SISTEMAS DE CLASSIFICAÇÃO (Brasil):\n"
        "  SINAPI — Composições de custo da Caixa Econômica Federal\n"
        "  TCPO — Tabelas de Composições de Preços para Orçamentos (PINI)\n"
        "  NBR 15965 — Sistema de classificação da construção (ABNT)\n"
        "  OmniClass — Mesa 13 (Produtos) ou Mesa 21 (Elementos)\n"
        "TAREFA: Sugira 3 classificações para este elemento, com código e descrição, "
        "priorizando SINAPI e NBR 15965 para o contexto brasileiro.\n"
        # v7.6: o exemplar trazia um codigo SINAPI concreto ("74209/001") no
        # campo que carrega a resposta. Estrato fora do escopo do benchmark
        # atual, mas e a mesma ancora textual que o guarda passou a barrar.
        "Formato JSON (os valores abaixo são PLACEHOLDER, não uma sugestão):\n"
        '{{"opcoes": [{{"codigo": "<codigo>", "sistema": "<SISTEMA_DA_LISTA>", "descricao": "...", '
        '"justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "thermal_incomplete": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), dados térmicos incompletos\n"
        "DADOS:\n"
        "- Propriedade faltante: {check_property}\n"
        "- Material: {material_name}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Externo: {is_external}\n"
        "- Zona bioclimática: {bioclimatic_zone}\n"
        "- Psets existentes: {existing_psets}\n"
        "PROPRIEDADES TÉRMICAS COMUNS:\n"
        "  ThermalTransmittance (U) [W/m²·K]: resistência global ao calor\n"
        "  SolarAbsorptance (α): 0–1, superfície escura ≈ 0,8, clara ≈ 0,2\n"
        "  SolarHeatGainCoefficient (SHGC): 0–1, apenas para janelas\n"
        "  ThermalMass [kJ/m²·K]: inércia térmica do elemento\n"
        "NORMA: NBR 15575, RTQ-C, ISO 6946\n"
        "TAREFA: Sugira 3 valores para {check_property} com referência normativa, "
        "considerando o material e zona bioclimática.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": ..., "unidade": "...", "justificativa": "...", '
        '"ref": "NBR 15575", "confianca": "alta/media/baixa"}}]}}'
    ),
    "material_unmapped": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), material não mapeado para padrão\n"
        "DADOS:\n"
        "- Nome do material no modelo: {material_name}\n"
        "- Tipo de elemento: {element_class}\n"
        "- Espessura: {thickness_m} m\n"
        "- Camadas: {existing_psets}\n"
        "CATEGORIAS PADRÃO IFC (IfcMaterialCategory):\n"
        "  Concrete, Masonry, Metal, Wood, Glass, Gypsum, Stone, Plastic, "
        "Insulation, Membrane, Earth, Finish, Liquid, Aggregate\n"
        "EXEMPLOS DE MAPEAMENTO:\n"
        "  'bloco cerâmico' → Masonry | 'concreto fck25' → Concrete\n"
        "  'perfil HEA 200' → Metal | 'OSB 18mm' → Wood\n"
        "  'EPS 50mm' → Insulation | 'gesso acartonado' → Gypsum\n"
        "TAREFA: Sugira 3 mapeamentos do material '{material_name}' para categorias IFC padrão, "
        "do mais adequado ao menos adequado.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"categoria_ifc": "Concrete", "nome_canonico": "Concreto armado fck≥20MPa", '
        '"justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "asset_unidentified": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), equipamento sem identificação\n"
        "DADOS:\n"
        "- Classe IFC: {element_class}\n"
        "- PredefinedType: {predefined_type}\n"
        "- Nome atual (genérico): {element_name}\n"
        "- Espaço contentor: {containing_space}\n"
        "- Pavimento: {floor}\n"
        "CATEGORIAS DE ATIVOS COMUNS:\n"
        "  IfcFlowTerminal → luminária, tomada, ponto de hidráulica, sprinkler, difusor de ar\n"
        "  IfcFlowTerminal (SANITARYTERMINAL) → vaso sanitário, pia, chuveiro, banheira, tanque\n"
        "  IfcEnergyConversionDevice → caldeira, bomba de calor, aquecedor, chiller\n"
        "  IfcFlowMovingDevice → bomba hidráulica, ventilador, exaustor, fan-coil\n"
        "  IfcFlowStorageDevice → reservatório, caixa d'água, tanque de combustível\n"
        "  IfcDistributionControlElement → termostato, sensor, controlador, painel elétrico\n"
        "  IfcFurnishingElement → mobiliário de escritório, equipamento de academia\n"
        "TAREFA: Sugira 3 identificações funcionais para este ativo (nome + categoria de manutenção), "
        "baseando-se na classe IFC e no espaço contentor.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"nome_ativo": "...", "categoria": "...", '
        '"periodicidade_manutencao": "mensal/trimestral/semestral/anual", '
        '"justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
}


PROFILE_TEMPLATES: dict[tuple[str, str], str] = {
    ("budget_readiness", "quantity_missing"): (
        "Você é um orçamentista brasileiro. O modelo BIM precisa de quantitativos confiáveis.\n"
        "ELEMENTO: {element_class} #{guid}\n"
        "DADOS GEOMÉTRICOS DISPONÍVEIS: {geometry_data}\n"
        "MATERIAL: {material}\n"
        "ESPESSURA: {thickness}\n"
        "QUANTIDADE FALTANTE: {quantity_name}\n"
        "Calcule ou estime {quantity_name} com base nos dados. "
        "Se o cálculo é direto, dê o valor exato. Se é estimativa, justifique.\n"
        '{{"opcoes": [{{"valor": ..., "unidade": "...", '
        '"metodo_calculo": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    ("budget_readiness", "classification_missing"): (
        "Você é um orçamentista brasileiro que trabalha com SINAPI e TCPO.\n"
        "ELEMENTO: {element_class} #{guid}\n"
        "MATERIAL: {material}, ESPESSURA: {thickness}cm, CAMADAS: {layers}\n"
        "TAREFA: Sugira 3 classificações orçamentárias para este elemento.\n"
        '{{"opcoes": [{{"codigo": "...", "descricao": "...", '
        '"fonte": "SINAPI/TCPO", "confianca": "..."}}]}}'
    ),
    ("energy_readiness", "thermal_incomplete"): (
        "Você é um engenheiro de desempenho térmico brasileiro, "
        "especialista em NBR 15575 e RTQ-C.\n"
        "CONTEXTO: Zona bioclimática {zone}, {building_type}\n"
        "ELEMENTO: {element_class} #{guid}\n"
        "PROPRIEDADE FALTANTE: {property_name}\n"
        "DADOS: material={material}, espessura={thickness}cm, "
        "camadas={layers}, IsExternal={is_external}\n"
        "Sugira 3 valores para {property_name} com referência normativa.\n"
        '{{"opcoes": [{{"valor": ..., "unidade": "...", "referencia": "...", '
        '"justificativa": "...", "confianca": "..."}}]}}'
    ),
    ("energy_readiness", "space_unnamed"): (
        "Você é um engenheiro de energia que precisa classificar zonas térmicas.\n"
        'ESPAÇO: #{guid}, nome atual "{current_name}", área {area_m2}m²\n'
        "CONTÉM: {contained_elements}\n"
        "ADJACENTE A: {adjacent_spaces}\n"
        "PAREDES EXTERNAS ADJACENTES: {external_wall_count}\n"
        "TEM JANELA EXTERNA: {has_external_window}\n"
        "Sugira 3 nomes funcionais que facilitem o zoneamento térmico "
        '(ex: diferencie "Sala de estar" de "Dormitório" pois tem '
        "requisitos térmicos distintos na NBR 15575).\n"
        '{{"opcoes": [{{"nome": "...", '
        '"zona_termica_sugerida": "condicionado/não-condicionado", '
        '"justificativa": "...", "confianca": "..."}}]}}'
    ),
    ("fm_readiness", "space_unnamed"): (
        "Você é um gestor de facilities brasileiro.\n"
        'ESPAÇO: #{guid}, nome atual "{current_name}", área {area_m2}m²\n'
        "CONTÉM: {contained_elements}\n"
        "EQUIPAMENTOS/ATIVOS: {assets}\n"
        "PAVIMENTO: {floor}\n"
        "Sugira 3 nomes funcionais orientados para operação e manutenção "
        "(priorize nomenclatura que facilite rotas de inspeção e ordens de serviço).\n"
        '{{"opcoes": [{{"nome": "...", "categoria_fm": "...", '
        '"justificativa": "...", "confianca": "..."}}]}}'
    ),
    ("fm_readiness", "asset_unidentified"): (
        "Você é um gestor de facilities.\n"
        "EQUIPAMENTO: {element_class} #{guid}, PredefinedType={predefined_type}\n"
        "LOCALIZAÇÃO: {containing_space}, pavimento {floor}\n"
        'NOME ATUAL: "{name}" (genérico ou vazio)\n'
        "Sugira 3 identificações para este ativo (nome funcional, categoria de manutenção).\n"
        '{{"opcoes": [{{"nome_ativo": "...", "categoria": "...", '
        '"periodicidade_manutencao": "...", "confianca": "..."}}]}}'
    ),
}


def _format_list(items: list[str] | Any) -> str:
    """Formata lista de strings como texto separado por vírgulas."""
    if not items:
        return "nenhum"
    if isinstance(items, list):
        return ", ".join(str(i) for i in items)
    return str(items)


def _specialized_pset_template_key(issue: Issue) -> str | None:
    """Retorna a chave do template especializado de pset_missing, ou None se genérico."""
    prop = issue.context.get("check_property", "")
    if prop == "ThermalTransmittance":
        # Esquadria nao e parede: o U de componente envidracado e dominado pelo
        # vidro e pelo caixilho, nao pela espessura da folha. Roteava para o
        # template de parede e todos os modelos respondiam ~2,48 (GT 5,7).
        if issue.element_class in ("IfcWindow", "IfcDoor", "IfcCurtainWall", "IfcPlate"):
            return "pset_missing_u_value_window"
        if issue.element_class in ("IfcSlab", "IfcSlabStandardCase", "IfcRoof"):
            return "pset_missing_u_value_slab"
        return "pset_missing_thermal"
    if prop == "FireRating":
        return "pset_missing_fire"
    if prop == "Category" and issue.element_class == "IfcSpace":
        return "pset_missing_space_category"
    if prop in ("AcousticRating", "SoundTransmissionLoss"):
        return "pset_missing_acoustic"
    if prop in ("SolarHeatGainCoefficient", "VisibleTransmittance"):
        return "pset_missing_solar"
    if prop in ("LoadBearing", "IsLoadBearing"):
        return "pset_missing_structural"
    # v7.6: superficie antiderrapante nao e funcao portante — recebia a tabela
    # de LoadBearing e 7 de 10 modelos responderam False por causa dela.
    if prop == "HasNonSkidSurface":
        return "pset_missing_nonskid"
    return None


def has_specialized_pset_template(issue: Issue) -> bool:
    """True se a issue pset_missing tem template especializado (térmico, fogo, etc.).

    Usado pelo roteamento da Fase A.2: issues genéricas COM grounding vão para
    ``build_pset_grounded_prompt``; as especializadas mantêm o caminho atual.
    """
    if issue.issue_type != "pset_missing":
        return False
    return _specialized_pset_template_key(issue) is not None


# v7.7: relation_broken entra no conjunto. O template relation_missing existia
# desde o v7.6, mas com o bSDD resolvendo a classe do elemento
# (``is_grounded=True``) a issue caia em ``build_compact_prompt`` e o
# vocabulario de subtipos de IfcRelationship nunca chegou ao fio — 0,00 em
# 20/20 estagios nas rodadas v7.5 e v7.6. Mesma regressao de roteamento de
# 2026-07-27, num terceiro issue_type.
_RICH_TEMPLATE_ISSUE_TYPES = {"space_unnamed", "system_unclassified", "relation_broken"}


def has_rich_template(issue: Issue) -> bool:
    """True se a issue tem template rico que o prompt compacto nao deve substituir.

    ``space_unnamed`` e ``system_unclassified`` carregam a evidencia da tarefa
    (mobiliario, adjacencias, area; camadas de material, espessura) e o
    vocabulario canonico no proprio template; os psets especializados carregam
    a norma. Substitui-los pelo prompt compacto foi a regressao do benchmark de
    2026-07-27 (masked caiu de 34-56% para 0-5% de top-1).
    """
    if issue.issue_type in _RICH_TEMPLATE_ISSUE_TYPES:
        return True
    return has_specialized_pset_template(issue)


def _select_template(issue: Issue) -> str:
    """Seleciona o template correto pelo issue_type, sub-tipo e contexto."""
    if issue.issue_type == "pset_missing":
        key = _specialized_pset_template_key(issue)
        if key is not None:
            return TEMPLATES[key]
        return TEMPLATES["pset_missing_generic"]
    if issue.issue_type == "relation_broken":
        # v7.6: template unico. O ramo so escolhe o texto do SINTOMA (montado em
        # build_prompt); a pergunta e o vocabulario sao os mesmos, e nenhum dos
        # dois nomeia a relacao esperada.
        return TEMPLATES["relation_missing"]
    if issue.issue_type == "system_unclassified":
        if issue.element_class in ("IfcSlab", "IfcSlabStandardCase"):
            return TEMPLATES["system_unclassified_slab"]
        if issue.element_class in ("IfcBeam", "IfcColumn"):
            return TEMPLATES["system_unclassified_structural"]
        return TEMPLATES["system_unclassified"]
    if issue.issue_type == "quantity_missing":
        return TEMPLATES["quantity_missing"]
    if issue.issue_type == "material_unmapped":
        return TEMPLATES["material_unmapped"]
    if issue.issue_type == "thermal_incomplete":
        return TEMPLATES["thermal_incomplete"]
    if issue.issue_type == "classification_missing":
        return TEMPLATES["classification_missing"]
    if issue.issue_type == "asset_unidentified":
        return TEMPLATES["asset_unidentified"]
    template = TEMPLATES.get(issue.issue_type)
    if template is None:
        logger.warning("Nenhum template para issue_type '{}', usando genérico", issue.issue_type)
        return TEMPLATES["pset_missing_generic"]
    return template


_MAX_ELEMENT_LABELS = 12
"""Rotulos distintos que cabem no prompt antes de virar ruido."""


_CODIGO_REVIT = re.compile(r"^[A-Z0-9][A-Z0-9\-\.]*$")
"""Segmento so de maiusculas/digitos: codigo de familia (F05770PT), nao nome."""

_DIMENSAO_REVIT = re.compile(r"^[\d\s.,x×]+\s*(mm|cm|m)?$", re.IGNORECASE)
"""Segmento de dimensao do tipo Revit: '26000 x 14000 mm'."""

_PALAVRAS_GENERICAS = {"blocks", "blocos", "generic", "generico", "genérico"}


def _clean_element_label(label: str) -> str:
    """Limpa o rotulo de um elemento contido, guardando so o que identifica.

    O exportador emite ``IfcBuildingElementProxy: Blocks_Caixa de Luz_F05770PT:
    Unico:1178721``: o id interno nao distingue nada (16 caixas de luz tem 16
    ids), o codigo de familia e ruido e o prefixo da classe se repete em toda
    linha. Sobra ``Caixa de Luz``, que e o que responde a pergunta.
    """
    texto = str(label).strip()
    if ": " in texto and texto.split(": ", 1)[0].startswith("Ifc"):
        texto = texto.split(": ", 1)[1]

    segmentos: list[str] = []
    for bruto in texto.split(":"):
        seg = bruto.strip()
        if not seg or seg.isdigit() or _DIMENSAO_REVIT.match(seg):
            continue
        # "Blocks_Caixa de Luz_F05770PT" -> "Caixa de Luz"
        pedacos = [
            p.strip()
            for p in seg.split("_")
            if p.strip()
            and not _CODIGO_REVIT.match(p.strip())
            and p.strip().casefold() not in _PALAVRAS_GENERICAS
        ]
        limpo = " ".join(pedacos).strip() if pedacos else seg
        if limpo:
            segmentos.append(limpo)

    if not segmentos:
        return "elemento"
    # O segmento mais descritivo e o que nomeia o objeto.
    return max(segmentos, key=len)


def _format_elements(elements: list[dict | str] | Any) -> str:
    """Formata elementos contidos agrupando repetidos e limpando ruido.

    Um espaco do predio chega a 84 elementos contidos com 43 rotulos distintos;
    despejar a lista crua soterra o sinal ("central de medidores") em ids do
    Revit. Agrupa por rotulo, ordena do mais frequente e trunca avisando.
    """
    if not elements or not isinstance(elements, list):
        return "nenhum"

    contagem: dict[str, int] = {}
    for el in elements:
        if isinstance(el, dict):
            bruto = el.get("functional_label") or el.get("name") or el.get("ifc_class", "")
        else:
            bruto = str(el)
        if not bruto:
            continue
        rotulo = _clean_element_label(bruto)
        contagem[rotulo] = contagem.get(rotulo, 0) + 1

    if not contagem:
        return "nenhum"

    ordenado = sorted(contagem.items(), key=lambda kv: (-kv[1], kv[0]))
    visiveis = ordenado[:_MAX_ELEMENT_LABELS]
    partes = [f"{n}x {rotulo}" if n > 1 else rotulo for rotulo, n in visiveis]
    restantes = len(ordenado) - len(visiveis)
    if restantes > 0:
        partes.append(f"(+{restantes} outros tipos, mais raros)")
    return ", ".join(partes)


def _format_planta(bounding_box: Any) -> str:
    """Descreve as dimensoes em planta a partir do bounding box do espaco.

    O template pede largura para separar circulacao de ambiente ("estreito
    < 1,5 m"), mas ``Perimeter`` vem ``None`` em todos os espacos do predio. O
    bounding box existe em todos e da a informacao diretamente.
    """
    if not isinstance(bounding_box, dict):
        return "N/D"
    try:
        largura = abs(float(bounding_box["max_x"]) - float(bounding_box["min_x"]))
        comprimento = abs(float(bounding_box["max_y"]) - float(bounding_box["min_y"]))
    except (KeyError, TypeError, ValueError):
        return "N/D"
    if largura <= 0 or comprimento <= 0:
        return "N/D"

    menor, maior = sorted((largura, comprimento))
    texto = f"{largura:.1f} x {comprimento:.1f} m (menor dimensão {menor:.1f} m)"
    if menor < 1.5:
        texto += " — ESTREITO"
    elif maior / menor >= 3.0:
        texto += " — alongado (proporção 1:%.0f)" % (maior / menor)
    return texto


def _format_spaces(spaces: list[dict | str] | Any) -> str:
    """Formata lista de espaços (dicts com guid/name ou strings) para texto legível."""
    if not spaces or not isinstance(spaces, list):
        return "nenhum"
    parts: list[str] = []
    for s in spaces:
        if isinstance(s, dict):
            name = s.get("name") or ""
            parts.append(name if name else s.get("guid", "")[:8])
        else:
            parts.append(str(s))
    return ", ".join(p for p in parts if p) or "nenhum"


_METAL_TOKENS = ("metal", "aco", "aço", "steel", "montante", "perfil")


def _is_stud_cavity(layers: list[dict], index: int) -> bool:
    """True quando a camada é montante metálico entre outras — cavidade, não maciço.

    Numa parede leve, a camada central de "Metal" é o montante, e o que ocupa o
    vão entre montantes é **ar**. Tratá-la como metal maciço (λ = 55) produz
    resistência quase nula: medido no smoke do v7, foi exatamente isso que fez o
    drywall (222 issues) sair 49% do ground truth.

    Só vale para camada **interna** de um pacote com 3+ camadas: chapa metálica
    de face é metal de verdade.
    """
    if len(layers) < 3 or index in (0, len(layers) - 1):
        return False
    nome = str(layers[index].get("name") or "").casefold()
    return any(token in nome for token in _METAL_TOKENS)


def _format_medida(valor: float, casas: int) -> str:
    """Arredonda medida do IFC para exibição, sem zeros e sem ruído binário."""
    texto = f"{valor:.{casas}f}".rstrip("0").rstrip(".")
    return texto or "0"


def _format_thickness_cm(thickness_m: float) -> str:
    """Formata espessura de camada em cm, preservando o milímetro.

    O arredondamento para centímetro inteiro transformava a chapa de gesso de
    1,5 cm em "2cm": o modelo que declarasse fielmente o que leu calculava
    U = 2,20 contra 2,35 do ground truth — 6,4% de erro embutido pelo próprio
    prompt, dentro de uma banda de tolerância de 10%. Também contradizia a
    espessura total exibida no mesmo estímulo (2+7+2 = 11 cm num pacote de
    10 cm).
    """
    cm = thickness_m * 100
    texto = f"{cm:.1f}".rstrip("0").rstrip(".")
    return f"{texto or '0'}cm"


def _format_material_layers(layers: list[dict] | Any) -> str:
    """Formata lista de camadas de material para texto legível.

    Anota o montante metálico como câmara de ar (evidência, não instrução —
    ver `docs/smoke-v7-2026-08-04.md` §3): a leitura entra ao lado do dado
    original, que é preservado.
    """
    if not layers or not isinstance(layers, list):
        return "não informado"
    parts: list[str] = []
    todas_dicts = all(isinstance(lay, dict) for lay in layers)
    for posicao, lay in enumerate(layers):
        if not isinstance(lay, dict):
            parts.append(str(lay))
            continue
        name = lay.get("name") or "?"
        thick = lay.get("thickness_m")
        texto = f"{name} ({_format_thickness_cm(thick)})" if thick is not None else str(name)
        if todas_dicts and _is_stud_cavity(layers, posicao):
            texto += " [montante: vão entre perfis = câmara de ar não ventilada, R = 0,17 m²K/W]"
        parts.append(texto)
    return ", ".join(parts) if parts else "não informado"


def _select_profile_template(profile_id: str, issue: Issue) -> str | None:
    """Retorna o template de perfil para (profile_id, issue_type) ou None se não existir."""
    return PROFILE_TEMPLATES.get((profile_id, issue.issue_type))


def _format_psets(psets: Any) -> str:
    """Formata o resumo de Psets do elemento como texto legível.

    Chegava ao prompt como ``repr`` de dict Python — chaves entre aspas simples,
    chaves vazias e floats com ruído binário (``1.4999999999999998``). É
    evidência do arquivo; o formato é que era ruído.
    """
    if not isinstance(psets, dict) or not psets:
        return "nenhum"
    partes: list[str] = []
    for nome, props in psets.items():
        if not isinstance(props, dict) or not props:
            continue
        campos = ", ".join(
            f"{chave}={_format_medida(valor, 3) if isinstance(valor, float) else valor}"
            for chave, valor in props.items()
        )
        partes.append(f"{nome} ({campos})")
    return "; ".join(partes) if partes else "nenhum"


def _format_context_value(value: Any) -> str:
    """Formata valores arbitrarios do contexto da issue para texto legivel."""
    if isinstance(value, list):
        if value and all(isinstance(item, dict) for item in value):
            if any("functional_label" in item or "ifc_class" in item for item in value):
                return _format_elements(value)
            if any("guid" in item or "name" in item for item in value):
                return _format_spaces(value)
        return _format_list(value)
    if isinstance(value, dict):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def build_grounded_prompt(
    issue: Issue,
    building_context: str,
    grounding_block: str,
    few_shot: str | None = None,
) -> str:
    """Constrói prompt com grounding injetado."""
    lines = [
        "Você é um engenheiro civil brasileiro especialista em BIM, IFC e normas de desempenho.",
        "",
        "CONTEXTO DA EDIFICAÇÃO:",
        building_context.strip() if building_context.strip() else "N/D",
        "",
        "CONTEXTO DA ISSUE:",
        f"- Classe do elemento: {issue.element_class}",
        f"- Nome do elemento: {issue.element_name or 'sem nome'}",
        f"- GUID: {issue.short_guid}",
        f"- Tipo da issue: {issue.issue_type}",
        f"- Descrição: {issue.description}",
    ]

    if issue.context:
        lines.append("- Dados adicionais:")
        for key, value in issue.context.items():
            lines.append(f"  - {key}: {_format_context_value(value)}")

    cleaned_grounding = grounding_block.strip()
    if cleaned_grounding:
        lines.extend(["", "GROUNDING BLOCK:", cleaned_grounding])
        lines.append(
            "RESTRIÇÃO: suas sugestões devem usar APENAS termos, propriedades e valores presentes no vocabulário acima. "
            "Não invente valores fora desse vocabulário."
        )

    if few_shot:
        lines.extend(["", "EXEMPLO:", few_shot.strip()])

    lines.extend(["", _LLM_OUTPUT_CONTRACT])
    return "\n".join(lines)


def build_prompt(
    issue: Issue,
    building_context: dict,
    profile_id: str | None = None,
    bsdd_context: BSDDContext | None = None,
    ids_context: IDSContext | None = None,
) -> tuple[str, str]:
    """Monta o prompt completo para uma issue.

    Retorna (system_prompt, user_prompt).

    Se profile_id for fornecido, tenta selecionar um template de perfil em
    PROFILE_TEMPLATES antes de cair no caminho genérico de _select_template.
    Preenche os placeholders com issue.context e building_context, e
    formata listas de elementos como texto legível.
    """
    if profile_id is not None:
        template = _select_profile_template(profile_id, issue) or _select_template(issue)
    else:
        template = _select_template(issue)

    fill_ctx: dict[str, Any] = {
        **building_context,
        **issue.context,
        "guid": issue.element_guid[:8],
        "element_class": issue.element_class,
        "element_name": issue.element_name or "sem nome",
        "current_name": issue.element_name or "sem nome",
    }

    # contained_elements: lista de dicts → extrair functional_label legível
    if "contained_elements" in fill_ctx:
        fill_ctx["contained_elements"] = _format_elements(fill_ctx["contained_elements"])

    # adjacent_spaces: lista de dicts com guid/name
    if "adjacent_spaces" in fill_ctx:
        fill_ctx["adjacent_spaces"] = _format_spaces(fill_ctx["adjacent_spaces"])

    # nearby_spaces: lista de dicts {guid, name} do diagnóstico de relações
    if "nearby_spaces" in fill_ctx:
        fill_ctx["nearby_spaces"] = _format_spaces(fill_ctx["nearby_spaces"])

    # relation_broken: o template é único e o ramo só escolhe o texto do sintoma.
    if issue.issue_type == "relation_broken":
        esperada = str(issue.context.get("expected_relation") or "")
        fill_ctx["sintoma"] = _RELATION_SINTOMAS.get(esperada, _RELATION_SINTOMA_FALLBACK)

    # Medidas de ponto flutuante do IFC chegam com ruído binário
    # (0.19999999999999998 m, 9.240000000001922 m²) e poluem o estímulo.
    for chave, casas in (("thickness_m", 3), ("area_m2", 2), ("height_m", 2)):
        valor = fill_ctx.get(chave)
        if isinstance(valor, float):
            fill_ctx[chave] = _format_medida(valor, casas)

    if isinstance(fill_ctx.get("existing_psets"), dict):
        fill_ctx["existing_psets"] = _format_psets(fill_ctx["existing_psets"])

    # Geometria em planta: o template decide corredor pela largura, mas Perimeter
    # vem None em 82 de 82 espacos do predio — o bounding_box esta em 82/82.
    if issue.issue_type in ("space_unnamed", "pset_missing"):
        fill_ctx["dimensoes"] = _format_planta(fill_ctx.get("bounding_box"))

    # system_unclassified: derivar material_layers e thickness_m do contexto do diagnóstico
    if issue.issue_type == "system_unclassified":
        layers = fill_ctx.get("materials") or []
        fill_ctx["material_layers"] = _format_material_layers(layers)
        fill_ctx.setdefault("thickness_m", fill_ctx.get("total_thickness") or "N/D")

    # pset_missing: o diagnostico grava as camadas em "layers" com a chave
    # "material"; os templates especializados (fogo, termico, estrutural) leem
    # {material_layers}. Sem esta ponte, a evidencia extraida nao chegava.
    if issue.issue_type == "pset_missing" and "layers" in fill_ctx:
        camadas = [
            {"name": lay.get("material") or lay.get("name"), "thickness_m": lay.get("thickness_m")}
            for lay in (fill_ctx.get("layers") or [])
            if isinstance(lay, dict)
        ]
        fill_ctx["material_layers"] = _format_material_layers(camadas)

    safe_ctx: defaultdict[str, Any] = defaultdict(lambda: "N/D", fill_ctx)
    user_prompt = template.format_map(safe_ctx)
    scoped_bsdd = _scoped_bsdd_context(issue, bsdd_context)
    user_prompt = _inject_grounding(user_prompt, scoped_bsdd, ids_context)
    system_prompt = SYSTEM_PROMPT
    # v7.8: a instrucao segue o que o bloco REALMENTE contem, nao a mera
    # presenca de grounding. Ver _grounding_has_closed_vocabulary.
    if _grounding_has_closed_vocabulary(scoped_bsdd, ids_context):
        system_prompt = f"{SYSTEM_PROMPT} {_GROUNDING_INSTRUCTION}"
    if issue.issue_type == "space_unnamed":
        # O template de nomeação já carrega o formato ({"opcoes":[{"nome":...}]});
        # aqui vale a mesma instrução usada nos caminhos compacto e grounded,
        # vinda de output_contract_for() para não divergirem entre si.
        user_prompt = f"{user_prompt}\n\n{output_contract_for(issue.issue_type)}"
    else:
        user_prompt = (
            f"{user_prompt}\n\nCRITERIO DE ENGENHARIA:\n"
            "Nao presuma que diferencas de espessura, material, dimensao ou tipo "
            "sejam erro de digitacao. Use esses dados para diferenciar elementos "
            "e ordenar as opcoes por confianca decrescente."
            # REGRAS, nao schema: o template acima ja declarou o formato, e
            # colar um schema divergente aqui fazia o modelo seguir este
            # (11 rejeicoes de parse no smoke do v7 contra 0 no v6).
            f"\n\nREGRAS DE SAIDA:\n{_LLM_OUTPUT_RULES}"
            f"{_MEMORIA_CONTRACT_SUFFIX if uses_layered_thermal_template(issue) else ''}"
        )

    return system_prompt, user_prompt


def _scoped_bsdd_context(issue: Issue, bsdd_context: BSDDContext | None) -> BSDDContext | None:
    """Restringe o bloco bSDD ao que a tarefa da issue realmente usa.

    Classificar sistema construtivo nao e preencher propriedade nem nomear a
    entidade IFC. Para ``system_unclassified``, duas coisas precisam sair do
    bloco — e as duas foram medidas em 2026-07-27 custando o estrato inteiro:

    1. **Lista de propriedades da classe** (Warranty Content, Net Volume, Surface
       Genus, Mean Time Between Failure...). Com ela no prompt, o gemma2:9b
       respondia ``Thickness``, ``Dimensions`` e ``Mean Time Between Failure``
       como sistema construtivo: 0,000 de top-1 em 872 issues.
    2. **Nomes de classe IFC entre as "classes candidatas"**. Com
       ``- IfcWall`` no bloco, o qwen2.5:7b-instruct respondia literalmente
       ``IfcWall``/``IfcSlab``: tambem 0,000 — enquanto o gemma2, que ignorou a
       instrucao, fez 0,977 no mesmo prompt.

    Classificacoes de dominio (nao-IFC) continuam sendo grounding legitimo. Se
    nada aproveitavel sobrar, devolve None: bloco de grounding vazio so gasta
    contexto e convida o modelo a inventar.
    """
    if bsdd_context is None:
        return None

    if issue.issue_type != "system_unclassified":
        # v7.8: sem propriedade pedida, nao ha propriedade a fundamentar — e a
        # lista da classe vira o prompt inteiro. Medido em 2026-08-18 no
        # relation_broken de porta: 42.473 chars de catalogo do IfcDoor contra
        # 434 do bloco mediano, prompt de 44,8 KB (~20,7 mil tokens estimados)
        # contra teto de janela 8192. O servidor cortava o inicio, que e onde
        # esta a tarefa, e os dez modelos respondiam tokens do proprio bloco
        # ("BARREL", "TEU", "PASSENGER" — enumeracao de logistica do IFC 4.3).
        # A ancora de classe (definicao + URI) fica: e grounding legitimo.
        if not str(issue.context.get("check_property") or "").strip():
            return bsdd_context.model_copy(
                update={"related_properties": [], "properties": []}
            )
        return bsdd_context

    classes_dominio = [
        cls
        for cls in bsdd_context.classification_suggestions
        if cls.name and not cls.name.strip().startswith("Ifc")
    ]
    if not classes_dominio:
        return None
    return bsdd_context.model_copy(
        update={
            "related_properties": [],
            "properties": [],
            "classification_suggestions": classes_dominio,
            "classes": classes_dominio,
            # v7.6: a definicao oficial da entidade IFC e o aviso de propriedade
            # ausente pertencem ao preenchimento de propriedade. Classificar
            # sistema construtivo nao e nomear a entidade — foi essa confusao
            # que zerou o estrato em 2026-07-27.
            "class_description": None,
            "property_absent_from_dictionary": False,
        }
    )


def _grounding_has_closed_vocabulary(
    bsdd_context: BSDDContext | None, ids_context: IDSContext | None
) -> bool:
    """Há vocabulário fechado no grounding que chegou ao prompt?

    Condiciona ``_GROUNDING_INSTRUCTION``. Mandar "use apenas o vocabulário
    fornecido" quando o bloco imprime ``livre`` em toda propriedade — o caso de
    100% das propriedades do experimento, porque o dicionário IFC 4.3 as tipa
    como ``IfcLabel`` — não restringe nada e mede-se como dano: na ablação de
    2026-08-18 o padrão das respostas escorregava para o literal mínimo
    (``EI 30`` no lugar da banda ``EI/REI 60``, ``True`` em IsLoadBearing).

    Contam como vocabulário fechado: qualquer requisito IDS (que carrega valor
    ou restrição computável), propriedades com ``allowed_values`` e
    classificações de dicionário não-IFC (onde a lista de classes É a resposta
    permitida).
    """
    if ids_context is not None:
        return True
    if bsdd_context is None:
        return False
    if any(prop.allowed_values for prop in bsdd_context.related_properties):
        return True
    return any(
        cls.name and not cls.name.strip().startswith("Ifc")
        for cls in bsdd_context.classification_suggestions
    )


def _inject_grounding(
    user_prompt: str,
    bsdd_context: BSDDContext | None,
    ids_context: IDSContext | None,
) -> str:
    """Anexa blocos de grounding estruturado (IDS + bSDD) ao prompt base."""
    blocks: list[str] = []
    if ids_context is not None:
        blocks.append("IDS_CONTEXT:")
        blocks.append(ids_context.as_prompt_block())
    if bsdd_context is not None:
        blocks.append("BSDD_CONTEXT:")
        blocks.append(bsdd_context.as_prompt_block())
    if not blocks:
        return user_prompt
    return f"{user_prompt}\n\n" + "\n".join(blocks)


# ---------------------------------------------------------------------------
# Parser de resposta LLM
# ---------------------------------------------------------------------------

_VALID_CONFIDENCES = ("alta", "media", "baixa")
_OPTION_LIST_KEYS = (
    "opcoes",
    "opções",
    "opÃ§Ãµes",
    "options",
    "suggestions",
    "sugestoes",
    "sugestões",
    "sugestÃµes",
    "alternativas",
    "alternatives",
    "result",
    "results",
    "data",
    "items",
)
_LABEL_KEYS = (
    "label",
    "nome",
    "name",
    "titulo",
    "title",
    "termo",
    "term",
    "canonical_term",
    "semantic_hint",
    "sugestao",
    "suggestion",
    "option",
    "opcao",
    "descrição",
    "descricao",
    "description",
)
_VALUE_KEYS = (
    "suggested_value",
    "value",
    "valor",
    "term",
    "termo",
    "canonical_term",
    "suggestion",
    "sugestao",
    "option",
    "opcao",
    "action",
    "acao",
)
_COMPACT_FORBIDDEN_KEYS = ("bsdd_uri", "uri", "ids_uri", "official_uri")
_EXPLICIT_VALUE_KEYS = ("suggested_value", "value", "valor")
_FALLBACK_VALUE_KEYS = (
    "term",
    "termo",
    "canonical_term",
    "suggestion",
    "sugestao",
    "option",
    "opcao",
    "action",
    "acao",
)
_JUSTIFICATION_KEYS = (
    "justificativa",
    "justification",
    "justificacao",
    "reason",
    "rationale",
    "explanation",
    "motivo",
    "porque",
)
_CONFIDENCE_KEYS = (
    "confianca",
    "confiança",
    "confidence",
    "certainty",
    "probability",
    "probabilidade",
    "confidence_level",
    "nivel_confianca",
    "score",
)


def _first_present(opt: dict, keys: tuple[str, ...], default: Any = None) -> Any:
    for key in keys:
        value = opt.get(key)
        if value is not None and value != "":
            return value
    return default


def _normalize_confidence(value: Any) -> str:
    if isinstance(value, (int, float)):
        if value >= 0.75:
            return "alta"
        if value >= 0.45:
            return "media"
        return "baixa"

    normalized = str(value or "").strip().casefold()
    aliases = {
        "alta": "alta",
        "high": "alta",
        "alto": "alta",
        "strong": "alta",
        "media": "media",
        "média": "media",
        "medium": "media",
        "moderate": "media",
        "baixa": "baixa",
        "low": "baixa",
        "baixo": "baixa",
        "weak": "baixa",
    }
    if normalized.endswith("%"):
        try:
            return _normalize_confidence(float(normalized[:-1].replace(",", ".")) / 100)
        except ValueError:
            return "baixa"
    try:
        numeric = float(normalized.replace(",", "."))
    except ValueError:
        return aliases.get(normalized, "baixa")
    return _normalize_confidence(numeric)


def _normalize_option(opt: dict, issue_type: str) -> Suggestion | None:
    """Converte um item de 'opcoes' do JSON do LLM em Suggestion.

    Retorna None se o item não tiver label válido.
    """
    justification = str(_first_present(opt, _JUSTIFICATION_KEYS, "") or "")
    confidence = _normalize_confidence(_first_present(opt, _CONFIDENCE_KEYS, "baixa"))
    normative_ref: str | None = opt.get("ref") or opt.get("normative_ref")
    canonical_term = opt.get("canonical_term")
    semantic_hint = opt.get("semantic_hint")
    # Memória de cálculo estruturada (contrato v7 do térmico): o LLM declara os
    # termos, a aritmética é feita por thermal_recompute.py.
    calc_memory = opt.get("memoria_calculo") or opt.get("calc_memory") or opt.get("memoria")
    source_candidates_raw = opt.get("source_candidates") or []
    review_required = bool(opt.get("review_required", False))

    if issue_type in ("space_unnamed",):
        label = _first_present(opt, _LABEL_KEYS, "")
        value: Any = _first_present(opt, _VALUE_KEYS, label)
    elif issue_type == "system_unclassified":
        label = opt.get("sistema") or _first_present(opt, _LABEL_KEYS, "")
        value = _first_present(opt, _VALUE_KEYS, label)
    elif issue_type == "classification_missing":
        label = opt.get("codigo") or opt.get("code") or _first_present(opt, _LABEL_KEYS, "")
        value = _first_present(opt, _VALUE_KEYS, label)
    elif issue_type == "asset_unidentified":
        label = opt.get("nome_ativo") or opt.get("asset_name") or _first_present(opt, _LABEL_KEYS, "")
        value = _first_present(opt, _VALUE_KEYS, label)
    else:
        raw_val = _first_present(opt, _EXPLICIT_VALUE_KEYS, None)
        if raw_val is None:
            raw_val = _first_present(opt, _LABEL_KEYS, "")
        if raw_val is None or raw_val == "":
            raw_val = _first_present(opt, _FALLBACK_VALUE_KEYS, "")
        label = str(raw_val) if raw_val != "" else ""
        value = raw_val

    if not label:
        return None
    label = str(label).strip()
    if not label:
        return None

    source_candidates: list[str] = []
    if isinstance(source_candidates_raw, list):
        source_candidates = [str(candidate).strip() for candidate in source_candidates_raw if str(candidate).strip()]
    elif isinstance(source_candidates_raw, str) and source_candidates_raw.strip():
        source_candidates = [source_candidates_raw.strip()]

    return Suggestion(
        label=label,
        value=value,
        justification=justification,
        confidence=confidence,
        normative_ref=normative_ref,
        source="llm",
        canonical_term=str(canonical_term).strip() if canonical_term is not None and str(canonical_term).strip() else None,
        semantic_hint=str(semantic_hint).strip() if semantic_hint is not None and str(semantic_hint).strip() else None,
        source_candidates=source_candidates,
        calc_memory=calc_memory if isinstance(calc_memory, dict) else None,
        review_required=review_required,
        ids_requirement_id=opt.get("ids_requirement_id"),
    )


def _strip_thinking_tags(text: str) -> str:
    """Remove blocos <think>...</think> emitidos por modelos com modo de raciocínio.

    Modelos como Qwen3 e DeepSeek-R1 emitem raciocínio interno antes da resposta.
    Trata dois casos:
    - Bloco fechado: <think>...</think> → remove o bloco inteiro
    - Bloco aberto (truncado por num_predict): <think>... → remove tudo até o primeiro {
      que pareça início de JSON válido fora do bloco de thinking
    """
    # Caso 1: bloco fechado corretamente
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    if cleaned:
        return cleaned

    # Caso 2: bloco aberto — tenta encontrar JSON após qualquer conteúdo de thinking
    if '<think>' in text:
        after_think = text.split('<think>', 1)[-1]
        # Procura pelo primeiro { que seja início de objeto JSON válido fora do thinking
        match = re.search(r'\{', after_think)
        if match:
            candidate = after_think[match.start():]
            # Verifica se parece JSON de sugestoes.
            if any(f'"{key}"' in candidate for key in _OPTION_LIST_KEYS):
                return candidate
        return ''

    return text.strip()


def _extract_json_object(raw: str, telemetry: dict | None = None) -> dict | None:
    """Tenta extrair e parsear o primeiro objeto JSON da string.

    Tenta três estratégias: parse direto, regex entre { e }, linha a linha.
    Remove blocos <think>...</think> antes de tentar (Qwen3, DeepSeek-R1).
    Quando ``telemetry`` é fornecido, registra ``json_repaired`` (reparo de
    truncamento usado).
    """
    stripped = _strip_thinking_tags(raw.strip())
    if not stripped:
        return None

    # 1. Parse direto
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
        if isinstance(result, list):
            return {"opcoes": result}
    except json.JSONDecodeError as exc:
        logger.debug("_extract_json_object: parse direto falhou: {}", exc)

    # 2. Reparo de truncamento: LLMs frequentemente truncam os colchetes/chaves finais.
    #    Tenta fechar o JSON progressivamente até ser válido.
    repaired = _repair_truncated_json(stripped)
    if repaired is not None:
        logger.debug("_extract_json_object: JSON reparado com sucesso")
        if telemetry is not None:
            telemetry["json_repaired"] = True
        return repaired

    # 3. Regex: último objeto JSON entre { e } (evita pegar fragmentos do thinking)
    matches = list(re.finditer(r'\{.*\}', stripped, re.DOTALL))
    for match in reversed(matches):
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
            if isinstance(result, list):
                return {"opcoes": result}
        except json.JSONDecodeError as exc:
            logger.debug("_extract_json_object: regex match falhou: {}", exc)

    logger.warning("_extract_json_object: nenhuma estratégia extraiu JSON válido. Raw: {!r}", stripped[:300])
    return None


def _repair_truncated_json(text: str) -> dict | None:
    """Tenta recuperar JSON truncado pelo limite de tokens do LLM.

    Estratégia: conta chaves e colchetes abertos, fecha na ordem correta.
    Retorna o dict parseado ou None se não conseguir reparar.
    """
    stack: list[str] = []
    in_string = False
    escape_next = False

    for ch in text:
        if escape_next:
            escape_next = False
            continue
        if ch == '\\' and in_string:
            escape_next = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch in ('{', '['):
            stack.append(']' if ch == '[' else '}')
        elif ch in ('}', ']'):
            if stack and stack[-1] == ch:
                stack.pop()

    if not stack:
        return None  # JSON já está íntegro — falhou por outro motivo

    closing = ''.join(reversed(stack))
    for suffix in [closing, closing.rstrip('}') + '}', closing + '}']:
        candidate = text + suffix
        try:
            result = json.loads(candidate)
            if isinstance(result, dict):
                return result
            if isinstance(result, list):
                return {"opcoes": result}
        except json.JSONDecodeError:
            continue

    return None


def _get_options_robust(parsed: dict) -> Any:
    """Extrai opcoes de resposta LLM com aliases e wrappers comuns."""
    for key in _OPTION_LIST_KEYS:
        options = parsed.get(key)
        if options is not None:
            if isinstance(options, dict):
                nested = _get_options_robust(options)
                if nested:
                    return nested
            return options
    if any(key in parsed for key in _LABEL_KEYS + _VALUE_KEYS):
        return [parsed]
    return []


def parse_llm_response(
    response: str, issue_type: str, telemetry: dict | None = None
) -> list[Suggestion]:
    """Parseia a resposta JSON do LLM e retorna lista de Suggestions.

    Tenta json.loads direto, extração via regex e, como último recurso,
    parse linha a linha. Sempre retorna lista (pode ser vazia).
    Define source="llm" em todas as sugestões geradas.

    Quando ``telemetry`` é fornecido (dict mutável), registra ``json_found``
    (algum objeto JSON foi extraído) e ``json_repaired`` (reparo de truncamento
    usado), para instrumentação de estabilidade (F12).
    """
    logger.debug("parse_llm_response raw ({} chars): {!r}", len(response), response[:2000])
    parsed = _extract_json_object(response, telemetry=telemetry)
    if telemetry is not None:
        telemetry["json_found"] = parsed is not None

    if parsed is None:
        # Fallback: linha a linha
        suggestions: list[Suggestion] = []
        for line in response.splitlines():
            line = line.strip()
            if line.startswith("{") and line.endswith("}"):
                try:
                    obj = json.loads(line)
                    if isinstance(obj, dict):
                        s = _normalize_option(obj, issue_type)
                        if s:
                            suggestions.append(s)
                    elif isinstance(obj, list):
                        for item in obj:
                            if isinstance(item, dict):
                                s = _normalize_option(item, issue_type)
                                if s:
                                    suggestions.append(s)
                except json.JSONDecodeError:
                    pass
        return suggestions

    options = _get_options_robust(parsed)
    if not isinstance(options, list):
        logger.warning("Resposta LLM sem lista 'opcoes' válida: {}", parsed)
        return []

    result: list[Suggestion] = []
    for opt in options:
        if isinstance(opt, dict):
            s = _normalize_option(opt, issue_type)
            if s:
                result.append(s)

    return result
