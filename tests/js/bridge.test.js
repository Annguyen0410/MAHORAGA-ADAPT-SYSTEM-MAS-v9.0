/* Node harness for the extension's bridge helpers (Extensions/tab-window-bridge/bridge.js).
 *
 * Why a JS test in a Python repo: the popup's half of the bridge protocol is
 * JavaScript, and the bug worth catching is precisely "the two halves disagree"
 * (a pairing code the desktop accepts and the popup refuses, an envelope the
 * bridge answers with invalid_payload, a reply nobody can read). The pure
 * helpers are CommonJS-loadable for exactly this, next to zip.js.
 *
 * Run by tests/test_extension_bridge_js.py:
 *   node tests/js/bridge.test.js
 *   node tests/js/bridge.test.js --parse-codes '["MEI1|127.0.0.1|18444|tok"]'
 * No dependencies, no network: every request is a fake fetch.
 */
"use strict";

const path = require("path");

const bridge = require(path.join(__dirname, "..", "..", "Extensions", "tab-window-bridge", "bridge.js"));

const failures = [];
let checks = 0;

function test(name, fn) {
  try {
    fn();
    checks += 1;
  } catch (error) {
    failures.push(name + " → " + (error && (error.message || error)));
  }
}

async function testAsync(name, fn) {
  try {
    await fn();
    checks += 1;
  } catch (error) {
    failures.push(name + " → " + (error && (error.message || error)));
  }
}

/* --- pairing codes ------------------------------------------------------- */

test("a code in the desktop's own format parses", () => {
  const parsed = bridge.parsePairingCode("MEI1|192.168.1.7|18444|a1b2c3");
  if (parsed.host !== "192.168.1.7" || parsed.port !== 18444 || parsed.token !== "a1b2c3") {
    throw new Error("got " + JSON.stringify(parsed));
  }
});

test("surrounding whitespace and port boundaries are tolerated", () => {
  const padded = bridge.parsePairingCode("  MEI1|127.0.0.1|18444|tok\n");
  if (padded.port !== 18444) throw new Error("padded code did not parse: " + JSON.stringify(padded));
  if (bridge.parsePairingCode("MEI1|h|1|t").port !== 1) throw new Error("port 1 rejected");
  if (bridge.parsePairingCode("MEI1|h|65535|t").port !== 65535) throw new Error("port 65535 rejected");
});

test("anything that is not a pairing code is refused", () => {
  const bad = [
    "",
    "not-a-code",
    "mei1|h|18444|t", // prefix is case-sensitive
    "MEI2|h|18444|t",
    "MEI1|h|18444",
    "MEI1||18444|t", // no host
    "MEI1|h|18444|", // no token
    "MEI1|h|18444|t|extra",
    "MEI1|h|notaport|t",
    "MEI1|h|0|t", // outside the real TCP range
    "MEI1|h|65536|t",
    "MEI1|127.0.0.1/x|18444|t",
    "MEI1|has space|18444|t",
    "MEI1|user@host|18444|t",
    "MEI1|host?redirect=evil|18444|t",
    "MEI1|host:123|18444|t",
    "MEI1|host|١٢٣|t",
    null,
    undefined,
    42,
    {},
  ];
  bad.forEach((code) => {
    if (bridge.parsePairingCode(code) !== null) {
      throw new Error("accepted a code it should refuse: " + JSON.stringify(code));
    }
  });
});

test("a 512-character token is still a code, a longer one is not", () => {
  const long = "t".repeat(512);
  if (!bridge.parsePairingCode(`MEI1|h|18444|${long}`)) throw new Error("512-char token refused");
  if (bridge.parsePairingCode(`MEI1|h|18444|${long}t`) !== null) throw new Error("513-char token accepted");
});

test("loopback hosts are recognised (including the LAN code the QR carries)", () => {
  ["127.0.0.1", "localhost", "::1", "[::1]", "LOCALHOST"].forEach((host) => {
    if (!bridge.isLoopbackHost(host)) throw new Error(host + " should be loopback");
  });
  ["192.168.1.7", "0.0.0.0", "10.0.0.2", ""].forEach((host) => {
    if (bridge.isLoopbackHost(host)) throw new Error(host + " should not be loopback");
  });
});

/* --- settings / URLs ----------------------------------------------------- */

test("settings fall back to the desktop defaults and stay URL-safe", () => {
  const defaults = bridge.normalizeSettings(null);
  if (defaults.host !== "127.0.0.1" || defaults.port !== 18444 || defaults.token !== "") {
    throw new Error("unexpected defaults " + JSON.stringify(defaults));
  }
  const stored = bridge.normalizeSettings({ host: "192.168.1.7", port: "9000", token: "  tok  " });
  if (stored.host !== "192.168.1.7" || stored.port !== 9000 || stored.token !== "tok") {
    throw new Error("unexpected settings " + JSON.stringify(stored));
  }
  [0, 70000, "x", null, undefined, -1].forEach((port) => {
    const fixed = bridge.normalizeSettings({ port });
    if (fixed.port !== 18444) throw new Error("port " + String(port) + " should fall back to 18444");
  });
  ["127.0.0.1/x", "has space", "pipe|host", ""].forEach((host) => {
    const fixed = bridge.normalizeSettings({ host });
    if (fixed.host !== "127.0.0.1") throw new Error("host " + host + " should fall back to loopback");
  });
  if (bridge.isConfigured({})) throw new Error("a token-less setting is not configured");
  if (!bridge.isConfigured({ token: "tok" })) throw new Error("a token means configured");
});

test("URLs point at the bridge endpoints the desktop serves", () => {
  const settings = { host: "127.0.0.1", port: 18444, token: "tok" };
  if (bridge.origin(settings) !== "http://127.0.0.1:18444") throw new Error("bad origin");
  if (bridge.ingestUrl(settings) !== "http://127.0.0.1:18444/api/mobile/ingest") throw new Error("bad ingest url");
  if (bridge.pingUrl(settings) !== "http://127.0.0.1:18444/api/mobile/ping") throw new Error("bad ping url");
  if (bridge.origin({ host: "::1", port: 18444 }) !== "http://[::1]:18444") throw new Error("IPv6 must be bracketed");
});

/* --- payloads ------------------------------------------------------------ */

test("an envelope carries the action, a source tag and a payload object", () => {
  const env = bridge.envelope("save_page", { url: "https://x/y" });
  if (env.action !== "save_page") throw new Error("bad action");
  if (env.source !== bridge.SOURCE) throw new Error("bad source");
  if (env.payload.url !== "https://x/y") throw new Error("payload lost");
  const bare = bridge.envelope("save_page");
  if (typeof bare.payload !== "object" || bare.payload === null) throw new Error("payload must default to an object");
  if (bridge.envelope("").action !== "") throw new Error("a missing action must stay missing for the bridge to refuse");
});

test("a tab becomes a save_page payload with a title fallback", () => {
  const tab = { url: "https://x/y", title: "  Krebs  " };
  const payload = bridge.tabPayload(tab);
  if (payload.title !== "Krebs") throw new Error("title should be trimmed: " + payload.title);
  const untitled = bridge.tabPayload({ url: "https://x/y" });
  if (untitled.title !== "https://x/y") throw new Error("an untitled tab should fall back to its URL");
  const empty = bridge.tabPayload({});
  if (empty.url !== "" || empty.title !== "") throw new Error("a tabless call should send empty strings");
  const withSummary = bridge.tabPayload(tab, { summary: "note to self", source_app: "" });
  if (withSummary.summary !== "note to self") throw new Error("extra fields should be merged");
  if ("source_app" in withSummary) throw new Error("empty extra fields should be dropped");
});

test("tags are cleaned, deduped and bounded", () => {
  const tags = bridge.splitTags("networking, #ôn thi, Networking , , phân trang");
  if (tags.join("|") !== "networking|ôn thi|phân trang") throw new Error("got " + tags.join("|"));
  const fromArray = bridge.splitTags(["graphs", "  #graphs  ", "week 2"]);
  if (fromArray.join("|") !== "graphs|week 2") throw new Error("got " + fromArray.join("|"));
  const many = bridge.splitTags(Array.from({ length: 30 }, (unused, i) => "tag" + i));
  if (many.length !== 12) throw new Error("expected 12 tags, got " + many.length);
  const long = bridge.splitTags(["x".repeat(80)]);
  if (long[0].length !== 48) throw new Error("expected a 48-character tag, got " + long[0].length);
  if (bridge.splitTags("").length !== 0) throw new Error("empty tags should stay empty");
  if (bridge.splitTags(["###"]).length !== 0) throw new Error("a bare hash is not a tag");
});

test("a selection becomes the payload save_selection expects", () => {
  const note = bridge.selectionPayload({ text: "citrate", url: "https://x/y", title: "Krebs", tags: "ôn thi" });
  if (note.as !== "note") throw new Error("default mode should be a note");
  if (note.title !== "Krebs" || note.url !== "https://x/y") throw new Error("source lost");
  if (note.tags.join("|") !== "ôn thi") throw new Error("tags lost");
  if ("front" in note) throw new Error("only a card has a front");

  const card = bridge.selectionPayload({ text: "7", mode: "card", title: "OSI layers" });
  if (card.front !== "OSI layers") throw new Error("a card front should default to the page title");
  const explicitFront = bridge.selectionPayload({ text: "7", mode: "card", title: "OSI", front: "How many layers?" });
  if (explicitFront.front !== "How many layers?") throw new Error("an explicit front was ignored");

  const page = bridge.selectionPayload({ text: "x", mode: "saved_page", url: "https://x/y" });
  if (page.as !== "saved_page") throw new Error("saved_page mode lost");

  const weird = bridge.selectionPayload({ text: "x", mode: "delete_everything" });
  if (weird.as !== "note") throw new Error("an unknown mode must fall back to note, never to a new verb");
  const empty = bridge.selectionPayload({});
  if (empty.text !== "" || empty.as !== "note") throw new Error("an empty selection is still sent for the bridge to refuse");
  if (empty.title !== "Selection") throw new Error("an untitled selection needs a name");
  const categorised = bridge.selectionPayload({ text: "x", category: "Study" });
  if (categorised.category !== "Study") throw new Error("an explicit category was lost");
});

/* --- replies ------------------------------------------------------------- */

test("replies become one readable sentence, ok or not", () => {
  const tab = bridge.replyMessage({ ok: true, action: "save_page", result: { url: "https://x/y" } });
  if (!tab.includes("https://x/y")) throw new Error("got " + tab);
  const card = bridge.replyMessage({ ok: true, action: "save_selection", result: { card_id: "c1", front: "OSI" } });
  if (!card.includes("OSI")) throw new Error("got " + card);
  const note = bridge.replyMessage({ ok: true, action: "save_selection", result: { note_id: "n1", category: "Clippings" } });
  if (!note.includes("Clippings")) throw new Error("got " + note);
  const refused = bridge.replyMessage({ ok: false, error: { code: "unauthorized", message: "Invalid or missing token" } });
  if (refused !== "Invalid or missing token") throw new Error("got " + refused);
  const codeless = bridge.replyMessage({ ok: false, error: { code: "invalid_payload" } });
  if (codeless !== "invalid_payload") throw new Error("got " + codeless);
  if (!bridge.replyMessage(null).length) throw new Error("a null body still needs a sentence");
  if (bridge.replyMessage({ ok: true }).length === 0) throw new Error("an ok body needs a sentence");
});

test("the capability line mentions the version, the mode, and a missing action", () => {
  const full = bridge.capabilitiesLine({ version: "1.0.0.0", mode: "local", capabilities: ["save_page", "save_selection"] });
  if (!full.includes("1.0.0.0") || !full.includes("this device only")) throw new Error("got " + full);
  if (full.includes("does not support")) throw new Error("a capable bridge must not be warned about");
  const old = bridge.capabilitiesLine({ version: "0.7.1.0", mode: "lan", capabilities: ["save_page"] });
  if (!old.includes("LAN") || !old.includes("does not support sending selections")) throw new Error("got " + old);
});

/* --- talking to the bridge (fake fetch, real logic) ----------------------- */

function jsonResponse(status, body) {
  return { status, text: () => Promise.resolve(typeof body === "string" ? body : JSON.stringify(body)) };
}

function recordingFetch(response, log) {
  return (url, options) => {
    log.push({ url, options });
    return Promise.resolve(response);
  };
}

async function run() {
  await testAsync("without a token nothing is sent and the message says so", async () => {
    const log = [];
    const reply = await bridge.post({}, "save_page", { url: "https://x/y" }, recordingFetch(jsonResponse(200, {}), log));
    if (reply.ok) throw new Error("a token-less call must not succeed");
    if (!reply.message.includes("not paired")) throw new Error("got " + reply.message);
    if (log.length) throw new Error("no request should have been made");
  });

  await testAsync("a request goes to /api/mobile/ingest with the token and the envelope", async () => {
    const log = [];
    const reply = await bridge.post(
      { host: "127.0.0.1", port: 18444, token: "tok" },
      "save_page",
      { url: "https://x/y", title: "Krebs" },
      recordingFetch(jsonResponse(200, { ok: true, action: "save_page", result: { url: "https://x/y" } }), log)
    );
    if (!reply.ok || reply.status !== 200) throw new Error("expected success, got " + JSON.stringify(reply));
    if (!reply.message.includes("https://x/y")) throw new Error("got " + reply.message);
    if (log.length !== 1) throw new Error("expected exactly one request");
    const sent = log[0];
    if (sent.url !== "http://127.0.0.1:18444/api/mobile/ingest") throw new Error("wrong url " + sent.url);
    if (sent.options.method !== "POST") throw new Error("wrong method");
    if (sent.options.headers.Authorization !== "Bearer tok") throw new Error("missing bearer token");
    if (!String(sent.options.headers["Content-Type"]).includes("application/json")) throw new Error("wrong content type");
    const body = JSON.parse(sent.options.body);
    if (body.action !== "save_page" || body.source !== bridge.SOURCE || body.payload.title !== "Krebs") {
      throw new Error("wrong envelope " + sent.options.body);
    }
  });

  await testAsync("a 401 from the bridge is reported as a sentence, not an exception", async () => {
    const reply = await bridge.post(
      { token: "stale" },
      "save_page",
      { url: "https://x/y" },
      () => Promise.resolve(jsonResponse(401, { ok: false, error: { code: "unauthorized", message: "Invalid or missing token" } }))
    );
    if (reply.ok || reply.status !== 401) throw new Error("expected a 401 result");
    if (reply.message !== "Invalid or missing token") throw new Error("got " + reply.message);
  });

  await testAsync("a reply that is not JSON is reported instead of crashing the popup", async () => {
    const reply = await bridge.post({ token: "tok" }, "save_page", { url: "u" }, () => Promise.resolve(jsonResponse(200, "<html>nope</html>")));
    if (reply.ok) throw new Error("an unreadable body must not look like success");
    if (!reply.message.includes("HTTP 200")) throw new Error("got " + reply.message);
  });

  await testAsync("a dead bridge and a sync-throwing fetch both end as guidance", async () => {
    const dead = await bridge.post({ token: "tok" }, "save_page", { url: "u" }, () => Promise.reject(new Error("Failed to fetch")));
    if (dead.status !== 0 || dead.ok) throw new Error("a dead bridge must be status 0");
    if (!dead.message.includes("http://127.0.0.1:18444") || !dead.message.includes("Mobile bridge")) {
      throw new Error("the message should name the address and the switch: " + dead.message);
    }
    const thrown = await bridge.post({ token: "tok" }, "save_page", { url: "u" }, () => {
      throw new Error("sync boom");
    });
    if (thrown.status !== 0 || !thrown.message.includes("sync boom")) throw new Error("got " + JSON.stringify(thrown));
  });

  await testAsync("a hung bridge times out into a sentence instead of hanging the popup", async () => {
    const hang = (url, options) =>
      new Promise((resolve, reject) => {
        if (options.signal) {
          options.signal.addEventListener("abort", () => {
            const error = new Error("aborted");
            error.name = "AbortError";
            reject(error);
          });
        }
      });
    const reply = await bridge.requestJson(
      { token: "tok" },
      "http://127.0.0.1:18444/api/mobile/ping",
      { method: "GET" },
      hang,
      40
    );
    if (reply.status !== 0) throw new Error("a timeout must be status 0");
    if (!reply.message.includes("did not respond")) throw new Error("got " + reply.message);
  });

  await testAsync("a stalled or failed response body never hangs or rejects", async () => {
    const settings = { token: "tok" };
    const hung = await bridge.requestJson(settings, bridge.pingUrl(settings), {}, () => Promise.resolve({
      status: 200, text: () => new Promise(() => {}),
    }), 30);
    if (hung.ok || !hung.message.includes("did not respond")) throw new Error("body deadline missing");
    const failed = await bridge.requestJson(settings, bridge.pingUrl(settings), {}, () => Promise.resolve({
      status: 200, text: () => Promise.reject(new Error("body failed")),
    }), 30);
    if (failed.ok || !failed.message.includes("body failed")) throw new Error("body rejection escaped");
  });

  await testAsync("ping reports the desktop version, mode and capabilities", async () => {
    const log = [];
    const reply = await bridge.ping(
      { token: "tok" },
      recordingFetch(jsonResponse(200, { ok: true, version: "1.0.0.0", mode: "local", capabilities: ["save_page", "save_selection"] }), log)
    );
    if (!reply.ok) throw new Error("ping should succeed");
    if (log[0].url !== "http://127.0.0.1:18444/api/mobile/ping") throw new Error("wrong url " + log[0].url);
    if (log[0].options.method !== "GET") throw new Error("ping must be a GET");
    if (log[0].options.headers.Authorization !== "Bearer tok") throw new Error("ping must carry the token");
    const line = bridge.capabilitiesLine(reply.body);
    if (!line.includes("1.0.0.0")) throw new Error("got " + line);
  });

  if (failures.length) {
    failures.forEach((line) => console.error("  ✗ " + line));
    console.log(`bridge.js: ${checks} passed, ${failures.length} failed`);
    process.exitCode = 1;
    return;
  }
  console.log(`bridge.js: ${checks} checks passed`);
}

/* Used by tests/test_extension_bridge_js.py to compare this parser against the
 * desktop's parse_pairing_code on the exact same strings. */
function parseCodesMode(payload) {
  const codes = JSON.parse(payload);
  const out = codes.map((code) => {
    const parsed = bridge.parsePairingCode(code);
    return parsed ? { host: parsed.host, port: String(parsed.port), token: parsed.token } : null;
  });
  process.stdout.write(JSON.stringify(out));
}

const args = process.argv.slice(2);
if (args[0] === "--parse-codes") {
  parseCodesMode(args[1]);
} else {
  run().catch((error) => {
    console.error("bridge.js: harness failed → " + (error && error.stack));
    process.exitCode = 1;
  });
}

