"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useAuthCriticalGate } from "@/hooks/useAuthCriticalGate";
import { useMe } from "@/hooks/useMe";

import { useExamAttempt } from "../hooks/useExamAttempt";
import { useAnswers } from "../hooks/useAnswers";
import { useModuleTimer } from "../hooks/useModuleTimer";
import { useModuleSubmit } from "../hooks/useModuleSubmit";
import { useAutosave } from "../hooks/useAutosave";
import { useMathRendering } from "../hooks/useMathRendering";

import { examApi } from "../services/examApiClient";
import { isCompleted, isModulePayloadMissing, isScoring } from "../state/attemptMerge";
import { isMath, moduleLabel, pauseAllowed, questions as selectQuestions, subjectKind } from "../state/selectors";
import { FIVE_MINUTE_WARNING_SECONDS } from "../utils/time";
import { clamp } from "../utils/time";
import { parseOptions } from "../utils/options";

import { ExamHeader } from "../components/ExamHeader";
import { SatColorRule } from "../components/SatColorRule";
import { PassagePane } from "../components/PassagePane";
import { AnswerPane } from "../components/AnswerPane";
import { ExamFooter } from "../components/ExamFooter";
import { QuestionNavigator } from "../components/QuestionNavigator";
import { ModuleTransitionOverlay } from "../components/ModuleTransitionOverlay";
import { ErrorScreen, LoadingScreen, ScoringScreen } from "../components/StatusScreens";
import { WelcomeScreen } from "../components/WelcomeScreen";
import { FullscreenWarning } from "../components/FullscreenWarning";
import { CheckYourWorkPage } from "../components/CheckYourWorkPage";
import { StudentProducedResponseGuide } from "../components/StudentProducedResponseGuide";
import { isStudentProducedResponse } from "../utils/questionKind";
import { ATTEMPT_STATE } from "../types";

import { useExamTools, ExamToolsLayer, MultiTabOverlay, useKeyboardShortcuts } from "../tools";
import { useMultiTabGuard } from "../tools/useMultiTabGuard";

/** Reflects browser connectivity so the runner can surface an offline state. */
function useOnlineStatus(): boolean {
  const [online, setOnline] = useState(typeof navigator === "undefined" ? true : navigator.onLine);
  useEffect(() => {
    const on = () => setOnline(true);
    const off = () => setOnline(false);
    window.addEventListener("online", on);
    window.addEventListener("offline", off);
    return () => {
      window.removeEventListener("online", on);
      window.removeEventListener("offline", off);
    };
  }, []);
  return online;
}

/**
 * Top-level Testing Simulation runner. Pure composition: it owns no engine
 * logic itself — it wires the attempt, timer, answers, submit and autosave
 * hooks together and lays out the SAT-style UI.
 */
export function ExamRunnerPage() {
  const router = useRouter();
  const params = useParams();
  const search = useSearchParams();
  const attemptId = Number(params.attemptId);
  const mockFlow = search.get("mockFlow") === "1";
  // Fresh pastpaper starts arrive with ?welcome=1 (set by the pastpaper card);
  // resumes don't, so they skip the welcome screen.
  const welcomeParam = search.get("welcome") === "1";

  const { assertCriticalAuth } = useAuthCriticalGate();
  // Load-error recovery actions are admin-only; students never see a Retry button.
  const { me } = useMe();
  const role = String((me as { role?: string } | undefined)?.role ?? "").toLowerCase();
  const isAdmin = role !== "" && role !== "student";
  // Student identity for the persistent footer (item: Student Identity Footer).
  const studentName = (() => {
    const u = me as { first_name?: string; last_name?: string } | undefined;
    return [u?.first_name, u?.last_name].filter(Boolean).join(" ").trim();
  })();

  // Multi-tab guard is resolved BEFORE the engine hooks so a blocked duplicate
  // tab can actually suspend polling/autosave/timer (not just show an overlay).
  const multiTab = useMultiTabGuard(attemptId);
  const online = useOnlineStatus();

  const { attempt, loading, error, clock, applyAttempt, reload, start } = useExamAttempt({
    attemptId,
    assertCriticalAuth,
    pollingEnabled: !multiTab.blocked,
    // Pastpapers hold the timer until the student clicks Start on the Welcome
    // screen; mock-exam flow keeps its existing auto-start (it has its own
    // break/intro orchestration upstream).
    autoStart: mockFlow,
  });

  const { answers, flagged, eliminated, currentIndex, moduleId, selectAnswer, toggleFlag, toggleEliminate, goTo, next, prev } =
    useAnswers(attempt, attemptId);

  const liveQuestions = useMemo(() => selectQuestions(attempt), [attempt]);
  const currentQuestion = liveQuestions[currentIndex];

  // ── SAT-experience tools (isolated from the engine) ─────────────────────────
  const tools = useExamTools({
    attemptId,
    questionId: currentQuestion?.id,
    // Highlightable regions — passage, question prompt/stem, and answer choices.
    // Each has its own offset space + storage, so annotations don't collide.
    getContainers: () => [
      { key: "passage", el: document.getElementById("ts-passage") },
      { key: "question", el: document.getElementById("ts-question") },
      { key: "choices", el: document.getElementById("ts-choices") },
    ],
  });

  // ── Local UI state ─────────────────────────────────────────────────────────
  const [paused, setPaused] = useState(false);
  const [eliminationMode, setEliminationMode] = useState(false);
  const [timerHidden, setTimerHidden] = useState(false);
  const [navigatorOpen, setNavigatorOpen] = useState(false);
  const [reviewOpen, setReviewOpen] = useState(false);
  const [showDirections, setShowDirections] = useState(false);
  // Welcome screen — shown once per fresh pastpaper start, acknowledged via the
  // Start button (persisted per attempt for the tab session so a refresh on the
  // running exam doesn't re-show it).
  const [welcomeAck, setWelcomeAck] = useState(() => {
    if (typeof window === "undefined") return false;
    try {
      return window.sessionStorage.getItem(`ts.welcomeAck.${attemptId}`) === "1";
    } catch {
      return false;
    }
  });
  const ackWelcome = useCallback(() => {
    setWelcomeAck(true);
    try {
      window.sessionStorage.setItem(`ts.welcomeAck.${attemptId}`, "1");
    } catch {
      /* sessionStorage unavailable — keep in-memory */
    }
  }, [attemptId]);
  const showWelcome = !mockFlow && welcomeParam && !welcomeAck;
  // SPR directions panel collapse state — persisted for the tab session so it is
  // remembered while navigating between Student-Produced Response questions.
  const [sprGuideExpanded, setSprGuideExpanded] = useState(() => {
    if (typeof window === "undefined") return true;
    try {
      const v = window.sessionStorage.getItem("ts.sprGuide.expanded");
      return v == null ? true : v === "1";
    } catch {
      return true;
    }
  });
  const toggleSprGuide = useCallback(() => {
    setSprGuideExpanded((v) => {
      const next = !v;
      try {
        window.sessionStorage.setItem("ts.sprGuide.expanded", next ? "1" : "0");
      } catch {
        /* sessionStorage unavailable — keep in-memory state */
      }
      return next;
    });
  }, []);
  const [splitPct, setSplitPct] = useState(50);
  const [transitionTo, setTransitionTo] = useState<number | null>(null);
  const zoom = tools.zoom;

  // ── Navigation freeze (item: Next / Back Freeze Protection) ──────────────────
  // After Next/Back, lock navigation for 500ms so a double-click (or held key)
  // can't skip a question or race the autosave/answer state. Visual feedback is
  // the disabled (dimmed) Back/Next buttons in the footer.
  const [navLocked, setNavLocked] = useState(false);
  const navLockTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (navLockTimer.current) clearTimeout(navLockTimer.current);
  }, []);
  const withNavLock = useCallback(
    (fn: () => void) => {
      if (navLocked) return;
      fn();
      setNavLocked(true);
      if (navLockTimer.current) clearTimeout(navLockTimer.current);
      navLockTimer.current = setTimeout(() => setNavLocked(false), 500);
    },
    [navLocked],
  );
  const guardedNext = useCallback(() => withNavLock(next), [withNavLock, next]);
  const guardedPrev = useCallback(() => withNavLock(prev), [withNavLock, prev]);

  // ── Welcome / start gate (items: Pastpaper Welcome Screen + Forced Fullscreen) ─
  // Start is the single user gesture that (a) enters fullscreen and (b) tells the
  // server to begin the module — so the timer genuinely doesn't run until now.
  const [starting, setStarting] = useState(false);
  const handleStart = useCallback(async () => {
    setStarting(true);
    try {
      if (tools.fullscreen.supported) {
        try {
          await tools.fullscreen.enter();
        } catch {
          /* user denied / unsupported — proceed without fullscreen */
        }
      }
      // Only call the engine start when the attempt genuinely hasn't begun
      // (forward-compatible with a future server-side timer hold). When the
      // backend already auto-started on create, Start just enters fullscreen.
      if (attempt?.current_state === ATTEMPT_STATE.NOT_STARTED) {
        await start();
      }
      ackWelcome();
    } finally {
      setStarting(false);
    }
  }, [tools.fullscreen, start, attempt?.current_state, ackWelcome]);

  // Close the Check Your Work page whenever the module changes (after a submit
  // advances M1→M2, or a fresh module loads) so it never lingers over new work.
  useEffect(() => {
    setReviewOpen(false);
  }, [attempt?.current_module_details?.id]);

  // ── Forced-fullscreen enforcement ────────────────────────────────────────────
  // Only enforce while the student is ACTIVELY in a pastpaper module — never on
  // the welcome/loading/scoring/transition/review screens, and never for mock
  // flow (which auto-starts with no Start gesture to establish fullscreen). This
  // prevents the countdown from ever firing where the student isn't actually
  // taking the test.
  const fsIsFull = tools.fullscreen.isFullscreen;
  const fsSupported = tools.fullscreen.supported;
  const fsEnforced =
    !mockFlow &&
    !showWelcome &&
    !multiTab.blocked &&
    transitionTo === null &&
    !reviewOpen &&
    !loading &&
    Boolean(currentQuestion) &&
    (attempt?.current_state === ATTEMPT_STATE.MODULE_1_ACTIVE ||
      attempt?.current_state === ATTEMPT_STATE.MODULE_2_ACTIVE);

  // Show the "return to fullscreen" overlay only after the student has stayed OUT
  // of fullscreen for a short grace window — so the native enter/exit transition
  // and the brief Start→enter gap never flash the modal. Hidden on re-entry.
  const [showFsWarning, setShowFsWarning] = useState(false);
  const fsWarnTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (fsWarnTimer.current) {
      clearTimeout(fsWarnTimer.current);
      fsWarnTimer.current = null;
    }
    if (!fsSupported || !fsEnforced || fsIsFull) {
      setShowFsWarning(false);
      return;
    }
    fsWarnTimer.current = setTimeout(() => setShowFsWarning(true), 400);
    return () => {
      if (fsWarnTimer.current) clearTimeout(fsWarnTimer.current);
    };
  }, [fsIsFull, fsSupported, fsEnforced]);

  // Off-fullscreen kick: once the warning is showing (student stayed out of
  // fullscreen past the grace window), count down 10s; if they don't return,
  // save their progress and remove them from the test (resumable via Save & Exit).
  const [fsCountdown, setFsCountdown] = useState<number | null>(null);
  const fsKickRef = useRef<(() => void) | null>(null);
  useEffect(() => {
    if (!showFsWarning) {
      setFsCountdown(null);
      return;
    }
    let remaining = 10;
    setFsCountdown(remaining);
    const iv = setInterval(() => {
      remaining -= 1;
      setFsCountdown(remaining);
      if (remaining <= 0) {
        clearInterval(iv);
        fsKickRef.current?.();
      }
    }, 1000);
    return () => clearInterval(iv);
  }, [showFsWarning]);

  // Keyboard shortcuts (pure input → existing handlers; no engine coupling).
  useKeyboardShortcuts({
    enabled: !loading && Boolean(currentQuestion) && transitionTo === null && !multiTab.blocked,
    onPrev: guardedPrev,
    onNext: guardedNext,
    onToggleMark: () => currentQuestion && toggleFlag(currentQuestion.id),
    onToggleNavigator: () => setNavigatorOpen((v) => !v),
    onToggleHelp: tools.toggleHelp,
    onSelectChoice: (idx) => {
      if (!currentQuestion || currentQuestion.is_math_input) return;
      const key = parseOptions(currentQuestion)[idx]?.key;
      if (key) selectAnswer(currentQuestion.id, key);
    },
  });

  // ── Submit (manual + auto on expiry) ────────────────────────────────────────
  const { submit, submitting, submitError, clearSubmitError } = useModuleSubmit({
    attemptId,
    attempt,
    answers,
    flagged,
    applyAttempt,
    assertCriticalAuth,
  });

  const onExpire = useCallback(() => {
    void submit();
  }, [submit]);

  const { secondsLeft, ready: timerReady } = useModuleTimer({
    attempt,
    clock,
    // A blocked duplicate tab must not run the countdown or auto-submit.
    paused: (paused && pauseAllowed(attempt, mockFlow)) || multiTab.blocked,
    onExpire,
  });

  // Autosave only while genuinely interactive (not submitting / transitioning /
  // paused, and never from a blocked duplicate tab). Runs for its side effect;
  // the header no longer surfaces a save indicator (work is also locally drafted).
  useAutosave({
    attempt,
    attemptId,
    answers,
    flagged,
    answersModuleId: moduleId,
    applyAttempt,
    enabled: !submitting && transitionTo === null && !(paused && pauseAllowed(attempt, mockFlow)) && !multiTab.blocked,
    online,
  });

  const mathQuestions = isMath(attempt);
  // Midterms never offer a calculator (same signal used by pauseAllowed). Reference sheet stays.
  const isMidtermExam = attempt?.practice_test_details?.mock_kind === "MIDTERM";
  useMathRendering(!loading && Boolean(attempt?.current_module_details), `${moduleId}:${currentIndex}`);

  // ── Timer warnings: 5 min, 1 min, expiry (per module; read-only on the clock) ─
  const [timerToast, setTimerToast] = useState<string | null>(null);
  const firedRef = useRef<{ moduleId: number | null; fired: Set<number> }>({ moduleId: null, fired: new Set() });
  useEffect(() => {
    if (!timerReady || moduleId == null) return;
    const f = firedRef.current;
    if (f.moduleId !== moduleId) {
      f.moduleId = moduleId;
      f.fired = new Set();
    }
    const fire = (at: number, msg: string) => {
      if (!f.fired.has(at)) {
        f.fired.add(at);
        setTimerToast(msg);
      }
    };
    if (secondsLeft <= 0) fire(0, "Time's up — submitting this module…");
    else if (secondsLeft <= 60) fire(60, "1 minute remaining in this module.");
    else if (secondsLeft <= 300) fire(300, "5 minutes remaining in this module.");
  }, [secondsLeft, timerReady, moduleId]);
  useEffect(() => {
    if (!timerToast) return;
    const t = setTimeout(() => setTimerToast(null), 8000);
    return () => clearTimeout(t);
  }, [timerToast]);


  // ── Sync pause state from server, once per attempt load (mocks never pause) ───
  const syncedPauseRef = useRef<number | null>(null);
  useEffect(() => {
    if (!attempt) return;
    if (!pauseAllowed(attempt, mockFlow)) {
      setPaused(false);
      return;
    }
    if (syncedPauseRef.current === attempt.id) return;
    syncedPauseRef.current = attempt.id;
    setPaused(Boolean(attempt.is_paused));
  }, [attempt, mockFlow]);

  // ── Module transition overlay: show briefly when the module order increases ──
  const prevOrderRef = useRef(0);
  useEffect(() => {
    const order = attempt?.current_module_details?.module_order ?? 0;
    if (prevOrderRef.current > 0 && order > prevOrderRef.current) {
      const to = order;
      setTransitionTo(to);
      const t = setTimeout(() => setTransitionTo(null), 1800);
      prevOrderRef.current = order;
      return () => clearTimeout(t);
    }
    if (order > 0) prevOrderRef.current = order;
  }, [attempt?.current_module_details?.module_order]);

  // ── Route out on completion (respecting mock flow) ──────────────────────────
  useEffect(() => {
    if (!attempt || !isCompleted(attempt)) return;
    const meid = search.get("mockExamId");
    const kind = subjectKind(attempt);
    if (mockFlow && meid && kind === "READING_WRITING") {
      router.push(`/mock/${meid}/break?rwAttempt=${attemptId}`);
      return;
    }
    if (mockFlow && meid && kind === "MATH") {
      const rw = search.get("rwAttempt");
      const qs = rw ? `?rwAttempt=${encodeURIComponent(rw)}&mathAttempt=${attemptId}` : `?mathAttempt=${attemptId}`;
      router.push(`/mock/${meid}/results${qs}`);
      return;
    }
    router.push(`/review/${attemptId}`);
  }, [attempt, mockFlow, search, router, attemptId]);

  // ── Resizable split divider ─────────────────────────────────────────────────
  const mainRef = useRef<HTMLDivElement | null>(null);
  const draggingRef = useRef(false);
  const onDividerDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    draggingRef.current = true;
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, []);
  useEffect(() => {
    const move = (e: MouseEvent) => {
      if (!draggingRef.current || !mainRef.current) return;
      const rect = mainRef.current.getBoundingClientRect();
      if (rect.width <= 0) return;
      setSplitPct(clamp(((e.clientX - rect.left) / rect.width) * 100, 28, 72));
    };
    const up = () => {
      draggingRef.current = false;
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
    return () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
  }, []);

  const handlePauseToggle = useCallback(async () => {
    if (!attempt || !pauseAllowed(attempt, mockFlow)) return;
    const nextPaused = !paused;
    setPaused(nextPaused); // optimistic
    try {
      const snap = nextPaused ? await examApi.pause(attemptId) : await examApi.resumePause(attemptId);
      applyAttempt(snap);
    } catch {
      setPaused(!nextPaused); // revert on failure
    }
  }, [attempt, mockFlow, paused, attemptId, applyAttempt]);

  // ── Save & Exit ─────────────────────────────────────────────────────────────
  // Force-majeure stop: persist current work (and pause the clock where allowed),
  // then leave. Returning to /exam/[id] resumes exactly where the student left
  // off. Uses the existing save/pause services — the engine itself is untouched.
  const [exiting, setExiting] = useState(false);
  const handleSaveAndExit = useCallback(async () => {
    setExiting(true);
    try {
      if (attempt && pauseAllowed(attempt, mockFlow)) {
        try {
          applyAttempt(await examApi.pause(attemptId));
        } catch {
          /* best-effort pause */
        }
      }
      applyAttempt(await examApi.saveAttempt(attemptId, answers, flagged, { expectedVersionNumber: attempt?.version_number }));
    } catch {
      /* progress is also continuously autosaved; proceed to exit regardless */
    } finally {
      router.push("/");
    }
  }, [attempt, mockFlow, attemptId, answers, flagged, applyAttempt, router]);

  // Keep the off-fullscreen kick action current without restarting the countdown
  // when handleSaveAndExit's identity changes (e.g. on autosave).
  useEffect(() => {
    fsKickRef.current = handleSaveAndExit;
  }, [handleSaveAndExit]);

  // ── Render gates ────────────────────────────────────────────────────────────
  const questions = liveQuestions;
  const twoPane = !mathQuestions; // RW shows passage + answers; Math is single column

  // A duplicate tab must not run a second timer/poller for the same attempt.
  // (Engine hooks above are already suspended via pollingEnabled / paused / enabled.)
  if (multiTab.blocked) {
    return <MultiTabOverlay onContinue={multiTab.takeOver} />;
  }

  if (exiting) {
    return <LoadingScreen label="Saving your progress…" />;
  }

  if (error) {
    return (
      <ErrorScreen
        title="Could not open the exam"
        message={error}
        {...(isAdmin ? { actionLabel: "Retry", onAction: reload } : { hint: "Please contact your teacher or administrator if this continues." })}
      />
    );
  }
  if (transitionTo !== null) {
    return <ModuleTransitionOverlay toModuleOrder={transitionTo} subjectLabel={moduleLabel(attempt)} />;
  }
  if (isScoring(attempt)) {
    return <ScoringScreen notice={null} />;
  }
  // Welcome / Start screen for a NOT_STARTED attempt (forward-compatible with a
  // future server-side timer hold). Today the backend auto-starts on create, so
  // the active-attempt branch below is the one that fires.
  if (showWelcome && !loading && attempt && attempt.current_state === ATTEMPT_STATE.NOT_STARTED) {
    const startMinutes =
      attempt.current_module_details?.time_limit_minutes ??
      attempt.practice_test_details.modules.find((m) => m.module_order === 1)?.time_limit_minutes;
    return (
      <WelcomeScreen
        moduleTitle={moduleLabel(attempt)}
        subjectLabel={subjectKind(attempt) === "MATH" ? "Math" : "Reading and Writing"}
        minutes={startMinutes}
        questionCount={attempt.current_module_details?.questions.length}
        starting={starting}
        fullscreenSupported={tools.fullscreen.supported}
        onStart={() => void handleStart()}
      />
    );
  }
  if (loading || !attempt || !attempt.current_module_details || !currentQuestion) {
    if (isModulePayloadMissing(attempt)) {
      return (
        <ErrorScreen
          title="Module failed to load"
          message="The attempt loaded but its module payload is missing. This is usually a transient server/network issue."
          {...(isAdmin ? { actionLabel: "Force refresh", onAction: reload } : { hint: "Please contact your teacher or administrator if this continues." })}
        />
      );
    }
    return <LoadingScreen />;
  }

  // Fresh-start welcome (active attempt). The backend auto-starts on create, so
  // by now the module is loaded; show the welcome until the student clicks Start
  // (which enters fullscreen + acknowledges it). Resumes have no ?welcome=1.
  if (showWelcome) {
    return (
      <WelcomeScreen
        moduleTitle={moduleLabel(attempt)}
        subjectLabel={subjectKind(attempt) === "MATH" ? "Math" : "Reading and Writing"}
        minutes={attempt.current_module_details.time_limit_minutes}
        questionCount={attempt.current_module_details.questions.length}
        starting={starting}
        fullscreenSupported={tools.fullscreen.supported}
        onStart={() => void handleStart()}
      />
    );
  }

  const warning = timerReady && secondsLeft <= FIVE_MINUTE_WARNING_SECONDS && secondsLeft > 0;

  // Check Your Work review page — shown before the module is submitted.
  if (reviewOpen) {
    const moduleOrder = attempt.current_module_details?.module_order ?? 1;
    const isLastModule = moduleOrder >= (attempt.practice_test_details.modules.length || 2);
    return (
      <CheckYourWorkPage
        moduleTitle={moduleLabel(attempt)}
        questions={questions}
        answers={answers}
        flagged={flagged}
        onJump={(i) => {
          goTo(i);
          setReviewOpen(false);
        }}
        onBack={() => setReviewOpen(false)}
        onSubmit={() => void submit()}
        submitting={submitting}
        isLastModule={isLastModule}
        studentName={studentName}
      />
    );
  }

  return (
    <div className="flex h-screen flex-col bg-white">
      <ExamHeader
        moduleTitle={moduleLabel(attempt)}
        secondsLeft={secondsLeft}
        timerHidden={timerHidden}
        onToggleTimer={() => setTimerHidden((v) => !v)}
        timerWarning={warning}
        showDirections={showDirections}
        onToggleDirections={() => setShowDirections((v) => !v)}
        mathTools={mathQuestions}
        showCalculator={mathQuestions && !isMidtermExam}
        tools={tools}
        pauseAllowed={pauseAllowed(attempt, mockFlow)}
        paused={paused}
        onTogglePause={handlePauseToggle}
        onSaveAndExit={handleSaveAndExit}
      />
      <SatColorRule />

      <main
        ref={mainRef}
        className={`flex min-h-0 flex-1 overflow-hidden ${tools.highlighterActive ? "ts-annotating [&_#ts-passage]:cursor-text [&_#ts-question]:cursor-text [&_#ts-choices]:cursor-text" : ""}`}
      >
        {twoPane ? (
          <>
            <PassagePane question={currentQuestion} zoom={zoom} style={{ width: `${splitPct}%`, flex: "none" }} />
            <div
              onMouseDown={onDividerDown}
              className="w-1 shrink-0 cursor-col-resize bg-slate-200 transition-colors hover:bg-blue-400"
              role="separator"
              aria-orientation="vertical"
            />
            <AnswerPane
              question={currentQuestion}
              displayNumber={currentIndex + 1}
              zoom={zoom}
              isMath={mathQuestions}
              flagged={flagged.includes(currentQuestion.id)}
              onToggleFlag={() => toggleFlag(currentQuestion.id)}
              eliminationMode={eliminationMode}
              onToggleEliminationMode={() => setEliminationMode((v) => !v)}
              answer={answers[currentQuestion.id]}
              eliminated={eliminated[currentQuestion.id] ?? []}
              onSelect={(v) => selectAnswer(currentQuestion.id, v)}
              onEliminate={(k) => toggleEliminate(currentQuestion.id, k)}
              style={{ width: `${100 - splitPct}%`, flex: "none" }}
            />
          </>
        ) : (
          <>
            {/* Calculator floats over the content (see ExamToolsLayer); it never
                reserves layout space, so the question column stays stable. */}
            {/* Student-Produced Response Directions — left column, SPR questions
                only (item: SPR Directions Panel). Collapsible to give the
                question more width; state persists across SPR questions. */}
            {isStudentProducedResponse(currentQuestion) && (
              <div
                className="h-full shrink-0 overflow-hidden transition-[width] duration-300 ease-out"
                style={{ width: sprGuideExpanded ? "min(46%, 640px)" : "3rem" }}
              >
                <StudentProducedResponseGuide expanded={sprGuideExpanded} onToggle={toggleSprGuide} />
              </div>
            )}
            <AnswerPane
              question={currentQuestion}
              displayNumber={currentIndex + 1}
              zoom={zoom}
              isMath={mathQuestions}
              flagged={flagged.includes(currentQuestion.id)}
              onToggleFlag={() => toggleFlag(currentQuestion.id)}
              eliminationMode={eliminationMode}
              onToggleEliminationMode={() => setEliminationMode((v) => !v)}
              answer={answers[currentQuestion.id]}
              eliminated={eliminated[currentQuestion.id] ?? []}
              onSelect={(v) => selectAnswer(currentQuestion.id, v)}
              onEliminate={(k) => toggleEliminate(currentQuestion.id, k)}
              style={{ flex: "1 1 0%", minWidth: 0 }}
              // SPR questions already show the directions panel on the left, so
              // don't also reserve calculator space (that pushes the question
              // off-screen); Desmos floats over the directions instead.
              calcReserve={
                tools.calculatorOpen && !isStudentProducedResponse(currentQuestion)
                  ? tools.calculatorEnlarged
                    ? 760
                    : 500
                  : 0
              }
            />
          </>
        )}
      </main>

      <SatColorRule />
      <ExamFooter
        navLabel={`Question ${currentIndex + 1} of ${questions.length}`}
        onToggleNavigator={() => setNavigatorOpen((v) => !v)}
        canGoBack={currentIndex > 0}
        onBack={guardedPrev}
        isLastQuestion={currentIndex === questions.length - 1}
        onNext={guardedNext}
        onSubmitModule={() => setReviewOpen(true)}
        submitting={submitting}
        studentName={studentName}
        navLocked={navLocked}
      />

      <QuestionNavigator
        open={navigatorOpen}
        onClose={() => setNavigatorOpen(false)}
        title={moduleLabel(attempt)}
        questions={questions}
        currentIndex={currentIndex}
        answers={answers}
        flagged={flagged}
        onJump={goTo}
        onGoToReview={() => setReviewOpen(true)}
      />

      {/* All SAT-experience tool overlays (calculator, reference, notes, help,
          highlight popover). Single mount point; each is engine-isolated. */}
      <ExamToolsLayer tools={tools} attemptId={attemptId} />

      {/* Forced fullscreen — if the student leaves fullscreen mid-test, block the
          UI until they re-enter (the only path is a user-gesture button). Gated on
          a short grace window (showFsWarning) so it never flickers during the
          native fullscreen transition. Unsupported browsers never see this. */}
      {showFsWarning && (
        <FullscreenWarning secondsLeft={fsCountdown ?? undefined} onReturn={() => void tools.fullscreen.enter()} />
      )}

      {/* Timer warnings (5 min / 1 min / expiry) — announced to screen readers. */}
      {timerToast && (
        <div
          role="alert"
          aria-live="assertive"
          className="fixed left-1/2 top-20 z-[65] -translate-x-1/2 rounded-xl bg-slate-900 px-5 py-3 text-sm font-bold text-white shadow-xl"
        >
          {timerToast}
        </div>
      )}

      {/* Recoverable submit failure — available to EVERY user, not just admins. */}
      {submitError && (
        <div role="alert" className="fixed inset-x-0 bottom-20 z-[65] flex justify-center px-4">
          <div className="flex max-w-md items-center gap-4 rounded-xl border border-red-200 bg-white px-5 py-3 shadow-xl">
            <span className="text-sm font-semibold text-slate-700">{submitError}</span>
            <button
              type="button"
              onClick={() => {
                clearSubmitError();
                void submit();
              }}
              disabled={submitting}
              className="shrink-0 rounded-lg bg-blue-600 px-4 py-2 text-sm font-bold text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {submitting ? "Submitting…" : "Try again"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
