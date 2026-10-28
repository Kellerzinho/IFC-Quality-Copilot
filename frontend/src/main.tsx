import { createRoot } from "react-dom/client";

import { App } from "@/app/App";

import "./index.css";

// Sem StrictMode: o viewer WebGL é montado uma vez por adaptador.
createRoot(document.getElementById("root")!).render(<App />);
