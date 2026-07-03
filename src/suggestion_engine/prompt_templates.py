"""Templates de prompt e parser de resposta LLM para o SuggestionGenerator."""

import json
import re
from collections import defaultdict
from typing import Any, TYPE_CHECKING

from loguru import logger

from src.models import BSDDContext, IDSContext, Issue, Suggestion

if TYPE_CHECKING:
    from src.suggestion_engine.grounding import GroundedIssueContext

# v4: contrato genérico não é mais anexado ao template de space_unnamed
# (só o prompt de nomeação muda entre v3 e v4; demais tarefas são idênticas).
PROMPT_VERSION = "v4"

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
    " Maximo 3 opcoes. Nao retorne URI. Se nao houver candidato confiavel, use review_required=true."
    " Ordene opcoes por confianca decrescente. Nao trate diferenca de espessura, material ou dimensao como erro de digitacao."
)


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
    lines.append(_COMPACT_OUTPUT_CONTRACT)
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
    lines.append(_COMPACT_OUTPUT_CONTRACT)
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

_HEADER_BR = "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"

TEMPLATES: dict[str, str] = {
    "space_unnamed": (
        _HEADER_BR +
        "ISSUE: IfcSpace #{guid}, nome atual \"{current_name}\"\n"
        "DADOS:\n"
        "- Área: {area_m2} m²\n"
        "- Pé-direito: {height_m} m\n"
        "- Perímetro: {perimeter_m} m\n"
        "- Pavimento: {floor}\n"
        "- Fronteira com exterior: {is_on_exterior}\n"
        "- Elementos presentes: {contained_elements}\n"
        "- Espaços adjacentes: {adjacent_spaces}\n"
        "INTERPRETAÇÃO DOS ELEMENTOS:\n"
        "  sofá/poltrona/cadeira → sala de estar | cama/berço → dormitório\n"
        "  mesa de jantar/cadeiras de jantar → sala de jantar\n"
        "  fogão/cooktop/forno → cozinha | pia de cozinha/bancada → cozinha\n"
        "  armário de cozinha/geladeira → cozinha\n"
        "  vaso sanitário/WC → banheiro/lavabo | cuba/lavatório/pia → banheiro/cozinha\n"
        "  chuveiro/box → banheiro | banheira → banheiro\n"
        "  tanque/máquina de lavar → área de serviço\n"
        "  TV/televisão → sala de estar | estante de livros → escritório/quarto\n"
        "  bancada de laboratório/equipamento científico → laboratório\n"
        "  mesa de escritório/computador → escritório\n"
        "ATENÇÃO:\n"
        "  - Laboratório tem bancadas de trabalho e equipamentos específicos, NÃO é quarto\n"
        "  - Sala de estar tem sofá e/ou TV, NÃO é área de circulação\n"
        "  - Sala de jantar tem mesa e cadeiras de jantar, NÃO é circulação\n"
        "  - Quarto tem cama; armazenamento tem prateleiras/caixas\n"
        "  - Corredor/circulação é estreito (largura tipicamente < 1,5 m) e sem mobiliário\n"
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
        "- Espessura total: {thickness_m} m\n"
        "- Com reboco: {has_plaster}\n"
        "- Elemento estrutural: {is_structural}\n"
        "NORMA: NBR 15575-4 Tabela C.2 — Transmitância térmica máxima de paredes externas\n"
        "TAREFA: Sugira 3 valores possíveis para ThermalTransmittance [W/(m²·K)] "
        "com base no material e espessura, do mais provável ao menos provável. "
        "Retorne valor numérico puro em JSON, sem unidade no campo valor.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": 2.48, "justificativa": "...", '
        '"ref": "NBR 15575-4 Tab. C.2", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_fire": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade FireRating ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Nome: {element_name}\n"
        "- Material: {material_name}\n"
        "NORMA: ABNT NBR 14432 — Exigências de resistência ao fogo de elementos construtivos\n"
        "TAREFA: Sugira 3 valores de FireRating no formato canônico \"REI 60\", \"REI 90\", \"REI 120\" "
        "para este elemento, do mais provável ao menos provável.\n"
        "RESTRICAO: o campo valor/value deve ser gravavel no IFC e conter apenas classe de resistencia "
        "ao fogo + minutos, como \"REI 30\", \"REI 60\", \"EI 30\" ou \"EI 60\". "
        "Use duracoes usuais como 30, 60, 90 ou 120 minutos. "
        "Nao use A1, N/A, NC, R 1, FireRating, nomes de propriedade, descricoes ou texto explicativo como valor.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "REI 60", "justificativa": "...", '
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
        "- Área: {area_m2} m²\n"
        "- Contém: {contained_elements}\n"
        "- Adjacente a: {adjacent_spaces}\n"
        "CATEGORIAS VÁLIDAS (IFC): BEDROOM, LIVING_ROOM, KITCHEN, BATHROOM, WC, CIRCULATION, "
        "SERVICE_AREA, OFFICE, MEETING_ROOM, LOBBY, STORAGE, BALCONY, GARAGE, TECHNICAL_AREA\n"
        "TAREFA: Identifique a Category IFC mais provável para este espaço com base no nome, "
        "área e elementos contidos. Retorne 3 opções ordenadas por probabilidade.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "BEDROOM", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "system_unclassified": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), sistema construtivo não classificado\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Camadas de material: {material_layers}\n"
        "SISTEMAS CONSTRUTIVOS COMUNS DE PAREDE (Brasil): "
        "Alvenaria de vedação em bloco cerâmico, "
        "Alvenaria estrutural em bloco cerâmico, Concreto armado moldado in loco, "
        "Concreto pré-moldado, Drywall / Steel frame, Alvenaria em bloco de concreto, "
        "Estrutura metálica, Painel de EPS\n"
        "TAREFA: Classifique o sistema construtivo desta parede com 3 opções "
        "ordenadas por probabilidade, considerando o material e espessura informados.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"sistema": "Alvenaria de vedação em bloco cerâmico", '
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
        "ordenadas por probabilidade. Use rótulos canônicos consistentes e sem variações redundantes "
        "para o mesmo sistema. Use o nome do objeto e camadas de material como pistas principais.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"sistema": "...", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "relation_fills_missing": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\") não possui IfcRelFillsElement — "
        "não está inserido em nenhuma abertura de parede no modelo IFC.\n"
        "DADOS:\n"
        "- Elemento: {element_class} \"{element_name}\"\n"
        "- Espaços no mesmo pavimento: {nearby_spaces}\n"
        "NORMA: ISO 16739-1 — IfcRelFillsElement vincula porta/janela à abertura (IfcOpeningElement) na parede\n"
        "TAREFA: Sugira 3 ações de diagnóstico e correção que o engenheiro deve executar "
        "no software BIM (Revit, ArchiCAD, etc.) para resolver este problema. "
        "Seja específico sobre o que verificar. Cada ação deve ser diferente.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "Verificar se o elemento foi inserido diretamente na parede '
        'ou apenas posicionado no modelo sem hospedeiro", '
        '"justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "relation_orphan": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\") não possui "
        "IfcRelContainedInSpatialStructure — não está associado a nenhum espaço ou pavimento.\n"
        "DADOS:\n"
        "- Elemento: {element_class} \"{element_name}\"\n"
        "- Espaços no mesmo pavimento: {nearby_spaces}\n"
        "NORMA: ISO 16739-1 — Todo elemento deve estar contido em uma estrutura espacial IFC\n"
        "TAREFA: Sugira 3 ações para associar este elemento ao espaço correto. "
        "Priorize os espaços listados acima se houver.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "...", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_acoustic": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Material: {material_name}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Externo: {is_external}\n"
        "NORMA: NBR 15575-4/5 — Desempenho acústico de vedações e lajes\n"
        "CLASSES DE DESEMPENHO (NBR 15575): D (mínimo) | M (intermediário) | S (superior)\n"
        "EXEMPLOS DE VALORES IFC para AcousticRating:\n"
        "  - Alvenaria 14cm: 'D' ou '35 dB'\n"
        "  - Concreto 12cm: 'M' ou '42 dB'\n"
        "  - Drywall duplo: 'S' ou '50 dB'\n"
        "TAREFA: Sugira 3 valores de {check_property} para este elemento, "
        "do mais provável ao menos provável. Use a classe de desempenho (D/M/S) ou valor em dB.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "...", "justificativa": "...", '
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
        "NORMA: NBR 15575-5 — Transmitância térmica de lajes e coberturas\n"
        "LIMITES MÁXIMOS (U em W/m²·K):\n"
        "  Zona 1-2 (frio): cobertura ≤ 2,30 | piso ≤ 2,00\n"
        "  Zona 3-6 (ameno): cobertura ≤ 2,30 | piso ≤ 2,00\n"
        "  Zona 7-8 (quente): cobertura ≤ 1,00 | piso ≤ 2,00\n"
        "TAREFA: Sugira 3 valores para ThermalTransmittance [W/(m²·K)] "
        "com base no material e espessura, do mais provável ao menos provável.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": 1.80, "justificativa": "...", '
        '"ref": "NBR 15575-5", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_solar": (
        _HEADER_BR +
        "ISSUE: IfcWindow #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Material/tipo de vidro: {material_name}\n"
        "- Externo: {is_external}\n"
        "- ThermalTransmittance (U): {existing_psets}\n"
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
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": 0.87, "justificativa": "...", '
        '"ref": "NBR 15575-4", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_structural": (
        _HEADER_BR +
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Nome: {element_name}\n"
        "- Material: {material_name}\n"
        "- Espessura/seção: {thickness_m} m\n"
        "INTERPRETAÇÃO:\n"
        "  IfcBeam/IfcColumn em concreto armado → normalmente LoadBearing = True\n"
        "  IfcWall fina (< 10cm) ou Drywall → geralmente LoadBearing = False\n"
        "  IfcSlab entre pavimentos → normalmente LoadBearing = True\n"
        "TAREFA: Sugira 3 valores booleanos (True/False) para {check_property} "
        "com justificativa baseada no tipo de elemento e material.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": true, "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
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
        "Formato JSON:\n"
        '{{"opcoes": [{{"sistema": "Viga de concreto armado moldada in loco", '
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
        "Formato JSON:\n"
        '{{"opcoes": [{{"codigo": "74209/001", "sistema": "SINAPI", "descricao": "...", '
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
        if issue.element_class in ("IfcSlab", "IfcSlabStandardCase", "IfcRoof", "IfcCurtainWall"):
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
    if prop in ("LoadBearing", "IsLoadBearing", "HasNonSkidSurface"):
        return "pset_missing_structural"
    return None


def has_specialized_pset_template(issue: Issue) -> bool:
    """True se a issue pset_missing tem template especializado (térmico, fogo, etc.).

    Usado pelo roteamento da Fase A.2: issues genéricas COM grounding vão para
    ``build_pset_grounded_prompt``; as especializadas mantêm o caminho atual.
    """
    if issue.issue_type != "pset_missing":
        return False
    return _specialized_pset_template_key(issue) is not None


def _select_template(issue: Issue) -> str:
    """Seleciona o template correto pelo issue_type, sub-tipo e contexto."""
    if issue.issue_type == "pset_missing":
        key = _specialized_pset_template_key(issue)
        if key is not None:
            return TEMPLATES[key]
        return TEMPLATES["pset_missing_generic"]
    if issue.issue_type == "relation_broken":
        expected = issue.context.get("expected_relation", "")
        if expected == "IfcRelFillsElement":
            return TEMPLATES["relation_fills_missing"]
        return TEMPLATES["relation_orphan"]
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


def _format_elements(elements: list[dict | str] | Any) -> str:
    """Formata lista de elementos contidos extraindo functional_label legível."""
    if not elements or not isinstance(elements, list):
        return "nenhum"
    parts: list[str] = []
    for el in elements:
        if isinstance(el, dict):
            label = el.get("functional_label") or el.get("name") or el.get("ifc_class", "")
            if label:
                parts.append(label)
        else:
            parts.append(str(el))
    return ", ".join(p for p in parts if p) or "nenhum"


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


def _format_material_layers(layers: list[dict] | Any) -> str:
    """Formata lista de camadas de material para texto legível."""
    if not layers or not isinstance(layers, list):
        return "não informado"
    parts: list[str] = []
    for lay in layers:
        if not isinstance(lay, dict):
            parts.append(str(lay))
            continue
        name = lay.get("name") or "?"
        thick = lay.get("thickness_m")
        if thick is not None:
            parts.append(f"{name} ({thick * 100:.0f}cm)")
        else:
            parts.append(name)
    return ", ".join(parts) if parts else "não informado"


def _select_profile_template(profile_id: str, issue: Issue) -> str | None:
    """Retorna o template de perfil para (profile_id, issue_type) ou None se não existir."""
    return PROFILE_TEMPLATES.get((profile_id, issue.issue_type))


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

    # system_unclassified: derivar material_layers e thickness_m do contexto do diagnóstico
    if issue.issue_type == "system_unclassified":
        layers = fill_ctx.get("materials") or []
        fill_ctx["material_layers"] = _format_material_layers(layers)
        fill_ctx.setdefault("thickness_m", fill_ctx.get("total_thickness") or "N/D")

    safe_ctx: defaultdict[str, Any] = defaultdict(lambda: "N/D", fill_ctx)
    user_prompt = template.format_map(safe_ctx)
    user_prompt = _inject_grounding(user_prompt, bsdd_context, ids_context)
    system_prompt = SYSTEM_PROMPT
    if ids_context is not None or bsdd_context is not None:
        system_prompt = f"{SYSTEM_PROMPT} {_GROUNDING_INSTRUCTION}"
    if issue.issue_type == "space_unnamed":
        # O template de nomeação carrega contrato próprio ({"opcoes":[{"nome":...}]}).
        # Anexar o contrato genérico (canonical_term/semantic_hint) por cima
        # desviava o LLM para pseudo-classes IFC ("IfcKitchen") em vez de nomes
        # funcionais — detectado no benchmark (nomeação com top-1 = 0%).
        user_prompt = (
            f"{user_prompt}\n\nIMPORTANTE: o campo 'nome' deve ser o nome funcional "
            "do ambiente em portugues (ex.: 'Sala de Estar', 'Banheiro Social'), "
            "nunca classe IFC, termo tecnico ou identificador."
        )
    else:
        user_prompt = (
            f"{user_prompt}\n\nCRITERIO DE ENGENHARIA:\n"
            "Nao presuma que diferencas de espessura, material, dimensao ou tipo "
            "sejam erro de digitacao. Use esses dados para diferenciar elementos "
            "e ordenar as opcoes por confianca decrescente."
            f"\n\nCONTRATO DE SAIDA:\n{_LLM_OUTPUT_CONTRACT}"
        )

    return system_prompt, user_prompt


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
