import { useMemo, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useVirtualizer } from "@tanstack/react-virtual";
import { motion } from "framer-motion";
import { Megaphone, Search, User, Users } from "lucide-react";
import { api, type ChatItem } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { cn } from "@/lib/cn";

export default function ChatsSidebar({
  selected,
  onSelect,
}: {
  selected: number | null;
  onSelect: (id: number | null) => void;
}) {
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery<ChatItem[]>({
    queryKey: ["chats"],
    queryFn: () => api.get<ChatItem[]>("/api/chats?limit=200"),
  });

  const filtered = useMemo(() => {
    if (!data) return [];
    if (!q.trim()) return data;
    const needle = q.trim().toLowerCase();
    return data.filter(
      (c) =>
        c.title.toLowerCase().includes(needle) ||
        (c.username || "").toLowerCase().includes(needle),
    );
  }, [data, q]);

  const parentRef = useRef<HTMLDivElement>(null);
  const rowVirtualizer = useVirtualizer({
    count: filtered.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => 64,
    overscan: 8,
  });

  return (
    <div className="flex flex-col flex-1 min-h-0">
      <div className="px-3 py-2 border-b border-border">
        <div className="relative">
          <Search
            aria-hidden="true"
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-foreground-muted"
          />
          <Input
            type="search"
            name="chat-search"
            autoComplete="off"
            spellCheck={false}
            aria-label="搜尋聊天"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="搜尋聊天…"
            className="pl-9 h-9"
          />
        </div>
      </div>

      <div ref={parentRef} className="flex-1 overflow-y-auto scrollbar-slim">
        {isLoading && (
          <div className="p-3 space-y-2">
            {Array.from({ length: 10 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        )}
        {!isLoading && (
          <div style={{ height: rowVirtualizer.getTotalSize(), position: "relative" }}>
            {rowVirtualizer.getVirtualItems().map((v) => {
              const chat = filtered[v.index];
              const active = chat.id === selected;
              return (
                <motion.button
                  key={chat.id}
                  type="button"
                  aria-current={active ? "true" : undefined}
                  style={{
                    position: "absolute",
                    top: 0,
                    left: 0,
                    width: "100%",
                    transform: `translateY(${v.start}px)`,
                    height: v.size,
                  }}
                  onClick={() => onSelect(chat.id)}
                  className={cn(
                    "flex items-center gap-3 px-3 text-left transition-colors duration-fast",
                    "hover:bg-[rgb(var(--surface-hover-rgb)/0.06)]",
                    active && "bg-[rgb(var(--primary)/0.1)]",
                  )}
                >
                  <div className="relative w-10 h-10 shrink-0 rounded-full bg-primary/20 grid place-items-center">
                    <KindIcon kind={chat.kind} />
                    {active && (
                      <motion.span
                        layoutId="active-indicator"
                        className="absolute left-0 top-0 w-0.5 h-full bg-primary -ml-3"
                        transition={{ type: "spring", damping: 26, stiffness: 280 }}
                      />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="truncate font-medium text-sm">{chat.title}</span>
                      {chat.unread_count > 0 && (
                        <span className="shrink-0 min-w-5 h-5 px-1.5 rounded-full bg-primary text-white text-xs font-semibold grid place-items-center">
                          {chat.unread_count > 99 ? "99+" : chat.unread_count}
                        </span>
                      )}
                    </div>
                    {chat.last_message && (
                      <p className="text-xs text-foreground-muted truncate">
                        {chat.last_message}
                      </p>
                    )}
                  </div>
                </motion.button>
              );
            })}
          </div>
        )}
        {!isLoading && filtered.length === 0 && (
          <div className="p-8 text-center text-sm text-foreground-muted">沒有符合的聊天</div>
        )}
      </div>
    </div>
  );
}

function KindIcon({ kind }: { kind: ChatItem["kind"] }) {
  const cls = "w-5 h-5 text-primary";
  if (kind === "user") return <User aria-hidden="true" className={cls} />;
  if (kind === "channel") return <Megaphone aria-hidden="true" className={cls} />;
  return <Users aria-hidden="true" className={cls} />;
}
