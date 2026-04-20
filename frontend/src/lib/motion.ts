import type { Variants } from "framer-motion";

export const easeOut = [0.16, 1, 0.3, 1] as const;
export const easeIn = [0.7, 0, 0.84, 0] as const;

export const fadeUp: Variants = {
  hidden: { opacity: 0, y: 8 },
  show: { opacity: 1, y: 0, transition: { duration: 0.2, ease: easeOut } },
  exit: { opacity: 0, y: 4, transition: { duration: 0.12, ease: easeIn } },
};

export const pageFade: Variants = {
  hidden: { opacity: 0, scale: 1.02 },
  show: { opacity: 1, scale: 1, transition: { duration: 0.28, ease: easeOut } },
  exit: { opacity: 0, scale: 0.98, transition: { duration: 0.18, ease: easeIn } },
};

export const sheetSlide: Variants = {
  hidden: { x: "100%", opacity: 0 },
  show: { x: 0, opacity: 1, transition: { duration: 0.28, ease: easeOut } },
  exit: { x: "100%", opacity: 0, transition: { duration: 0.18, ease: easeIn } },
};

export const pressScale: Variants = {
  rest: { scale: 1 },
  tap: { scale: 0.97, transition: { duration: 0.12, ease: easeOut } },
};

export const thumbEnter: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  show: (i: number = 0) => ({
    opacity: 1,
    scale: 1,
    transition: { delay: i * 0.04, duration: 0.2, ease: easeOut },
  }),
};

export const modalPop: Variants = {
  hidden: { opacity: 0, scale: 0.96 },
  show: {
    opacity: 1,
    scale: 1,
    transition: { type: "spring", damping: 22, stiffness: 180 },
  },
  exit: { opacity: 0, scale: 0.98, transition: { duration: 0.18, ease: easeIn } },
};

export const crossfade: Variants = {
  hidden: { opacity: 0 },
  show: { opacity: 1, transition: { duration: 0.15 } },
  exit: { opacity: 0, transition: { duration: 0.1 } },
};
