"""Fontes da prospecção M7-09: arquitetura, licença e catálogo Ollama dos candidatos.

Cada número traz URL, data de acesso e status. ``fonte_primaria`` é o card ou o
``config.json`` do produtor; ``espelho_a_verificar`` é cópia de terceiros (o
repositório oficial exige login) e precisa ser conferida no original;
``catalogo_runtime`` é a página de tags do Ollama. Nada aqui foi medido: são
insumos da estimativa, não do hardware.
"""

from __future__ import annotations

from src.experiment.budget_v1.prospection import (
    ArchitectureSpec,
    Gate,
    OllamaTagInfo,
    SourcedValue,
)

SOURCES_ACCESSED_ON = "2026-10-12"

_HF = "https://huggingface.co"
_OLLAMA = "https://ollama.com/library"


def _primary(value: str | int | float, url: str, note: str | None = None) -> SourcedValue:
    """Valor lido na fonte primária do produtor na data de acesso."""
    return SourcedValue(
        value=value,
        status="fonte_primaria",
        source=url,
        accessed_on=SOURCES_ACCESSED_ON,
        note=note,
    )


def _mirror(value: str | int | float, url: str, note: str | None = None) -> SourcedValue:
    """Valor lido em espelho público; conferir no repositório oficial."""
    return SourcedValue(
        value=value,
        status="espelho_a_verificar",
        source=url,
        accessed_on=SOURCES_ACCESSED_ON,
        note=note,
    )


def _tag(tag: str, size_gb: float, context: str, family_page: str) -> OllamaTagInfo:
    """Tag publicada no catálogo do Ollama, com o tamanho exibido (GB decimais)."""
    return OllamaTagInfo(
        tag=tag,
        catalog_size_gb=size_gb,
        catalog_context=context,
        source=f"{_OLLAMA}/{family_page}/tags",
        accessed_on=SOURCES_ACCESSED_ON,
    )


_QWEN3_CTX_NOTE = "32.768 nativo; 131.072 com YaRN (card). config.json: 40.960"
_QWEN35_CTX_NOTE = "262.144 nativo; extensível a 1.010.000 (card)"
_LLAMACPP = "https://github.com/ggml-org/llama.cpp/blob/8f574b0ad44c"
_QWEN35_STATE_NOTE = (
    "Estado fixo por sequência das 24 camadas lineares, independente do contexto: "
    "n_embd_s = ssm_d_state x ssm_d_inner = 128 x 4096 e n_embd_r (conv) = "
    "(d_conv-1) x (ssm_d_inner + 2 x n_group x ssm_d_state) = 3 x 8192, em float32 "
    "(recurrent_type_r/s = GGML_TYPE_F32 em src/llama-model.cpp): "
    "24 x (524288 + 24576) x 4 B = 52.690.944 B = 0,049 GiB. Fórmulas e tipo em "
    "src/llama-hparams.cpp e src/llama-model.cpp do llama.cpp; dimensões do config.json "
    "(linear_key_head_dim=128, linear_num_value_heads x linear_value_head_dim=4096, "
    "linear_num_key_heads=16, linear_conv_kernel_dim=4). A verificar: o mapeamento "
    "config -> hparams no GGUF e se o runtime do Ollama 0.40.3 aloca igual ao llama.cpp"
)


def _recurrent_state(model: str) -> SourcedValue:
    """Estado recorrente das camadas lineares do Qwen3.5 (constante no contexto)."""
    return SourcedValue(
        value=0.049,
        status="derivado",
        source=(
            f"{_HF}/Qwen/{model}/raw/main/config.json; "
            f"{_LLAMACPP}/src/llama-hparams.cpp; {_LLAMACPP}/src/llama-model.cpp"
        ),
        accessed_on=SOURCES_ACCESSED_ON,
        note=_QWEN35_STATE_NOTE,
    )


# Revisão (commit) do repositório Hugging Face na data de acesso e SHA-256 do
# arquivo LICENSE baixado. A revisão é a do upstream, não a do GGUF do Ollama.
_QWEN_LICENSE_EVIDENCE: dict[str, tuple[str, str]] = {
    "Qwen3-4B": ("1cfa9a720891", "832dd9e00a68dd83"),
    "Qwen3-8B": ("b968826d9c46", "832dd9e00a68dd83"),
    "Qwen3.5-4B": ("851bf6e806ef", "bbedc3fda3305820"),
    "Qwen3.5-9B": ("c20223623576", "bbedc3fda3305820"),
}


def _qwen_license(model: str) -> SourcedValue:
    """Licença Qwen conferida no LICENSE oficial e no metadado do card."""
    revision, digest = _QWEN_LICENSE_EVIDENCE[model]
    return SourcedValue(
        value="apache-2.0",
        status="fonte_primaria",
        source=f"{_HF}/Qwen/{model}/blob/{revision}/LICENSE",
        accessed_on=SOURCES_ACCESSED_ON,
        note=(
            f"Apache License 2.0 no arquivo LICENSE (SHA-256 {digest}...) e "
            f"cardData.license=apache-2.0 na revisão {revision}"
        ),
    )


def _qwen_gate(model: str) -> Gate:
    """Gate de licença Qwen: texto Apache 2.0 sem cláusula de campo de uso."""
    return Gate(
        kind="licenca",
        status="sem_restricao_identificada",
        summary=(
            "Apache 2.0 confirmada no LICENSE oficial; o texto não tem cláusula de "
            "restrição por campo de uso (militar, defesa ou outro)"
        ),
        sources=[_qwen_license(model)],
    )


_LLAMA_REPO = "https://github.com/meta-llama/llama-models/blob"
_LLAMA_MILITARY_SUMMARY = (
    "bloqueio potencial: uso militar — decisão do orientador (Cel Giuseppe). "
    "A licença incorpora por referência a Acceptable Use Policy, que lista entre os "
    "usos proibidos atividades 'related to ... Military, warfare, nuclear industries "
    "or applications, espionage' e as sujeitas ao ITAR. Candidato mantido e "
    "condicionado por licença; este registro não conclui se pode ou não ser usado"
)
_LLAMA_DEAD_LINK = (
    "A URL da política citada no próprio LICENSE redireciona para "
    "developer.meta.com e termina em 404 em 2026-10-12; o texto usado é o do "
    "repositório oficial meta-llama/llama-models"
)


def _llama_license(version: str, commit: str, release: str) -> SourcedValue:
    """Licença Llama lida no repositório oficial da Meta, fixada no commit."""
    folder = f"llama{version.replace('.', '_')}"
    return SourcedValue(
        value=f"Llama {version} Community License",
        status="fonte_primaria",
        source=f"{_LLAMA_REPO}/{commit}/models/{folder}/LICENSE",
        accessed_on=SOURCES_ACCESSED_ON,
        note=(
            f"Version Release Date: {release}. §1.b.iv incorpora a Acceptable Use Policy; "
            "§2 exige licença da Meta acima de 700 milhões de usuários ativos mensais"
        ),
    )


def _llama_gate(version: str, commit: str, release: str, item: str, quote: str) -> Gate:
    """Gate de licença Llama: restrição militar na AUP vai para decisão do orientador."""
    folder = f"llama{version.replace('.', '_')}"
    return Gate(
        kind="licenca",
        status="condicionado",
        summary=_LLAMA_MILITARY_SUMMARY,
        decision_owner="orientador (Cel Giuseppe)",
        sources=[
            _llama_license(version, commit, release),
            SourcedValue(
                value=f"Llama {version} Acceptable Use Policy, {item}",
                status="fonte_primaria",
                source=f"{_LLAMA_REPO}/{commit}/models/{folder}/USE_POLICY.md",
                accessed_on=SOURCES_ACCESSED_ON,
                note=f"Texto: {quote}. {_LLAMA_DEAD_LINK}",
            ),
        ],
    )


_LLAMA31_GATE_ARGS = (
    "3.1",
    "1f0feb795a41",
    "July 23, 2024",
    "Prohibited Uses, item 2, primeiro subitem",
    "'Engage in, promote, incite, facilitate, or assist in the planning or development "
    "of activities that present a risk of death or bodily harm to individuals, including "
    "use of Llama 3.1 related to the following: Military, warfare, nuclear industries or "
    "applications, espionage, use for materials or activities that are subject to the "
    "International Traffic Arms Regulations (ITAR) ...'",
)
_LLAMA32_GATE_ARGS = (
    "3.2",
    "8d29d93fa570",
    "September 25, 2024",
    "Prohibited Uses, item 2, subitem 8",
    "'Engage in, promote, incite, facilitate, or assist in the planning or development "
    "of activities that present a risk of death or bodily harm to individuals, including "
    "use of Llama 3.2 related to the following: 8. Military, warfare, nuclear industries "
    "or applications, espionage, use for materials or activities that are subject to the "
    "International Traffic Arms Regulations (ITAR) ...'",
)

CANDIDATES: tuple[ArchitectureSpec, ...] = (
    ArchitectureSpec(
        family="Qwen3",
        model="Qwen3-4B",
        params_billion=_primary(4.0, f"{_HF}/Qwen/Qwen3-4B", "3,6B sem embeddings"),
        kv_layers=_primary(36, f"{_HF}/Qwen/Qwen3-4B/raw/main/config.json"),
        kv_heads=_primary(8, f"{_HF}/Qwen/Qwen3-4B/raw/main/config.json"),
        head_dim=_primary(128, f"{_HF}/Qwen/Qwen3-4B/raw/main/config.json"),
        context_advertised=_primary(32768, f"{_HF}/Qwen/Qwen3-4B", _QWEN3_CTX_NOTE),
        license=_qwen_license("Qwen3-4B"),
        license_gate=_qwen_gate("Qwen3-4B"),
        ollama_tags={
            "Q8_0": _tag("qwen3:4b-q8_0", 4.4, "40K", "qwen3"),
            "Q5_K_M": None,
            "Q4_K_M": _tag("qwen3:4b-q4_K_M", 2.6, "40K", "qwen3"),
            "Q3_K_M": None,
        },
        notes=[
            "A tag padrão qwen3:4b (2,5 GB, 256K) não é a mesma de qwen3:4b-q4_K_M "
            "(2,6 GB, 40K): aponta para outro checkpoint. Usar a tag explícita; "
            "conferir o digest antes de qualquer ensaio.",
        ],
    ),
    ArchitectureSpec(
        family="Qwen3",
        model="Qwen3-8B",
        params_billion=_primary(8.2, f"{_HF}/Qwen/Qwen3-8B", "6,95B sem embeddings"),
        kv_layers=_primary(36, f"{_HF}/Qwen/Qwen3-8B/raw/main/config.json"),
        kv_heads=_primary(8, f"{_HF}/Qwen/Qwen3-8B/raw/main/config.json"),
        head_dim=_primary(128, f"{_HF}/Qwen/Qwen3-8B/raw/main/config.json"),
        context_advertised=_primary(32768, f"{_HF}/Qwen/Qwen3-8B", _QWEN3_CTX_NOTE),
        license=_qwen_license("Qwen3-8B"),
        license_gate=_qwen_gate("Qwen3-8B"),
        ollama_tags={
            "Q8_0": _tag("qwen3:8b-q8_0", 8.9, "40K", "qwen3"),
            "Q5_K_M": None,
            "Q4_K_M": _tag("qwen3:8b-q4_K_M", 5.2, "40K", "qwen3"),
            "Q3_K_M": None,
        },
    ),
    ArchitectureSpec(
        family="Qwen3.5",
        model="Qwen3.5-4B",
        params_billion=_primary(
            4.0,
            f"{_HF}/Qwen/Qwen3.5-4B",
            "card: 4B; metadado safetensors: 5B (inclui encoder de visão/MTP, a verificar)",
        ),
        kv_layers=_primary(
            8,
            f"{_HF}/Qwen/Qwen3.5-4B/raw/main/config.json",
            "32 camadas, das quais 8 full_attention (full_attention_interval=4); "
            "as 24 lineares não têm KV por token",
        ),
        kv_heads=_primary(4, f"{_HF}/Qwen/Qwen3.5-4B/raw/main/config.json"),
        head_dim=_primary(256, f"{_HF}/Qwen/Qwen3.5-4B/raw/main/config.json"),
        recurrent_state_gib=_recurrent_state("Qwen3.5-4B"),
        context_advertised=_primary(262144, f"{_HF}/Qwen/Qwen3.5-4B", _QWEN35_CTX_NOTE),
        license=_qwen_license("Qwen3.5-4B"),
        license_gate=_qwen_gate("Qwen3.5-4B"),
        ollama_tags={
            "Q8_0": _tag("qwen3.5:4b-q8_0", 5.2, "256K", "qwen3.5"),
            "Q5_K_M": None,
            "Q4_K_M": _tag("qwen3.5:4b-q4_K_M", 3.3, "256K", "qwen3.5"),
            "Q3_K_M": None,
        },
        notes=[
            "Modelo multimodal (encoder de visão de 27 blocos); o tamanho do catálogo "
            "inclui partes que o MVP textual não usa.",
        ],
    ),
    ArchitectureSpec(
        family="Qwen3.5",
        model="Qwen3.5-9B",
        params_billion=_primary(
            9.0,
            f"{_HF}/Qwen/Qwen3.5-9B",
            "card: 9B; metadado safetensors: 10B (inclui encoder de visão/MTP, a verificar)",
        ),
        kv_layers=_primary(
            8,
            f"{_HF}/Qwen/Qwen3.5-9B/raw/main/config.json",
            "32 camadas, das quais 8 full_attention (full_attention_interval=4)",
        ),
        kv_heads=_primary(4, f"{_HF}/Qwen/Qwen3.5-9B/raw/main/config.json"),
        head_dim=_primary(256, f"{_HF}/Qwen/Qwen3.5-9B/raw/main/config.json"),
        recurrent_state_gib=_recurrent_state("Qwen3.5-9B"),
        context_advertised=_primary(262144, f"{_HF}/Qwen/Qwen3.5-9B", _QWEN35_CTX_NOTE),
        license=_qwen_license("Qwen3.5-9B"),
        license_gate=_qwen_gate("Qwen3.5-9B"),
        ollama_tags={
            "Q8_0": _tag("qwen3.5:9b-q8_0", 10.0, "256K", "qwen3.5"),
            "Q5_K_M": None,
            "Q4_K_M": _tag("qwen3.5:9b-q4_K_M", 6.6, "256K", "qwen3.5"),
            "Q3_K_M": None,
        },
        notes=[
            "Default atual do repositório (src/config.py: qwen3.5:9b).",
            "Modelo multimodal (encoder de visão de 27 blocos); o tamanho do catálogo "
            "inclui partes que o MVP textual não usa.",
        ],
    ),
    ArchitectureSpec(
        family="Llama 3.x",
        model="Llama-3.2-3B-Instruct",
        params_billion=_primary(3.21, f"{_HF}/meta-llama/Llama-3.2-3B-Instruct"),
        kv_layers=_mirror(28, f"{_HF}/unsloth/Llama-3.2-3B-Instruct/raw/main/config.json"),
        kv_heads=_mirror(8, f"{_HF}/unsloth/Llama-3.2-3B-Instruct/raw/main/config.json"),
        head_dim=_mirror(128, f"{_HF}/unsloth/Llama-3.2-3B-Instruct/raw/main/config.json"),
        context_advertised=_primary(131072, f"{_HF}/meta-llama/Llama-3.2-3B-Instruct"),
        license=_llama_license(*_LLAMA32_GATE_ARGS[:3]),
        license_gate=_llama_gate(*_LLAMA32_GATE_ARGS),
        ollama_tags={
            "Q8_0": _tag("llama3.2:3b-instruct-q8_0", 3.4, "128K", "llama3.2"),
            "Q5_K_M": _tag("llama3.2:3b-instruct-q5_K_M", 2.3, "128K", "llama3.2"),
            "Q4_K_M": _tag("llama3.2:3b-instruct-q4_K_M", 2.0, "128K", "llama3.2"),
            "Q3_K_M": _tag("llama3.2:3b-instruct-q3_K_M", 1.7, "128K", "llama3.2"),
        },
        notes=[
            "Arquitetura lida no espelho unsloth: o config.json oficial da Meta exige "
            "login no Hugging Face.",
        ],
    ),
    ArchitectureSpec(
        family="Llama 3.x",
        model="Llama-3.1-8B-Instruct",
        params_billion=_primary(8.0, f"{_HF}/meta-llama/Llama-3.1-8B-Instruct", "card: 8B"),
        kv_layers=_mirror(32, f"{_HF}/unsloth/Meta-Llama-3.1-8B-Instruct/raw/main/config.json"),
        kv_heads=_mirror(8, f"{_HF}/unsloth/Meta-Llama-3.1-8B-Instruct/raw/main/config.json"),
        head_dim=_mirror(128, f"{_HF}/unsloth/Meta-Llama-3.1-8B-Instruct/raw/main/config.json"),
        context_advertised=_primary(131072, f"{_HF}/meta-llama/Llama-3.1-8B-Instruct"),
        license=_llama_license(*_LLAMA31_GATE_ARGS[:3]),
        license_gate=_llama_gate(*_LLAMA31_GATE_ARGS),
        ollama_tags={
            "Q8_0": _tag("llama3.1:8b-instruct-q8_0", 8.5, "128K", "llama3.1"),
            "Q5_K_M": _tag("llama3.1:8b-instruct-q5_K_M", 5.7, "128K", "llama3.1"),
            "Q4_K_M": _tag("llama3.1:8b-instruct-q4_K_M", 4.9, "128K", "llama3.1"),
            "Q3_K_M": _tag("llama3.1:8b-instruct-q3_K_M", 4.0, "128K", "llama3.1"),
        },
        notes=[
            "Llama 3.2 e 3.1 são gerações vizinhas, não a mesma: o par mede "
            "tamanho e geração juntos.",
            "Arquitetura lida no espelho unsloth: o config.json oficial da Meta exige "
            "login no Hugging Face.",
        ],
    ),
)
