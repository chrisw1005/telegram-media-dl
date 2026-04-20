export class ApiError extends Error {
  constructor(
    public status: number,
    public detail?: string,
  ) {
    super(detail || `HTTP ${status}`);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  opts: RequestInit = {},
): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
      ...(opts.headers || {}),
    },
    ...opts,
  });

  if (res.status === 401) {
    if (!path.includes("/auth/")) {
      window.dispatchEvent(new CustomEvent("auth:unauthorized"));
    }
    throw new ApiError(401, "unauthorized");
  }

  if (!res.ok) {
    let detail: string | undefined;
    try {
      const data = await res.json();
      detail = typeof data?.detail === "string" ? data.detail : JSON.stringify(data);
    } catch {
      detail = res.statusText;
    }
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as unknown as T;
  return (await res.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "POST", body: JSON.stringify(body ?? {}) }),
  put: <T>(path: string, body?: unknown) =>
    request<T>(path, { method: "PUT", body: JSON.stringify(body ?? {}) }),
};

// ---- Type definitions mirrored from backend ----

export interface MeResponse {
  tg_user_id: number;
  is_admin: boolean;
}

export interface ChatItem {
  id: number;
  title: string;
  username: string | null;
  kind: "user" | "group" | "channel";
  unread_count: number;
  last_message: string | null;
}

export interface MediaItem {
  chat_id: number;
  message_id: number;
  kind: "photo" | "video" | "document" | "audio" | "voice";
  filename: string | null;
  size: number;
  duration_sec: number;
  width: number;
  height: number;
  mime_type: string | null;
  date_ts: number;
  has_animated_preview: boolean;
}

export interface MediaPage {
  items: MediaItem[];
  next_offset: number;
  has_more: boolean;
}

export interface KeyframesReady {
  ready: true;
  frame_count: number;
  offsets: number[];
  duration_sec: number;
  urls: string[];
}

export interface KeyframesPending {
  ready: false;
  status: "pending" | "running" | "completed" | "failed" | "skipped";
  error: string | null;
  progress_done: number;
  progress_total: number;
}

export type KeyframesResponse = KeyframesReady | KeyframesPending;

export interface DownloadJob {
  id: string;
  tg_user_id: number;
  chat_id: number;
  message_id: number;
  kind: string;
  dest_dir: string;
  status:
    | "pending"
    | "running"
    | "completed"
    | "failed"
    | "cancelled"
    | "flood_wait";
  bytes_total: number;
  bytes_done: number;
  filename: string | null;
  error: string | null;
  flood_wait_until: number;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  result_path: string | null;
  send_to_saved: boolean;
}

export interface UserSettings {
  download_dir: string | null;
  preferred_concurrency: number | null;
  theme: "auto" | "light" | "dark";
  keyframe_density: "low" | "medium" | "high";
}

export interface AppInfo {
  deployment_mode: "local" | "public";
  download_dir_default: string;
}
