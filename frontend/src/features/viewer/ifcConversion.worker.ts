/// <reference lib="webworker" />
// Conversão IFC → Fragments fora da thread principal, para a lista e o painel
// continuarem responsivos durante a carga. WASM servido localmente (/viewer/).
// COORDINATE_TO_ORIGIN desligado: cada modelo fica nas coordenadas do próprio IFC,
// sem deslocamento por modelo (federação independente da ordem de carga).
import { IfcImporter } from "@thatopen/fragments";

interface Pedido {
  id: number;
  bytes: Uint8Array;
  wasmPath: string;
}

self.onmessage = async (event: MessageEvent<Pedido>) => {
  const { id, bytes, wasmPath } = event.data;
  try {
    const importer = new IfcImporter();
    importer.wasm = { absolute: true, path: wasmPath };
    importer.webIfcSettings = { COORDINATE_TO_ORIGIN: false };
    const saida = await importer.process({ bytes });
    (self as unknown as DedicatedWorkerGlobalScope).postMessage({ id, ok: true, bytes: saida }, [saida.buffer]);
  } catch (erro) {
    const mensagem = erro instanceof Error ? erro.message : String(erro);
    (self as unknown as DedicatedWorkerGlobalScope).postMessage({ id, ok: false, mensagem });
  }
};
