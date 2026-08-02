# Revisão do Ground Truth candidato — prédio (norm-derived-draft)

Gerado por `scripts/build_predio_gt.py` **sem participação de LLM**
(propagação por tipo + NBR 15220-2 + NBR 14432 + mapeamentos fechados).

**Como revisar:** cada linha abaixo agrupa itens idênticos (mesmo tipo,
mesmo valor, mesma justificativa). Aprovar uma linha = aprovar todos os
seus itens no `ground_truth.yaml` (trocar `verified: false` → `true`).
Linhas marcadas com CONFERIR pedem atenção especial.

**Itens propostos:** 2546 | **Skips:** 246

## Itens propostos (agrupados)

| Tarefa | Propriedade | Tipo/origem | Valor proposto | Qtde | Justificativa |
|---|---|---|---|---|---|
| pset_missing | FireRating | Pilar retangular - concreto:0,20 x 0,40 | `R 60` | 352 | Pilar de concreto armado, elemento estrutural (critério R): NBR 14432:2001 Tab. A.1 (A-2, P3: 12<h≤23 m) → TRRF 60 min. Dimensionamento em incêndio pela NBR 15200. |
| pset_missing | FireRating | Parede básica:parede interna 20cm_growarq | `REI 60` | 262 | Alvenaria 16 cm + revestimentos, compartimentação: NBR 14432:2001 Tab. A.1 (A-2, P3: 12<h≤23 m) → TRRF 60 min. Desempenho provável do sistema ≥ 90 min (IT-08 CBPMESP Tab. paredes). |
| system_unclassified | — | Parede básica:parede interna 20cm_growarq | `Alvenaria de vedação em bloco cerâmico` | 262 | Camada '.alvenaria deitado 18 cm' + massa corrida; material genérico no modelo — CONFERIR se bloco cerâmico ou de concreto. |
| pset_missing | ThermalTransmittance | Parede básica:CRO5 - Dry-Wall 10cm | `2.35` | 222 | NBR 15220-2: Rsi 0,13 + gesso 0,015/0,35 + câmara não ventilada 0,17 + gesso 0,015/0,35 + Rse 0,04 = 0,426 m²K/W → U=2,35 W/(m²·K). |
| system_unclassified | — | Parede básica:CRO5 - Dry-Wall 10cm | `Drywall / Steel frame` | 222 | Gesso acartonado 15 mm + montantes metálicos 70 mm (camadas do modelo). |
| pset_missing | FireRating | Parede básica:CRO5 - Dry-Wall 10cm | `EI 30` | 222 | Drywall chapa simples ST 15 mm cada face ≈ EI 30 (catálogos Gypsum/Knauf; IT-08). Não portante (LoadBearing=false no modelo). ATENÇÃO: tipo marcado IsExternal=true no modelo — conferir. |
| pset_missing | FireRating | Parede básica:Parede externa 20cm | `REI 60` | 167 | Alvenaria de bloco de concreto 15 cm + revestimentos: NBR 14432:2001 Tab. A.1 (A-2, P3: 12<h≤23 m) → TRRF 60 min. |
| system_unclassified | — | Parede básica:Parede externa 20cm | `Alvenaria em bloco de concreto` | 167 | Camada 'Unidades de alvenaria de concreto' 15 cm no modelo. |
| pset_missing | ThermalTransmittance | Piso:laje de concreto + piso genérico 15cm_growarq | `3.2` | 107 | NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 = 0,312 → U=3,20 W/(m²·K). |
| system_unclassified | — | Piso:laje de concreto + piso genérico 15cm_growarq | `Laje maciça de concreto armado` | 107 | Camada '.concreto genérico' ≥ 10 cm moldado in loco. |
| pset_missing | ThermalTransmittance | DOM - Janela Correr 2 Folhas:1.5 x 1.0 | `5.7` | 55 | Esquadria com vidro simples: U≈5,7 W/(m²·K) (valor de referência NBR 15575-4 / catálogos de esquadrias) — CONFERIR tipo de vidro. |
| pset_missing | ThermalTransmittance | Piso:laje de concreto usinado + piso genérico 15cm_growarq | `3.2` | 53 | NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 = 0,312 → U=3,20 W/(m²·K). |
| system_unclassified | — | Piso:laje de concreto usinado + piso genérico 15cm_growarq | `Laje maciça de concreto armado` | 53 | Camada '.concreto usinado' 10 cm. |
| pset_missing | ThermalTransmittance | CRO5 - Janela Máx-ar:0.4 x 0.6 Vidro Mini boreal | `5.7` | 38 | Esquadria com vidro simples: U≈5,7 W/(m²·K) (valor de referência NBR 15575-4 / catálogos de esquadrias) — CONFERIR tipo de vidro. |
| pset_missing | ThermalTransmittance | Piso:laje de concreto + piso porcelanato 80x80cm 15cm_growarq | `3.2` | 31 | NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 = 0,312 → U=3,20 W/(m²·K). |
| system_unclassified | — | Piso:laje de concreto + piso porcelanato 80x80cm 15cm_growarq | `Laje maciça de concreto armado` | 31 | Camada '.concreto genérico' ≥ 10 cm moldado in loco. |
| pset_missing | LoadBearing | Patamar monolítico:espessura 200mm | `True` | 20 | Patamar monolítico de escada é estrutural. |
| system_unclassified | — | Patamar monolítico:espessura 200mm | `Laje maciça de concreto armado` | 20 | Patamar monolítico de escada em concreto. |
| pset_missing | ThermalTransmittance | Blocks_Janela Guilhotina Simples_F03337PT:Branco | `5.7` | 17 | Esquadria com vidro simples: U≈5,7 W/(m²·K) (valor de referência NBR 15575-4 / catálogos de esquadrias) — CONFERIR tipo de vidro. |
| pset_missing | FireRating | Escada moldada no local:escada monolítica piso pedra_growarq | `REI 60` | 10 | Escada monolítica de concreto — estrutural e rota de fuga: NBR 14432:2001 Tab. A.1 (A-2, P3: 12<h≤23 m) → TRRF 60 min. CONFERIR exigência específica de escada no projeto de incêndio (IT-11). |
| pset_missing | LoadBearing | Telhado básico:NormaDOM - Telhado Fibrocimento Ondulado | `False` | 9 | Telha de fibrocimento apoiada — não portante. |
| pset_missing | FireRating | CRO5 - Porta Corta Fogo:0.90 x 2.1 | `EI 30` | 7 | Porta corta-fogo de escada (NBR 11742): P-CF 30 usual para escada protegida em residencial P3; conferir projeto de incêndio. |
| pset_missing | ThermalTransmittance | Telhado básico:NormaDOM - Telhado Fibrocimento Ondulado | `4.6` | 5 | Telha de fibrocimento sem forro: U≈4,6 W/(m²·K) (NBR 15575-5 / LabEEE, valor consagrado para cobertura leve sem forro). |
| pset_missing | ThermalTransmittance | Parede cortina:divisória de vidro 100x212cm_growarq | `5.7` | 5 | Divisória de vidro simples: U≈5,7 W/(m²·K) — CONFERIR composição. |
| pset_missing | ThermalTransmittance | Piso:laje de concreto + piso genérico 20cm_growarq | `2.93` | 4 | NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,15/1,75 + Rse 0,04 = 0,341 → U=2,93 W/(m²·K). |
| system_unclassified | — | Piso:laje de concreto + piso genérico 20cm_growarq | `Laje maciça de concreto armado` | 4 | Camada '.concreto genérico' ≥ 10 cm moldado in loco. |
| pset_missing | ThermalTransmittance | Piso:laje de concreto usinado 10cm_growarq | `3.2` | 2 | NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 = 0,312 → U=3,20 W/(m²·K). |
| pset_missing | ThermalTransmittance | Piso:laje de concreto 10cm_growarq | `3.2` | 2 | NBR 15220-2, fluxo descendente: Rsi 0,17 + piso 0,02/1,05 + regularização 0,03/1,15 + concreto 0,10/1,75 + Rse 0,04 = 0,312 → U=3,20 W/(m²·K). |
| pset_missing | ThermalTransmittance | Vidraça inclinada:cobertura de vidro 80 cm 2_growarq | `5.7` | 2 | Vidraça com vidro simples: U≈5,7 W/(m²·K) — CONFERIR composição. |
| pset_missing | ThermalTransmittance | Parede cortina:Vitrine | `5.7` | 2 | Fachada/divisória envidraçada com vidro simples: U≈5,7 W/(m²·K) — CONFERIR composição. |
| system_unclassified | — | Piso:laje de concreto usinado 10cm_growarq | `Laje maciça de concreto armado` | 2 | Camada '.concreto usinado' 10 cm. |
| system_unclassified | — | Piso:grama 2cm_growarq | `Grama natural ou artificial` | 2 | Rótulo canônico do template de lajes do projeto. |
| system_unclassified | — | Piso:laje de concreto 10cm_growarq | `Laje maciça de concreto armado` | 2 | Camada '.concreto genérico' ≥ 10 cm moldado in loco. |
| pset_missing | ThermalTransmittance | Blocks_Janela de Canto_F03349PT:Branco | `5.7` | 1 | Esquadria com vidro simples: U≈5,7 W/(m²·K) (valor de referência NBR 15575-4 / catálogos de esquadrias) — CONFERIR tipo de vidro. |
| pset_missing | ThermalTransmittance | DOM - Janela Correr 2 Folhas1:1.5 x 1.0 | `5.7` | 1 | Esquadria com vidro simples: U≈5,7 W/(m²·K) (valor de referência NBR 15575-4 / catálogos de esquadrias) — CONFERIR tipo de vidro. |
| pset_missing | ThermalTransmittance | CRO5 - Janela Máx-ar:0.8 x 0.8 Vidro Mini boreal | `5.7` | 1 | Esquadria com vidro simples: U≈5,7 W/(m²·K) (valor de referência NBR 15575-4 / catálogos de esquadrias) — CONFERIR tipo de vidro. |
| pset_missing | Category | Hall de Circulação 40 | `CIRCULATION` | 1 | LongName 'Hall de Circulação': Circulação. |
| pset_missing | Category | Guarita 41 | `OFFICE` | 1 | LongName 'Guarita': Posto de trabalho da portaria — CONFERIR. |
| pset_missing | Category | Banheiro Guarita 42 | `BATHROOM` | 1 | LongName 'Banheiro Guarita': Banheiro. |
| pset_missing | Category | Medidores de Luz 43 | `TECHNICAL_AREA` | 1 | LongName 'Medidores de Luz': Área técnica. |
| pset_missing | Category | Casa de Hidrômeros 44 | `TECHNICAL_AREA` | 1 | LongName 'Casa de Hidrômeros': Área técnica (hidrômetros). |
| pset_missing | Category | Depósito de Lixo 45 | `STORAGE` | 1 | LongName 'Depósito de Lixo': Depósito condominial. |
| pset_missing | Category | Depósito de Gás 46 | `TECHNICAL_AREA` | 1 | LongName 'Depósito de Gás': Central de GLP — área técnica. |
| pset_missing | Category | Hall de Entrada 50 | `LOBBY` | 1 | LongName 'Hall de Entrada': Acesso principal. |
| pset_missing | Category | Salão de Festas 51 | `MEETING_ROOM` | 1 | LongName 'Salão de Festas': Uso coletivo — CONFERIR. |
| pset_missing | Category | Cozinha Salão de Festas 52 | `KITCHEN` | 1 | LongName 'Cozinha Salão de Festas': Cozinha (inclui cozinha do salão de festas). |
| pset_missing | Category | Despensa 53 | `STORAGE` | 1 | LongName 'Despensa': Armazenamento. |
| pset_missing | Category | Lavatório SF 55 | `WC` | 1 | LongName 'Lavatório SF': Lavabo/lavatório. |
| pset_missing | Category | Banheiro SF 56 | `BATHROOM` | 1 | LongName 'Banheiro SF': Banheiro. |
| pset_missing | Category | Escadas de Incêndio 57 | `CIRCULATION` | 1 | LongName 'Escadas de Incêndio': Circulação vertical de emergência. |
| pset_missing | Category | Depósito Geral 58 | `STORAGE` | 1 | LongName 'Depósito Geral': Armazenamento. |
| pset_missing | Category | Lavatório Geral 59 | `WC` | 1 | LongName 'Lavatório Geral': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Geral 60 | `BATHROOM` | 1 | LongName 'Banheiro Geral': Banheiro. |
| pset_missing | Category | Cisternas e Casa de Maquinas 63 | `TECHNICAL_AREA` | 1 | LongName 'Cisternas e Casa de Maquinas': Área técnica. |
| pset_missing | Category | Sacada 64 | `BALCONY` | 1 | LongName 'Sacada': Sacada. |
| pset_missing | Category | Quarto 1 65 | `BEDROOM` | 1 | LongName 'Quarto 1': Dormitório. |
| pset_missing | Category | Quarto 2 66 | `BEDROOM` | 1 | LongName 'Quarto 2': Dormitório. |
| pset_missing | Category | Suíte 67 | `BEDROOM` | 1 | LongName 'Suíte': Dormitório (suíte). |
| pset_missing | Category | Corredor 68 | `CIRCULATION` | 1 | LongName 'Corredor': Circulação. |
| pset_missing | Category | Sala de Estar 69 | `LIVING_ROOM` | 1 | LongName 'Sala de Estar': Estar. |
| pset_missing | Category | Sala de Jantar 70 | `LIVING_ROOM` | 1 | LongName 'Sala de Jantar': Jantar integrado; vocabulário sem DINING. |
| pset_missing | Category | Cozinha 71 | `KITCHEN` | 1 | LongName 'Cozinha': Cozinha (inclui cozinha do salão de festas). |
| pset_missing | Category | Área de Serviço 72 | `SERVICE_AREA` | 1 | LongName 'Área de Serviço': Serviço. |
| pset_missing | Category | Lavatório Social 73 | `WC` | 1 | LongName 'Lavatório Social': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Social 74 | `BATHROOM` | 1 | LongName 'Banheiro Social': Banheiro. |
| pset_missing | Category | Lavatório Suíte 75 | `WC` | 1 | LongName 'Lavatório Suíte': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Suíte 76 | `BATHROOM` | 1 | LongName 'Banheiro Suíte': Banheiro. |
| pset_missing | Category | Banheiro Área de Serviço 77 | `BATHROOM` | 1 | LongName 'Banheiro Área de Serviço': Banheiro. |
| pset_missing | Category | Hall de Circulação 93 | `CIRCULATION` | 1 | LongName 'Hall de Circulação': Circulação. |
| pset_missing | Category | Sacada 94 | `BALCONY` | 1 | LongName 'Sacada': Sacada. |
| pset_missing | Category | Quarto 1 95 | `BEDROOM` | 1 | LongName 'Quarto 1': Dormitório. |
| pset_missing | Category | Quarto 2 96 | `BEDROOM` | 1 | LongName 'Quarto 2': Dormitório. |
| pset_missing | Category | Suíte 97 | `BEDROOM` | 1 | LongName 'Suíte': Dormitório (suíte). |
| pset_missing | Category | Corredor 98 | `CIRCULATION` | 1 | LongName 'Corredor': Circulação. |
| pset_missing | Category | Sala de Estar 99 | `LIVING_ROOM` | 1 | LongName 'Sala de Estar': Estar. |
| pset_missing | Category | Sala de Jantar 100 | `LIVING_ROOM` | 1 | LongName 'Sala de Jantar': Jantar integrado; vocabulário sem DINING. |
| pset_missing | Category | Cozinha 101 | `KITCHEN` | 1 | LongName 'Cozinha': Cozinha (inclui cozinha do salão de festas). |
| pset_missing | Category | Área de Serviço 103 | `SERVICE_AREA` | 1 | LongName 'Área de Serviço': Serviço. |
| pset_missing | Category | Lavatório Social 104 | `WC` | 1 | LongName 'Lavatório Social': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Social 105 | `BATHROOM` | 1 | LongName 'Banheiro Social': Banheiro. |
| pset_missing | Category | Lavatório Suíte 106 | `WC` | 1 | LongName 'Lavatório Suíte': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Suíte 107 | `BATHROOM` | 1 | LongName 'Banheiro Suíte': Banheiro. |
| pset_missing | Category | Banheiro Área de Serviço 108 | `BATHROOM` | 1 | LongName 'Banheiro Área de Serviço': Banheiro. |
| pset_missing | Category | Hall de Circulação 109 | `CIRCULATION` | 1 | LongName 'Hall de Circulação': Circulação. |
| pset_missing | Category | Sacada 110 | `BALCONY` | 1 | LongName 'Sacada': Sacada. |
| pset_missing | Category | Quarto 1 111 | `BEDROOM` | 1 | LongName 'Quarto 1': Dormitório. |
| pset_missing | Category | Quarto 2 112 | `BEDROOM` | 1 | LongName 'Quarto 2': Dormitório. |
| pset_missing | Category | Suíte 113 | `BEDROOM` | 1 | LongName 'Suíte': Dormitório (suíte). |
| pset_missing | Category | Corredor 114 | `CIRCULATION` | 1 | LongName 'Corredor': Circulação. |
| pset_missing | Category | Sala de Estar 115 | `LIVING_ROOM` | 1 | LongName 'Sala de Estar': Estar. |
| pset_missing | Category | Sala de Jantar 116 | `LIVING_ROOM` | 1 | LongName 'Sala de Jantar': Jantar integrado; vocabulário sem DINING. |
| pset_missing | Category | Cozinha 117 | `KITCHEN` | 1 | LongName 'Cozinha': Cozinha (inclui cozinha do salão de festas). |
| pset_missing | Category | Área de Serviço 118 | `SERVICE_AREA` | 1 | LongName 'Área de Serviço': Serviço. |
| pset_missing | Category | Lavatório Social 119 | `WC` | 1 | LongName 'Lavatório Social': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Social 120 | `BATHROOM` | 1 | LongName 'Banheiro Social': Banheiro. |
| pset_missing | Category | Lavatório Suíte 121 | `WC` | 1 | LongName 'Lavatório Suíte': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Suíte 122 | `BATHROOM` | 1 | LongName 'Banheiro Suíte': Banheiro. |
| pset_missing | Category | Banheiro Área de Serviço 123 | `BATHROOM` | 1 | LongName 'Banheiro Área de Serviço': Banheiro. |
| pset_missing | Category | Hall de Circulação 124 | `CIRCULATION` | 1 | LongName 'Hall de Circulação': Circulação. |
| pset_missing | Category | Sacada 125 | `BALCONY` | 1 | LongName 'Sacada': Sacada. |
| pset_missing | Category | Quarto 1 126 | `BEDROOM` | 1 | LongName 'Quarto 1': Dormitório. |
| pset_missing | Category | Quarto 2 127 | `BEDROOM` | 1 | LongName 'Quarto 2': Dormitório. |
| pset_missing | Category | Suíte 128 | `BEDROOM` | 1 | LongName 'Suíte': Dormitório (suíte). |
| pset_missing | Category | Corredor 129 | `CIRCULATION` | 1 | LongName 'Corredor': Circulação. |
| pset_missing | Category | Sala de Estar 130 | `LIVING_ROOM` | 1 | LongName 'Sala de Estar': Estar. |
| pset_missing | Category | Sala de Jantar 131 | `LIVING_ROOM` | 1 | LongName 'Sala de Jantar': Jantar integrado; vocabulário sem DINING. |
| pset_missing | Category | Cozinha 132 | `KITCHEN` | 1 | LongName 'Cozinha': Cozinha (inclui cozinha do salão de festas). |
| pset_missing | Category | Área de Serviço 133 | `SERVICE_AREA` | 1 | LongName 'Área de Serviço': Serviço. |
| pset_missing | Category | Lavatório Social 134 | `WC` | 1 | LongName 'Lavatório Social': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Social 135 | `BATHROOM` | 1 | LongName 'Banheiro Social': Banheiro. |
| pset_missing | Category | Lavatório Suíte 136 | `WC` | 1 | LongName 'Lavatório Suíte': Lavabo/lavatório. |
| pset_missing | Category | Banheiro Suíte 137 | `BATHROOM` | 1 | LongName 'Banheiro Suíte': Banheiro. |
| pset_missing | Category | Banheiro Área de Serviço 138 | `BATHROOM` | 1 | LongName 'Banheiro Área de Serviço': Banheiro. |

## Issues sem GT (abstenção documentada)

| Tarefa | Propriedade | Tipo/origem | Qtde | Motivo |
|---|---|---|---|---|
| pset_missing | FireRating | porta multiplas_growarq:porta giro simples 70 cm_growarq | 73 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | Blocks_Porta Sanfonada Permatti_F05601PT:PVC Preto - 0.60 x 2.10 | 54 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | PORTA DE VIDRO COM ESQUADRIA DE CORRER - 4 FOLHAS:280 x 220 | 20 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | porta multiplas_growarq:porta de correr 70 cm_growarq | 19 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | ThermalTransmittance | CRO5 - Basculante 1F:1.0 x 0.5 | 17 | sem valor no modelo e sem memória de cálculo para o tipo; decisão do revisor |
| pset_missing | FireRating | porta multiplas_growarq:porta giro simples 80 cm_growarq | 16 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| system_unclassified | — | Telhado básico:NormaDOM - Telhado Fibrocimento Ondulado | 9 | cobertura de fibrocimento — rótulo fora do vocabulário canônico; decisão do revisor |
| pset_missing | FireRating | CRO5 - Porta de Abrir 02 Folhas1:1.20 x 2.10 - Divisória Branca | 4 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | ThermalTransmittance | Piso:asfalto 20cm_growarq | 3 | pavimentação externa; transmitância térmica não aplicável ao escopo NBR 15575 |
| system_unclassified | — | Piso:asfalto 20cm_growarq | 3 | pavimentação asfáltica — rótulo fora do vocabulário canônico; decisão do revisor |
| pset_missing | ThermalTransmittance | Piso:grama 2cm_growarq | 2 | revestimento paisagístico; transmitância térmica não aplicável |
| pset_missing | FireRating | CRO5 - Porta de Abrir 02 Folhas2:1.20 x 2.10 - Divisória Branca 2 | 2 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | CRO5 - Porta de Correr 02 Folhas.0001:1.5 x 2.1 | 2 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | ThermalTransmittance | Vidraça inclinada:NormaDOM - Terças | 2 | elemento estrutural de cobertura; transmitância térmica não aplicável |
| pset_missing | ThermalTransmittance | Piso:NormaDOM - Terreno - 10cm - Piso Intertravado | 1 | pavimentação externa; transmitância térmica não aplicável |
| pset_missing | ThermalTransmittance | Piso:NormaDOM - Terreno - 10cm - Calçada | 1 | pavimentação externa; transmitância térmica não aplicável |
| pset_missing | ThermalTransmittance | Piso:calçada 20cm_growarq | 1 | pavimentação externa; transmitância térmica não aplicável |
| pset_missing | FireRating | Blocks_Portão de Abrir Contemporâneo_F04376PT:Metal Preto - 4.00 x 2.35 | 1 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | Blocks_Portão de Abrir Contemporâneo com Bandeira_F05919PT:Aço Branco - 1.20 x 2.10 | 1 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | Blocks_Porta de Correr Skye_F05594PT:Preto - 2.00 x 2.10 | 1 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | Blocks_Porta de Correr Skye_F05594PT:Preto - 4.00 x 2.10 | 1 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | Blocks_Porta de Correr Aladin Poket Duo_F02317PT:1,20 x 2,10 | 1 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | FireRating | Blocks_Porta Sanfonada Permatti_F05601PT:PVC Preto - 0.70 x 2.10 | 1 | porta/janela comum sem exigência de resistência ao fogo (NBR 14432); GT omitido |
| pset_missing | ThermalTransmittance | Vidraça inclinada:NormaDOM - Caibros | 1 | elemento estrutural de cobertura; transmitância térmica não aplicável |
| pset_missing | ThermalTransmittance | Vidraça inclinada:Estrutura - Caibros | 1 | elemento estrutural de cobertura; transmitância térmica não aplicável |
| pset_missing | Category | Área de Recreação Infantil 47 | 1 | LongName 'Área de Recreação Infantil' sem mapeamento inequívoco no vocabulário fechado; decisão do revisor |
| pset_missing | Category | Área de Churrasco 48 | 1 | LongName 'Área de Churrasco' sem mapeamento inequívoco no vocabulário fechado; decisão do revisor |
| pset_missing | Category | Quadra de Basquete 49 | 1 | LongName 'Quadra de Basquete' sem mapeamento inequívoco no vocabulário fechado; decisão do revisor |
| pset_missing | Category | Lava Pés 61 | 1 | LongName 'Lava Pés' sem mapeamento inequívoco no vocabulário fechado; decisão do revisor |
| pset_missing | Category | Pátio 139 | 1 | LongName 'Pátio' sem mapeamento inequívoco no vocabulário fechado; decisão do revisor |
| system_unclassified | — | Piso:NormaDOM - Terreno - 10cm - Piso Intertravado | 1 | piso intertravado — rótulo fora do vocabulário canônico; decisão do revisor |
| system_unclassified | — | Piso:NormaDOM - Terreno - 10cm - Calçada | 1 | calçada de concreto — rótulo fora do vocabulário canônico; decisão do revisor |
| system_unclassified | — | Piso:calçada 20cm_growarq | 1 | calçada de concreto — rótulo fora do vocabulário canônico; decisão do revisor |
| relation_broken | — | 00 | 1 | issue_type/propriedade fora do protocolo norm-derived (relation_broken/) |

## Referências

- NBR 14432:2001 — Tab. A.1 (TRRF por ocupação/altura); prédio A-2, P3 → 60 min
- NBR 15220-2 — propriedades térmicas e método de cálculo de U
- NBR 15575-4/5:2021 — requisitos de desempenho (contexto dos limites)
- IT-08 (CBPMESP) — resistência ao fogo de elementos construtivos
- NBR 11742 — portas corta-fogo

## Emendas pós-aprovação

### Emenda 2026-08-02 — EI aceito em vedação não portante (⚠️ pendente ratificação do autor)

**Regra declarada do experimento:** em elementos de vedação cujo modelo declara
`Pset_WallCommon.LoadBearing = false`, a classe **EI** de duração ≥ à exigida é
aceita como alternativa ao **REI** da prática de compartimentação. O critério
estrito da NBR 14432 para elemento sem função estrutural é estanqueidade +
isolamento (EI); um modelo que responde EI está seguindo a evidência dada pelo
arquivo e não deve ser penalizado. REI 60 permanece como `expected_value`
(resposta preferida); EI 60/90/120 entram em `accepted_alternatives`,
espelhando o padrão já aprovado de aceitar classes superiores (REI 90/120).

**Escopo (429 itens de FireRating, 2 grupos):**

| Grupo | Itens | LoadBearing no IFC (amostra n=8) |
|---|---|---|
| Parede básica:parede interna 20cm_growarq | 262 | `False` |
| Parede básica:Parede externa 20cm | 167 | `False` |

Fora do escopo (inalterados): pilares (`R 60`, critério estrutural), escada
monolítica (`REI 60`, estrutural + rota de fuga), drywall (`EI 30`, já EI),
porta corta-fogo (`EI 30`).

**Origem:** análise do benchmark 2026-07-28
(`docs/analise-benchmark-2026-07-28.md`, §5 — "não é fraqueza de modelo"):
os 2 estímulos concentravam 429/1020 issues do estrato e eram errados por
todos os modelos que respondiam conforme a evidência.

**Impacto medido (re-score do run 2026-07-28, mesma coleta, sem GPU):**

| Modelo | Top-1 prédio (antes → depois) | Fogo por estímulo (de 6) |
|---|---|---|
| qwen3.5:4b | 0,6705 → **0,8390** | 4 → 6 |
| gemma2:9b | 0,7361 → **0,8016** | 3 → 4 |
| llama3.1:8b | 0,5460 → 0,7145 | 2 → 4 |
| qwen2.5:7b-instruct | 0,4745 → 0,6430 | 2 → 4 |
| qwen3.5:9b | 0,4183 → 0,5868 | 1 → 3 |
| falcon3:7b | 0,2989 → 0,4018 | 1 → 2 |
| demais (granite4, phi4-mini, lfm2.5, mistral) | sem mudança no top-1 | — |

O mistral:7b segue 0,1009: classes de uma letra (`E 60`) continuam não
cumprindo nem REI nem EI — a emenda não o beneficia, como esperado.

**Nota metodológica para o artigo:** reportar o efeito da emenda como mudança
de **critério de avaliação** (recalculável de runs gravados), separado do
efeito do instrumento v6 (que exige nova coleta). Hash do YAML emendado:
`D08D2C74…` (anterior, da aprovação integral: `3924D611…`).

**Ratificação:** ( ) aprovo a regra declarada — Felipe Keller, data ____.
