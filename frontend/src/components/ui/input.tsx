import * as React from "react";
import { cn } from "@/lib/cn";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "w-full h-11 px-3 rounded-button bg-bg-card border border-border text-foreground placeholder:text-foreground-muted text-base",
      "transition-colors duration-fast focus:border-primary focus:outline-none",
      className,
    )}
    {...props}
  />
));
Input.displayName = "Input";
