# Testing Simulation

The SAT exam runner (the digital-Bluebook-style exam-taking experience), rebuilt
from scratch as a self-contained, modular feature. Replaces the legacy 2772-line
monolith at `app/exam/[attemptId]/page.tsx` (now a 3-line route shell).

## Principles

- **Server-authoritative.** The backend (`backend/exams/`) owns the timer, state
  machine, scoring, and concurrency. The client renders truth and submits intent;
  it never invents timing or state. The device clock cannot speed up or bypass it.
- **Single responsibility.** Each hook owns exactly one concern. No component
  holds more than its own UI state.
- **Forward-only state.** Every snapshot is merged through `state/attemptMerge`,
  which rejects stale/regressing polls. Pure and unit-tested.
- **Typed at the boundary.** Every network payload is validated by Zod
  (`types/attempt.ts`); the rest of the module trusts its types.

## Layout

```
testing-simulation/
├── types/        attempt.ts (Zod contract + parse), index.ts (view types)
├── utils/        time, options, idempotency, image  (pure, no React)
├── services/     examApiClient (typed 6-endpoint client), draftStore (offline backup)
├── state/        attemptMerge (forward-only guard), selectors (derived views)  — pure
├── hooks/        useServerClock, useModuleTimer, useExamAttempt, useAnswers,
│                 useModuleSubmit, useAutosave, useMathRendering
├── components/   ExamHeader, Timer, PassagePane, AnswerPane, ChoiceList,
│                 SprInput, QuestionNavigator, ExamFooter, ModuleTransitionOverlay,
│                 StatusScreens
├── pages/        ExamRunnerPage (composition root)
└── __tests__/    attemptMerge, utils, draftStore
```

## Data flow

```
ExamRunnerPage
 ├─ useExamAttempt ──── owns Attempt; load + start + poll(active/scoring) + merge
 │     └─ useServerClock  calibrates clock from server_now (anti-cheat)
 ├─ useModuleTimer ──── server-anchored countdown; onExpire → submit
 ├─ useAnswers ──────── per-module answers/flags/eliminations + navigation
 ├─ useModuleSubmit ─── lock + idempotency + 409 reconcile + watchdog + retry
 ├─ useAutosave ─────── debounced save_attempt + local draft (module-id guarded)
 └─ useMathRendering ── KaTeX re-render on DOM mutation
```

## Backend contract (wire-compatible, unchanged)

`GET status/` · `POST start/` · `POST pause/` · `POST resume_pause/` ·
`POST submit_module/` · `POST save_attempt/` — all return a `TestAttempt`.
States: `NOT_STARTED → MODULE_1_ACTIVE → MODULE_2_ACTIVE → SCORING → COMPLETED`.

## SAT-experience tools (`tools/`) — engine-isolated

Added in the SAT Experience Phase. **None of these import or mutate an engine
hook** (timer/autosave/transitions/submit/scoring). They are pure UI + local
persistence, aggregated by `useExamTools` and mounted via `<ExamToolsLayer>`:

```
tools/
├── FloatingPanel.tsx          draggable/resizable window (shared)
├── calculator/                Calculator.tsx + expression.ts (safe evaluator, no eval)
├── ReferenceSheet.tsx         SAT Math reference figures
├── useFullscreen.ts           Fullscreen API wrapper
├── highlight/                 offsets.ts (char-range ↔ DOM) + store + useHighlighter + popover
├── notes/                     NotesPanel + notesStore (localStorage, never submitted)
├── MoreMenu.tsx               secondary-tool dropdown (fullscreen/highlight/notes/zoom/pause/help)
├── KeyboardShortcutsHelp.tsx  + useKeyboardShortcuts.ts (←/→, A–D, M, R, ?)
├── MultiTabOverlay.tsx        + useMultiTabGuard.ts (BroadcastChannel, oldest tab wins)
├── useExamTools.ts            aggregates all tool state
└── ExamToolsLayer.tsx         single mount point for all overlays
```

Isolation contract: tools persist only to `localStorage` (highlights, notes) and
never to the backend; the page wires them through callbacks. Highlights are
stored as character offsets (not HTML) so they survive React re-renders.

**Verified:** tsc + eslint clean; 34 unit tests pass (engine 23 + tools 11:
expression evaluator, highlight offset engine). Static-checked; a live Playwright
regression run against staging is recommended before deploy.
