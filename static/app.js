// ═══════════════════════════════════════════════════════════════
// CUTE POKER – Client v3 (bug fixes + polish)
// ═══════════════════════════════════════════════════════════════

// ─── Hand strength lookup ───
const HAND_RANKINGS = (() => {
  const tiers = {
    1: ["AA","KK","QQ","JJ","TT","AKs","AQs","AJs","KQs","AKo","ATs","KJs","99"],
    2: ["AQo","QJs","KTs","AJo","KQo","QTs","88","A9s","K9s","A8s","ATo","JTs","77","Q9s","J9s","KJo","A7s","A5s","A6s","A4s","T9s","66","A3s"],
    3: ["KTo","K8s","QJo","A2s","55","J8s","Q8s","K7s","JTo","T8s","K6s","98s","QTo","44","K5s","87s","Q7s","K4s","33","97s","76s","22","J7s","K3s","K2s","Q6s","T7s","Q5s","86s","65s","Q4s","J9o","Q3s","J6s","96s","54s"],
    4: ["T9o","75s","Q2s","J5s","J4s","T6s","64s","98o","J3s","85s","T5s","53s","J2s","87o","T4s","74s","43s","T3s","T2s","95s","63s","76o","92s","84s","52s","65o","42s","93s","54o","32s","73s","82s"],
    5: ["62s","72s","83s","94s","86o","75o","64o","53o","43o","97o","T8o","J8o","96o","85o","74o","42o","32o","52o","62o","72o","82o","92o","T7o","Q8o","Q9o","K9o","A9o","J7o","T6o","95o","84o","73o","63o","93o","83o","94o"]
  };
  const map = {};
  let rank = 1;
  for (let t = 1; t <= 5; t++) for (const h of tiers[t]) { map[h] = { tier: t, rank }; rank++; }
  return map;
})();

function parseRank(c) { return c.startsWith("10") ? "T" : ("AKQJT98765432".includes(c[0]) ? c[0] : null); }
function parseSuit(c) { return c.includes("♠") ? "s" : c.includes("♥") ? "h" : c.includes("♦") ? "d" : c.includes("♣") ? "c" : "?"; }
function rankVal(r) { return "23456789TJQKA".indexOf(r); }

function getHandStrength(cards) {
  if (!cards || cards.length < 2 || cards.some(c => c.includes("🂠"))) return null;
  const r1 = parseRank(cards[0]), r2 = parseRank(cards[1]);
  const s1 = parseSuit(cards[0]), s2 = parseSuit(cards[1]);
  if (!r1 || !r2) return null;
  const ranks = [r1, r2].sort((a, b) => rankVal(b) - rankVal(a));
  const key = ranks[0] === ranks[1] ? ranks[0]+ranks[1] : ranks[0]+ranks[1]+(s1===s2?"s":"o");
  const info = HAND_RANKINGS[key];
  if (!info) return { tier: 4, label: "Marginal", beats: "unranked" };
  const total = Object.keys(HAND_RANKINGS).length;
  const pct = Math.round(((total - info.rank) / total) * 100);
  const labels = { 1: "Premium", 2: "Strong", 3: "Playable", 4: "Marginal", 5: "Spec" };
  return { tier: info.tier, label: labels[info.tier], beats: `beats ${pct}%` };
}

// ─── DOM refs ───
const $ = id => document.getElementById(id);
const els = {};
["status","connectScreen","gameScreen","nameInput","roomInput","createBtn","joinBtn",
"reconnectBtn","roomsList","roomId","phaseBadge","potValue","community","playerPositions","hintsToggle",
"winnerOverlay","winnerContent","yourHandBar","yourCards","handStrength","startBtn",
"foldBtn","checkCallBtn","betHalfPotBtn","betPotBtn","betAllInBtn","customBetInput",
"customBetBtn","resetBtn","adminActions","copyRoomBtn","leaveBtn","chatToggle","chatClose",
"chatPanel","chatMessages","chatInput","chatBtn","actionBar","outsBox","turnInfo",
"pauseBtn","sitOutBtn","spectateBtn","addBotBtn","removeBotBtn"
].forEach(id => { els[id] = $(id); });

let ws = null;
let roomId = localStorage.getItem("poker_room_id") || "";
let token = localStorage.getItem("poker_token") || "";
let lastState = null, prevPhase = null, isAllInRunout = false;
let winnerTimeout = null;
let winnerDismissedForPhase = null; // FIX #7: track dismissed winner
let selectedAvatar = localStorage.getItem("poker_avatar") || "🎭";

// Hints toggle state
let hintsEnabled = localStorage.getItem("poker_hints") !== "false"; // default ON

// All-in runout timing state
let allInRunoutActive = false;        // persists across phases during an all-in runout
let lastCommunityCardTime = 0;        // timestamp when the last community card was rendered
let showdownRevealTime = 0;           // timestamp when showdown state (hands face-up) arrived
let winnerOverlayDelayTimer = null;   // timer for delayed winner overlay display

// Speech bubble tracking: { botName: { text, shownAt } }
let botSpeechBubbles = {};

// Avatar picker
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

// ─── Connection ───
function connect() {
  if (ws && ws.readyState === WebSocket.OPEN) return ws;
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);
  ws.onopen = () => { els.status.textContent = ""; fetchRooms(); };
  ws.onmessage = ev => {
    const { event, payload } = JSON.parse(ev.data);
    console.log("[WS recv]", event, payload);
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
      // If reconnect failed, clear stale credentials and show lobby
      if (event === "reconnect_failed") {
        roomId = ""; token = "";
        localStorage.removeItem("poker_room_id");
        localStorage.removeItem("poker_token");
        els.gameScreen.classList.add("hidden");
        els.connectScreen.classList.remove("hidden");
        fetchRooms();
      }
    }
  };
  ws.onclose = () => { els.status.textContent = "Disconnected."; ws = null; };
  return ws;
}

// FIX #2: send with explicit room_id and token override
function send(event, payload = {}) {
  const s = connect();
  // Merge: payload values override globals (so join can pass token:"")
  const finalPayload = { room_id: roomId, token, ...payload };
  console.log("[WS send]", event, finalPayload);
  const msg = JSON.stringify({ event, payload: finalPayload });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function fetchRooms() {
  // list_rooms doesn't need credentials — send clean
  const s = connect();
  const msg = JSON.stringify({ event: "list_rooms", payload: {} });
  if (s.readyState === WebSocket.OPEN) s.send(msg);
  else s.addEventListener("open", () => s.send(msg), { once: true });
}

function leaveToLobby() {
  roomId = ""; token = "";
  localStorage.removeItem("poker_room_id");
  localStorage.removeItem("poker_token");
  els.gameScreen.classList.add("hidden");
  els.connectScreen.classList.remove("hidden");
  els.winnerOverlay.classList.add("hidden");
  lastState = null; prevPhase = null;
  winnerDismissedForPhase = null;
  allInRunoutActive = false;
  lastCommunityCardTime = 0;
  showdownRevealTime = 0;
  prevCommunityCards = [];
  if (winnerOverlayDelayTimer) { clearTimeout(winnerOverlayDelayTimer); winnerOverlayDelayTimer = null; }
  connect(); // ensure WS is alive
  setTimeout(fetchRooms, 300);
}

// ─── Room list ───
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

// ─── Actions ───
function createRoom() {
  send("create", { name: els.nameInput.value || "Player", avatar: selectedAvatar });
}

// FIX #2: Clear globals BEFORE sending join so payload is clean
function joinRoom() {
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
  try { send("leave", {}); } catch(e) {}
  setTimeout(leaveToLobby, 200);
}

// ─── Render ───
function renderState(state) {
  const active = state.players.filter(p => !p.folded && p.cards && p.cards.length > 0);
  const canAct = active.filter(p => !p.all_in && p.stack > 0);
  const newPhase = prevPhase && prevPhase !== state.phase;

  // Detect all-in runout: all active players are all-in (none can act)
  // Set the persistent flag when we first detect it, keep it until new hand
  if (newPhase && canAct.length === 0 && active.length > 1 && !["showdown","lobby","preflop"].includes(state.phase)) {
    allInRunoutActive = true;
  }
  isAllInRunout = allInRunoutActive && !["showdown","lobby"].includes(state.phase);

  // Track when community cards change (new card dealt)
  const prevCommunityCount = lastState ? (lastState.community ? lastState.community.length : 0) : 0;
  const currCommunityCount = state.community ? state.community.length : 0;
  if (currCommunityCount > prevCommunityCount) {
    lastCommunityCardTime = Date.now();
  }

  // Track when showdown arrives (hands revealed face-up)
  if (newPhase && state.phase === "showdown" && allInRunoutActive) {
    showdownRevealTime = Date.now();
  }

  // FIX #7: Reset winner dismissed tracker on new hand
  if (newPhase && state.phase === "preflop") {
    winnerDismissedForPhase = null;
    allInRunoutActive = false;
    lastCommunityCardTime = 0;
    showdownRevealTime = 0;
    prevCommunityCards = [];
    if (winnerOverlayDelayTimer) { clearTimeout(winnerOverlayDelayTimer); winnerOverlayDelayTimer = null; }
  }
  prevPhase = state.phase;
  lastState = state;

  els.roomId.textContent = state.room_id;
  els.phaseBadge.textContent = state.paused ? "PAUSED" : state.phase.toUpperCase();
  els.potValue.textContent = state.pot;

  // FIX #3: Turn indication - highlight action bar
  const isMyTurn = state.viewer.is_turn;
  if (isMyTurn) {
    els.turnInfo.textContent = state.viewer.to_call > 0 ? `⚡ YOUR TURN · Call ${state.viewer.to_call}` : "⚡ YOUR TURN";
    els.turnInfo.className = "turn-indicator your-turn";
    els.actionBar.classList.add("my-turn");
  } else {
    els.turnInfo.textContent = "";
    els.turnInfo.className = "turn-indicator";
    els.actionBar.classList.remove("my-turn");
  }

  // Admin / deal button
  const canDeal = ["lobby", "showdown"].includes(state.phase) && !state.paused;

  // Start button in action row
  els.startBtn.style.display = canDeal ? "" : "none";

  // Admin side panel
  if (state.viewer.is_admin) {
    els.adminActions.classList.remove("hidden");
    els.resetBtn.style.display = "";
    els.pauseBtn.style.display = "";
    els.addBotBtn.style.display = "";
    els.removeBotBtn.style.display = "";
    if (els.pauseBtn) els.pauseBtn.textContent = state.paused ? "▶ Resume" : "⏸ Pause";
  } else {
    els.adminActions.classList.add("hidden");
  }

  // Sit-out / spectate
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

  renderCommunity(state.community);
  renderYourHand(viewerData);

  // Detect new bot messages for speech bubbles
  if (state.messages && state.messages.length > 0) {
    const prevMsgCount = lastState && lastState.messages ? lastState.messages.length : 0;
    if (state.messages.length > prevMsgCount) {
      const newMsgs = state.messages.slice(prevMsgCount);
      const botNames = state.players.filter(p => p.is_bot).map(p => p.name);
      newMsgs.forEach(m => {
        if (botNames.includes(m.name)) {
          botSpeechBubbles[m.name] = { text: m.text, shownAt: Date.now() };
        }
      });
    }
  }

  renderPlayers(state.players);
  renderWinners(state.winners, viewerData);
  renderChat(state.messages);

  // Button labels
  if (isMyTurn) {
    els.checkCallBtn.textContent = state.viewer.to_call > 0 ? `Call ${state.viewer.to_call}` : "Check";
    els.customBetInput.placeholder = `Min ${state.current_bet + state.min_raise}`;
  } else {
    els.checkCallBtn.textContent = "Check / Call";
    els.customBetInput.placeholder = "Raise to...";
  }
}

// FIX #4: Longer stagger delays for card dealing
let prevCommunityCards = [];
function renderCommunity(cards) {
  els.community.innerHTML = "";
  if (!cards || cards.length === 0) {
    els.community.innerHTML = '<span class="hint-text">Waiting for deal...</span>';
    prevCommunityCards = [];
    return;
  }
  const prevCount = prevCommunityCards.length;
  cards.forEach((c, i) => {
    const el = makeCard(c);
    if (isAllInRunout && i >= prevCount) {
      // Only slow-reveal NEW cards, not already-visible ones
      el.classList.add("slow-reveal");
      el.style.animationDelay = `${(i - prevCount) * 0.5}s`;
    } else if (i >= prevCount) {
      el.style.animationDelay = `${(i - prevCount) * 0.12}s`;
    }
    els.community.appendChild(el);
  });
  prevCommunityCards = [...cards];
}

function renderYourHand(viewer) {
  if (!viewer || !viewer.cards || viewer.cards.length === 0) {
    els.yourHandBar.classList.remove("hand-bar-enter");
    els.yourHandBar.classList.add("hand-bar-hidden");
    return;
  }
  const isBack = c => c === "🂠" || c.includes("🂠") || c === "BACK";
  if (viewer.cards.every(isBack)) {
    els.yourHandBar.classList.remove("hand-bar-enter");
    els.yourHandBar.classList.add("hand-bar-hidden");
    return;
  }

  els.yourHandBar.classList.remove("hand-bar-hidden");
  els.yourHandBar.classList.add("hand-bar-enter");
  els.yourCards.innerHTML = "";
  viewer.cards.forEach(c => els.yourCards.appendChild(makeCard(c)));

  const odds = lastState && lastState.viewer && lastState.viewer.odds;
  if (odds && hintsEnabled) {
    let parts = [];
    if (odds.made_hand) parts.push(odds.made_hand);
    if (odds.is_nuts) parts.push("🔥 NUTS");
    else if (odds.nuts_rank === 2) parts.push("2nd Nuts");
    else if (odds.nuts_rank === 3) parts.push("3rd Nuts");
    if (odds.draws && odds.draws.length > 0) parts.push(odds.draws.join(" + "));
    if (odds.equity !== null && odds.equity !== undefined) {
      let eqStr = `${odds.equity}%`;
      if (odds.current_ahead !== null) eqStr += `/${odds.current_ahead}%ahead`;
      parts.push(eqStr);
    }
    els.handStrength.textContent = parts.join(" · ");
    const eq = odds.equity || 50;
    const tier = odds.is_nuts ? 1 : eq >= 65 ? 1 : eq >= 45 ? 2 : eq >= 30 ? 3 : eq >= 15 ? 4 : 5;
    els.handStrength.className = `hand-strength-badge tier-${tier}`;
  } else if (hintsEnabled) {
    const str = getHandStrength(viewer.cards);
    if (str) { els.handStrength.textContent = `${str.label} · ${str.beats}`; els.handStrength.className = `hand-strength-badge tier-${str.tier}`; }
    else { els.handStrength.textContent = ""; els.handStrength.className = "hand-strength-badge"; }
  } else {
    els.handStrength.textContent = "";
    els.handStrength.className = "hand-strength-badge";
  }
}

function renderPlayers(players) {
  els.playerPositions.innerHTML = "";
  players.forEach((p, idx) => {
    const pos = SEAT_POSITIONS[idx % SEAT_POSITIONS.length];
    const seat = document.createElement("div");
    let cls = "player-seat";
    if (p.is_action) cls += " active-turn";
    if (p.folded) cls += " folded";
    if (p.is_you) cls += " is-you";
    seat.className = cls;
    seat.style.top = pos.top;
    seat.style.left = pos.left;
    seat.style.transform = "translate(-50%, -50%)";

    const badges = [];
    if (p.is_you) badges.push('<span class="seat-badge">YOU</span>');
    if (p.is_bot) badges.push('<span class="seat-badge">🤖</span>');
    if (p.is_dealer) badges.push('<span class="seat-badge">D</span>');
    if (p.is_sb) badges.push('<span class="seat-badge">SB</span>');
    if (p.is_bb) badges.push('<span class="seat-badge">BB</span>');
    if (p.all_in) badges.push('<span class="seat-badge">ALL-IN</span>');
    if (p.folded) badges.push('<span class="seat-badge warn">FOLD</span>');
    if (!p.connected && !p.is_bot) badges.push('<span class="seat-badge warn">DC</span>');
    if (p.sitting_out) badges.push('<span class="seat-badge warn">SIT OUT</span>');
    if (p.is_spectator) badges.push('<span class="seat-badge">👁</span>');

    let cards = "";
    if (p.cards && p.cards.length > 0 && !p.is_you) {
      cards = `<div class="seat-cards">${p.cards.map(makeCardHtml).join("")}</div>`;
    }

    // Spectator hand strength display
    let spectatorInfo = "";
    if (p.hand_classification) {
      const tierColors = { gold: "#ffca28", green: "#66bb6a", blue: "#42a5f5", gray: "#78909c" };
      const tierTextColors = { gold: "#1a1a1a", green: "#1a1a1a", blue: "#1a1a1a", gray: "#fff" };
      const equityBadge = p.equity_pct != null && p.equity_tier
        ? `<span class="spectator-equity" style="background:${tierColors[p.equity_tier] || '#78909c'};color:${tierTextColors[p.equity_tier] || '#fff'}">${p.equity_pct}%</span>`
        : "";
      spectatorInfo = `<div class="spectator-info"><span class="spectator-hand-class">${esc(p.hand_classification)}</span>${equityBadge}</div>`;
    }

    // Speech bubble: show most recent chat from this bot (within last 5 seconds)
    let speechBubble = "";
    if (p.is_bot && botSpeechBubbles[p.name]) {
      const bubble = botSpeechBubbles[p.name];
      if (Date.now() - bubble.shownAt < 5000) {
        speechBubble = `<div class="speech-bubble">${esc(bubble.text)}</div>`;
      }
    }

    seat.innerHTML = `
      ${speechBubble}
      <div class="seat-header"><span class="seat-avatar">${p.avatar||"🎭"}</span><span class="seat-name">${esc(p.name)}</span><span class="seat-stack">💰${p.stack}</span></div>
      <div class="seat-badges">${badges.join("")}</div>
      ${cards}
      ${spectatorInfo}
      ${p.committed > 0 ? `<div class="seat-meta">Bet: ${p.committed}</div>` : ""}
      ${p.hand_name ? `<div class="seat-meta" style="color:var(--gold-light)">${esc(p.hand_name)}</div>` : ""}
    `;
    els.playerPositions.appendChild(seat);
  });
}

// FIX #6 & #7: Winner differentiation + don't re-show after dismiss
function renderWinners(winners, viewer) {
  if (winnerTimeout) { clearTimeout(winnerTimeout); winnerTimeout = null; }

  if (!winners || winners.length === 0) {
    els.winnerOverlay.classList.add("hidden");
    return;
  }

  // FIX #7: Don't re-show if user already dismissed for this showdown
  if (winnerDismissedForPhase === "showdown") {
    return;
  }

  // All-in runout delay: ensure the winner overlay doesn't appear too quickly
  // after cards are revealed and hands are shown face-up
  if (allInRunoutActive && !winnerOverlayDelayTimer) {
    const now = Date.now();
    // Calculate minimum delay based on timing requirements:
    // - At least 2.5s after last community card appeared
    // - At least 2.0s after showdown state (hands face-up)
    // - At least 1.5s from when showdown card reveal became visible
    const sinceLastCard = lastCommunityCardTime ? now - lastCommunityCardTime : Infinity;
    const sinceShowdown = showdownRevealTime ? now - showdownRevealTime : Infinity;

    const delayForCards = Math.max(0, 2500 - sinceLastCard);
    const delayForFaceUp = Math.max(0, 2000 - sinceShowdown);
    const delayForReveal = Math.max(0, 1500 - sinceShowdown);

    const delay = Math.max(delayForCards, delayForFaceUp, delayForReveal);

    if (delay > 0) {
      winnerOverlayDelayTimer = setTimeout(() => {
        winnerOverlayDelayTimer = null;
        showWinnerOverlay(winners, viewer);
      }, delay);
      return;
    }
  }

  showWinnerOverlay(winners, viewer);
}

function showWinnerOverlay(winners, viewer) {
  // FIX #7: Don't re-show if user already dismissed for this showdown
  if (winnerDismissedForPhase === "showdown") {
    return;
  }

  els.winnerOverlay.classList.remove("hidden");
  const w = winners[0];
  const viewerWon = viewer && winners.some(x => x.name === viewer.name);
  const best = w.best_cards && w.best_cards.length ? `<div class="winner-best-cards">${w.best_cards.map(makeCardHtml).join("")}</div>` : "";
  const others = winners.length > 1 ? `<div style="font-size:12px;color:var(--text-dim);margin-top:6px">Split: ${winners.slice(1).map(x=>esc(x.name)).join(", ")}</div>` : "";

  // FIX #6: Different message if you won vs lost
  const trophy = viewerWon ? "🎉" : "💀";
  const headline = viewerWon ? "You Won!" : "You Lost";
  const subline = viewerWon ? "" : `<div style="font-size:14px;color:var(--text-dim);margin-bottom:4px">${esc(w.name)} wins with ${esc(w.hand_name||w.reason)}</div>`;

  els.winnerContent.innerHTML = `
    <div class="winner-trophy">${trophy}</div>
    <div class="winner-name">${headline}</div>
    ${viewerWon ? `<div class="winner-amount">+${w.amount}</div>` : subline}
    ${viewerWon ? `<div class="winner-hand">${esc(w.hand_name||w.reason)}</div>` : ""}
    ${best}${others}
    <div class="winner-dismiss">Tap to dismiss</div>
  `;

  // Auto-dismiss: shorter if you lost
  const dismissTime = viewerWon ? 10000 : 5000;
  winnerTimeout = setTimeout(() => els.winnerOverlay.classList.add("hidden"), dismissTime);
}

// FIX #7: Chat rendering is separate from winner display
function renderChat(messages) {
  if (!messages) return;
  els.chatMessages.innerHTML = messages.map(m =>
    `<div class="chat-msg"><span class="chat-name">${esc(m.name)}:</span> ${esc(m.text)}</div>`
  ).join("");
  els.chatMessages.scrollTop = els.chatMessages.scrollHeight;
}

// ─── Card helpers ───
function makeCard(card) {
  const d = document.createElement("div"); d.className = "playing-card";
  if (card === "🂠") { d.classList.add("card-back"); d.textContent = "🂠"; return d; }
  d.textContent = card;
  if (card.includes("♥") || card.includes("♦")) d.classList.add("red");
  return d;
}
function makeCardHtml(card) {
  if (card === "🂠") return '<div class="playing-card card-back">🂠</div>';
  return `<div class="playing-card${card.includes("♥")||card.includes("♦")?" red":""}">${esc(card)}</div>`;
}
function esc(s) { return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

// Player positions around the table
const SEAT_POSITIONS = [
  { top: "78%", left: "50%" },   // 1: bottom center
  { top: "65%", left: "10%" },   // 2: lower left
  { top: "30%", left: "5%" },    // 3: mid left
  { top: "5%",  left: "25%" },   // 4: upper left
  { top: "5%",  left: "75%" },   // 5: upper right
  { top: "30%", left: "95%" },   // 6: mid right
  { top: "65%", left: "90%" },   // 7: lower right
  { top: "5%",  left: "50%" },   // 8: top center
];

// ─── Event handlers ───
els.createBtn.onclick = createRoom;
els.joinBtn.onclick = joinRoom;
els.reconnectBtn.onclick = reconnectLast;
els.leaveBtn.onclick = leaveGame;
els.startBtn.onclick = () => action("start_hand");
els.foldBtn.onclick = () => action("fold");
els.checkCallBtn.onclick = () => action("check_call");
els.betHalfPotBtn.onclick = () => { if(!lastState)return; action("bet_raise",{amount:Math.max(lastState.current_bet+lastState.min_raise, lastState.current_bet+Math.floor(lastState.pot/2))}); };
els.betPotBtn.onclick = () => { if(!lastState)return; action("bet_raise",{amount:Math.max(lastState.current_bet+lastState.min_raise, lastState.current_bet+lastState.pot)}); };
els.betAllInBtn.onclick = () => { if(!lastState)return; action("bet_raise",{amount:lastState.viewer.committed+lastState.viewer.stack}); };
els.customBetBtn.onclick = () => { const v=parseInt(els.customBetInput.value,10); if(v>0){action("bet_raise",{amount:v});els.customBetInput.value="";} };
els.customBetInput.onkeydown = ev => { if(ev.key==="Enter") els.customBetBtn.click(); };
els.resetBtn.onclick = () => action("reset_stacks");
els.pauseBtn.onclick = () => action("toggle_pause");
els.addBotBtn.onclick = () => { console.log("[BTN] add_bot clicked, roomId=", roomId, "token=", token.slice(0,8), "ws=", ws && ws.readyState); action("add_bot"); };
els.removeBotBtn.onclick = () => { console.log("[BTN] remove_bot clicked"); action("remove_bot"); };
els.sitOutBtn.onclick = () => action("sit_out");
els.spectateBtn.onclick = () => action("spectate");
els.copyRoomBtn.onclick = async () => { try{await navigator.clipboard.writeText(roomId);}catch{} };

// FIX #7: Track dismiss so re-broadcasts don't re-show
els.winnerOverlay.onclick = () => {
  els.winnerOverlay.classList.add("hidden");
  winnerDismissedForPhase = "showdown";
};

els.chatToggle.onclick = () => els.chatPanel.classList.toggle("hidden");
els.hintsToggle.onclick = () => {
  hintsEnabled = !hintsEnabled;
  localStorage.setItem("poker_hints", hintsEnabled ? "true" : "false");
  els.hintsToggle.textContent = hintsEnabled ? "💡" : "🚫";
  if (lastState) renderState(lastState);
};
// Apply initial hints button state
if (!hintsEnabled) els.hintsToggle.textContent = "🚫";
els.chatClose.onclick = () => els.chatPanel.classList.add("hidden");
els.chatBtn.onclick = () => { const t=els.chatInput.value.trim(); if(t){send("chat",{text:t});els.chatInput.value="";} };
els.chatInput.onkeydown = ev => { if(ev.key==="Enter") els.chatBtn.click(); };

// ─── Init ───
if (roomId && token) {
  reconnectLast();
} else {
  // Clear any stale data
  roomId = ""; token = "";
  connect();
  setTimeout(fetchRooms, 500);
}
