"use client";

export type RealtimeEvent = {
  id: number;
  type: string;
  data: Record<string, unknown>;
};

type Handlers = {
  onEvent: (ev: RealtimeEvent) => void;
  onStatus?: (s: "connecting" | "open" | "closed") => void;
};

const PRIORITY_ORDER: Record<string, number> = {
  high: 0,
  medium: 1,
  low: 2,
};

function priorityRank(ev: RealtimeEvent): number {
  if (ev.type === "resync") return -1;
  const p = ev.data?.priority;
  if (typeof p === "string" && p in PRIORITY_ORDER) return PRIORITY_ORDER[p]!;
  return 1;
}

function sortEventsForDelivery(events: RealtimeEvent[]): RealtimeEvent[] {
  return [...events].sort((a, b) => {
    const pa = priorityRank(a);
    const pb = priorityRank(b);
    if (pa !== pb) return pa - pb;
    return a.id - b.id;
  });
}

export type RealtimeSubscribeOptions = {
  /** Coalesce rapid events and refetch less often (ms). Set 0 to disable. Default 64. */
  debounceMs?: number;
};

function apiUrl(path: string): string {
  return `/api${path}`;
}

export function subscribeRealtime(handlers: Handlers, options?: RealtimeSubscribeOptions): () => void {
  const debounceMs = options?.debounceMs ?? 64;
  let closed = false;
  let es: EventSource | null = null;
  let retryMs = 1000;
  let lastId = 0;

  let pending: RealtimeEvent[] = [];
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;

  const flushPending = () => {
    debounceTimer = null;
    if (pending.length === 0) return;
    const batch = sortEventsForDelivery(pending);
    pending = [];
    for (const ev of batch) {
      handlers.onEvent(ev);
    }
  };

  const scheduleOrFlush = (ev: RealtimeEvent) => {
    if (debounceMs <= 0) {
      handlers.onEvent(ev);
      return;
    }
    const urgent = ev.type === "resync" || priorityRank(ev) === 0;
    if (urgent) {
      if (debounceTimer != null) {
        clearTimeout(debounceTimer);
        debounceTimer = null;
      }
      if (pending.length) {
        const batch = sortEventsForDelivery([...pending, ev]);
        pending = [];
        for (const e of batch) handlers.onEvent(e);
      } else {
        handlers.onEvent(ev);
      }
      return;
    }
    pending.push(ev);
    if (debounceTimer != null) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(flushPending, debounceMs);
  };

  const connect = () => {
    if (closed) return;
    handlers.onStatus?.("connecting");
    const url = new URL(apiUrl("/realtime/events/"), window.location.origin);
    if (lastId > 0) url.searchParams.set("last_id", String(lastId));
    es = new EventSource(url.toString());

    es.onopen = () => {
      retryMs = 1000;
      handlers.onStatus?.("open");
    };

    es.onmessage = (m) => {
      void m;
    };

    const handle = (type: string) => (m: MessageEvent) => {
      const id = Number((m as { lastEventId?: string }).lastEventId || 0);
      if (Number.isFinite(id) && id > 0) lastId = id;
      let data: Record<string, unknown> = {};
      try {
        data = m.data ? (JSON.parse(String(m.data)) as Record<string, unknown>) : {};
      } catch {
        data = {};
      }
      scheduleOrFlush({ id: lastId, type, data });
    };

    es.addEventListener("hello", handle("hello"));
    es.addEventListener("ping", handle("ping"));
    es.addEventListener("stream.updated", handle("stream.updated"));
    es.addEventListener("workspace.updated", handle("workspace.updated"));
    es.addEventListener("comments.updated", handle("comments.updated"));
    es.addEventListener("notifications.updated", handle("notifications.updated"));
    es.addEventListener("resync", handle("resync"));

    es.onerror = () => {
      handlers.onStatus?.("closed");
      try {
        es?.close();
      } catch {
        // ignore
      }
      es = null;
      if (closed) return;
      const wait = retryMs;
      retryMs = Math.min(30000, Math.floor(retryMs * 1.6));
      window.setTimeout(connect, wait);
    };
  };

  connect();

  return () => {
    closed = true;
    if (debounceTimer != null) clearTimeout(debounceTimer);
    flushPending();
    handlers.onStatus?.("closed");
    try {
      es?.close();
    } catch {
      // ignore
    }
    es = null;
  };
}
