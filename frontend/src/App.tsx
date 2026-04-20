import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { api, type MeResponse } from "@/lib/api";
import { useTheme } from "@/lib/theme";
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
    void check();
    const onUnauth = () => setMe(null);
    window.addEventListener("auth:unauthorized", onUnauth);
    return () => window.removeEventListener("auth:unauthorized", onUnauth);
  }, []);

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
