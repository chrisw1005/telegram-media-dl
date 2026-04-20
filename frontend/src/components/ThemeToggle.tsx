import { Moon, Sun, SunMoon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";

export default function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  const next = () => {
    setChoice(choice === "auto" ? "dark" : choice === "dark" ? "light" : "auto");
  };
  const label =
    choice === "auto" ? "切換主題（目前：自動）" : choice === "dark" ? "切換主題（目前：深色）" : "切換主題（目前：明亮）";
  return (
    <Button variant="icon" size="icon" onClick={next} aria-label={label}>
      {choice === "auto" ? (
        <SunMoon aria-hidden="true" className="w-5 h-5" />
      ) : choice === "dark" ? (
        <Moon aria-hidden="true" className="w-5 h-5" />
      ) : (
        <Sun aria-hidden="true" className="w-5 h-5" />
      )}
    </Button>
  );
}
