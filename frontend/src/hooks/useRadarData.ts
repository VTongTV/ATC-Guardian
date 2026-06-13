/** useRadarData — hook that polls the backend for radar snapshots. */

import { useCallback, useEffect, useRef } from "react";
import { useAtcStore } from "../stores/atcStore";
import type { RadarSnapshot } from "../lib/types";

/** Default backend URL (read from env at build time). */
const API_BASE_URL: string = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

/** Polling interval in milliseconds. */
const POLL_INTERVAL_MS = 4000;

/**
 * Custom hook that polls the backend `/data/simulated` endpoint
 * and updates the ATC Zustand store with the latest radar snapshot.
 *
 * @returns Object with a manual `refetch` callback and the current `isFetching` flag.
 */
export function useRadarData(): {
  refetch: () => Promise<void>;
  isFetching: boolean;
} {
  const setSnapshot = useAtcStore((s) => s.setSnapshot);
  const setLoading = useAtcStore((s) => s.setLoading);
  const setError = useAtcStore((s) => s.setError);
  const isLoading = useAtcStore((s) => s.isLoading);

  const isFetchingRef = useRef(false);

  const fetchData = useCallback(async (): Promise<void> => {
    if (isFetchingRef.current) return;
    isFetchingRef.current = true;
    setLoading(true);

    try {
      const response = await fetch(`${API_BASE_URL}/data/simulated`);

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
    fetchData();
    const interval = setInterval(fetchData, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [fetchData]);

  return { refetch: fetchData, isFetching: isLoading };
}
