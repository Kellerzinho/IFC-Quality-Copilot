# Operação e recuperação local do catálogo

A área possui banco SQLite em `db/operations.sqlite3` e armazenamento de artefatos em `a/`. Estado, evento e recibo compartilham a autoridade de persistência. O propósito `operational` ou `synthetic_test` é fixado no nascimento; release sintética não é adotada em banco operacional. Releases e fontes retidas são imutáveis; revisões de rascunho e análise têm avanço por comparação de revisão.

## Provisionar a área no servidor

Escolha uma pasta nova, exclusiva desta instalação. No runtime do projeto, substitua o marcador por esse caminho:

```powershell
uv run python -c "from pathlib import Path; from src.domain_catalog.workspace import open_components; open_components(Path(r'<AREA_NOVA>'), purpose='operational')"
$env:IFCQC_CATALOG_ROOT = '<AREA_NOVA>'
uv run streamlit run src/ui/app.py
```

O provisionamento apenas inicializa a autoridade/diretórios existentes. Não semeia dados, não publica, não adota e não autentica. A UI exige banco já existente e nunca aceita caminho do navegador. Para ensaio, prefira o modo de simulação sintética; não provisione sobre pasta de outra instalação.

## Primeiro catálogo

Abra a página do catálogo, selecione a área autorizada e declare o ator local. Em área vazia, use o formulário inicial para criar rascunho vazio ou importar bytes de `candidates.json` do staging. O parser exige JSON/UTF-8 válido, limite de 8 MiB e contratos consistentes; lifecycle já aprovado é recusado. O namespace é provisório. Criar/importar não aprova, publica ou escreve IFC.

## Aprovação e adoção

Revise o candidato exato antes de aprovar e publicar, com justificativa e hash. A publicação não muda pins. Prepare e confira o plano de atualização do projeto, seu hash e os impactos; confirmar cria nova análise para os pares ativos. Alteração de entrada, revisão ou plano invalida o comando esperado. Não copie aprovações de outra análise.

## Interrupção e recuperação

Preserve a pasta e os recibos ao ocorrer falha. Consulte o estado do comando antes de repetir a operação. Reutilize a mesma chave e payload para recuperar um recibo; mudar payload com a mesma chave é conflito. Operações de publicação distinguem preparo, pacote final, quarentena e finalização; use os serviços de recuperação, sem editar tabelas ou mover artefatos manualmente.

A cópia consistente usa `src.operations.backup` e o serviço da UI; inclui banco e artefatos referenciados, com manifesto e hashes. Não trate cópia do arquivo SQLite isolado durante escrita como backup completo. Restaure primeiro em diretório vazio e isolado; verifique integridade, propósito e referências antes de qualquer uso. Restore não publica um catálogo, não autentica atores e não aprova IFC.

Rollback de adoção é um novo plano explícito para release anterior, com nova análise; não apaga histórico nem reaproveita aprovações. Preserve também o backup anterior à operação.

## Alcance comprovado

Os testes de interrupção, backup, restauração isolada e rollback usam dados sintéticos. O recorte é disco local e um processo por área; não certifica pasta de rede, multiusuário institucional, queda física de energia, retenção ou políticas M6. Consulte os resultados integrados no relatório de validação. Aceite operacional humano permanece separado.
