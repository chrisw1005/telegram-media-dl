import { cn } from "@/lib/cn";

export function Skeleton({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "bg-[rgb(var(--surface-hover-rgb)/0.08)] rounded animate-pulse",
        className,
      )}
      {...props}
    />
  );
}
