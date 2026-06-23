// ═══════════════════════════════════════════════════════════════
// CUTE POKER – Debug Table Client (minimal, no animations)
// Direct state rendering. No overlays, no animations, no timers.
// ═══════════════════════════════════════════════════════════════

// ─── DOM refs ───
const $ = id => document.getElementById(id);
const els = {};
["status","connectScreen","gameScreen","nameInput","roomInput","createBtn","joinBtn",
"reconnectBtn","roomsList","roomId","phaseBadge","potValue","community","playerPositions",
"winnerOverlay","winnerContent","yourHandBar","yourCards","handStrength","startBtn",
"foldBtn","checkCallBtn","betHalfPotBtn","betPotBtn","betAllInBtn","customBetInput",
"customBetBtn","resetBtn","adminActions","copyRoomBtn","leaveBtn","chatToggle","chatClose",
"chatPanel","chatMessages","chatInput","chatBtn","actionBar","turnInfo",
"pauseBtn","sitOutBtn","spectateBtn","addBotBtn","removeBotBtn","botDifficultySelect",
"hintsToggle","bbToggleBtn","potChips","autoDealToggle","autoDealCountdown","outsBox"
].forEach(id => { els[id] = $(id); });

// ─── State ───
let ws = null;
let roomId = localStorage.getItem("poker_room_id") || "";
let token = localStorage.getItem("poker_token") || "";
let lastState = null;
let selectedAvatar = localStorage.getItem("poker_avatar") || "🎭";
let reconnectAttempts = 0;
let reconnectTimer = null;
let intentionalDisconnect = false;

// ─── Helpers ───
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function makeCardHtml(card) {
  if (card === "🂠") return '<div class="playing-card card-back">🂠</div>';
  const red = card.includes("♥") || card.includes("♦") ? " red" : "";
  return `<div class="playing-card${red}">${esc(card)}</div>`;
}

function safeGetItem(key) { try { return localStorage.getItem(key); } catch { return null; } }
function safeSetItem(key, val) { try { localStorage.setItem(key, val); } catch {} }

// ─── Name persistence ───
function loadSavedPlayerName() {
  const saved = safeGetItem("poker_player_name");
  if (saved && saved.trim()) els.nameInput.value = saved;
}
function savePlayerName(name) {
  const t = (name || "").trim().slice(0, 20);
  if (t) safeSetItem("poker_player_name", t);
}

// ─── Avatar picker ───
document.querySelectorAll(".avatar-opt").forEach(el => {
  if (el.dataset.av === selectedAvatar) el.classList.add("selected");
  else el.classList.remove("selected");
  el.onclick = () => {
    document.querySelectorAll(".avatar-opt").forEach(e => e.classList.remove("selected"));
    el.classList.add("selected");
    selectedAvatar = el.dataset.av;
    localStorage.setItem("poker_avatar", selectedAvatar);
  };
});

// ─── Room settings / game history toggles ───
document.addEventListener("DOMContentLoaded", () => {
  const histHeader = document.querySelector(".game-history-header");
  const histBody = document.querySelector(".game-history-body");
  if (histHeader && histBody) {
    histHeader.addEventListener("click", () => {
      const exp = histHeader.getAttribute("aria-expanded") === "true";
      histHeader.setAttribute("aria-expanded", !exp);
      histBody.classList.toggle("collapsed", exp);
      histBody.classList.toggle("expanded", !exp);
    });
  }
  const settHeader = document.querySelector(".room-settings-header");
  const settBody = document.querySelector(".room-settings-body");
  if (settHeader && settBody) {
    settHeader.addEventListener("click", () => {
      settBody.classList.toggle("collapsed");
    });
  }
});

// ─── Seat positions (8 max) ───
const SEAT_POSITIONS = [
  { top: "78%", left: "50%" },
  { top: "65%", left: "10%" },
  { top: "30%", left: "5%" },
  { top: "5%",  left: "25%" },
  { top: "5%",  left: "75%" },
  { top: "30%", left: "95%" },
  { top: "65%", left: "90%" },
  { top: "5%",  left: "50%" },
];

// ═══════════════════════════════════════════════════════════════
// WebSocket
// ═══════════════════════════════════════════════════════════════
function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return ws;
  intentionalDisconnect = false;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    reconnectAttempts = 0;
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    els.status.textContent = "";
    fetchRooms();
  };

  ws.onmessage = ev => {
    const { event, payload } = JSON.parse(ev.data);
    if (event === "joined") {
      roomId = payload.room_id;
      token = payload.token;
      localStorage.setItem("poker_room_id", roomId);
      localStorage.setItem("poker_token", token);
      els.connectScreen.classList.add("hidden");
      els.gameScreen.classList.remove("hidden");
    }
    if (event === "state") renderState(payload);
    if (event === "left") leaveToLobby();
    if (event === "rooms_list") renderRoomsList(payload.rooms);
    if (event === "error" || event === "reconnect_failed") {
      els.status.textContent = payload.message;
      if (event === "reconnect_failed") {
        roomId = ""; token = "";
        localStorage.removeItem("poker_room_id");
        localStorage.removeItem("poker_token");
        els.gameScreen.classList.add("hidden");
        els.connectScreen.classList.remove("hidden");
        reconnectAttempts = 0;
        fetchRooms();
      }
    }
  };

  ws.onclose = () => {
    els.status.textContent = "Disconnected.";
    ws = null;
    if (!intentionalDisconnect) attemptReconnect();
  };

  return ws;
}

function send(event, payload = {}) {
  const s = connect();
  const finalPayload = { room_id: roomId, token, ...payload };
  const msg = JSON.stringify({ event, payload: finalPayload });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function fetchRooms() {
  const s = connect();
  const msg = JSON.stringify({ event: "list_rooms", payload: {} });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function attemptReconnect() {
  if (intentionalDisconnect || !roomId || !token) return;
  const delay = Math.min(1000 * Math.pow(2, reconnectAttempts), 10000);
  reconnectAttempts++;
  els.status.textContent = `Reconnecting... (attempt ${reconnectAttempts})`;

  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    if (intentionalDisconnect) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => {
      reconnectAttempts = 0;
      els.status.textContent = "";
      ws.send(JSON.stringify({ event: "reconnect", payload: { room_id: roomId, token } }));
    };
    ws.onmessage = ev => {
      const { event, payload } = JSON.parse(ev.data);
      if (event === "joined") {
        roomId = payload.room_id; token = payload.token;
        localStorage.setItem("poker_room_id", roomId);
        localStorage.setItem("poker_token", token);
        els.connectScreen.classList.add("hidden");
        els.gameScreen.classList.remove("hidden");
      }
      if (event === "state") renderState(payload);
      if (event === "left") leaveToLobby();
      if (event === "rooms_list") renderRoomsList(payload.rooms);
      if (event === "error" || event === "reconnect_failed") {
        els.status.textContent = payload.message;
        if (event === "reconnect_failed") {
          roomId = ""; token = "";
          localStorage.removeItem("poker_room_id");
          localStorage.removeItem("poker_token");
          els.gameScreen.classList.add("hidden");
          els.connectScreen.classList.remove("hidden");
          reconnectAttempts = 0;
          fetchRooms();
        }
      }
    };
    ws.onclose = () => {
      ws = null;
      if (!intentionalDisconnect) attemptReconnect();
    };
  }, delay);
}

// ═══════════════════════════════════════════════════════════════
// Room list / lobby
// ═══════════════════════════════════════════════════════════════
function renderRoomsList(rooms) {
  if (!rooms || rooms.length === 0) { els.roomsList.innerHTML = ""; return; }
  els.roomsList.innerHTML = `<div class="rooms-list-title">Active Rooms</div>` +
    rooms.map(r => `<div class="room-item" data-id="${r.room_id}">
      <span class="room-item-id">${r.room_id}</span>
      <span class="room-item-info">${r.connected}/${r.max} · ${r.phase}</span>
    </div>`).join("");
  els.roomsList.querySelectorAll(".room-item").forEach(el => {
    el.onclick = () => { els.roomInput.value = el.dataset.id; joinRoom(); };
  });
}

function leaveToLobby() {
  roomId = ""; token = "";
  localStorage.removeItem("poker_room_id");
  localStorage.removeItem("poker_token");
  els.gameScreen.classList.add("hidden");
  els.connectScreen.classList.remove("hidden");
  els.winnerOverlay.classList.add("hidden");
  lastState = null;
  connect();
  setTimeout(fetchRooms, 300);
}

// ═══════════════════════════════════════════════════════════════
// Actions
// ═══════════════════════════════════════════════════════════════
function createRoom() {
  savePlayerName(els.nameInput.value);
  const blindIncrease = parseInt(document.getElementById("blindIncreaseInput")?.value || "0", 10);
  const ante = parseInt(document.getElementById("anteInput")?.value || "0", 10);
  const anteMode = document.getElementById("anteModeSelect")?.value || "classic";
  const autoAnte = document.getElementById("autoAnteCheck")?.checked || false;
  send("create", {
    name: els.nameInput.value || "Player",
    avatar: selectedAvatar,
    blind_increase_hands: blindIncrease || 0,
    ante: ante || 0,
    ante_mode: anteMode,
    auto_ante: autoAnte,
  });
}

function joinRoom() {
  savePlayerName(els.nameInput.value);
  const targetRoom = els.roomInput.value.trim().toUpperCase();
  roomId = targetRoom;
  token = "";
  send("join", { name: els.nameInput.value || "Player", room_id: targetRoom, token: "", avatar: selectedAvatar });
}

function reconnectLast() {
  roomId = localStorage.getItem("poker_room_id") || "";
  token = localStorage.getItem("poker_token") || "";
  if (!roomId || !token) { els.status.textContent = "No saved session."; return; }
  send("reconnect", { room_id: roomId, token });
}

function action(name, extra = {}) { send("action", { action: name, ...extra }); }

function leaveGame() {
  intentionalDisconnect = true;
  try { send("leave", {}); } catch(e) {}
  setTimeout(leaveToLobby, 200);
}

// ═══════════════════════════════════════════════════════════════
// Render state — pure DOM update, no animations
// ═══════════════════════════════════════════════════════════════
function renderState(state) {
  lastState = state;

  // ─── HUD ───
  els.roomId.textContent = state.room_id;
  els.phaseBadge.textContent = state.paused ? "PAUSED" : state.phase.toUpperCase();
  els.potValue.textContent = state.pot;

  // Pot label
  const potLabel = document.querySelector(".pot-label");
  if (potLabel) potLabel.textContent = state.phase === "showdown" ? "FINAL POT" : "POT";

  // Blind info
  const blindEl = document.getElementById("blindInfo");
  if (blindEl) {
    let txt = `${state.small_blind}/${state.big_blind}`;
    if (state.ante > 0) txt += state.ante_mode === "bba" ? " +BBA" : ` +${state.ante}a`;
    if (state.blind_increase_hands > 0) {
      const until = state.blind_increase_hands - (state.hands_played % state.blind_increase_hands);
      txt += ` · ↑${until}h`;
    }
    blindEl.textContent = txt;
  }

  // Pot chips (just text, no chip visual)
  if (els.potChips) els.potChips.innerHTML = "";

  // ─── Turn indicator ───
  const isMyTurn = state.viewer && state.viewer.is_turn;
  if (isMyTurn) {
    els.turnInfo.textContent = state.viewer.to_call > 0
      ? `⚡ YOUR TURN · Call ${state.viewer.to_call}` : "⚡ YOUR TURN";
    els.turnInfo.className = "turn-indicator your-turn";
    els.actionBar.classList.add("my-turn");
  } else {
    els.turnInfo.textContent = "";
    els.turnInfo.className = "turn-indicator";
    els.actionBar.classList.remove("my-turn");
  }

  // ─── Winners in pot area (text, no overlay) ───
  if (state.winners && state.winners.length > 0 && state.phase === "showdown") {
    const winTxt = state.winners.map(w =>
      `${esc(w.name)} wins ${w.amount} (${esc(w.hand_name || w.reason || "")})`
    ).join(" | ");
    els.potValue.textContent = `${state.pot} — ${winTxt}`;
    els.winnerOverlay.classList.add("hidden");
  } else {
    els.winnerOverlay.classList.add("hidden");
  }

  // ─── Deal button visible in showdown/lobby ───
  const canDeal = ["lobby", "showdown"].includes(state.phase) && !state.paused;
  els.startBtn.style.display = canDeal ? "" : "none";

  // ─── Admin panel ───
  if (state.viewer && state.viewer.is_admin) {
    els.adminActions.classList.remove("hidden");
    if (els.pauseBtn) els.pauseBtn.textContent = state.paused ? "▶ Resume" : "⏸ Pause";
  } else {
    els.adminActions.classList.add("hidden");
  }

  // ─── Sit out / spectate ───
  const viewerData = state.players.find(p => p.is_you);
  if (els.sitOutBtn && viewerData) {
    els.sitOutBtn.textContent = viewerData.sitting_out ? "Sit In" : "Sit Out";
    const inHand = ["preflop","flop","turn","river"].includes(state.phase);
    const canSitOut = !viewerData.is_spectator && (!inHand || viewerData.folded || !viewerData.cards || viewerData.cards.length === 0);
    els.sitOutBtn.style.display = canSitOut ? "" : "none";
  }
  if (els.spectateBtn && viewerData) {
    els.spectateBtn.textContent = viewerData.is_spectator ? "Join Game" : "Spectate";
    els.spectateBtn.style.display = ["lobby","showdown"].includes(state.phase) ? "" : "none";
  }

  // ─── Community cards ───
  renderCommunity(state.community);

  // ─── Your hand ───
  renderYourHand(viewerData);

  // ─── Player seats ───
  renderPlayers(state.players);

  // ─── Chat ───
  renderChat(state.messages);

  // ─── Action button labels ───
  if (isMyTurn) {
    els.checkCallBtn.textContent = state.viewer.to_call > 0 ? `Call ${state.viewer.to_call}` : "Check";
    els.customBetInput.placeholder = `Min ${state.current_bet + state.min_raise}`;
  } else {
    els.checkCallBtn.textContent = "Check / Call";
    els.customBetInput.placeholder = "Raise to...";
  }

  // Hide outs box (removed feature)
  if (els.outsBox) els.outsBox.classList.add("hidden");
  // Hide auto-deal countdown
  if (els.autoDealCountdown) els.autoDealCountdown.classList.add("hidden");
  if (els.autoDealToggle) els.autoDealToggle.style.display = "none";
}

// ─── Community cards ───
function renderCommunity(cards) {
  if (!cards || cards.length === 0) { els.community.innerHTML = ""; return; }
  els.community.innerHTML = cards.map(makeCardHtml).join("");
}

// ─── Your hand ───
function renderYourHand(viewer) {
  if (!viewer || !viewer.cards || viewer.cards.length === 0) {
    els.yourHandBar.classList.add("hand-bar-hidden");
    els.yourCards.innerHTML = "";
    els.handStrength.textContent = "";
    return;
  }
  els.yourHandBar.classList.remove("hand-bar-hidden");
  els.yourCards.innerHTML = viewer.cards.map(makeCardHtml).join("");
  els.handStrength.textContent = viewer.hand_name || "";
}

// ─── Players around table ───
function renderPlayers(players) {
  els.playerPositions.innerHTML = "";

  players.forEach((p, idx) => {
    const pos = SEAT_POSITIONS[idx % SEAT_POSITIONS.length];
    const seat = document.createElement("div");
    let cls = "player-seat";
    if (p.is_turn) cls += " active-turn";
    if (p.folded) cls += " folded";
    if (p.is_you) cls += " is-you";
    seat.className = cls;
    seat.style.top = pos.top;
    seat.style.left = pos.left;
    seat.style.transform = "translate(-50%, -50%)";

    // Badges
    const badges = [];
    if (p.is_you) badges.push('<span class="seat-badge">YOU</span>');
    if (p.is_dealer) badges.push('<span class="seat-badge">D</span>');
    if (p.is_bot) badges.push('<span class="seat-badge">🤖</span>');
    if (p.all_in) badges.push('<span class="seat-badge">ALL-IN</span>');
    if (p.folded) badges.push('<span class="seat-badge warn">FOLD</span>');
    if (!p.connected && !p.is_bot) badges.push('<span class="seat-badge warn">DC</span>');
    if (p.sitting_out) badges.push('<span class="seat-badge warn">SIT OUT</span>');
    if (p.is_spectator) badges.push('<span class="seat-badge">👁</span>');

    // Cards (other players, not you)
    let cards = "";
    if (p.cards && p.cards.length > 0 && !p.is_you) {
      cards = `<div class="seat-cards">${p.cards.map(makeCardHtml).join("")}</div>`;
    }

    seat.innerHTML = `
      <div class="seat-header">
        <span class="seat-avatar">${p.avatar || "🎭"}</span>
        <span class="seat-name">${esc(p.name)}</span>
        <span class="seat-stack">💰${p.stack}</span>
      </div>
      <div class="seat-badges">${badges.join("")}</div>
      ${cards}
      ${p.committed > 0 ? `<div class="seat-meta">Bet: ${p.committed}</div>` : ""}
      ${p.hand_name ? `<div class="seat-meta" style="color:var(--gold-light)">${esc(p.hand_name)}</div>` : ""}
    `;
    els.playerPositions.appendChild(seat);
  });
}

// ─── Chat ───
function renderChat(messages) {
  if (!messages) return;
  els.chatMessages.innerHTML = messages.map(m =>
    `<div class="chat-msg"><span class="chat-name">${esc(m.name)}:</span> ${esc(m.text)}</div>`
  ).join("");
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

// ═══════════════════════════════════════════════════════════════
// Event handlers
// ═══════════════════════════════════════════════════════════════
els.createBtn.onclick = createRoom;
els.joinBtn.onclick = joinRoom;
els.reconnectBtn.onclick = reconnectLast;
els.leaveBtn.onclick = leaveGame;
els.startBtn.onclick = () => action("start_hand");
els.foldBtn.onclick = () => action("fold");
els.checkCallBtn.onclick = () => action("check_call");
els.betHalfPotBtn.onclick = () => {
  if (!lastState) return;
  action("bet_raise", { amount: Math.max(lastState.current_bet + lastState.min_raise, lastState.current_bet + Math.floor(lastState.pot / 2)) });
};
els.betPotBtn.onclick = () => {
  if (!lastState) return;
  action("bet_raise", { amount: Math.max(lastState.current_bet + lastState.min_raise, lastState.current_bet + lastState.pot) });
};
els.betAllInBtn.onclick = () => {
  if (!lastState) return;
  action("bet_raise", { amount: lastState.viewer.committed + lastState.viewer.stack });
};
els.customBetBtn.onclick = () => {
  const v = parseInt(els.customBetInput.value, 10);
  if (v > 0) { action("bet_raise", { amount: v }); els.customBetInput.value = ""; }
};
els.customBetInput.onkeydown = ev => { if (ev.key === "Enter") els.customBetBtn.click(); };
els.resetBtn.onclick = () => action("reset_stacks");
els.pauseBtn.onclick = () => action("toggle_pause");
els.addBotBtn.onclick = () => {
  const diff = els.botDifficultySelect ? els.botDifficultySelect.value : "hard";
  action("add_bot", { difficulty: diff });
};
els.removeBotBtn.onclick = () => action("remove_bot");
els.sitOutBtn.onclick = () => action("sit_out");
els.spectateBtn.onclick = () => action("spectate");
els.copyRoomBtn.onclick = async () => { try { await navigator.clipboard.writeText(roomId); } catch {} };

// Chat
els.chatToggle.onclick = () => els.chatPanel.classList.toggle("hidden");
els.chatClose.onclick = () => els.chatPanel.classList.add("hidden");
els.chatBtn.onclick = () => {
  const t = els.chatInput.value.trim();
  if (t) { send("chat", { text: t }); els.chatInput.value = ""; }
};
els.chatInput.onkeydown = ev => { if (ev.key === "Enter") els.chatBtn.click(); };

// Hints toggle (kept but simplified — no outs box rendering)
if (els.hintsToggle) els.hintsToggle.onclick = () => {};

// BB toggle — just a no-op now (values shown as raw chips)
if (els.bbToggleBtn) els.bbToggleBtn.style.display = "none";

// ═══════════════════════════════════════════════════════════════
// Init
// ═══════════════════════════════════════════════════════════════
loadSavedPlayerName();

if (roomId && token) {
  reconnectLast();
} else {
  roomId = ""; token = "";
  connect();
  setTimeout(fetchRooms, 500);
}
