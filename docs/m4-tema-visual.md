# Tema visual da UI M4: Proposta Oliva-Turquesa (em avaliação)

Branch `feat/m4-tema-visual`, a partir de `feat/m4-plataforma-base`, ajustada em 2026-10-23.

## Situação em relação ao plano

O plano M4 (§1, §6.2, §13.4) deixa a escolha de tema **aberta** entre três propostas: claro limpo,
escuro com foco no 3D e painéis compactos. A escolha depende de comparação com Felipe e Nonato.

Esta é uma proposta adicional, **em avaliação**, e não substitui a decisão pendente. A tela de revisão
mostra o selo "Tema em avaliação".

- **Por que a identidade mudou:** a plataforma é do IME para o Exército. A identidade sai do LEPV e passa
  a usar verde-oliva, azul-turquesa (cor da arma de Engenharia) e ouro.
- **Proposta anterior:** a proposta LEPV (papel, tinta e vinho) está preservada, sem push, na branch
  `feat/m4-tema-lepv` (`1a230a0`).

O tema mantém o que o plano fixa para qualquer proposta:

- três áreas redimensionáveis (D4-12);
- contorno de seleção e informação que não dependem só de cor (D4-14). Seleção, lacunas e "GUID
  repetido" sempre têm borda, ícone ou texto;
- fontes e ativos locais, sem CDN (D4-27);
- uso só em desktop (D4-01).

Não houve mudança de comportamento, contrato de API ou `data-testid` existente. Os acréscimos são:

- `data-testid` `resumo-*-rotulo` nos rótulos da faixa;
- botão copiar na chave e na revisão IFC.

> **Ressalva.** Os códigos de cor abaixo são **aproximados**. Antes de qualquer uso oficial, confira-os
> com o manual de identidade visual do Exército Brasileiro e com a comunicação do IME. A tela não usa
> brasão, logotipo nem marca oficial. O vínculo institucional aparece só em texto
> ("Instituto Militar de Engenharia · PIBITI 2026/2027").

## Paleta

Os tokens têm os mesmos nomes nos dois temas e ficam em `frontend/src/index.css`. No bloco `@theme`,
eles são mapeados para os nomes do shadcn/Tailwind.

| Token | Claro | Escuro | Nome shadcn/Tailwind |
|---|---|---|---|
| `--bg` | `#f7f7f4` | `#141511` | `background` |
| `--surface` | `#ffffff` | `#1f201c` | `card`, `popover` |
| `--sunken` | `#ebece6` | `#2b2c28` | `muted`, `secondary` |
| `--line` | `#d8d8d1` | `#40403a` | `border` |
| `--ink` | `#1b1b18` | `#ebece6` | `foreground` |
| `--muted` | `#555650` | `#a2a29b` | `muted-foreground`, `input` |
| `--band` | `#292f0e` | `#0f110a` | `band` |
| `--band-ink` | `#f7f7f4` | `#ebece6` | `band-foreground` |
| `--band-muted` | `#d3dfa7` | `#b9c58e` | `band-muted` |
| `--primary` | `#525b27` | `#b9c58e` | `primary` |
| `--primary-ink` | `#ffffff` | `#191d0a` | `primary-foreground` |
| `--accent` | `#026266` | `#56d3da` | `accent`, `ring` |
| `--accent-soft` | `#e1fdff` | `#02494d` | `accent-soft` |
| `--gold` | `#e4b750` | `#e4b750` | `gold` |
| `--gold-text` | `#6d5001` | `#ffd16b` | `gold-text` |
| `--gold-soft` | `#fef6e5` | `#392800` | `gold-soft` |
| `--danger` | `#b63b35` | `#f57569` | `destructive` |
| `--danger-soft` | `#fff4f2` | `#560507` | `destructive-soft` |
| `--viewer` | `#ebece6` | `#1b1b18` | lido pelo adaptador 3D |

## Papéis das cores

- **primary (oliva):** botões primários ("Criar projeto", "Confirmar", "Abrir revisão").
- **accent (turquesa):**
  - seleção na lista: fundo `accent-soft` com borda `accent`;
  - links ("Enviar IFC/IDS");
  - anel de foco de 2 px com offset;
  - switches ligados.
- **gold (ouro):**
  - números grandes da faixa de resumo;
  - filete de 3 px sob as faixas oliva da entrada e da revisão;
  - destaque do elemento selecionado no 3D, igual nos dois temas.
  - Em texto pequeno, usa-se `gold-text` sobre `gold-soft`: selos de lacuna, alerta de vínculo e aviso
    do 3D.
- **danger:** mensagens de erro, selo "repetido neste arquivo", "GUID repetido" na lista e selo
  "ambígua". Os selos usam `danger-soft` como fundo e `danger` como texto e borda.
- **band (oliva escuro):** faixa da entrada (eyebrow, título e resumo) e faixa da revisão (projeto e
  números).
- **sunken e muted:** botão desativado (fundo `sunken`, texto `muted`, sem opacidade), hover neutro de
  botões e da lista, e a seção de passos da entrada.
- **Decisões que não estavam no pedido:**
  - a borda de campo usa `muted`, porque `line` (1,3:1) não chega aos 3:1 exigidos para limite de
    componente;
  - o hover de botões e da lista é `sunken`, porque o `accent` do shadcn passou a ser o turquesa forte.

## Contraste (WCAG 2.1 AA)

O teste automatizado `frontend/tests/unit/contraste.test.ts` lê os tokens de `src/index.css` e
confere, nos temas claro e escuro, **20 pares de texto (≥ 4,5:1)** e **4 pares de borda e foco
(≥ 3:1)**. São 48 asserções, todas aprovadas.

| Par (frente / fundo) | Claro | Escuro |
|---|---|---|
| ink / bg | 16,1 | 15,4 |
| muted / sunken (botão desativado) | 6,2 | 5,5 |
| primary-ink / primary | 7,3 | 9,4 |
| accent / surface (link, foco) | 7,1 | 9,2 |
| accent / accent-soft (selecionado) | 6,7 | 5,7 |
| gold / band (números) | 7,4 | 10,1 |
| band-muted / band | 9,9 | 10,4 |
| gold-text / gold-soft | 7,0 | 9,9 |
| danger / danger-soft | 5,3 | 5,4 |

- **Fora do teste:** o destaque 3D em `gold` sobre o fundo do viewer claro (`#ebece6`) tem **1,58:1**.
  - É contraste de objeto na cena, não de texto, e a identificação nunca depende só dele: a lista
    marca o item com borda accent e o painel nomeia o elemento.
  - Mesmo assim, fica abaixo dos 3:1 de componente gráfico.
  - No escuro, o mesmo par dá 9,2:1.
  - Ver **Pendências**.
- **Foco visível:** anel `accent` sólido de 2 px com offset em botão, campo, switch, item da lista, alça
  de redimensionamento e envio de arquivo (o anel fica no rótulo, porque o input é `sr-only`).
- **Movimento:** não há movimento automático. Com `prefers-reduced-motion`, as transições vão a ~0.

## Fontes

As fontes são pacotes locais `@fontsource` importados no CSS, e o Vite as copia para `dist/assets/`.
No build, com CSP `font-src 'self'`, as três famílias carregam, com zero violações.

| Uso | Família | Pacote (versão exata) | Licença |
|---|---|---|---|
| Títulos | Barlow Condensed 600 | `@fontsource/barlow-condensed@5.3.0` (subconjunto latin) | SIL OFL 1.1 |
| Interface | IBM Plex Sans (variável, 100–700) | `@fontsource-variable/ibm-plex-sans@5.3.0` | SIL OFL 1.1 |
| Hashes, ids, express_id e medidas | IBM Plex Mono 400 | `@fontsource/ibm-plex-mono@5.3.0` (subconjunto latin) | SIL OFL 1.1 |

- **Maiúsculas:** títulos em maiúsculas na faixa da revisão (nome do projeto) e na entrada (título,
  cards e passos). O nome do elemento no detalhe usa Barlow com a grafia original.
- **Mono:** usada em `express_id`, GlobalId, revisões, chave, tamanho de arquivo e tempos do 3D. Os
  selos de disciplina (ARQ/EST) ficam na sans.
- **Instrument Serif e Instrument Sans foram removidas.** O `check:dist` agora:
  - aceita só as famílias do tema em `@font-face`;
  - exige que cada `url()` exista no próprio build.

## Telas

- **Entrada:**
  - faixa oliva com o eyebrow em texto, título em Barlow Condensed maiúsculo e resumo;
  - filete ouro de 3 px por baixo, no lugar da onda vinho;
  - o card "Novo projeto" fica centralizado em telas largas;
  - os três passos reais da tela (enviar, confirmar, revisar) ficam numa seção `sunken`, com números em
    `gold-text`.
- **Revisão:**
  - faixa oliva com filete ouro e nome do projeto;
  - quatro números em ouro com plural correto: "1 Ambígua", "2 Ambíguas". Zero e "—" ficam no plural;
  - linha clara com arquivo, revisão e IDS;
  - lista com seleção em `accent-soft` e borda `accent`;
  - fundo do viewer = `--viewer`;
  - destaque 3D em `--gold`.
- **Painel de detalhe:**
  - texto com `break-words`;
  - chave e revisão inteiras no DOM, truncadas com reticências, com `title` completo e botão copiar;
  - em painel estreito (< 20rem), rótulo sobre valor, para os selos `nowrap` não vazarem.

## Pendências

1. **Escolha visual** com Felipe e Nonato (§13.4). Concorrem as três propostas do plano, a LEPV e esta.
2. **Conferir os hex** com o manual de identidade visual do Exército e com a comunicação do IME.
3. **Destaque 3D em ouro sobre fundo claro (1,58:1).** Opções, sem decisão tomada:
   - contorno escuro no elemento destacado;
   - fundo do viewer claro mais escuro;
   - um ouro mais saturado só na cena.
4. O `<select>` de arquivo usa o controle nativo, com estilo do sistema no menu aberto.
5. A logo "That Open Company" no canto do viewer vem da biblioteca, não do tema.
