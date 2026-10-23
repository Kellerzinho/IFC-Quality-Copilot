# Tema visual LEPV da UI M4: proposta em avaliação (2026-10-23)

Branch `feat/m4-tema-visual`, a partir de `feat/m4-plataforma-base`.

## Situação em relação ao plano

O plano M4 (§1, §6.2, §13.4) deixa a escolha de tema **aberta** entre três propostas: claro limpo,
escuro com foco no 3D e painéis compactos. A escolha depende de comparação com Felipe e Nonato.

Este tema é uma **quarta direção, pedida por Nonato**, com a identidade do LEPV. Ele foi implementado
como proposta e **não substitui a decisão pendente**: a tela de revisão mostra o selo
"Tema em avaliação". O tema mantém o que o plano já fixa para qualquer proposta:

- três áreas redimensionáveis (D4-12);
- contorno de seleção independente da paleta e informação que não depende só de cor (D4-14).
  O destaque 3D continua âmbar, e as lacunas usam ícone e texto;
- fontes e ativos locais, sem CDN (D4-27);
- uso só em desktop (D4-01). Os screenshots foram feitos a 1440 e 1024 px.

Não houve mudança de comportamento, contrato de API ou `data-testid`. Os acréscimos são:

- alternância claro/escuro;
- faixa de resumo, com novos `data-testid` `resumo-*`;
- fundo da cena 3D lido do token `--viewer-bg`.

## Paleta

Tokens em `frontend/src/index.css` (variáveis do shadcn/Tailwind v4).

| Papel | Token | Claro | Escuro |
|---|---|---|---|
| Papel (fundo) | `--background` | `#f7f5f0` | `#151312` |
| Superfície (painéis, cards) | `--card` | `#fdfcf9` | `#1e1b19` |
| Tinta | `--foreground` | `#1b1918` | `#ede8e1` |
| Tinta secundária | `--muted-foreground` | `#5c5650` | `#a9a097` |
| Vinho (botão primário, destaque, foco) | `--primary` / `--ring` | `#7b1e2c` | `#d9808e` / `#e08a97` |
| Texto sobre o vinho | `--primary-foreground` | `#fdfcf9` | `#1f0a0e` |
| Seleção na lista | `--accent` | `#f1e5e3` | `#3a2226` |
| Linhas finas | `--border` | `#dcd6cc` | `#36312d` |
| Borda de campo | `--input` | `#8f877c` | `#7a7168` |
| Erro | `--destructive` | `#b42318` | `#f0645a` |
| Atenção (fundo a 10–20%) | `--warning` | `#c27c0e` | `#e0a040` |
| Faixa escura | `--band` | `#1b1918` | `#0d0c0b` |
| Fundo 3D | `--viewer-bg` | `#efece6` | `#1a1816` |

No escuro, o vinho clareia e recebe texto escuro. O vinho original `#7b1e2c` ficaria com 2,9:1
sobre o fundo escuro.

O vermelho de erro (`#b42318`) é mais claro e mais quente que o vinho. Selos de erro sempre têm
texto, por exemplo "ambígua" ou "repetido neste arquivo".

## Contraste (WCAG 2.1 AA)

Os valores foram calculados a partir dos tokens. O script foi usado fora do repo; o resumo vem abaixo.

- **Texto (mínimo 4,5:1), nos dois temas:**
  - tinta/papel: 16,1 no claro e 15,2 no escuro;
  - tinta secundária sobre papel, card e muted: 5,8 a 7,2;
  - texto sobre o vinho: 9,9 no claro e 6,7 no escuro;
  - vinho como texto (links de envio): 9,3 no claro e 6,6 no escuro;
  - erro sobre papel: 6,0 no claro e 5,9 no escuro;
  - números e rótulos da faixa escura: 7,6 a 16,1;
  - texto sobre o fundo de atenção: 9,6 ou mais.
- **Não texto (mínimo 3:1):**
  - anel de foco: 6,7 ou mais;
  - borda de campo: 3,25 a 3,87.
- **Foco visível:** anel sólido de 2 px com offset em botão, campo, switch, item da lista e alça de
  redimensionamento.
  - O envio de arquivo usa input `sr-only`, por isso o anel fica no rótulo (`has-[:focus-visible]`).
  - Conferido em screenshot (`revisao-foco-escuro-*.png`).
- **Movimento:** o único movimento automático é a onda da entrada, desenhada uma vez. Com
  `prefers-reduced-motion`, a duração vai a ~0.

## Fontes

As fontes são pacotes locais (`@fontsource`) importados no CSS. O Vite as copia para `dist/assets/`.
A CSP `font-src 'self'` foi conferida no build: as três faces carregam, com zero violações.

| Uso | Família | Pacote (versão exata) | Licença |
|---|---|---|---|
| Títulos (serifa estreita, itálico pontual) | Instrument Serif | `@fontsource/instrument-serif@5.3.0` | SIL OFL 1.1 |
| UI, números de destaque | Instrument Sans (variável, 400–700) | `@fontsource-variable/instrument-sans@5.3.0` | SIL OFL 1.1 |
| GUID, hash, chave | monoespaçada do sistema | — | — |

- **Só o subconjunto latin da serifa:** o português está no Latin-1. A sans inclui latin-ext.
- **Números e nomes de elemento na sans.** O "1" da Instrument Serif se confunde com "l": "J-01" lia
  "J-0l". Num instrumento de revisão isso é risco de leitura, então a serifa ficou para títulos de
  projeto e da entrada.
- **`check:dist`:** antes rejeitava qualquer `@font-face`. Agora exige que cada `url()` de
  `@font-face` exista no próprio build. Uma `url()` externa continua acusada.

## O que veio de cada referência (`C:\dev\ref-lepv\`)

- **lepv.org:**
  - papel off-white e tinta quase preta;
  - vinho no botão primário e nos destaques;
  - serifa estreita nos títulos, com itálico vinho numa palavra;
  - sans neutra na UI e muito respiro na entrada;
  - linhas finas no lugar de sombras;
  - a linha ondulada vinho, usada só na entrada, como assinatura.
- **Design1 (estúdio de arquitetura):** hierarquia tipográfica forte (título de entrada a 72 px) e
  números grandes com rótulo pequeno, usados na faixa de resumo.
- **Design2 (portfólio):** cards com cantos arredondados (`--radius` 10 px, card 14 px) e muito
  espaço em volta dos títulos.
- **Design3 (coworking):** contraste claro/escuro entre seções. A entrada termina numa faixa escura,
  e o topo da revisão é uma faixa escura. Também vieram os números grandes em sans.

## Adaptação por tela

- **Entrada (editorial):**
  - título serifado grande e resumo curto do que a revisão faz;
  - onda vinho;
  - formulário ou tabela de vínculos num card;
  - faixa escura com os três passos reais da tela: enviar, confirmar e revisar. Passos de decisão e
    exportação ainda não existem na build e ficaram de fora.
- **Revisão (ferramenta densa):**
  - faixa escura compacta com o nome do projeto e quatro números: elementos, lacunas, ambíguas e
    sem geometria. Sem modelo analisado, lacunas e ambíguas mostram travessão, não zero;
  - linha clara com arquivo, revisão e IDS de cada disciplina;
  - lista e detalhe em superfície de card;
  - área 3D sem decoração.

## Pendências

1. Escolha visual com Felipe e Nonato, conforme o §13.4. Este tema é uma das opções.
2. O `<select>` de arquivo usa o controle nativo, com estilo do sistema no menu aberto.
3. O destaque 3D continua `#f59e0b`, sem revisão de contraste contra `--viewer-bg` escuro.
4. A logo "That Open Company" no canto do viewer vem da biblioteca, não do tema.
