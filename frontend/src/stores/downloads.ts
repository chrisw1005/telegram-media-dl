import { create } from "zustand";
import type { DownloadJob } from "@/lib/api";
import { connectWs } from "@/lib/ws";

interface DownloadState {
  jobs: Record<string, DownloadJob>;
  activeCount: number;
  wsHandle: { close: () => void } | null;
  connect: () => void;
  disconnect: () => void;
  upsert: (job: DownloadJob) => void;
  snapshot: (jobs: DownloadJob[]) => void;
}

function countActive(jobs: Record<string, DownloadJob>): number {
  let n = 0;
  for (const j of Object.values(jobs)) {
    if (j.status === "running" || j.status === "pending" || j.status === "flood_wait") n += 1;
  }
  return n;
}

export const useDownloadStore = create<DownloadState>((set, get) => ({
  jobs: {},
  activeCount: 0,
  wsHandle: null,

  connect: () => {
    if (get().wsHandle) return;
    const handle = connectWs("/api/ws/downloads", (msg) => {
      const m = msg as { event: string; job?: DownloadJob; jobs?: DownloadJob[] };
      if (m.event === "snapshot" && m.jobs) {
        get().snapshot(m.jobs);
      } else if (m.job) {
        get().upsert(m.job);
      }
    });
    set({ wsHandle: handle });
  },

  disconnect: () => {
    get().wsHandle?.close();
    set({ wsHandle: null });
  },

  upsert: (job) =>
    set((s) => {
      const next = { ...s.jobs, [job.id]: job };
      return { jobs: next, activeCount: countActive(next) };
    }),

  snapshot: (jobs) => {
    const map: Record<string, DownloadJob> = {};
    for (const j of jobs) map[j.id] = j;
    set({ jobs: map, activeCount: countActive(map) });
  },
}));

// helper: messages in-queue or done, keyed by "chat:msg"
export function useMessageStatus(): Record<string, DownloadJob["status"]> {
  const jobs = useDownloadStore((s) => s.jobs);
  const map: Record<string, DownloadJob["status"]> = {};
  for (const j of Object.values(jobs)) {
    const key = `${j.chat_id}:${j.message_id}`;
    const existing = map[key];
    // Prefer most-advanced status
    const priority = { pending: 0, flood_wait: 1, running: 2, cancelled: 3, failed: 4, completed: 5 };
    if (!existing || priority[j.status] > priority[existing]) {
      map[key] = j.status;
    }
  }
  return map;
}
