# Fixtures bSDD — SINTÉTICAS

`synthetic-dictionary-v1.json` foi escrita para os testes da E4 (22/10/2026) a partir do
template oficial do modelo de importação JSON 2.0 do bSDD ([documentação oficial](https://github.com/buildingSMART/bSDD)).
Organização `ifcqc-teste`, códigos `syn-*` e textos são inventados; nenhum dado vem de
dicionário real, do bSDD publicado ou de qualquer dicionário de projeto. A
URI `.../ifc/4.3/prop/FireRating` aparece só como **referência externa** a ser mantida
pendente: o importador não a resolve nem baixa.

Cobre: enum textual com `Code` ≠ `Value`, códigos `"01"` que não viram inteiro, booleano,
inteiro, real com várias unidades e dimensão (não projetável), `Time` (não projetável),
restrição numérica com zero (não projetável), enum numérico (não projetável), campo
desconhecido preservado, restrição de classe mais estreita que a global e `IsRequired`
falso. Os testes derivam variantes negativas em `tmp_path`.
