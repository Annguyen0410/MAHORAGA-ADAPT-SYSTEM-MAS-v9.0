const STORAGE_KEY = "litebrowserWindowBatches";

function setStatus(text, isError = false) {
  const node = document.getElementById("status");
  node.textContent = text || "";
  node.style.color = isError ? "#fca5a5" : "#fde68a";
}

async function getStoredBatches() {
  const data = await chrome.storage.local.get([STORAGE_KEY]);
  return data[STORAGE_KEY] || {};
}

async function saveStoredBatches(batches) {
  await chrome.storage.local.set({ [STORAGE_KEY]: batches });
}

function normalizeBrowserName() {
  const ua = navigator.userAgent || "";
  if (/OPR\//i.test(ua) || /Opera/i.test(ua)) return "opera-gx";
  if (/Chrome/i.test(ua)) return "chrome";
  return "chromium";
}

/* --- pure helpers -------------------------------------------------------- */

function tabsToPayload(tabs, browserName) {
  return tabs
    .filter(tab => tab.url && /^https?:/i.test(tab.url))
    .map(tab => ({
      url: tab.url,
      title: tab.title || tab.url,
      active: Boolean(tab.active),
      pinned: Boolean(tab.pinned),
      index: Number(tab.index || 0),
    }))
    .sort((a, b) => a.index - b.index);
}

function buildWindowPayload(windowId, sourceLabel, tabs, browserName, createdAt, screenIndex) {
  const payload = {
    batch_id: `${browserName}_window_${windowId}`,
    window_id: String(windowId),
    source_browser: browserName,
    source_label: sourceLabel || `Window ${windowId}`,
    created_at: createdAt,
    tabs,
  };
  if (Number.isInteger(screenIndex)) payload.screen_index = screenIndex;
  return payload;
}

/* Wrap the whole multi-window export in a container Mei's Import Center
 * understands. Each browser window (i.e. each monitor/screen) becomes one
 * batch, so screen 1 → batch 1 (50 tabs), screen 2 → batch 2 (32 tabs), etc. */
function buildWorkspacePayload(batches, browserName, createdAt) {
  return {
    format: "mei-multi-window",
    version: 1,
    source_browser: browserName,
    created_at: createdAt,
    window_count: batches.length,
    batches,
  };
}

/* --- captures ------------------------------------------------------------- */

async function captureCurrentWindow() {
  const [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!currentTab?.windowId) {
    throw new Error("Could not detect the current window.");
  }

  const tabs = await chrome.tabs.query({ currentWindow: true });
  const httpTabs = tabsToPayload(tabs, normalizeBrowserName());
  if (!httpTabs.length) {
    throw new Error("This window has no normal web tabs to export.");
  }

  const now = Date.now();
  const browserName = normalizeBrowserName();
  const labelInput = document.getElementById("labelInput").value.trim();
  const payload = buildWindowPayload(
    currentTab.windowId,
    labelInput || `Window ${currentTab.windowId}`,
    httpTabs,
    browserName,
    now,
  );

  const batches = await getStoredBatches();
  batches[String(currentTab.windowId)] = payload;
  await saveStoredBatches(batches);
  return payload;
}

async function captureAllWindows() {
  // One browser window == one screen/monitor. Order windows so screen 1 is
  // first; each gets a numbered label and its tabs sorted by position.
  let windows = await chrome.windows.getAll({ populate: true });
  if (!windows.length) {
    throw new Error("No browser windows found.");
  }
  // Sort left→right so "Screen 1" is the leftmost monitor, matching how people
  // read a dual-monitor desk (screen 1 = 50 tabs, screen 2 = 32 tabs, ...).
  windows = windows.slice().sort((a, b) => (a.left || 0) - (b.left || 0));
  const browserName = normalizeBrowserName();
  const now = Date.now();
  const stored = await getStoredBatches();
  const payloads = [];

  windows.forEach((win, idx) => {
    const httpTabs = tabsToPayload(win.tabs || [], browserName);
    if (!httpTabs.length) return;
    const payload = buildWindowPayload(
      win.id,
      `Screen ${idx + 1}`,
      httpTabs,
      browserName,
      now,
      idx,
    );
    payloads.push(payload);
    stored[String(win.id)] = payload;
  });

  if (!payloads.length) {
    throw new Error("No windows with normal web tabs to export.");
  }

  await saveStoredBatches(stored);
  return buildWorkspacePayload(payloads, browserName, now);
}

/* --- rendering ------------------------------------------------------------ */

async function loadCurrentWindowBatch() {
  const [currentTab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!currentTab?.windowId) return null;
  const batches = await getStoredBatches();
  return batches[String(currentTab.windowId)] || null;
}

function showPayload(payload) {
  document.getElementById("payloadOutput").value = payload ? JSON.stringify(payload, null, 2) : "";
  if (payload?.source_label) {
    document.getElementById("labelInput").value = payload.source_label;
  }
}

async function writeClipboardText(text) {
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text);
      return;
    } catch (error) {
      console.warn("navigator.clipboard failed; falling back to textarea copy.", error);
    }
  }

  const output = document.getElementById("payloadOutput");
  output.value = text;
  output.focus();
  output.select();
  if (!document.execCommand("copy")) {
    throw new Error("Clipboard copy is not available in this browser context.");
  }
}

/* --- actions -------------------------------------------------------------- */

async function copyPayload() {
  let payload = await loadCurrentWindowBatch();
  if (!payload) payload = await captureCurrentWindow();
  showPayload(payload);
  await writeClipboardText(JSON.stringify(payload, null, 2));
  setStatus(`Copied ${payload.tabs.length} tabs from ${payload.source_label}.`);
}

async function downloadPayload() {
  let payload = await loadCurrentWindowBatch();
  if (!payload) payload = await captureCurrentWindow();
  showPayload(payload);
  await downloadBlob(JSON.stringify(payload, null, 2), `litebrowser-window-${payload.window_id}.json`, "application/json");
  setStatus(`Downloaded window ${payload.window_id}.`);
}

async function captureAllAndShow() {
  const workspace = await captureAllWindows();
  showPayload(workspace);
  const total = workspace.batches.reduce((sum, b) => sum + b.tabs.length, 0);
  setStatus(`Captured ${workspace.window_count} windows · ${total} tabs.`);
}

async function downloadAllJson() {
  const workspace = await captureAllWindows();
  showPayload(workspace);
  await downloadBlob(JSON.stringify(workspace, null, 2), "mei-workspace-all-windows.json", "application/json");
  setStatus(`Downloaded JSON with ${workspace.window_count} windows.`);
}

async function downloadAllZip() {
  const workspace = await captureAllWindows();
  showPayload(workspace);

  // One JSON file per window/screen plus a combined manifest so Mei can split
  // screen 1 and screen 2 back into separate workspaces.
  const entries = workspace.batches.map((batch, idx) => ({
    name: `screen-${idx + 1}.json`,
    data: JSON.stringify(batch, null, 2),
  }));
  entries.unshift({
    name: "workspace.json",
    data: JSON.stringify(workspace, null, 2),
  });

  const zip = MeiZip.createZip(entries);
  const blob = new Blob([zip], { type: "application/zip" });
  const url = URL.createObjectURL(blob);
  try {
    await chrome.downloads.download({ url, filename: "mei-workspace-all-windows.zip", saveAs: true });
    setStatus(`Downloaded ZIP with ${workspace.window_count} windows.`);
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function downloadBlob(text, filename, mime) {
  const blob = new Blob([text], { type: mime });
  const url = URL.createObjectURL(blob);
  try {
    await chrome.downloads.download({ url, filename, saveAs: true });
  } finally {
    URL.revokeObjectURL(url);
  }
}

async function refreshStoredBatch() {
  const payload = await loadCurrentWindowBatch();
  showPayload(payload);
  if (!payload) {
    setStatus("No stored batch for this window yet.");
    return;
  }
  setStatus(`Loaded stored batch with ${payload.tabs.length} tabs.`);
}

/* --- talking to Mei (desktop bridge) -------------------------------------- */

const BRIDGE_KEY = "meiBridgeSettings";

function setBridgeStatus(text, isError = false) {
  const node = document.getElementById("bridgeStatus");
  node.textContent = text || "";
  node.style.color = isError ? "#fca5a5" : "#fde68a";
}

function setSendStatus(text, isError = false) {
  const node = document.getElementById("sendStatus");
  node.textContent = text || "";
  node.style.color = isError ? "#fca5a5" : "#fde68a";
}

async function loadBridgeSettings() {
  const data = await chrome.storage.local.get([BRIDGE_KEY]);
  return MeiBridge.normalizeSettings(data[BRIDGE_KEY] || null);
}

async function saveBridgeSettings(settings) {
  await chrome.storage.local.set({ [BRIDGE_KEY]: settings });
}

async function currentWebTab() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !/^https?:/i.test(tab.url || "")) {
    throw new Error("The current tab is not an HTTP/HTTPS page and cannot be sent.");
  }
  return tab;
}

/* Pair (or re-pair) with the desktop bridge, then prove it with a ping.
 * Returns the settings in use, or null when Mei could not be reached — the
 * status line already explains why in that case. */
async function connectBridge(options = {}) {
  const raw = document.getElementById("pairingInput").value.trim();
  let settings = await loadBridgeSettings();
  if (raw) {
    const parsed = MeiBridge.parsePairingCode(raw);
    if (!parsed) {
      throw new Error("Use a pairing code in the form MEI1|host|port|token (copy it from Mei → Settings → Mobile bridge).");
    }
    // The code carries the LAN address so a phone can reach the desktop; this
    // extension runs on that same machine, so it takes the shortest road and
    // never needs the bridge opened to the network.
    settings = MeiBridge.isLoopbackHost(parsed.host) ? parsed : { ...parsed, host: MeiBridge.DEFAULT_HOST };
    await saveBridgeSettings(settings);
    document.getElementById("pairingInput").value = "";
  }
  if (!settings.token) {
    if (options.quiet) {
      setBridgeStatus("Not connected to Mei — paste a pairing code to begin.");
      return null;
    }
    throw new Error("Paste the pairing code from Mei → Settings → Mobile bridge (“Copy pairing code”).");
  }
  const reply = await MeiBridge.ping(settings);
  if (!reply.ok) {
    setBridgeStatus((raw ? "Code saved, but " : "") + reply.message, true);
    return null;
  }
  setBridgeStatus("Connected to " + MeiBridge.capabilitiesLine(reply.body));
  return settings;
}

async function readSelection(tabId) {
  if (!chrome.scripting || !chrome.scripting.executeScript) return "";
  try {
    const frames = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => String(window.getSelection ? window.getSelection().toString() : ""),
    });
    const first = Array.isArray(frames) ? frames[0] : null;
    return first && typeof first.result === "string" ? first.result : "";
  } catch (error) {
    console.warn("Could not read the page selection.", error);
    throw new Error("Could not read the selection on this page — reload it and try again.");
  }
}

async function sendTabToMei() {
  const settings = await connectBridge({});
  if (!settings) {
    setSendStatus("Not sent — check the Mei connection above.", true);
    return;
  }
  const tab = await currentWebTab();
  const reply = await MeiBridge.post(settings, "save_page", MeiBridge.tabPayload(tab));
  setSendStatus(reply.message, !reply.ok);
}

async function sendSelectionToMei() {
  const settings = await connectBridge({});
  if (!settings) {
    setSendStatus("Not sent — check the Mei connection above.", true);
    return;
  }
  const tab = await currentWebTab();
  const text = (await readSelection(tab.id)).trim();
  if (!text) {
    throw new Error("No text selected — highlight text on the page and try again.");
  }
  const payload = MeiBridge.selectionPayload({
    text,
    url: tab.url,
    title: tab.title,
    mode: document.getElementById("selectionMode").value,
    tags: document.getElementById("tagsInput").value,
  });
  const reply = await MeiBridge.post(settings, "save_selection", payload);
  setSendStatus(reply.message, !reply.ok);
}

function setSendBusy(busy) {
  ["connectBtn", "sendTabBtn", "sendSelectionBtn"].forEach(id => {
    document.getElementById(id).disabled = busy;
  });
}

/* --- wire-up -------------------------------------------------------------- */

document.getElementById("captureBtn").addEventListener("click", async () => {
  try {
    const payload = await captureCurrentWindow();
    showPayload(payload);
    setStatus(`Stored ${payload.tabs.length} tabs for ${payload.source_label}.`);
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Capture failed.", true);
  }
});

document.getElementById("captureAllBtn").addEventListener("click", async () => {
  try {
    await captureAllAndShow();
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Capture all failed.", true);
  }
});

document.getElementById("copyBtn").addEventListener("click", async () => {
  try {
    await copyPayload();
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Copy failed.", true);
  }
});

document.getElementById("downloadBtn").addEventListener("click", async () => {
  try {
    await downloadPayload();
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Download failed.", true);
  }
});

document.getElementById("downloadAllJsonBtn").addEventListener("click", async () => {
  try {
    await downloadAllJson();
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Download all failed.", true);
  }
});

document.getElementById("downloadAllZipBtn").addEventListener("click", async () => {
  try {
    await downloadAllZip();
  } catch (error) {
    console.error(error);
    setStatus(error.message || "ZIP export failed.", true);
  }
});

document.getElementById("refreshBtn").addEventListener("click", async () => {
  try {
    await refreshStoredBatch();
  } catch (error) {
    console.error(error);
    setStatus(error.message || "Refresh failed.", true);
  }
});

document.getElementById("connectBtn").addEventListener("click", async () => {
  try {
    setBridgeStatus("Connecting…");
    await connectBridge({});
  } catch (error) {
    console.error(error);
    setBridgeStatus(error.message || "Could not connect to Mei.", true);
  }
});

document.getElementById("sendTabBtn").addEventListener("click", async () => {
  setSendBusy(true);
  try {
    setSendStatus("Sending…");
    await sendTabToMei();
  } catch (error) {
    console.error(error);
    setSendStatus(error.message || "Could not send the tab.", true);
  } finally {
    setSendBusy(false);
  }
});

document.getElementById("sendSelectionBtn").addEventListener("click", async () => {
  setSendBusy(true);
  try {
    setSendStatus("Sending…");
    await sendSelectionToMei();
  } catch (error) {
    console.error(error);
    setSendStatus(error.message || "Could not send the selection.", true);
  } finally {
    setSendBusy(false);
  }
});

refreshStoredBatch().catch(error => {
  console.error(error);
  setStatus("Could not read stored batch.", true);
});

/* Opening the popup is the most common moment to notice Mei is (not) running,
 * so the pairing is checked quietly instead of waiting for a click. */
connectBridge({ quiet: true }).catch(error => {
  console.error(error);
  setBridgeStatus("Could not read the pairing settings.", true);
});
