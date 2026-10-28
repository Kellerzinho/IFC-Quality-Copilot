# Estudo de formato de contexto — protocolo (rascunho para aprovação)

> **Estado:** protocolo e ferramentas em dry-run, 28/10/2026. **Nenhuma inferência foi executada.**
> O modo real do harness está bloqueado no código (`REAL_MODE_AUTHORIZED = False`) até autorização
> registrada (plano M7, tarefa M7-10). Este estudo é um ensaio de desenvolvimento ligado à M7-08
> (condições de contexto) e à M7-10 (triagem); não é a rodada congelada do benchmark e não troca
> modelo de rodada nenhuma (D7-16).

## 1. Pergunta

Para um elemento estrutural com propriedades nativas de nomes variados conforme o exportador, **qual
combinação modelo × quantização × formato de contexto** encontra a propriedade sinônima do conceito
pedido (fck, cobrimento nominal, CAA) e devolve **valor + unidade padronizada** (MPa, mm; CAA em I–IV)
— ou **se abstém** quando o conceito está ausente, a unidade não está declarada ou há valores
conflitantes?

Aritmética de conversão não é tarefa de LLM no produto (CLAUDE.md, "Aritmética não é tarefa de LLM").
Aqui a conversão é medida como **sintoma**: um modelo que acerta a origem e erra a unidade revela que o
produto precisa declarar termos e deixar a conta para o código.

## 2. Variáveis

| Fator | Níveis | Fonte |
|---|---|---|
| Modelo | Qwen3-4B, Qwen3.5-4B, Llama-3.2-3B-Instruct | prospecção M7-09 (`research/M7/prospection/`): cabem inteiros na RTX 4050 (6 GB) a 4k |
| Quantização | Q4_K_M, Q8_0 (tags publicadas); Q5_K_M só onde há tag publicada (Llama) | idem; Q3/Q5 sem tag ficam fora por procedência |
| Formato | JSON indentado, JSON compacto, Markdown (lista), tabela | `render_context` |
| Escopo | contexto inteiro (todas as propriedades, com distratores) × entrada recuperada (top-3 lexical pelo vocabulário genérico do conceito) | `retrieve` |
| Idioma da instrução | PT × EN (as propriedades ficam como o exportador escreveu) | `build_prompt` |

Fixos: instrução e JSON Schema de saída iguais em todas as células, temperatura 0, `num_ctx` 4096,
mesmo runtime (Ollama 0.40.3 medido na prospecção) e mesmo casamento de tags/digests, registrados no
manifesto.

**Gate de licença.** Llama-3.2-3B-Instruct está `condicionado`: a licença incorpora a Acceptable Use
Policy, que proíbe uso relacionado a atividades militares/ITAR. A decisão de incluir é do orientador
(Cel Giuseppe); sem ela, o braço Llama não roda e o estudo fica com as duas famílias Qwen (Apache 2.0).
O gate é registrado por modelo antes de qualquer download.

## 3. Casos e gabarito

Gerador determinístico (`generate_cases`, semente registrada; mesma semente → mesmos bytes). Para cada
conceito, tipos de caso balanceados:

| Tipo | fck | cobrimento | CAA | Gabarito |
|---|---|---|---|---|
| direto (unidade padrão) | ✓ | ✓ | ✓ | valor |
| conversão (Pa, kN/cm², kgf/cm²; cm, m) | ✓ | ✓ | — | valor convertido |
| unidade só no nome ("FCK (MPa)") | ✓ | ✓ | — | valor |
| classe (C25, C25/30 → 25 MPa) | ✓ | — | — | valor |
| ausente (só distratores; `fcd` como armadilha) | ✓ | ✓ | ✓ | abstenção `ausente` |
| sem unidade declarada | ✓ | ✓ | — | abstenção `unidade_desconhecida` |
| conflito (ocorrência × tipo com valores diferentes) | ✓ | ✓ | ✓ | abstenção `conflito` |

Valores de domínio: classes C20–C50 (NBR 8953), cobrimento nominal por CAA e tipo de peça (NBR 6118,
tabela 7.2), CAA escrita como "II", "CAA II", "2" ou "Moderada". Nomes por exportador (Revit BR, TQS,
Eberick, Tekla, genérico EN) são variações de grafia, não aliases aprovados do catálogo (M1 §2.2).
Os casos são fixtures de software (plano M7 §4), não casos reais; a confirmação em modelos reais fica
para o corpus da M7-03/M7-04.

**Vocabulário vindo de arquivo (desde 28/10, 2ª rodada).** Grafias por exportador, termos de busca,
unidades, fatores de conversão, classes de resistência, tabela de cobrimento por CAA e não-sinônimos
saem de `data/dicionario_provisorio/conceitos-estruturais.json` (§8), não de constantes no código. O
arquivo é **provisório, aguardando o dicionário da Juliana / M1**. A grafia "C-25" da fonte Daiane
(A7-015, A8-013, A9-014: `Pset_ConcreteElementGeneral.StrengthClass`) entrou entre as variantes de classe.

## 4. Métricas

Por célula (formato × escopo × idioma × modelo × quantização):

- **Acerto top-1** (casos com valor): origem `Pset.Nome` + valor (tolerância relativa 1 %) + unidade.
- **Abstenção correta** (casos de abstenção); motivo correto é informativo, não critério.
- **Proposta indevida**: valor quando o gabarito pede abstenção (o erro mais caro para o produto).
- **JSON válido** contra o JSON Schema 2020-12 de saída (validado com `jsonschema`, não por regex).
- **Erro de unidade**: origem correta com valor/unidade errados.
- **Latência** (ms por chamada, carga separada da inferência) e **VRAM** de pico (nvidia-smi) — só no
  modo real; no dry-run ficam nulas.
- Tokens de entrada: aproximados (caracteres ÷ 4) no dry-run; no modo real, `prompt_eval_count` do runtime.

## 5. Desenho

- Temperatura 0, seed fixa quando o runtime aceitar; **3 repetições** por célula para medir a
  estabilidade da resposta estruturada (a temperatura 0 não garante determinismo em GPU).
- Ordem das células em blocos por modelo × quantização (custo de carga), sequência registrada;
  dentro do bloco, ordem dos casos embaralhada com a semente.
- Uma inferência ativa por vez (fila serial M6); aquecimento descartado e registrado.
- Tamanho: 3 conceitos × tipos admissíveis (14 combinações) × 4 casos = 56 casos por célula;
  32 células de formato/escopo/idioma × até 6 configurações de modelo.
- Relatório: proporções com intervalo de Wilson por célula; comparação pareada entre formatos
  (mesmos casos) com McNemar; nenhum vencedor declarado só por diferença pontual (D7-10).

## 6. Ameaças à validade

- **Sintético × real:** nomes e unidades vêm de um gerador; acertar aqui não garante acerto em IFC
  real. Mitigação: repetir as células finalistas no corpus real da M7.
- **Recuperação lexical** usa o vocabulário do conceito; pode favorecer o escopo "recuperado" nos
  exportadores cujos nomes contêm os termos. O relatório mostra a cobertura da recuperação
  (quantos gabaritos ficaram entre os k recuperados) separada do acerto do modelo.
- **Contagem de tokens aproximada** no dry-run; comparações de custo só com a contagem do runtime.
- **Vazamento:** o prompt nunca contém gabarito, id ou tipo do caso (teste automatizado); o gerador
  não é exposto ao modelo.
- **Não determinismo** em GPU e diferenças de template de chat entre famílias; registrar digests e
  template efetivo.
- **Licença:** se o braço Llama for excluído pelo gate, a comparação entre famílias fica restrita a
  Qwen; não extrapolar.

## 7. Como rodar (dry-run)

```powershell
uv run python scripts/estudo_formato_contexto.py gerar --seed 20261028 --por-tipo 4
uv run python scripts/estudo_formato_contexto.py harness --dry-run
# saídas em research/M7/estudo-formato-contexto/ (ignorado pelo git)
uv run python scripts/estudo_formato_contexto.py harness --real   # recusado (código 2)
```

## 8. Dicionário provisório × formato do catálogo M1

Arquivo: `data/dicionario_provisorio/conceitos-estruturais.json`; carregador:
`src/experiment/budget_v1/provisional_dictionary.py`. Formato de referência: pacote
`ifcqc-catalog-package` v1 (`data/catalogs/schemas/catalog-v1.json`, `src/domain_catalog/models.py` e
`contracts.py` na branch `codex/m1-domain-catalog`, lidos sem alteração).

**Conferência.** As seções `source_artifacts`, `source_assertions`, `concepts`, `units`, `value_sets`,
`applicability_rules`, `bindings` e `aliases`, sem os campos `x_*`, validam **sem erro** contra as
`$defs` do `catalog-v1.json` (Draft 2020-12, 28/10/2026). As regras de negócio dos modelos pydantic do
catálogo não foram executadas (exigiriam importar a branch do Felipe); a regra de alias de resolução
(escopo + binding alvo) e a de escrita (`write_enabled` só com tudo aprovado) são replicadas em teste.

| Tema | Catálogo M1 | Dicionário provisório | Por quê |
|---|---|---|---|
| Empacotamento | Um arquivo por seção + `manifest.json` com `files` (bytes, sha256, entries) | Um único JSON; `manifest` sem `files` | Insumo de pesquisa, não release; sem publicação nem hash por arquivo |
| Estado | `lifecycle` por entrada; release publicado com proveniência | Tudo `draft`; `namespace_status: provisional`; `content_origin: synthetic_fixture`; `x_status` | Nada aqui é aprovado; marcação explícita de provisório |
| Nome padronizado (EB_Orçamento) | Não há campo; o portador é um `IFCBinding` (`set_name`, `field_name`) | Binding `EB_Orçamento.<Campo>` com `set_kind: custom` **e** qualificador `nome_padronizado` no conceito | Qualificador é campo existente do formato; facilita a leitura sem resolver bindings |
| Chave do estudo | — | Qualificador `chave_estudo` (`fck`, `cobrimento`, `caa`) | Liga o conceito às chaves do gerador sem depender do `code` |
| Tipo de relação | Só a `purpose` do alias (`search`, `representation_match`…) | `purpose` do alias **+** `x_relacao` no binding: `portador_padronizado`, `derivacao` (StrengthClass → fck), `relacionado_nao_equivalente` (CompressiveStrength, ExposureClass) | O formato não distingue "mesmo campo" de "deriva por regra" ou "parecido, mas outra grandeza" |
| Não-sinônimos | Não representável (alias nunca nega) | `x_extensoes_provisorias.nao_sinonimos` (fcd, fct,m → fck; ExposureClass → CAA), com fonte | M1 §2.2: fck e fcd não são sinônimos; o gerador usa como armadilha |
| Conversão de unidade | `UnitDefinition` só tem símbolo e dimensão | `conversoes_para_unidade_do_conceito` (Pa, kPa, kN/cm², kgf/cm² → MPa; cm, m → mm) | Precisamos do fator para gerar e conferir; no produto a conta é do código (`docs/pontos-de-calculo.md`) |
| Faixa plausível | Não existe (só `AllowedValueSet` para códigos) | `faixas_plausiveis` (fck 20–50 MPa; cobrimento 15–60 mm) | Guardas de plausibilidade; candidata a `Qualifier` ou política no M1 |
| Tabela normativa | Não existe | `cobrimento_nominal_por_caa_mm` (NBR 6118 t. 7.2), `classe_por_fck_cubo_eurocodigo` | Dado de domínio que o gerador usa; o M1 decide se vira conteúdo |
| Grafias da CAA | `AllowedValue.labels` | `labels` no value set **+** `grafias_da_caa` ("CAA II", "2", "Moderada") | Grafias de exportador não são rótulos oficiais |
| Exportador | Não há conceito de exportador; só `scope.set_names` do alias | `x_extensoes_provisorias.exportadores` (id → `set_name`) | O gerador precisa agrupar grafias por "software" |
| Fontes normativas | `SourceArtifact`/`SourceAssertion` com `locator` | Mesmo formato; NBR citadas por seção/tabela, `artifact_type: dictionary_snapshot`, sem `sha256` (norma não adquirida) | Seções a conferir pela curadoria; sem reprodução do texto da norma |
| Ids | `urn:uuid` (gerados) | `urn:uuid` uuid5 determinísticos | Reprodutível entre gerações do arquivo |

**Quando o dicionário da Juliana/M1 existir:** trocar o arquivo e o carregador por um leitor do release
(`CatalogReader`), mapear `x_relacao` para o que o M1 adotar e levar as extensões ao M1 como proposta
(conversões, faixas, não-sinônimos). O gerador já aceita outro `Vocabulary` (`generate_cases(vocab=...)`).

## 9. Modo real: o que rodar quando houver autorização

O harness está pronto e **travado**: `--real` sem `--confirmo-autorizacao "<registro>"` sai com código 2
e não abre conexão. O cliente (`src/experiment/budget_v1/context_format_runner.py`) usa `POST /api/chat`
do Ollama local com `format` = JSON Schema da saída (saída estruturada), `temperature 0`, `seed 20261028`,
`num_ctx 4096`, `think: false`, timeout de 120 s por chamada, uma chamada por vez. Cada chamada vira uma
linha em `research/M7/estudo-formato-contexto/resultados-real.jsonl`; rodar de novo **retoma** (linhas já
gravadas não são refeitas, linha truncada por interrupção é refeita). Latência: relógio da chamada e
tempos do Ollama (`total_duration`, `load_duration`, tokens). VRAM: pico por amostragem do `nvidia-smi`
a cada 0,25 s durante a chamada.

### Modelos (seleção automática da prospecção M7-09)

`uv run python scripts/estudo_formato_contexto.py modelos` lista a decisão e o motivo de cada um. Padrão:
licença Apache-2.0/MIT, tag publicada no Ollama e "GPU inteira" a 4k no perfil da RTX 4050 (cenário nominal).

| Tag | Licença | Memória estimada a 4k (M7-09) | Observação |
|---|---|---|---|
| `qwen3:4b-q4_K_M` | Apache-2.0 | 3,68 GiB | |
| `qwen3:4b-q8_0` | Apache-2.0 | 5,36 GiB | perto do limite de 6 GB |
| `qwen3.5:4b-q4_K_M` | Apache-2.0 | 3,95 GiB | |
| `qwen3.5:4b-q8_0` | Apache-2.0 | 5,72 GiB | no instantâneo medido ficaria com offload parcial: feche outros programas |

Fora: Llama-3.2-3B e Llama-3.1-8B (licença condicionada; entram só com
`--licenca-condicionada-autorizada "<decisão do orientador>"`, e o 8B não cabe em 6 GB); quantizações sem
tag publicada (procedência); 8B/9B em Q4/Q8 (não cabem).

### Antes de rodar (ações suas, fora deste harness)

1. Baixar os modelos (≈ 14,4 GB em disco no total, tamanhos do catálogo Ollama):
   `ollama pull qwen3:4b-q4_K_M`, `ollama pull qwen3:4b-q8_0`, `ollama pull qwen3.5:4b-q4_K_M`,
   `ollama pull qwen3.5:4b-q8_0`. Registrar os digests (`ollama list`).
2. Fechar navegador e IDE: a coleta da M7-09 mediu **0,84 GiB de RAM livre** de 7,71 GiB.
3. Gerar os casos: `uv run python scripts/estudo_formato_contexto.py gerar --seed 20261028 --por-tipo 4`.

### Comandos

Piloto curto (recomendado primeiro; 16 casos × 16 células × 1 repetição = 256 chamadas por modelo):

```powershell
cd C:\dev\IFC-Quality-Copilot
uv run python scripts/estudo_formato_contexto.py gerar --seed 20261028 --por-tipo 1 --out research/M7/estudo-formato-contexto/piloto
uv run python scripts/estudo_formato_contexto.py harness --real --repeticoes 1 `
  --casos research/M7/estudo-formato-contexto/piloto/casos.jsonl --out research/M7/estudo-formato-contexto/piloto `
  --confirmo-autorizacao "<quem autorizou>, <data>, <meio>"
```

Grade completa (64 casos × 16 células × 3 repetições = 3.072 chamadas por modelo; 12.288 no total):

```powershell
uv run python scripts/estudo_formato_contexto.py harness --real `
  --confirmo-autorizacao "<quem autorizou>, <data>, <meio>"
```

Um modelo por vez (útil para dividir em sessões): acrescentar `--modelos qwen3:4b-q4_K_M`. Interromper
com Ctrl+C é seguro; o mesmo comando continua de onde parou.

### Estimativa de tempo (NÃO medida; refazer com o piloto)

Premissas: prompt de ~400–450 tokens (+ template de chat), saída de 40–70 tokens com o schema, RTX 4050
Laptop (6 GB, ~192 GB/s). Avaliação do prompt ~800–1.500 tok/s; geração limitada por banda de memória:
~45–60 tok/s em Q4_K_M e ~28–35 tok/s em Q8_0 para modelos de 4B.

| Configuração | Por chamada | Piloto (256) | Grade completa (3.072) |
|---|---|---|---|
| 4B Q4_K_M (qwen3, qwen3.5) | ~1,3–2,0 s | ~6–9 min | ~65–100 min |
| 4B Q8_0 (qwen3, qwen3.5) | ~2,0–3,0 s | ~9–13 min | ~100–155 min |
| **4 modelos** | | **~30–45 min** | **~6–8 h** (+ ~10–30 s de carga por modelo) |

Se a memória transbordar para a CPU (offload), o tempo por chamada pode multiplicar por 3–10; o pico de
VRAM e a latência registrados no JSONL mostram isso já no piloto.

### Uso esperado de memória na sua máquina (RTX 4050 6 GB, 8 GB RAM)

- **VRAM:** a estimativa da M7-09 (pesos + KV f16 a 4k + 0,7 GiB de reserva CUDA) dá 3,7–4,0 GiB em Q4_K_M
  e 5,4–5,7 GiB em Q8_0, de 6,0 GiB. O Q8 deixa pouca folga: com o Windows usando ~0,4 GiB da GPU, o
  qwen3.5 Q8 pode cair em offload parcial.
- **RAM:** servidor Ollama ~0,3–0,6 GiB residente com o modelo inteiro na GPU, mais leitura do arquivo do
  modelo na carga (cache de disco, transitório) e ~0,2 GiB do harness Python. Com 8 GB e navegador aberto,
  o sistema pode paginar; com offload, a RAM precisa comportar as camadas que ficaram na CPU.
- Esses números são **estimativas**; o relatório real (`relatorio-real.json`) traz a VRAM de pico medida
  por célula e a latência mediana/p90.
