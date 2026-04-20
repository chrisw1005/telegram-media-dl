/**
 * Telegram Mini App (Web App) integration.
 *
 * Detects whether we are running inside a Telegram client's WebView, reads
 * `initData` (signed by the bot), and syncs Telegram's `themeParams` to our
 * CSS variables so the Mini App matches the user's Telegram theme.
 *
 * Docs: https://core.telegram.org/bots/webapps
 */

interface TgThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
  section_bg_color?: string;
  accent_text_color?: string;
  destructive_text_color?: string;
}

interface TgWebApp {
  initData: string;
  initDataUnsafe: { user?: { id: number; username?: string } };
  colorScheme: "light" | "dark";
  themeParams: TgThemeParams;
  viewportHeight: number;
  viewportStableHeight: number;
  isExpanded: boolean;
  platform: string;
  version: string;
  ready(): void;
  expand(): void;
  close(): void;
  BackButton: { show(): void; hide(): void; onClick(cb: () => void): void };
  MainButton: {
    show(): void;
    hide(): void;
    setText(text: string): void;
    onClick(cb: () => void): void;
  };
  onEvent(name: string, cb: () => void): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp?: TgWebApp };
  }
}

export function getWebApp(): TgWebApp | null {
  return window.Telegram?.WebApp ?? null;
}

export function isInsideTelegram(): boolean {
  const w = getWebApp();
  return Boolean(w && w.initData && w.initData.length > 0);
}

function hexToRgbString(hex: string): string | null {
  const cleaned = hex.replace(/^#/, "").trim();
  if (cleaned.length !== 6) return null;
  const r = parseInt(cleaned.slice(0, 2), 16);
  const g = parseInt(cleaned.slice(2, 4), 16);
  const b = parseInt(cleaned.slice(4, 6), 16);
  if ([r, g, b].some(Number.isNaN)) return null;
  return `${r} ${g} ${b}`;
}

export function applyTelegramTheme(): void {
  const w = getWebApp();
  if (!w) return;
  const root = document.documentElement;
  const tp = w.themeParams;

  if (w.colorScheme === "light") {
    root.classList.add("light");
  } else {
    root.classList.remove("light");
  }

  const set = (cssVar: string, hex?: string) => {
    if (!hex) return;
    const rgb = hexToRgbString(hex);
    if (rgb) root.style.setProperty(cssVar, rgb);
  };
  set("--bg-base", tp.bg_color);
  set("--bg-elevated", tp.secondary_bg_color || tp.section_bg_color || tp.bg_color);
  set("--bg-card", tp.section_bg_color || tp.secondary_bg_color || tp.bg_color);
  set("--foreground", tp.text_color);
  set("--foreground-muted", tp.hint_color);
  set("--primary", tp.button_color || tp.link_color);
  set("--destructive", tp.destructive_text_color);
  set("--ring", tp.button_color || tp.link_color);
}

export function initTelegramWebApp(): TgWebApp | null {
  const w = getWebApp();
  if (!w) return null;
  w.ready();
  w.expand();
  applyTelegramTheme();
  w.onEvent("themeChanged", applyTelegramTheme);
  return w;
}
