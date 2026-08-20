/* =========================================================================
 * chain.js — Project Chain (bản chạy chung cho cả 7 app + hub)
 *
 * Một file duy nhất giúp các app nhận diện lẫn nhau:
 *   - Chạy local  (file://)  -> dùng đường dẫn tương đối ../<folder>/index.html
 *   - Deploy online (http/s) -> dùng URL remote tuyệt đối (Netlify/Render)
 *
 * Nguồn dữ liệu gốc là chain.json (cùng thư mục chain root). File này nhúng
 * sẵn một bản fallback để chạy offline (file://) và tự cập nhật từ chain.json
 * khi trang được mở qua http/https.
 * ========================================================================= */
(function () {
  "use strict";

  var EMBEDDED = {
    "version": 1,
    "name": "Project Chain",
    "chainName": "LiteBrowser · Project Chain",
    "apps": [
      { "id": "linklumina", "name": "LinkLumina", "glyph": "🔖", "subtitle": "Visual bookmark manager — lưu, sắp xếp và khám phá liên kết với nền sống động.", "color": "#e06c5b", "folder": "link", "remote": "https://graceful-kangaroo-4ebbee.netlify.app" },
      { "id": "cucquanly", "name": "Cục Quản Lý", "glyph": "📋", "subtitle": "Hub điều phối chính: năng lượng, lưu trữ, visualgraph, thư viện và trích xuất.", "color": "#5bc0de", "folder": "Cục Quản Lý", "remote": "https://starlit-lily-f90e23.netlify.app" },
      { "id": "mas", "name": "MAS — Mahoraga Adapt System", "glyph": "🔄", "subtitle": "Huấn luyện khả năng thích ứng với bất cứ thứ gì, từng bước một.", "color": "#8f7ae6", "folder": "MAS - Mahoraga Adapt System", "remote": "https://mahoraga-adapt-system-mas-v9-0.onrender.com" },
      { "id": "worldleaderboard", "name": "World Leaderboard", "glyph": "🏆", "subtitle": "Tính thứ hạng toàn cầu của bạn theo nhiều chỉ số, với biểu đồ và cột mốc.", "color": "#e6c05b", "folder": "World Leaderboard", "remote": "https://worldleaderboard.netlify.app" },
      { "id": "bimat", "name": "Bí Mật — PersonalFrequency", "glyph": "🔮", "subtitle": "Tần số cá nhân và những bí mật — khám phá tiềm năng qua con số và thông điệp riêng.", "color": "#b06bd1", "folder": "bí mật", "remote": "https://personalfrequencys.netlify.app" },
      { "id": "boitoan", "name": "Bói Toán Web", "glyph": "🎴", "subtitle": "Gieo quẻ và giải đáp — nhập câu hỏi cùng điều kiện, nhận lời giải đáp ngay trên web.", "color": "#e0a45b", "folder": "../../Bói Toán Web", "remote": "https://boitoanzaigame.netlify.app" },
      { "id": "hub", "name": "Project Hub", "glyph": "☰", "subtitle": "Trung tâm điều phối toàn chuỗi — một điểm khởi chạy cho cả 7.", "color": "#d8bf95", "folder": "hub", "remote": "" }
    ]
  };

  var isLocal = /^file:/i.test(location.protocol);
  // Root của thư mục chung chứa các app (thường là "../" vì các app nằm cạnh nhau
  // trong cùng một thư mục cha). Riêng Bói Toán Web nằm NGOÀI Code folder nên bản
  // chain.js trong thư mục đó ghi đè dòng này thành "../Code folder/".
  var localBase = "../";
  var manifest = EMBEDDED;

  function resolveUrl(app) {
    // Khi deploy (http/https) -> ưu tiên remote tuyệt đối; local -> ../folder/index.html
    if (!isLocal && app.remote) {
      return app.remote.replace(/\/+$/, "");
    }
    return localBase + app.folder + "/index.html";
  }

  function buildChain(data) {
    var apps = (data && data.apps) || [];
    var chain = {
      mode: isLocal ? "local" : "remote",
      name: (data && data.chainName) || (data && data.name) || "Project Chain",
      apps: apps.map(function (app) {
        return {
          id: app.id,
          name: app.name,
          glyph: app.glyph || "▦",
          subtitle: app.subtitle || "",
          color: app.color || "#d8bf95",
          folder: app.folder || app.id,
          remote: app.remote || "",
          local: localBase + (app.folder || app.id) + "/index.html",
          url: resolveUrl(app)
        };
      })
    };
    chain.appsById = {};
    chain.apps.forEach(function (a) { chain.appsById[a.id] = a; });
    chain.url = function (id) {
      var a = chain.appsById[id];
      return a ? a.url : "";
    };
    chain.app = function (id) { return chain.appsById[id] || null; };
    chain.hubUrl = chain.url("hub");
    chain.isLocal = isLocal;
    chain.manifestUrl = (isLocal ? "" : new URL("chain.json", location.href).href);
    return chain;
  }

  var CHAIN = buildChain(manifest);

  // Cập nhật mọi thẻ [data-chain-link="<id>"] về URL đúng theo ngữ cảnh.
  function applyLinks() {
    var nodes = document.querySelectorAll("[data-chain-link]");
    for (var i = 0; i < nodes.length; i++) {
      var el = nodes[i];
      var id = el.getAttribute("data-chain-link");
      var url = CHAIN.url(id);
      if (url) el.setAttribute("href", url);
      if (el.hasAttribute("data-chain-text")) {
        var a = CHAIN.app(id);
        if (a) el.textContent = el.getAttribute("data-chain-text").replace("{name}", a.name);
      }
    }
    // Thông báo cho page biết chain đã sẵn sàng.
    if (document.dispatchEvent) {
      document.dispatchEvent(new CustomEvent("chain:ready", { detail: CHAIN }));
    }
  }

  window.CHAIN = CHAIN;

  function ready(fn) {
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", fn);
    } else {
      fn();
    }
  }
  ready(applyLinks);

  // Khi online (http/https), đồng bộ lại từ chain.json để remote URL luôn mới.
  if (!isLocal) {
    try {
      fetch("chain.json", { cache: "no-store" })
        .then(function (r) { return r.ok ? r.json() : null; })
        .then(function (data) {
          if (!data || !data.apps) return;
          window.CHAIN = CHAIN = buildChain(data);
          applyLinks();
        })
        .catch(function () { /* giữ fallback embedded */ });
    } catch (e) { /* fetch không khả dụng */ }
  }
})();
