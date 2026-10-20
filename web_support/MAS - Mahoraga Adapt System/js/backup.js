// Backup: export/import all local data as a single JSON file.
const BACKUP_FORMAT = "mas-backup";
function buildBackupPayload() {
  return { app: BACKUP_FORMAT, version: "9.0.0", exportedAt: new Date().toISOString(),
    session: currentSession || null, templates, history: adaptationHistory };
}
function exportData() {
  const blob = new Blob([JSON.stringify(buildBackupPayload(), null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `mas-backup-${new Date().toISOString().slice(0, 10)}.json`;
  document.body.appendChild(a);
  a.click(); a.remove(); URL.revokeObjectURL(url);
}
function importData(file) {
  return new Promise((resolve, reject) => {
    if (file.size > 20 * 1024 * 1024) return reject(new Error("Backup exceeds 20 MB."));
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read the file."));
    reader.onload = () => {
      let data;
      try { data = JSON.parse(reader.result); } catch { return reject(new Error("Not valid JSON.")); }
      if (!data || typeof data !== "object" || Array.isArray(data) || data.app !== BACKUP_FORMAT) {
        return reject(new Error("Not a MAS backup file."));
      }
      const previous = { session: currentSession, templates, history: adaptationHistory };
      const keys = [STORAGE_KEYS.session, STORAGE_KEYS.templates, STORAGE_KEYS.history];
      let stored;
      try {
        if (data.session !== undefined && data.session !== null && (!data.session || typeof data.session !== "object" || Array.isArray(data.session))) throw new Error("Invalid session.");
        for (const key of ["templates", "history"]) {
          if (data[key] !== undefined && !Array.isArray(data[key])) throw new Error(`Invalid ${key}.`);
        }
        const next = {
          session: data.session === undefined ? currentSession : normalizeSession(data.session),
          templates: data.templates === undefined ? templates : normalizeTemplates(data.templates),
          history: data.history === undefined ? adaptationHistory : normalizeHistory(data.history)
        };
        stored = keys.map(key => localStorage.getItem(key));
        writeJson(keys[0], next.session);
        writeJson(keys[1], next.templates);
        writeJson(keys[2], next.history);
        for (const key of ["session", "capture"]) clearTimeout(_saveTimers[key]);
        currentSession = next.session; templates = next.templates; adaptationHistory = next.history;
        renderSession(); renderTemplates(); renderAdaptationPanel();
        resolve({ session: !!currentSession, templates: templates.length, history: adaptationHistory.length });
      } catch (error) {
        currentSession = previous.session; templates = previous.templates; adaptationHistory = previous.history;
        let recoveryFailed = false;
        if (stored) keys.forEach((key, index) => {
          try {
            if (stored[index] === null) localStorage.removeItem(key);
            else localStorage.setItem(key, stored[index]);
          } catch { recoveryFailed = true; }
        });
        reject(new Error("Import failed: " + error.message + (recoveryFailed ? " Storage recovery failed; retain your backup." : "")));
      }
    };
    reader.readAsText(file);
  });
}
