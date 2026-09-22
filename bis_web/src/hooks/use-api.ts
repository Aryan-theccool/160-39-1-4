"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError } from "@/lib/api";

export interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
}

/**
 * Run an async function on mount and expose `{data, error, loading}`.
 *
 * Two details that matter more than they look:
 *
 * 1. **A stale response never overwrites a fresh one.** Type "cement", then
 *    "cement testing" before the first request lands, and without this the
 *    slower first response wins and the screen shows results for a query the
 *    user has already replaced. Each run gets a sequence number and only the
 *    newest may write.
 * 2. **Unmounting does not set state.** Navigating away mid-request would
 *    otherwise warn and leak.
 */
export function useAsync<T>(
  fn: () => Promise<T>,
  deps: unknown[],
  options: { skip?: boolean } = {},
) {
  const [state, setState] = useState<AsyncState<T>>({
    data: null,
    error: null,
    loading: !options.skip,
  });

  const seq = useRef(0);
  const mounted = useRef(true);
  const fnRef = useRef(fn);
  fnRef.current = fn;

  const run = useCallback(async () => {
    const mine = ++seq.current;
    setState((prev) => ({ ...prev, loading: true, error: null }));
    try {
      const data = await fnRef.current();
      if (mounted.current && mine === seq.current) {
        setState({ data, error: null, loading: false });
      }
      return data;
    } catch (error) {
      const apiError =
        error instanceof ApiError
          ? error
          : new ApiError(0, "unknown_error", String(error));
      if (mounted.current && mine === seq.current) {
        setState({ data: null, error: apiError, loading: false });
      }
      return null;
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    if (!options.skip) void run();
    return () => {
      mounted.current = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);

  return { ...state, reload: run, setData: (data: T | null) => setState({ data, error: null, loading: false }) };
}

/** Debounce a rapidly changing value -- used so search does not fire per keypress. */
export function useDebounced<T>(value: T, delay = 350): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}
