import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { ChevronLeft, ChevronRight, Download, X } from "lucide-react";
import type { KeyframesResponse, MediaItem } from "@/lib/api";
import { formatDateTs, formatDuration, formatSize } from "@/lib/format";
import { useMessageStatus } from "@/stores/downloads";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";

interface Props {
  items: MediaItem[];
  index: number | null;
  onClose: () => void;
  onNavigate: (idx: number) => void;
  onEnqueue: (messageId: number) => void;
}

export default function MediaPreviewModal({
  items,
  index,
  onClose,
  onNavigate,
  onEnqueue,
}: Props) {
  const item = index != null ? items[index] : null;

  if (!item) {
    return (
      <AnimatePresence>{/* nothing */}</AnimatePresence>
    );
  }

  return (
    <AnimatePresence mode="wait">
      <InnerModal
        key={`${item.chat_id}:${item.message_id}`}
        items={items}
        index={index!}
        onClose={onClose}
        onNavigate={onNavigate}
        onEnqueue={onEnqueue}
      />
    </AnimatePresence>
  );
}

function InnerModal({
  items,
  index,
  onClose,
  onNavigate,
  onEnqueue,
}: {
  items: MediaItem[];
  index: number;
  onClose: () => void;
  onNavigate: (idx: number) => void;
  onEnqueue: (messageId: number) => void;
}) {
  const item = items[index];
  const videoRef = useRef<HTMLVideoElement>(null);
  const filmstripRef = useRef<HTMLDivElement>(null);
  const [currentTime, setCurrentTime] = useState(0);
  const [keyframes, setKeyframes] = useState<KeyframesResponse | null>(null);
  const statusMap = useMessageStatus();
  const jobStatus = statusMap[`${item.chat_id}:${item.message_id}`];

  useEffect(() => {
    setKeyframes(null);
    setCurrentTime(0);
    if (item.kind !== "video") return;
    let cancelled = false;
    const load = async () => {
      try {
        const res = await fetch(
          `/api/keyframes/${item.chat_id}/${item.message_id}?trigger=true`,
          { credentials: "include" },
        );
        const data = (await res.json()) as KeyframesResponse;
        if (!cancelled) setKeyframes(data);
        if (!cancelled && !data.ready) {
          const poll = window.setInterval(async () => {
            const r = await fetch(
              `/api/keyframes/${item.chat_id}/${item.message_id}`,
              { credentials: "include" },
            );
            const d = (await r.json()) as KeyframesResponse;
            if (!cancelled) setKeyframes(d);
            if (d.ready || (d.status === "skipped" || d.status === "failed")) {
              window.clearInterval(poll);
            }
          }, 2000);
          window.setTimeout(() => window.clearInterval(poll), 120_000);
        }
      } catch {
        // ignore
      }
    };
    void load();
    return () => {
      cancelled = true;
    };
  }, [item.chat_id, item.message_id, item.kind]);

  const activeKeyframeIdx = useMemo(() => {
    if (!keyframes?.ready) return -1;
    const offsets = keyframes.offsets;
    for (let i = offsets.length - 1; i >= 0; i -= 1) {
      if (currentTime >= offsets[i]) return i;
    }
    return 0;
  }, [currentTime, keyframes]);

  useEffect(() => {
    if (activeKeyframeIdx < 0 || !filmstripRef.current) return;
    const target = filmstripRef.current.querySelector<HTMLElement>(
      `[data-kf-idx="${activeKeyframeIdx}"]`,
    );
    target?.scrollIntoView({ behavior: "smooth", block: "nearest", inline: "center" });
  }, [activeKeyframeIdx]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      const t = e.target as HTMLElement;
      const isTextInput =
        t && ["INPUT", "TEXTAREA"].includes(t.tagName);
      if (isTextInput) return;

      if (e.key === " ") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "d" || e.key === "D" || e.key === "Enter") {
        e.preventDefault();
        onEnqueue(item.message_id);
        goNext();
      } else if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        const dir = e.key === "ArrowRight" ? 1 : -1;
        if (e.shiftKey || !keyframes?.ready) {
          goStep(dir);
        } else {
          // navigate media instead
          const next = index + dir;
          if (next >= 0 && next < items.length) onNavigate(next);
        }
      } else if (e.key === "," || e.key === ".") {
        if (keyframes?.ready) {
          const dir = e.key === "." ? 1 : -1;
          jumpKeyframe(dir);
        }
      } else if (e.key === "j" || e.key === "J") {
        seek(-5);
      } else if (e.key === "l" || e.key === "L") {
        seek(5);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [item.message_id, index, items.length, keyframes]);

  function goStep(dir: number) {
    const next = index + dir;
    if (next >= 0 && next < items.length) onNavigate(next);
  }
  function goNext() {
    goStep(1);
  }
  function togglePlay() {
    const v = videoRef.current;
    if (!v) return;
    if (v.paused) void v.play();
    else v.pause();
  }
  function seek(deltaSec: number) {
    const v = videoRef.current;
    if (!v) return;
    v.currentTime = Math.max(0, Math.min(v.duration, v.currentTime + deltaSec));
  }
  function jumpKeyframe(dir: number) {
    if (!keyframes?.ready || !videoRef.current) return;
    const nextIdx = Math.max(0, Math.min(keyframes.offsets.length - 1, activeKeyframeIdx + dir));
    videoRef.current.currentTime = keyframes.offsets[nextIdx];
  }
  function jumpToKeyframe(idx: number) {
    if (!keyframes?.ready || !videoRef.current) return;
    videoRef.current.currentTime = keyframes.offsets[idx];
  }

  const streamUrl = `/api/stream/${item.chat_id}/${item.message_id}`;
  const thumbUrl = `/api/thumb/${item.chat_id}/${item.message_id}`;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1, transition: { duration: 0.2 } }}
      exit={{ opacity: 0, transition: { duration: 0.15 } }}
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm grid grid-cols-[1fr_320px] grid-rows-[1fr_auto]"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{
          opacity: 1,
          scale: 1,
          transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] },
        }}
        className="col-start-1 row-start-1 min-h-0 grid place-items-center p-6"
        onClick={(e) => e.stopPropagation()}
      >
        {item.kind === "video" ? (
          <video
            ref={videoRef}
            src={streamUrl}
            poster={thumbUrl}
            controls
            autoPlay
            playsInline
            onTimeUpdate={(e) => setCurrentTime(e.currentTarget.currentTime)}
            className="max-w-full max-h-full rounded-card"
          />
        ) : item.kind === "photo" ? (
          <img
            src={streamUrl}
            alt=""
            className="max-w-full max-h-full rounded-card object-contain"
          />
        ) : (
          <div className="text-center text-foreground-muted">
            <p className="text-lg mb-2">{item.filename || "(no name)"}</p>
            <p className="text-sm">{formatSize(item.size)} · {item.mime_type}</p>
            <p className="text-xs mt-4">此類型不支援預覽，直接下載即可</p>
          </div>
        )}
      </motion.div>

      {/* Metadata panel (right) */}
      <motion.aside
        initial={{ opacity: 0, x: 20 }}
        animate={{ opacity: 1, x: 0, transition: { delay: 0.05, duration: 0.25 } }}
        className="col-start-2 row-start-1 row-span-2 bg-bg-elevated border-l border-border p-5 flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-sm font-semibold">媒體資訊</h2>
          <button onClick={onClose} className="text-foreground-muted hover:text-foreground">
            <X className="w-5 h-5" />
          </button>
        </div>

        <dl className="space-y-3 text-sm flex-1">
          <MetaRow label="類型" value={item.kind} />
          {item.filename && <MetaRow label="檔名" value={item.filename} mono />}
          <MetaRow label="大小" value={formatSize(item.size)} mono />
          {item.duration_sec > 0 && (
            <MetaRow label="時長" value={formatDuration(item.duration_sec)} mono />
          )}
          {item.width > 0 && (
            <MetaRow label="解析度" value={`${item.width} × ${item.height}`} mono />
          )}
          {keyframes?.ready && (
            <MetaRow label="Keyframes" value={`${keyframes.frame_count} 張`} mono />
          )}
          {item.mime_type && <MetaRow label="MIME" value={item.mime_type} mono />}
          {item.date_ts > 0 && <MetaRow label="時間" value={formatDateTs(item.date_ts)} />}
          {jobStatus && <MetaRow label="狀態" value={jobStatus} />}
        </dl>

        <div className="pt-4 border-t border-border space-y-2">
          <Button
            className="w-full"
            onClick={() => {
              onEnqueue(item.message_id);
              goNext();
            }}
          >
            <Download className="w-4 h-4" /> 加入下載 (D / Enter)
          </Button>
          <div className="grid grid-cols-2 gap-2">
            <Button variant="secondary" size="sm" onClick={() => goStep(-1)} disabled={index === 0}>
              <ChevronLeft className="w-4 h-4" /> 上一個
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => goStep(1)}
              disabled={index >= items.length - 1}
            >
              下一個 <ChevronRight className="w-4 h-4" />
            </Button>
          </div>
          <p className="text-[11px] text-foreground-muted text-center pt-2">
            Space 播放/暫停 · J/L ±5s · ,/. 跳 keyframe · Esc 關閉
          </p>
        </div>
      </motion.aside>

      {/* Filmstrip (bottom, full width of left column) */}
      {item.kind === "video" && keyframes?.ready && (
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0, transition: { delay: 0.1, duration: 0.25 } }}
          className="col-start-1 row-start-2 bg-bg-elevated/90 border-t border-border py-3 relative"
          onClick={(e) => e.stopPropagation()}
        >
          <div
            ref={filmstripRef}
            className="flex gap-1.5 px-4 overflow-x-auto scrollbar-slim scroll-smooth"
          >
            {keyframes.urls.map((url, i) => (
              <button
                key={i}
                data-kf-idx={i}
                onClick={() => jumpToKeyframe(i)}
                className={cn(
                  "shrink-0 relative rounded-md overflow-hidden border-2 transition-all duration-fast",
                  activeKeyframeIdx === i ? "border-primary" : "border-transparent",
                )}
                title={formatDuration(keyframes.offsets[i])}
              >
                <img
                  src={url}
                  alt=""
                  className="w-[120px] h-[68px] object-cover"
                  loading="lazy"
                />
                <span className="absolute bottom-0 right-0 px-1 bg-black/70 text-white text-[9px] font-mono tabular-nums">
                  {formatDuration(keyframes.offsets[i])}
                </span>
              </button>
            ))}
          </div>
          {/* Left/right edge fade */}
          <div className="pointer-events-none absolute inset-y-0 left-0 w-6 bg-gradient-to-r from-bg-elevated to-transparent" />
          <div className="pointer-events-none absolute inset-y-0 right-0 w-6 bg-gradient-to-l from-bg-elevated to-transparent" />
        </motion.div>
      )}
      {item.kind === "video" && keyframes && !keyframes.ready && (
        <div
          className="col-start-1 row-start-2 bg-bg-elevated/90 border-t border-border py-4 text-center text-xs text-foreground-muted"
          onClick={(e) => e.stopPropagation()}
        >
          {keyframes.status === "running"
            ? `抽幀中 ${keyframes.progress_done}/${keyframes.progress_total}…`
            : keyframes.status === "skipped"
              ? "影片較大，無 keyframe filmstrip（可直接拖曳播放軸）"
              : keyframes.status === "failed"
                ? `抽幀失敗：${keyframes.error || "未知錯誤"}`
                : "準備中…"}
        </div>
      )}
    </motion.div>
  );
}

function MetaRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-foreground-muted shrink-0">{label}</dt>
      <dd className={cn("text-right break-all", mono && "font-mono text-[13px]")}>{value}</dd>
    </div>
  );
}
