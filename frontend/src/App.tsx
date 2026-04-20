import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api, type MeResponse } from "@/lib/api";
import { useTheme } from "@/lib/theme";
import { getWebApp, initTelegramWebApp, isInsideTelegram } from "@/lib/twa";
import Login from "@/pages/Login";
import AppShell from "@/pages/AppShell";
import { pageFade } from "@/lib/motion";

export default function App() {
  const initTheme = useTheme((s) => s.init);
  const [me, setMe] = useState<MeResponse | null>(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    initTheme();
  }, [initTheme]);

  useEffect(() => {
    void bootstrap();
    const onUnauth = () => setMe(null);
    window.addEventListener("auth:unauthorized", onUnauth);
    return () => window.removeEventListener("auth:unauthorized", onUnauth);
  }, []);

  async function bootstrap() {
    // Inside Telegram Mini App: apply theme + exchange initData for cookie.
    if (isInsideTelegram()) {
      initTelegramWebApp();
      const webApp = getWebApp();
      if (webApp?.initData) {
        try {
          await api.post("/api/auth/miniapp", { init_data: webApp.initData });
        } catch {
          // fall through — check /me; may still be anonymous
        }
      }
    } else {
      // Regular web: handle deep link from Bot: `?bot_token=...`
      const url = new URL(location.href);
      const botToken = url.searchParams.get("bot_token");
      if (botToken) {
        try {
          await api.post("/api/auth/bot_token", { bot_token: botToken });
        } catch {
          // ignore — fall through to /me check
        }
        url.searchParams.delete("bot_token");
        history.replaceState(null, "", url.toString());
      }
    }
    await check();
  }

  async function check() {
    try {
      const res = await api.get<MeResponse>("/api/auth/me");
      setMe(res);
    } catch {
      setMe(null);
    } finally {
      setReady(true);
    }
  }

  if (!ready) {
    return <div className="min-h-dvh grid place-items-center text-foreground-muted">讀取中…</div>;
  }

  return (
    <AnimatePresence mode="wait">
      {me ? (
        <motion.div
          key="shell"
          variants={pageFade}
          initial="hidden"
          animate="show"
          exit="exit"
          className="h-dvh"
        >
          <AppShell me={me} onLogout={() => setMe(null)} />
        </motion.div>
      ) : (
        <motion.div
          key="login"
          variants={pageFade}
          initial="hidden"
          animate="show"
          exit="exit"
        >
          <Login onLoggedIn={() => void check()} />
        </motion.div>
      )}
    </AnimatePresence>
  );
}
