# M4 — Pesquisa de visualizadores IFC e protocolo de comparação

**Data de integração:** 12/10/2026. **Responsável pelo M4:** Nonato.
**Status:** pesquisa documental integrada; nenhum ensaio, instalação ou escolha de biblioteca executado.

Este apoio incorpora o resumo da pesquisa paralela enviado pela coordenação durante a
redação do [plano M4](../modulo-04-interface-revisao.md#m4-pesquisa). As fontes primárias
abaixo foram abertas para conferência documental nesta integração. O relatório integral
remoto mencionado pela coordenação não foi transferido para o checkout; não se alega sua
leitura integral. O resumo recebido e as páginas vinculadas sustentam este registro.

Há três níveis distintos de evidência: documentação oficial descreve contratos/capacidades;
issues/discussões relatam experiências individuais, com versões e limites; decisões de
arquitetura e testes do projeto são propostas nossas. Nenhum relato foi reproduzido aqui.
Estado aberto/fechado e release são um retrato da consulta, não previsão de comportamento
de uma versão futura. Não escolher ou descartar biblioteca apenas por contagem de issues.

<a id="m4-pesquisa-oficial"></a>

## 1. Contratos oficiais e consequências propostas

| Fonte primária | O que a documentação apresenta | Implicação proposta para o M4 |
|---|---|---|
| [That Open — IfcLoader](https://docs.thatopen.com/Tutorials/Components/Core/IfcLoader) | Importação IFC converte para Fragments; configuração de classes pode excluir entidades por padrão; exemplo configura WASM/worker por URLs externas | Registrar classes e ausências da conversão; ausência de malha não prova ausência IFC; empacotar ativos localmente |
| [That Open — FragmentsManager](https://docs.thatopen.com/Tutorials/Components/Core/FragmentsManager) | Exemplo de múltiplos modelos com modelId, worker e descarregamento/dispose | Dois modelos são requisito de ensaio; liberar recursos e não usar nome como identidade persistente |
| [That Open — API FragmentsModel](https://docs.thatopen.com/api/@thatopen/fragments/classes/FragmentsModel) | Distingue IDs locais, GUIDs/modelo, dados básicos e acesso a relações | Não presumir localId igual a EXPRESS ID; contrato M2 é autoridade dos dados semânticos |
| [That Open — API FragmentsManager](https://docs.thatopen.com/api/@thatopen/components/classes/FragmentsManager) | `applyBaseCoordinateSystem` usa uma base associada ao primeiro modelo carregado | Ensaiar A→B/B→A, unidades/offsets e origem comum; não prometer alinhamento universal |
| [That Open — Highlighter](https://docs.thatopen.com/Tutorials/Components/Front/Highlighter) | Seleção por clique/programática, mapa modelId→localIds, estilos e eventos | Traduzir referências e conservar alvo/origem distintos; testar interferência de estilos |
| [That Open — Clipper](https://docs.thatopen.com/Tutorials/Components/Core/Clipper) | Planos de corte e interação com a cena | Implementar cortes reversíveis sem alterar diagnóstico ou IFC |
| [IfcOpenShell — processamento geométrico Python](https://docs.ifcopenshell.org/ifcopenshell-python/geometry_processing.html) | Acesso a identificação, transformação, vértices e materiais de formas geradas | Alternativa de conversão local com mapa explícito; exige construir/adaptar a camada visual e suas interações |
| [IfcViewer — build e integração](https://docs.ifcopenshell.org/ifcviewer/installation.html) | Caminho web em WebAssembly/WebGPU e uso de formato `.ifcview`; documentação de integração/federação | Alternativa exploratória: verificar maturidade, build, navegador, licença e integração; não adoção automática |

Estas implicações são requisitos de projeto, não garantias oferecidas pelos tutoriais.
Não copiar downloads de exemplo como dependência obrigatória de produção. Registrar parser,
conversor, renderer, workers, WASM, política de classes e coordenadas no manifesto do derivado.

<a id="m4-pesquisa-relatos"></a>

## 2. Relatos reais e limite de interpretação

| Relato primário | Versão/data e conteúdo relatado | Limite e teste proposto |
|---|---|---|
| [Fragments #260](https://github.com/ThatOpen/engine_fragment/issues/260) | Aberto em 02/08/2026; Fragments 3.4.6/web-ifc 0.0.77. O autor descreve conversões repetidas do mesmo IFC2X3 com triângulos totais iguais, mas vínculos item–geometria variáveis | Causa não demonstrada pelo relato e não reproduzida aqui. T4-06 compara associação por entidade em três conversões frias; hash/totais sozinhos não bastam |
| [web-ifc #1999](https://github.com/ThatOpen/engine_web-ifc/issues/1999) | Aberto em 19/05/2026; versão 0.0.77; relato de modelo IFC4 MEP de cerca de 400 MB em Node, leitura de metadados seguida de erro de memória WASM em geometria | Volume do relato não é limite do projeto; MEP não amplia nosso domínio. T4-42 mede nosso corpus/hardware por etapa |
| [web-ifc #1380](https://github.com/ThatOpen/engine_web-ifc/issues/1380) | Discussão histórica de consumo de memória entre GetFlatMesh e streaming; fechamento relatado em 09/04/2025; discussão sobre callback síncrono | Fechamento não comprova release de correção aplicável. Comparar estratégia de consumo/liberação na combinação escolhida |
| [components #803](https://github.com/ThatOpen/engine_components/issues/803) | Pedido aberto em 15/09/2026 para AbortSignal consistente em operações assíncronas; versão não informada no resumo | Pedido não prova que todas as operações ignoram cancelamento. T4-48 verifica operação concreta e callback tardio |
| [components #775](https://github.com/ThatOpen/engine_components/issues/775) | Relato de ponto de picking inconsistente com câmera em movimento, em 25/07/2026 | T4-15 reproduz cenário no build fixado; não presumir que o bug persiste em versões posteriores |
| [Release components v3.4.9](https://github.com/ThatOpen/engine_components/releases/tag/v3.4.9) | Release de 06/10/2026 declara correções de picking, importação remota com Three r185+ e dispose, entre outras | Registro de correção é evidência do mantenedor, não teste da nossa aplicação. Repetir cenário crítico na versão selecionada |
| [web-ifc #2229](https://github.com/ThatOpen/engine_web-ifc/issues/2229) | Aberto em 28/09/2026; 0.0.77; diferença de transparência entre IfcSurfaceStyleShading e Rendering. Em 08/10 contributor pede reteste 0.0.78 | Pedido de reteste/expectativa de fix não confirma resultado do autor. Ensaiar transparência de material e override de contexto separadamente |
| [web-ifc #1739](https://github.com/ThatOpen/engine_web-ifc/issues/1739) | Relato 0.0.72 sobre NominalValue retornado versus tipo TypeScript; fechamento em 19/02/2026 associado a #1851, conforme levantamento | Histórico de contrato/runtime, não bug atual certificado. Validar DTOs em runtime e não presumir segurança só por compilar TS |
| [web-ifc #91](https://github.com/ThatOpen/engine_web-ifc/issues/91) | Relato histórico de 2021 sobre coordenadas grandes, fechado | Não prova defeito atual. Motiva cenário de coordenadas e precisão visual em T4-08/T4-13 |
| [xeokit discussão #1893](https://github.com/xeokit/xeokit-sdk/discussions/1893) | Usuário relata conversão lenta de IFC de cerca de 100 MB em junho de 2025; resposta discute dependência de web-ifc | Trocar viewer pode conservar o parser/conversor limitante. Separar tempos de parsing, conversão e renderização |
| [xeokit #1803](https://github.com/xeokit/xeokit-sdk/issues/1803) | Issue de 2025 sobre integração TypeScript e erro de runtime `Parameter expected: WebIFC`, fechada | Não é evidência de defeito específico do React. Conferir configuração e tipos na integração escolhida |

Datas/versões das issues são contexto do relato, não versões recomendadas para instalação.
Não há declaração de que o projeto reproduz qualquer uma dessas falhas nem de que uma
correção declarada remove todos os riscos. Vincular resultado de ensaio futuro à issue
somente quando as condições forem comparáveis.

<a id="m4-pesquisa-alternativas"></a>

## 3. Alternativas e critérios de seleção

| Estratégia | Motivo para comparar | Custo/questão a resolver |
|---|---|---|
| That Open / Fragments / web-ifc | Contratos documentados de carregamento, múltiplos modelos, seleção e cortes | Fidelidade de identidade, classes convertidas, recursos, versões e empacotamento local |
| xeokit SDK e XKT | Possível separação entre conversão e consumo de derivado, com identidade por modelo | Pipeline pode compartilhar web-ifc; não presumir ganho de parsing. Verificar licenças e custo de distribuição |
| Geometria Python IfcOpenShell + camada de renderização | Aproxima conversão da base Python e permite manifestos controlados | Mais trabalho de cena, seleção, cortes, otimização, ponte de IDs e formato derivado |
| IfcViewer web | Caminho exploratório WebGPU/WASM dentro do ecossistema IfcOpenShell | Maturidade e capacidades precisam de ensaio; suporte WebGPU não é universal |

O [repositório xeokit](https://github.com/xeokit/xeokit-sdk) identifica licença AGPL-3.0
e aponta condições comerciais; a adequação à distribuição pretendida exige conferência
específica com M6. O [XKTLoaderPlugin](https://xeokit.github.io/xeokit-sdk/docs/class/src/plugins/XKTLoaderPlugin/XKTLoaderPlugin.js~XKTLoaderPlugin.html)
documenta `globalizeObjectIds`, relevante para preservar o contexto de modelo, mas isso
não substitui nossa identidade de arquivo/revisão/entidade ou autoriza evidência cruzada.

Conferir licenças por componente/ferramenta do [IfcOpenShell](https://github.com/IfcOpenShell/IfcOpenShell),
inclusive dependências do caminho escolhido. Não assumir licença única de um ecossistema
inteiro. Este registro não emite parecer jurídico nem conclui adequação de distribuição.

Não atribuir notas inventadas de rapidez, robustez ou facilidade. A matriz comparativa
deverá registrar observado, não testado e impedimento, com versões e critérios iguais.

<a id="m4-pesquisa-protocolo"></a>

## 4. Protocolo de ensaio proposto — não executado

1. Conferir hashes, schema, unidades, quantidade de entidades, direitos e hardware dos
   arquivos usados. Os locais `casa_v1.ifc` e `predio_v1.ifc` são candidatos de recurso;
   não afirmar que são um par coordenado arquitetura/estrutura. Tamanhos aproximados
   recebidos na pesquisa devem ser medidos, não usados como promessa de suporte.
2. Obter o par coordenado e IDSs exigidos pelo MVP; acrescentar fixtures de GUID duplicado,
   ausência de geometria, unidades, offsets, partes e falhas, identificadas como sintéticas.
3. Carregar isoladamente e em federação A→B/B→A. Registrar referencial, política de origem
   e transformações; conferir elementos de referência e relações espaciais.
4. Fazer três conversões frias por estratégia/configuração e comparar entidade→geometria,
   não apenas total de triângulos, tamanho ou hash do derivado. Declarar classes excluídas.
5. Exercitar seleção rápida, câmera, cortes, transparência, ocultar/isolar/enquadrar e
   restauração. Comparar clique→ElementRef→linha com uma referência independente do viewer.
6. Cancelar/remover durante carga; garantir que resposta tardia não ressuscita modelo.
   Falhar um IFC e conservar outro, diagnóstico e decisões.
7. Abrir/fechar repetidamente e observar memória do processo/worker, heap/WASM/GPU quando
   disponível. Declarar limites da instrumentação e verificar descarregamento de recursos.
8. Registrar tempos por etapa, primeira imagem útil, lista disponível, seleção p50/p95,
   cache frio/quente e estabilidade. Não fixar limites universais antes desses dados.
9. Ensaiar pacote com ativos locais, build reproduzível quando autorizado e runtime com
   rede externa bloqueada. Nenhuma imagem, fonte, worker ou WASM deve exigir CDN.
10. Consolidar gates de identidade, alinhamento, completude, recuperação, localidade,
    licença/distribuição e recursos; escolher candidata somente com lacunas explicitadas.

Cada execução futura precisa de manifesto: data, operador, hardware/SO/navegador, versões
e hashes de parser/conversor/viewer/assets, arquivos/configuração, observado versus esperado,
capturas locais, falhas, métodos de medição e conclusão limitada à combinação testada.
Relato externo não é resultado nosso; benchmark de geometria não é benchmark de LLM.

**Correspondência:** [tarefas M4-03/M4-05/M4-07/M4-18/M4-19](../modulo-04-interface-revisao.md#m4-tarefas)
e [casos T4-03 a T4-15, T4-35, T4-40, T4-42, T4-48 e T4-50](../modulo-04-interface-revisao.md#m4-testes).

## 5. Resultado desta pesquisa documental

That Open permanece candidata. Nenhum viewer, limite de volume, nível de compatibilidade
ou resultado de performance foi aprovado neste apoio. A pesquisa produz perguntas e testes
concretos; a seleção final e o aceite 3D exigem ensaios reais. A escolha entre as três
propostas visuais entregues ao usuário também permanece pendente e é independente da
escolha técnica de biblioteca.
