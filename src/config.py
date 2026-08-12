"""Configuracoes globais da aplicacao, carregadas do .env."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parent.parent
IDS_XSD_PATH = BASE_DIR / "data" / "ids_schema" / "ids.xsd"


class Settings(BaseSettings):
    """Configuracoes da aplicacao carregadas de variaveis de ambiente ou .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    ollama_url: str = Field(default="http://localhost:11434", description="URL base do servidor Ollama")
    ollama_model: str = Field(default="qwen3.5:9b", description="Modelo LLM usado no Ollama")
    ollama_temperature: float = Field(default=0.1, description="Temperatura de geracao")
    ollama_num_ctx: int = Field(
        default=8192,
        description="Teto da janela de contexto; só governa a política 'fit'",
    )
    ollama_num_ctx_policy: Literal["fit", "fixed"] = Field(
        default="fixed",
        description=(
            "Como a janela de contexto e escolhida. 'fixed' usa ollama_num_ctx_fixed "
            "em toda chamada; 'fit' dimensiona ao prompt, com ollama_num_ctx como teto."
        ),
    )
    ollama_num_ctx_fixed: int = Field(
        default=4096,
        description=(
            "Janela usada quando a politica e 'fixed'. Medido em 2026-08-12 sobre a "
            "rodada v7.5: a politica 'fit' alternava entre 2048 e 4096 ao longo da fila "
            "e o Ollama realoca o KV cache a cada troca — 400 recargas forcadas, "
            "+2,3 a +4,0 s de mediana cada, ~7% do tempo de fila. 4096 cobre o maior "
            "prompt do corpus (4.721 chars ~ 1.951 tokens) com folga."
        ),
    )
    ollama_num_predict: int = Field(
        default=768,
        description=(
            "Tokens maximos gerados por resposta. 768 da folga sobre a resposta mais longa "
            "observada no benchmark (mistral:7b, media de 557 tok/sugestao) e mantem o "
            "orcamento prompt+resposta dentro de uma janela de 2048, o que evita transbordo "
            "de VRAM nos modelos de 9B."
        ),
    )
    ollama_keep_alive: str = Field(default="15m", description="Tempo para manter o modelo carregado no Ollama")
    ollama_think: bool = Field(default=False, description="Habilita thinking em modelos compativeis")
    ollama_generate_timeout_seconds: float = Field(default=120.0, description="Timeout de geracao no Ollama")
    ollama_max_retries: int = Field(default=3, description="Numero maximo de tentativas no Ollama")
    ollama_retry_backoff_seconds: float = Field(default=1.0, description="Backoff base entre tentativas do Ollama")
    ollama_seed: int | None = Field(default=42, description="Seed determinista para o Ollama (None = aleatorio)")
    ollama_top_p: float = Field(default=0.9, description="Top-p para amostragem do Ollama")
    ollama_repeat_penalty: float = Field(default=1.1, description="Penalidade de repeticao do Ollama")
    suggestion_cache_enabled: bool = Field(default=True, description="Habilita cache persistente de sugestoes")
    suggestion_cache_path: str = Field(
        default="data/cache/suggestion_cache.db",
        description="Caminho do banco SQLite de cache de sugestoes",
    )
    max_concurrent_llm_calls: int = Field(default=1, description="Concorrencia maxima de chamadas LLM ativas")
    log_level: str = Field(default="DEBUG", description="Nivel de log")
    ifc_upload_dir: str = Field(default="./uploads", description="Diretorio para armazenar arquivos IFC enviados")
    bsdd_base_url: str = Field(default="https://api.bsdd.buildingsmart.org", description="URL base da API bSDD")
    bsdd_timeout_seconds: int = Field(default=10, description="Timeout das chamadas ao bSDD em segundos")
    bsdd_api_url: str = Field(default="https://api.bsdd.buildingsmart.org", description="URL da API bSDD")
    bsdd_cache_enabled: bool = Field(default=True, description="Habilita cache local para respostas do bSDD")
    bsdd_cache_path: str = Field(
        default="data/cache/bsdd_cache.json",
        description="Caminho do cache persistente local do bSDD",
    )
    post_validation_enabled: bool = Field(default=True, description="Habilita validacao pos-correcao")
    ids_xsd_path: str = Field(default="data/ids_schema/ids.xsd", description="Caminho do XSD oficial do IDS")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retorna a instancia singleton das configuracoes."""
    return Settings()
