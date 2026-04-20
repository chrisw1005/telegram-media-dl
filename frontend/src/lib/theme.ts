import { create } from "zustand";

type ThemeChoice = "auto" | "light" | "dark";

interface ThemeState {
  choice: ThemeChoice;
  effective: "light" | "dark";
  setChoice: (c: ThemeChoice) => void;
  init: () => void;
}

const STORAGE_KEY = "tgmedia-theme";

function detectSystem(): "light" | "dark" {
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

function apply(effective: "light" | "dark") {
  const root = document.documentElement;
  if (effective === "light") root.classList.add("light");
  else root.classList.remove("light");
}

export const useTheme = create<ThemeState>((set, get) => ({
  choice: (localStorage.getItem(STORAGE_KEY) as ThemeChoice) || "auto",
  effective: "dark",
  setChoice: (c) => {
    localStorage.setItem(STORAGE_KEY, c);
    const effective = c === "auto" ? detectSystem() : c;
    apply(effective);
    set({ choice: c, effective });
  },
  init: () => {
    const choice = get().choice;
    const effective = choice === "auto" ? detectSystem() : choice;
    apply(effective);
    set({ effective });
    if (choice === "auto") {
      window
        .matchMedia("(prefers-color-scheme: dark)")
        .addEventListener("change", (ev) => {
          const e = ev.matches ? "dark" : "light";
          apply(e);
          set({ effective: e });
        });
    }
  },
}));
