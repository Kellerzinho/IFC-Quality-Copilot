import { useCallback, useState } from "react";

import { ProjectEntry } from "@/features/project/ProjectEntry";
import { ReviewWorkspace } from "@/features/review/ReviewWorkspace";
import { ThatOpenViewerAdapter } from "@/features/viewer/ThatOpenViewerAdapter";
import type { ViewerAdapter } from "@/features/viewer/ViewerPort";
import { api as apiPadrao, type Api } from "@/shared/api";
import type { Project } from "@/shared/types";

interface Props {
  api?: Api;
  createViewer?: () => ViewerAdapter;
  initialProject?: Project | null;
  initialView?: "entrada" | "revisao";
}

const viewerPadrao = () => new ThatOpenViewerAdapter();

export function App({ api = apiPadrao, createViewer = viewerPadrao, initialProject = null, initialView = "entrada" }: Props) {
  const [project, setProject] = useState<Project | null>(initialProject);
  const [view, setView] = useState(initialView);
  const voltar = useCallback(() => setView("entrada"), []);

  if (view === "revisao" && project) {
    return <ReviewWorkspace api={api} project={project} createViewer={createViewer} onVoltar={voltar} />;
  }
  return (
    <ProjectEntry
      api={api}
      project={project}
      onProjectChange={setProject}
      onCloseProject={() => setProject(null)}
      onOpenReview={() => setView("revisao")}
    />
  );
}
