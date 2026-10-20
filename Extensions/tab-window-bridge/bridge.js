/* The extension's half of the Mei bridge protocol (v1.2).
 *
 * Purpose: the popup used to only *export* a workspace file and ask you to
 * import it by hand. It can now call the desktop bridge directly — "send this
 * tab to Mei", "send this selection" — so the wire format lives in one place
 * instead of being spelled out inside click handlers.
 *
 * Everything here is pure: no DOM, no chrome.*, no side effects. popup.js
 * supplies the storage/fetch parts; bridge.js decides what a pairing code
 * means, what an envelope looks like, and how a reply is worded. It is
 * CommonJS-loadable, so tests/js/bridge.test.js exercises it under Node the same
 * way the ZIP writer is exercised.
 *
 * Desktop side, for reference (litebrowser/services/android_bridge_service.py):
 *   POST /api/mobile/ingest   {action, source, payload}   Authorization: Bearer <token>
 *   GET  /api/mobile/ping     {ok, app, version, mode, capabilities}
 * A browser extension is answered over CORS; a web page never is.
 */
(function (root) {
  "use strict";

  var PAIRING_PREFIX = "MEI1";
  var DEFAULT_HOST = "127.0.0.1";
  var DEFAULT_PORT = 18444; /* prefs.MOBILE_BRIDGE_DEFAULT_PORT */
  var SOURCE = "extension.tab-window-bridge";
  var SELECTION_MODES = ["note", "card", "saved_page"];
  var LOOPBACK_HOSTS = ["127.0.0.1", "localhost", "::1"];
  var MAX_TOKEN_CHARS = 512; /* android_bridge_service.PAIRING_MAX_TOKEN_CHARS */
  var MAX_TAGS = 12;
  var MAX_TAG_CHARS = 48;
  var REQUEST_TIMEOUT_MS = 8000;

  /* --- pairing / settings -------------------------------------------------- */

  function cleanHost(value) {
    var host = String(value == null ? "" : value).trim();
    if (!host) return "";
    if (host.length > 253 || /[\s/\\|,?#@%]/.test(host)) return "";
    if (host.indexOf(":") >= 0) {
      if (!/^(?:[0-9a-f]*:){2,}[0-9a-f.]*$/i.test(host.replace(/^\[|\]$/g, ""))) return "";
    } else if (!/^[a-z0-9.-]+$/i.test(host)) return "";
    return host;
  }

  function isLoopbackHost(value) {
    return LOOPBACK_HOSTS.indexOf(String(value || "").trim().toLowerCase().replace(/^\[|\]$/g, "")) >= 0;
  }

  /* Mirrors android_bridge_service.parse_pairing_code: MEI1|host|port|token,
   * exactly four parts, digits for the port, a real TCP port range, and
   * non-empty host + token. Anything else is "not a pairing code", so the
   * popup can say so instead of failing later with a network error. */
  function parsePairingCode(code) {
    var parts = String(code == null ? "" : code).trim().split("|");
    if (parts.length !== 4 || parts[0] !== PAIRING_PREFIX) return null;
    var host = cleanHost(parts[1]);
    var rawPort = parts[2].trim();
    var token = parts[3].trim();
    if (!host || !token || !/^[0-9]{1,5}$/.test(rawPort)) return null;
    var port = Number(rawPort);
    if (!(port >= 1 && port <= 65535)) return null;
    if (token.length > MAX_TOKEN_CHARS || /[\r\n\x00]/.test(token)) return null;
    return { host: host, port: port, token: token };
  }

  /* Anything read back from storage/inputs becomes a settings object the URL
   * builders can trust: a host, a usable port, a trimmed token. */
  function normalizeSettings(raw) {
    var stored = raw || {};
    var host = cleanHost(stored.host) || DEFAULT_HOST;
    var port = Math.floor(Number(stored.port));
    if (!Number.isFinite(port) || port < 1 || port > 65535) port = DEFAULT_PORT;
    var token = String(stored.token == null ? "" : stored.token).trim();
    return { host: host, port: port, token: token };
  }

  function isConfigured(settings) {
    return Boolean(normalizeSettings(settings).token);
  }

  function origin(settings) {
    var s = normalizeSettings(settings);
    var host = s.host.indexOf(":") >= 0 ? "[" + s.host.replace(/^\[|\]$/g, "") + "]" : s.host;
    return "http://" + host + ":" + s.port;
  }

  function ingestUrl(settings) {
    return origin(settings) + "/api/mobile/ingest";
  }

  function pingUrl(settings) {
    return origin(settings) + "/api/mobile/ping";
  }

  /* --- payloads ------------------------------------------------------------ */

  function envelope(action, payload) {
    return { action: String(action || ""), source: SOURCE, payload: payload || {} };
  }

  /* A tab as save_page expects it. Title falls back to the URL because a tab
   * that is still loading has no title yet, and an empty title on the desktop
   * becomes a note named "". */
  function tabPayload(tab, extra) {
    var t = tab || {};
    var url = String(t.url || "").trim();
    var payload = { url: url, title: String(t.title || "").trim() || url };
    var merged = extra || {};
    Object.keys(merged).forEach(function (key) {
      var value = merged[key];
      if (value == null || value === "") return;
      payload[key] = value;
    });
    return payload;
  }

  /* "networking, ôn thi" / ["#networking"] → ["networking", "ôn thi"].
   * Anki tags carry no spaces, so the card side turns inner spaces into dashes;
   * the note side keeps whatever the reader typed. */
  function splitTags(value) {
    var raw = [];
    if (Array.isArray(value)) {
      raw = value.slice();
    } else {
      raw = String(value == null ? "" : value).split(",");
    }
    var out = [];
    raw.forEach(function (item) {
      var tag = String(item == null ? "" : item).trim().replace(/^#+/, "").trim();
      if (!tag) return;
      if (tag.length > MAX_TAG_CHARS) tag = tag.slice(0, MAX_TAG_CHARS).trim();
      if (!tag) return;
      var seen = out.some(function (existing) {
        return existing.toLowerCase() === tag.toLowerCase();
      });
      if (seen) return;
      if (out.length >= MAX_TAGS) return;
      out.push(tag);
    });
    return out;
  }

  /* A selection as save_selection expects it. `as` decides where it lands:
   * note (Clippings), card (a deck flashcard), saved_page (library). */
  function selectionPayload(input) {
    var i = input || {};
    var mode = SELECTION_MODES.indexOf(String(i.mode || "")) >= 0 ? String(i.mode) : "note";
    var url = String(i.url || "").trim();
    var title = String(i.title || "").trim();
    var payload = {
      text: String(i.text == null ? "" : i.text),
      as: mode,
      url: url,
      title: title || url || "Selection",
    };
    var tags = splitTags(i.tags);
    if (tags.length) payload.tags = tags;
    if (mode === "card") payload.front = String(i.front || "").trim() || title || url;
    if (mode === "note" && i.category) payload.category = String(i.category).trim();
    return payload;
  }

  /* --- replies ------------------------------------------------------------- */

  function describeReply(body) {
    var result = (body && body.result) || {};
    switch ((body && body.action) || "") {
      case "save_page":
        return "Tab sent to Mei: " + (result.url || "");
      case "save_selection":
        if (result.card_id != null) return "Saved as a flashcard: " + (result.front || "");
        if (result.saved_page_id != null) return "Page saved: " + (result.url || "");
        return "Note saved in Mei" + (result.category ? " (" + result.category + ")" : "");
      default:
        return "Received by Mei.";
    }
  }

  /* One line a human can read, whether the bridge said ok or refused. */
  function replyMessage(body) {
    if (body && body.ok) return describeReply(body);
    var error = (body && body.error) || {};
    return error.message || error.code || "Mei rejected the request.";
  }

  function capabilitiesLine(body) {
    var b = body || {};
    var caps = Array.isArray(b.capabilities) ? b.capabilities : [];
    var line = "Mei " + (b.version || "?") + " · " + (b.mode === "lan" ? "LAN" : "this device only");
    if (caps.indexOf("save_selection") < 0) {
      line += " · this Mei version does not support sending selections";
    }
    return line;
  }

  /* --- talking to the bridge ----------------------------------------------- */

  function unreachable(settings, detail) {
    return {
      status: 0,
      ok: false,
      body: null,
      message:
        "Could not reach Mei at " +
        origin(settings) +
        " (" +
        detail +
        "). Check that Mei → Settings → Mobile bridge is enabled and the pairing code is current.",
    };
  }

  function failureDetail(error, timeoutMs) {
    if (error && error.name === "AbortError") {
      var seconds = Math.max(1, Math.round((timeoutMs || REQUEST_TIMEOUT_MS) / 1000));
      return "Mei did not respond after " + seconds + "s";
    }
    return (error && (error.message || error.name)) || "network error";
  }

  /* A fetch implementation that throws synchronously behaves like one that
   * rejects, so a caller has one failure path instead of two — and never a
   * half-built "response" that readReply would ask for .text(). */
  function sendRequest(impl, url, options) {
    try {
      return Promise.resolve(impl(url, options));
    } catch (error) {
      return Promise.reject(error);
    }
  }

  /* Never rejects: a caller always gets {status, ok, body, message}, because a
   * "network error" in a popup is a dead end while a sentence is a next step. */
  function requestJson(settings, url, init, fetchImpl, timeoutMs) {
    var s = normalizeSettings(settings);
    var impl = fetchImpl || (typeof fetch === "function" ? fetch : null);
    if (!impl) return Promise.resolve(unreachable(s, "this browser does not support fetch"));
    var budget = timeoutMs || REQUEST_TIMEOUT_MS;

    var options = Object.assign({}, init);
    var controller = typeof AbortController === "function" && !options.signal ? new AbortController() : null;
    if (controller) options.signal = controller.signal;
    // Keep the deadline through response.text(), not just response headers.
    // Promise.race also bounds fetch implementations that ignore abort.
    var timer;
    var deadline = new Promise(function (resolve) {
      timer = setTimeout(function () {
        if (controller) controller.abort();
        resolve(unreachable(s, failureDetail({ name: "AbortError" }, budget)));
      }, budget);
    });
    var request = sendRequest(impl, url, options).then(readReply).catch(function (error) {
      return unreachable(s, failureDetail(error, budget));
    });
    return Promise.race([request, deadline]).then(function (reply) {
      clearTimeout(timer);
      return reply;
    });
  }

  function readReply(response) {
    return response.text().then(function (raw) {
      var body = null;
      if (raw) {
        try {
          body = JSON.parse(raw);
        } catch (error) {
          body = null;
        }
      }
      if (!body || typeof body !== "object") {
        return {
          status: response.status,
          ok: false,
          body: null,
          message: "Unreadable response from Mei (HTTP " + response.status + ").",
        };
      }
      return {
        status: response.status,
        ok: response.status >= 200 && response.status < 300 && body.ok === true,
        body: body,
        message: replyMessage(body),
      };
    });
  }

  function needsToken() {
    return {
      status: 0,
      ok: false,
      body: null,
      message: "Mei is not paired — paste the pairing code (MEI1|host|port|token) from Mei → Settings → Mobile bridge and press Connect.",
    };
  }

  function post(settings, action, payload, fetchImpl) {
    var s = normalizeSettings(settings);
    if (!s.token) return Promise.resolve(needsToken());
    return requestJson(
      s,
      ingestUrl(s),
      {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Authorization: "Bearer " + s.token,
        },
        body: JSON.stringify(envelope(action, payload)),
        cache: "no-store",
      },
      fetchImpl
    );
  }

  function ping(settings, fetchImpl) {
    var s = normalizeSettings(settings);
    if (!s.token) return Promise.resolve(needsToken());
    return requestJson(
      s,
      pingUrl(s),
      {
        method: "GET",
        headers: { Authorization: "Bearer " + s.token },
        cache: "no-store",
      },
      fetchImpl
    );
  }

  var api = {
    PAIRING_PREFIX: PAIRING_PREFIX,
    DEFAULT_HOST: DEFAULT_HOST,
    DEFAULT_PORT: DEFAULT_PORT,
    SOURCE: SOURCE,
    SELECTION_MODES: SELECTION_MODES,
    cleanHost: cleanHost,
    isLoopbackHost: isLoopbackHost,
    parsePairingCode: parsePairingCode,
    normalizeSettings: normalizeSettings,
    isConfigured: isConfigured,
    origin: origin,
    ingestUrl: ingestUrl,
    pingUrl: pingUrl,
    envelope: envelope,
    tabPayload: tabPayload,
    splitTags: splitTags,
    selectionPayload: selectionPayload,
    describeReply: describeReply,
    replyMessage: replyMessage,
    capabilitiesLine: capabilitiesLine,
    requestJson: requestJson,
    post: post,
    ping: ping,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = api;
  } else {
    root.MeiBridge = api;
  }
})(typeof globalThis !== "undefined" ? globalThis : this);
