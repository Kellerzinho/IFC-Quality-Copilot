# Condição escala-4070 — mesma régua, modelos que não cabem no notebook (2026-08-16)

Extensão do par unificado v7.7 (`docs/condicao-v7-7-2026-08-13.md` §7), já
prevista na análise do par como "sonda de escala 14B na 4070". A pergunta:
**o que parâmetros a mais compram, dentro da mesma família, com instrumento
fixo?** O desenho: uma rodada nova só na RTX 4070 12 GB, com 10 modelos que
não cabem (ou transbordam) nos 8 GB do notebook. O lado pequeno de cada
comparação **não é re-rodado**: é a perna 4070 do par v7.7 — mesma máquina,
mesma release de instrumento, mesmos estímulos. Como os prompts independem do
lock, os estímulos desta rodada são byte-idênticos aos do par; a comparação
grande×pequeno é intra-máquina e item a item.

**Isto não é um v7.8.** O instrumento (prompt v7.7, ground truth com a emenda
de 12/08, comparador) não muda em nada. Muda a **população de modelos** — e
população é dimensão declarada da identidade de execução
(`models_lock_sha256`), então a rodada ganha identidade própria por desenho.

## 1. O que muda e o que não muda

Muda:

- `src/experiment/results/models.lock.json` — população nova (§3), runtime
  preservado (Ollama **0.32.5** pinado, mesmo `asset_sha256` do par).
- `RELEASE_DATE` em `scripts/build_windows_release.py`: 2026-08-13 →
  2026-08-16 (republicação, conforme o contrato da constante).
- Pinos de teste do lock (`tests/experiment/test_model_lock.py`): soma
  45_852_962_404 → **91_733_110_513**; `required_free_bytes({})`
  57_032_733_355 → **114_699_862_808**.

Não muda: prompt v7.7 byte-idêntico (`PROMPT_VERSION` inalterado em
`prompt_templates.py`, `build_windows_release.py` e `install.ps1`); ground
truth sem deriva (4720/263); comparador; `num_ctx` fixo 4096; seed 42;
temperatura 0,1; réplica 1; cache off; reuse-equivalent; **prompt uniforme
entre modelos** — nenhuma condição por modelo, como sempre.

## 2. A máquina (inventário da perna 4070 do par, 13/08)

RTX 4070 desktop, **12.282 MiB** de VRAM (driver 591.86, CC 8.9, 200 W);
i9-12900 (16c/24t); **64 GB** de RAM DDR4-3200; disco C: com ~13 GB livres e
**D: com ~846 GB livres** — o armazém de modelos da release precisa ficar no
D: (o lock novo exige 114,7 GB livres; ver §6).

## 3. A população: 10 modelos, 5 eixos declarados

Fila = ordem do lock: residentes por download crescente; os dois transbordos
declarados ao fim (estágios rápidos consolidam retomada cedo; o risco fica
concentrado no fim da fila).

| # | tag | download | params | arch | quant | ctx | eixo |
|---|-----|----------|--------|------|-------|-----|------|
| 1 | falcon3:10b | 6,29 GB | 10,3B | llama | Q4_K_M | 32K | par estrito de falcon3:7b (1,4×) |
| 2 | mistral-nemo:12b | 7,07 GB | 12,2B | llama | Q4_0 | 1000K | escada Mistral, degrau 2 (1,7×) |
| 3 | gemma4:12b | 7,56 GB | 11,9B | gemma4 | Q4_K_M | 256K | escada geracional Gemma, geração +2 |
| 4 | gemma3:12b | 8,15 GB | 12,2B | gemma3 | Q4_K_M | 128K | escada geracional Gemma, geração +1 |
| 5 | deepseek-r1:14b | 8,99 GB | 14,8B | qwen2 | Q4_K_M | 128K | família nova: destilado de raciocínio |
| 6 | qwen2.5:14b-instruct | 8,99 GB | 14,8B | qwen2 | Q4_K_M | 32K | par estrito de qwen2.5:7b-instruct (2,0×) |
| 7 | phi4:14b | 9,05 GB | 14,7B | phi3 | Q4_K_M | 16K | par estrito de phi4-mini (3,9×) |
| 8 | qwen3:14b | 9,28 GB | 14,8B | qwen3 | Q4_K_M | 40K | linhagem Qwen: geração a porte fixo |
| 9 | mistral-small:22b | 12,57 GB | 22,2B | llama | Q4_0 | 128K | escada Mistral, degrau 3 + transbordo denso |
| 10 | gpt-oss:20b | 13,79 GB | 20,9B | gptoss | MXFP4 | 128K | família nova (OpenAI, MoE a3,6B) + transbordo MoE |

Os cinco eixos:

1. **Pares estritos** (lado pequeno medido no par v7.7): qwen2.5 7,6B→14,8B;
   phi4-mini 3,8B→phi4 14,7B; mistral 7,2B→nemo 12,2B; falcon3 7,5B→10,3B.
2. **Escada Mistral de 3 degraus** (7B→12B→22B): a única família com dois
   saltos medíveis dentro da janela — curva, não só par.
3. **Escada geracional Gemma no porte de 12 GB**: gemma2:9b (campeão top-1
   do par, 0,8216/0,8250) × gemma3:12b × gemma4:12b. Não é escala de
   parâmetros pura (arquiteturas gemma2→gemma3→gemma4); é a pergunta
   complementar: no mesmo orçamento de VRAM, a geração compra o que a
   escala não compra?
4. **Geração a porte fixo na linhagem Qwen**: qwen2.5:14b × qwen3:14b
   (14,8B ambos). Bônus de desenho: **deepseek-r1:14b é destilado sobre o
   Qwen2.5-14B** — mesma base, pós-treino de raciocínio; o trio 6×5×8 isola
   geração e pós-treino com parâmetros constantes. (Os downloads de r1:14b e
   qwen2.5:14b diferem por 12 KB — os pesos-base são o mesmo bolo.)
5. **Transbordo declarado** (extensão direta do achado do par: os dois
   líderes transbordam os 8 GB da 4060): mistral-small:22b (denso) ×
   gpt-oss:20b (MoE, 3,6B ativos) — frações de residência parecidas
   (~80–90% dos 12 GB), arquiteturas opostas. Na 4060, 16 GB de RAM
   seguraram o transbordo do gemma2 a 2,9× de latência; aqui há 64 GB.

## 4. Quem ficou de fora, com números

Regra do condutor: "se não tiver um superior que entre nessa máquina,
famílias novas ou modelos recentes". Aplicação, tudo medido no registry em
16/08:

- **qwen3.5:27b — 17,42 GB**: o degrau acima do qwen3.5:9b não entra em
  12 GB (denso, ~64% residente). qwen3.6 (27b/17 GB) e qwen3.8 (27,9B,
  ago/26) idem: a linhagem 3.5+ salta a janela.
- **granite4:small-h — 19,48 GB** (32,2B a9B): não entra; granite4 fica sem
  sucessor medível.
- **lfm2.5 — só existe em 8b**: sem irmão maior. (A instabilidade cross-GPU
  do lfm2.5 segue sendo história de modelo pequeno.)
- **llama3.1 — sem porte médio**: a linhagem 3.x para em 8B/70B; o sucessor
  local da Meta em 2026 (**muse-glimmer, 27,9B — 18,16 GB**) tampouco entra.
- **nemotron-3.5-lightning — 25,43 GB** (32,9B): fora. **gemma4:26b —
  18 GB**: fora.
- **mistral-small:24b — 14 GB e ctx 32K**: preterido pelo 22b (12,57 GB,
  ctx 128K, transbordo menor).
- **olmo2:13b — 8,35 GB**: entraria; considerado e preterido — inglês-
  cêntrico e sem elo com o lock pequeno; as escadas acima rendem mais por
  vaga. Fica pré-registrado como **substituto** (digest
  `6c279ebc980f…`) caso um dos dois modelos de risco (§7) falhe
  estruturalmente no piloto.
- Fronteira ago/2026 (deepseek-v4-flash, kimi-k3, laguna, ornith:35b,
  north-mini-code): tudo ≥27B/17 GB ou na classe ≤9B já medida — **os
  lançamentos de 2026 saltaram a janela de 12 GB**; o censo desta condição
  cobre o que existe nela.

## 5. Autoria do lock sem pull local (método novo, validado)

Nenhum dos 10 roda nesta máquina de 8 GB, e o pull local só para pinar
digests custaria ~92 GB. O lock foi autorado direto do registry oficial
(`scripts/lock_from_registry.py`, novo): digest = SHA-256 dos bytes crus do
manifest em `registry.ollama.ai`; `size_bytes` = config + soma das camadas;
arquitetura/parâmetros/quantização = config blob; `context_length` =
declarado por argumento, conferido na página oficial da tag (a regra de
exibição valor/1024 foi validada contra as 10 entradas do lock do par,
incluindo "125K" = 128000 do lfm2.5 e "1000K" = 1024000 do nemo).

Validação do método: gemma2:9b, lfm2.5:8b e qwen3.5:9b reproduzem
byte a byte o digest e o `size_bytes` do lock do par; gemma2:9b reproduz
também arquitetura/parâmetros/quantização. Comando registrado (a ordem é a
fila):

```bash
python scripts/lock_from_registry.py \
  falcon3:10b@32768 mistral-nemo:12b@1024000 gemma4:12b@262144 \
  gemma3:12b@131072 deepseek-r1:14b@131072 qwen2.5:14b-instruct@32768 \
  phi4:14b@16384 qwen3:14b@40960 mistral-small:22b@131072 gpt-oss:20b@131072
```

Tags do registry são móveis: se algum `ollama pull` na 4070 divergir do
digest pinado, o instalador aborta por contrato — nesse caso, re-executar o
comando acima, reconstruir a release e declarar a substituição do artefato
(mesma tag, digest novo) neste documento.

## 6. Viabilidade estimada (a rodada mede a verdade via telemetria)

Estimativa de carga = download + ~1,4 GB (KV a 4096 + overhead CUDA;
coerente com a telemetria do par: gemma2:9b, 5,44 GB de blobs, carregou
~6,9 GB). Com ~11 GB úteis na 4070: os oito primeiros ficam **residentes**
(7,7 a 10,7 GB estimados); mistral-small:22b ~85–90% residente e
gpt-oss:20b ~78–82% — transbordo declarado, como os líderes do par na 4060.
`llmfit fit --memory 12` (0.9.33) concorda: a classe 14B/Q4 é o teto
residente em 12 GB; o bundle de evidência da rodada coleta o llmfit da
própria máquina, como sempre.

Disco: download total **91,73 GB**; `required_free_bytes` = **114,7 GB** ⇒
armazém no **D:** (846 GB livres). Fila: o par fez 4h22 na 4070 com modelos
de 2,5–6,6 GB; com 6,3–13,8 GB e dois transbordos, planejar **~9–14 h**
(overnight). Como no par: reportar **latência por chamada** como métrica de
hardware, não a fila absoluta.

## 7. Riscos declarados e piloto obrigatório

Lição do ciclo v7.5/v7.6: pilotos acharam 3 defeitos antes da rodada
oficial. Aqui os riscos são de **formato de resposta**, concentrados nos
dois modelos de raciocínio:

- **deepseek-r1:14b** emite bloco de raciocínio antes do JSON. Precedente
  favorável: r1:8b passou pelo smoke de jul/26 com **0 falhas de JSON**.
- **gpt-oss:20b** usa o formato harmony; o Ollama 0.32.5 separa o canal
  `thinking` do `response` — conferir no piloto que o JSON estruturado
  chega inteiro em `response` e que a normalização o aceita.

**Piloto**: antes da fila oficial, rodar na 4070 os dois modelos de risco
sobre a casa (fila curta, 101 issues):

```bash
python scripts/run_benchmark.py --only-model gpt-oss:20b [...]
python scripts/run_benchmark.py --only-model deepseek-r1:14b [...]
```

Como a identidade de execução é a mesma, os estágios do piloto são
**reutilizados** pela retomada integral da fila oficial — piloto não
desperdiça GPU. Se um dos dois falhar estruturalmente (falhas de JSON em
série, canal vazio), entra o substituto pré-registrado (§4, olmo2:13b),
re-autorado no lock pelo §5, com nova release e emenda datada aqui.

## 8. Como verificar

```bash
# 1. O lock reproduz a partir do registry (digests, tamanhos, totais)
python scripts/lock_from_registry.py <argumentos do §5>

# 2. Guardas do lock, da release e do instrumento intacto
pytest tests/experiment/test_model_lock.py tests/windows -q
pytest tests/test_condicao_v7_7.py tests/test_prompt_nao_vaza_ground_truth.py -q

# 3. O ground truth segue sem deriva
python scripts/build_ground_truths.py --dataset all --check

# 4. Suíte completa
pytest tests/ -q --ignore=tests/evaluation
```

## 9. Estado na publicação

Lock escala-4070 gravado e validado pelo schema v2 (10 tags únicas, runtime
0.32.5 preservado, SHA-256 `eca716718094c800…`); pinos de teste atualizados;
`RELEASE_DATE` 2026-08-16; release **`ifcqc-2026-08-16-8623c03acde6`**
construída com prompt v7.7 inalterado
(`dist/IFCQC-Benchmark-2026-08-16-8623c03acde6.zip`, 73,3 MB). Resultado do
par unificado v7.7 permanece o resultado oficial do eixo principal; esta
condição adiciona o eixo de escala sem tocá-lo.
