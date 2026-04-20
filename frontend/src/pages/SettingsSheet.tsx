import { useEffect, useId, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { api, type AppInfo, type MeResponse, type UserSettings } from "@/lib/api";
import { Sheet } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import FolderPicker from "@/components/FolderPicker";
import { useTheme } from "@/lib/theme";
import { cn } from "@/lib/cn";

export default function SettingsSheet({
  open,
  onClose,
  me,
}: {
  open: boolean;
  onClose: () => void;
  me: MeResponse;
}) {
  const [settings, setSettings] = useState<UserSettings | null>(null);
  const { data: info } = useQuery<AppInfo>({
    queryKey: ["info"],
    queryFn: () => api.get<AppInfo>("/api/info"),
    enabled: open,
  });
  const theme = useTheme();
  const concurrencyId = useId();
  const minAspectId = useId();
  const maxAspectId = useId();

  useEffect(() => {
    if (!open) return;
    void api.get<UserSettings>("/api/settings").then(setSettings);
  }, [open]);

  const queryClient = useQueryClient();

  async function save(partial: Partial<UserSettings>) {
    if (!settings) return;
    const next = { ...settings, ...partial };
    setSettings(next);
    try {
      await api.put("/api/settings", next);
      // Tell ChatMedia (which watches the settings query) to re-layout.
      queryClient.setQueryData(["settings"], next);
      toast.success("已儲存", { duration: 1500 });
    } catch (e) {
      toast.error(`儲存失敗：${String(e)}`);
    }
  }

  return (
    <Sheet open={open} onClose={onClose} title="設定" width="480px">
      {!settings ? (
        <div className="p-6 text-sm text-foreground-muted">讀取中…</div>
      ) : (
        <div className="p-5 space-y-6">
          <section>
            <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
              帳號
            </h3>
            <div className="rounded-card border border-border bg-bg-card p-3 space-y-1">
              <p className="text-sm font-mono tabular-nums">TG User ID: {me.tg_user_id}</p>
              {me.is_admin && (
                <p className="text-xs text-primary">Admin</p>
              )}
            </div>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
              下載
            </h3>
            <div className="space-y-3">
              {info?.deployment_mode === "local" ? (
                <div>
                  <p className="text-xs text-foreground-muted mb-1">目標資料夾</p>
                  <FolderPicker
                    value={settings.download_dir || info?.download_dir_default || null}
                    onChange={(p) => save({ download_dir: p })}
                  />
                </div>
              ) : (
                <p className="text-xs text-foreground-muted">
                  公開部署模式：檔案會直接串流到瀏覽器下載
                </p>
              )}

              <div>
                <label
                  htmlFor={concurrencyId}
                  className="block text-xs text-foreground-muted mb-2"
                >
                  預設並行數：{settings.preferred_concurrency ?? 4}
                </label>
                <input
                  id={concurrencyId}
                  type="range"
                  min={2}
                  max={8}
                  step={1}
                  value={settings.preferred_concurrency ?? 4}
                  onChange={(e) =>
                    save({ preferred_concurrency: parseInt(e.target.value) })
                  }
                  className="w-full accent-primary"
                />
              </div>

              <div>
                <label className="block text-xs text-foreground-muted mb-2">
                  Keyframe 密度
                </label>
                <div className="grid grid-cols-3 gap-1" role="group" aria-label="Keyframe 密度">
                  {(["low", "medium", "high"] as const).map((d) => (
                    <button
                      key={d}
                      type="button"
                      aria-pressed={settings.keyframe_density === d}
                      onClick={() => save({ keyframe_density: d })}
                      className={cn(
                        "h-9 rounded-button text-sm border transition-colors",
                        settings.keyframe_density === d
                          ? "border-primary text-primary bg-[rgb(var(--primary)/0.1)]"
                          : "border-border text-foreground-muted hover:text-foreground",
                      )}
                    >
                      {d === "low" ? "低" : d === "medium" ? "中" : "高"}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
              媒體 Grid
            </h3>
            <div className="space-y-3">
              <div>
                <label className="block text-xs text-foreground-muted mb-2">
                  欄數
                </label>
                <div className="grid grid-cols-6 gap-1" role="group" aria-label="Grid 欄數">
                  {(["auto", "3", "4", "5", "6", "8"] as const).map((c) => (
                    <button
                      key={c}
                      type="button"
                      aria-pressed={settings.grid_columns === c}
                      onClick={() => save({ grid_columns: c })}
                      className={cn(
                        "h-9 rounded-button text-sm border transition-colors",
                        settings.grid_columns === c
                          ? "border-primary text-primary bg-[rgb(var(--primary)/0.1)]"
                          : "border-border text-foreground-muted hover:text-foreground",
                      )}
                    >
                      {c === "auto" ? "自動" : c}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label
                  htmlFor={minAspectId}
                  className="block text-xs text-foreground-muted mb-2"
                >
                  最窄高寬比：<span className="font-mono">
                    {settings.grid_min_aspect.toFixed(2)}
                  </span>
                  <span className="ml-2 text-foreground-muted/70">
                    （portrait 最高 1:{(1 / settings.grid_min_aspect).toFixed(1)}）
                  </span>
                </label>
                <input
                  id={minAspectId}
                  type="range"
                  min={0.3}
                  max={1.0}
                  step={0.05}
                  value={settings.grid_min_aspect}
                  onChange={(e) =>
                    save({ grid_min_aspect: parseFloat(e.target.value) })
                  }
                  className="w-full accent-primary"
                />
              </div>

              <div>
                <label
                  htmlFor={maxAspectId}
                  className="block text-xs text-foreground-muted mb-2"
                >
                  最寬高寬比：<span className="font-mono">
                    {settings.grid_max_aspect.toFixed(2)}
                  </span>
                  <span className="ml-2 text-foreground-muted/70">
                    （pano 最寬 {settings.grid_max_aspect.toFixed(1)}:1）
                  </span>
                </label>
                <input
                  id={maxAspectId}
                  type="range"
                  min={1.0}
                  max={3.0}
                  step={0.1}
                  value={settings.grid_max_aspect}
                  onChange={(e) =>
                    save({ grid_max_aspect: parseFloat(e.target.value) })
                  }
                  className="w-full accent-primary"
                />
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
              外觀
            </h3>
            <div className="grid grid-cols-3 gap-1" role="group" aria-label="主題外觀">
              {(["auto", "light", "dark"] as const).map((c) => (
                <button
                  key={c}
                  type="button"
                  aria-pressed={theme.choice === c}
                  onClick={() => {
                    theme.setChoice(c);
                    void save({ theme: c });
                  }}
                  className={cn(
                    "h-9 rounded-button text-sm border transition-colors",
                    theme.choice === c
                      ? "border-primary text-primary bg-[rgb(var(--primary)/0.1)]"
                      : "border-border text-foreground-muted hover:text-foreground",
                  )}
                >
                  {c === "auto" ? "自動" : c === "light" ? "明亮" : "深色"}
                </button>
              ))}
            </div>
          </section>

          {me.is_admin && <AdminSection />}
        </div>
      )}
    </Sheet>
  );
}

function AdminSection() {
  const { data, refetch } = useQuery({
    queryKey: ["admin", "acl"],
    queryFn: () =>
      api.get<{ allowlist: number[]; admin_ids: number[] }>("/api/admin/acl"),
  });
  const [newId, setNewId] = useState("");

  async function add(promote = false) {
    const id = parseInt(newId);
    if (!id) return;
    try {
      await api.post("/api/admin/acl/add", {
        tg_user_id: id,
        promote_to_admin: promote,
      });
      setNewId("");
      toast.success("已加入白名單");
      void refetch();
    } catch (e) {
      toast.error(String(e));
    }
  }

  async function remove(id: number) {
    const isAdmin = data?.admin_ids.includes(id);
    const confirmed = window.confirm(
      `確定要將 ${id}${isAdmin ? "（管理員）" : ""} 從白名單移除？此動作無法復原。`,
    );
    if (!confirmed) return;
    try {
      await api.post("/api/admin/acl/remove", { tg_user_id: id });
      toast.success("已從白名單移除");
      void refetch();
    } catch (e) {
      toast.error(String(e));
    }
  }

  return (
    <section>
      <h3 className="text-xs font-semibold text-foreground-muted uppercase tracking-wider mb-3">
        管理員 · 白名單
      </h3>
      <div className="space-y-2">
        <div className="flex gap-2">
          <Input
            type="text"
            name="tg_user_id"
            autoComplete="off"
            aria-label="新增 TG User ID"
            placeholder="TG User ID，例：123456789…"
            inputMode="numeric"
            value={newId}
            onChange={(e) => setNewId(e.target.value.replace(/\D/g, ""))}
          />
          <Button size="md" variant="secondary" onClick={() => void add(false)}>
            加入
          </Button>
          <Button size="md" onClick={() => void add(true)}>
            Admin
          </Button>
        </div>
        <ul className="space-y-1">
          {data?.allowlist.map((id) => (
            <li
              key={id}
              className="flex items-center justify-between px-2 py-1.5 text-sm font-mono tabular-nums rounded border border-border bg-bg-card"
            >
              <span>
                {id}
                {data.admin_ids.includes(id) && (
                  <span className="ml-2 text-xs text-primary font-sans">admin</span>
                )}
              </span>
              <button
                onClick={() => void remove(id)}
                className="text-destructive text-xs hover:underline"
              >
                移除
              </button>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
