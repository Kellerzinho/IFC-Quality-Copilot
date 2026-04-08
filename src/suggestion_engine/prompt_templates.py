"""Templates de prompt e parser de resposta LLM para o SuggestionGenerator."""

import json
import re
from collections import defaultdict
from typing import Any

from loguru import logger

from src.models import Issue, Suggestion

SYSTEM_PROMPT = (
    "Você é um engenheiro civil brasileiro especialista em BIM, IFC e desempenho "
    "de edificações conforme a NBR 15575. Responda sempre em JSON válido, sem markdown, "
    "sem explicações fora do JSON."
)

TEMPLATES: dict[str, str] = {
    "space_unnamed": (
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
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
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
        "ISSUE: {element_class} #{guid}, propriedade ThermalTransmittance ausente\n"
        "DADOS:\n"
        "- Material: {material_name}\n"
        "- Espessura total: {thickness_m} m\n"
        "- Com reboco: {has_plaster}\n"
        "- Elemento estrutural: {is_structural}\n"
        "NORMA: NBR 15575-4 Tabela C.2 — Transmitância térmica máxima de paredes externas\n"
        "TAREFA: Sugira 3 valores possíveis para ThermalTransmittance [W/(m²·K)] "
        "com base no material e espessura, do mais provável ao menos provável.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": 2.48, "justificativa": "...", '
        '"ref": "NBR 15575-4 Tab. C.2", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_fire": (
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade FireRating ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Nome: {element_name}\n"
        "- Material: {material_name}\n"
        "NORMA: ABNT NBR 14432 — Exigências de resistência ao fogo de elementos construtivos\n"
        "TAREFA: Sugira 3 valores de FireRating (tempo de resistência em minutos, ex: \"30\", \"60\", \"90\") "
        "para este elemento, do mais provável ao menos provável.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "60", "justificativa": "...", '
        '"ref": "NBR 14432", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_generic": (
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
        "ISSUE: {element_class} #{guid} (\"{element_name}\"), propriedade {check_property} ausente\n"
        "DADOS:\n"
        "- Tipo de elemento: {element_class}\n"
        "- Nome: {element_name}\n"
        "- Pset alvo: {pset_name}\n"
        "TAREFA: Sugira 3 valores possíveis para a propriedade IFC \"{check_property}\" "
        "do Pset \"{pset_name}\", do mais provável ao menos provável. "
        "Considere o tipo de elemento e o contexto construtivo brasileiro.\n"
        "Formato JSON:\n"
        '{{"opcoes": [{{"valor": "...", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "pset_missing_space_category": (
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
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
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
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
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
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
        "Formato JSON:\n"
        '{{"opcoes": [{{"sistema": "...", "justificativa": "...", "confianca": "alta/media/baixa"}}]}}'
    ),
    "relation_fills_missing": (
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
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
        "CONTEXTO: {building_type}, zona bioclimática {bioclimatic_zone}.\n"
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


def _select_template(issue: Issue) -> str:
    """Seleciona o template correto pelo issue_type, sub-tipo e contexto."""
    if issue.issue_type == "pset_missing":
        prop = issue.context.get("check_property", "")
        if prop == "ThermalTransmittance":
            return TEMPLATES["pset_missing_thermal"]
        if prop == "FireRating":
            return TEMPLATES["pset_missing_fire"]
        if prop == "Category" and issue.element_class in ("IfcSpace",):
            return TEMPLATES["pset_missing_space_category"]
        return TEMPLATES["pset_missing_generic"]
    if issue.issue_type == "relation_broken":
        expected = issue.context.get("expected_relation", "")
        if expected == "IfcRelFillsElement":
            return TEMPLATES["relation_fills_missing"]
        return TEMPLATES["relation_orphan"]
    if issue.issue_type == "system_unclassified":
        if issue.element_class in ("IfcSlab", "IfcSlabStandardCase"):
            return TEMPLATES["system_unclassified_slab"]
        return TEMPLATES["system_unclassified"]
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


def build_prompt(
    issue: Issue,
    building_context: dict,
    profile_id: str | None = None,
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

    return SYSTEM_PROMPT, user_prompt


# ---------------------------------------------------------------------------
# Parser de resposta LLM
# ---------------------------------------------------------------------------

_VALID_CONFIDENCES = ("alta", "media", "baixa")


def _normalize_option(opt: dict, issue_type: str) -> Suggestion | None:
    """Converte um item de 'opcoes' do JSON do LLM em Suggestion.

    Retorna None se o item não tiver label válido.
    """
    justification = opt.get("justificativa", "")
    confidence_raw = opt.get("confianca", "baixa")
    confidence = confidence_raw if confidence_raw in _VALID_CONFIDENCES else "baixa"
    normative_ref: str | None = opt.get("ref")

    if issue_type in ("space_unnamed",):
        label = opt.get("nome", "")
        value: Any = label
    elif issue_type == "system_unclassified":
        label = opt.get("sistema", "")
        value = label
    elif issue_type == "classification_missing":
        label = opt.get("codigo", "")
        value = label
    elif issue_type == "asset_unidentified":
        label = opt.get("nome_ativo", "")
        value = label
    else:
        raw_val = opt.get("valor", "")
        label = str(raw_val) if raw_val != "" else ""
        value = raw_val

    if not label:
        return None

    return Suggestion(
        label=label,
        value=value,
        justification=justification,
        confidence=confidence,
        normative_ref=normative_ref,
        source="llm",
    )


def _extract_json_object(raw: str) -> dict | None:
    """Tenta extrair e parsear o primeiro objeto JSON da string.

    Tenta três estratégias: parse direto, regex entre { e }, linha a linha.
    """
    stripped = raw.strip()
    if not stripped:
        return None

    # 1. Parse direto
    try:
        result = json.loads(stripped)
        if isinstance(result, dict):
            return result
    except json.JSONDecodeError:
        pass

    # 2. Regex: primeiro objeto JSON entre { e }
    match = re.search(r'\{.*\}', stripped, re.DOTALL)
    if match:
        try:
            result = json.loads(match.group())
            if isinstance(result, dict):
                return result
        except json.JSONDecodeError:
            pass

    return None


def parse_llm_response(response: str, issue_type: str) -> list[Suggestion]:
    """Parseia a resposta JSON do LLM e retorna lista de Suggestions.

    Tenta json.loads direto, extração via regex e, como último recurso,
    parse linha a linha. Sempre retorna lista (pode ser vazia).
    Define source="llm" em todas as sugestões geradas.
    """
    parsed = _extract_json_object(response)

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
                except json.JSONDecodeError:
                    pass
        return suggestions

    options = parsed.get("opcoes", [])
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
