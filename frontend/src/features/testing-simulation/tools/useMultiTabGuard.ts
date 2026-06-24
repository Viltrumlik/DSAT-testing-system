"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * Single-tab ownership for an attempt, backed by a `localStorage` heartbeat lock.
 *
 * Why a lock and not just a BroadcastChannel announce: the engine (polling,
 * autosave, timer/auto-submit) is suspended on `blocked`, so ownership has to be
 * (1) decided *synchronously* at mount — no async round-trip during which a
 * duplicate tab could fire a save; (2) self-healing — if the owner tab closes or
 * crashes, a surviving tab must reclaim instead of staying locked forever; and
 * (3) deadlock-free across a refresh of the owner.
 *
 * Model: the owner writes `{ id, ts }` to `ts.owner.<attemptId>` and refreshes
 * `ts` on a heartbeat. A lock is "stale" once no heartbeat has landed within
 * STALE_MS. Any tab that finds the lock free / stale / already its own claims it
 * and runs; otherwise it blocks. Cross-tab `storage` events make hand-off
 * instant; the heartbeat interval is the fallback that heals crashes. Purely
 * advisory to the engine — it only flips a boolean the page reads.
 */

export const STALE_MS = 6000;
const HEARTBEAT_MS = 2000;

interface Lock {
  id: string;
  ts: number;
}

export function lockKey(attemptId: number | string): string {
  return `ts.owner.${attemptId}`;
}

export function readLock(key: string): Lock | null {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return null;
    const v = JSON.parse(raw) as Partial<Lock>;
    return typeof v?.id === "string" && typeof v?.ts === "number" ? { id: v.id, ts: v.ts } : null;
  } catch {
    return null;
  }
}

export function isFresh(lock: Lock | null, now: number = Date.now()): lock is Lock {
  return !!lock && now - lock.ts < STALE_MS;
}

/**
 * Pure ownership decision: a tab takes (or keeps) the lock when it's free, stale,
 * or already its own; otherwise it must block. Heart of the single-tab guard,
 * extracted so it can be tested without rendering.
 */
export function shouldOwn(lock: Lock | null, myId: string, now: number = Date.now()): boolean {
  return !isFresh(lock, now) || lock.id === myId;
}

export function useMultiTabGuard(attemptId: number | string) {
  const idRef = useRef(Math.random().toString(36).slice(2));

  // Decide ownership synchronously on the very first render so a duplicate tab
  // never gets even one frame where the engine sees `blocked === false`.
  const [blocked, setBlocked] = useState<boolean>(() => {
    if (typeof window === "undefined") return false;
    const lock = readLock(lockKey(attemptId));
    return isFresh(lock) && lock.id !== idRef.current;
  });

  useEffect(() => {
    if (typeof window === "undefined") return;
    const key = lockKey(attemptId);
    const me = idRef.current;

    const claim = () => {
      try {
        localStorage.setItem(key, JSON.stringify({ id: me, ts: Date.now() } satisfies Lock));
      } catch {
        /* private mode / quota — fall back to advisory-only, never block the exam */
      }
    };

    // Take ownership if the lock is free, stale, or already ours; else block.
    const evaluate = () => {
      if (shouldOwn(readLock(key), me)) {
        claim();
        setBlocked(false);
      } else {
        setBlocked(true);
      }
    };

    evaluate();

    // Re-read on any cross-tab write (claim, heartbeat, or release). Re-reading
    // current storage (not the event payload) keeps concurrent claims convergent:
    // whoever wrote last owns the key; everyone else reads that and blocks.
    const onStorage = (e: StorageEvent) => {
      if (e.key !== null && e.key !== key) return;
      evaluate();
    };
    window.addEventListener("storage", onStorage);

    // Heartbeat: owners refresh their timestamp; blocked tabs reclaim a lock that
    // has gone stale (owner closed/crashed) — this is what heals an orphan.
    const hb = setInterval(evaluate, HEARTBEAT_MS);

    // Release on unload/unmount so a surviving tab claims instantly instead of
    // waiting out STALE_MS, and so refreshing the owner can't deadlock.
    const release = () => {
      if (readLock(key)?.id === me) {
        try {
          localStorage.removeItem(key);
        } catch {
          /* ignore */
        }
      }
    };
    window.addEventListener("beforeunload", release);

    return () => {
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("beforeunload", release);
      clearInterval(hb);
      release();
    };
  }, [attemptId]);

  /** "Continue in this tab" — forcibly claim ownership; other tabs will block. */
  const takeOver = useCallback(() => {
    try {
      localStorage.setItem(lockKey(attemptId), JSON.stringify({ id: idRef.current, ts: Date.now() } satisfies Lock));
    } catch {
      /* ignore */
    }
    setBlocked(false);
  }, [attemptId]);

  return { blocked, takeOver };
}
