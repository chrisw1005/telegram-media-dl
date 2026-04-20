import { useEffect, useState } from "react";
import { ChevronUp, FolderClosed, FolderPlus, RefreshCw } from "lucide-react";
import { api } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface DirEntry {
  name: string;
  path: string;
  is_dir: boolean;
}

interface ListResponse {
  path: string;
  parent: string | null;
  entries: DirEntry[];
}

export default function FolderPicker({
  value,
  onChange,
  disabled,
}: {
  value: string | null;
  onChange: (path: string) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [browsing, setBrowsing] = useState(value || "~");
  const [data, setData] = useState<ListResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    void list(value || "~");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  async function list(p: string) {
    setLoading(true);
    setError(null);
    try {
      const res = await api.get<ListResponse>(`/api/fs/list?path=${encodeURIComponent(p)}`);
      setData(res);
      setBrowsing(res.path);
    } catch (e) {
      setError(String(e));
    } finally {
      setLoading(false);
    }
  }

  async function mkdir() {
    const name = prompt("新資料夾名稱");
    if (!name) return;
    const full = `${browsing.replace(/\/$/, "")}/${name}`;
    try {
      await api.post(`/api/fs/mkdir?path=${encodeURIComponent(full)}`);
      void list(browsing);
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div className="space-y-2">
      <div className="flex gap-2">
        <Input
          value={value || ""}
          readOnly
          placeholder="選擇下載資料夾"
          className="flex-1"
        />
        <Button
          variant="secondary"
          size="md"
          onClick={() => setOpen((o) => !o)}
          disabled={disabled}
        >
          {open ? "收合" : "瀏覽"}
        </Button>
      </div>
      {open && (
        <div className="rounded-card border border-border bg-bg-card p-2 max-h-80 overflow-y-auto scrollbar-slim">
          <div className="flex items-center gap-1 mb-2">
            <Button
              variant="icon"
              size="icon"
              onClick={() => data?.parent && list(data.parent)}
              disabled={!data?.parent}
              aria-label="上層"
            >
              <ChevronUp className="w-4 h-4" />
            </Button>
            <Button
              variant="icon"
              size="icon"
              onClick={() => list(browsing)}
              aria-label="重新整理"
            >
              <RefreshCw className="w-4 h-4" />
            </Button>
            <span className="text-xs text-foreground-muted truncate flex-1" title={browsing}>
              {browsing}
            </span>
            <Button variant="icon" size="icon" onClick={() => void mkdir()} aria-label="新增資料夾">
              <FolderPlus className="w-4 h-4" />
            </Button>
          </div>
          {loading && <p className="text-xs text-foreground-muted p-2">讀取中…</p>}
          {error && <p className="text-xs text-destructive p-2">{error}</p>}
          {!loading && data && (
            <>
              <ul className="space-y-0.5">
                {data.entries.map((e) => (
                  <li key={e.path}>
                    <button
                      onDoubleClick={() => list(e.path)}
                      onClick={() => onChange(e.path)}
                      className="w-full flex items-center gap-2 px-2 py-1.5 rounded text-sm hover:bg-[rgb(var(--surface-hover-rgb)/0.06)] text-left"
                    >
                      <FolderClosed className="w-4 h-4 text-primary" />
                      <span className="truncate">{e.name}</span>
                    </button>
                  </li>
                ))}
              </ul>
              {data.entries.length === 0 && (
                <p className="text-xs text-foreground-muted p-2 text-center">
                  （無子資料夾）
                </p>
              )}
              <div className="flex justify-end gap-2 mt-2 pt-2 border-t border-border">
                <Button variant="primary" size="sm" onClick={() => onChange(browsing)}>
                  使用「{browsing}」
                </Button>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
