# Prospecção de modelos — M7-09

> Arquivo gerado por `scripts/prospecta_modelos.py` a partir de `hardware-profiles.json` e `models.jsonl`. Não editar à mão.
>
> **Todos os valores de memória são ESTIMATIVA (pesos + KV + reserva), não medição.** Nenhum modelo foi carregado, baixado ou testado. Contexto anunciado não é contexto utilizável (plano M7, §13).

## Equipamentos

### `pessoal-nvidia-geforce-rtx-4050-laptop-gpu` (pessoal, observado)

- Coleta (data UTC): 2026-10-13
- SO: Windows 11 (build 10.0.26200) (medido)
- GPU: NVIDIA GeForce RTX 4050 Laptop GPU, 6141 MiB, driver 572.83
- CUDA máximo do driver: 12.8 (medido); toolkit (nvcc): indisponivel
- RAM total: 7,71 (medido) GiB; livre na coleta: 0,43 (medido) GiB
- Disco livre (unidade do projeto): 82,4 (medido) GiB
- Ollama: 0.40.3 (medido), servidor no_ar (medido)
- Modelos instalados (ollama list): nenhum

### `ime-se2-lab` (ime, nao_confirmado)

- Laboratório da SE2 (linha IME): GPU, VRAM, RAM, acesso e concorrência ainda não confirmados. Toda célula fica condicionada até haver inventário real (T7-26).

## Tabela

| Família | Modelo | Quant. (bits efetivos) | Tag Ollama | Pesos fórmula (GiB) | Catálogo (GiB) | KV 4k (GiB) | KV 8k (GiB) | Total 4k (GiB) | Total 8k (GiB) | Pessoal 4k | Pessoal 8k | ime-se2-lab |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| Qwen3 | Qwen3-4B | Q8_0 (8,5008) | `qwen3:4b-q8_0` | 3,96 | 4,10 | 0,56 | 1,12 | 5,22 | 5,78 | GPU inteira | GPU inteira | condicionado |
| Qwen3 | Qwen3-4B | Q5_K_M (5,7036) | não publicada | 2,66 | — | 0,56 | 1,12 | 3,92 | 4,48 | GPU inteira | GPU inteira | condicionado |
| Qwen3 | Qwen3-4B | Q4_K_M (4,8944) | `qwen3:4b-q4_K_M` | 2,28 | 2,42 | 0,56 | 1,12 | 3,54 | 4,10 | GPU inteira | GPU inteira | condicionado |
| Qwen3 | Qwen3-4B | Q3_K_M (3,996) | não publicada | 1,86 | — | 0,56 | 1,12 | 3,12 | 3,69 | GPU inteira | GPU inteira | condicionado |
| Qwen3 | Qwen3-8B | Q8_0 (8,5008) | `qwen3:8b-q8_0` | 8,12 | 8,29 | 0,56 | 1,12 | 9,38 | 9,94 | offload parcial | inviável | condicionado |
| Qwen3 | Qwen3-8B | Q5_K_M (5,7036) | não publicada | 5,45 | — | 0,56 | 1,12 | 6,71 | 7,27 | offload parcial | offload parcial | condicionado |
| Qwen3 | Qwen3-8B | Q4_K_M (4,8944) | `qwen3:8b-q4_K_M` | 4,67 | 4,84 | 0,56 | 1,12 | 5,93 | 6,50 | GPU inteira → offload parcial* | offload parcial | condicionado |
| Qwen3 | Qwen3-8B | Q3_K_M (3,996) | não publicada | 3,81 | — | 0,56 | 1,12 | 5,08 | 5,64 | GPU inteira | GPU inteira | condicionado |
| Qwen3.5 | Qwen3.5-4B | Q8_0 (8,5008) | `qwen3.5:4b-q8_0` | 3,96 | 4,84 | 0,17 | 0,30 | 4,83 | 4,96 | GPU inteira | GPU inteira | condicionado |
| Qwen3.5 | Qwen3.5-4B | Q5_K_M (5,7036) | não publicada | 2,66 | — | 0,17 | 0,30 | 3,53 | 3,65 | GPU inteira | GPU inteira | condicionado |
| Qwen3.5 | Qwen3.5-4B | Q4_K_M (4,8944) | `qwen3.5:4b-q4_K_M` | 2,28 | 3,07 | 0,17 | 0,30 | 3,15 | 3,28 | GPU inteira | GPU inteira | condicionado |
| Qwen3.5 | Qwen3.5-4B | Q3_K_M (3,996) | não publicada | 1,86 | — | 0,17 | 0,30 | 2,73 | 2,86 | GPU inteira | GPU inteira | condicionado |
| Qwen3.5 | Qwen3.5-9B | Q8_0 (8,5008) | `qwen3.5:9b-q8_0` | 8,91 | 9,31 | 0,17 | 0,30 | 9,78 | 9,91 | inviável | inviável | condicionado |
| Qwen3.5 | Qwen3.5-9B | Q5_K_M (5,7036) | não publicada | 5,98 | — | 0,17 | 0,30 | 6,85 | 6,97 | offload parcial | offload parcial | condicionado |
| Qwen3.5 | Qwen3.5-9B | Q4_K_M (4,8944) | `qwen3.5:9b-q4_K_M` | 5,13 | 6,15 | 0,17 | 0,30 | 6,00 | 6,13 | offload parcial | offload parcial | condicionado |
| Qwen3.5 | Qwen3.5-9B | Q3_K_M (3,996) | não publicada | 4,19 | — | 0,17 | 0,30 | 5,06 | 5,19 | GPU inteira | GPU inteira | condicionado |
| Llama 3.x | Llama-3.2-3B-Instruct | Q8_0 (8,5008) | `llama3.2:3b-instruct-q8_0` | 3,18 | 3,17 | 0,44 | 0,88 | 4,31 | 4,75 | GPU inteira | GPU inteira | condicionado |
| Llama 3.x | Llama-3.2-3B-Instruct | Q5_K_M (5,7036) | `llama3.2:3b-instruct-q5_K_M` | 2,13 | 2,14 | 0,44 | 0,88 | 3,27 | 3,71 | GPU inteira | GPU inteira | condicionado |
| Llama 3.x | Llama-3.2-3B-Instruct | Q4_K_M (4,8944) | `llama3.2:3b-instruct-q4_K_M` | 1,83 | 1,86 | 0,44 | 0,88 | 2,97 | 3,40 | GPU inteira | GPU inteira | condicionado |
| Llama 3.x | Llama-3.2-3B-Instruct | Q3_K_M (3,996) | `llama3.2:3b-instruct-q3_K_M` | 1,49 | 1,58 | 0,44 | 0,88 | 2,63 | 3,07 | GPU inteira | GPU inteira | condicionado |
| Llama 3.x | Llama-3.1-8B-Instruct | Q8_0 (8,5008) | `llama3.1:8b-instruct-q8_0` | 7,92 | 7,92 | 0,50 | 1,00 | 9,12 | 9,62 | offload parcial | offload parcial | condicionado |
| Llama 3.x | Llama-3.1-8B-Instruct | Q5_K_M (5,7036) | `llama3.1:8b-instruct-q5_K_M` | 5,31 | 5,31 | 0,50 | 1,00 | 6,51 | 7,01 | offload parcial | offload parcial | condicionado |
| Llama 3.x | Llama-3.1-8B-Instruct | Q4_K_M (4,8944) | `llama3.1:8b-instruct-q4_K_M` | 4,56 | 4,56 | 0,50 | 1,00 | 5,76 | 6,26 | GPU inteira | offload parcial | condicionado |
| Llama 3.x | Llama-3.1-8B-Instruct | Q3_K_M (3,996) | `llama3.1:8b-instruct-q3_K_M` | 3,72 | 3,73 | 0,50 | 1,00 | 4,92 | 5,42 | GPU inteira | GPU inteira | condicionado |

`*` a classificação muda quando se usa o tamanho publicado no catálogo do Ollama no lugar da fórmula (o arquivo real costuma ser maior: embeddings e partes multimodais ficam em maior precisão).

## Premissas

- Fórmula: pesos = parâmetros × bits_efetivos ÷ 8; KV = 2 × camadas_com_KV × cabeças_KV × dim_cabeça × contexto × 2 bytes (f16); total = pesos + KV + estado recorrente + reserva de runtime.
- Bits efetivos: https://github.com/ggml-org/llama.cpp/blob/master/tools/quantize/README.md (tabela medida em meta-llama/Llama-3.1-8B; acesso 2026-10-12).
- ESTIMATIVA, não medição: o pico real só existe após ensaio autorizado (M7-10).
- KV em f16 (padrão do Ollama), uma sequência por vez (fila serial M6).
- Reserva de runtime CUDA de 0,70 GiB, descontada da VRAM.
- RAM para offload = RAM total − 4,00 GiB reservados ao sistema e aplicativos (premissa declarada).
- Buffers de computação do grafo não estão incluídos.
- 1 GiB = 1024³ bytes; tamanhos do catálogo Ollama convertidos de GB decimais.
- Qwen3.5: só 8 das 32 camadas têm KV por token; as 24 lineares têm estado recorrente de tamanho fixo, somado na coluna KV.

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
- **Qwen3-4B**: Q5_K_M não publicado no catálogo do Ollama para Qwen3-4B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Qwen3-4B**: Q3_K_M não publicado no catálogo do Ollama para Qwen3-4B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Qwen3-8B**: Q5_K_M não publicado no catálogo do Ollama para Qwen3-8B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Qwen3-8B**: Q3_K_M não publicado no catálogo do Ollama para Qwen3-8B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Qwen3.5-4B**: Modelo multimodal (encoder de visão de 27 blocos); o tamanho do catálogo inclui partes que o MVP textual não usa.
- **Qwen3.5-4B**: Q5_K_M não publicado no catálogo do Ollama para Qwen3.5-4B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Qwen3.5-4B**: Q3_K_M não publicado no catálogo do Ollama para Qwen3.5-4B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Qwen3.5-9B**: Default atual do repositório (src/config.py: qwen3.5:9b).
- **Qwen3.5-9B**: Modelo multimodal (encoder de visão de 27 blocos); o tamanho do catálogo inclui partes que o MVP textual não usa.
- **Qwen3.5-9B**: Q5_K_M não publicado no catálogo do Ollama para Qwen3.5-9B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Qwen3.5-9B**: Q3_K_M não publicado no catálogo do Ollama para Qwen3.5-9B: exigiria importar GGUF de terceiros (procedência a verificar).
- **Llama-3.2-3B-Instruct**: Arquitetura lida no espelho unsloth: o config.json oficial da Meta exige login no Hugging Face.
- **Llama-3.1-8B-Instruct**: Llama 3.2 e 3.1 são gerações vizinhas, não a mesma: o par mede tamanho e geração juntos.
- **Llama-3.1-8B-Instruct**: Arquitetura lida no espelho unsloth: o config.json oficial da Meta exige login no Hugging Face.
