"""Mede, para cada modelo, se ele cabe 100% na GPU com num_ctx=2048 e quao rapido roda.

Usa o prompt real do projeto. Cada modelo e medido isolado: unload -> load ->
aquecimento -> medicoes -> unload.
"""

import json
import statistics
import sys
import time

import httpx

BASE = "http://localhost:11434"
NUM_CTX = 2048

SYSTEM = "Voce e um engenheiro BIM/IFC criterioso. Responda APENAS com JSON valido."
PROMPT = """issue_id: b061f0170db9
tipo: pset_missing
classe: IfcWall
guid: 3FPolghi
elemento: Parede Externa 01
pset_alvo: Pset_WallCommon
propriedade: FireRating
tipo_dado: String
classe_bsdd: IfcWall (https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall)
candidatos: REI 30, REI 60, REI 90, REI 120
instrucao: escolha entre os candidatos acima quando aplicavel.
camadas_material: Bloco ceramico 14cm (0.14 m); Reboco (0.025 m)
espessura_total_m: 0.165
is_external: True
floor: Pavimento 2

Retorne JSON: {"opcoes":[{"issue_id":"...","suggested_value":...,"confidence":"alta|media|baixa","justification":"<=120 chars","review_required":true|false}]}. Maximo 3 opcoes."""

OPTS = {
    "temperature": 0.1,
    "seed": 42,
    "top_p": 0.9,
    "repeat_penalty": 1.1,
    "num_predict": 1024,
    "num_ctx": NUM_CTX,
}


def unload(model: str) -> None:
    try:
        httpx.post(f"{BASE}/api/generate", json={"model": model, "prompt": "", "keep_alive": 0}, timeout=180)
    except Exception:
        pass


def estado(model: str) -> tuple[float, float, str]:
    """Retorna (tamanho_gb, pct_gpu, texto)."""
    try:
        for m in httpx.get(f"{BASE}/api/ps", timeout=10).json().get("models", []):
            if m.get("name") == model or m.get("model") == model:
                total, vram = m.get("size", 0), m.get("size_vram", 0)
                pct = 100 * vram / total if total else 0
                return total / 2**30, pct, f"{total/2**30:.2f} GB, {pct:.0f}% GPU"
    except Exception as exc:
        return 0.0, 0.0, f"(erro {exc})"
    return 0.0, 0.0, "(nao carregado)"


def chamada(model: str) -> tuple[float, str, int]:
    payload = {
        "model": model,
        "prompt": PROMPT,
        "system": SYSTEM,
        "stream": False,
        "think": False,
        "format": "json",
        "keep_alive": "5m",
        "options": OPTS,
    }
    t0 = time.perf_counter()
    r = httpx.post(f"{BASE}/api/generate", json=payload, timeout=900)
    r.raise_for_status()
    body = r.json()
    return time.perf_counter() - t0, body.get("response", ""), body.get("eval_count", 0)


def json_valido(texto: str) -> bool:
    try:
        d = json.loads(texto)
    except Exception:
        return False
    return isinstance(d, dict) and bool(d.get("opcoes"))


def testar(model: str, medicoes: int = 3) -> dict | None:
    unload(model)
    time.sleep(2)
    try:
        chamada(model)  # aquecimento / load
    except Exception as exc:
        print(f"  {model:44} ERRO: {type(exc).__name__}: {str(exc)[:60]}")
        return None
    gb, pct, txt = estado(model)
    tempos, validos, toks = [], 0, []
    for _ in range(medicoes):
        try:
            dt, resp, ec = chamada(model)
        except Exception as exc:
            print(f"  {model:44} ERRO na medicao: {type(exc).__name__}")
            unload(model)
            return None
        tempos.append(dt)
        toks.append(ec)
        validos += json_valido(resp)
    unload(model)
    return {
        "model": model,
        "gb": gb,
        "pct_gpu": pct,
        "estado": txt,
        "mediana_s": statistics.median(tempos),
        "json_ok": f"{validos}/{medicoes}",
        "tok": statistics.median(toks) if toks else 0,
    }


def main() -> int:
    modelos = sys.argv[1:]
    if not modelos:
        print("uso: testa_modelos.py <modelo> [modelo...]")
        return 1
    print(f"num_ctx = {NUM_CTX} | prompt = {len(PROMPT)} chars")
    print("=" * 100)
    print(f"{'modelo':40} {'GB':>6} {'GPU%':>6} {'mediana':>9} {'tok':>5} {'JSON':>6}")
    print("-" * 100)
    linhas = []
    for m in modelos:
        res = testar(m)
        if res:
            linhas.append(res)
            marca = "OK " if res["pct_gpu"] >= 99.5 else "!! "
            print(
                f"{marca}{res['model'][:38]:38} {res['gb']:6.2f} {res['pct_gpu']:6.0f} "
                f"{res['mediana_s']:8.2f}s {res['tok']:5.0f} {res['json_ok']:>6}"
            )
    print("-" * 100)
    cabem = [r for r in linhas if r["pct_gpu"] >= 99.5]
    print(f"cabem 100% na GPU com ctx {NUM_CTX}: {len(cabem)}/{len(linhas)}")
    if cabem:
        rapido = min(cabem, key=lambda r: r["mediana_s"])
        print(f"mais rapido entre os que cabem: {rapido['model']} ({rapido['mediana_s']:.2f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
