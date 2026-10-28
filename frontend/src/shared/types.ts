// Aliases dos tipos gerados a partir do OpenAPI (src/shared/contracts.ts).
// Nenhum tipo de domínio é declarado à mão no frontend.
import type { components } from "./contracts";

type Schemas = components["schemas"];

export type ElementRef = Schemas["ElementRef"];
export type ElementRecord = Schemas["ElementRecord"];
export type ElementList = Schemas["ElementList"];
export type ModelPairBinding = Schemas["ModelPairBinding"];
export type Project = Schemas["Project"];
export type ProjectSummary = Schemas["ProjectSummary"];
export type ProjectList = Schemas["ProjectList"];
export type SourceArtifactRef = Schemas["SourceArtifactRef"];
export type Gap = Schemas["Gap"];
export type GapList = Schemas["GapList"];
export type ObservedValue = Schemas["ObservedValue"];
export type ApiError = Schemas["ApiError"];
export type Discipline = ModelPairBinding["discipline"];
