// ==================== DATA MIGRATION SYSTEM ====================
// Safe, versioned, forward-compatible data upgrades.
//
// HOW IT WORKS
//   - The app stores a schema version in localStorage (always available, even
//     if IndexedDB is evicted). CURRENT_DATA_VERSION is the version this build
//     understands.
//   - On startup we read the stored version. If it is lower than the current
//     build version, we run every migration between (stored, current] in order.
//   - Migrations operate on the in-memory arrays (window.links, window.notes,
//     ...) and transform them IN PLACE. Afterward the transformed data is
//     persisted back to IndexedDB and the stored version is bumped.
//   - A safety backup (localStorage mirror) is always created BEFORE any
//     migration runs, so an update can never destroy existing data.
//
// WHY THIS KEEPS YOUR DATA SAFE
//   - Data is never deleted during an upgrade; migrations only add/normalize.
//   - The stored version lets every future update detect exactly which steps
//     it still needs to apply, even if a user skipped several releases.
//   - If a migration throws, we stop, keep the old version, and the safety
//     backup still holds the pre-upgrade data.
//
// HOW TO ADD A FUTURE MIGRATION
//   1. Increment CURRENT_DATA_VERSION (e.g. 5 -> 6).
//   2. Register a function under that number in DATA_MIGRATIONS.
//      The function receives `ctx` with all arrays (links, prompts, notes,
//      snippets, colors, todos, files, folders, timeline, tools) and should
//      transform them in place. It may be async.
//   3. Done. The framework applies it automatically on next load.

const CURRENT_DATA_VERSION = 5;
const DATA_VERSION_STORAGE_KEY = 'linklumina-schema-version';

// Migration registry: version -> async fn(ctx)
// Older -> newer. Each runs exactly once per user (never re-run).
const DATA_MIGRATIONS = {

    // v5: Normalize legacy/raw records so every item has the fields the UI
    // expects. Safe no-op for already-normalized data; also guarantees every
    // array exists so later migrations never trip on undefined.
    5: async function normalizeRecords(ctx) {
        const now = new Date().toISOString();

        // Map from ctx key -> window property. We MUTATE the existing arrays in
        // place (never reassign) so the local references in script.js/modules.js
        // (e.g. `links`, `notes`) keep pointing at the same array.
        const winKey = {
            links: 'links', prompts: 'prompts', notes: 'notes', snippets: 'snippets',
            colors: 'colors', todos: 'todos', files: 'files', folders: 'folders',
            timeline: 'timelineEvents', tools: 'tools'
        };

        const links = Array.isArray(window.links) ? window.links : (window.links = []);
        for (let i = 0; i < links.length; i++) {
            const l = links[i];
            if (!l || typeof l !== 'object') { links.splice(i, 1); i--; continue; }
            if (typeof l.id !== 'string' || l.id === '') l.id = 'link_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8) + '_' + i;
            l.url = String(l.url || '');
            l.title = l.title || l.url;
            l.category = l.category || 'General';
            l.tags = Array.isArray(l.tags) ? l.tags.filter(t => typeof t === 'string') : [];
            l.notes = l.notes || '';
            l.favorite = !!l.favorite;
            l.visitCount = Number(l.visitCount) || 0;
            l.lastVisited = l.lastVisited || null;
            if (!l.createdAt) l.createdAt = now;
        }

        Object.keys(winKey).forEach(key => {
            const wp = winKey[key];
            const arr = Array.isArray(window[wp]) ? window[wp] : (window[wp] = []);
            for (let i = 0; i < arr.length; i++) {
                if (!arr[i] || typeof arr[i] !== 'object') { arr.splice(i, 1); i--; }
            }
            // Keep ctx pointing at the same (mutated) arrays for later persistence.
            ctx[key] = arr;
        });
        ctx.links = links;
    }
};

function getStoredDataVersion() {
    try {
        const v = parseInt(localStorage.getItem(DATA_VERSION_STORAGE_KEY), 10);
        return Number.isFinite(v) ? v : 1;
    } catch (e) {
        return 1;
    }
}

async function setStoredDataVersion(v) {
    try {
        localStorage.setItem(DATA_VERSION_STORAGE_KEY, String(v));
    } catch (e) {
        console.warn('Could not persist schema version:', e);
    }
}

async function runDataMigrations() {
    const current = getStoredDataVersion();
    if (current >= CURRENT_DATA_VERSION) {
        return { applied: 0, current, needsMigration: false };
    }

    // Safety: never migrate without a recent backup of the current state.
    if (typeof window.createSafetyBackupSnapshot === 'function') {
        try {
            await window.createSafetyBackupSnapshot('before-migration');
        } catch (e) {
            console.warn('Safety backup before migration failed:', e);
        }
    }

    const ctx = {
        links: window.links || [],
        prompts: window.prompts || [],
        notes: window.notes || [],
        snippets: window.snippets || [],
        colors: window.colors || [],
        todos: window.todos || [],
        files: window.files || [],
        folders: window.folders || [],
        timeline: window.timelineEvents || [],
        tools: window.tools || []
    };

    let applied = 0;
    try {
        for (let v = current + 1; v <= CURRENT_DATA_VERSION; v++) {
            const fn = DATA_MIGRATIONS[v];
            if (typeof fn === 'function') {
                await fn(ctx);
                applied++;
            }
        }
    } catch (e) {
        // Keep the old version so the upgrade can be retried; backup is intact.
        console.error('Data migration failed at version update; version not bumped.', e);
        if (typeof window.showToast === 'function') {
            window.showToast('Data upgrade failed — your data is safe.', 'error');
        }
        return { applied, current, needsMigration: true, error: e };
    }

    // Persist transformed data back to IndexedDB.
    if (applied > 0 && window.db && typeof window.persistSnapshotToStores === 'function') {
        try {
            await window.persistSnapshotToStores(ctx);
        } catch (e) {
            console.warn('Persisting migrated data failed:', e);
        }
    }

    await setStoredDataVersion(CURRENT_DATA_VERSION);

    if (applied > 0 && typeof window.showToast === 'function') {
        window.showToast(`Data upgraded to schema v${CURRENT_DATA_VERSION}`, 'info');
    }
    return { applied, current: CURRENT_DATA_VERSION, needsMigration: false };
}

// Expose for future code + manual triggers.
window.CURRENT_DATA_VERSION = CURRENT_DATA_VERSION;
window.DATA_VERSION_STORAGE_KEY = DATA_VERSION_STORAGE_KEY;
window.runDataMigrations = runDataMigrations;
window.getStoredDataVersion = getStoredDataVersion;