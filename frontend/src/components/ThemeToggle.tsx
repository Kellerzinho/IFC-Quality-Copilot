import { Moon, Sun } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useTema } from "@/shared/theme";

/** Alterna claro/escuro; o rótulo diz o que o clique faz. */
export function ThemeToggle({ className }: { className?: string }) {
  const [tema, alternar] = useTema();
  const rotulo = tema === "escuro" ? "Usar tema claro" : "Usar tema escuro";
  return (
    <Button size="icon" variant="ghost" className={cn("size-8", className)} onClick={alternar} aria-label={rotulo} title={rotulo}>
      {tema === "escuro" ? <Sun aria-hidden /> : <Moon aria-hidden />}
    </Button>
  );
}
