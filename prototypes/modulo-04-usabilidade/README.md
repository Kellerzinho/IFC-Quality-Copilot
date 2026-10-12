# Módulo 04 — protótipo descartável de usabilidade

Abra **modulo-04.html** por duplo clique no navegador desktop. O HTML é o único arquivo necessário: contém CSS, JavaScript, dados fictícios e SVG, sem servidor, bibliotecas, fontes, CDN ou requisições externas. As demais peças nesta pasta documentam QA; não são dependências.

## Três organizações

1. Modelo em foco: cena esquemática dominante, lista sincronizada e propriedades recolhíveis.
2. Mesa de revisão: tabela dominante com miniatura e propriedades laterais.
3. Revisão guiada: um campo por vez, evidência visível e ações de revisão.

As três compartilham decisões, seleção e filtros. Há 11 elementos e 10 campos, dois arquivos demonstrativos de arquitetura/estrutura, GUID repetido em arquivos distintos, peitoril GRANITO de J03 e caixilho MADEIRA separados, conflito, falta de evidência, erro e requisito inadequado.

Os controles executam revisão individual, manual com fonte/justificativa e checagens ilustrativas, lote com prévia e confirmação, exclusões, desfazer, salvamento local com conferência e tratamento de falha, reinício confirmado e resumo JSON. O armazenamento depende do navegador e do caminho file://. O JSON é registro demonstrativo, não é IFC nem formato de importação de sessão.

## Limites

Não lê/escreve IFC, não valida IDS, não executa LLM e não envia modelos. O SVG isométrico é esquema selecionável, não engine BIM, e não oferece órbita/cortes. Aprovação humana registrada não representa escrita ou revalidação. É estudo de usabilidade descartável; não substitui a arquitetura React + TypeScript + Vite + shadcn/ui + API Python. Não há avaliação observada com Felipe/Nonato nesta entrega nem certificação BIM. Uso desktop; testado entre 1024 e 1920 px de largura.

## QA executado

- 55/55 verificações em Chrome headless instalado no executor, protocolo CDP local, arquivo file:// e emulação offline ativada.
- Três layouts, troca sem perder decisão, lista/tabela/SVG sincronizados, GUID composto, origem preservando alvo, busca e interseção vazias, disciplinas ocultas e navegação filtrada.
- Aceitar, tipo/unidade/fonte/justificativa inválidos, manual válido, rejeitar, manter pendente, requisito em revisão, erro/ausência/conflito bloqueados.
- Lote com confirmação, 4 elegíveis na situação testada, bloqueios, aplicação e desfazer integral; requisito sinalizado pelo revisor também excluído.
- Resumo sem falsa escrita, salvamento conferido, recarga file://, falha de storage simulada, reinício confirmado e restauração via desfazer.
- Contexto transparente, só pendências, cores/legendas, teclado no SVG, painel recolhido/expandido; 1024×1000, 1440×1000 e 1920×1000 sem overflow horizontal da página.
- Console: zero erros. Rede: somente duas navegações file:// (abertura e recarga); zero HTTP externo. CSP também bloqueia conexões.
- Inspeção visual das capturas locais dos três layouts. Corrigidos a altura da miniatura lateral e o botão de recolher fora do layout Modelo. Evidência guiada agora aparece de imediato.

Evidência verificável: `qa-results.json`, script `qa.cjs` e `qa-model.png`, `qa-table.png`, `qa-guided.png`. As capturas são QA interno, não substituem o HTML entregue. O script utiliza Node 24 e Chrome já instalado com depuração local na porta 9327; não exige npm.

## Artefato entregue

- Nome: `modulo-04.html`
- Tamanho: 37.545 bytes
- SHA256: `4FB13CE04AB7B05F9AB89ACCE8D92B3AF45C98E848F21787855827BDB3D4482D`
- Library: `libfile_c7444c875da48191b0543d32a6c14f76`
- File ID: `file_00000000d894820eaae2d16185f3b567`
- Versão Library: 0; upload confirmado, MIME `text/html`.

O helper de metadados locais da skill Library não estava acessível; a identidade retornada está registrada aqui e em `library-upload.json`, sem alegar xattrs locais aplicados. Isso não impediu o upload confirmado.

Nenhum plano M3/M4, backend ou arquivo de produção foi alterado. Nenhum stage, commit, push ou publicação foi feito. Alterações locais anteriores preservadas.
