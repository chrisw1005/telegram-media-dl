import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Download, LogOut, Settings as SettingsIcon } from "lucide-react";
import { api, type MeResponse } from "@/lib/api";
import { Button } from "@/components/ui/button";
import ChatsSidebar from "@/pages/ChatsSidebar";
import ChatMedia from "@/pages/ChatMedia";
import DownloadsSheet from "@/pages/DownloadsSheet";
import SettingsSheet from "@/pages/SettingsSheet";
import ThemeToggle from "@/components/ThemeToggle";
import { useDownloadStore } from "@/stores/downloads";

export default function AppShell({ me, onLogout }: { me: MeResponse; onLogout: () => void }) {
  const [selectedChat, setSelectedChat] = useState<number | null>(null);
  const [downloadsOpen, setDownloadsOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  const activeCount = useDownloadStore((s) => s.activeCount);
  const connect = useDownloadStore((s) => s.connect);
  const disconnect = useDownloadStore((s) => s.disconnect);

  useEffect(() => {
    connect();
    return () => disconnect();
  }, [connect, disconnect]);

  async function logout() {
    try {
      await api.post("/api/auth/logout");
    } finally {
      onLogout();
    }
  }

  return (
    <div className="flex h-dvh overflow-hidden bg-bg-base">
      <aside className="w-80 border-r border-border flex flex-col bg-bg-elevated">
        <header className="h-14 px-4 flex items-center justify-between border-b border-border">
          <h1 className="text-sm font-semibold tracking-tight">Telegram Media</h1>
          <div className="flex items-center gap-1">
            <ThemeToggle />
            <Button
              variant="icon"
              size="icon"
              onClick={() => setDownloadsOpen(true)}
              aria-label="下載佇列"
            >
              <div className="relative">
                <Download aria-hidden="true" className="w-5 h-5" />
                <AnimatePresence>
                  {activeCount > 0 && (
                    <motion.span
                      key={activeCount}
                      initial={{ scale: 0, opacity: 0 }}
                      animate={{
                        scale: 1,
                        opacity: 1,
                        transition: { type: "spring", damping: 12, stiffness: 280 },
                      }}
                      exit={{ scale: 0, opacity: 0 }}
                      className="absolute -top-1 -right-1 min-w-4 h-4 px-1 rounded-full bg-primary text-white text-[10px] font-semibold grid place-items-center"
                    >
                      {activeCount}
                    </motion.span>
                  )}
                </AnimatePresence>
              </div>
            </Button>
            <Button
              variant="icon"
              size="icon"
              onClick={() => setSettingsOpen(true)}
              aria-label="設定"
            >
              <SettingsIcon aria-hidden="true" className="w-5 h-5" />
            </Button>
            <Button variant="icon" size="icon" onClick={() => void logout()} aria-label="登出">
              <LogOut aria-hidden="true" className="w-5 h-5" />
            </Button>
          </div>
        </header>
        <ChatsSidebar selected={selectedChat} onSelect={setSelectedChat} />
      </aside>

      <main className="flex-1 overflow-hidden">
        <AnimatePresence mode="wait">
          {selectedChat != null ? (
            <motion.div
              key={selectedChat}
              initial={{ opacity: 0 }}
              animate={{ opacity: 1, transition: { duration: 0.2 } }}
              exit={{ opacity: 0, transition: { duration: 0.1 } }}
              className="h-full"
            >
              <ChatMedia chatId={selectedChat} />
            </motion.div>
          ) : (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              className="h-full grid place-items-center text-foreground-muted text-sm"
            >
              從左側選擇一個聊天以開始瀏覽媒體
            </motion.div>
          )}
        </AnimatePresence>
      </main>

      <DownloadsSheet open={downloadsOpen} onClose={() => setDownloadsOpen(false)} />
      <SettingsSheet
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        me={me}
      />
    </div>
  );
}
