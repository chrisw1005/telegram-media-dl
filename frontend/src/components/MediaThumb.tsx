import { useEffect, useRef, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { Check, FileText, Hourglass, PlayCircle, TriangleAlert } from "lucide-react";
import type { MediaItem, KeyframesResponse } from "@/lib/api";
import { formatDuration, formatSize } from "@/lib/format";
import { cn } from "@/lib/cn";
import { useMessageStatus } from "@/stores/downloads";

const SLIDESHOW_INTERVAL_MS = 250;
const HOVER_DELAY_MS = 400;

interface Props {
  item: MediaItem;
  selected: boolean;
  onToggleSelect: () => void;
  onOpen: () => void;
}

export default function MediaThumb({ item, selected, onToggleSelect, onOpen }: Props) {
  const [hovering, setHovering] = useState(false);
  const [slideshowActive, setSlideshowActive] = useState(false);
  const [frames, setFrames] = useState<string[] | null>(null);
  const [frameIdx, setFrameIdx] = useState(0);
  const [extractionState, setExtractionState] = useState<
    "idle" | "loading" | "done" | "unavailable"
  >("idle");
  const hoverTimer = useRef<number | null>(null);
  const slideshowTimer = useRef<number | null>(null);

  const statusMap = useMessageStatus();
  const jobStatus = statusMap[`${item.chat_id}:${item.message_id}`];

  useEffect(() => {
    return () => {
      if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
      if (slideshowTimer.current) window.clearInterval(slideshowTimer.current);
    };
  }, []);

  async function ensureKeyframes() {
    if (item.kind !== "video" || extractionState === "loading" || extractionState === "unavailable") {
      return;
    }
    setExtractionState("loading");
    try {
      const data = await fetch(
        `/api/keyframes/${item.chat_id}/${item.message_id}?trigger=true`,
        { credentials: "include" },
      ).then((r) => r.json() as Promise<KeyframesResponse>);

      if (data.ready) {
        setFrames(data.urls);
        setExtractionState("done");
        return;
      }
      if (data.status === "skipped" || data.status === "failed") {
        setExtractionState("unavailable");
        return;
      }
      // poll until ready or fail
      const timer = window.setInterval(async () => {
        const check = await fetch(
          `/api/keyframes/${item.chat_id}/${item.message_id}`,
          { credentials: "include" },
        ).then((r) => r.json() as Promise<KeyframesResponse>);
        if (check.ready) {
          setFrames(check.urls);
          setExtractionState("done");
          window.clearInterval(timer);
        } else if (check.status === "skipped" || check.status === "failed") {
          setExtractionState("unavailable");
          window.clearInterval(timer);
        }
      }, 2000);
      // safety: clear after 60s
      window.setTimeout(() => window.clearInterval(timer), 60_000);
    } catch {
      setExtractionState("unavailable");
    }
  }

  function startHover() {
    if (item.kind !== "video") return;
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
    hoverTimer.current = window.setTimeout(() => {
      setSlideshowActive(true);
      void ensureKeyframes();
    }, HOVER_DELAY_MS);
  }

  function endHover() {
    if (hoverTimer.current) window.clearTimeout(hoverTimer.current);
    setSlideshowActive(false);
    setFrameIdx(0);
    if (slideshowTimer.current) window.clearInterval(slideshowTimer.current);
  }

  useEffect(() => {
    if (!slideshowActive || !frames || frames.length === 0) return;
    if (slideshowTimer.current) window.clearInterval(slideshowTimer.current);
    slideshowTimer.current = window.setInterval(() => {
      setFrameIdx((i) => (i + 1) % frames.length);
    }, SLIDESHOW_INTERVAL_MS);
    return () => {
      if (slideshowTimer.current) window.clearInterval(slideshowTimer.current);
    };
  }, [slideshowActive, frames]);

  const thumbUrl = `/api/thumb/${item.chat_id}/${item.message_id}`;
  const aspect = item.width && item.height ? item.width / item.height : 16 / 9;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.96 }}
      animate={{
        opacity: 1,
        scale: selected ? 0.96 : 1,
        transition: { duration: 0.2, ease: [0.16, 1, 0.3, 1] },
      }}
      whileHover={{ scale: selected ? 0.96 : 1.02 }}
      onMouseEnter={() => {
        setHovering(true);
        startHover();
      }}
      onMouseLeave={() => {
        setHovering(false);
        endHover();
      }}
      onClick={(e) => {
        if (e.shiftKey || e.metaKey || e.ctrlKey) {
          onToggleSelect();
        } else {
          onOpen();
        }
      }}
      onContextMenu={(e) => {
        e.preventDefault();
        onToggleSelect();
      }}
      className={cn(
        "relative cursor-pointer rounded-card overflow-hidden bg-bg-card group",
        "ring-2 ring-transparent transition-all duration-fast",
        selected && "ring-primary",
        hovering && !selected && "ring-primary/40",
      )}
      style={{ aspectRatio: aspect }}
    >
      {/* Base layer: thumbnail or document icon */}
      {item.kind === "document" || item.kind === "audio" || item.kind === "voice" ? (
        <div className="w-full h-full grid place-items-center p-4 bg-bg-elevated">
          <FileText className="w-10 h-10 text-foreground-muted" />
          <p className="mt-2 text-xs text-foreground-muted line-clamp-2 text-center">
            {item.filename || "(no name)"}
          </p>
        </div>
      ) : (
        <img
          src={thumbUrl}
          alt=""
          loading="lazy"
          className="w-full h-full object-cover"
          draggable={false}
        />
      )}

      {/* Video slideshow overlay */}
      <AnimatePresence>
        {slideshowActive && frames && frames.length > 0 && (
          <motion.img
            key={`frame-${frameIdx}`}
            src={frames[frameIdx]}
            alt=""
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.15 } }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            className="absolute inset-0 w-full h-full object-cover"
          />
        )}
      </AnimatePresence>

      {/* Play icon center (video only) */}
      {item.kind === "video" && !slideshowActive && (
        <div className="absolute inset-0 grid place-items-center pointer-events-none">
          <PlayCircle className="w-12 h-12 text-white/80 drop-shadow-lg group-hover:text-white transition-colors" />
        </div>
      )}

      {/* Size badge */}
      {item.size > 0 && (
        <span className="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded-md bg-black/60 text-white text-[10px] font-mono tabular-nums">
          {formatSize(item.size)}
        </span>
      )}

      {/* Duration badge */}
      {item.duration_sec > 0 && (
        <span className="absolute bottom-1.5 right-1.5 px-1.5 py-0.5 rounded-md bg-black/60 text-white text-[10px] font-mono tabular-nums">
          {formatDuration(item.duration_sec)}
        </span>
      )}

      {/* Extraction spinner */}
      {item.kind === "video" && slideshowActive && extractionState === "loading" && (
        <span className="absolute bottom-1.5 left-1.5 px-1.5 py-0.5 rounded-md bg-black/60 text-white text-[10px]">
          抽幀中…
        </span>
      )}

      {/* Status badge */}
      <StatusBadge status={jobStatus} />

      {/* Selection checkbox (top-right, always visible when selected, else hover) */}
      <button
        type="button"
        onClick={(e) => {
          e.stopPropagation();
          onToggleSelect();
        }}
        aria-label={selected ? "取消選取" : "選取"}
        className={cn(
          "absolute top-1.5 right-1.5 w-6 h-6 rounded-full border-2 transition-all duration-fast",
          "grid place-items-center",
          selected
            ? "bg-primary border-primary"
            : "bg-black/40 border-white/70 opacity-0 group-hover:opacity-100",
        )}
      >
        {selected && <Check className="w-4 h-4 text-white" strokeWidth={3} />}
      </button>
    </motion.div>
  );
}

function StatusBadge({ status }: { status?: string }) {
  if (!status) return null;
  if (status === "completed") {
    return (
      <motion.span
        initial={{ scale: 0 }}
        animate={{ scale: 1, transition: { type: "spring", damping: 14, stiffness: 260 } }}
        className="absolute bottom-1.5 left-1.5 w-6 h-6 rounded-full bg-accent-success grid place-items-center"
      >
        <Check className="w-4 h-4 text-white" strokeWidth={3} />
      </motion.span>
    );
  }
  if (status === "pending" || status === "running" || status === "flood_wait") {
    return (
      <span className="absolute bottom-1.5 left-1.5 w-6 h-6 rounded-full bg-accent-warn grid place-items-center">
        <Hourglass className="w-3.5 h-3.5 text-white" />
      </span>
    );
  }
  if (status === "failed") {
    return (
      <span className="absolute bottom-1.5 left-1.5 w-6 h-6 rounded-full bg-destructive grid place-items-center">
        <TriangleAlert className="w-3.5 h-3.5 text-white" />
      </span>
    );
  }
  return null;
}
