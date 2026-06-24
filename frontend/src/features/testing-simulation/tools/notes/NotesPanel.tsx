"use client";
import { useEffect, useState } from "react";
import { FloatingPanel } from "../FloatingPanel";
import { readNotes, writeNotes } from "./notesStore";

interface NotesPanelProps {
  attemptId: number | string;
  onClose: () => void;
}

/** Scratch-notes pad. Local-only; persisted per attempt. Never sent to backend. */
export function NotesPanel({ attemptId, onClose }: NotesPanelProps) {
  const [value, setValue] = useState("");

  useEffect(() => {
    setValue(readNotes(attemptId));
  }, [attemptId]);

  return (
    <FloatingPanel title="Notes" onClose={onClose} initial={{ x: 260, y: 130, w: 360, h: 420 }} minW={260} minH={220}>
      <div className="flex h-full flex-col p-3">
        <textarea
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            writeNotes(attemptId, e.target.value);
          }}
          placeholder="Scratch notes (saved locally on this device, never submitted)…"
          className="h-full w-full resize-none rounded-lg border border-slate-200 p-3 text-sm leading-relaxed text-slate-800 outline-none focus:border-blue-500"
        />
      </div>
    </FloatingPanel>
  );
}
