(function (root, factory) {
  const api = factory(root || {});
  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  }
  if (root) {
    root.PokerSfx = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : (typeof window !== "undefined" ? window : this), function (root) {
  const STORAGE_ENABLED = "poker_sfx_enabled";
  const STORAGE_VOLUME = "poker_sfx_volume";
  const DEFAULT_ENABLED = true;
  const DEFAULT_VOLUME = 0.6;
  const TIMER_WARNING_THRESHOLD = 5;

  function safeGet(storage, key) {
    try {
      return storage && typeof storage.getItem === "function" ? storage.getItem(key) : null;
    } catch {
      return null;
    }
  }

  function safeSet(storage, key, value) {
    try {
      if (storage && typeof storage.setItem === "function") {
        storage.setItem(key, String(value));
      }
    } catch {}
  }

  function parseEnabled(value, fallback = DEFAULT_ENABLED) {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") {
      const normalized = value.trim().toLowerCase();
      if (["1", "true", "yes", "on"].includes(normalized)) return true;
      if (["0", "false", "no", "off", ""].includes(normalized)) return false;
    }
    return fallback;
  }

  function parseVolume(value, fallback = DEFAULT_VOLUME) {
    const num = Number(value);
    if (!Number.isFinite(num)) return fallback;
    return Math.max(0, Math.min(1, num));
  }

  function handKeyFromState(state) {
    if (!state) return "";
    const roomId = String(state.room_id || "");
    const handNum = Number(state.hands_played ?? state.hand_number ?? 0) || 0;
    return `${roomId}:${handNum}`;
  }

  function actionLogFromState(state) {
    return Array.isArray(state && state.action_log) ? state.action_log : [];
  }

  function mapActionToSound(entry) {
    if (!entry) return null;
    const action = String(entry.action || "").toLowerCase();

    if (["ante", "small_blind", "big_blind", "big_blind_ante"].includes(action)) {
      return "chip_quiet";
    }
    if (action === "fold" || action === "timeout_fold") return "fold";
    if (action === "timeout_check") return "check";
    if (action === "check") return "check";
    if (action === "call") return "call";
    if (action === "check_call") {
      if (entry.is_all_in) return "all_in";
      return Number(entry.amount) > 0 ? "call" : "check";
    }
    if (action === "bet" || action === "raise" || action === "bet_raise") {
      return entry.is_all_in ? "all_in" : "bet_raise";
    }
    if (action === "all_in") return "all_in";
    if (action === "showdown") return "showdown";
    if (action === "pot_win") return "pot_win";
    if (action === "deal" || action === "card") return "deal";

    if (entry.is_all_in) return "all_in";
    return null;
  }

  function createTone(ctx, start, duration, frequency, gain, type = "sine") {
    const osc = ctx.createOscillator();
    const amp = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(frequency, start);
    amp.gain.setValueAtTime(0.0001, start);
    amp.gain.exponentialRampToValueAtTime(Math.max(0.0001, gain), start + 0.012);
    amp.gain.exponentialRampToValueAtTime(0.0001, start + duration);
    osc.connect(amp);
    amp.connect(ctx.destination);
    osc.start(start);
    osc.stop(start + duration + 0.03);
  }

  function playPattern(ctx, volume, pattern) {
    const base = ctx.currentTime + 0.01;
    pattern.forEach(step => {
      createTone(
        ctx,
        base + (step.start || 0),
        step.duration || 0.08,
        step.frequency || 440,
        (step.gain || 0.04) * volume,
        step.type || "sine",
      );
    });
  }

  function buildSynth() {
    return {
      deal(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.05, frequency: 960, gain: 0.045, type: "triangle" },
        ]);
      },
      chip_quiet(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.05, frequency: 740, gain: 0.03, type: "triangle" },
        ]);
      },
      check(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.045, frequency: 620, gain: 0.03, type: "sine" },
        ]);
      },
      call(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.05, frequency: 620, gain: 0.032, type: "triangle" },
          { start: 0.045, duration: 0.05, frequency: 520, gain: 0.022, type: "triangle" },
        ]);
      },
      bet_raise(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.06, frequency: 300, gain: 0.034, type: "square" },
          { start: 0.055, duration: 0.06, frequency: 420, gain: 0.03, type: "square" },
        ]);
      },
      fold(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.075, frequency: 170, gain: 0.03, type: "sawtooth" },
          { start: 0.055, duration: 0.06, frequency: 120, gain: 0.02, type: "sawtooth" },
        ]);
      },
      all_in(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.045, frequency: 260, gain: 0.036, type: "square" },
          { start: 0.05, duration: 0.045, frequency: 410, gain: 0.036, type: "square" },
          { start: 0.10, duration: 0.07, frequency: 620, gain: 0.04, type: "triangle" },
        ]);
      },
      showdown(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.06, frequency: 392, gain: 0.03, type: "sine" },
          { start: 0.055, duration: 0.06, frequency: 494, gain: 0.03, type: "sine" },
          { start: 0.11, duration: 0.08, frequency: 587, gain: 0.032, type: "sine" },
        ]);
      },
      pot_win(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.06, frequency: 523, gain: 0.035, type: "triangle" },
          { start: 0.05, duration: 0.06, frequency: 659, gain: 0.035, type: "triangle" },
          { start: 0.10, duration: 0.08, frequency: 784, gain: 0.04, type: "triangle" },
        ]);
      },
      timer_warning(ctx, volume) {
        playPattern(ctx, volume, [
          { start: 0.00, duration: 0.04, frequency: 880, gain: 0.03, type: "sine" },
          { start: 0.12, duration: 0.04, frequency: 880, gain: 0.03, type: "sine" },
        ]);
      },
    };
  }

  function createPokerSfx(options = {}) {
    const storage = options.storage || root.localStorage || null;
    const doc = options.document || root.document || null;
    const AudioContextCtor = options.audioContextCtor || root.AudioContext || root.webkitAudioContext || null;
    const playback = typeof options.playback === "function" ? options.playback : null;
    const synth = buildSynth();

    let enabled = parseEnabled(safeGet(storage, STORAGE_ENABLED), DEFAULT_ENABLED);
    let volume = parseVolume(safeGet(storage, STORAGE_VOLUME), DEFAULT_VOLUME);
    let unlocked = false;
    let ctx = null;
    let controls = { enabledInput: null, volumeInput: null, volumeValue: null };
    let controlsBound = false;
    let unlockListenerBound = false;
    let lastHandKey = "";
    let lastActionCount = 0;
    let lastShowdownKey = "";
    let lastPotWinKey = "";
    let lastTimerWarningKey = "";

    function persist() {
      safeSet(storage, STORAGE_ENABLED, enabled);
      safeSet(storage, STORAGE_VOLUME, volume);
    }

    function syncControls() {
      if (controls.enabledInput) {
        controls.enabledInput.checked = enabled;
        const label = controls.enabledInput.parentElement && controls.enabledInput.parentElement.querySelector("span");
        if (label) label.textContent = enabled ? "On" : "Off";
      }
      if (controls.volumeInput) {
        controls.volumeInput.value = String(volume);
      }
      if (controls.volumeValue) {
        controls.volumeValue.textContent = `${Math.round(volume * 100)}%`;
      }
    }

    function setEnabled(nextEnabled) {
      enabled = Boolean(nextEnabled);
      persist();
      syncControls();
    }

    function setVolume(nextVolume) {
      volume = parseVolume(nextVolume, volume);
      persist();
      syncControls();
    }

    function ensureContext() {
      if (ctx) return ctx;
      if (!AudioContextCtor) return null;
      try {
        ctx = new AudioContextCtor();
      } catch {
        ctx = null;
      }
      return ctx;
    }

    function unlock() {
      unlocked = true;
      const audio = ensureContext();
      if (audio && audio.state === "suspended" && typeof audio.resume === "function") {
        try { audio.resume(); } catch {}
      }
      return true;
    }

    function installUnlockListeners() {
      if (unlockListenerBound || !doc) return;
      unlockListenerBound = true;
      const handler = () => unlock();
      ["pointerdown", "keydown", "touchstart"].forEach(type => {
        doc.addEventListener(type, handler, { capture: true, once: true });
      });
    }

    function playSound(eventName, meta = {}, shouldEmit = true) {
      if (!eventName) return false;
      if (!shouldEmit) return false;
      if (!enabled || volume <= 0) return false;
      if (playback) {
        playback(eventName, meta);
        return true;
      }
      const audio = ensureContext();
      if (!audio || !unlocked) return false;
      const fn = synth[eventName];
      if (typeof fn !== "function") return false;
      try {
        fn(audio, volume, meta);
        return true;
      } catch {
        return false;
      }
    }

    function processState(state, options = {}) {
      if (!state) return;
      const emitSounds = !(options.historyReviewDisplay || state.__history_review);

      const handKey = handKeyFromState(state);
      const actionLog = actionLogFromState(state);
      const previousState = options.previousState || null;
      const prevHandKey = handKeyFromState(previousState);
      const sameHand = handKey && handKey === prevHandKey;

      if (handKey !== lastHandKey) {
        lastHandKey = handKey;
        lastActionCount = 0;
        lastShowdownKey = "";
        lastPotWinKey = "";
        lastTimerWarningKey = "";
      }

      if (actionLog.length < lastActionCount) {
        lastActionCount = 0;
      }

      for (let i = lastActionCount; i < actionLog.length; i += 1) {
        const entry = actionLog[i];
        const sound = mapActionToSound(entry, state);
        if (sound) {
          playSound(sound, { entry, index: i, state }, emitSounds);
        }
      }
      lastActionCount = actionLog.length;

      if (previousState && sameHand) {
        const prevCommunity = Array.isArray(previousState.community) ? previousState.community : [];
        const currCommunity = Array.isArray(state.community) ? state.community : [];
        if (currCommunity.length > prevCommunity.length) {
          playSound("deal", { state, previousState, addedCards: currCommunity.length - prevCommunity.length }, emitSounds);
        }
      }

      const showdownNow = state.phase === "showdown" || Boolean(state.showdown_mode);
      const showdownBefore = previousState
        ? (previousState.phase === "showdown" || Boolean(previousState.showdown_mode))
        : false;
      if (showdownNow && !showdownBefore && lastShowdownKey !== handKey) {
        playSound("showdown", { state, previousState }, emitSounds);
        lastShowdownKey = handKey;
      }

      const currentWinners = Array.isArray(state.winners) ? state.winners : [];
      const previousWinners = Array.isArray(previousState && previousState.winners) ? previousState.winners : [];
      if (currentWinners.length > 0 && previousWinners.length === 0 && lastPotWinKey !== handKey) {
        playSound("pot_win", { state, previousState, winners: currentWinners }, emitSounds);
        lastPotWinKey = handKey;
      }

      const timerPlayerId = String(state.action_timer_player_id || "");
      const timerRemaining = Number(state.action_timer_remaining_seconds);
      const timerKey = `${handKey}:${timerPlayerId}:${String(state.phase || "")}:${Number(state.current_bet) || 0}`;
      if (state.action_timer_active && timerPlayerId && Number.isFinite(timerRemaining) && timerRemaining <= TIMER_WARNING_THRESHOLD) {
        if (lastTimerWarningKey !== timerKey) {
          playSound("timer_warning", { state, previousState, remaining: timerRemaining }, emitSounds);
          lastTimerWarningKey = timerKey;
        }
      } else if (!state.action_timer_active || !timerPlayerId || !Number.isFinite(timerRemaining) || timerRemaining > TIMER_WARNING_THRESHOLD) {
        if (lastTimerWarningKey === timerKey && (!state.action_timer_active || timerRemaining > TIMER_WARNING_THRESHOLD)) {
          lastTimerWarningKey = "";
        }
      }
    }

    function bindControls(nextControls = {}) {
      controls = {
        enabledInput: nextControls.enabledInput || null,
        volumeInput: nextControls.volumeInput || null,
        volumeValue: nextControls.volumeValue || null,
      };
      if (controlsBound) {
        syncControls();
        return;
      }
      controlsBound = true;

      if (controls.enabledInput) {
        controls.enabledInput.addEventListener("change", () => setEnabled(controls.enabledInput.checked));
      }
      if (controls.volumeInput) {
        controls.volumeInput.addEventListener("input", () => setVolume(controls.volumeInput.value));
      }

      syncControls();
    }

    installUnlockListeners();
    syncControls();

    function playTestSound() {
      if (!enabled) setEnabled(true);
      if (volume <= 0) setVolume(0.7);
      unlock();
      // Slight delay gives suspended AudioContext.resume() a moment to settle.
      setTimeout(() => playSound("call", { test: true }, true), 25);
      return true;
    }

    return {
      bindControls,
      processState,
      setEnabled,
      setVolume,
      unlock,
      playSound: (eventName, meta = {}) => {
        unlock();
        return playSound(eventName, meta, true);
      },
      playTestSound,
      isEnabled: () => enabled,
      getVolume: () => volume,
      getState: () => ({
        enabled,
        volume,
        unlocked,
        audioState: ctx ? ctx.state : "none",
        handKey: lastHandKey,
        actionCount: lastActionCount,
      }),
      mapActionToSound,
      _storageKeys: { STORAGE_ENABLED, STORAGE_VOLUME },
    };
  }

  let browserInstance = null;

  function getInstance() {
    if (!browserInstance && root && root.document) {
      browserInstance = createPokerSfx({ document: root.document, storage: root.localStorage || null });
      root.pokerSfxDebug = browserInstance;
      root.PokerSfxInstance = browserInstance;
    }
    return browserInstance;
  }

  function installTestButton() {
    const inst = getInstance();
    const doc = root && root.document;
    if (!inst || !doc || doc.getElementById("soundTestBtn")) return;

    const volumeInput = doc.getElementById("soundVolumeInput");
    if (!volumeInput) return;

    const btn = doc.createElement("button");
    btn.id = "soundTestBtn";
    btn.type = "button";
    btn.className = "mini-btn sound-test-btn";
    btn.textContent = "Test sound";
    volumeInput.insertAdjacentElement("afterend", btn);

    btn.addEventListener("click", async () => {
      inst.setEnabled(true);
      if (inst.getVolume() <= 0) inst.setVolume(0.7);
      await inst.unlock();
      inst.playTestSound();
      console.log("[sfx] test", inst.getState());
    });
  }

  const api = {
    createPokerSfx,
    mapActionToSound,
    handKeyFromState,
    getInstance,
    bindControls: (...args) => getInstance() && getInstance().bindControls(...args),
    processState: (...args) => getInstance() && getInstance().processState(...args),
    setEnabled: (...args) => getInstance() && getInstance().setEnabled(...args),
    setVolume: (...args) => getInstance() && getInstance().setVolume(...args),
    unlock: (...args) => getInstance() && getInstance().unlock(...args),
    playSound: (...args) => getInstance() && getInstance().playSound(...args),
    playTestSound: (...args) => getInstance() && getInstance().playTestSound(...args),
    getState: () => getInstance() && getInstance().getState(),
  };

  if (root && root.document) {
    getInstance();
    if (root.document.readyState === "loading") {
      root.document.addEventListener("DOMContentLoaded", installTestButton);
    } else {
      installTestButton();
    }
  }

  return api;
});
