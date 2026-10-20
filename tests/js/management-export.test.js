"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const root = path.resolve(__dirname, "../..");
const source = fs.readFileSync(path.join(root, "web_support/Cục Quản Lý/Hệ Thống Trích Xuất/app.js"), "utf8");
const keys = ["an_nguyen_storage_system_v1", "an_nguyen_storage_summary_v1", "an_nguyen_visualgraph_v1", "an_nguyen_visualgraph_summary_v1"];
const values = new Map([
  [keys[0], JSON.stringify([{ name: "file.txt", size: 12, category: "document", extension: "txt" }])],
  [keys[1], JSON.stringify({ count: 1, usedBytes: 12, remainingBytes: 100, categoryBreakdown: {} })],
  [keys[2], JSON.stringify([{ title: "Topic", keywords: ["keyword"], nodes: [{}], edges: [] }])],
  [keys[3], JSON.stringify({ title: "Topic", summary: "Summary" })],
]);
let failKey = null;
const elements = {};
const context = vm.createContext({
  localStorage: {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => { if (failKey === key) { failKey = null; throw new Error("quota"); } values.set(key, value); },
    removeItem: key => values.delete(key),
  },
  window: { addEventListener() {} },
  document: { getElementById: id => elements[id] ||= { value: { datasetScope: "all", formatSelect: "json", reportMode: "full" }[id], addEventListener() {} } },
  TextEncoder, TextDecoder, Uint8Array, DataView, ArrayBuffer,
});
vm.runInContext(source.replace(/    updatePreview\(\);\s*\}\)\(\);\s*$/, "    globalThis.qa = { collectData, pickScope, buildExportObject, previewText, applyRestoreObject, createSimpleZip, extractSimpleZipJson };\n})();"), context);
const qa = context.qa;
assert.ok(qa, "test seam must expose the real implementation");
let checks = 0;
for (const scope of ["all", "energy", "storage", "visualgraph"]) {
  for (const mode of ["full", "summary", "audit"]) {
    for (const format of ["json", "csv", "txt", "md", "html", "doc", "pdf"]) {
      const result = qa.buildExportObject(qa.pickScope(qa.collectData(), scope), mode);
      assert.ok(qa.previewText(result, format, mode).length, `${scope}/${mode}/${format}`);
      if (scope !== "all") assert.equal(result.scope, scope);
      if (format === "html") assert.ok(qa.previewText(result, format, mode).includes('lang="en"'));
      checks++;
    }
  }
}
const before = new Map(values);
assert.throws(() => qa.applyRestoreObject({ schema: "cuc-quan-ly-backup-v1", payload: { [keys[0]]: "[]", [keys[2]]: "{}" } }), /Invalid/);
assert.deepEqual(values, before, "validate all values before writing");
failKey = keys[2];
assert.throws(() => qa.applyRestoreObject({ schema: "cuc-quan-ly-backup-v1", payload: { [keys[0]]: "[]", [keys[2]]: "[]" } }), /preserved/);
assert.deepEqual(values, before, "quota failure must roll back earlier writes");
qa.applyRestoreObject({ schema: "cuc-quan-ly-backup-v1", payload: { [keys[0]]: null, [keys[2]]: "[]", unknown: "ignored" } });
assert.equal(values.has(keys[0]), false);
assert.equal(values.get(keys[2]), "[]");
assert.equal(values.get(keys[1]), before.get(keys[1]), "sparse restores preserve omitted keys");
assert.equal(values.has("unknown"), false);
const zip = qa.createSimpleZip("backup.json", '{"hello":"world"}');
assert.equal(qa.extractSimpleZipJson(zip.buffer), '{"hello":"world"}');
// Flip a payload byte, not the central-directory trailer.
const damaged = qa.createSimpleZip("backup.json", '{"hello":"world"}');
damaged[41] ^= 1;
assert.throws(() => qa.extractSimpleZipJson(damaged.buffer), /checksum/);
assert.throws(() => qa.extractSimpleZipJson(new ArrayBuffer(2)), /Invalid/);
console.log(`${checks} export combinations and backup validation/rollback checks passed`);
