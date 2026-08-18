// MAS test runner: runs each *.test.js in a clean child process.
const { spawnSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const files = fs.readdirSync(__dirname).filter((f) => f.endsWith(".test.js")).sort();
let failed = 0;

for (const f of files) {
  const r = spawnSync(process.execPath, [path.join(__dirname, f)], { encoding: "utf8", timeout: 30000 });
  if (r.status === 0) {
    console.log("PASS  " + f);
    if (r.stdout) process.stdout.write(r.stdout);
  } else {
    failed++;
    console.error("FAIL  " + f);
    if (r.stderr) process.stderr.write(r.stderr);
    if (r.stdout) process.stdout.write(r.stdout);
  }
}

console.log(failed === 0
  ? `\nAll ${files.length} test files passed`
  : `\n${failed}/${files.length} test files FAILED`);
process.exit(failed === 0 ? 0 : 1);
