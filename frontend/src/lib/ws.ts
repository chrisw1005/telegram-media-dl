export type WsHandler = (msg: unknown) => void;

export function connectWs(
  path: string,
  onMessage: WsHandler,
  onOpen?: () => void,
): { close: () => void } {
  let ws: WebSocket | null = null;
  let closed = false;
  let retries = 0;

  const open = () => {
    const url = (location.protocol === "https:" ? "wss://" : "ws://") + location.host + path;
    ws = new WebSocket(url);
    ws.onopen = () => {
      retries = 0;
      onOpen?.();
    };
    ws.onmessage = (ev) => {
      try {
        onMessage(JSON.parse(ev.data));
      } catch {
        onMessage(ev.data);
      }
    };
    ws.onclose = () => {
      if (closed) return;
      const delay = Math.min(5000, 500 * 2 ** retries);
      retries += 1;
      setTimeout(open, delay);
    };
    ws.onerror = () => ws?.close();
  };

  open();

  return {
    close() {
      closed = true;
      ws?.close();
    },
  };
}
