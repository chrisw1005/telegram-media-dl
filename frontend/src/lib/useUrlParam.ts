import { useCallback, useEffect, useState } from "react";

/**
 * Two-way bind a single query-string key to local state. When the value equals
 * defaultValue the key is removed from the URL rather than serialized, so
 * defaults stay out of shareable links. Browser back/forward updates the
 * state.
 */
export function useUrlParam(
  key: string,
  defaultValue: string,
): [string, (next: string) => void] {
  const read = useCallback(() => {
    if (typeof window === "undefined") return defaultValue;
    return new URL(window.location.href).searchParams.get(key) ?? defaultValue;
  }, [key, defaultValue]);

  const [value, setValue] = useState<string>(read);

  useEffect(() => {
    const url = new URL(window.location.href);
    if (value === defaultValue) url.searchParams.delete(key);
    else url.searchParams.set(key, value);
    if (url.toString() !== window.location.href) {
      window.history.replaceState(null, "", url.toString());
    }
  }, [key, value, defaultValue]);

  useEffect(() => {
    const onPop = () => setValue(read());
    window.addEventListener("popstate", onPop);
    return () => window.removeEventListener("popstate", onPop);
  }, [read]);

  return [value, setValue];
}
