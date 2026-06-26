// ═══════════════════════════════════════════════════════════════
// Unit Tests for Action Log Toggle and Auto-Scroll Behavior
// Uses jsdom to simulate the DOM environment
// ═══════════════════════════════════════════════════════════════
// Validates: Requirements 4.2, 4.3, 4.4, 5.1, 5.2, 5.3

const { JSDOM } = require("jsdom");

// ─── Test runner ───
let totalPassed = 0;
let totalFailed = 0;

function assert(condition, message) {
  if (!condition) throw new Error(message || "Assertion failed");
}

function assertEqual(actual, expected, message) {
  if (actual !== expected) {
    throw new Error(
      `${message || "Assertion failed"}: expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`
    );
  }
}

function runTest(name, testFn) {
  try {
    testFn();
    totalPassed++;
    console.log(`  ✓ ${name}`);
  } catch (e) {
    totalFailed++;
    console.error(`  ✗ ${name}`);
    console.error(`    ${e.message}`);
  }
}

// ─── DOM setup helper ───
const PANEL_KEY = "poker_action_log_expanded";

function createTestDOM(viewportWidth = 1024) {
  const html = `<!DOCTYPE html>
<html>
<body>
  <div id="actionLogPanel" class="action-log-panel">
    <div class="action-log-header">
      <span class="action-log-title">Hand #<span id="actionLogHandNum">0</span></span>
    </div>
    <div id="actionLogBody" class="action-log-body" style="overflow-y:auto; height:200px;"></div>
  </div>
  <button id="actionLogToggle" class="action-log-toggle">◀</button>
</body>
</html>`;

  const dom = new JSDOM(html, { url: "http://localhost", runScripts: "dangerously" });
  const { window } = dom;
  const { document, localStorage } = window;
  window.matchMedia = query => ({
    matches: query.includes("max-width: 768px") && viewportWidth <= 768,
    media: query,
    addEventListener: () => {},
    removeEventListener: () => {},
  });

  // Build the els object mimicking the app
  const els = {
    actionLogPanel: document.getElementById("actionLogPanel"),
    actionLogToggle: document.getElementById("actionLogToggle"),
    actionLogBody: document.getElementById("actionLogBody"),
    actionLogHandNum: document.getElementById("actionLogHandNum"),
  };

  return { dom, window, document, localStorage, els };
}

// ─── Inline the toggle logic (same as app.js) ───
function createToggleController(els, localStorage, window) {
  let panelExpanded = true;

  function applyPanelState() {
    if (!els.actionLogPanel || !els.actionLogToggle) return;
    if (panelExpanded) {
      els.actionLogPanel.classList.remove("collapsed");
      els.actionLogToggle.classList.remove("panel-collapsed");
      els.actionLogToggle.textContent = "◀";
    } else {
      els.actionLogPanel.classList.add("collapsed");
      els.actionLogToggle.classList.add("panel-collapsed");
      els.actionLogToggle.textContent = "▶";
    }
  }

  function initActionLogToggle() {
    try {
      const stored = localStorage.getItem(PANEL_KEY);
      const defaultExpanded = !window.matchMedia || !window.matchMedia("(max-width: 768px)").matches;
      panelExpanded = stored === null ? defaultExpanded : stored !== "false";
    } catch (e) {
      panelExpanded = true;
    }
    applyPanelState();

    if (els.actionLogToggle) {
      els.actionLogToggle.addEventListener("click", () => {
        panelExpanded = !panelExpanded;
        applyPanelState();
        try {
          localStorage.setItem(PANEL_KEY, String(panelExpanded));
        } catch (e) {}
      });
    }
  }

  return { initActionLogToggle, getExpanded: () => panelExpanded };
}

// ─── Inline the auto-scroll logic (same as app.js) ───
function createAutoScrollController(els) {
  let actionLogAutoScroll = true;

  function onActionLogScroll() {
    const el = els.actionLogBody;
    if (!el) return;
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 10;
    actionLogAutoScroll = atBottom;
  }

  function scrollActionLogToBottom() {
    if (actionLogAutoScroll && els.actionLogBody) {
      els.actionLogBody.scrollTop = els.actionLogBody.scrollHeight;
    }
  }

  return {
    onActionLogScroll,
    scrollActionLogToBottom,
    getAutoScroll: () => actionLogAutoScroll,
    setAutoScroll: (v) => { actionLogAutoScroll = v; },
  };
}

// ═══════════════════════════════════════════════════════════════
// Toggle Tests — Requirements 4.2, 4.3, 4.4
// ═══════════════════════════════════════════════════════════════
console.log("\nToggle collapse/expand behavior (Req 4.2, 4.3):");

runTest("Toggle click collapses panel (adds 'collapsed' class)", () => {
  const { els, localStorage, window } = createTestDOM();
  const controller = createToggleController(els, localStorage, window);
  controller.initActionLogToggle();

  // Initially expanded
  assert(!els.actionLogPanel.classList.contains("collapsed"), "Panel should start expanded");

  // Click toggle → should collapse
  els.actionLogToggle.click();
  assert(els.actionLogPanel.classList.contains("collapsed"), "Panel should be collapsed after click");
  assert(els.actionLogToggle.classList.contains("panel-collapsed"), "Toggle button should have panel-collapsed class");
  assertEqual(els.actionLogToggle.textContent, "▶", "Toggle button should show ▶ when collapsed");
});

runTest("Toggle click expands panel on second click (removes 'collapsed' class)", () => {
  const { els, localStorage, window } = createTestDOM();
  const controller = createToggleController(els, localStorage, window);
  controller.initActionLogToggle();

  // Click to collapse
  els.actionLogToggle.click();
  assert(els.actionLogPanel.classList.contains("collapsed"), "Panel should be collapsed after first click");

  // Click again to expand
  els.actionLogToggle.click();
  assert(!els.actionLogPanel.classList.contains("collapsed"), "Panel should be expanded after second click");
  assert(!els.actionLogToggle.classList.contains("panel-collapsed"), "Toggle should not have panel-collapsed class");
  assertEqual(els.actionLogToggle.textContent, "◀", "Toggle button should show ◀ when expanded");
});

console.log("\nToggle localStorage persistence (Req 4.4):");

runTest("localStorage is written on toggle click", () => {
  const { els, localStorage, window } = createTestDOM();
  const controller = createToggleController(els, localStorage, window);
  controller.initActionLogToggle();

  // Click to collapse
  els.actionLogToggle.click();
  assertEqual(localStorage.getItem(PANEL_KEY), "false", "localStorage should store 'false' after collapse");

  // Click to expand
  els.actionLogToggle.click();
  assertEqual(localStorage.getItem(PANEL_KEY), "true", "localStorage should store 'true' after expand");
});

runTest("localStorage is read on init — collapsed state is restored", () => {
  const { els, localStorage, window } = createTestDOM();
  // Pre-set localStorage to collapsed
  localStorage.setItem(PANEL_KEY, "false");

  const controller = createToggleController(els, localStorage, window);
  controller.initActionLogToggle();

  assert(els.actionLogPanel.classList.contains("collapsed"), "Panel should be collapsed on init from localStorage");
  assertEqual(els.actionLogToggle.textContent, "▶", "Toggle should show ▶ when restored as collapsed");
});

runTest("localStorage is read on init — expanded state is restored", () => {
  const { els, localStorage, window } = createTestDOM();
  localStorage.setItem(PANEL_KEY, "true");

  const controller = createToggleController(els, localStorage, window);
  controller.initActionLogToggle();

  assert(!els.actionLogPanel.classList.contains("collapsed"), "Panel should be expanded on init from localStorage 'true'");
  assertEqual(els.actionLogToggle.textContent, "◀", "Toggle should show ◀ when restored as expanded");
});

runTest("Default is expanded when localStorage key is absent", () => {
  const { els, localStorage, window } = createTestDOM();
  // Don't set anything in localStorage

  const controller = createToggleController(els, localStorage, window);
  controller.initActionLogToggle();

  assert(!els.actionLogPanel.classList.contains("collapsed"), "Panel should default to expanded");
  assertEqual(controller.getExpanded(), true, "Internal state should be true (expanded)");
  assertEqual(els.actionLogToggle.textContent, "◀", "Toggle should show ◀ (expanded) by default");
});

// ═══════════════════════════════════════════════════════════════
// Auto-Scroll Tests — Requirements 5.1, 5.2, 5.3
// ═══════════════════════════════════════════════════════════════
runTest("Default is collapsed on mobile when localStorage key is absent", () => {
  const { els, localStorage, window } = createTestDOM(412);

  const controller = createToggleController(els, localStorage, window);
  controller.initActionLogToggle();

  assert(els.actionLogPanel.classList.contains("collapsed"), "Panel should default to collapsed on mobile");
  assertEqual(controller.getExpanded(), false, "Internal state should be false (collapsed)");
  assertEqual(els.actionLogToggle.textContent, "â–¶", "Toggle should show â–¶ when collapsed by default");
});

console.log("\nAuto-scroll behavior (Req 5.1, 5.2, 5.3):");

runTest("Auto-scroll is enabled by default", () => {
  const { els } = createTestDOM();
  const scrollCtrl = createAutoScrollController(els);

  assertEqual(scrollCtrl.getAutoScroll(), true, "Auto-scroll should be enabled by default");
});

runTest("scrollActionLogToBottom updates scrollTop when auto-scroll is enabled", () => {
  const { els } = createTestDOM();
  const scrollCtrl = createAutoScrollController(els);

  // Simulate content taller than the container
  // jsdom doesn't actually compute layout, so scrollHeight stays 0.
  // We mock the scrollHeight to simulate behavior.
  Object.defineProperty(els.actionLogBody, "scrollHeight", { value: 500, writable: true });
  Object.defineProperty(els.actionLogBody, "clientHeight", { value: 200, writable: true });
  els.actionLogBody.scrollTop = 0;

  scrollCtrl.scrollActionLogToBottom();
  assertEqual(els.actionLogBody.scrollTop, 500, "scrollTop should be set to scrollHeight when auto-scroll is on");
});

runTest("scrollActionLogToBottom does NOT update scrollTop when auto-scroll is disabled", () => {
  const { els } = createTestDOM();
  const scrollCtrl = createAutoScrollController(els);

  Object.defineProperty(els.actionLogBody, "scrollHeight", { value: 500, writable: true });
  Object.defineProperty(els.actionLogBody, "clientHeight", { value: 200, writable: true });
  els.actionLogBody.scrollTop = 50;

  // Disable auto-scroll
  scrollCtrl.setAutoScroll(false);

  scrollCtrl.scrollActionLogToBottom();
  assertEqual(els.actionLogBody.scrollTop, 50, "scrollTop should not change when auto-scroll is disabled");
});

runTest("Manual scroll-up disables auto-scroll (user not at bottom)", () => {
  const { els } = createTestDOM();
  const scrollCtrl = createAutoScrollController(els);

  // Simulate: scrollHeight=500, clientHeight=200, scrollTop=100 → 500-100-200=200 (>10 → NOT at bottom)
  Object.defineProperty(els.actionLogBody, "scrollHeight", { value: 500, writable: true });
  Object.defineProperty(els.actionLogBody, "clientHeight", { value: 200, writable: true });
  els.actionLogBody.scrollTop = 100;

  scrollCtrl.onActionLogScroll();
  assertEqual(scrollCtrl.getAutoScroll(), false, "Auto-scroll should be disabled when user scrolls up (not at bottom)");
});

runTest("Scroll-to-bottom re-enables auto-scroll (within 10px threshold)", () => {
  const { els } = createTestDOM();
  const scrollCtrl = createAutoScrollController(els);

  // First disable auto-scroll
  Object.defineProperty(els.actionLogBody, "scrollHeight", { value: 500, writable: true });
  Object.defineProperty(els.actionLogBody, "clientHeight", { value: 200, writable: true });
  els.actionLogBody.scrollTop = 100;
  scrollCtrl.onActionLogScroll();
  assertEqual(scrollCtrl.getAutoScroll(), false, "Should be disabled after scrolling up");

  // Now scroll to bottom (within 10px threshold): 500 - 295 - 200 = 5 (<10 → at bottom)
  els.actionLogBody.scrollTop = 295;
  scrollCtrl.onActionLogScroll();
  assertEqual(scrollCtrl.getAutoScroll(), true, "Auto-scroll should re-enable when user scrolls to bottom");
});

runTest("Scroll exactly at threshold boundary (10px) disables auto-scroll", () => {
  const { els } = createTestDOM();
  const scrollCtrl = createAutoScrollController(els);

  // scrollHeight=500, clientHeight=200, scrollTop=290 → 500-290-200=10 (NOT < 10, so NOT at bottom)
  Object.defineProperty(els.actionLogBody, "scrollHeight", { value: 500, writable: true });
  Object.defineProperty(els.actionLogBody, "clientHeight", { value: 200, writable: true });
  els.actionLogBody.scrollTop = 290;

  scrollCtrl.onActionLogScroll();
  assertEqual(scrollCtrl.getAutoScroll(), false, "At exactly 10px from bottom, auto-scroll should be disabled (threshold is strictly < 10)");
});

runTest("Scroll just within threshold (9px from bottom) enables auto-scroll", () => {
  const { els } = createTestDOM();
  const scrollCtrl = createAutoScrollController(els);

  // scrollHeight=500, clientHeight=200, scrollTop=291 → 500-291-200=9 (<10 → at bottom)
  Object.defineProperty(els.actionLogBody, "scrollHeight", { value: 500, writable: true });
  Object.defineProperty(els.actionLogBody, "clientHeight", { value: 200, writable: true });
  els.actionLogBody.scrollTop = 291;

  scrollCtrl.onActionLogScroll();
  assertEqual(scrollCtrl.getAutoScroll(), true, "At 9px from bottom (< 10), auto-scroll should be enabled");
});

// ═══════════════════════════════════════════════════════════════
// Summary
// ═══════════════════════════════════════════════════════════════
console.log(`\n═══ Results: ${totalPassed} passed, ${totalFailed} failed ═══\n`);
if (totalFailed > 0) {
  process.exit(1);
}
