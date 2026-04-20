import { Moon, Sun, SunMoon } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useTheme } from "@/lib/theme";

export default function ThemeToggle() {
  const { choice, setChoice } = useTheme();
  const next = () => {
    setChoice(choice === "auto" ? "dark" : choice === "dark" ? "light" : "auto");
  };
  return (
    <Button variant="icon" size="icon" onClick={next} aria-label={`主題：${choice}`}>
      {choice === "auto" ? (
        <SunMoon className="w-5 h-5" />
      ) : choice === "dark" ? (
        <Moon className="w-5 h-5" />
      ) : (
        <Sun className="w-5 h-5" />
      )}
    </Button>
  );
}
