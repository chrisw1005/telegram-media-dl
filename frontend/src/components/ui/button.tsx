import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/cn";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-button font-medium transition-colors duration-fast ease-out disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        primary:
          "bg-primary text-white hover:brightness-110 shadow-[0_0_0_1px_rgba(59,130,246,0.3)]",
        secondary:
          "bg-bg-card text-foreground border border-border hover:bg-[rgb(var(--surface-hover-rgb)/0.06)]",
        ghost: "text-foreground hover:bg-[rgb(var(--surface-hover-rgb)/0.06)]",
        destructive: "bg-destructive text-white hover:brightness-110",
        icon: "text-foreground-muted hover:text-foreground hover:bg-[rgb(var(--surface-hover-rgb)/0.06)]",
      },
      size: {
        sm: "h-8 px-3 text-sm",
        md: "h-10 px-4 text-sm",
        lg: "h-12 px-6 text-base",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "primary", size: "md" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, onClick, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    const handleClick = (e: React.MouseEvent<HTMLButtonElement>) => {
      // subtle press feedback via CSS (active:scale-[0.97])
      onClick?.(e);
    };
    return (
      <Comp
        ref={ref as React.Ref<HTMLButtonElement>}
        className={cn(
          buttonVariants({ variant, size, className }),
          "active:scale-[0.97] transition-transform duration-fast",
        )}
        onClick={handleClick}
        {...props}
      />
    );
  },
);
Button.displayName = "Button";
