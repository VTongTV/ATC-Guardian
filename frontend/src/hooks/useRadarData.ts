/** useRadarData — hook that connects to the backend WebSocket for real-time radar data.

Replaces HTTP polling with a persistent WebSocket connection.
The server pushes RadarSnapshot JSON on every simulation tick.
Falls back to HTTP polling if WebSocket connection fails.
*/

import { useCallback, useEffect, useRef } from "react";
import { useAtcStore } from "../stores/atcStore";
import type { RadarSnapshot } from "../lib/types";

/** WebSocket base URL. In dev, Vite proxies /ws to the backend. */
const WS_BASE_URL: string = import.meta.env.VITE_WS_URL ?? "";

/** HTTP fallback base URL for polling. */
const HTTP_BASE_URL: string = import.meta.env.VITE_API_URL ?? "";

/** Polling interval in milliseconds (fallback mode only). */
const POLL_INTERVAL_MS = 4000;

/** Reconnect delay in milliseconds after WebSocket disconnect. */
const RECONNECT_DELAY_MS = 3000;

/**
 * Custom hook that connects to the backend WebSocket for real-time
 * radar data, with automatic reconnection and HTTP polling fallback.
 */
export function useRadarData(): {
  refetch: () => Promise<void>;
  isFetching: boolean;
} {
  const setSnapshot = useAtcStore((s) => s.setSnapshot);
  const setLoading = useAtcStore((s) => s.setLoading);
  const setError = useAtcStore((s) => s.setError);
  const isLoading = useAtcStore((s) => s.isLoading);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isFetchingRef = useRef(false);

  const processSnapshot = useCallback(
    (data: unknown) => {
      const snapshot = data as RadarSnapshot;
      setSnapshot(snapshot);
    },
    [setSnapshot],
  );

  const connectWebSocket = useCallback(() => {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const host = WS_BASE_URL
      ? WS_BASE_URL.replace(/^https?:\/\//, "").replace(/^wss?:\/\//, "")
      : `${window.location.host}`;
    const wsUrl = `${protocol}//${host}/ws/radar`;

    try {
      const ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setLoading(false);
        setError(null);
        logger.info("WebSocket connected to %s", wsUrl);
      };

      ws.onmessage = (event: MessageEvent) => {
        try {
          const data = JSON.parse(event.data as string) as RadarSnapshot;
          processSnapshot(data);
        } catch {
          logger.error("Failed to parse WebSocket message");
        }
      };

      ws.onclose = () => {
        logger.info("WebSocket disconnected, reconnecting in %dms", RECONNECT_DELAY_MS);
        reconnectTimerRef.current = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
      };

      ws.onerror = () => {
        setError("WebSocket connection failed, falling back to HTTP polling");
        ws.close();
      };

      wsRef.current = ws;
    } catch {
      setError("Failed to create WebSocket, using HTTP polling fallback");
    }
  }, [processSnapshot, setError, setLoading]);

  /** HTTP polling fallback — used when WebSocket fails. */
  const fetchViaHttp = useCallback(async (): Promise<void> => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    setLoading(true);

    try {
      const response = await fetch(`${HTTP_BASE_URL}/data/simulated`);
      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }
      const snapshot: RadarSnapshot = await response.json();
      setSnapshot(snapshot);
    } catch (err) {
      const message = err instanceof Error ? err.message : "Unknown fetch error";
      setError(message);
    } finally {
      isFetchingRef.current = false;
    }
  }, [setSnapshot, setLoading, setError]);

  useEffect(() => {
    setLoading(true);
    connectWebSocket();

    // Also do an initial HTTP fetch for immediate data while WS connects
    fetchViaHttp();

    // Set up HTTP polling as fallback if WS never connects
    const interval = setInterval(fetchViaHttp, POLL_INTERVAL_MS);

    return () => {
      if (wsRef.current) {
        wsRef.current.onclose = null; // Prevent reconnect on cleanup
        wsRef.current.close();
      }
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      clearInterval(interval);
    };
  }, [connectWebSocket, fetchViaHttp, setLoading]);

  return { refetch: fetchViaHttp, isFetching: isLoading };
}

/** Minimal logger for the hook. */
const logger = {
  info: (...args: unknown[]) => console.log("[useRadarData]", ...args),
  error: (...args: unknown[]) => console.error("[useRadarData]", ...args),
};
