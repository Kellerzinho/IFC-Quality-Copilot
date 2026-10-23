import { createRoot } from "react-dom/client";

import { App } from "@/app/App";
import { iniciarTema } from "@/shared/theme";

import "./index.css";

iniciarTema();
// Sem StrictMode: o viewer WebGL é montado uma vez por adaptador.
createRoot(document.getElementById("root")!).render(<App />);
