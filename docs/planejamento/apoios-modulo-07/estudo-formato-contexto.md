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
para o corpus da M7-03/M7-04. **Decisão registrada:** não encontrei no repositório um arquivo de
dicionário com as entradas fck/cobrimento/CAA; usei os termos do `scripts/mapear_propriedades.py`
(branch M3) e os valores normativos acima. Trocar pela fonte do dicionário quando ela existir.

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
