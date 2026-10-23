# Prospecção de modelos — M7-09

> Arquivo gerado por `scripts/prospecta_modelos.py` a partir de `hardware-profiles.json` e `models.jsonl`. Não editar à mão.
>
> **Todos os valores de memória são ESTIMATIVA (pesos + KV + reserva), não medição.** Nenhum modelo foi carregado, baixado ou testado. Contexto anunciado não é contexto utilizável (plano M7, §13).

## Equipamentos

### `pessoal-nvidia-geforce-rtx-4050-laptop-gpu` (pessoal, observado)

- Coleta (UTC): 2026-10-13T02:52:53+00:00
- SO: Windows 11 (build 10.0.26200) (medido)
- GPU: NVIDIA GeForce RTX 4050 Laptop GPU, driver 572.83; VRAM total 6141 MiB, em uso 433 MiB, livre 5489 MiB (na coleta)
- CUDA máximo do driver: 12.8 (medido); toolkit (nvcc): indisponivel
- RAM total: 7,71 (medido) GiB; disponível na coleta: 0,84 (medido) GiB
- Disco livre (unidade do projeto): 82,2 (medido) GiB
- Ollama: 0.40.3 (medido), servidor no_ar (medido)
- Modelos instalados (ollama list): nenhum

### `ime-se2-lab` (ime, nao_confirmado)

- Laboratório da SE2 (linha IME): GPU, VRAM, RAM, acesso e concorrência ainda não confirmados. Toda célula fica condicionada até haver inventário real (T7-26).

## Tabela

| Família | Modelo | Quant. (bits efetivos) | Tag Ollama | Pesos fórmula (GiB) | Pesos publicados (GiB) | Pesos usados | KV 4k (GiB) | KV 8k (GiB) | Total 4k (GiB) | Total 8k (GiB) | Nominal 4k | Nominal 8k | Instantâneo 4k | Instantâneo 8k | ime-se2-lab | Gates condicionantes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3 | Qwen3-4B | Q8_0 (8,5008) | `qwen3:4b-q8_0` | 3,96 | 4,10 | publicado | 0,56 | 1,12 | 5,36 | 5,92 | GPU inteira | GPU inteira | GPU inteira | offload parcial | condicionado | — |
| Qwen3 | Qwen3-4B | Q5_K_M (5,7036) | não publicada | 2,66 | — | formula | 0,56 | 1,12 | 3,92 | 4,48 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | procedencia |
| Qwen3 | Qwen3-4B | Q4_K_M (4,8944) | `qwen3:4b-q4_K_M` | 2,28 | 2,42 | publicado | 0,56 | 1,12 | 3,68 | 4,25 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | — |
| Qwen3 | Qwen3-4B | Q3_K_M (3,996) | não publicada | 1,86 | — | formula | 0,56 | 1,12 | 3,12 | 3,69 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | procedencia |
| Qwen3 | Qwen3-8B | Q8_0 (8,5008) | `qwen3:8b-q8_0` | 8,12 | 8,29 | publicado | 0,56 | 1,12 | 9,55 | 10,11 | offload parcial | inviável | inviável | inviável | condicionado | — |
| Qwen3 | Qwen3-8B | Q5_K_M (5,7036) | não publicada | 5,45 | — | formula | 0,56 | 1,12 | 6,71 | 7,27 | offload parcial | offload parcial | inviável | inviável | condicionado | procedencia |
| Qwen3 | Qwen3-8B | Q4_K_M (4,8944) | `qwen3:8b-q4_K_M` | 4,67 | 4,84 | publicado | 0,56 | 1,12 | 6,11 | 6,67 | offload parcial | offload parcial | offload parcial | inviável | condicionado | — |
| Qwen3 | Qwen3-8B | Q3_K_M (3,996) | não publicada | 3,81 | — | formula | 0,56 | 1,12 | 5,08 | 5,64 | GPU inteira | GPU inteira | GPU inteira | offload parcial | condicionado | procedencia |
| Qwen3.5 | Qwen3.5-4B | Q8_0 (8,5008) | `qwen3.5:4b-q8_0` | 3,96 | 4,84 | publicado | 0,17 | 0,30 | 5,72 | 5,84 | GPU inteira | GPU inteira | offload parcial | offload parcial | condicionado | — |
| Qwen3.5 | Qwen3.5-4B | Q5_K_M (5,7036) | não publicada | 2,66 | — | formula | 0,17 | 0,30 | 3,53 | 3,65 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | procedencia |
| Qwen3.5 | Qwen3.5-4B | Q4_K_M (4,8944) | `qwen3.5:4b-q4_K_M` | 2,28 | 3,07 | publicado | 0,17 | 0,30 | 3,95 | 4,07 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | — |
| Qwen3.5 | Qwen3.5-4B | Q3_K_M (3,996) | não publicada | 1,86 | — | formula | 0,17 | 0,30 | 2,73 | 2,86 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | procedencia |
| Qwen3.5 | Qwen3.5-9B | Q8_0 (8,5008) | `qwen3.5:9b-q8_0` | 8,91 | 9,31 | publicado | 0,17 | 0,30 | 10,19 | 10,31 | inviável | inviável | inviável | inviável | condicionado | — |
| Qwen3.5 | Qwen3.5-9B | Q5_K_M (5,7036) | não publicada | 5,98 | — | formula | 0,17 | 0,30 | 6,85 | 6,97 | offload parcial | offload parcial | inviável | inviável | condicionado | procedencia |
| Qwen3.5 | Qwen3.5-9B | Q4_K_M (4,8944) | `qwen3.5:9b-q4_K_M` | 5,13 | 6,15 | publicado | 0,17 | 0,30 | 7,02 | 7,15 | offload parcial | offload parcial | inviável | inviável | condicionado | — |
| Qwen3.5 | Qwen3.5-9B | Q3_K_M (3,996) | não publicada | 4,19 | — | formula | 0,17 | 0,30 | 5,06 | 5,19 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | procedencia |
| Llama 3.x | Llama-3.2-3B-Instruct | Q8_0 (8,5008) | `llama3.2:3b-instruct-q8_0` | 3,18 | 3,17 | publicado | 0,44 | 0,88 | 4,30 | 4,74 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | licenca |
| Llama 3.x | Llama-3.2-3B-Instruct | Q5_K_M (5,7036) | `llama3.2:3b-instruct-q5_K_M` | 2,13 | 2,14 | publicado | 0,44 | 0,88 | 3,28 | 3,72 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | licenca |
| Llama 3.x | Llama-3.2-3B-Instruct | Q4_K_M (4,8944) | `llama3.2:3b-instruct-q4_K_M` | 1,83 | 1,86 | publicado | 0,44 | 0,88 | 3,00 | 3,44 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | licenca |
| Llama 3.x | Llama-3.2-3B-Instruct | Q3_K_M (3,996) | `llama3.2:3b-instruct-q3_K_M` | 1,49 | 1,58 | publicado | 0,44 | 0,88 | 2,72 | 3,16 | GPU inteira | GPU inteira | GPU inteira | GPU inteira | condicionado | licenca |
| Llama 3.x | Llama-3.1-8B-Instruct | Q8_0 (8,5008) | `llama3.1:8b-instruct-q8_0` | 7,92 | 7,92 | publicado | 0,50 | 1,00 | 9,12 | 9,62 | offload parcial | offload parcial | inviável | inviável | condicionado | licenca |
| Llama 3.x | Llama-3.1-8B-Instruct | Q5_K_M (5,7036) | `llama3.1:8b-instruct-q5_K_M` | 5,31 | 5,31 | publicado | 0,50 | 1,00 | 6,51 | 7,01 | offload parcial | offload parcial | inviável | inviável | condicionado | licenca |
| Llama 3.x | Llama-3.1-8B-Instruct | Q4_K_M (4,8944) | `llama3.1:8b-instruct-q4_K_M` | 4,56 | 4,56 | publicado | 0,50 | 1,00 | 5,76 | 6,26 | GPU inteira | offload parcial | offload parcial | inviável | condicionado | licenca |
| Llama 3.x | Llama-3.1-8B-Instruct | Q3_K_M (3,996) | `llama3.1:8b-instruct-q3_K_M` | 3,72 | 3,73 | publicado | 0,50 | 1,00 | 4,92 | 5,42 | GPU inteira | GPU inteira | GPU inteira | offload parcial | condicionado | licenca |

## Premissas

- Fórmula: pesos = tamanho publicado da tag (ou, sem tag, parâmetros × bits_efetivos ÷ 8); KV = 2 × camadas_com_KV × cabeças_KV × dim_cabeça × contexto × 2 bytes (f16); total = pesos + KV + estado recorrente + reserva de runtime.
- Bits efetivos (fallback da fórmula): https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md (tabela medida em meta-llama/Llama-3.1-8B; acesso 2026-10-12).
- ESTIMATIVA, não medição: o pico real só existe após ensaio autorizado (M7-10).
- Pesos = tamanho publicado da tag no catálogo do Ollama; fórmula só sem tag publicada. Tamanho de arquivo não é pico de memória medido.
- KV em f16 (padrão do Ollama), uma sequência por vez (fila serial M6).
- Reserva de runtime CUDA de 0,70 GiB, descontada da VRAM nos dois cenários.
- Cenário nominal: VRAM total; RAM para offload = RAM total − 4,00 GiB reservados ao sistema e aplicativos (premissa).
- Cenário instantâneo: VRAM livre e RAM disponível medidas no horário da coleta.
- Buffers de computação do grafo não estão incluídos.
- 1 GiB = 1024³ bytes; tamanhos do catálogo Ollama convertidos de GB decimais.
- Qwen3.5: só 8 das 32 camadas têm KV por token; as 24 lineares têm estado recorrente de tamanho fixo, somado na coluna KV.
- Estado recorrente de Qwen3.5-4B: 0,049 (derivado) GiB — https://huggingface.co/Qwen/Qwen3.5-4B/raw/main/config.json; https://github.com/ggml-org/llama.cpp/blob/8f574b0ad44c/src/llama-hparams.cpp; https://github.com/ggml-org/llama.cpp/blob/8f574b0ad44c/src/llama-model.cpp — acesso 2026-10-12. Estado fixo por sequência das 24 camadas lineares, independente do contexto: n_embd_s = ssm_d_state x ssm_d_inner = 128 x 4096 e n_embd_r (conv) = (d_conv-1) x (ssm_d_inner + 2 x n_group x ssm_d_state) = 3 x 8192, em float32 (recurrent_type_r/s = GGML_TYPE_F32 em src/llama-model.cpp): 24 x (524288 + 24576) x 4 B = 52.690.944 B = 0,049 GiB. Fórmulas e tipo em src/llama-hparams.cpp e src/llama-model.cpp do llama.cpp; dimensões do config.json (linear_key_head_dim=128, linear_num_value_heads x linear_value_head_dim=4096, linear_num_key_heads=16, linear_conv_kernel_dim=4). A verificar: o mapeamento config -> hparams no GGUF e se o runtime do Ollama 0.40.3 aloca igual ao llama.cpp
- Estado recorrente de Qwen3.5-9B: 0,049 (derivado) GiB — https://huggingface.co/Qwen/Qwen3.5-9B/raw/main/config.json; https://github.com/ggml-org/llama.cpp/blob/8f574b0ad44c/src/llama-hparams.cpp; https://github.com/ggml-org/llama.cpp/blob/8f574b0ad44c/src/llama-model.cpp — acesso 2026-10-12. Estado fixo por sequência das 24 camadas lineares, independente do contexto: n_embd_s = ssm_d_state x ssm_d_inner = 128 x 4096 e n_embd_r (conv) = (d_conv-1) x (ssm_d_inner + 2 x n_group x ssm_d_state) = 3 x 8192, em float32 (recurrent_type_r/s = GGML_TYPE_F32 em src/llama-model.cpp): 24 x (524288 + 24576) x 4 B = 52.690.944 B = 0,049 GiB. Fórmulas e tipo em src/llama-hparams.cpp e src/llama-model.cpp do llama.cpp; dimensões do config.json (linear_key_head_dim=128, linear_num_value_heads x linear_value_head_dim=4096, linear_num_key_heads=16, linear_conv_kernel_dim=4). A verificar: o mapeamento config -> hparams no GGUF e se o runtime do Ollama 0.40.3 aloca igual ao llama.cpp

## Gates de licença

- **Qwen3-4B** — `sem_restricao_identificada`: Apache 2.0 confirmada no LICENSE oficial; o texto não tem cláusula de restrição por campo de uso (militar, defesa ou outro).
  - https://huggingface.co/Qwen/Qwen3-4B/blob/1cfa9a720891/LICENSE — acesso 2026-10-12. Apache License 2.0 no arquivo LICENSE (SHA-256 832dd9e00a68dd83...) e cardData.license=apache-2.0 na revisão 1cfa9a720891
- **Qwen3-8B** — `sem_restricao_identificada`: Apache 2.0 confirmada no LICENSE oficial; o texto não tem cláusula de restrição por campo de uso (militar, defesa ou outro).
  - https://huggingface.co/Qwen/Qwen3-8B/blob/b968826d9c46/LICENSE — acesso 2026-10-12. Apache License 2.0 no arquivo LICENSE (SHA-256 832dd9e00a68dd83...) e cardData.license=apache-2.0 na revisão b968826d9c46
- **Qwen3.5-4B** — `sem_restricao_identificada`: Apache 2.0 confirmada no LICENSE oficial; o texto não tem cláusula de restrição por campo de uso (militar, defesa ou outro).
  - https://huggingface.co/Qwen/Qwen3.5-4B/blob/851bf6e806ef/LICENSE — acesso 2026-10-12. Apache License 2.0 no arquivo LICENSE (SHA-256 bbedc3fda3305820...) e cardData.license=apache-2.0 na revisão 851bf6e806ef
- **Qwen3.5-9B** — `sem_restricao_identificada`: Apache 2.0 confirmada no LICENSE oficial; o texto não tem cláusula de restrição por campo de uso (militar, defesa ou outro).
  - https://huggingface.co/Qwen/Qwen3.5-9B/blob/c20223623576/LICENSE — acesso 2026-10-12. Apache License 2.0 no arquivo LICENSE (SHA-256 bbedc3fda3305820...) e cardData.license=apache-2.0 na revisão c20223623576
- **Llama-3.2-3B-Instruct** — `condicionado`: bloqueio potencial: uso militar — decisão do orientador (Cel Giuseppe). A licença incorpora por referência a Acceptable Use Policy, que lista entre os usos proibidos atividades 'related to ... Military, warfare, nuclear industries or applications, espionage' e as sujeitas ao ITAR. Candidato mantido e condicionado por licença; este registro não conclui se pode ou não ser usado. Decisão: orientador (Cel Giuseppe).
  - https://github.com/meta-llama/llama-models/blob/8d29d93fa570/models/llama3_2/LICENSE — acesso 2026-10-12. Version Release Date: September 25, 2024. §1.b.iv incorpora a Acceptable Use Policy; §2 exige licença da Meta acima de 700 milhões de usuários ativos mensais
  - https://github.com/meta-llama/llama-models/blob/8d29d93fa570/models/llama3_2/USE_POLICY.md — acesso 2026-10-12. Texto: 'Engage in, promote, incite, facilitate, or assist in the planning or development of activities that present a risk of death or bodily harm to individuals, including use of Llama 3.2 related to the following: 8. Military, warfare, nuclear industries or applications, espionage, use for materials or activities that are subject to the International Traffic Arms Regulations (ITAR) ...'. A URL da política citada no próprio LICENSE redireciona para developer.meta.com e termina em 404 em 2026-10-12; o texto usado é o do repositório oficial meta-llama/llama-models
- **Llama-3.1-8B-Instruct** — `condicionado`: bloqueio potencial: uso militar — decisão do orientador (Cel Giuseppe). A licença incorpora por referência a Acceptable Use Policy, que lista entre os usos proibidos atividades 'related to ... Military, warfare, nuclear industries or applications, espionage' e as sujeitas ao ITAR. Candidato mantido e condicionado por licença; este registro não conclui se pode ou não ser usado. Decisão: orientador (Cel Giuseppe).
  - https://github.com/meta-llama/llama-models/blob/1f0feb795a41/models/llama3_1/LICENSE — acesso 2026-10-12. Version Release Date: July 23, 2024. §1.b.iv incorpora a Acceptable Use Policy; §2 exige licença da Meta acima de 700 milhões de usuários ativos mensais
  - https://github.com/meta-llama/llama-models/blob/1f0feb795a41/models/llama3_1/USE_POLICY.md — acesso 2026-10-12. Texto: 'Engage in, promote, incite, facilitate, or assist in the planning or development of activities that present a risk of death or bodily harm to individuals, including use of Llama 3.1 related to the following: Military, warfare, nuclear industries or applications, espionage, use for materials or activities that are subject to the International Traffic Arms Regulations (ITAR) ...'. A URL da política citada no próprio LICENSE redireciona para developer.meta.com e termina em 404 em 2026-10-12; o texto usado é o do repositório oficial meta-llama/llama-models

## Contexto, licença e estado por modelo

| Modelo | Contexto anunciado | Contexto no catálogo | Contexto utilizável | Licença | Instalado | Testado | Selecionado | Runs antigos |
|---|---|---|---|---|---|---|---|---|
| Qwen3-4B | 32768 (fonte_primaria) | 40K | nao_medido | apache-2.0 (fonte_primaria) | não | não | não | pendente_M7-02 |
| Qwen3-8B | 32768 (fonte_primaria) | 40K | nao_medido | apache-2.0 (fonte_primaria) | não | não | não | pendente_M7-02 |
| Qwen3.5-4B | 262144 (fonte_primaria) | 256K | nao_medido | apache-2.0 (fonte_primaria) | não | não | não | pendente_M7-02 |
| Qwen3.5-9B | 262144 (fonte_primaria) | 256K | nao_medido | apache-2.0 (fonte_primaria) | não | não | não | pendente_M7-02 |
| Llama-3.2-3B-Instruct | 131072 (fonte_primaria) | 128K | nao_medido | Llama 3.2 Community License (fonte_primaria) | não | não | não | pendente_M7-02 |
| Llama-3.1-8B-Instruct | 131072 (fonte_primaria) | 128K | nao_medido | Llama 3.1 Community License (fonte_primaria) | não | não | não | pendente_M7-02 |

## Notas

- **Qwen3-4B**: A tag padrão qwen3:4b (2,5 GB, 256K) não é a mesma de qwen3:4b-q4_K_M (2,6 GB, 40K): aponta para outro checkpoint. Usar a tag explícita; conferir o digest antes de qualquer ensaio.
- **Qwen3.5-4B**: Modelo multimodal (encoder de visão de 27 blocos); o tamanho do catálogo inclui partes que o MVP textual não usa.
- **Qwen3.5-9B**: Default atual do repositório (src/config.py: qwen3.5:9b).
- **Qwen3.5-9B**: Modelo multimodal (encoder de visão de 27 blocos); o tamanho do catálogo inclui partes que o MVP textual não usa.
- **Llama-3.2-3B-Instruct**: Arquitetura lida no espelho unsloth: o config.json oficial da Meta exige login no Hugging Face.
- **Llama-3.1-8B-Instruct**: Llama 3.2 e 3.1 são gerações vizinhas, não a mesma: o par mede tamanho e geração juntos.
- **Llama-3.1-8B-Instruct**: Arquitetura lida no espelho unsloth: o config.json oficial da Meta exige login no Hugging Face.
