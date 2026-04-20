import { useEffect, useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Clock3, Loader2, PauseCircle, Trash2, XCircle } from "lucide-react";
import { api, type DownloadJob } from "@/lib/api";
import { useDownloadStore } from "@/stores/downloads";
import { Sheet } from "@/components/ui/sheet";
import { formatSize } from "@/lib/format";
import { cn } from "@/lib/cn";

export default function DownloadsSheet({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const jobs = Object.values(useDownloadStore((s) => s.jobs));

  const active = jobs.filter((j) => j.status === "running" || j.status === "flood_wait");
  const queued = jobs.filter((j) => j.status === "pending");
  const completed = jobs
    .filter((j) => j.status === "completed" || j.status === "failed" || j.status === "cancelled")
    .sort((a, b) => (b.finished_at ?? 0) - (a.finished_at ?? 0));

  return (
    <Sheet open={open} onClose={onClose} title="下載" width="480px">
      <div className="p-4 space-y-5">
        <Section title="進行中" count={active.length}>
          {active.length === 0 && <EmptyLine text="無進行中的下載" />}
          {active.map((j) => (
            <JobCard key={j.id} job={j} />
          ))}
        </Section>

        <Section title="排隊中" count={queued.length}>
          {queued.length === 0 && <EmptyLine text="無排隊項目" />}
          {queued.map((j) => (
            <JobCard key={j.id} job={j} />
          ))}
        </Section>

        <Section title="已完成" count={completed.length}>
          {completed.length === 0 && <EmptyLine text="尚無完成歷史" />}
          <AnimatePresence initial={false}>
            {completed.slice(0, 50).map((j) => (
              <JobCard key={j.id} job={j} compact />
            ))}
          </AnimatePresence>
        </Section>
      </div>
    </Sheet>
  );
}

function Section({
  title,
  count,
  children,
}: {
  title: string;
  count: number;
  children: React.ReactNode;
}) {
  return (
    <section>
      <header className="flex items-center justify-between mb-2">
        <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider">
          {title}
        </h3>
        <span className="text-xs text-foreground-muted tabular-nums">{count}</span>
      </header>
      <div className="space-y-2">{children}</div>
    </section>
  );
}

function EmptyLine({ text }: { text: string }) {
  return <p className="text-xs text-foreground-muted px-2 py-4 text-center">{text}</p>;
}

function JobCard({ job, compact }: { job: DownloadJob; compact?: boolean }) {
  const [prevStatus, setPrevStatus] = useState(job.status);
  const [flash, setFlash] = useState(false);
  useEffect(() => {
    if (prevStatus !== "completed" && job.status === "completed") {
      setFlash(true);
      setTimeout(() => setFlash(false), 600);
    }
    setPrevStatus(job.status);
  }, [job.status, prevStatus]);

  const pct =
    job.bytes_total > 0 ? Math.round((job.bytes_done / job.bytes_total) * 100) : 0;

  const icon = (() => {
    switch (job.status) {
      case "completed":
        return <CheckCircle2 className="w-4 h-4 text-accent-success" />;
      case "failed":
        return <XCircle className="w-4 h-4 text-destructive" />;
      case "cancelled":
        return <XCircle className="w-4 h-4 text-foreground-muted" />;
      case "flood_wait":
        return <PauseCircle className="w-4 h-4 text-accent-warn animate-pulse" />;
      case "pending":
        return <Clock3 className="w-4 h-4 text-foreground-muted" />;
      case "running":
      default:
        return <Loader2 className="w-4 h-4 text-primary animate-spin" />;
    }
  })();

  const cancel = async () => {
    try {
      await api.post(`/api/jobs/${job.id}/cancel`);
    } catch {
      // ignore
    }
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 6 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -6 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        "rounded-card bg-bg-card border border-border p-3",
        flash && "animate-flash-success",
        job.status === "flood_wait" && "bg-[rgb(var(--accent-warn)/0.08)]",
      )}
    >
      <div className="flex items-center gap-2">
        {icon}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium truncate">
            {job.filename || `msg-${job.message_id}`}
          </p>
          {!compact && (
            <p className="text-[11px] text-foreground-muted tabular-nums">
              {job.status === "flood_wait"
                ? `FLOOD_WAIT：${Math.max(0, Math.round(job.flood_wait_until - Date.now() / 1000))}s`
                : `${formatSize(job.bytes_done)} / ${formatSize(job.bytes_total)} · ${pct}%`}
            </p>
          )}
          {compact && job.error && (
            <p className="text-[11px] text-destructive truncate">{job.error}</p>
          )}
        </div>
        {(job.status === "pending" || job.status === "running" || job.status === "flood_wait") && (
          <button
            onClick={() => void cancel()}
            className="text-foreground-muted hover:text-destructive transition-colors p-1"
            aria-label="取消"
          >
            <Trash2 className="w-4 h-4" />
          </button>
        )}
      </div>
      {!compact && job.bytes_total > 0 && (
        <div className="mt-2 h-1 rounded-full bg-[rgb(var(--surface-hover-rgb)/0.08)] overflow-hidden">
          <div
            className={cn(
              "h-full transition-[width] duration-200 ease-linear",
              job.status === "flood_wait" ? "bg-accent-warn" : "bg-primary",
            )}
            style={{ width: `${pct}%` }}
          />
        </div>
      )}
    </motion.div>
  );
}
