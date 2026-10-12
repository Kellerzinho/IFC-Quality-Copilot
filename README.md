# IFC Quality Copilot

Projeto de pesquisa para diagnóstico e enriquecimento semântico de modelos IFC,
com requisitos IDS, contexto técnico, LLM local e revisão humana. O objetivo é
melhorar a qualidade dos dados preservando controle técnico e rastreabilidade.

## Estado da base — 9 de outubro de 2026

A implementação Python reúne leitura IFC, parser e regras IDS, cliente bSDD,
geração de sugestões via Ollama, interface Streamlit, escrita IFC, auditoria,
exportação BCF e avaliação experimental. A existência desses componentes não
certifica conformidade integral nem todas as garantias da arquitetura pretendida.

Catálogo completo de domínio, revisão visual 3D por elemento, persistência da
revisão humana e comparação entre revisões IFC são capacidades a desenvolver.
Os contratos de `src/foundation/` iniciam essa evolução; sua aplicação transversal
ainda precisa ser implementada e verificada.

## Comece por aqui

1. [Índice da documentação](docs/README.md): arquitetura, ciência e histórico.
2. [Planejamento atual](docs/planejamento/README.md): decisões e sequência de trabalho.
3. [Mapa das sete frentes](docs/planejamento/mapa-sete-frentes.md): responsabilidades e caminhos existentes.
4. [Arquitetura base](docs/arquitetura/base-do-projeto.md): fluxo atual, evolução e contratos.

A [consolidação de 09/10](docs/planejamento/CONSOLIDACAO-2026-10-09.md) conserva o
inventário e as decisões recebidas até sua gravação. Decisões confirmadas depois
estão datadas no índice de planejamento, mantendo esse registro intacto.
Para trabalhar na base, leia também as [convenções](CLAUDE.md) e o
[contexto técnico](PROJECT_CONTEXT.md), com as ressalvas datadas de ambos.

## Limites confirmados para a primeira versão

- Arquitetura e estrutura, tendo a base completa de Daiane como piso de cobertura
  a operacionalizar, incluindo `EB_Orçamento` fiel/reconciliado à dissertação,
  sem restringir o motor a um único catálogo nem substituí-lo silenciosamente por `Cost_Prop`.
- O operador fornece um **IDS pronto**. Autoria de IDS pela UI fica fora do escopo inicial.
- IDS pode conter propriedades desconhecidas pelo catálogo: requisitos suportados
  devem ser validados independentemente do cadastro; ausência de mapeamento é explícita.
- Após checar os arquivos, o fluxo pretendido prossegue com os requisitos
  suportados e sinaliza limitações. Arquivos ilegíveis ou inválidos bloqueiam
  quando impedem interpretação confiável; não verificado nunca significa aprovado.
- O operador pode solicitar mapeamentos; somente o curador aprova e publica uma
  versão do catálogo. Sugestões do LLM não viram cadastro aprovado automaticamente.
- Cadastro e extensão de propriedades pela plataforma são requisitos confirmados.
  A direção de tabela editável com detalhamento foi aprovada; layout e interação
  serão aprofundados na implementação. Adicionar cadastro não cria automaticamente
  operação de extração/inferência nem altera IDS ou IFC.
- Definição, aplicabilidade e evidências ficam separadas; conceitos podem ser
  reutilizados quando têm o mesmo significado. Cada projeto fixa uma versão do
  catálogo e a atualiza explicitamente, com diff, reprocessamento e histórico rastreável.
- Cadastro sem código usa operações suportadas. Novas extrações ou cálculos
  exigem implementação e ficam sem enriquecimento até ela existir.
- Inferência, dados e ativos operacionais ficam locais ou internos ao IME. O
  inventário registra dependências externas legadas ainda a tratar.
- O LLM sugere; a evolução pretendida aplica somente campos aprovados em uma cópia
  IFC e revalida a saída. Os achados de integridade existentes estão documentados.

O catálogo provisório deve ser substituível pelo trabalho de Juliana. SINAPI
operacional, preços, composições e orçamento ficam para etapa futura.
A obtenção do IDS original de dez especificações e da planilha editável será
buscada com Juliana; enquanto isso, a base será estruturada pelos apêndices,
mantendo divergências pendentes e a distinção entre fontes.
Autoria/criação de IDS é um [módulo futuro previsto](docs/planejamento/README.md#extensao-futura--autoria-ids),
com aprofundamento posterior e sem ampliar o escopo da primeira entrega.
O instrumento científico permanece em `PROMPT_VERSION v7.8`; condições,
gabaritos e resultados históricos mantêm suas identidades próprias.
