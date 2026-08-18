// ============================================================
// Backup: export/import all local data as a single JSON file
// Loaded as a classic script (shared global scope). Order matters:
// utils -> storage -> api -> graph -> adaptation -> assessment ->
// session -> templates -> backup -> ui -> main (see index.html).
// ============================================================

const BACKUP_FORMAT = "mas-backup";

function buildBackupPayload() {
  return {
    app: BACKUP_FORMAT,
    version: "9.0.0",
    exportedAt: new Date().toISOString(),
    session: currentSession || null,
    templates,
    history: adaptationHistory
  };
}

function exportData() {
  const payload = buildBackupPayload();
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `mas-backup-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

// Reads a backup file and replaces local state. Returns a summary object.
function importData(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read the file."));
    reader.onload = () => {
      let data;
      try {
        data = JSON.parse(reader.result);
      } catch {
        return reject(new Error("Not valid JSON."));
      }
      if (data.app !== BACKUP_FORMAT) {
        return reject(new Error("Not a MAS backup file."));
      }
      try {
        if (data.session) currentSession = normalizeSession(data.session);
        if (Array.isArray(data.templates)) templates = normalizeTemplates(data.templates);
        if (Array.isArray(data.history)) adaptationHistory = normalizeHistory(data.history);

        saveSession();
        writeJson(STORAGE_KEYS.templates, templates);
        writeJson(STORAGE_KEYS.history, adaptationHistory);

        renderSession();
        renderTemplates();
        renderAdaptationPanel();
        resolve({
          session: !!data.session,
          templates: templates.length,
          history: adaptationHistory.length
        });
      } catch (e) {
        reject(new Error("Import failed: " + e.message));
      }
    };
    reader.readAsText(file);
  });
}
