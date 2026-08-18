# Auditoria bSDD × IDS — mecanismo, censo e estrutura do projeto (2026-08-18)

Estudo motivado pela pergunta "por que o bSDD não devolve valores permitidos?"
(discussão da condição de ablação). Três frentes: (1) como o bSDD carrega
vocabulário e se o consumimos corretamente; (2) censo ao vivo do catálogo —
existe dicionário brasileiro?; (3) a estrutura do projeto está na melhor forma?
Relatório completo e navegável no artifact "Auditoria bSDD"; este doc registra
os fatos duros e as referências. Scripts do censo no scratchpad da sessão
(`censo_bsdd.py`, `testes_decisivos.py`, `acca_retry.py`), API pública
`api.bsdd.buildingsmart.org`, consultas de 2026-08-18.

## 1. O mecanismo existe e nós o consumimos corretamente

- **`allowedValues` funciona no próprio dicionário IFC 4.3** — para
  propriedades tipadas por PEnum no schema: `Status` retorna a enumeração
  completa (`DEMOLISH, EXISTING, NEW, NOTKNOWN, OTHER, TEMPORARY, UNSET`) via
  `GET /api/Property/v4`. A ausência em `FireRating`/`AcousticRating`
  (IfcLabel) e `ThermalTransmittance` (measure) é **conteúdo tipado pelo
  schema**, não falha da API nem da nossa integração — a nota da própria API
  diz "Such objects are not included in bSDD for simplicity reason".
- **O endpoint de propriedades-da-classe nunca traz valores**:
  `GET /api/Class/Properties/v1` de IfcWall → 233 propriedades, 0 com campo de
  valores (o campo nem aparece nas chaves do payload).
- **Nosso cliente faz o caminho certo em duas etapas**: lista sem valores
  (`src/bsdd/client.py:165-186`) e enriquece por `Property/v4` **apenas as
  propriedades filtradas** (`src/bsdd/context_builder.py:287-306`) — o
  comentário registra o porquê (233 chamadas HTTP para descartar quase todas).
  Também conformes: consulta por classe nua com censo que a justificou
  (`context_builder.py:211-227`), guarda de correspondência primária
  (`:249-268`), filtro de boilerplate (`src/models.py:323-335`), URIs
  canônicas (`semantic_registry`), `source_status` honesto (live/offline/empty
  e `property_absent_from_dictionary`, `context_builder.py:175-192`).

## 2. Censo do bSDD (ao vivo, 2026-08-18)

**426 dicionários** (311 Preview, 67 Active, 48 Inactive). O dicionário IFC
4.3 está ele próprio em **Preview**, sem atualização desde 2024-01-12.

**Existem 11 dicionários pt-BR** — a afirmação "não existe dicionário para o
Brasil" é falsa no nível do catálogo:

| org | dicionário | status | conteúdo |
|---|---|---|---|
| labimpr (Lab BIM Paraná) | Testes LaBIM PR - Edificações 0.2.3 | **Active** | 21 classes EOI (Fundações→Viga…) + 11 props orçamentárias (FCK, Aço CA-50) |
| labimpr | Caderno BIM PR - INFRA (2.0/3.0/0.1) | Preview | 69 classes de infraestrutura |
| CD0BIM (Carlos Dias) | CIBW78_2024 - **NBR 15965** | Preview | **6.719 classes** — port acadêmico da taxonomia (materiais, processos…) |
| CD0BIM | CISCEA / Workshop | Inactive | — |
| Labeee (UFSC) | Natural_Ventilation_AirflowNetwork | Preview | 25 classes + 46 props EnergyPlus |

**O que NÃO existe**: nenhuma organização ABNT; nenhum dicionário normativo
nacional; nenhum com valores de desempenho (fogo/térmica/acústica NBR
14432/15220/15575). O port da NBR 15965 é taxonomia de classificação
(análoga à OmniClass) — serviria a `system_unclassified`/`Category`, não a
valores de propriedade.

**Precedentes internacionais do que falta ao Brasil**: ACCA (it/fr) publica
"Classificazione Antincendio" com propriedades que **têm** `allowedValues`
(Reazione al fuoco: 0–5; resistência com R/E/I e minutos) — resistência ao
fogo modelada em bSDD, por um ator privado, em Preview; buildingsmart-de tem
"Fire Safety Requirements" (psets FSR); Iuav publica "UValue-CAM"; dataholz
(AT) publica 2.439 componentes de madeira com códigos de sistema; nacionais
maduros: Uniclass 2015 (14.328 classes), CCI, NL-SfB, ETIM (5.799, Active).

## 3. O canal IDS de vocabulário está desligado de ponta a ponta

O lugar padrão openBIM para vocabulário fechado por projeto/norma é o IDS
(`requirements/property/value` com `xs:enumeration`). No projeto, quatro
travas independentes o mantêm vazio:

1. **Vínculo issue→IDS por proveniência, não por conteúdo**
   (`src/pipeline.py:818-824`: exige `issue.context["rule_id"]`). Como o
   diagnóstico programático acha as mesmas lacunas primeiro e a deduplicação
   zera as issues vindas do IDS (`issues_from_ids: 0` com `ids_rules: 5`),
   nenhuma issue do benchmark recebe `IDSContext` — `grounding_sources` é
   `['bsdd']` em 100% dos 4.983 itens, embora as 5 especificações espelhem
   quase 1:1 os diagnósticos (FireRating/U em parede externa, LoadBearing em
   laje, LongName em espaço, IfcRelFillsElement em porta).
2. **O parser lê apenas a primeira `xs:enumeration`**
   (`src/translator/ids_parser.py:37-39` e `:70-78` — `children[0]` →
   `equals:<primeiro>`). Um IDS com vocabulário multi-valor seria achatado
   para igualdade com o primeiro item, silenciosamente.
3. **Os IDS autorados não carregam vocabulário de valor**: 184
   `xs:enumeration` nos 6 perfis de `data/ids_templates/` — 100% identidade
   (entidade/pset/propriedade) ou valor único (`TRUE`); zero enumerações
   múltiplas em `requirements/value` (verificado por regex multiline).
4. Consequência medida: o vocabulário normativo migrou para os templates de
   prompt — heterogeneamente (fogo = gramática sem lista; Category = menu
   fechado; sistemas/acústica = tipologia) — conforme mapeado na condição de
   ablação (`docs/condicao-ablacao-bsdd-2026-08-18.md` §2/§8).

## 4. Estrutura: conforme, com três ressalvas de desenho

Conformidades já listadas em §1. Ressalvas:

- **Mono-dicionário por default** (`client.py:20-22`), com a emenda já
  declarada em comentário: outro dicionário entraria por `dictionary_uri`
  próprio, não por texto (`context_builder.py:220-221`); `issue.context`
  aceita `bsdd_domain` (`context_builder.py:243-247`). A costura existe; o
  conteúdo é que nunca justificou usá-la.
- **Política de fontes trata todo `identifier.buildingsmart.org/` como
  oficial** (`src/semantic_registry/registry.py:8-15`): pronto para um
  dicionário BR sem mudança de código — e, simetricamente, sem distinção de
  governança entre buildingSMART e qualquer org (labimpr, CD0BIM, demo2025
  virariam "official"). Ao ir multi-dicionário, acrescentar allowlist por
  `dictionary_uri`.
- **`_select_primary_match` casa apenas nomes de classe IFC**
  (`context_builder.py:249-268`) — correto hoje; um dicionário de
  classificação (NBR 15965) exigiria estratégia própria de correspondência.

## 5. Organização-alvo (não bloqueia o artigo atual)

Três camadas com portador certo: **evidência** (arquivo IFC → templates,
como hoje), **requisitos + vocabulário fechado** (IDS com `xs:enumeration`
multi-valor por tipologia/norma), **âncora terminológica** (bSDD; opcional:
publicar dicionário "NBR-desempenho" — precedentes ACCA e CD0BIM mostram que
um ator não-oficial publica em Preview). Migração: (S) crosswalk por conteúdo
issue↔spec (~1 dia); (M) parser `one_of` + `allowed_values` no
`IDSContext`→prompt (~2-3 dias — **mudança de estímulo**: exigiria condição
pré-registrada própria, natureza "vocabulário genérico", nunca antes da
rodada de ablação atual); (L) dicionário próprio no bSDD (semanas +
governança; ganho: `has_official_candidates=True` nativo + contribuição
citável). As condições de ablação registradas em 18/08 não mudam — esta
auditoria reforça o racional da §2 delas.

## 6. Correções ao que foi dito na discussão

- "Não existe dicionário para o Brasil" → existem 11 pt-BR; não existe
  **normativo/ABNT** nem valores de desempenho (a frase da condição de
  ablação §2, sobre NBR 14432, permanece verdadeira).
- "O bSDD não fornece vocabulário fechado" → o **mecanismo** existe e
  funciona (Status, ACCA); o dicionário IFC o usa só onde o schema define
  PEnum. A ausência nas propriedades do experimento é limitação de conteúdo
  do dicionário consultado, não do bSDD como plataforma nem da nossa
  integração.
