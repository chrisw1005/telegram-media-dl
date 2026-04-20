/** @type {import('tailwindcss').Config} */
export default {
  darkMode: "class",
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        "bg-base": "rgb(var(--bg-base) / <alpha-value>)",
        "bg-elevated": "rgb(var(--bg-elevated) / <alpha-value>)",
        "bg-card": "rgb(var(--bg-card) / <alpha-value>)",
        foreground: "rgb(var(--foreground) / <alpha-value>)",
        "foreground-muted": "rgb(var(--foreground-muted) / <alpha-value>)",
        primary: {
          DEFAULT: "rgb(var(--primary) / <alpha-value>)",
          glow: "rgb(var(--primary) / 0.25)",
        },
        "accent-success": "rgb(var(--accent-success) / <alpha-value>)",
        "accent-warn": "rgb(var(--accent-warn) / <alpha-value>)",
        destructive: "rgb(var(--destructive) / <alpha-value>)",
        border: "rgb(var(--border) / <alpha-value>)",
        ring: "rgb(var(--ring) / <alpha-value>)",
        "surface-hover": "rgb(var(--surface-hover-rgb) / <alpha-value>)",
      },
      fontFamily: {
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "monospace"],
      },
      fontVariantNumeric: {
        tabular: "tabular-nums",
      },
      borderRadius: {
        card: "12px",
        button: "8px",
      },
      transitionTimingFunction: {
        out: "cubic-bezier(0.16, 1, 0.3, 1)",
        in: "cubic-bezier(0.7, 0, 0.84, 0)",
      },
      transitionDuration: {
        fast: "120ms",
        base: "200ms",
        page: "280ms",
        exit: "180ms",
      },
      keyframes: {
        "pulse-ring": {
          "0%, 100%": { opacity: "0.5" },
          "50%": { opacity: "1" },
        },
        shimmer: {
          "0%": { backgroundPosition: "-200% 0" },
          "100%": { backgroundPosition: "200% 0" },
        },
        "flash-success": {
          "0%": { backgroundColor: "rgb(var(--accent-success) / 0.2)" },
          "100%": { backgroundColor: "transparent" },
        },
      },
      animation: {
        shimmer: "shimmer 1.5s linear infinite",
        "flash-success": "flash-success 0.5s ease-out forwards",
      },
    },
  },
  plugins: [],
};
