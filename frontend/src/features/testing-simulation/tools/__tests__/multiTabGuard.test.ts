import { beforeEach, describe, expect, it } from "vitest";
import { isFresh, lockKey, readLock, shouldOwn, STALE_MS } from "../useMultiTabGuard";

const KEY = lockKey(42);

describe("useMultiTabGuard — heartbeat ownership lock", () => {
  beforeEach(() => localStorage.clear());

  it("scopes the lock key per attempt", () => {
    expect(lockKey(42)).not.toEqual(lockKey(43));
  });

  it("reads a valid lock and rejects corrupt/partial storage", () => {
    localStorage.setItem(KEY, JSON.stringify({ id: "abc", ts: 123 }));
    expect(readLock(KEY)).toEqual({ id: "abc", ts: 123 });

    localStorage.setItem(KEY, "{not json");
    expect(readLock(KEY)).toBeNull();

    localStorage.setItem(KEY, JSON.stringify({ id: "abc" })); // missing ts
    expect(readLock(KEY)).toBeNull();
  });

  it("treats a lock as stale once no heartbeat lands within STALE_MS", () => {
    const now = 1_000_000;
    expect(isFresh({ id: "x", ts: now }, now)).toBe(true);
    expect(isFresh({ id: "x", ts: now - (STALE_MS - 1) }, now)).toBe(true);
    expect(isFresh({ id: "x", ts: now - STALE_MS }, now)).toBe(false);
    expect(isFresh(null, now)).toBe(false);
  });

  describe("shouldOwn — the single-owner decision", () => {
    const now = 1_000_000;

    it("claims a free lock (no orphaned blocked tab)", () => {
      expect(shouldOwn(null, "me", now)).toBe(true);
    });

    it("reclaims a stale lock (owner closed/crashed self-heals)", () => {
      expect(shouldOwn({ id: "dead", ts: now - STALE_MS }, "me", now)).toBe(true);
    });

    it("keeps a lock that is already ours (heartbeat refresh)", () => {
      expect(shouldOwn({ id: "me", ts: now }, "me", now)).toBe(true);
    });

    it("blocks when another tab holds a fresh lock", () => {
      expect(shouldOwn({ id: "other", ts: now }, "me", now)).toBe(false);
    });

    it("is convergent: against the same fresh foreign lock, exactly one of two ids owns", () => {
      const lock = { id: "other", ts: now };
      // Neither competing tab owns while 'other' is the fresh holder.
      expect(shouldOwn(lock, "me", now)).toBe(false);
      expect(shouldOwn(lock, "me2", now)).toBe(false);
      // The holder keeps it.
      expect(shouldOwn(lock, "other", now)).toBe(true);
    });
  });
});
