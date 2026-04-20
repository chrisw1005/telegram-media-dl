import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  keepPreviousData,
  useInfiniteQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { CheckSquare, Download } from "lucide-react";
import { toast } from "sonner";
import { api, type MediaItem, type MediaPage } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import MediaThumb from "@/components/MediaThumb";
import MediaPreviewModal from "@/components/MediaPreviewModal";
import { cn } from "@/lib/cn";

type KindFilter = "all" | "photo" | "video" | "document" | "audio" | "voice";

const FILTERS: { key: KindFilter; label: string }[] = [
  { key: "all", label: "全部" },
  { key: "photo", label: "相片" },
  { key: "video", label: "影片" },
  { key: "document", label: "文件" },
  { key: "audio", label: "音訊" },
  { key: "voice", label: "語音" },
];

export default function ChatMedia({ chatId }: { chatId: number }) {
  const [kind, setKind] = useState<KindFilter>("all");
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [previewIdx, setPreviewIdx] = useState<number | null>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);

  const queryClient = useQueryClient();
  const { data, fetchNextPage, hasNextPage, isFetching, isLoading } = useInfiniteQuery({
    queryKey: ["media", chatId, kind],
    initialPageParam: 0,
    queryFn: async ({ pageParam }) => {
      const qs = new URLSearchParams();
      qs.set("offset_id", String(pageParam));
      qs.set("limit", "60");
      if (kind !== "all") qs.set("kind", kind);
      return api.get<MediaPage>(`/api/chats/${chatId}/media?${qs}`);
    },
    getNextPageParam: (last) => (last.has_more ? last.next_offset : undefined),
    placeholderData: keepPreviousData,
  });

  const items = useMemo<MediaItem[]>(
    () => data?.pages.flatMap((p) => p.items) ?? [],
    [data],
  );

  useEffect(() => {
    setSelected(new Set());
  }, [chatId, kind]);

  useEffect(() => {
    if (!sentinelRef.current) return;
    const obs = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting && hasNextPage && !isFetching) {
        void fetchNextPage();
      }
    });
    obs.observe(sentinelRef.current);
    return () => obs.disconnect();
  }, [hasNextPage, isFetching, fetchNextPage]);

  const toggleSelect = useCallback((id: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  const selectAll = useCallback(() => {
    setSelected(new Set(items.map((i) => i.message_id)));
  }, [items]);

  const clearSelection = useCallback(() => setSelected(new Set()), []);

  // Keyboard: Ctrl+A select all (when not in a text input)
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      if (t && ["INPUT", "TEXTAREA"].includes(t.tagName)) return;
      if ((e.metaKey || e.ctrlKey) && e.key === "a") {
        e.preventDefault();
        selectAll();
      }
      if (e.key === "Escape" && selected.size > 0) {
        clearSelection();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selectAll, clearSelection, selected.size]);

  const enqueue = useMutation({
    mutationFn: (messageIds: number[]) =>
      api.post<{ job_ids: string[] }>("/api/download", {
        chat_id: chatId,
        message_ids: messageIds,
      }),
    onSuccess: (res) => {
      toast.success(`已加入 ${res.job_ids.length} 個檔案到下載佇列`);
      clearSelection();
      queryClient.invalidateQueries({ queryKey: ["jobs"] });
    },
    onError: (err) => {
      toast.error(`加入下載失敗：${String(err)}`);
    },
  });

  function enqueueSelected() {
    if (selected.size === 0) return;
    enqueue.mutate(Array.from(selected));
  }

  function enqueueSingle(mid: number) {
    enqueue.mutate([mid]);
  }

  return (
    <div className="h-full flex flex-col">
      <header className="h-14 px-4 flex items-center gap-2 border-b border-border shrink-0">
        <div className="flex items-center gap-1 flex-wrap">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              onClick={() => setKind(f.key)}
              className={cn(
                "px-3 h-8 rounded-button text-sm font-medium transition-colors duration-fast",
                kind === f.key
                  ? "bg-primary text-white"
                  : "text-foreground-muted hover:text-foreground hover:bg-[rgb(var(--surface-hover-rgb)/0.06)]",
              )}
            >
              {f.label}
            </button>
          ))}
        </div>
        <div className="flex-1" />
        <AnimatePresence>
          {selected.size > 0 && (
            <motion.div
              initial={{ opacity: 0, x: 12 }}
              animate={{ opacity: 1, x: 0, transition: { duration: 0.2 } }}
              exit={{ opacity: 0, x: 12, transition: { duration: 0.15 } }}
              className="flex items-center gap-2"
            >
              <span className="text-sm text-foreground-muted tabular-nums">
                已選 {selected.size}
              </span>
              <Button variant="secondary" size="sm" onClick={clearSelection}>
                取消
              </Button>
              <Button
                size="sm"
                onClick={enqueueSelected}
                disabled={enqueue.isPending}
              >
                <Download className="w-4 h-4" /> 下載所選
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
        {selected.size === 0 && items.length > 0 && (
          <Button variant="ghost" size="sm" onClick={selectAll}>
            <CheckSquare className="w-4 h-4" /> 全選
          </Button>
        )}
      </header>

      <div className="flex-1 overflow-y-auto scrollbar-slim p-4">
        {isLoading && (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3">
            {Array.from({ length: 12 }).map((_, i) => (
              <Skeleton key={i} className="aspect-video rounded-card" />
            ))}
          </div>
        )}

        {!isLoading && items.length === 0 && (
          <div className="h-full grid place-items-center text-foreground-muted text-sm">
            這個聊天沒有對應類型的媒體
          </div>
        )}

        {!isLoading && items.length > 0 && (
          <div className="grid grid-cols-[repeat(auto-fill,minmax(180px,1fr))] gap-3 auto-rows-auto">
            {items.map((item, i) => (
              <MediaThumb
                key={`${item.chat_id}:${item.message_id}`}
                item={item}
                selected={selected.has(item.message_id)}
                onToggleSelect={() => toggleSelect(item.message_id)}
                onOpen={() => setPreviewIdx(i)}
              />
            ))}
          </div>
        )}

        <div ref={sentinelRef} className="h-10" />
        {isFetching && items.length > 0 && (
          <div className="py-4 text-center text-xs text-foreground-muted">載入更多…</div>
        )}
      </div>

      <MediaPreviewModal
        items={items}
        index={previewIdx}
        onClose={() => setPreviewIdx(null)}
        onNavigate={setPreviewIdx}
        onEnqueue={enqueueSingle}
      />
    </div>
  );
}
