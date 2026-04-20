import { AnimatePresence, motion } from "framer-motion";
import { X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import { cn } from "@/lib/cn";
import { useFocusTrap } from "@/lib/useFocusTrap";

interface Props {
  open: boolean;
  onClose: () => void;
  title?: string;
  width?: string;
  children: ReactNode;
}

export function Sheet({ open, onClose, title, width = "440px", children }: Props) {
  const titleId = useId();
  const panelRef = useRef<HTMLElement>(null);

  useFocusTrap(panelRef, open);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        onClose();
      }
    };
    window.addEventListener("keydown", onKey);
    const t = window.setTimeout(() => {
      panelRef.current?.focus();
    }, 0);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(t);
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.18 }}
          onClick={onClose}
          className="fixed inset-0 bg-black/50 z-40"
        >
          <motion.aside
            ref={panelRef}
            tabIndex={-1}
            initial={{ x: "100%" }}
            animate={{ x: 0, transition: { duration: 0.28, ease: [0.16, 1, 0.3, 1] } }}
            exit={{ x: "100%", transition: { duration: 0.18, ease: [0.7, 0, 0.84, 0] } }}
            onClick={(e) => e.stopPropagation()}
            style={{ width, overscrollBehavior: "contain" }}
            className={cn(
              "absolute right-0 top-0 h-full bg-bg-elevated border-l border-border",
              "flex flex-col shadow-2xl focus:outline-none",
            )}
            role="dialog"
            aria-modal
            aria-labelledby={title ? titleId : undefined}
          >
            <header className="h-14 px-5 flex items-center justify-between border-b border-border shrink-0">
              <h2 id={titleId} className="text-sm font-semibold">
                {title}
              </h2>
              <button
                onClick={onClose}
                className="text-foreground-muted hover:text-foreground transition-colors"
                aria-label="關閉"
              >
                <X aria-hidden="true" className="w-5 h-5" />
              </button>
            </header>
            <div className="flex-1 overflow-y-auto scrollbar-slim">{children}</div>
          </motion.aside>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
