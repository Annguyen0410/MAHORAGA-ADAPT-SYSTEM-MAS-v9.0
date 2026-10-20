// Lazy-load heavy libs (keep initial payload small)
function loadScript(url) {
    if (window.__loadedScripts && window.__loadedScripts[url]) return window.__loadedScripts[url];
    var p = new Promise(function (resolve, reject) {
        var s = document.createElement('script');
        s.src = url;
        s.onload = function () { (window.__loadedScripts = window.__loadedScripts || {})[url] = Promise.resolve(); resolve(); };
        s.onerror = reject;
        document.head.appendChild(s);
    });
    (window.__loadedScripts = window.__loadedScripts || {})[url] = p;
    return p;
}

// State Management
// Global variables
var db = window.db = null;
let links = window.links = [];
let prompts = window.prompts = [];
let searchTerm = '';
// Terms used to highlight matches in card titles/tags while a search is active.
let _activeHighlightTerms = [];
let selectedCategory = 'all';
let sortBy = localStorage.getItem('linkLumina_sortBy') || 'newest';
let showFavoritesOnly = false;
let selectedTags = new Set(); // Multi-tag state
let editingLinkId = null;
let editingPromptId = null;
let selectedLinks = new Set();
let allTags = new Set();

let currentView = localStorage.getItem('linkLumina_view') || 'grid'; // 'grid', 'list', 'timeline', 'gallery'
let collections = [];
let linkHealthCache = new Map();

// Tag Folder & Batch Mode State
let isSelectionMode = false;
let batchSelectedLinks = new Set();

// Performance Optimization State
let renderedCount = 0;
const BATCH_SIZE = 50;
let currentFilteredLinks = [];
let infiniteScrollObserver = null;

// Lazy-loading for card thumbnail background images (grid/list use inline
// `background-image`, which `loading="lazy"` can't help — so we defer via a
// single shared IntersectionObserver and swap the URL in just before visible).
let lazyImageObserver = null;
function getLazyImageObserver() {
    if (!lazyImageObserver && typeof IntersectionObserver !== 'undefined') {
        lazyImageObserver = new IntersectionObserver((entries) => {
            entries.forEach(entry => {
                if (!entry.isIntersecting) return;
                const el = entry.target;
                const url = el.getAttribute('data-bg');
                if (url) {
                    el.style.backgroundImage = `url('${url}')`;
                    el.classList.add('bg-loaded');
                }
                el.removeAttribute('data-bg');
                lazyImageObserver.unobserve(el);
            });
        }, { rootMargin: '400px 0px' });
    }
    return lazyImageObserver;
}

// Observe a list of [data-bg] thumbnails. Falls back to immediate load if
// IntersectionObserver is unavailable.
function observeLazyTargets(targets) {
    if (!targets || targets.length === 0) return;
    const observer = getLazyImageObserver();
    if (!observer) {
        targets.forEach(el => {
            const url = el.getAttribute('data-bg');
            if (url) el.style.backgroundImage = `url('${url}')`;
            el.removeAttribute('data-bg');
        });
        return;
    }
    targets.forEach(el => observer.observe(el));
}

// Observe every [data-bg] thumbnail inside a container element.
function observeLazyImages(rootEl) {
    if (!rootEl) return;
    observeLazyTargets(rootEl.querySelectorAll('[data-bg]'));
}
window.observeLazyImages = observeLazyImages;
window.observeLazyTargets = observeLazyTargets;

const RECOVERY_SNAPSHOT_KEY = 'linklumina-recovery-snapshot-v1';
const RECOVERY_SNAPSHOT_MAX_LOCALSTORAGE_BYTES = 4 * 1024 * 1024;
let recoverySnapshotTimer = null;
let recoverySnapshotInFlight = false;

function buildRecoverySnapshotPayload() {
    return {
        version: 1,
        savedAt: new Date().toISOString(),
        links: Array.isArray(window.links) ? window.links : [],
        prompts: Array.isArray(window.prompts) ? window.prompts : [],
        notes: Array.isArray(window.notes) ? window.notes : [],
        snippets: Array.isArray(window.snippets) ? window.snippets : [],
        colors: Array.isArray(window.colors) ? window.colors : [],
        todos: Array.isArray(window.todos) ? window.todos : [],
        files: Array.isArray(window.files) ? window.files : [],
        folders: Array.isArray(window.folders) ? window.folders : [],
        timeline: Array.isArray(window.timelineEvents) ? window.timelineEvents : [],
        tools: Array.isArray(window.tools) ? window.tools : []
    };
}

function readRecoverySnapshot() {
    try {
        const raw = localStorage.getItem(RECOVERY_SNAPSHOT_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (e) {
        console.warn('Failed to read recovery snapshot:', e);
        return null;
    }
}

function hasRecoveryData(snapshot) {
    if (!snapshot || typeof snapshot !== 'object') return false;
    const keys = ['links', 'prompts', 'notes', 'snippets', 'colors', 'todos', 'files', 'folders', 'timeline', 'tools'];
    return keys.some(key => Array.isArray(snapshot[key]) && snapshot[key].length > 0);
}

function writeRecoverySnapshot(payload) {
    try {
        const json = JSON.stringify(payload);
        if (json.length > RECOVERY_SNAPSHOT_MAX_LOCALSTORAGE_BYTES) {
            console.warn('Recovery snapshot skipped because it exceeds localStorage budget.');
            return false;
        }
        localStorage.setItem(RECOVERY_SNAPSHOT_KEY, json);
        localStorage.setItem('linklumina-recovery-snapshot-updated-at', payload.savedAt || new Date().toISOString());
        return true;
    } catch (e) {
        console.warn('Failed to write recovery snapshot:', e);
        return false;
    }
}

async function createSafetyBackupSnapshot(reason) {
    try {
        await flushRecoverySnapshot(reason || 'safety-backup');
        return true;
    } catch (e) {
        console.warn('Failed to create safety snapshot:', e);
        return false;
    }
}

function ensureArray(value) {
    return Array.isArray(value) ? value : [];
}

function normalizeUrlForMerge(url) {
    return String(url || '').trim().replace(/\/+$/, '').toLowerCase();
}

function appendUniqueById(target, items) {
    if (!Array.isArray(target) || !Array.isArray(items)) return 0;
    const existingIds = new Set(target.map(item => item && item.id).filter(Boolean));
    let added = 0;
    for (const item of items) {
        if (!item || typeof item !== 'object' || !item.id || existingIds.has(item.id)) continue;
        existingIds.add(item.id);
        target.push(item);
        added++;
    }
    return added;
}

async function requestPersistentStorage() {
    try {
        if (!navigator.storage || typeof navigator.storage.persist !== 'function') return false;
        const alreadyPersisted = typeof navigator.storage.persisted === 'function'
            ? await navigator.storage.persisted()
            : false;
        if (alreadyPersisted) return true;
        const granted = await navigator.storage.persist();
        if (!granted) {
            console.warn('Persistent storage was not granted by the browser.');
        }
        return granted;
    } catch (e) {
        console.warn('Persistent storage request failed:', e);
        return false;
    }
}

async function persistSnapshotToStores(snapshot) {
    if (!snapshot || !db) return;

    const storeMappings = [
        ['links', snapshot.links],
        ['prompts', snapshot.prompts],
        ['notes', snapshot.notes],
        ['snippets', snapshot.snippets],
        ['colors', snapshot.colors],
        ['todos', snapshot.todos],
        ['files', snapshot.files],
        ['folders', snapshot.folders],
        ['timeline', snapshot.timeline],
        ['tools', snapshot.tools]
    ];

    for (const [storeName, items] of storeMappings) {
        if (!Array.isArray(items) || items.length === 0) continue;
        if (!db.objectStoreNames.contains(storeName)) continue;

        await new Promise((resolve, reject) => {
            const tx = db.transaction([storeName], 'readwrite');
            const store = tx.objectStore(storeName);
            items.forEach(item => {
                if (item && typeof item === 'object' && item.id != null) {
                    store.put(item);
                }
            });
            tx.oncomplete = () => resolve();
            tx.onerror = () => reject(tx.error);
            tx.onabort = () => reject(tx.error);
        });
    }
}

async function restoreDataFromRecoverySnapshotIfNeeded() {
    let snapshot = readRecoverySnapshot();
    if (!hasRecoveryData(snapshot) || !db) return false;

    // If IndexedDB already has data, nothing to restore.
    if (hasIndexedDbData()) return false;

    await persistSnapshotToStores(snapshot);
    await reloadAllStores();

    showToast('Recovered your saved data from local recovery snapshot.', 'success');
    return true;
}

async function restoreDataFromLocalMirrorIfNeeded() {
    if (!db) return false;
    // Only restore when IndexedDB is empty (covers IndexedDB eviction).
    if (hasIndexedDbData()) return false;

    const mirror = readLocalMirror();
    if (!hasMirrorData(mirror)) return false;

    await persistSnapshotToStores(mirror);
    await reloadAllStores();

    showToast('Recovered your saved data from the localStorage backup.', 'success');
    return true;
}

function hasIndexedDbData() {
    return (
        (Array.isArray(window.links) && window.links.length > 0) ||
        (Array.isArray(window.prompts) && window.prompts.length > 0) ||
        (Array.isArray(window.notes) && window.notes.length > 0) ||
        (Array.isArray(window.snippets) && window.snippets.length > 0) ||
        (Array.isArray(window.colors) && window.colors.length > 0) ||
        (Array.isArray(window.todos) && window.todos.length > 0) ||
        (Array.isArray(window.files) && window.files.length > 0) ||
        (Array.isArray(window.folders) && window.folders.length > 0) ||
        (Array.isArray(window.timelineEvents) && window.timelineEvents.length > 0) ||
        (Array.isArray(window.tools) && window.tools.length > 0)
    );
}

async function reloadAllStores() {
    await loadLinks();
    await loadPrompts();
    if (typeof window.loadNewModuleData === 'function') await window.loadNewModuleData();
    if (typeof window.initFolders === 'function') await window.initFolders();
    if (typeof window.loadTimelineEvents === 'function') await window.loadTimelineEvents();
}

async function flushRecoverySnapshot(reason) {
    if (recoverySnapshotInFlight) return false;
    recoverySnapshotInFlight = true;
    try {
        const payload = buildRecoverySnapshotPayload();
        payload.reason = reason || 'manual';
        const ok = writeRecoverySnapshot(payload);
        writeLocalMirror(); // Durable chunked mirror in localStorage (survives IndexedDB eviction)
        if (typeof scheduleImmediateBackupDownload === 'function') scheduleImmediateBackupDownload();
        return ok;
    } finally {
        recoverySnapshotInFlight = false;
    }
}

function scheduleRecoverySnapshot(reason) {
    if (recoverySnapshotTimer) clearTimeout(recoverySnapshotTimer);
    recoverySnapshotTimer = setTimeout(() => {
        flushRecoverySnapshot(reason);
    }, 1200);
}

function setupRecoverySnapshotLifecycle() {
    window.addEventListener('pagehide', () => {
        flushRecoverySnapshot('pagehide');
    });

    document.addEventListener('visibilitychange', () => {
        if (document.visibilityState === 'hidden') {
            flushRecoverySnapshot('hidden');
        }
    });

    window.addEventListener('beforeunload', () => {
        flushRecoverySnapshot('beforeunload');
    });
}

// ==================== Durable localStorage Mirror ====================
// localStorage is written on every change (debounced) AND on page leave.
// It is split into chunks so it can survive IndexedDB eviction and be used
// as a restore fallback when IndexedDB comes back empty.

const LOCAL_MIRROR_META_KEY = 'linklumina-mirror-meta-v1';
const LOCAL_MIRROR_PART_PREFIX = 'linklumina-mirror-part-';
const LOCAL_MIRROR_PART_MAX = 1.5 * 1024 * 1024; // ~1.5MB per key, keeps under the per-key quota

function clearLocalMirror() {
    try {
        const raw = localStorage.getItem(LOCAL_MIRROR_META_KEY);
        const meta = raw ? JSON.parse(raw) : null;
        const count = (meta && typeof meta.count === 'number') ? meta.count : 0;
        for (let i = 0; i <= count; i++) {
            localStorage.removeItem(LOCAL_MIRROR_PART_PREFIX + i);
        }
        localStorage.removeItem(LOCAL_MIRROR_META_KEY);
    } catch (e) {
        console.warn('Failed to clear localStorage mirror:', e);
    }
}

function writeLocalMirror() {
    try {
        const payload = buildRecoverySnapshotPayload();
        payload.savedAt = new Date().toISOString();
        const json = JSON.stringify(payload);
        clearLocalMirror();
        const partCount = Math.max(1, Math.ceil(json.length / LOCAL_MIRROR_PART_MAX));
        for (let i = 0; i < partCount; i++) {
            localStorage.setItem(LOCAL_MIRROR_PART_PREFIX + i, json.slice(i * LOCAL_MIRROR_PART_MAX, (i + 1) * LOCAL_MIRROR_PART_MAX));
        }
        localStorage.setItem(LOCAL_MIRROR_META_KEY, JSON.stringify({ version: 1, count: partCount - 1, savedAt: payload.savedAt }));
        return true;
    } catch (e) {
        console.warn('Failed to write localStorage mirror (data may exceed localStorage quota):', e);
        return false;
    }
}

function readLocalMirror() {
    try {
        const metaRaw = localStorage.getItem(LOCAL_MIRROR_META_KEY);
        if (!metaRaw) return null;
        const meta = JSON.parse(metaRaw);
        if (!meta || typeof meta.count !== 'number' || meta.count < 0) return null;
        let json = '';
        for (let i = 0; i <= meta.count; i++) {
            const part = localStorage.getItem(LOCAL_MIRROR_PART_PREFIX + i);
            if (part == null) return null; // incomplete -> treat as corrupt
            json += part;
        }
        const parsed = JSON.parse(json);
        return parsed && typeof parsed === 'object' ? parsed : null;
    } catch (e) {
        console.warn('Failed to read localStorage mirror:', e);
        return null;
    }
}

function hasMirrorData(snapshot) {
    if (!snapshot || typeof snapshot !== 'object') return false;
    const keys = ['links', 'prompts', 'notes', 'snippets', 'colors', 'todos', 'files', 'folders', 'timeline', 'tools'];
    return keys.some(key => Array.isArray(snapshot[key]) && snapshot[key].length > 0);
}

// ==================== Auto Backup Download (for saving on D drive) ====================
// Backs up immediately (debounced) whenever data changes, so edits are captured right away.

const AUTO_BACKUP_SIG_KEY = 'linklumina-auto-backup-sig';
let backupDownloadTimer = null;

function updateLastBackupDate() {
    const el = document.getElementById('lastBackupDate');
    if (!el) return;
    try {
        const last = localStorage.getItem('linklumina-last-backup-time');
        if (last) {
            el.textContent = new Date(Number(last)).toLocaleString();
        } else {
            el.textContent = 'Never';
        }
    } catch (e) {
        el.textContent = 'Never';
    }
}

function downloadFullBackup() {
    const payload = buildRecoverySnapshotPayload();
    const backup = {
        ...payload,
        version: '4.1',
        exportDate: new Date().toISOString()
    };
    const blob = new Blob([JSON.stringify(backup, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `linklumina-backup-${new Date().toISOString().split('T')[0]}-${Date.now()}.json`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    try {
        localStorage.setItem('linklumina-last-backup-time', String(Date.now()));
    } catch (e) { /* ignore */ }
    updateLastBackupDate();
}

function dataSignature() {
    const p = buildRecoverySnapshotPayload();
    const keys = ['links', 'prompts', 'notes', 'snippets', 'colors', 'todos', 'files', 'folders', 'timeline', 'tools'];
    return keys.map(k => `${k}:${(p[k] || []).length}`).join('|');
}

// Debounce so a burst of edits triggers a single backup once the user pauses.
function scheduleImmediateBackupDownload() {
    if (backupDownloadTimer) clearTimeout(backupDownloadTimer);
    backupDownloadTimer = setTimeout(() => {
        try {
            const sig = dataSignature();
            const hasData = sig !== 'links:0|prompts:0|notes:0|snippets:0|colors:0|todos:0|files:0|folders:0|timeline:0|tools:0';
            if (!hasData) return;
            const lastSig = localStorage.getItem(AUTO_BACKUP_SIG_KEY) || '';
            if (sig === lastSig) return; // nothing new since last backup
            localStorage.setItem(AUTO_BACKUP_SIG_KEY, sig);
            downloadFullBackup();
            showToast('💾 Auto-backup downloaded — move it to your D drive', 'info');
        } catch (e) {
            console.warn('Auto backup failed:', e);
        }
    }, 4000);
}


// Supabase config moved to sync.js / index.html

// Unified categories for links (single source of truth – used in form, filters, auto-detect)
const LINK_CATEGORIES = [
    'General', 'Social', 'Entertainment', 'Video', 'Development', 'Design', 'Tools', 'AI Tools',
    'Shopping', 'News', 'Article', 'Reference', 'Learning', 'Finance', 'Productivity',
    'Inspiration', 'Resources', 'Personal', 'Other'
];

function populateLinkCategoryOptions(optionalCurrentValue) {
    const sel = document.getElementById('linkCategory');
    if (!sel) return;
    const current = optionalCurrentValue != null ? optionalCurrentValue : sel.value;
    const allowed = new Set(LINK_CATEGORIES);
    if (current && !allowed.has(current)) allowed.add(current);
    const ordered = [...LINK_CATEGORIES];
    if (current && !LINK_CATEGORIES.includes(current)) ordered.push(current);
    sel.innerHTML = ordered.map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    if (ordered.includes(current)) sel.value = current;
    else sel.value = 'General';
}

// Accent palette — red + gold
const neonColors = [
    '#dc2626', // gold
    '#b91c1c', // crimson
    '#f59e0b', // amber
    '#eab308', // yellow
    '#dc2626', // red-600
    '#dc2626', // yellow-600
    '#fbbf24', // red-400
    '#991b1b', // red-800
];

// Category → accent color (one distinct hue per category for instant visual scanning)
const CATEGORY_COLORS = {
    'General': '#64748b',
    'Social': '#ec4899',
    'Entertainment': '#8b5cf6',
    'Video': '#ef4444',
    'Development': '#3b82f6',
    'Design': '#f59e0b',
    'Tools': '#06b6d4',
    'AI Tools': '#a855f7',
    'Shopping': '#f97316',
    'News': '#dc2626',
    'Article': '#10b981',
    'Reference': '#14b8a6',
    'Learning': '#22c55e',
    'Finance': '#84cc16',
    'Productivity': '#0ea5e9',
    'Inspiration': '#eab308',
    'Resources': '#6366f1',
    'Personal': '#f43f5e',
    'Other': '#78716c'
};

function getCategoryColor(category) {
    return (category && CATEGORY_COLORS[category]) || null;
}

// Theme Manager
const ThemeManager = {
    currentTheme: localStorage.getItem('linkLumina_theme') || 'dark',

    init() {
        this.applyTheme(this.currentTheme);
        // When theme is "system", react to OS dark/light changes
        try {
            const mq = window.matchMedia('(prefers-color-scheme: dark)');
            if (mq.addEventListener) {
                mq.addEventListener('change', () => {
                    if (this.currentTheme === 'system') this.applyTheme('system');
                });
            }
        } catch (e) { /* ignore */ }
    },

    toggle() {
        const themes = ['dark', 'light', 'chill', 'system'];
        const currentIndex = themes.indexOf(this.currentTheme);
        const nextTheme = themes[(currentIndex + 1) % themes.length];
        this.setTheme(nextTheme);
    },

    setTheme(theme) {
        this.currentTheme = theme;
        localStorage.setItem('linkLumina_theme', theme);
        this.applyTheme(theme);
        const labels = { 'dark': 'Dark Mode', 'light': 'Light Mode', 'chill': 'Chill Mode', 'system': 'System' };
        showToast(`${labels[theme] || theme} Activated`, 'info');
    },

    resolveTheme(theme) {
        if (theme !== 'system') return theme;
        try {
            return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
        } catch (e) { return 'dark'; }
    },

    applyTheme(theme) {
        const resolved = this.resolveTheme(theme);
        document.documentElement.setAttribute('data-theme', resolved);
        if (typeof LivingBackground !== 'undefined' && LivingBackground.setTheme) {
            LivingBackground.setTheme(resolved);
        }
        this.updateToggleIcon();
    },

    updateToggleIcon() {
        const btn = document.getElementById('themeToggleBtn');
        if (!btn) return;

        const icons = {
            'dark': 'moon',
            'light': 'sun',
            'chill': 'coffee',
            'system': 'monitor'
        };

        // Remove old icon
        btn.innerHTML = '';

        const iconName = icons[this.currentTheme] || 'moon';
        const i = document.createElement('i');
        i.setAttribute('data-lucide', iconName);
        i.className = 'w-4 h-4 md:w-5 md:h-5';
        btn.appendChild(i);

        // Re-init icon
        if (window.lucide) lucide.createIcons();
    }
};

// Compact / Dense Mode — a minimal, information-dense layout for large libraries
const CompactMode = {
    enabled: localStorage.getItem('linkLumina_compact') === '1',

    init() {
        this.apply(this.enabled);
    },

    toggle() {
        this.set(!this.enabled);
    },

    set(on) {
        this.enabled = on;
        localStorage.setItem('linkLumina_compact', on ? '1' : '0');
        this.apply(on);
        showToast(on ? 'Compact Mode — dense layout' : 'Comfortable layout', 'info');
    },

    apply(on) {
        document.body.classList.toggle('compact-mode', on);
        // Header icon button (legacy; optional)
        const btn = document.getElementById('compactModeBtn');
        if (btn) {
            btn.classList.toggle('active', on);
            btn.title = on ? 'Exit Compact Mode' : 'Compact Mode';
            btn.innerHTML = '';
            const i = document.createElement('i');
            i.setAttribute('data-lucide', on ? 'rows-3' : 'layout-grid');
            i.className = 'w-4 h-4 md:w-5 md:h-5';
            btn.appendChild(i);
        }
        // More-menu item keeps its label + shows a check when active
        const menuBtn = document.getElementById('compactModeMenuBtn');
        if (menuBtn) {
            menuBtn.innerHTML =
                `<i data-lucide="${on ? 'rows-3' : 'layout-grid'}" class="w-4 h-4 text-red-400"></i>` +
                `<span class="flex-1">Dense View</span>` +
                `<i data-lucide="check" class="w-3.5 h-3.5 ${on ? 'text-red-400' : 'opacity-0'}"></i>`;
        }
        if (window.lucide) lucide.createIcons();
    }
};

// Initialize app
document.addEventListener('DOMContentLoaded', async () => {
    initializeIcons();
    initializeBackground();
    await initIndexedDB();
    await requestPersistentStorage();
    await migrateFromLocalStorage();
    await loadLinks();
    await loadPrompts();

    // Initialize sub-modules
    // Note: initIndexedDB is called above, this check might be for a different module or future use.
    if (window.initIndexedDB) await window.initIndexedDB();
    if (window.initFolders) await window.initFolders(); // Original had await, keep it.
    if (window.loadTimelineEvents) await window.loadTimelineEvents();
    if (window.LayoutManager) window.LayoutManager.init(); // Initialize Layout
    await restoreDataFromRecoverySnapshotIfNeeded();
    await restoreDataFromLocalMirrorIfNeeded();

    ThemeManager.init(); // Initialize Theme
    CompactMode.init(); // Initialize compact/dense layout
    populateLinkCategoryOptions();
    updateAllTags();
    setupEventListeners();
    setupFolderListeners();
    setupTimelineListeners();
    setupNewFeatureListeners();
    setupExtendedKeyboardShortcuts();
    setupCommandPalette(); // Wire Ctrl+K palette search + keyboard nav (was never called — bug fix)
    if (window.LawEngine) window.LawEngine.init(); // Initialize Cognitive Laws
    registerAllFeatures(); // Register every feature into AppFeatures hub
    if (window.AppFeatures && Array.isArray(commands)) {
        // Features appear in Ctrl+K palette — skip ones that duplicate a builtin command
        const existingIds = new Set(commands.map(c => c.id));
        for (const c of window.AppFeatures.toCommands()) {
            const baseId = c.id.replace(/^feature-/, '');
            if (!existingIds.has(baseId) && !existingIds.has(c.id)) commands.push(c);
        }
    }
    setupActivityFeed();
    handleBookmarkletDeepLink();
    renderLinks();
    renderCategoryFilters();
    renderPrompts();
    if (typeof updateMobileFabVisibility === 'function') updateMobileFabVisibility();

    window.addEventListener('resize', () => { if (typeof updateMobileFabVisibility === 'function') updateMobileFabVisibility(); });

    // Retry persistent-storage request on first real user gesture.
    // Persistent storage makes the origin exempt from automatic eviction (~1 week), which is the
    // main reason data "disappears" on hosted deployments.
    const retryPersistentOnce = async () => {
        try {
            if (navigator.storage && typeof navigator.storage.persisted === 'function') {
                const persisted = await navigator.storage.persisted();
                if (!persisted && navigator.storage.persist) {
                    await navigator.storage.persist();
                }
            }
        } catch (e) {
            console.warn('Persistent storage retry failed:', e);
        }
    };
    ['pointerdown', 'touchstart', 'keydown'].forEach(type => {
        window.addEventListener(type, () => { retryPersistentOnce(); }, { once: true, passive: true });
    });

    const params = new URLSearchParams(window.location.search);
    const quickSaveUrl = params.get('quickSave') || params.get('url');
    if (quickSaveUrl) {
        try {
            const decoded = decodeURIComponent(quickSaveUrl);
            if (decoded.startsWith('http')) {
                openQuickSave(decoded);
                history.replaceState({}, document.title, window.location.pathname || '/');
            }
        } catch (e) { /* ignore */ }
    }

    // Auto-Close Batch Import from Extension
    const batchDataRaw = params.get('importBatchData');
    if (batchDataRaw) {
        try {
            const decodedJson = decodeURIComponent(atob(batchDataRaw));
            const batchLinks = JSON.parse(decodedJson);

            if (Array.isArray(batchLinks) && batchLinks.length > 0) {
                // Determine or create 'Auto-Closed Archive' folder
                let archiveFolder = window.folders ? window.folders.find(f => f.name === 'Auto-Closed Archive') : null;
                if (!archiveFolder && window.folders) {
                    archiveFolder = {
                        id: 'folder_' + Date.now().toString() + '_' + Math.random().toString(36).slice(2, 8),
                        name: 'Auto-Closed Archive',
                        icon: 'archive',
                        color: '#dc2626',
                        parentId: null
                    };
                    window.folders.push(archiveFolder);
                    if (typeof window.saveFoldersToDB === 'function') await window.saveFoldersToDB(archiveFolder);
                }

                const newLinks = [];
                const existingUrls = new Set((window.links || []).map(link => normalizeUrlForMerge(link.url)).filter(Boolean));
                let skippedDuplicates = 0;
                for (let i = 0; i < batchLinks.length; i++) {
                    const l = batchLinks[i];
                    if (!l.url) continue;
                    const normalizedUrl = normalizeUrlForMerge(l.url);
                    if (normalizedUrl && existingUrls.has(normalizedUrl)) {
                        skippedDuplicates++;
                        continue;
                    }
                    if (normalizedUrl) existingUrls.add(normalizedUrl);
                    const newLink = {
                        id: Date.now().toString() + '_' + Math.random().toString(36).slice(2, 8) + i,
                        url: l.url,
                        title: l.title || l.url,
                        category: '',
                        tags: ['auto-closed'],
                        folderId: archiveFolder ? archiveFolder.id : null,
                        visitCount: 0,
                        lastVisited: new Date().toISOString(),
                        addedAt: new Date().toISOString()
                    };
                    newLinks.push(newLink);
                    if (window.links) window.links.unshift(newLink);
                }

                if (newLinks.length > 0) {
                    if (typeof saveLinkToDB === 'function') {
                        // Concurrently save only new links to prevent freezing on large datasets
                        await Promise.all(newLinks.map(l => saveLinkToDB(l)));
                    } else if (typeof saveLinks === 'function') {
                        await saveLinks();
                    }
                    if (typeof window.updateAllTags === 'function') window.updateAllTags();
                    if (window.EventBus && window.EVENTS) window.EventBus.emit(window.EVENTS.LINK_ADDED, { count: newLinks.length });
                    if (typeof showToast === 'function') {
                        const duplicateNote = skippedDuplicates > 0 ? ` (${skippedDuplicates} duplicates skipped)` : '';
                        showToast(`Imported ${newLinks.length} inactive tabs from Extension!${duplicateNote}`, 'success');
                    }
                    if (typeof renderLinks === 'function') renderLinks();
                    if (typeof window.renderSidebar === 'function') window.renderSidebar();
                } else if (skippedDuplicates > 0 && typeof showToast === 'function') {
                    showToast(`No new inactive tabs imported. ${skippedDuplicates} duplicates skipped.`, 'info');
                }

                history.replaceState({}, document.title, window.location.pathname || '/');
            }
        } catch (e) {
            console.error('Failed to process batch tab import from extension:', e);
            if (typeof showToast === 'function') showToast('Failed to import tabs', 'error');
        }
    }

    // Extension API: for browser extension or external callers
    window.LinkLumina = window.LinkLumina || {};
    window.LinkLumina.quickSaveFromUrl = function (url) {
        if (typeof url === 'string' && url.startsWith('http')) openQuickSave(url);
    };
    window.LinkLumina.openQuickSave = openQuickSave;
    window.LinkLumina.addLink = async function (payload) {
        if (payload && payload.url) {
            const link = {
                id: payload.id || Date.now().toString() + '_' + Math.random().toString(36).slice(2, 8),
                url: payload.url,
                title: payload.title || '',
                category: payload.category || 'General',
                tags: payload.tags || [],
                notes: payload.notes || '',
                image: payload.image || null,
                accentColor: payload.accentColor || neonColors[0],
                favorite: !!payload.favorite,
                visitCount: payload.visitCount || 0,
                createdAt: payload.createdAt || new Date().toISOString(),
                lastVisited: payload.lastVisited || null
            };
            links.push(link);
            await saveLinkToDB(link);
            updateAllTags();
            renderLinks();
            renderCategoryFilters();
            return link.id;
        }
    };

    setupRecoverySnapshotLifecycle();
    window.scheduleRecoverySnapshot = scheduleRecoverySnapshot;
    scheduleRecoverySnapshot('app-init');
});

// Initialize IndexedDB
function initIndexedDB() {
    return new Promise((resolve, reject) => {
        const request = indexedDB.open('LinkLuminaDB', 5); // v5: Added tools store (Product Hunt style)

        request.onerror = () => reject(request.error);
        request.onsuccess = () => {
            db = request.result;
            resolve();
        };

        request.onupgradeneeded = (event) => {
            const database = event.target.result;
            const transaction = event.target.transaction;

            // Links store
            if (!database.objectStoreNames.contains('links')) {
                const linksStore = database.createObjectStore('links', { keyPath: 'id' });
                linksStore.createIndex('url', 'url', { unique: false });
                linksStore.createIndex('category', 'category', { unique: false });
                linksStore.createIndex('createdAt', 'createdAt', { unique: false });
            }

            // Upgrade: Add folderId index to existing links store
            if (database.objectStoreNames.contains('links')) {
                const linksStore = transaction.objectStore('links');
                if (!linksStore.indexNames.contains('folderId')) {
                    linksStore.createIndex('folderId', 'folderId', { unique: false });
                }
            }

            // Prompts store
            if (!database.objectStoreNames.contains('prompts')) {
                const promptsStore = database.createObjectStore('prompts', { keyPath: 'id' });
                promptsStore.createIndex('createdAt', 'createdAt', { unique: false });
                promptsStore.createIndex('category', 'category', { unique: false });
            }

            // Storage metadata store
            if (!database.objectStoreNames.contains('metadata')) {
                database.createObjectStore('metadata', { keyPath: 'key' });
            }

            // Notes store
            if (!database.objectStoreNames.contains('notes')) {
                const notesStore = database.createObjectStore('notes', { keyPath: 'id' });
                notesStore.createIndex('createdAt', 'createdAt', { unique: false });
            }

            // Snippets store
            if (!database.objectStoreNames.contains('snippets')) {
                const snippetsStore = database.createObjectStore('snippets', { keyPath: 'id' });
                snippetsStore.createIndex('language', 'language', { unique: false });
            }

            // Colors store
            if (!database.objectStoreNames.contains('colors')) {
                const colorsStore = database.createObjectStore('colors', { keyPath: 'id' });
            }

            // Folders store (New in v3)
            if (!database.objectStoreNames.contains('folders')) {
                const foldersStore = database.createObjectStore('folders', { keyPath: 'id' });
                foldersStore.createIndex('createdAt', 'createdAt', { unique: false });
            }

            // Todos store
            if (!database.objectStoreNames.contains('todos')) {
                const todosStore = database.createObjectStore('todos', { keyPath: 'id' });
                todosStore.createIndex('completed', 'completed', { unique: false });
            }

            // Files store
            if (!database.objectStoreNames.contains('files')) {
                database.createObjectStore('files', { keyPath: 'id' });
            }

            // Timeline store (New in v4) - Cognitive Timeline
            if (!database.objectStoreNames.contains('timeline')) {
                const timelineStore = database.createObjectStore('timeline', { keyPath: 'id' });
                timelineStore.createIndex('timestamp', 'timestamp', { unique: false });
                timelineStore.createIndex('type', 'type', { unique: false });
                timelineStore.createIndex('eventType', 'eventType', { unique: false });
                timelineStore.createIndex('sourceId', 'sourceId', { unique: false });
            }

            // Tools store (v5) - Product Hunt style: n=name, d=desc, u=url, t=createdAt (minimal keys for size)
            if (!database.objectStoreNames.contains('tools')) {
                const toolsStore = database.createObjectStore('tools', { keyPath: 'id' });
                toolsStore.createIndex('t', 't', { unique: false });
            }
        };
    });
}

// Migrate from localStorage to IndexedDB
async function migrateFromLocalStorage() {
    const migrationKey = 'linklumina-migrated-to-indexeddb';
    const migrated = await getMetadata(migrationKey);

    if (migrated) return; // Already migrated

    // Migrate links
    const storedLinks = localStorage.getItem('linklumina-links');
    if (storedLinks) {
        try {
            const linksToMigrate = JSON.parse(storedLinks);
            for (const link of linksToMigrate) {
                await saveLinkToDB(link);
            }
        } catch (e) {
            console.error('Error migrating links:', e);
        }
    }

    // Migrate storage prompt
    const storagePrompt = localStorage.getItem('linklumina-storage-prompt');
    if (storagePrompt) {
        await setMetadata('storagePrompt', storagePrompt);
    }

    // Mark as migrated
    await setMetadata(migrationKey, true);
    showToast('Data migrated to IndexedDB (10GB capacity)', 'success');
}

// Database helper functions
function getStore(storeName, mode = 'readonly') {
    return db.transaction([storeName], mode).objectStore(storeName);
}

async function saveLinkToDB(link) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['links'], 'readwrite');
        const store = transaction.objectStore('links');
        const request = store.put(link);
        transaction.oncomplete = () => {
            scheduleRecoverySnapshot('links:save');
            bumpDataVersion();
            resolve();
        };
        transaction.onabort = () => reject(transaction.error || new Error('Save was aborted'));
        transaction.onerror = () => reject(transaction.error || request.error);
    });
}

async function deleteLinkFromDB(id) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['links'], 'readwrite');
        const store = transaction.objectStore('links');
        const request = store.delete(id);
        request.onsuccess = () => {
            scheduleRecoverySnapshot('links:delete');
            bumpDataVersion();
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function getAllLinksFromDB() {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['links'], 'readonly');
        const store = transaction.objectStore('links');
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

// New DB Helpers for Full Backup
async function getAllFoldersFromDB() {
    // Check if store exists
    if (!db.objectStoreNames.contains('folders')) return [];
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['folders'], 'readonly');
        const store = transaction.objectStore('folders');
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function getAllNotesFromDB() {
    if (!db.objectStoreNames.contains('notes')) return [];
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['notes'], 'readonly');
        const store = transaction.objectStore('notes');
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function saveFolderToDB(folder) {
    if (!db.objectStoreNames.contains('folders')) return;
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['folders'], 'readwrite');
        const store = transaction.objectStore('folders');
        const request = store.put(folder);
        request.onsuccess = () => {
            scheduleRecoverySnapshot('folders:save');
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function saveNoteToDB(note) {
    if (!db.objectStoreNames.contains('notes')) return;
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['notes'], 'readwrite');
        const store = transaction.objectStore('notes');
        const request = store.put(note);
        request.onsuccess = () => {
            scheduleRecoverySnapshot('notes:save');
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function savePromptToDB(prompt) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['prompts'], 'readwrite');
        const store = transaction.objectStore('prompts');
        const request = store.put(prompt);
        request.onsuccess = () => {
            scheduleRecoverySnapshot('prompts:save');
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function deletePromptFromDB(id) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['prompts'], 'readwrite');
        const store = transaction.objectStore('prompts');
        const request = store.delete(id);
        request.onsuccess = () => {
            scheduleRecoverySnapshot('prompts:delete');
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function getAllPromptsFromDB() {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['prompts'], 'readonly');
        const store = transaction.objectStore('prompts');
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function getAllToolsFromDB() {
    if (!db || !db.objectStoreNames.contains('tools')) return [];
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['tools'], 'readonly');
        const store = transaction.objectStore('tools');
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result || []);
        request.onerror = () => reject(request.error);
    });
}

async function saveToolToDB(tool) {
    if (!db || !db.objectStoreNames.contains('tools')) return;
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['tools'], 'readwrite');
        const store = transaction.objectStore('tools');
        const request = store.put(tool);
        request.onsuccess = () => {
            scheduleRecoverySnapshot('tools:save');
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function deleteToolFromDB(id) {
    if (!db || !db.objectStoreNames.contains('tools')) return;
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['tools'], 'readwrite');
        const store = transaction.objectStore('tools');
        const request = store.delete(id);
        request.onsuccess = () => {
            scheduleRecoverySnapshot('tools:delete');
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function getMetadata(key) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['metadata'], 'readonly');
        const store = transaction.objectStore('metadata');
        const request = store.get(key);
        request.onsuccess = () => resolve(request.result ? request.result.value : null);
        request.onerror = () => reject(request.error);
    });
}

async function setMetadata(key, value) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['metadata'], 'readwrite');
        const store = transaction.objectStore('metadata');
        const request = store.put({ key, value });
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

window.saveLinkToDB = saveLinkToDB;
window.deleteLinkFromDB = deleteLinkFromDB;
window.saveFolderToDB = saveFolderToDB;
window.saveNoteToDB = saveNoteToDB;
window.savePromptToDB = savePromptToDB;
window.deletePromptFromDB = deletePromptFromDB;
window.saveToolToDB = saveToolToDB;

// Initialize Lucide icons
// Batched icon init — multiple calls in same frame run once (performance).
// When many icons are pending (big library render) the work is chunked across
// frames so no single rAF blocks for ~100ms (avoids layout jank / violations).
let _iconsScheduled = false;
const ICON_CHUNK = 250;
function initializeIcons() {
    if (typeof lucide === 'undefined') return;
    if (_iconsScheduled) return;
    _iconsScheduled = true;
    requestAnimationFrame(() => {
        _iconsScheduled = false;
        const els = document.querySelectorAll('[data-lucide]');
        if (els.length <= ICON_CHUNK) { lucide.createIcons(); return; }
        const arr = Array.from(els);
        let i = 0;
        const step = () => {
            const slice = arr.slice(i, i + ICON_CHUNK);
            i += ICON_CHUNK;
            lucide.createIcons({ nodes: slice });
            if (i < arr.length) requestAnimationFrame(step);
        };
        step();
    });
}

// Create animated background
function initializeBackground() {
    const background = document.getElementById('background');
    background.innerHTML = `
        <div class="orb orb-1"></div>
        <div class="orb orb-2"></div>
        <div class="orb orb-3"></div>
    `;
}

// Load links from IndexedDB
async function loadLinks() {
    try {
        links = await getAllLinksFromDB();
        // Ensure all links have required fields
        links = links.map(link => ({
            ...link,
            favorite: link.favorite || false,
            visitCount: link.visitCount || 0,
            notes: link.notes || '',
            lastVisited: link.lastVisited || null,
            tags: link.tags || [],
            category: link.category || 'General'
        }));
        // Re-expose to window for neural.js access
        window.links = links;
    } catch (e) {
        console.error('Error loading links:', e);
        links = [];
        window.links = links;
        bumpDataVersion();
    }
}

// Load prompts from IndexedDB
async function loadPrompts() {
    try {
        prompts = await getAllPromptsFromDB();
        window.prompts = prompts;
    } catch (e) {
        console.error('Error loading prompts:', e);
        prompts = [];
    }
}

// Update all tags set
function updateAllTags() {
    allTags.clear();
    links.forEach(link => {
        link.tags.forEach(tag => allTags.add(tag));
    });
}

// Save links to IndexedDB
async function saveLinks() {
    try {
        // Save all links to IndexedDB
        for (const link of links) {
            await saveLinkToDB(link);
        }
    } catch (e) {
        console.error('Error saving links:', e);
        showToast('Error saving to storage', 'error');
    }
}

// Save a single link
async function saveSingleLink(link) {
    try {
        await saveLinkToDB(link);
    } catch (e) {
        console.error('Error saving link:', e);
        showToast('Error saving link', 'error');
    }
}

// Setup event listeners
function setupEventListeners() {
    // Add link button
    document.getElementById('addLinkBtn').addEventListener('click', () => openModal(null));

    // Close modal
    document.getElementById('closeModal').addEventListener('click', closeModal);
    document.getElementById('cancelBtn').addEventListener('click', closeModal);
    document.getElementById('modalOverlay').addEventListener('click', closeModal);
    document.getElementById('openTranscriptBtn')?.addEventListener('click', () => {
        const currentUrl = document.getElementById('linkUrl')?.value?.trim() || '';
        openTranscriptModal(editingLinkId || null, currentUrl);
    });

    // Storage modal
    document.getElementById('storageBtn').addEventListener('click', openStorageModal);
    // Manual "Backup Now" button (storage modal)
    document.getElementById('backupNowBtn')?.addEventListener('click', () => {
        if (typeof downloadFullBackup === 'function') downloadFullBackup();
        if (typeof showToast === 'function') showToast('💾 Backup downloaded — move it to your D drive', 'info');
    });
    document.getElementById('closeStorageModal').addEventListener('click', closeStorageModal);
    document.getElementById('storageModalOverlay').addEventListener('click', closeStorageModal);

    // Storage actions
    document.getElementById('optimizeStorageBtn').addEventListener('click', optimizeStorage);
    document.getElementById('clearImagesBtn').addEventListener('click', clearAllImages);
    if (document.getElementById('checkLinkHealthBtn')) {
        document.getElementById('checkLinkHealthBtn').addEventListener('click', batchCheckLinkHealth);
    }
    document.getElementById('exportBackupBtn').addEventListener('click', exportBackup);
    document.getElementById('clearAllDataBtn').addEventListener('click', clearAllData);

    // Storage prompt save
    document.getElementById('storagePrompt').addEventListener('blur', saveStoragePrompt);

    // Prompt modal
    document.getElementById('addPromptBtn').addEventListener('click', () => openPromptModal(null));
    document.getElementById('closePromptModal').addEventListener('click', closePromptModal);
    document.getElementById('cancelPromptBtn').addEventListener('click', closePromptModal);
    document.getElementById('promptModalOverlay').addEventListener('click', closePromptModal);
    document.getElementById('promptForm').addEventListener('submit', handlePromptSubmit);

    // Export/Import
    // Multiple buttons share these IDs (toolbar dropdown + storage modal), so wire ALL of them.
    document.getElementById('exportBtn').addEventListener('click', exportLinks); // unique Excel export card
    document.querySelectorAll('#exportJsonBtn').forEach(btn => btn.addEventListener('click', exportLinksAsJSON));
    document.querySelectorAll('#exportZipBtn').forEach(btn => btn.addEventListener('click', exportFolderBackup));
    document.querySelectorAll('#importFile, #importFileStorage').forEach(input => input.addEventListener('change', importLinks));
    document.querySelectorAll('#importBtn').forEach(btn => btn.addEventListener('click', () => {
        // Click the file input nearest to this button (falls back to the first one).
        const fileInput = btn.querySelector('input[type="file"]') || document.querySelector('#importFile');
        if (fileInput) fileInput.click();
    }));

    // Browser import
    document.querySelectorAll('#importBrowserBtn').forEach(btn => btn.addEventListener('click', () => {
        document.getElementById('browserImportModal').classList.remove('hidden');
        document.body.style.overflow = 'hidden';
        initializeIcons();
    }));
    document.getElementById('closeBrowserImport').addEventListener('click', closeBrowserImport);
    document.getElementById('cancelBrowserImport').addEventListener('click', closeBrowserImport);
    document.getElementById('browserImportOverlay').addEventListener('click', closeBrowserImport);
    document.getElementById('startBrowserImport').addEventListener('click', startBrowserImport);
    document.getElementById('browserBookmarksFile').addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            document.getElementById('startBrowserImport').disabled = false;
        }
    });

    // Quick save (header zap icon triggers this; the redundant menu entry was merged away)
    const quickSaveBtn = document.getElementById('quickSaveBtn');
    if (quickSaveBtn) quickSaveBtn.addEventListener('click', openQuickSave);
    document.getElementById('closeQuickSave').addEventListener('click', closeQuickSave);
    document.getElementById('cancelQuickSave').addEventListener('click', closeQuickSave);
    document.getElementById('quickSaveOverlay').addEventListener('click', closeQuickSave);
    document.getElementById('quickSaveForm').addEventListener('submit', handleQuickSave);

    // Single-URL quick save: Fetch metadata & Save one link
    const quickSaveFetchBtn = document.getElementById('quickSaveFetchBtn');
    const quickSaveOneBtn = document.getElementById('quickSaveOneBtn');
    if (quickSaveFetchBtn) quickSaveFetchBtn.addEventListener('click', fetchAndShowQuickSaveOne);
    if (quickSaveOneBtn) quickSaveOneBtn.addEventListener('click', saveQuickSaveOne);

    const quickSaveUrlInput = document.getElementById('quickSaveUrl');
    if (quickSaveUrlInput) {
        quickSaveUrlInput.addEventListener('paste', () => setTimeout(fetchAndShowQuickSaveOne, 100));
        quickSaveUrlInput.addEventListener('blur', () => { if (quickSaveUrlInput.value.trim()) fetchAndShowQuickSaveOne(); });
    }

    // Auto-newline on paste for Quick Save (bulk textarea)
    const quickSaveUrls = document.getElementById('quickSaveUrls');
    if (quickSaveUrls) {
        quickSaveUrls.addEventListener('paste', handleQuickSavePaste);
    }

    // Analytics
    document.getElementById('analyticsBtn').addEventListener('click', openAnalytics);
    document.getElementById('closeAnalytics').addEventListener('click', closeAnalytics);
    document.getElementById('analyticsOverlay').addEventListener('click', closeAnalytics);

    // View modes
    document.getElementById('viewGridBtn').addEventListener('click', () => switchView('grid'));
    document.getElementById('viewListBtn').addEventListener('click', () => switchView('list'));
    document.getElementById('viewTimelineBtn').addEventListener('click', () => switchView('timeline'));
    document.getElementById('viewGalleryBtn').addEventListener('click', () => switchView('gallery'));

    // Favorites filter
    document.getElementById('showFavoritesBtn').addEventListener('click', toggleFavorites);

    // Sort
    document.getElementById('sortSelect').addEventListener('change', (e) => {
        sortBy = e.target.value;
        localStorage.setItem('linkLumina_sortBy', sortBy);
        renderLinks();
    });

    // Smart Filter
    const filterSelect = document.getElementById('filterSelect');
    if (filterSelect) {
        filterSelect.addEventListener('change', () => {
            renderLinks();
        });
    }

    // Phase 4: Advanced filters & presets
    const advBar = document.getElementById('advancedFiltersBar');
    const toggleAdv = document.getElementById('toggleAdvancedFilters');
    if (toggleAdv && advBar) {
        toggleAdv.addEventListener('click', () => {
            advBar.classList.toggle('hidden');
            advBar.classList.toggle('flex');
        });
    }
    function applyAdvancedFilters() {
        const from = document.getElementById('filterDateFrom');
        const to = document.getElementById('filterDateTo');
        const minVis = document.getElementById('filterVisitMin');
        window.linkLumina_dateFrom = from && from.value ? from.value : null;
        window.linkLumina_dateTo = to && to.value ? to.value : null;
        window.linkLumina_visitMin = minVis && minVis.value !== '' ? parseInt(minVis.value, 10) : null;
        if (window.linkLumina_dateFrom) localStorage.setItem('linkLumina_dateFrom', window.linkLumina_dateFrom);
        else localStorage.removeItem('linkLumina_dateFrom');
        if (window.linkLumina_dateTo) localStorage.setItem('linkLumina_dateTo', window.linkLumina_dateTo);
        else localStorage.removeItem('linkLumina_dateTo');
        if (window.linkLumina_visitMin != null) localStorage.setItem('linkLumina_visitMin', window.linkLumina_visitMin);
        else localStorage.removeItem('linkLumina_visitMin');
        renderLinks();
    }
    const filterDateFrom = document.getElementById('filterDateFrom');
    const filterDateTo = document.getElementById('filterDateTo');
    const filterVisitMin = document.getElementById('filterVisitMin');
    if (filterDateFrom) filterDateFrom.addEventListener('change', applyAdvancedFilters);
    if (filterDateTo) filterDateTo.addEventListener('change', applyAdvancedFilters);
    if (filterVisitMin) filterVisitMin.addEventListener('input', applyAdvancedFilters);
    const clearAdv = document.getElementById('clearAdvancedFilters');
    if (clearAdv) {
        clearAdv.addEventListener('click', () => {
            if (filterDateFrom) filterDateFrom.value = '';
            if (filterDateTo) filterDateTo.value = '';
            if (filterVisitMin) filterVisitMin.value = '';
            window.linkLumina_dateFrom = null;
            window.linkLumina_dateTo = null;
            window.linkLumina_visitMin = null;
            localStorage.removeItem('linkLumina_dateFrom');
            localStorage.removeItem('linkLumina_dateTo');
            localStorage.removeItem('linkLumina_visitMin');
            renderLinks();
        });
    }
    if (typeof window.getFilterPresets === 'function') {
        const presets = window.getFilterPresets();
        if (presets.length) {
            window.linkLumina_dateFrom = localStorage.getItem('linkLumina_dateFrom') || null;
            window.linkLumina_dateTo = localStorage.getItem('linkLumina_dateTo') || null;
            const v = localStorage.getItem('linkLumina_visitMin');
            window.linkLumina_visitMin = v !== null && v !== '' ? parseInt(v, 10) : null;
            if (filterDateFrom && window.linkLumina_dateFrom) filterDateFrom.value = window.linkLumina_dateFrom;
            if (filterDateTo && window.linkLumina_dateTo) filterDateTo.value = window.linkLumina_dateTo;
            if (filterVisitMin && window.linkLumina_visitMin != null) filterVisitMin.value = window.linkLumina_visitMin;
        }
    }
    const savePresetBtn = document.getElementById('saveFilterPresetBtn');
    if (savePresetBtn && typeof window.saveFilterPreset === 'function') {
        savePresetBtn.addEventListener('click', () => {
            const name = prompt('Name this filter preset:');
            if (name && name.trim()) {
                window.saveFilterPreset(name.trim());
                showToast('Filter preset saved', 'success');
                const sel = document.getElementById('filterPresetSelect');
                if (sel) {
                    const presets = window.getFilterPresets();
                    sel.innerHTML = '<option value="">Presets</option>' + presets.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
                }
            }
        });
    }
    const presetSelect = document.getElementById('filterPresetSelect');
    if (presetSelect && typeof window.getFilterPresets === 'function' && typeof window.applyFilterPreset === 'function') {
        const presets = window.getFilterPresets();
        presetSelect.innerHTML = '<option value="">Presets</option>' + presets.map(p => `<option value="${p.id}">${escapeHtml(p.name)}</option>`).join('');
        presetSelect.addEventListener('change', (e) => {
            const id = e.target.value;
            if (!id) return;
            const presets = window.getFilterPresets();
            const preset = presets.find(p => p.id === id);
            if (preset) window.applyFilterPreset(preset);
            presetSelect.value = '';
        });
    }

    // Bulk delete (legacy inline button — bulk actions now live in the floating bar)
    const bulkDeleteBtn = document.getElementById('bulkDeleteBtn');
    if (bulkDeleteBtn) bulkDeleteBtn.addEventListener('click', bulkDelete);

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {
        // Escape - Close any open modal
        if (e.key === 'Escape') {
            const modals = [
                { el: document.getElementById('addLinkModal'), close: closeModal },
                { el: document.getElementById('storageModal'), close: closeStorageModal },
                { el: document.getElementById('promptModal'), close: closePromptModal },
                { el: document.getElementById('analyticsModal'), close: closeAnalytics },
                { el: document.getElementById('quickSaveModal'), close: closeQuickSave },
                { el: document.getElementById('syncModal'), close: window.closeSyncModal },
                { el: document.getElementById('batchMoveModal'), close: closeBatchMoveModal },
                { el: document.getElementById('commandPalette'), close: closeCommandPalette },
            ];
            for (const modal of modals) {
                if (modal.el && !modal.el.classList.contains('hidden')) {
                    if (typeof modal.close === 'function') modal.close();
                    e.preventDefault();
                    return;
                }
            }
            // Exit selection mode if active
            if (isSelectionMode) {
                toggleSelectionMode();
                e.preventDefault();
            }
        }

        // Ctrl+K - Command Palette (existing)
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            if (typeof openCommandPalette === 'function') openCommandPalette();
        }

        // F11 or Ctrl+Shift+F - Zen Mode
        if (e.key === 'F11' || ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'f')) {
            e.preventDefault();
            document.body.classList.toggle('zen-mode');
            const isZen = document.body.classList.contains('zen-mode');
            if (window.showToast) showToast(isZen ? 'Zen Mode Enabled' : 'Zen Mode Disabled', 'info');

            // Handle Fullscreen request alongside Zen Mode
            if (isZen && !document.fullscreenElement) {
                document.documentElement.requestFullscreen().catch((err) => console.log('Fullscreen rejected by browser', err));
            } else if (!isZen && document.fullscreenElement) {
                document.exitFullscreen().catch((err) => console.log('Exit fullscreen rejected', err));
            }
        }

        // Ctrl+F - Focus search
        if ((e.ctrlKey || e.metaKey) && e.key === 'f') {
            e.preventDefault();
            document.getElementById('searchInput').focus();
        }

        // Ctrl+N - New link
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            openModal();
        }

        // Ctrl+S - Quick save
        if ((e.ctrlKey || e.metaKey) && e.key === 's') {
            e.preventDefault();
            openQuickSave();
        }

        // ? - Show keyboard shortcuts help (when not typing)
        if (e.key === '?' && !e.target.matches('input, textarea')) {
            showKeyboardShortcuts();
        }
    });

    // Form submission
    document.getElementById('addLinkForm').addEventListener('submit', handleAddLink);

    // Search input with debounce + power-search UI (suggestions / chips)
    const searchInput = document.getElementById('searchInput');
    const clearSearchBtn = document.getElementById('clearSearch');
    let _suggestDebounce = null;

    searchInput.addEventListener('input', (e) => {
        const val = e.target.value;
        clearSearchBtn.classList.toggle('hidden', !val);
        renderSearchChips();

        clearTimeout(_searchDebounceTimer);
        _searchDebounceTimer = setTimeout(() => {
            searchTerm = val.toLowerCase();
            if (typeof window.pushSearchHistory === 'function' && searchTerm.length >= 2) window.pushSearchHistory(searchTerm);
            renderLinks();
        }, 250);

        clearTimeout(_suggestDebounce);
        _suggestDebounce = setTimeout(buildSearchSuggestions, 90);
    });

    searchInput.addEventListener('focus', () => {
        if (!searchInput.value.trim()) buildSearchSuggestions();
    });

    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            const box = document.getElementById('searchSuggestions');
            if (box && !box.classList.contains('hidden')) {
                e.preventDefault();
                _moveSuggestion(e.key === 'ArrowDown' ? 1 : -1);
            }
        } else if (e.key === 'Enter') {
            const box = document.getElementById('searchSuggestions');
            if (box && !box.classList.contains('hidden') && _suggestionActive >= 0) {
                const el = box.querySelectorAll('.ss-item')[_suggestionActive];
                if (el) { e.preventDefault(); _applySuggestion(el.dataset.apply); return; }
            }
            // Commit search immediately
            clearTimeout(_searchDebounceTimer);
            searchTerm = e.target.value.toLowerCase();
            if (typeof window.pushSearchHistory === 'function' && searchTerm.length >= 2) window.pushSearchHistory(searchTerm);
            renderLinks();
            closeSearchSuggestions();
        } else if (e.key === 'Escape') {
            closeSearchSuggestions();
            const tips = document.getElementById('searchTipsPopover');
            if (tips) tips.classList.add('hidden');
        } else if (e.key === 'Tab') {
            const box = document.getElementById('searchSuggestions');
            if (box && !box.classList.contains('hidden') && _suggestionActive >= 0) {
                const el = box.querySelectorAll('.ss-item')[_suggestionActive];
                if (el) { e.preventDefault(); _applySuggestion(el.dataset.apply); }
            }
        }
    });

    // Clear search
    clearSearchBtn.addEventListener('click', () => {
        clearTimeout(_searchDebounceTimer);
        searchInput.value = '';
        searchTerm = '';
        clearSearchBtn.classList.add('hidden');
        renderSearchChips();
        closeSearchSuggestions();
        renderLinks();
        searchInput.focus();
        initializeIcons();
    });

    // Search tips popover
    const tipsBtn = document.getElementById('searchTipsBtn');
    const tipsPop = document.getElementById('searchTipsPopover');
    tipsBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        const willOpen = tipsPop.classList.contains('hidden');
        tipsPop.classList.toggle('hidden');
        closeSearchSuggestions();
        if (willOpen) { tipsPop.innerHTML = SEARCH_TIPS_HTML; initializeIcons(); }
    });

    // Close suggestions / tips on outside click
    document.addEventListener('click', (e) => {
        if (!e.target.closest('#searchSuggestions') && !e.target.closest('.search-card')) {
            closeSearchSuggestions();
        }
        if (e.target !== tipsBtn && !e.target.closest('#searchTipsPopover')) {
            tipsPop.classList.add('hidden');
        }
    });

    // Tag suggestions
    const linkTags = document.getElementById('linkTags');
    linkTags.addEventListener('input', showTagSuggestions);
    linkTags.addEventListener('focus', showTagSuggestions);

    // More Menu Toggle
    const moreMenuBtn = document.getElementById('moreMenuBtn');
    const moreMenuDropdown = document.getElementById('moreMenuDropdown');

    if (moreMenuBtn && moreMenuDropdown) {
        moreMenuBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            moreMenuDropdown.classList.toggle('hidden');
        });

        document.addEventListener('click', (e) => {
            if (!moreMenuDropdown.classList.contains('hidden') && !moreMenuDropdown.contains(e.target) && e.target !== moreMenuBtn) {
                moreMenuDropdown.classList.add('hidden');
            }
        });
    }

    // More menu: Dense View toggle (moved out of the header to declutter)
    const compactMenuBtn = document.getElementById('compactModeMenuBtn');
    if (compactMenuBtn) {
        compactMenuBtn.addEventListener('click', () => {
            CompactMode.toggle();
            moreMenuDropdown.classList.add('hidden');
        });
    }

    // Image upload
    setupImageUpload();



    // ==================== BATCH MODE HANDLERS ====================
    // Toggle Selection Mode
    document.getElementById('selectModeBtn').addEventListener('click', toggleSelectionMode);
    document.getElementById('exitSelectModeBtn').addEventListener('click', toggleSelectionMode);

    // Batch Actions
    document.getElementById('batchMoveBtn').addEventListener('click', openBatchMoveModal);
    document.getElementById('batchDeleteBtn').addEventListener('click', handleBatchDelete);

    // Bulk Auto Enhance ("Magic Enchant") – one button: Tags + Description + Category for all selected
    async function bulkAutoEnhance() {
        if (batchSelectedLinks.size === 0) {
            showToast('Select at least one link to Magic Enchant.', 'info');
            return;
        }
        const linksToEnhance = [];
        for (const id of batchSelectedLinks) {
            const link = links.find(l => l.id === id);
            if (link) linksToEnhance.push(link);
        }
        const total = linksToEnhance.length;
        if (!confirm(`Magic Enchant ${total} selected links?\n\n✨ Automatically: Tags, Category, Description (Notes)\n\nImages can be enabled separately with the "Auto-load images" button.`)) return;

        let enhancedCount = 0;
        const updates = [];
        for (let i = 0; i < linksToEnhance.length; i++) {
            const link = linksToEnhance[i];
            let modified = false;

            // 1. Merge auto tags (never remove existing)
            const newTags = generateAutoTags(link);
            newTags.forEach(tag => {
                if (!link.tags) link.tags = [];
                if (!link.tags.includes(tag)) {
                    link.tags.push(tag);
                    modified = true;
                }
            });

            // 2. Auto category: set if empty, General, or Other (use unified getAutoCategory)
            const currentCat = (link.category || '').trim();
            const emptyOrGeneric = !currentCat || currentCat === 'General' || currentCat.toLowerCase() === 'other';
            if (emptyOrGeneric) {
                const detected = getAutoCategory(link.url, link.title);
                if (detected && detected !== 'General') {
                    link.category = detected;
                    modified = true;
                } else if (!currentCat) {
                    link.category = 'General';
                    modified = true;
                }
            }

            // 3. Auto description (notes) only if empty – use shared smart note (QoL)
            if (!link.notes || link.notes.trim() === '') {
                const autoNote = generateAutoNoteForLink(link);
                if (autoNote) {
                    link.notes = autoNote;
                    modified = true;
                }
            }

            if (modified) {
                updates.push(saveLinkToDB(link));
                enhancedCount++;
            }
            if (i % 5 === 0 || i === linksToEnhance.length - 1) {
                await new Promise(r => requestAnimationFrame(r));
                if (window.showToast) showToast(`Magic Enchant ${i + 1}/${total}...`, 'info');
            }
        }

        if (updates.length > 0) {
            await Promise.all(updates);
            renderLinks();
            renderCategoryFilters();
            updateAllTags();
            showToast(`✨ Magic Enchanted ${enhancedCount} links: Tags, Category, Description`, 'success');
        } else {
            showToast('These links are already optimized.', 'info');
        }
    }
    window.bulkAutoEnhance = bulkAutoEnhance;

    // ==================== COMBINED MAGIC ENHANCE (Smart + Unified) ====================
    // One-click: enhances metadata (tags/category/notes) + loads images
    // Smart skip: only processes what's missing
    async function bulkMagicEnhance() {
        const ids = Array.from(batchSelectedLinks);
        const total = ids.length;
        if (total === 0) {
            showToast('Select at least one link.', 'info');
            return;
        }
        const linksToProcess = [];
        for (const id of ids) {
            const link = links.find(l => l.id === id);
            if (link) linksToProcess.push(link);
        }

        const confirmMsg = `Magic Enhance ${total} links?\n\n✨ Will do:\n• Tags (if missing)\n• Category (if General/Other/empty)\n• Description/Notes (if empty)\n• Screenshot/favicon image (if missing)\n\n⏭️ Skips items that already exist.`;
        if (!confirm(confirmMsg)) return;

        showBulkProgress('Magic Enhance…');
        let done = 0, imgDone = 0, metaDone = 0;
        const updatePromises = [];

        for (let i = 0; i < linksToProcess.length; i++) {
            const link = linksToProcess[i];
            let metaModified = false;
            let imgAdded = false;

            // --- 1. METADATA (Tags, Category, Notes) ---
            // 1a. Tags: only add missing auto-tags
            const newTags = generateAutoTags(link);
            if (newTags.length > 0) {
                if (!link.tags) link.tags = [];
                newTags.forEach(tag => {
                    if (!link.tags.includes(tag)) {
                        link.tags.push(tag);
                        metaModified = true;
                    }
                });
            }

            // 1b. Category: only if empty, General, or Other
            const currentCat = (link.category || '').trim();
            const emptyOrGeneric = !currentCat || currentCat === 'General' || currentCat.toLowerCase() === 'other';
            if (emptyOrGeneric) {
                const detected = getAutoCategory(link.url, link.title);
                if (detected && detected !== 'General') {
                    link.category = detected;
                    metaModified = true;
                } else if (!currentCat) {
                    link.category = 'General';
                    metaModified = true;
                }
            }

            // 1c. Notes: only if empty
            if (!link.notes || link.notes.trim() === '') {
                const autoNote = generateAutoNoteForLink(link);
                if (autoNote) {
                    link.notes = autoNote;
                    metaModified = true;
                }
            }

            // --- 2. IMAGE: only if missing or is a favicon placeholder ---
            const hasRealImage = link.image &&
                link.image !== '' &&
                !link.image.includes('faviconV2') &&
                !link.image.includes('mshots/v1');
            if (!hasRealImage) {
                const url = await getImageUrlForLink(link);
                if (url) {
                    link.image = url;
                    imgAdded = true;
                }
            }

            if (metaModified || imgAdded) {
                updatePromises.push(saveLinkToDB(link));
                if (metaModified) metaDone++;
                if (imgAdded) imgDone++;
            }

            done++;
            // Yield every 3 items to keep UI responsive
            if (i % 3 === 0 || i === linksToProcess.length - 1) {
                await new Promise(r => requestAnimationFrame(r));
                updateBulkProgress(done, total, `Magic Enhance ${done}/${total} · Images ${imgDone} · Metadata ${metaDone}`);
            }
        }

        if (updatePromises.length > 0) {
            await Promise.all(updatePromises);
            renderLinks();
            renderCategoryFilters();
            updateAllTags();
            showToast(`✨ Magic Enhance done: ${metaDone} links updated metadata, ${imgDone} links loaded images`, 'success');
        } else {
            showToast('All links are already optimized — nothing more to do.', 'info');
        }

        hideBulkProgress();

        // Clean, animated exit from selection mode
        batchSelectedLinks.clear();
        if (isSelectionMode && typeof toggleSelectionMode === 'function') toggleSelectionMode();
        if (typeof initializeIcons === 'function') initializeIcons();
    }
    window.bulkMagicEnhance = bulkMagicEnhance;

    // Batch Modal Controls
    document.getElementById('cancelBatchMove').addEventListener('click', closeBatchMoveModal);
    document.getElementById('batchMoveOverlay').addEventListener('click', closeBatchMoveModal);
    document.getElementById('confirmBatchMove').addEventListener('click', confirmBatchMove);

    const cancelBulkEdit = document.getElementById('cancelBulkEdit');
    const bulkEditOverlay = document.getElementById('bulkEditOverlay');
    const confirmBulkEditBtn = document.getElementById('confirmBulkEdit');
    if (cancelBulkEdit) cancelBulkEdit.addEventListener('click', closeBulkEditModal);
    if (bulkEditOverlay) bulkEditOverlay.addEventListener('click', closeBulkEditModal);
    if (confirmBulkEditBtn) confirmBulkEditBtn.addEventListener('click', confirmBulkEdit);

    // Auto-fetch screenshot on URL blur (WOW Feature)
    const linkUrlInput = document.getElementById('linkUrl');
    linkUrlInput.addEventListener('blur', async (e) => {
        const url = e.target.value.trim();
        const dropZoneContent = document.getElementById('dropZoneContent');
        const imagePreview = document.getElementById('imagePreview');
        const previewImg = document.getElementById('previewImg');

        // Handle protocol
        let targetUrl = url;
        if (url && !url.match(/^https?:\/\//) && !url.match(/^file:\/\//)) {
            targetUrl = 'https://' + url;
        }

        // Simple URL validation
        const isValid = (str) => {
            try { return Boolean(new URL(str)); } catch (e) { return false; }
        };

        if (url && isValid(targetUrl) && imagePreview.classList.contains('hidden')) {
            const originalContent = dropZoneContent.innerHTML;

            // Show loading state
            dropZoneContent.innerHTML = `
                <div class="flex flex-col items-center justify-center text-red-400 animate-pulse py-4">
                    <i data-lucide="aperture" class="w-8 h-8 mb-2"></i>
                    <span class="text-sm font-medium">Capturing website preview...</span>
                </div>
    `;
            initializeIcons();

            try {
                // progressive loading strategy:
                // 1. Show High-Res Favicon INSTANTLY (0s wait)
                // 2. Load Full Screenshot in background -> Swap when ready

                const domain = new URL(targetUrl).hostname;
                const faviconUrl = `https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${encodeURIComponent(targetUrl)}&size=256`;

                // 1. Instant Feedback
                previewImg.src = faviconUrl;
                previewImg.dataset.screenshotUrl = faviconUrl;
                imagePreview.classList.remove('hidden');
                dropZoneContent.classList.add('hidden');
                dropZoneContent.innerHTML = originalContent;

                // 2. Background Load Screenshot (WordPress mshots)
                const screenshotUrl = `https://s.wordpress.com/mshots/v1/${encodeURIComponent(targetUrl)}?w=1280&h=960`;

                const bgImg = new Image();
                bgImg.onload = () => {
                    // Swap to screenshot when ready
                    previewImg.src = screenshotUrl;
                    previewImg.dataset.screenshotUrl = screenshotUrl;
                };
                // Minimal delay to allow UI to settle, then fetch
                setTimeout(() => { bgImg.src = screenshotUrl; }, 100);

            } catch (error) {
                console.error('Auto-preview failed:', error);
                dropZoneContent.innerHTML = originalContent;
            }
        }
    });

    // Remove image button - use event delegation since button is in hidden div
    document.addEventListener('click', (e) => {
        if (e.target.closest('#removeImageBtn')) {
            e.preventDefault();
            e.stopPropagation();
            document.getElementById('imagePreview').classList.add('hidden');
            document.getElementById('dropZoneContent').classList.remove('hidden');
            document.getElementById('imageInput').value = '';
            initializeIcons();
        }
    });
}

// Setup image upload with drag and drop
function setupImageUpload() {
    const dropZone = document.getElementById('imageDropZone');
    const fileInput = document.getElementById('imageInput');
    const preview = document.getElementById('imagePreview');
    const previewImg = document.getElementById('previewImg');
    const dropZoneContent = document.getElementById('dropZoneContent');

    // Click to select
    dropZone.addEventListener('click', () => fileInput.click());

    // File input change
    fileInput.addEventListener('change', (e) => {
        handleFileSelect(e.target.files[0]);
    });

    // Drag and drop
    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('drag-over');
        const file = e.dataTransfer.files[0];
        if (file) {
            handleFileSelect(file);
        }
    });

    function handleFileSelect(file) {
        if (!file.type.startsWith('image/')) {
            alert('Please select an image file.');
            return;
        }

        // Check file size (50MB limit)
        if (file.size > 50 * 1024 * 1024) {
            alert('Image size must be less than 50MB. Please compress the image and try again.');
            return;
        }

        const reader = new FileReader();
        reader.onload = (e) => {
            previewImg.src = e.target.result;
            preview.classList.remove('hidden');
            dropZoneContent.classList.add('hidden');
            initializeIcons(); // Initialize icons for the remove button
        };
        reader.readAsDataURL(file);
    }
}

// Open add/edit link modal
function openModal(linkId = null) {
    editingLinkId = linkId;
    const modal = document.getElementById('addLinkModal');
    const modalTitle = document.getElementById('modalTitle');
    const submitText = document.getElementById('submitText');

    if (linkId) {
        const link = links.find(l => l.id === linkId);
        if (link) {
            modalTitle.textContent = 'Edit Link';
            submitText.textContent = 'Save Changes';
            populateLinkCategoryOptions(link.category);
            document.getElementById('linkUrl').value = link.url;
            document.getElementById('linkTitle').value = link.title;
            document.getElementById('linkCategory').value = link.category || 'General';
            document.getElementById('linkTags').value = link.tags.join(', ');
            document.getElementById('linkNotes').value = link.notes || '';

            // Render Related Links
            const relatedContainer = document.getElementById('relatedLinksSection');
            const relatedList = document.getElementById('relatedLinksList');

            if (relatedContainer && relatedList) {
                // Find related by tags
                const related = window.links
                    .filter(l => l.id !== link.id && l.tags.some(t => link.tags.includes(t)))
                    .map(l => {
                        const overlap = l.tags.filter(t => link.tags.includes(t)).length;
                        return { link: l, overlap };
                    })
                    .sort((a, b) => b.overlap - a.overlap)
                    .slice(0, 3);

                if (related.length > 0) {
                    relatedContainer.classList.remove('hidden');
                    relatedList.innerHTML = related.map(item => `
                        <div class="flex items-center gap-2 p-2 rounded bg-white/5 hover:bg-white/10 cursor-pointer transition-colors" onclick="openModal('${item.link.id}')">
                            <i data-lucide="link" class="w-3 h-3 text-red-400"></i>
                            <div class="flex-1 min-w-0">
                                <div class="text-sm text-gray-200 truncate">${item.link.title}</div>
                                <div class="text-xs text-gray-500 truncate">${item.overlap} shared tag(s)</div>
                            </div>
                        </div>
                    `).join('');
                } else {
                    relatedContainer.classList.add('hidden');
                }
            }

            if (link.image) {
                document.getElementById('previewImg').src = link.image;
                document.getElementById('imagePreview').classList.remove('hidden');
                document.getElementById('dropZoneContent').classList.add('hidden');
            } else {
                document.getElementById('imagePreview').classList.add('hidden');
                document.getElementById('dropZoneContent').classList.remove('hidden');
            }
        }
    } else {
        modalTitle.textContent = 'Add New Link';
        submitText.textContent = 'Add Link';
        populateLinkCategoryOptions('General');
        if (document.getElementById('relatedLinksSection')) {
            document.getElementById('relatedLinksSection').classList.add('hidden');
        }
    }

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    // Focus on URL input
    setTimeout(() => {
        document.getElementById('linkUrl').focus();
    }, 100);
    initializeIcons();
}

// Close add link modal
function closeModal() {
    const modal = document.getElementById('addLinkModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';

    // Reset form
    document.getElementById('addLinkForm').reset();
    document.getElementById('imagePreview').classList.add('hidden');
    document.getElementById('dropZoneContent').classList.remove('hidden');
    document.getElementById('imageInput').value = '';
    document.getElementById('tagSuggestions').classList.add('hidden');
    editingLinkId = null;

    // Reset submit button
    const submitBtn = document.getElementById('submitBtn');
    const submitText = document.getElementById('submitText');
    const submitLoading = document.getElementById('submitLoading');
    if (submitBtn && submitText && submitLoading) {
        submitText.classList.remove('hidden');
        submitLoading.classList.add('hidden');
        submitBtn.disabled = false;
    }
}

// Handle add link form submission
// Enhanced handleAddLink with Auto-Magic 🪄
async function handleAddLink(e) {
    e.preventDefault();

    const submitBtn = document.getElementById('submitBtn');
    const submitText = document.getElementById('submitText');
    const submitLoading = document.getElementById('submitLoading');
    if (submitBtn.disabled) return;
    const originalBtnContent = submitBtn.innerHTML;
    const previousLinks = links.slice();
    let committedLink = null;

    // Show loading state with Magic Indicator
    if (submitText && submitLoading) {
        submitText.classList.add('hidden');
        submitLoading.classList.remove('hidden');
    }
    submitBtn.innerHTML = '<i data-lucide="sparkles" class="w-4 h-4 animate-spin"></i> Magic Processing...';
    submitBtn.disabled = true;

    // reset helper
    const resetSubmitButton = () => {
        if (submitText && submitLoading) {
            submitText.classList.remove('hidden');
            submitLoading.classList.add('hidden');
        }
        submitBtn.innerHTML = originalBtnContent;
        submitBtn.disabled = false;
        // Restore icon if needed
        const icon = submitBtn.querySelector('i');
        if (icon) icon.setAttribute('data-lucide', 'plus');
        initializeIcons();
    };

    try {
    const url = document.getElementById('linkUrl').value.trim();
    let title = document.getElementById('linkTitle').value.trim();
    let category = document.getElementById('linkCategory').value;
    const tagsInput = document.getElementById('linkTags').value.trim();
    let notes = document.getElementById('linkNotes').value.trim();
    const imageInput = document.getElementById('imageInput');

    if (!url) {
        showToast('URL is required.', 'error');
        resetSubmitButton();
        return;
    }

    // Validate URL
    let validUrl;
    try {
        validUrl = new URL(url);
        if (!['http:', 'https:'].includes(validUrl.protocol) || validUrl.username || validUrl.password) throw new Error('Only web links are supported');
    } catch {
        showToast('Please enter a valid URL.', 'error');
        resetSubmitButton();
        return;
    }

    // --- Duplicate URL check (links features together: add ↔ existing library) ---
    if (typeof findDuplicateUrl === 'function') {
        const dup = findDuplicateUrl(url);
        if (dup && dup.id !== editingLinkId) {
            const openExisting = confirm(`⚠️ This link is already in your library:\n\n"${dup.title}"\n\n• OK → Open the saved link (no duplicate added)\n• Cancel → Add a duplicate anyway`);
            if (openExisting) {
                resetSubmitButton();
                closeModal();
                visitLink(dup.url, dup.id);
                showToast('Opened the existing link', 'info');
                return;
            }
        }
    }

    // --- AUTOMATION START ---

    // 1. Process Image (User Upload > User Screenshot > Auto Fetch)
    let imageBase64 = null;

    // Check Upload
    if (imageInput.files && imageInput.files[0]) {
        try {
            const file = imageInput.files[0];
            if (file.size > 50 * 1024 * 1024) throw new Error('Image too large (>50MB)');
            imageBase64 = await convertToBase64(file);
        } catch (error) {
            showToast('Error processing image: ' + error.message, 'error');
            resetSubmitButton();
            return;
        }
    }
    // Check Manual Screenshot
    else {
        const imagePreview = document.getElementById('imagePreview');
        const previewImg = document.getElementById('previewImg');
        if (!imagePreview.classList.contains('hidden') && previewImg.src) {
            imageBase64 = previewImg.dataset.screenshotUrl || previewImg.src;
        }
    }

    // 2. Fetch Metadata if Title is missing OR Image is still null
    if (!title || !imageBase64) {
        // Only fetch if we need something
        try {
            let metadataTimer;
            const metadata = await Promise.race([
                fetchMetadataHelper(url),
                new Promise((_, reject) => { metadataTimer = setTimeout(() => reject(new Error('Metadata timed out; saving the link without it')), 4000); })
            ]).finally(() => clearTimeout(metadataTimer));

            // Auto-Title
            if (!title && metadata.title) {
                title = metadata.title;
            }

            // Auto-Image (Favicon/OG)
            if (!imageBase64 && metadata.image) {
                imageBase64 = metadata.image;
            }
        } catch (err) {
            console.warn('Auto-metadata failed:', err);
        }
    }

    // 3. Auto-Categorize
    if (category === 'general' || category === 'General') {
        const autoCat = autoCategorizeUrl(url, title);
        if (autoCat) category = autoCat;
    }

    // 4. Auto-Tags
    let tags = tagsInput
        ? tagsInput.split(',').map(tag => tag.trim().toLowerCase()).filter(tag => tag)
        : [];

    if (tags.length === 0) {
        const tempLink = { url, title: title || validUrl.hostname.replace('www.', '') };
        tags = generateAutoTags(tempLink);
    }

    // --- AUTOMATION END ---


    if (editingLinkId) {
        // Update existing link
        const linkIndex = links.findIndex(l => l.id === editingLinkId);
        if (linkIndex !== -1) {
            const existingLink = links[linkIndex];
            // Update favicon if URL changed logic preserved or handled by metadata?
            // For now, let's keep it simple. If imageBase64 is null, keep existing.
            // But if we auto-fetched a new one, we use it. 

            // Re-fetch favicon logic from original (simplified)
            let favicon = existingLink.favicon;
            if (existingLink.url !== url) {
                favicon = imageBase64 && imageBase64.startsWith('http') ? imageBase64 : `https://t3.gstatic.com/faviconV2?url=${encodeURIComponent(validUrl.href)}&size=64`;
            }

            links[linkIndex] = {
                ...existingLink,
                url,
                title: title || validUrl.hostname.replace('www.', ''),
                category,
                tags,
                favicon,
                notes,
                image: imageBase64 !== null ? imageBase64 : existingLink.image,
            };
            await saveLinkToDB(links[linkIndex]);
            committedLink = links[linkIndex];
            showToast('Link updated successfully! ✨', 'success');
        }
    } else {
        // Create new link
        const accentColor = neonColors[Math.floor(Math.random() * neonColors.length)];

        // Get initial favicon from our fetch if possible (usually same as image if from helper)
        let favicon = imageBase64 && imageBase64.startsWith('http') ? imageBase64 : `https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${encodeURIComponent(validUrl.href)}&size=64`;

        const finalTitle = title || validUrl.hostname.replace('www.', '');
        const notesToSave = notes || generateAutoNoteForLink({ url, title: finalTitle, category }) || '';

        const newLink = {
            id: typeof crypto.randomUUID === 'function' ? crypto.randomUUID() : Date.now().toString() + '-' + Math.random().toString(16).slice(2),
            url,
            title: finalTitle,
            category,
            tags,
            notes: notesToSave,
            image: imageBase64,
            favicon,
            accentColor,
            favorite: false,
            visitCount: 0,
            createdAt: new Date().toISOString(),
            lastVisited: null,
        };
        links.push(newLink);
        await saveLinkToDB(newLink);
        committedLink = newLink;

        // Emit via EventBus
        if (window.EventBus && window.EVENTS) {
            window.EventBus.emit(window.EVENTS.LINK_ADDED, { item: newLink, eventType: 'link_added' });
        } else if (window.LawEngine && newLink) {
            window.LawEngine.emit('link_added', { item: newLink, eventType: 'link_added' });
        }

        showToast('Link saved with Auto-Magic! 🪄', 'success');
        checkMilestone(links.length);
    }

    updateAllTags();
    // The changed record is already committed; do not rewrite the entire library.
    renderLinks();
    renderCategoryFilters();
    closeModal();
    initializeIcons();
    updateStorageStatsIfOpen();
    } catch (error) {
        if (!committedLink) {
            links.splice(0, links.length, ...previousLinks);
            showToast('Could not save this link. Your form is retained: ' + error.message, 'error');
        } else {
            // A rendering/plugin failure cannot undo an already durable save.
            showToast('Link saved locally. Refresh the view if it has not updated.', 'warning');
            closeModal();
            console.warn('Post-save update failed', error);
        }
    } finally {
        resetSubmitButton();
    }
}

// Convert file to Base64
function convertToBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

function looksLikeVideoPlatformUrl(url) {
    try {
        const hostname = new URL(url).hostname.replace(/^www\./, '').toLowerCase();
        return [
            'youtube.com',
            'youtu.be',
            'm.youtube.com',
            'tiktok.com',
            'vm.tiktok.com',
            'instagram.com',
            'facebook.com',
            'fb.watch',
            'douyin.com',
            'iesdouyin.com'
        ].some(domain => hostname === domain || hostname.endsWith('.' + domain));
    } catch (e) {
        return false;
    }
}

function normalizeTranscriptSourceUrl(url) {
    try {
        const parsed = new URL(String(url || '').trim());
        parsed.hash = '';
        [
            'utm_source',
            'utm_medium',
            'utm_campaign',
            'utm_term',
            'utm_content',
            'fbclid',
            'gclid',
            'si'
        ].forEach(key => parsed.searchParams.delete(key));
        return parsed.toString();
    } catch (e) {
        return String(url || '').trim();
    }
}

function buildTranscriptReaderCandidates(url) {
    const normalized = normalizeTranscriptSourceUrl(url);
    const withoutProtocol = normalized.replace(/^https?:\/\//i, '');
    return [
        `https://r.jina.ai/http://${withoutProtocol}`,
        `https://r.jina.ai/http://${normalized}`,
        `https://r.jina.ai/http://r.jina.ai/http://${withoutProtocol}`
    ];
}

function cleanupTranscriptText(raw) {
    const normalized = String(raw || '')
        .replace(/\r/g, '')
        .replace(/\t/g, ' ')
        .replace(/\u00a0/g, ' ');

    const lines = normalized.split('\n');
    const cleaned = [];
    let transcriptStart = -1;

    for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();
        if (/^#{1,6}\s*(transcript|captions?|subtitles?)/i.test(line) || /^transcript\s*[:\-]?$/i.test(line)) {
            transcriptStart = i + 1;
            break;
        }
    }

    const sourceLines = transcriptStart >= 0 ? lines.slice(transcriptStart) : lines;
    let lastLine = '';
    for (const originalLine of sourceLines) {
        let line = originalLine.trim();
        if (!line) continue;
        if (/^title:\s*/i.test(line)) continue;
        if (/^url source:\s*/i.test(line)) continue;
        if (/^markdown content:\s*/i.test(line)) continue;
        if (/^\[!?\[.*\]\(.*\)\]\(.*\)$/.test(line)) continue;
        if (/^!\[.*\]\(.*\)$/.test(line)) continue;
        if (/^https?:\/\//i.test(line)) continue;
        if (/^(sign in|log in|sign up|follow|share|download|home|search|menu)$/i.test(line)) continue;
        if (/^[|<>~`*_=\-]{3,}$/.test(line)) continue;
        if (/^[A-Za-z0-9 _-]{1,20}:\s*$/.test(line) && !/transcript/i.test(line)) continue;

        line = line
            .replace(/\[(.*?)\]\((.*?)\)/g, '$1')
            .replace(/\s{2,}/g, ' ')
            .trim();

        if (!line) continue;
        if (line === lastLine) continue;
        lastLine = line;
        cleaned.push(line);
    }

    const text = cleaned.join('\n');
    return text
        .replace(/\n{3,}/g, '\n\n')
        .replace(/[ \t]+\n/g, '\n')
        .trim();
}

async function fetchComprehensiveTranscript(url) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 30000);
    try {
        const candidates = buildTranscriptReaderCandidates(url);
        let lastStatus = null;
        let lastError = null;

        for (const candidate of candidates) {
            try {
                const res = await fetch(candidate, {
                    method: 'GET',
                    signal: controller.signal,
                    headers: { 'Accept': 'text/plain' }
                });
                lastStatus = res.status;
                if (!res.ok) continue;

                const raw = await res.text();
                const text = cleanupTranscriptText(raw);
                if (!text || text.length < 120) continue;

                return {
                    transcript: text,
                    fetchedAt: new Date().toISOString(),
                    sourceUrl: normalizeTranscriptSourceUrl(url),
                    method: 'r.jina.ai'
                };
            } catch (error) {
                lastError = error;
            }
        }

        if (lastStatus === 422) {
            throw new Error('This link was rejected by the reader (422). Try the full original video link instead of a share/short link.');
        }
        if (lastError && lastError.name === 'AbortError') {
            throw new Error('Timed out while fetching the transcript.');
        }
        throw new Error('Could not find enough transcript content from this link.');
    } finally {
        clearTimeout(timeoutId);
    }
}

function formatTranscriptForNotes(result) {
    const fetchedAt = new Date(result.fetchedAt).toLocaleString();
    return [
        '=== VIDEO TRANSCRIPT ===',
        `Nguon: ${result.sourceUrl}`,
        `Lay luc: ${fetchedAt}`,
        '',
        result.transcript
    ].join('\n');
}

function injectTranscriptIntoCurrentForm(transcriptBlock) {
    const notesEl = document.getElementById('linkNotes');
    if (!notesEl) return false;
    const existing = notesEl.value.trim();
    notesEl.value = existing ? `${existing}\n\n${transcriptBlock}` : transcriptBlock;
    return true;
}

async function saveTranscriptToLink(linkId, transcriptBlock) {
    const link = (window.links || []).find(l => l.id === linkId);
    if (!link) return false;
    link.notes = link.notes ? `${link.notes}\n\n${transcriptBlock}` : transcriptBlock;
    await saveSingleLink(link);
    renderLinks();
    return true;
}

function renderTranscriptResult(result) {
    const output = document.getElementById('transcriptOutput');
    const meta = document.getElementById('transcriptMeta');
    const copyBtn = document.getElementById('copyTranscriptBtn');
    const saveBtn = document.getElementById('saveTranscriptBtn');
    if (!output || !meta) return;

    output.value = result.transcript;
    output.dataset.transcriptBlock = formatTranscriptForNotes(result);
    meta.textContent = `Nguon: ${result.sourceUrl} • ${new Date(result.fetchedAt).toLocaleString()}`;
    if (copyBtn) copyBtn.disabled = false;
    if (saveBtn) saveBtn.disabled = false;
}

function populateTranscriptLinkSelect() {
    const select = document.getElementById('transcriptTabLinkSelect');
    if (!select) return;
    const currentValue = select.value;
    const options = ['<option value="">Select a link to save the transcript...</option>'];
    (window.links || []).slice().sort((a, b) => {
        const aTitle = String(a.title || '').toLowerCase();
        const bTitle = String(b.title || '').toLowerCase();
        return aTitle.localeCompare(bTitle);
    }).forEach(link => {
        options.push(`<option value="${escapeHtml(link.id)}">${escapeHtml(link.title || link.url)}</option>`);
    });
    select.innerHTML = options.join('');
    if (currentValue && (window.links || []).some(link => link.id === currentValue)) {
        select.value = currentValue;
    }
}

function renderTranscriptTab() {
    populateTranscriptLinkSelect();
    if (window.initializeTranscriptTab) window.initializeTranscriptTab();
}

function initializeTranscriptTab() {
    const fetchBtn = document.getElementById('transcriptTabFetchBtn');
    const copyBtn = document.getElementById('transcriptTabCopyBtn');
    const saveBtn = document.getElementById('transcriptTabSaveBtn');
    const input = document.getElementById('transcriptTabUrlInput');
    const output = document.getElementById('transcriptTabOutput');
    const meta = document.getElementById('transcriptTabMeta');
    const statusBadge = document.getElementById('transcriptTabStatusBadge');
    const select = document.getElementById('transcriptTabLinkSelect');
    if (!fetchBtn || !copyBtn || !saveBtn || !input || !output || !meta || !statusBadge || !select) return;
    if (fetchBtn.dataset.bound === '1') return;
    fetchBtn.dataset.bound = '1';

    fetchBtn.addEventListener('click', async () => {
        const url = input.value.trim();
        if (!url) {
            showToast('Enter a video link first.', 'warning');
            return;
        }
        try {
            new URL(url);
        } catch (e) {
            showToast('Invalid video link.', 'error');
            return;
        }

        fetchBtn.disabled = true;
        copyBtn.disabled = true;
        saveBtn.disabled = true;
        output.value = '';
        delete output.dataset.transcriptBlock;
        meta.textContent = 'Fetching transcript...';
        statusBadge.textContent = looksLikeVideoPlatformUrl(url) ? 'Fetching social video transcript' : 'Fetching readable page content';

        try {
            const result = await fetchComprehensiveTranscript(url);
            output.value = result.transcript;
            output.dataset.transcriptBlock = formatTranscriptForNotes(result);
            meta.textContent = `Nguon: ${result.sourceUrl} • ${new Date(result.fetchedAt).toLocaleString()}`;
            statusBadge.textContent = 'Transcript fetched';
            copyBtn.disabled = false;
            saveBtn.disabled = false;
            showToast('Transcript fetched.', 'success');
        } catch (error) {
            console.error('Transcript tab fetch failed:', error);
            meta.textContent = 'Could not fetch a transcript from this link.';
            statusBadge.textContent = 'Fetch failed';
            showToast(error.message || 'Could not fetch the transcript.', 'error');
        } finally {
            fetchBtn.disabled = false;
        }
    });

    copyBtn.addEventListener('click', async () => {
        const text = output.value.trim();
        if (!text) return;
        try {
            await navigator.clipboard.writeText(text);
            showToast('Transcript copied.', 'success');
        } catch (e) {
            showToast('Failed to copy transcript.', 'error');
        }
    });

    saveBtn.addEventListener('click', async () => {
        const linkId = select.value;
        const transcriptBlock = output.dataset.transcriptBlock || '';
        if (!transcriptBlock) {
            showToast('No transcript to save yet.', 'warning');
            return;
        }
        if (!linkId) {
            showToast('Select a link to save the transcript.', 'warning');
            return;
        }
        try {
            await saveTranscriptToLink(linkId, transcriptBlock);
            showToast('Transcript saved to the link\'s notes.', 'success');
            populateTranscriptLinkSelect();
        } catch (error) {
            console.error('Transcript tab save failed:', error);
            showToast('Failed to save the transcript.', 'error');
        }
    });
}

function openTranscriptModal(linkId = null, initialUrl = '') {
    if (!window.showGenericModal) return;
    const safeUrl = escapeHtml(initialUrl || '');
    const content = `
        <div class="p-5 space-y-4">
            <div class="flex items-start justify-between gap-3">
                <div>
                    <h3 class="text-xl font-bold text-white">Video Transcript</h3>
                    <p class="text-sm text-gray-400 mt-1">Best-effort transcript for social video links. The app tries to grab the captions/readable content from the video page.</p>
                </div>
                <button type="button" onclick="closeGenericModal()" class="p-2 rounded-lg bg-white/5 hover:bg-white/10 text-gray-300">
                    <i data-lucide="x" class="w-5 h-5"></i>
                </button>
            </div>
            <div class="space-y-2">
                <label class="block text-sm font-medium text-gray-300">Video URL</label>
                <input id="transcriptUrlInput" type="url" value="${safeUrl}" placeholder="https://youtube.com/watch?v=..."
                    class="w-full px-4 py-3 rounded-lg bg-black/30 border border-white/10 text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-red-500">
                <p id="transcriptStatus" class="text-xs text-gray-500">Best support for YouTube, TikTok, Instagram, Facebook, Douyin and pages with readable captions/text.</p>
            </div>
            <div class="flex flex-wrap gap-2">
                <button type="button" id="runTranscriptBtn" data-link-id="${linkId || ''}" class="px-4 py-2 rounded-lg brand-gradient text-white flex items-center gap-2">
                    <i data-lucide="file-text" class="w-4 h-4"></i>
                    Fetch Transcript
                </button>
                <button type="button" id="copyTranscriptBtn" disabled class="px-4 py-2 rounded-lg bg-white/5 hover:bg-white/10 disabled:opacity-40 disabled:cursor-not-allowed text-white flex items-center gap-2">
                    <i data-lucide="copy" class="w-4 h-4"></i>
                    Copy
                </button>
                <button type="button" id="saveTranscriptBtn" disabled data-link-id="${linkId || ''}" class="px-4 py-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 disabled:opacity-40 disabled:cursor-not-allowed text-red-100 flex items-center gap-2">
                    <i data-lucide="save" class="w-4 h-4"></i>
                    Save to notes
                </button>
            </div>
            <div class="rounded-xl border border-white/10 bg-black/20 p-3">
                <div id="transcriptMeta" class="text-xs text-gray-500 mb-2">No transcript yet.</div>
                <textarea id="transcriptOutput" class="w-full min-h-[320px] max-h-[55vh] resize-y rounded-lg bg-black/30 border border-white/10 text-gray-100 p-4 focus:outline-none focus:ring-2 focus:ring-red-500" placeholder="Transcript will appear here..."></textarea>
            </div>
        </div>
    `;

    window.showGenericModal(content);

    const runBtn = document.getElementById('runTranscriptBtn');
    const copyBtn = document.getElementById('copyTranscriptBtn');
    const saveBtn = document.getElementById('saveTranscriptBtn');
    const statusEl = document.getElementById('transcriptStatus');
    const output = document.getElementById('transcriptOutput');

    if (runBtn) {
        runBtn.addEventListener('click', async () => {
            const input = document.getElementById('transcriptUrlInput');
            const url = input ? input.value.trim() : '';
            if (!url) {
                showToast('Enter a video link first.', 'warning');
                return;
            }
            try {
                new URL(url);
            } catch (e) {
                showToast('Invalid video link.', 'error');
                return;
            }

            runBtn.disabled = true;
            if (statusEl) statusEl.textContent = looksLikeVideoPlatformUrl(url)
                ? 'Fetching transcript from the video...'
                : 'Trying to read this page\'s content to build a transcript...';
            if (output) output.value = '';
            if (copyBtn) copyBtn.disabled = true;
            if (saveBtn) saveBtn.disabled = true;

            try {
                const result = await fetchComprehensiveTranscript(url);
                renderTranscriptResult(result);
                if (statusEl) statusEl.textContent = 'Transcript fetched. You can copy it or save it to notes.';
                showToast('Transcript fetched.', 'success');
            } catch (error) {
                console.error('Transcript fetch failed:', error);
                if (statusEl) statusEl.textContent = 'Could not fetch a transcript from this link. Try the video\'s original link, not a redirect/share short link.';
                showToast(error.message || 'Could not fetch the transcript.', 'error');
            } finally {
                runBtn.disabled = false;
            }
        });
    }

    if (copyBtn) {
        copyBtn.addEventListener('click', async () => {
            const text = output ? output.value.trim() : '';
            if (!text) return;
            try {
                await navigator.clipboard.writeText(text);
                showToast('Transcript copied.', 'success');
            } catch (e) {
                showToast('Failed to copy transcript.', 'error');
            }
        });
    }

    if (saveBtn) {
        saveBtn.addEventListener('click', async () => {
            const transcriptBlock = output ? output.dataset.transcriptBlock : '';
            const targetLinkId = saveBtn.getAttribute('data-link-id') || '';
            if (!transcriptBlock) {
                showToast('No transcript to save yet.', 'warning');
                return;
            }
            try {
                const saved = targetLinkId
                    ? await saveTranscriptToLink(targetLinkId, transcriptBlock)
                    : injectTranscriptIntoCurrentForm(transcriptBlock);
                if (!saved) throw new Error('No place found to save the transcript.');
                showToast('Transcript saved to notes.', 'success');
                closeGenericModal();
            } catch (error) {
                console.error('Transcript save failed:', error);
                showToast(error.message || 'Failed to save the transcript.', 'error');
            }
        });
    }
}

// Delete link with undo capability
let lastDeletedLink = null;
let undoDeleteTimer = null;

async function deleteLink(id, event = null) {
    if (event) event.stopPropagation();

    // Find the link before deletion
    const linkToDelete = links.find(link => link.id === id);
    if (!linkToDelete) return;

    // Store for potential undo + persistent Trash (restore later, even after reload)
    lastDeletedLink = { ...linkToDelete };
    if (typeof addToTrash === 'function') addToTrash(linkToDelete);

    // Remove from array (soft delete first)
    links = links.filter(link => link.id !== id);
    selectedLinks.delete(id);

    // Update UI immediately
    updateBulkActionUI();
    renderLinks();
    renderCategoryFilters();
    updateStorageStatsIfOpen();

    // Activity feed
    if (window.EventBus && window.EVENTS) {
        window.EventBus.emit(window.EVENTS.LINK_DELETED, { item: linkToDelete });
    }

    // Show toast with undo button
    showUndoToast(`"${linkToDelete.title}" deleted`, async () => {
        // Undo action
        if (lastDeletedLink) {
            links.push(lastDeletedLink);
            await saveLinkToDB(lastDeletedLink);
            lastDeletedLink = null;
            renderLinks();
            renderCategoryFilters();
            showToast('Link restored!', 'success');
        }
    });

    // Clear undo timer
    clearTimeout(undoDeleteTimer);

    // Actually delete from DB after 5 seconds (giving time to undo)
    undoDeleteTimer = setTimeout(async () => {
        if (lastDeletedLink && lastDeletedLink.id === id) {
            await deleteLinkFromDB(id);
            lastDeletedLink = null;
        }
    }, 5000);
}

// Show toast with undo action button
function showUndoToast(message, undoCallback) {
    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');
    const toastIcon = document.getElementById('toastIcon');

    // Create undo button HTML
    toastMessage.innerHTML = `
        <span>${message}</span>
        <button id="undoBtn" class="ml-3 px-3 py-1 bg-red-500 hover:bg-red-600 text-white text-sm font-medium rounded-lg transition-colors">
            Undo
        </button>
    `;

    toastIcon.setAttribute('data-lucide', 'trash-2');
    toast.classList.remove('translate-x-full');
    toast.classList.add('translate-x-0', 'bg-red-500/20', 'border-l-4', 'border-red-500');

    if (typeof lucide !== 'undefined') lucide.createIcons();

    // Attach undo listener
    setTimeout(() => {
        const undoBtn = document.getElementById('undoBtn');
        if (undoBtn) {
            undoBtn.addEventListener('click', () => {
                undoCallback();
                hideToast();
            });
        }
    }, 50);

    // Auto-hide after 5 seconds
    setTimeout(() => {
        hideToast();
    }, 5000);
}

function hideToast() {
    const toast = document.getElementById('toast');
    toast.classList.remove('translate-x-0', 'bg-red-500/20', 'border-l-4', 'border-red-500');
    toast.classList.add('translate-x-full');
}

// Duplicate / Clone link
async function duplicateLink(id, event) {
    if (event) event.stopPropagation();
    const link = links.find(l => l.id === id);
    if (!link) return;
    const clone = {
        id: Date.now().toString() + '_' + Math.random().toString(36).slice(2, 8),
        url: link.url,
        title: (link.title || '') + ' (copy)',
        category: link.category || 'General',
        tags: (link.tags || []).slice(),
        notes: link.notes || '',
        image: link.image || null,
        accentColor: link.accentColor || neonColors[0],
        favorite: false,
        visitCount: 0,
        createdAt: new Date().toISOString(),
        lastVisited: null,
        folderId: link.folderId || null
    };
    links.push(clone);
    await saveLinkToDB(clone);
    updateAllTags();
    renderLinks();
    renderCategoryFilters();
    showToast('Link duplicated', 'success');
}
window.duplicateLink = duplicateLink;

// Update storage stats if modal is open
async function updateStorageStatsIfOpen() {
    if (!document.getElementById('storageModal').classList.contains('hidden')) {
        await updateStorageStats();
    }
}

// ==================== Prompt Management ====================

// Render prompts
function renderPrompts() {
    const container = document.getElementById('promptsList');
    if (!container) return;

    if (prompts.length === 0) {
        container.innerHTML = '<p class="text-sm text-gray-500 text-center py-4">No prompts yet. Click "Add Prompt" to create one.</p>';
        return;
    }

    container.innerHTML = prompts.map(prompt => `
        <div class="glass-card p-3 flex items-start justify-between group">
            <div class="flex-1">
                <h4 class="text-white font-semibold mb-1">${escapeHtml(prompt.title)}</h4>
                <p class="text-gray-400 text-sm line-clamp-2">${escapeHtml(prompt.content)}</p>
                <div class="flex items-center gap-2 mt-2">
                    <span class="text-xs px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300">${escapeHtml(prompt.category)}</span>
                    <span class="text-xs text-gray-500">${new Date(prompt.createdAt).toLocaleDateString()}</span>
                </div>
            </div>
            <div class="flex gap-2 ml-3 opacity-0 group-hover:opacity-100 transition-opacity">
                <button 
                    onclick="openPromptModal('${prompt.id}')" 
                    class="p-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 transition-all"
                    title="Edit"
                >
                    <i data-lucide="edit" class="w-4 h-4"></i>
                </button>
                <button 
                    onclick="copyPrompt('${prompt.id}')" 
                    class="p-2 rounded-lg bg-blue-500/20 hover:bg-blue-500/30 text-blue-300 transition-all"
                    title="Copy"
                >
                    <i data-lucide="copy" class="w-4 h-4"></i>
                </button>
                <button 
                    onclick="deletePrompt('${prompt.id}')" 
                    class="p-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 transition-all"
                    title="Delete"
                >
                    <i data-lucide="trash-2" class="w-4 h-4"></i>
                </button>
            </div>
        </div>
    `).join('');

    initializeIcons();
}

// Open prompt modal
function openPromptModal(promptId = null) {
    editingPromptId = promptId;
    const modal = document.getElementById('promptModal');
    const modalTitle = document.getElementById('promptModalTitle');

    if (promptId) {
        const prompt = prompts.find(p => p.id === promptId);
        if (prompt) {
            modalTitle.textContent = 'Edit Prompt';
            document.getElementById('promptTitle').value = prompt.title;
            document.getElementById('promptContent').value = prompt.content;
            document.getElementById('promptCategory').value = prompt.category;
        }
    } else {
        modalTitle.textContent = 'Add New Prompt';
        document.getElementById('promptForm').reset();
    }

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    setTimeout(() => {
        document.getElementById('promptTitle').focus();
    }, 100);
    initializeIcons();
}

// Close prompt modal
function closePromptModal() {
    const modal = document.getElementById('promptModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
    document.getElementById('promptForm').reset();
    editingPromptId = null;
}

// Handle prompt form submission
async function handlePromptSubmit(e) {
    e.preventDefault();

    const title = document.getElementById('promptTitle').value.trim();
    const content = document.getElementById('promptContent').value.trim();
    const category = document.getElementById('promptCategory').value;

    if (!title || !content) {
        showToast('Title and content are required', 'error');
        return;
    }

    if (editingPromptId) {
        const promptIndex = prompts.findIndex(p => p.id === editingPromptId);
        if (promptIndex !== -1) {
            prompts[promptIndex] = {
                ...prompts[promptIndex],
                title,
                content,
                category,
                updatedAt: new Date().toISOString()
            };
            await savePromptToDB(prompts[promptIndex]);
            showToast('Prompt updated successfully!', 'success');
        }
    } else {
        const newPrompt = {
            id: Date.now().toString(),
            title,
            content,
            category,
            createdAt: new Date().toISOString(),
            updatedAt: null
        };
        prompts.push(newPrompt);
        await savePromptToDB(newPrompt);
        showToast('Prompt added successfully!', 'success');

        // Track in Cognitive Timeline
        if (window.trackCognitiveEvent) {
            window.trackCognitiveEvent('prompt_saved', newPrompt.id, newPrompt.title, `Saved prompt: ${newPrompt.content.substring(0, 100)}`, null);
        }
    }

    renderPrompts();
    closePromptModal();
    await updateStorageStatsIfOpen();
}

// Delete prompt
async function deletePrompt(id) {
    if (!confirm('Are you sure you want to delete this prompt?')) {
        return;
    }

    prompts = prompts.filter(p => p.id !== id);
    await deletePromptFromDB(id);
    renderPrompts();
    await updateStorageStatsIfOpen();
    showToast('Prompt deleted successfully', 'success');
}

// Copy prompt to clipboard
function copyPrompt(id) {
    const prompt = prompts.find(p => p.id === id);
    if (prompt) {
        navigator.clipboard.writeText(prompt.content).then(() => {
            showToast('Prompt copied to clipboard!', 'success');
        }).catch(() => {
            showToast('Failed to copy prompt', 'error');
        });
    }
}

// ==================== Browser Bookmarks Import ====================

// Close browser import modal
function closeBrowserImport() {
    document.getElementById('browserImportModal').classList.add('hidden');
    document.body.style.overflow = '';
    document.getElementById('browserBookmarksFile').value = '';
    const progressDiv = document.getElementById('browserImportProgress');
    if (progressDiv) progressDiv.classList.add('hidden');
}

// Parse browser bookmarks HTML
function parseBrowserBookmarks(htmlContent) {
    const parser = new DOMParser();
    const doc = parser.parseFromString(htmlContent, 'text/html');
    const bookmarks = [];
    const folders = [];

    // Parse DL/DT/DD structure (Netscape bookmark format)
    function parseBookmarkList(dlElement, parentFolder = '') {
        if (!dlElement) return;

        const children = Array.from(dlElement.children);
        let currentFolder = parentFolder;

        for (let i = 0; i < children.length; i++) {
            const child = children[i];

            if (child.tagName === 'DT') {
                const h3 = child.querySelector('H3');
                const a = child.querySelector('A');

                if (h3) {
                    // It's a folder
                    currentFolder = parentFolder ? `${parentFolder}/${h3.textContent.trim()}` : h3.textContent.trim();
                    folders.push(currentFolder);

                    // Parse nested bookmarks
                    const nestedDL = child.querySelector('DL');
                    if (nestedDL) {
                        parseBookmarkList(nestedDL, currentFolder);
                    }
                } else if (a) {
                    // It's a bookmark
                    const url = a.getAttribute('HREF') || '';
                    const title = a.textContent.trim() || url;
                    const addDate = a.getAttribute('ADD_DATE');
                    const icon = a.getAttribute('ICON');

                    if (url && url.startsWith('http')) {
                        bookmarks.push({
                            url,
                            title,
                            category: currentFolder || 'Imported',
                            addDate: addDate ? new Date(parseInt(addDate) * 1000).toISOString() : new Date().toISOString(),
                            icon
                        });
                    }
                }
            }
        }
    }

    const dl = doc.querySelector('DL');
    if (dl) {
        parseBookmarkList(dl);
    }

    return bookmarks;
}

// Detect browser from bookmarks HTML (Chrome, Firefox, Edge, Safari use Netscape format)
function detectBrowserFromBookmarks(htmlContent) {
    const head = (htmlContent || '').slice(0, 800).toLowerCase();
    if (head.includes('mozilla firefox') || head.includes('firefox')) return 'Firefox';
    if (head.includes('msedge') || head.includes('microsoft edge')) return 'Edge';
    if (head.includes('safari') && head.includes('apple')) return 'Safari';
    if (head.includes('chrome') || head.includes('google chrome')) return 'Chrome';
    if (head.includes('netscape') || head.includes('bookmark')) return 'Netscape';
    return 'Browser';
}

// Start browser import
async function startBrowserImport() {
    const fileInput = document.getElementById('browserBookmarksFile');
    const file = fileInput.files[0];

    if (!file) {
        showToast('Please select a bookmarks file', 'error');
        return;
    }

    const progressDiv = document.getElementById('browserImportProgress');
    const progressBar = document.getElementById('browserImportProgressBar');
    const progressText = document.getElementById('browserImportProgressText');
    const importBtn = document.getElementById('startBrowserImport');

    if (progressDiv) progressDiv.classList.remove('hidden');
    if (importBtn) importBtn.disabled = true;

    try {
        const text = await file.text();
        const bookmarks = parseBrowserBookmarks(text);
        const detected = detectBrowserFromBookmarks(text);

        if (bookmarks.length === 0) {
            showToast('No bookmarks found in file', 'error');
            if (progressDiv) progressDiv.classList.add('hidden');
            if (importBtn) importBtn.disabled = false;
            return;
        }

        let imported = 0;
        let skipped = 0;

        for (let i = 0; i < bookmarks.length; i++) {
            const bookmark = bookmarks[i];

            // Check for duplicates
            if (links.some(l => l.url === bookmark.url)) {
                skipped++;
            } else {
                const newLink = {
                    id: Date.now().toString() + Math.random(),
                    url: bookmark.url,
                    title: bookmark.title,
                    category: bookmark.category,
                    tags: [],
                    notes: '',
                    image: null,
                    accentColor: neonColors[Math.floor(Math.random() * neonColors.length)],
                    favorite: false,
                    visitCount: 0,
                    createdAt: bookmark.addDate,
                    lastVisited: null
                };

                links.push(newLink);
                await saveLinkToDB(newLink);
                imported++;
            }

            // Update progress
            if (progressBar && progressText) {
                const progress = ((i + 1) / bookmarks.length) * 100;
                progressBar.style.width = `${progress}%`;
                progressText.textContent = `${Math.round(progress)}%`;
            }
        }

        updateAllTags();
        renderLinks();
        renderCategoryFilters();
        closeBrowserImport();
        showToast(`Imported ${imported} bookmark(s) from ${detected}${skipped > 0 ? ` · ${skipped} duplicates skipped` : ''}`, 'success');
    } catch (error) {
        console.error('Import error:', error);
        showToast('Error importing bookmarks', 'error');
        if (progressDiv) progressDiv.classList.add('hidden');
        if (importBtn) importBtn.disabled = false;
    }
}

// ==================== Quick Save Feature ====================

// Open quick save modal
function openQuickSave() {
    const modal = document.getElementById('quickSaveModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    setTimeout(() => {
        const urlInput = document.getElementById('quickSaveUrl');
        if (urlInput) urlInput.focus();
    }, 100);
    initializeIcons();
}

// Close quick save modal
function closeQuickSave() {
    const modal = document.getElementById('quickSaveModal');
    if (!modal) return;
    modal.classList.add('hidden');
    document.body.style.overflow = '';
    const form = document.getElementById('quickSaveForm');
    if (form) form.reset();
    const preview = document.getElementById('quickSavePreview');
    if (preview) preview.classList.add('hidden');
}

// --- Automations ---

// Pure Helper to fetch metadata (Heuristic + Favicon)
// Returns { title, description, image, favicon }
async function fetchMetadataHelper(url) {
    try {
        const urlObj = new URL(url);
        const hostname = urlObj.hostname.replace('www.', '');
        const domainParts = hostname.split('.');
        const siteName = domainParts.length >= 2 ? domainParts[domainParts.length - 2] : hostname;

        // 1. Title (Heuristic)
        const title = siteName.charAt(0).toUpperCase() + siteName.slice(1);

        // 2. Favicon (Sequential Check)
        const faviconSources = [
            `https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${encodeURIComponent(urlObj.href)}&size=64`,
            `https://icons.duckduckgo.com/ip3/${hostname}.ico`,
            `${urlObj.origin}/favicon.ico`
        ];

        let validFavicon = null;
        const tryLoad = (src) => new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(src);
            img.onerror = reject;
            img.src = src;
        });

        for (const src of faviconSources) {
            try {
                await tryLoad(src);
                validFavicon = src;
                break;
            } catch (e) { }
        }

        return {
            title: title,
            favicon: validFavicon,
            image: validFavicon, // Use favicon as cover image fallback if no OG image
            description: url // Simple description
        };
    } catch (e) {
        return { title: url, favicon: null, image: null, description: '' };
    }
}

// Smart Categorization – single source: URL + title → LINK_CATEGORIES
function getAutoCategory(url, title) {
    if (!url) return 'General';
    const text = ((url || '') + ' ' + (title || '')).toLowerCase();
    let hostname = '';
    try {
        hostname = new URL(url).hostname.replace('www.', '').toLowerCase();
    } catch (e) {
        hostname = String(url).toLowerCase();
    }

    // Domain-first rules (higher priority)
    const domainMap = {
        'Social': /facebook|twitter|x\.com|instagram|linkedin|tiktok|reddit|discord|snapchat|threads|pinterest|tumblr|mastodon|bluesky/,
        'Entertainment': /youtube|vimeo|twitch|netflix|spotify|soundcloud|dailymotion|hulu|disneyplus|crunchyroll/,
        'Video': /youtube|vimeo|twitch|dailymotion|vimeo/,
        'Development': /github|gitlab|stackoverflow|npmjs|npm\.|codepen|jsfiddle|codesandbox|vercel|netlify|heroku|bitbucket|sourceforge/,
        'Design': /figma|dribbble|behance|canva|unsplash|pexels|adobe|sketch|framer|webflow/,
        'AI Tools': /openai|chatgpt|claude|anthropic|gemini|bard|huggingface|replicate|midjourney|stability|runway|perplexity|cohere|together\.ai/,
        'Shopping': /amazon|ebay|shopee|lazada|tiki|aliexpress|shopify|etsy|alibaba/,
        'News': /bbc|cnn|reuters|nytimes|theguardian|techcrunch|vnexpress|tuoitre|dantri|thanhnien/,
        'Article': /medium|dev\.to|substack|hashnode|ghost\.org|wordpress\.com/,
        'Reference': /docs\.|documentation|wiki|mozilla\.org|w3schools|mdn|developer\.mozilla/,
        'Learning': /udemy|coursera|edx|skillshare|duolingo|khanacademy|pluralsight|freecodecamp|codecademy|linkedin\.com\/learning/,
        'Finance': /paypal|wise|stripe|binance|coinbase|tradingview|investing|bank|revolut/,
        'Productivity': /notion|trello|asana|slack|monday|clickup|todoist|evernote|obsidian/,
        'Tools': /canva|notion|figma|miro|mural|airtable|zapier|ifttt|make\.com/
    };
    for (const [cat, regex] of Object.entries(domainMap)) {
        if (regex.test(hostname) || regex.test(text)) return cat;
    }

    // Keyword fallback (title/URL)
    const keywordMap = {
        'Social': ['social', 'community', 'forum', 'chat', 'share'],
        'Video': ['video', 'tutorial', 'stream', 'watch', 'playlist'],
        'Development': ['code', 'programming', 'api', 'dev', 'react', 'vue', 'node', 'npm', 'git'],
        'Design': ['design', 'ui', 'ux', 'font', 'color', 'icon', 'template'],
        'AI Tools': ['ai', 'llm', 'gpt', 'machine learning', 'ml'],
        'Article': ['article', 'blog', 'post', 'read'],
        'Reference': ['docs', 'documentation', 'reference', 'guide', 'howto'],
        'Learning': ['course', 'learn', 'tutorial', 'education', 'training'],
        'Shopping': ['shop', 'store', 'buy', 'cart', 'deal'],
        'News': ['news', 'headline', 'breaking'],
        'Tools': ['tool', 'converter', 'generator', 'util', 'app', 'calculator'],
        'Inspiration': ['inspiration', 'showcase', 'examples', 'ideas'],
        'Resources': ['resource', 'library', 'collection', 'curated']
    };
    for (const [cat, keywords] of Object.entries(keywordMap)) {
        if (keywords.some(k => text.includes(k))) return cat;
    }
    return 'General';
}

function autoCategorizeUrl(url, title) {
    return getAutoCategory(url, title);
}

// DOM-bound Metadata Fetcher for Quick Save Modal
async function fetchUrlMetadata() {
    const urlInput = document.getElementById('quickSaveUrl');
    if (!urlInput) return;
    const url = urlInput.value.trim();

    if (!url) return;

    try { new URL(url); } catch { return; }

    const preview = document.getElementById('quickSavePreview');
    const titleEl = document.getElementById('quickSaveTitle');
    const descEl = document.getElementById('quickSaveDescription');
    const faviconEl = document.getElementById('quickSaveFavicon');

    if (!preview || !titleEl || !descEl || !faviconEl) return;

    titleEl.textContent = 'Fetching...';
    preview.classList.remove('hidden');

    // Use shared helper
    const metadata = await fetchMetadataHelper(url);

    titleEl.textContent = metadata.title;
    descEl.textContent = metadata.description;

    if (metadata.favicon) {
        faviconEl.src = metadata.favicon;
        faviconEl.classList.remove('hidden');
    } else {
        faviconEl.classList.add('hidden');
    }
}

// Handle Quick Save (Single Link Mode)
async function handleQuickSave(e) {
    if (e) e.preventDefault();

    const urlInput = document.getElementById('quickSaveUrl');
    if (!urlInput) return;
    const url = urlInput.value.trim();

    if (!url) {
        showToast('URL is required', 'error');
        return;
    }

    // Duplicate Check
    if (links.some(l => l.url === url)) {
        if (!confirm('Link already exists. Add anyway?')) return;
    }

    const titleEl = document.getElementById('quickSaveTitle');
    const title = titleEl ? titleEl.textContent : (await fetchMetadataHelper(url)).title;

    // Auto-Categorize & Tag
    const category = autoCategorizeUrl(url, title);
    const tags = generateAutoTags({ url, title });

    const newLink = {
        id: Date.now().toString(),
        url,
        title,
        category: category,
        tags: tags,
        notes: '',
        image: null,
        accentColor: neonColors[Math.floor(Math.random() * neonColors.length)],
        favorite: false,
        visitCount: 0,
        createdAt: new Date().toISOString(),
        lastVisited: null
    };

    links.push(newLink);
    await saveLinkToDB(newLink);

    updateAllTags();
    renderLinks();
    renderCategoryFilters();
    closeQuickSave();
    showToast('Link quick-saved! ⚡', 'success');
}

// ==================== Analytics Dashboard ====================

// Open analytics modal
async function openAnalytics() {
    if (typeof Chart === 'undefined') {
        showToast('Loading Chart...', 'info');
        try {
            await loadScript('https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js');
        } catch (e) {
            showToast('Could not load Chart.', 'error');
            return;
        }
    }
    const modal = document.getElementById('analyticsModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    renderAnalytics();
    initializeIcons();
}

// Close analytics modal
function closeAnalytics() {
    const modal = document.getElementById('analyticsModal');
    if (!modal) return;
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

// Render analytics dashboard
function renderAnalytics() {
    const content = document.getElementById('analyticsContent');
    if (!content) return;
    const filteredLinks = getFilteredLinks();

    // Calculate statistics
    const totalLinks = links.length;
    const totalVisits = links.reduce((sum, link) => sum + (link.visitCount || 0), 0);
    const linksWithImages = links.filter(l => l.image).length;
    const favoriteCount = links.filter(l => l.favorite).length;

    // Category distribution
    const categoryCounts = {};
    links.forEach(link => {
        categoryCounts[link.category] = (categoryCounts[link.category] || 0) + 1;
    });

    // Tag frequency
    const tagCounts = {};
    links.forEach(link => {
        (link.tags || []).forEach(tag => {
            tagCounts[tag] = (tagCounts[tag] || 0) + 1;
        });
    });

    // Domain distribution (analytics by domain)
    const domainCounts = {};
    links.forEach(link => {
        try {
            const hostname = new URL(link.url).hostname.replace(/^www\./, '');
            domainCounts[hostname] = (domainCounts[hostname] || 0) + 1;
        } catch (e) { /* skip invalid URL */ }
    });
    const topDomains = Object.entries(domainCounts)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 15);

    // Links added over time (last 30 days)
    const last30Days = [];
    for (let i = 29; i >= 0; i--) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        const dateStr = date.toISOString().split('T')[0];
        const count = links.filter(l => l.createdAt && typeof l.createdAt === 'string' && l.createdAt.startsWith(dateStr)).length;
        last30Days.push({ date: dateStr, count });
    }

    // Most visited links
    const mostVisited = [...links].sort((a, b) => (b.visitCount || 0) - (a.visitCount || 0)).slice(0, 10);

    // Unvisited links (30+ days)
    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);
    const forgottenLinks = links.filter(l => !l.lastVisited || new Date(l.lastVisited) < thirtyDaysAgo).slice(0, 10);

    content.innerHTML = `
        <!-- Statistics Cards -->
        <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-6">
            <div class="glass-card p-4">
                <div class="text-sm text-gray-400 mb-1">Total Links</div>
                <div class="text-3xl font-bold text-white">${totalLinks}</div>
            </div>
            <div class="glass-card p-4">
                <div class="text-sm text-gray-400 mb-1">Total Visits</div>
                <div class="text-3xl font-bold text-white">${totalVisits}</div>
            </div>
            <div class="glass-card p-4">
                <div class="text-sm text-gray-400 mb-1">With Images</div>
                <div class="text-3xl font-bold text-white">${linksWithImages}</div>
            </div>
            <div class="glass-card p-4">
                <div class="text-sm text-gray-400 mb-1">Favorites</div>
                <div class="text-3xl font-bold text-white">${favoriteCount}</div>
            </div>
        </div>
        
        <!-- Charts Row -->
        <div class="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
            <div class="glass-card p-6">
                <h3 class="text-lg font-semibold text-white mb-4">Category Distribution</h3>
                <div style="position: relative; height: 300px;">
                    <canvas id="categoryChart"></canvas>
                </div>
            </div>
            <div class="glass-card p-6">
                <h3 class="text-lg font-semibold text-white mb-4">Links Added (Last 30 Days)</h3>
                <div style="position: relative; height: 300px;">
                    <canvas id="timelineChart"></canvas>
                </div>
            </div>
        </div>
        
        <!-- Top Domains (Analytics by domain) -->
        <div class="glass-card p-6 mb-6">
            <h3 class="text-lg font-semibold text-white mb-4 flex items-center gap-2"><i data-lucide="globe" class="w-5 h-5 text-cyan-400"></i> Top Domains</h3>
            <div class="space-y-2">
                ${topDomains.length > 0 ? topDomains.map(([domain, count]) => `
                    <div class="flex items-center justify-between p-2 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
                        <span class="text-gray-300 font-mono text-sm truncate flex-1">${escapeHtml(domain)}</span>
                        <span class="text-red-400 font-semibold text-sm shrink-0 ml-2">${count} link${count !== 1 ? 's' : ''}</span>
                    </div>
                `).join('') : '<p class="text-gray-500 text-sm py-2">No domains yet.</p>'}
            </div>
        </div>

        <!-- Top Tags -->
        <div class="glass-card p-6 mb-6">
            <h3 class="text-lg font-semibold text-white mb-4">Most Used Tags</h3>
            <div class="flex flex-wrap gap-2">
                ${Object.entries(tagCounts)
            .sort((a, b) => b[1] - a[1])
            .slice(0, 20)
            .map(([tag, count]) => `
                        <span class="tag px-3 py-1 text-sm" style="font-size: ${Math.max(0.75, Math.min(1.2, count / 10))}rem;">
                            #${escapeHtml(tag)} <span class="text-gray-500">(${count})</span>
                        </span>
                    `).join('')}
            </div>
        </div>
        
        <!-- Most Visited Links -->
        <div class="glass-card p-6 mb-6">
            <h3 class="text-lg font-semibold text-white mb-4">Most Visited Links</h3>
            <div class="space-y-2">
                ${mostVisited.map(link => `
                    <div class="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
                        <div class="flex-1">
                            <div class="text-white font-medium">${escapeHtml(link.title)}</div>
                            <div class="text-gray-400 text-sm">${escapeHtml(link.url)}</div>
                        </div>
                        <div class="text-red-400 font-semibold">${link.visitCount || 0}</div>
                    </div>
                `).join('')}
            </div>
        </div>
        
        <!-- Forgotten Links -->
        <div class="glass-card p-6 mb-6">
            <h3 class="text-lg font-semibold text-white mb-4">Links You Might Have Forgotten</h3>
            <div class="space-y-2">
                ${forgottenLinks.length > 0 ? forgottenLinks.map(link => `
                    <div class="flex items-center justify-between p-3 rounded-lg bg-white/5 hover:bg-white/10 transition-colors">
                        <div class="flex-1">
                            <div class="text-white font-medium">${escapeHtml(link.title)}</div>
                            <div class="text-gray-400 text-sm">${escapeHtml(link.url)}</div>
                        </div>
                        <button onclick="visitLink('${escapeHtml(link.url)}', '${link.id}', event)" class="px-3 py-1 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 text-sm transition-colors">
                            Visit
                        </button>
                    </div>
                `).join('') : '<p class="text-gray-400 text-center py-4">All links have been visited recently!</p>'}
            </div>
        </div>

        <!-- Phase 3: Insights & Activity -->
        <div class="glass-card p-6 mb-6">
            <h3 class="text-lg font-semibold text-white mb-4 flex items-center gap-2"><i data-lucide="lightbulb" class="w-5 h-5 text-red-400"></i> Insights</h3>
            <div class="space-y-2 text-sm text-gray-300">
                ${totalLinks > 0 ? `
                <p>• You have <strong class="text-white">${Object.keys(categoryCounts).length}</strong> categories. ${Object.keys(categoryCounts).length > 5 ? 'Consider using folders to group them.' : ''}</p>
                <p>• <strong class="text-white">${mostVisited.length ? mostVisited[0].title : '—'}</strong> is your most visited link (${mostVisited.length ? mostVisited[0].visitCount : 0} visits).</p>
                <p>• ${forgottenLinks.length > 0 ? `${forgottenLinks.length} link(s) not visited in 30+ days.` : 'You\'ve been visiting your links regularly!'}</p>
                ` : '<p>Add links to see insights.</p>'}
            </div>
        </div>
        <div class="glass-card p-6">
            <h3 class="text-lg font-semibold text-white mb-4 flex items-center gap-2"><i data-lucide="activity" class="w-5 h-5 text-cyan-400"></i> Recent Activity</h3>
            <div class="space-y-2">
                ${[...links].sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt)).slice(0, 10).map(link => `
                    <div class="flex items-center justify-between p-2 rounded-lg bg-white/5 text-sm">
                        <span class="text-gray-300 truncate flex-1">${escapeHtml(link.title)}</span>
                        <span class="text-gray-500 text-xs shrink-0">${new Date(link.createdAt).toLocaleDateString()}</span>
                    </div>
                `).join('') || '<p class="text-gray-500 text-sm">No activity yet.</p>'}
            </div>
        </div>
    `;

    // Initialize charts
    setTimeout(() => {
        initializeAnalyticsCharts(categoryCounts, last30Days);
    }, 100);
}

// Initialize analytics charts
function initializeAnalyticsCharts(categoryCounts, timelineData) {
    // Destroy existing charts if they exist
    if (window.categoryChartInstance) {
        window.categoryChartInstance.destroy();
    }
    if (window.timelineChartInstance) {
        window.timelineChartInstance.destroy();
    }

    // Category distribution chart
    const categoryCtx = document.getElementById('categoryChart');
    if (categoryCtx && typeof Chart !== 'undefined') {
        window.categoryChartInstance = new Chart(categoryCtx, {
            type: 'doughnut',
            data: {
                labels: Object.keys(categoryCounts),
                datasets: [{
                    data: Object.values(categoryCounts),
                    backgroundColor: [
                        'rgba(139, 92, 246, 0.8)',
                        'rgba(185, 28, 28, 0.8)',
                        'rgba(239, 68, 68, 0.8)',
                        'rgba(16, 185, 129, 0.8)',
                        'rgba(239, 68, 68, 0.8)',
                        'rgba(239, 68, 68, 0.8)',
                    ]
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        top: 10,
                        bottom: 10,
                        left: 10,
                        right: 10
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#fff',
                            padding: 10,
                            font: {
                                size: 12
                            }
                        },
                        position: 'bottom'
                    }
                }
            }
        });
    }

    // Timeline chart
    const timelineCtx = document.getElementById('timelineChart');
    if (timelineCtx && typeof Chart !== 'undefined') {
        window.timelineChartInstance = new Chart(timelineCtx, {
            type: 'line',
            data: {
                labels: timelineData.map(d => new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })),
                datasets: [{
                    label: 'Links Added',
                    data: timelineData.map(d => d.count),
                    borderColor: 'rgba(139, 92, 246, 1)',
                    backgroundColor: 'rgba(139, 92, 246, 0.1)',
                    tension: 0.4,
                    fill: true,
                    pointRadius: 4,
                    pointHoverRadius: 6
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                layout: {
                    padding: {
                        top: 10,
                        bottom: 10,
                        left: 10,
                        right: 10
                    }
                },
                plugins: {
                    legend: {
                        labels: {
                            color: '#fff',
                            font: {
                                size: 12
                            }
                        },
                        display: true
                    }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        ticks: {
                            color: '#fff',
                            stepSize: 1
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)',
                            drawBorder: false
                        }
                    },
                    x: {
                        ticks: {
                            color: '#fff',
                            maxRotation: 45,
                            minRotation: 45
                        },
                        grid: {
                            color: 'rgba(255, 255, 255, 0.1)',
                            drawBorder: false
                        }
                    }
                }
            }
        });
    }
}

// Make prompt functions globally available
window.openPromptModal = openPromptModal;
window.deletePrompt = deletePrompt;
window.copyPrompt = copyPrompt;

// Toggle favorite
async function toggleFavorite(id, event = null) {
    if (event) event.stopPropagation();
    const link = links.find(l => l.id === id);
    if (link) {
        link.favorite = !link.favorite;
        await saveSingleLink(link);
        renderLinks();
        showToast(link.favorite ? 'Added to favorites' : 'Removed from favorites', 'success');
    }
}

// Copy link to clipboard
function copyLink(url, event = null) {
    if (event) event.stopPropagation();
    navigator.clipboard.writeText(url).then(() => {
        showToast('Link copied to clipboard!', 'success');
    }).catch(() => {
        showToast('Failed to copy link', 'error');
    });
}

// Copy "Title — URL" for a link (handy for sharing or pasting into docs/notes)
function copyLinkTitleUrl(linkId, event = null) {
    if (event) event.stopPropagation();
    const link = links.find(l => l.id === linkId);
    if (!link) return;
    const text = `${link.title || ''}\n${link.url || ''}`;
    navigator.clipboard.writeText(text).then(() => {
        showToast('Title + URL copied', 'success');
    }).catch(() => {
        showToast('Failed to copy', 'error');
    });
}

// ==================== Bulk Operation Progress Bar ====================
function showBulkProgress(label) {
    const bar = document.getElementById('bulkProgress');
    if (!bar) return;
    bar.classList.remove('hidden');
    const fill = document.getElementById('bulkProgressFill');
    if (fill) fill.style.width = '0%';
    const lbl = document.getElementById('bulkProgressLabel');
    if (lbl) lbl.textContent = label || 'Processing…';
}

function updateBulkProgress(current, total, label) {
    const fill = document.getElementById('bulkProgressFill');
    if (fill) fill.style.width = Math.min(100, Math.round((current / Math.max(1, total)) * 100)) + '%';
    const lbl = document.getElementById('bulkProgressLabel');
    if (lbl && label != null) lbl.textContent = label;
}

function hideBulkProgress() {
    const bar = document.getElementById('bulkProgress');
    if (!bar) return;
    bar.classList.add('hidden');
}

// Toggle favorites filter
function toggleFavorites() {
    showFavoritesOnly = !showFavoritesOnly;
    const btn = document.getElementById('showFavoritesBtn');
    if (showFavoritesOnly) {
        btn.classList.add('active');
        btn.style.background = 'rgba(251, 191, 36, 0.3)';
        btn.style.borderColor = 'rgba(251, 191, 36, 0.5)';
    } else {
        btn.classList.remove('active');
        btn.style.background = '';
        btn.style.borderColor = '';
    }
    renderLinks();
}

// Toggle link selection for bulk delete
function toggleLinkSelection(id, event = null) {
    if (event) event.stopPropagation();
    if (selectedLinks.has(id)) {
        selectedLinks.delete(id);
    } else {
        selectedLinks.add(id);
    }
    updateBulkActionUI();
    renderLinks();
}

// Update Bulk Action UI
function updateBulkActionUI() {
    // Bulk actions live in the floating action bar — keep its counter in sync.
    const countEl = document.getElementById('selectedCount');
    if (countEl) countEl.textContent = batchSelectedLinks.size;
    if (typeof updateFloatingBar === 'function') updateFloatingBar();
}

// Select All Links (Toggle)
function selectAllLinks() {
    if (!isSelectionMode) return;

    // Get current context links
    const targetLinks = (typeof currentFilteredLinks !== 'undefined' && currentFilteredLinks.length > 0)
        ? currentFilteredLinks
        : getFilteredLinks();

    if (targetLinks.length === 0) return;

    // Check if all are currently selected
    const allSelected = targetLinks.every(link => batchSelectedLinks.has(link.id));

    if (allSelected) {
        // Deselect all
        targetLinks.forEach(link => batchSelectedLinks.delete(link.id));
        showToast('Deselected all links', 'info');
    } else {
        // Select all
        targetLinks.forEach(link => batchSelectedLinks.add(link.id));
        showToast(`Selected ${targetLinks.length} links`, 'success');
    }

    updateBulkActionUI();
    updateFloatingBar(); // Sync bottom floating bar
    renderLinks(); // Re-render to show checks
}

// Bulk Auto Tag
async function bulkAutoTag() {
    if (batchSelectedLinks.size === 0) return;

    const count = batchSelectedLinks.size;
    if (!confirm(`Auto-generate tags for ${count} selected link(s)?`)) return;

    let updatedCount = 0;

    for (const id of batchSelectedLinks) {
        const link = links.find(l => l.id === id);
        if (link) {
            // Generate new smart tags
            const newTags = generateAutoTags(link);

            // Merge with existing logic: ensure uniqueness
            const existingTags = new Set(link.tags || []);
            newTags.forEach(tag => existingTags.add(tag));

            link.tags = Array.from(existingTags);
            await saveSingleLink(link);
            updatedCount++;
        }
    }

    updateAllTags();
    renderLinks();
    showToast(`✨ Auto-tagged ${updatedCount} links!`, 'success');

    initializeIcons();
}

// Select All Links

// Helper: get image URL for a link (screenshot or favicon), same logic as edit modal
function getImageUrlForLink(link) {
    let targetUrl = (link.url || '').trim();
    if (!targetUrl) return Promise.resolve('');
    if (!/^https?:\/\//i.test(targetUrl)) targetUrl = 'https://' + targetUrl;
    try {
        new URL(targetUrl);
    } catch (e) {
        return Promise.resolve('');
    }
    const faviconUrl = 'https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=' + encodeURIComponent(targetUrl) + '&size=256';
    const screenshotUrl = 'https://s.wordpress.com/mshots/v1/' + encodeURIComponent(targetUrl) + '?w=400&h=300';
    return new Promise(function (resolve) {
        const img = new Image();
        const t = setTimeout(function () { resolve(faviconUrl); }, 8000);
        img.onload = function () { clearTimeout(t); resolve(screenshotUrl); };
        img.onerror = function () { clearTimeout(t); resolve(faviconUrl); };
        img.src = screenshotUrl;
    });
}

// Bulk auto-load images for all selected links (Magic Enchant Images) – auto-save, no manual Save
async function bulkAutoLoadImages() {
    if (batchSelectedLinks.size === 0) {
        showToast('Select at least one link.', 'info');
        return;
    }
    const ids = Array.from(batchSelectedLinks);
    const total = ids.length;
    if (!confirm('Auto-load images for ' + total + ' selected links? Images will be updated and saved automatically.')) return;

    let done = 0;
    for (let i = 0; i < ids.length; i++) {
        const link = links.find(function (l) { return l.id === ids[i]; });
        if (!link) continue;
        const url = await getImageUrlForLink(link);
        if (url) {
            link.image = url;
            await saveLinkToDB(link);
        }
        done++;
        if (i % 3 === 0 || i === ids.length - 1) {
            await new Promise(function (r) { requestAnimationFrame(r); });
            if (window.showToast) showToast('Loading images ' + done + '/' + total + '...', 'info');
        }
    }
    renderLinks();
    if (window.showToast) showToast('Updated images for ' + done + ' links.', 'success');
    if (window.initializeIcons) initializeIcons();
}
window.bulkAutoLoadImages = bulkAutoLoadImages;

// Bulk delete (with Undo)
async function bulkDelete() {
    if (selectedLinks.size === 0) return;
    const count = selectedLinks.size;
    if (confirm(`Delete ${count} selected link(s)?`)) {
        const idsToDelete = Array.from(selectedLinks);
        const deletedLinksBackup = links.filter(l => selectedLinks.has(l.id)).map(l => ({ ...l }));

        links = links.filter(link => !selectedLinks.has(link.id));
        selectedLinks.clear();

        for (const id of idsToDelete) {
            await deleteLinkFromDB(id);
        }

        updateBulkActionUI();
        renderLinks();
        renderCategoryFilters();
        updateStorageStatsIfOpen();

        showUndoToast(`${count} link(s) deleted`, async () => {
            for (const link of deletedLinksBackup) {
                links.push(link);
                await saveLinkToDB(link);
            }
            renderLinks();
            renderCategoryFilters();
            updateStorageStatsIfOpen();
            showToast('Links restored.', 'success');
        });
    }
}

// Helper to strip default/empty values for smaller file size
function minifyLinkData(link) {
    const minified = { ...link };

    // Remove defaults to save space (Import must handle defaults!)
    if (!minified.visitCount) delete minified.visitCount;
    if (minified.favorite === false) delete minified.favorite;
    if (minified.pinned === false) delete minified.pinned;
    if (minified.isRead === false) delete minified.isRead;
    if (!minified.image) delete minified.image;
    if (!minified.notes) delete minified.notes;
    if (!minified.folderId) delete minified.folderId;
    if (!minified.category || minified.category === 'General') delete minified.category;
    if (minified.tags && minified.tags.length === 0) delete minified.tags;

    // Round dates? No, keep precision for sync
    return minified;
}

// Export links as Excel file with embedded images using ExcelJS (lazy-loaded)
async function exportLinks() {
    if (typeof ExcelJS === 'undefined') {
        showToast('Loading Excel library...', 'info');
        try {
            await loadScript('https://cdnjs.cloudflare.com/ajax/libs/exceljs/4.4.0/exceljs.min.js');
        } catch (e) {
            showToast('Could not load the Excel library.', 'error');
            return;
        }
        return exportLinks();
    }

    // Detect mobile for optimization
    const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);

    // For very large datasets on mobile, recommend JSON instead
    if (isMobile && links.length > 500) {
        if (!confirm(`You have ${links.length} links. Excel export may be slow on mobile.\n\nWould you like to continue? (Tap Cancel to use faster JSON export)`)) {
            exportLinksAsJSON();
            return;
        }
    }

    showToast('Generating backup... ⏳', 'info');

    // Use setTimeout to allow toast to render before heavy processing
    await new Promise(r => setTimeout(r, 100));

    try {
        const workbook = new ExcelJS.Workbook();
        workbook.creator = 'LinkLumina';
        workbook.created = new Date();

        // 1. LINKS Sheet - Optimized columns (no ImageData on mobile)
        const linksSheet = workbook.addWorksheet('Links');

        // Reduced columns for smaller file
        const baseColumns = [
            { header: 'ID', key: 'id', width: 12 },
            { header: 'URL', key: 'url', width: 35 },
            { header: 'Title', key: 'title', width: 25 },
            { header: 'Category', key: 'category', width: 12 },
            { header: 'Tags', key: 'tags', width: 18 },
            { header: 'Notes', key: 'notes', width: 25 },
            { header: 'Fav', key: 'favorite', width: 5 },
            { header: 'Visits', key: 'visitCount', width: 6 },
            { header: 'Created', key: 'createdAt', width: 12 },
            { header: 'Folder', key: 'folderId', width: 12 }
        ];

        // Only include ImageData column on desktop (major size savings)
        if (!isMobile) {
            baseColumns.push({ header: 'ImageData', key: 'imageData', width: 0 });
        }

        linksSheet.columns = baseColumns;

        // Simpler header styling (less XML bloat)
        const headerRow = linksSheet.getRow(1);
        headerRow.font = { bold: true };
        headerRow.fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFd4af37' } };

        // Add links data (yield every 80 rows to keep UI responsive)
        const YIELD_EVERY = 80;
        for (let i = 0; i < links.length; i++) {
            if (i > 0 && i % YIELD_EVERY === 0) await new Promise(r => requestAnimationFrame(r));
            const link = links[i];
            const rowData = {
                id: link.id,
                url: link.url,
                title: link.title || '',
                createdAt: new Date(link.createdAt).toISOString().split('T')[0],
            };
            if (link.category && link.category !== 'General') rowData.category = link.category;
            if (link.tags && link.tags.length > 0) rowData.tags = link.tags.join(',');
            if (link.notes) rowData.notes = link.notes.substring(0, 25000);
            if (link.favorite) rowData.favorite = '★';
            if (link.visitCount > 0) rowData.visitCount = link.visitCount;
            if (link.folderId) rowData.folderId = link.folderId;
            if (!isMobile && link.image) rowData.imageData = link.image;
            linksSheet.addRow(rowData);
        }

        // 2. PROMPTS Sheet (Optimized)
        if (prompts && prompts.length > 0) {
            const promptsSheet = workbook.addWorksheet('Prompts');
            promptsSheet.columns = [
                { header: 'ID', key: 'id', width: 15 },
                { header: 'Title', key: 'title', width: 30 },
                { header: 'Content', key: 'content', width: 60 },
                { header: 'Category', key: 'category', width: 15 },
                { header: 'Created', key: 'createdAt', width: 15 },
                { header: 'Tags', key: 'tags', width: 20 }
            ];
            promptsSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
            promptsSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFb91c1c' } };

            prompts.forEach(p => {
                const rowData = {
                    id: p.id,
                    title: p.title,
                    content: p.content,
                    createdAt: p.createdAt ? new Date(p.createdAt).toISOString() : ''
                };
                if (p.category && p.category !== 'General') rowData.category = p.category;
                if (p.tags && p.tags.length > 0) rowData.tags = p.tags.join(', ');
                promptsSheet.addRow(rowData);
            });
        }

        // 3. FOLDERS Sheet
        try {
            const allFolders = window.folders || [];
            if (allFolders.length > 0) {
                const foldersSheet = workbook.addWorksheet('Folders');
                foldersSheet.columns = [
                    { header: 'ID', key: 'id', width: 15 },
                    { header: 'Name', key: 'name', width: 30 },
                    { header: 'Color', key: 'color', width: 15 },
                    { header: 'ParentID', key: 'parentId', width: 15 },
                    { header: 'Created', key: 'createdAt', width: 15 }
                ];
                foldersSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
                foldersSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF10b981' } };

                allFolders.forEach(f => {
                    foldersSheet.addRow({
                        id: f.id,
                        name: f.name,
                        color: f.color || '',
                        parentId: f.parentId || '',
                        createdAt: f.createdAt ? new Date(f.createdAt).toISOString() : ''
                    });
                });
            }
        } catch (e) { console.log('Error adding folders sheet', e); }

        // 4. NOTES Sheet
        try {
            const allNotes = window.notes || [];
            if (allNotes.length > 0) {
                const notesSheet = workbook.addWorksheet('Notes');
                notesSheet.columns = [
                    { header: 'ID', key: 'id', width: 15 },
                    { header: 'Title', key: 'title', width: 30 },
                    { header: 'Content', key: 'content', width: 60 },
                    { header: 'Created', key: 'createdAt', width: 15 },
                    { header: 'Tags', key: 'tags', width: 20 }
                ];
                notesSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
                notesSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFf59e0b' } };

                allNotes.forEach(n => {
                    notesSheet.addRow({
                        id: n.id,
                        title: n.title,
                        content: n.content,
                        createdAt: n.createdAt ? new Date(n.createdAt).toISOString() : '',
                        tags: (n.tags || []).join(', ')
                    });
                });
            }
        } catch (e) { console.log('Error adding notes sheet', e); }

        // 5. COLORS Sheet
        try {
            const allColors = window.colors || [];
            if (allColors.length > 0) {
                const colorsSheet = workbook.addWorksheet('Colors');
                colorsSheet.columns = [
                    { header: 'ID', key: 'id', width: 15 },
                    { header: 'Name', key: 'name', width: 20 },
                    { header: 'Hex', key: 'hex', width: 15 },
                    { header: 'Created', key: 'createdAt', width: 15 }
                ];
                colorsSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
                colorsSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFe879f9' } };

                allColors.forEach(c => {
                    colorsSheet.addRow({
                        id: c.id,
                        name: c.name || '',
                        hex: c.hex || c.value || '',
                        createdAt: c.createdAt ? new Date(c.createdAt).toISOString() : ''
                    });
                });
            }
        } catch (e) { console.log('Error adding colors sheet', e); }

        // 6. TIMELINE Sheet
        try {
            const allTimeline = window.timelineEvents || [];
            if (allTimeline.length > 0) {
                const timelineSheet = workbook.addWorksheet('Timeline');
                timelineSheet.columns = [
                    { header: 'ID', key: 'id', width: 15 },
                    { header: 'Type', key: 'type', width: 15 },
                    { header: 'Title', key: 'title', width: 30 },
                    { header: 'Description', key: 'description', width: 40 },
                    { header: 'Timestamp', key: 'timestamp', width: 20 },
                    { header: 'SourceID', key: 'sourceId', width: 15 },
                    { header: 'Context', key: 'context', width: 50 }
                ];
                timelineSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
                timelineSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF3b82f6' } };

                allTimeline.forEach(t => {
                    timelineSheet.addRow({
                        id: t.id,
                        type: t.type || t.eventType || '',
                        title: t.title || '',
                        description: t.description || '',
                        timestamp: t.timestamp ? new Date(t.timestamp).toISOString() : '',
                        sourceId: t.sourceId || '',
                        context: t.context ? JSON.stringify(t.context) : ''
                    });
                });
            }
        } catch (e) { console.log('Error adding timeline sheet', e); }

        // 7. SNIPPETS Sheet
        try {
            const allSnippets = window.snippets || [];
            if (allSnippets.length > 0) {
                const snippetsSheet = workbook.addWorksheet('Snippets');
                snippetsSheet.columns = [
                    { header: 'ID', key: 'id', width: 15 },
                    { header: 'Title', key: 'title', width: 30 },
                    { header: 'Code', key: 'code', width: 60 },
                    { header: 'Language', key: 'language', width: 15 }
                ];
                snippetsSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
                snippetsSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF22c55e' } };

                allSnippets.forEach(s => {
                    snippetsSheet.addRow({
                        id: s.id,
                        title: s.title || '',
                        code: s.code || s.content || '',
                        language: s.language || ''
                    });
                });
            }
        } catch (e) { console.log('Error adding snippets sheet', e); }

        // 8. TODOS Sheet
        try {
            const allTodos = window.todos || [];
            if (allTodos.length > 0) {
                const todosSheet = workbook.addWorksheet('Todos');
                todosSheet.columns = [
                    { header: 'ID', key: 'id', width: 15 },
                    { header: 'Text', key: 'text', width: 50 },
                    { header: 'Completed', key: 'completed', width: 10 },
                    { header: 'Created', key: 'createdAt', width: 15 }
                ];
                todosSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
                todosSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFfbbf24' } };

                allTodos.forEach(td => {
                    todosSheet.addRow({
                        id: td.id,
                        text: td.text || td.title || '',
                        completed: td.completed ? 'Yes' : 'No',
                        createdAt: td.createdAt ? new Date(td.createdAt).toISOString() : ''
                    });
                });
            }
        } catch (e) { console.log('Error adding todos sheet', e); }

        // 9. TOOLS (Product Hunt style)
        try {
            const allTools = (window.tools && window.tools.length) ? window.tools : (typeof getAllToolsFromDB === 'function' ? await getAllToolsFromDB() : []);
            if (allTools && allTools.length > 0) {
                const toolsSheet = workbook.addWorksheet('Tools');
                toolsSheet.columns = [
                    { header: 'ID', key: 'id', width: 20 },
                    { header: 'Name', key: 'n', width: 35 },
                    { header: 'Description', key: 'd', width: 50 },
                    { header: 'URL', key: 'u', width: 45 },
                    { header: 'Created', key: 't', width: 15 }
                ];
                toolsSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
                toolsSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FFf59e0b' } };
                allTools.forEach(t => {
                    toolsSheet.addRow({
                        id: t.id,
                        n: t.n || '',
                        d: t.d || '',
                        u: t.u || '',
                        t: t.t ? new Date(t.t).toISOString() : ''
                    });
                });
            }
        } catch (e) { console.log('Error adding tools sheet', e); }

        // 10. SETTINGS
        const settingsSheet = workbook.addWorksheet('Settings');
        settingsSheet.columns = [
            { header: 'Key', key: 'key', width: 30 },
            { header: 'Value', key: 'value', width: 50 }
        ];
        settingsSheet.getRow(1).font = { bold: true, color: { argb: 'FFFFFFFF' } };
        settingsSheet.getRow(1).fill = { type: 'pattern', pattern: 'solid', fgColor: { argb: 'FF64748b' } };

        const storagePrompt = await getMetadata('storagePrompt');
        if (storagePrompt) settingsSheet.addRow({ key: 'storagePrompt', value: storagePrompt });
        settingsSheet.addRow({ key: 'schemaVersion', value: '4' });
        settingsSheet.addRow({ key: 'backupVersion', value: '4.0-full' });

        await new Promise(r => requestAnimationFrame(r));
        // Generate Excel file
        const buffer = await workbook.xlsx.writeBuffer();
        const blob = new Blob([buffer], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' });
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `linklumina-full-backup-${new Date().toISOString().split('T')[0]}.xlsx`;
        link.click();
        URL.revokeObjectURL(url);
        localStorage.setItem('linkLumina_lastExport', new Date().toISOString());
        showToast('Full Excel backup exported! 📦', 'success');
    } catch (error) {
        console.error('Export error:', error);
        showToast('Error exporting file: ' + error.message, 'error');
    }
}

// Export links as JSON (Full Backup - Optimized & Minified)
// ==================== ZIP FOLDER BACKUP (images/ + data/*.json) ====================
// Download = 1 folder: images/links/, images/tools/ + data/links.json, prompts,
// notes, colors, files, snippets, todos, folders, timeline, transcripts, tools.
const ZIP_EXPORT_VERSION = '5.0';

async function _loadJSZip() {
    if (typeof JSZip !== 'undefined') return JSZip;
    await loadScript('https://cdnjs.cloudflare.com/ajax/libs/jszip/3.10.1/jszip.min.js');
    return JSZip;
}

// Pure helpers extracted to backup-core.js (UMD — runs in both browser and Node tests).
const BackupCore = (typeof window !== "undefined" && window.BackupCore) || globalThis.BackupCore;
function _safeFilename(n) { return BackupCore.safeFilename(n); }
function _imageExt(u) { return BackupCore.imageExt(u); }
async function _tryDownloadImage(url, timeoutMs) { return BackupCore.tryDownloadImage(url, timeoutMs); }

function _blobToDataURL(blob) {
    return new Promise((res, rej) => {
        const r = new FileReader();
        r.onload = () => res(r.result);
        r.onerror = () => rej(r.error);
        r.readAsDataURL(blob);
    });
}

// Compress downloaded images: resize to maxDim + re-encode WebP/JPEG for lighter backups.
// Only handles photo images (jpg/webp/avif); png/gif/svg are kept as-is (transparency/anim/vector).
const ZIP_IMG_MAX_DIM = 640;
const ZIP_IMG_QUALITY = 0.72;

function _decodeImage(blob) {
    // Try createImageBitmap first (fast, GC-friendly), fallback to <img>+objectURL
    if (typeof createImageBitmap === 'function') {
        return createImageBitmap(blob).then(b => ({ bitmap: b, close: () => b.close() }));
    }
    return new Promise((res, rej) => {
        const url = URL.createObjectURL(blob);
        const img = new Image();
        img.onload = () => { URL.revokeObjectURL(url); res({ img }); };
        img.onerror = () => { URL.revokeObjectURL(url); rej(new Error('decode')); };
        img.src = url;
    });
}

async function _compressImage(blob, maxDim, quality) {
    // Returns { blob, outExt, compressed } — outExt 'webp' when WebP encoding succeeds
    try {
        const src = await _decodeImage(blob);
        const w = src.img ? src.img.naturalWidth : src.bitmap.width;
        const h = src.img ? src.img.naturalHeight : src.bitmap.height;
        const smallEnough = (w > 0 && h > 0) && w <= maxDim && h <= maxDim && blob.size < 60000;
        if (smallEnough || !w || !h) {
            if (src.close) src.close();
            return { blob: blob, outExt: null, compressed: false };
        }
        const scale = Math.min(1, maxDim / Math.max(w, h));
        const cw = Math.max(1, Math.round(w * scale));
        const ch = Math.max(1, Math.round(h * scale));
        const canvas = document.createElement('canvas');
        canvas.width = cw;
        canvas.height = ch;
        const ctx = canvas.getContext('2d');
        if (src.img) ctx.drawImage(src.img, 0, 0, cw, ch);
        else ctx.drawImage(src.bitmap, 0, 0, cw, ch);
        if (src.close) src.close();

        let outBlob = null;
        let outExt = null;
        if (typeof canvas.toBlob === 'function') {
            // Try WebP first (lighter), fall back to JPEG
            const webpBlob = await new Promise(r => canvas.toBlob(b => r(b), 'image/webp', quality));
            if (webpBlob && webpBlob.size > 0) { outBlob = webpBlob; outExt = 'webp'; }
            else {
                const jpgBlob = await new Promise(r => canvas.toBlob(b => r(b), 'image/jpeg', quality));
                if (jpgBlob && jpgBlob.size > 0) { outBlob = jpgBlob; outExt = 'jpg'; }
            }
        }
        // Compression doesn't help (or encoding fails) → keep the original
        if (!outBlob || outBlob.size >= blob.size * 0.9) {
            return { blob: blob, outExt: null, compressed: false };
        }
        return { blob: outBlob, outExt: outExt, compressed: true };
    } catch (e) {
        return { blob: blob, outExt: null, compressed: false };
    }
}

const ZIP_NO_COMPRESS_RE = /\.(png|gif|svg)$/i;

async function exportFolderBackup() {
    let JSZip;
    try { JSZip = await _loadJSZip(); } catch (e) { showToast('Could not load the ZIP library.', 'error'); return; }
    showToast('Packing ZIP backup...', 'info');

    const zip = new JSZip();
    const dataFolder = zip.folder('data');
    const imgLinksFolder = zip.folder('images/links');
    const imgToolsFolder = zip.folder('images/tools');

    const allFolders = window.folders || [];
    const allNotes = window.notes || [];
    const allColors = window.colors || [];
    const allSnippets = window.snippets || [];
    const allTodos = window.todos || [];
    const allFiles = window.files || [];
    const allTimeline = window.timelineEvents || [];
    const allTools = (window.tools && window.tools.length) ? window.tools : (typeof getAllToolsFromDB === 'function' ? await getAllToolsFromDB() : []);

    const minifiedLinks = links.map(minifyLinkData);
    const transcripts = [];
    minifiedLinks.forEach(l => {
        if (l.notes && l.notes.indexOf('=== VIDEO TRANSCRIPT ===') !== -1) {
            transcripts.push({ linkId: l.id, url: l.url, title: l.title, transcript: l.notes });
        }
    });

    dataFolder.file('links.json', JSON.stringify(minifiedLinks));
    dataFolder.file('prompts.json', JSON.stringify(prompts || []));
    dataFolder.file('notes.json', JSON.stringify(allNotes));
    dataFolder.file('colors.json', JSON.stringify(allColors));
    dataFolder.file('files.json', JSON.stringify(allFiles));
    dataFolder.file('snippets.json', JSON.stringify(allSnippets));
    dataFolder.file('todos.json', JSON.stringify(allTodos));
    dataFolder.file('folders.json', JSON.stringify(allFolders));
    dataFolder.file('timeline.json', JSON.stringify(allTimeline));
    dataFolder.file('tools.json', JSON.stringify(allTools));
    dataFolder.file('transcripts.json', JSON.stringify(transcripts));
    dataFolder.file('metadata.json', JSON.stringify({
        version: ZIP_EXPORT_VERSION,
        exportDate: new Date().toISOString(),
        app: 'LinkLumina',
        counts: { links: minifiedLinks.length, prompts: (prompts || []).length, tools: allTools.length, notes: allNotes.length }
    }));

    // --- Images (best-effort download, concurrency 5) ---
    const jobs = [];
    minifiedLinks.forEach((l, i) => { if (l.image) jobs.push({ item: l, field: 'image', folder: imgLinksFolder, path: 'images/links/' }); });
    allTools.forEach((t) => { if (t.img) jobs.push({ item: t, field: 'img', folder: imgToolsFolder, path: 'images/tools/' }); });
    let imgCount = 0, skipped = 0, idx = 0, savedBytes = 0, origBytes = 0, compressedCount = 0;
    const worker = async () => {
        while (idx < jobs.length) {
            const cur = jobs[idx++];
            const url = cur.item[cur.field];
            const blob = await _tryDownloadImage(url);
            if (blob) {
                let outBlob = blob;
                let outExt = _imageExt(url);
                if (!ZIP_NO_COMPRESS_RE.test(url)) {
                    const res = await _compressImage(blob, ZIP_IMG_MAX_DIM, ZIP_IMG_QUALITY);
                    if (res.compressed && res.outExt) {
                        outBlob = res.blob;
                        outExt = res.outExt;
                        compressedCount++;
                        savedBytes += blob.size - outBlob.size;
                        origBytes += blob.size;
                    }
                }
                const name = _safeFilename(cur.item.id) + '.' + outExt;
                cur.folder.file(name, outBlob);
                cur.item[cur.field] = cur.path + name;
                imgCount++;
            } else { skipped++; }
            if (idx % 25 === 0 || idx === jobs.length) {
                const toast = document.querySelector('.toast-notification.info');
                if (toast) toast.textContent = `Backup: downloading + compressing images ${idx}/${jobs.length}...`;
            }
        }
    };
    await Promise.all(Array.from({ length: Math.min(5, Math.max(1, jobs.length)) }, worker));
    // Re-write JSONs with rewritten local image paths
    dataFolder.file('links.json', JSON.stringify(minifiedLinks));
    dataFolder.file('tools.json', JSON.stringify(allTools));

    const blob = await zip.generateAsync({ type: 'blob' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `linklumina-backup-${new Date().toISOString().split('T')[0]}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(url), 2000);

    const stats = `${minifiedLinks.length} links · ${allTools.length} tools · ${imgCount} images` + (skipped ? ` · ${skipped} images failed to download` : '');
    const zipSize = (blob.size / 1024 / 1024).toFixed(2);
    const compressNote = compressedCount
        ? ` · compressed ${compressedCount} images saving ${Math.round((savedBytes / (origBytes || 1)) * 100)}%`
        : '';
    showToast(`📦 ZIP backup done: ${stats}${compressNote} (${zipSize} MB)`, 'success');
    try { localStorage.setItem('linklumina-last-backup-time', String(Date.now())); } catch (e) { }
    if (typeof updateLastBackupDate === 'function') updateLastBackupDate();
}

async function importFolderBackup(file) {
    let JSZip;
    try { JSZip = await _loadJSZip(); } catch (e) { showToast('Could not load the ZIP library.', 'error'); return; }
    showToast('Extracting ZIP backup...', 'info');

    let zip;
    try { zip = await JSZip.loadAsync(file); } catch (e) { showToast('Invalid ZIP file.', 'error'); return; }

    const data = {};
    const imageMap = new Map();
    const names = Object.keys(zip.files);
    for (const name of names) {
        const entry = zip.files[name];
        if (entry.dir) continue;
        if (name.startsWith('data/') && name.endsWith('.json')) {
            try {
                const key = name.slice(5, -5);
                data[key] = JSON.parse(await entry.async('string'));
            } catch (e) { console.warn('Skipping bad file:', name, e); }
        } else if (name.startsWith('images/')) {
            try {
                const lower = name.toLowerCase();
                const mime = BackupCore.mimeFromExt(name);
                imageMap.set(name, 'data:' + mime + ';base64,' + await entry.async('base64'));
            } catch (e) { }
        }
    }

    // Rewrite local image paths -> dataURL (saved straight into IndexedDB)
    (data.links || []).forEach(l => {
        if (l.image && l.image.startsWith('images/')) { const dl = imageMap.get(l.image); if (dl) l.image = dl; }
    });
    (data.tools || []).forEach(t => {
        if (t.img && t.img.startsWith('images/')) { const dl = imageMap.get(t.img); if (dl) t.img = dl; }
    });

    const merged = {
        version: '4.0',
        links: data.links || [],
        prompts: data.prompts || [],
        notes: data.notes || [],
        folders: data.folders || [],
        colors: data.colors || [],
        snippets: data.snippets || [],
        todos: data.todos || [],
        files: data.files || [],
        timeline: data.timeline || [],
        tools: data.tools || [],
        settings: { schemaVersion: 4 },
        exportDate: new Date().toISOString()
    };
    const fakeFile = new File([JSON.stringify(merged)], (file.name || 'backup').replace(/\.zip$/i, '.json'), { type: 'application/json' });
    await importJsonFile(fakeFile);
}

async function exportLinksAsJSON() {
    try {
        await new Promise(r => requestAnimationFrame(r));
        const storagePrompt = await getMetadata('storagePrompt') || '';

        // Gather all data stores
        const allFolders = window.folders || [];
        const allNotes = window.notes || [];
        const allColors = window.colors || [];
        const allSnippets = window.snippets || [];
        const allTodos = window.todos || [];
        const allFiles = window.files || [];
        const allTimeline = window.timelineEvents || [];
        const allTools = (window.tools && window.tools.length) ? window.tools : (typeof getAllToolsFromDB === 'function' ? await getAllToolsFromDB() : []);

        // Minify link data
        const minifiedLinks = links.map(minifyLinkData);

        const exportData = {
            // Primary Data
            links: minifiedLinks,
            prompts: prompts,
            folders: allFolders,
            notes: allNotes,

            // Extended Modules
            colors: allColors,
            snippets: allSnippets,
            todos: allTodos,
            files: allFiles,
            tools: Array.isArray(allTools) ? allTools : [],

            // Cognitive System
            timeline: allTimeline,

            // Metadata
            settings: {
                storagePrompt: storagePrompt,
                schemaVersion: 4
            },
            exportDate: new Date().toISOString(),
            version: '4.0' // Full backup version
        };

        // Minified JSON (no whitespace)
        const dataStr = JSON.stringify(exportData);

        const dataBlob = new Blob([dataStr], { type: 'application/json' });
        const url = URL.createObjectURL(dataBlob);
        const link = document.createElement('a');
        link.href = url;
        link.download = `linklumina-full-backup-${new Date().toISOString().split('T')[0]}.json`;
        link.click();
        URL.revokeObjectURL(url);

        // Calculate stats
        const toolsCount = Array.isArray(allTools) ? allTools.length : 0;
        const stats = [
            `${minifiedLinks.length} Links`,
            prompts.length ? `${prompts.length} Prompts` : null,
            allFolders.length ? `${allFolders.length} Folders` : null,
            allNotes.length ? `${allNotes.length} Notes` : null,
            allColors.length ? `${allColors.length} Colors` : null,
            toolsCount ? `${toolsCount} Tools` : null,
            allTimeline.length ? `${allTimeline.length} Timeline Events` : null
        ].filter(Boolean).join(', ');

        localStorage.setItem('linkLumina_lastExport', new Date().toISOString());
        showToast(`Full backup exported! (${stats})`, 'success');
    } catch (e) {
        console.error('Export JSON error:', e);
        showToast('Error exporting JSON: ' + e.message, 'error');
    }
}

// Escape CSV values (handle commas, quotes, newlines)
function escapeCSV(value) {
    if (value === null || value === undefined) return '';
    const stringValue = String(value);
    // If value contains comma, quote, or newline, wrap in quotes and escape quotes
    if (stringValue.includes(',') || stringValue.includes('"') || stringValue.includes('\n')) {
        return '"' + stringValue.replace(/"/g, '""') + '"';
    }
    return stringValue;
}

// Import links (supports JSON and Excel)
async function importLinks(event) {
    const file = event.target.files[0];
    if (!file) return;

    const fileName = file.name.toLowerCase();
    const isExcel = fileName.endsWith('.xlsx') || fileName.endsWith('.xls');

    if (fileName.endsWith('.zip')) {
        // ZIP folder backup (images/ + data/*.json)
        await importFolderBackup(file);
    } else if (isExcel) {
        // Handle Excel import using ExcelJS
        await importExcelFile(file);
    } else {
        // Handle JSON/CSV import
        await importJsonFile(file);
    }

    event.target.value = ''; // Reset input
}

// Import Excel File (Enhanced for Full Backup & Performance)
async function importExcelFile(file) {
    try {
        if (typeof ExcelJS === 'undefined') {
            showToast('Loading Excel library...', 'info');
            try {
                await loadScript('https://cdnjs.cloudflare.com/ajax/libs/exceljs/4.4.0/exceljs.min.js');
            } catch (e) {
                showToast('Could not load the Excel library.', 'error');
                return;
            }
            showToast('Library loaded. Click Import again.', 'success');
            return;
        }

        showToast('Reading Excel file... 📂', 'info');

        const arrayBuffer = await file.arrayBuffer();
        const workbook = new ExcelJS.Workbook();
        await workbook.xlsx.load(arrayBuffer);

        let stats = { links: 0, prompts: 0, folders: 0, notes: 0, tools: 0, skipped: 0 };

        // --- 1. Links Import (Optimized) ---
        const linksSheet = workbook.getWorksheet('Links');
        if (linksSheet) {
            console.log('Found Links sheet - utilizing full backup mode');

            // Map columns
            const headerRow = linksSheet.getRow(1);
            const colMap = {};
            headerRow.eachCell((cell, colNumber) => {
                const key = String(cell.value || '').toLowerCase().replace(/\s+/g, '');
                if (key === 'id') colMap.id = colNumber;
                if (key === 'url') colMap.url = colNumber;
                if (key === 'title') colMap.title = colNumber;
                if (key === 'category') colMap.category = colNumber;
                if (key === 'tags') colMap.tags = colNumber;
                if (key === 'notes') colMap.notes = colNumber;
                if (key === 'favorite') colMap.favorite = colNumber;
                if (key === 'imagedata') colMap.imageData = colNumber;
                if (key === 'folderid') colMap.folderId = colNumber;
            });

            // Pre-fetch existing URLs for O(1) lookup
            const existingUrls = new Set(links.map(l => l.url));

            // Extract all rows first (Synchronous extraction, but fast enough for <10k rows usually)
            const rowsAndValues = [];
            linksSheet.eachRow((row, rowNumber) => {
                if (rowNumber === 1) return;
                rowsAndValues.push({
                    url: colMap.url ? String(row.getCell(colMap.url).value || '').trim() : '',
                    row: row
                });
            });

            // Process in Chunks
            const BATCH_SIZE = 100;
            let processed = 0;
            const total = rowsAndValues.length;

            showToast(`Importing ${total} links... (0%)`, 'info');

            // Recursive function for chunk processing
            const processChunk = async (startIndex) => {
                const endIndex = Math.min(startIndex + BATCH_SIZE, total);

                for (let i = startIndex; i < endIndex; i++) {
                    const item = rowsAndValues[i];
                    if (!item.url) continue;

                    // O(1) Check
                    if (existingUrls.has(item.url)) {
                        stats.skipped++;
                        continue;
                    }

                    // Construct Link
                    const row = item.row;
                    const link = {
                        id: colMap.id ? String(row.getCell(colMap.id).value) : Date.now().toString() + Math.random(),
                        url: item.url,
                        title: colMap.title ? String(row.getCell(colMap.title).value || '') : '',
                        category: colMap.category ? String(row.getCell(colMap.category).value || 'General') : 'General',
                        tags: colMap.tags ? String(row.getCell(colMap.tags).value || '').split(',').map(t => t.trim()).filter(Boolean) : [],
                        notes: colMap.notes ? String(row.getCell(colMap.notes).value || '') : '',
                        favorite: colMap.favorite ? Boolean(row.getCell(colMap.favorite).value) : false,
                        image: colMap.imageData ? String(row.getCell(colMap.imageData).value || '') : '',
                        folderId: colMap.folderId ? String(row.getCell(colMap.folderId).value || '') : null,
                        visitCount: 0,
                        createdAt: Date.now()
                    };

                    if (!link.title) {
                        try { link.title = new URL(item.url).hostname; } catch { link.title = item.url; }
                    }

                    links.push(link);
                    existingUrls.add(link.url); // Add to Set to prevent dupes within same file
                    await saveLinkToDB(link);
                    stats.links++;
                }

                processed = endIndex;
                const percent = Math.round((processed / total) * 100);

                // Update Toast every chunk
                const toast = document.querySelector('.toast-notification.info');
                if (toast) toast.textContent = `Importing links... (${percent}%)`;

                if (processed < total) {
                    // Schedule next chunk
                    requestAnimationFrame(() => processChunk(processed));
                } else {
                    // Done with Links, proceed to other sheets
                    await processOtherSheets();
                }
            };

            // Start Link Processing
            requestAnimationFrame(() => processChunk(0));

        } else {
            // Fallback - just scan first sheet (simplified non-blocking)
            console.log('No Links sheet found - scanning first sheet for URLs');
            const worksheet = workbook.worksheets[0];
            const existingUrls = new Set(links.map(l => l.url));
            const rowsToProcess = [];

            worksheet.eachRow((row, rowNumber) => {
                if (rowNumber === 1) return;
                const cell = row.getCell(1);
                const val = String(cell.value || '').trim();
                if (val.startsWith('http')) {
                    rowsToProcess.push(val);
                }
            });

            // Simple Loop for fallback (assuming small size or just loop it)
            for (const val of rowsToProcess) {
                if (existingUrls.has(val)) { stats.skipped++; continue; }
                const link = {
                    id: Date.now() + Math.random().toString(),
                    url: val,
                    title: val,
                    category: 'Imported',
                    tags: ['excel-import'],
                    createdAt: Date.now()
                };
                links.push(link);
                existingUrls.add(val);
                await saveLinkToDB(link);
                stats.links++;
            }
            await processOtherSheets();
        }

        // Helper to process non-link sheets (usually smaller data)
        async function processOtherSheets() {
            // 2. PROMPTS
            const promptsSheet = workbook.getWorksheet('Prompts');
            if (promptsSheet) {
                promptsSheet.eachRow((row, rowNumber) => {
                    if (rowNumber === 1) return;
                    const id = String(row.getCell(1).value || Date.now());
                    const content = String(row.getCell(3).value || '');
                    if (!content) return;

                    // Simple check if prompt ID exists? For now append.
                    const prompt = {
                        id: id,
                        title: String(row.getCell(2).value || 'Untitled'),
                        content: content,
                        category: String(row.getCell(4).value || 'General'),
                        tags: String(row.getCell(6).value || '').split(',').map(t => t.trim()),
                        createdAt: Date.now()
                    };
                    prompts.push(prompt);
                    savePromptToDB(prompt);
                    stats.prompts++;
                });
            }

            // 3. FOLDERS
            const foldersSheet = workbook.getWorksheet('Folders');
            if (foldersSheet) {
                foldersSheet.eachRow((row, rowNumber) => {
                    if (rowNumber === 1) return;
                    saveFolderToDB({
                        id: String(row.getCell(1).value),
                        name: String(row.getCell(2).value),
                        color: String(row.getCell(3).value),
                        createdAt: Date.now()
                    });
                    stats.folders++;
                });
            }

            // 4. SETTINGS & Notes
            const settingsSheet = workbook.getWorksheet('Settings');
            if (settingsSheet) {
                settingsSheet.eachRow((row, rowNumber) => {
                    if (rowNumber === 1) return;
                    const key = String(row.getCell(1).value);
                    if (key) setMetadata(key, String(row.getCell(2).value));
                });
            }

            const notesSheet = workbook.getWorksheet('Notes');
            if (notesSheet) {
                notesSheet.eachRow((row, rowNumber) => {
                    if (rowNumber === 1) return;
                    saveNoteToDB({
                        id: String(row.getCell(1).value),
                        title: String(row.getCell(2).value),
                        content: String(row.getCell(3).value),
                        createdAt: Date.now(),
                        tags: String(row.getCell(5).value || '').split(',')
                    });
                    stats.notes++;
                });
            }

            // Tools sheet (id, n, d, u, t)
            const toolsSheet = workbook.getWorksheet('Tools');
            if (toolsSheet && typeof saveToolToDB === 'function') {
                const headerRow = toolsSheet.getRow(1);
                const col = {};
                headerRow.eachCell((cell, colNumber) => {
                    const k = String(cell.value || '').toLowerCase().replace(/\s+/g, '');
                    if (k === 'id') col.id = colNumber;
                    if (k === 'name' || k === 'n') col.n = col.n || colNumber;
                    if (k === 'description' || k === 'd') col.d = col.d || colNumber;
                    if (k === 'url' || k === 'u') col.u = col.u || colNumber;
                    if (k === 'created' || k === 't') col.t = col.t || colNumber;
                });
                const toolRows = [];
                toolsSheet.eachRow((row, rowNumber) => {
                    if (rowNumber === 1) return;
                    const id = col.id ? String(row.getCell(col.id).value || '').trim() : '';
                    const u = col.u ? String(row.getCell(col.u).value || '').trim() : '';
                    if (!id || !u) return;
                    toolRows.push({
                        id: id,
                        n: col.n ? String(row.getCell(col.n).value || '').trim().slice(0, 120) : '',
                        d: col.d ? String(row.getCell(col.d).value || '').trim().slice(0, 200) : '',
                        u: u.slice(0, 2048),
                        t: col.t ? (parseInt(row.getCell(col.t).value, 10) || Date.now()) : Date.now()
                    });
                });
                for (const tool of toolRows) {
                    if (!window.tools) window.tools = [];
                    window.tools.push(tool);
                    await saveToolToDB(tool);
                    stats.tools = (stats.tools || 0) + 1;
                }
            }

            finalizeImport();
        }

        function finalizeImport() {
            updateAllTags();
            renderLinks();
            if (typeof renderCategoryFilters === 'function') renderCategoryFilters();
            if (typeof renderPrompts === 'function') renderPrompts();

            const msg = [];
            if (stats.links) msg.push(`${stats.links} Links`);
            if (stats.prompts) msg.push(`${stats.prompts} Prompts`);
            if (stats.folders) msg.push(`${stats.folders} Folders`);
            if (stats.notes) msg.push(`${stats.notes} Notes`);
            if (stats.tools) msg.push(`${stats.tools} Tools`);

            if (msg.length > 0) {
                showToast(`✅ Restore Complete: ${msg.join(', ')}`, 'success');
            } else {
                showToast(`⚠️ No new data found. ${stats.skipped} duplicates skipped.`, 'warning');
            }
        }

    } catch (error) {
        console.error('Excel import error:', error);
        showToast('Error importing Excel: ' + error.message, 'error');
    }
}

// Import JSON file (Optimized)
async function importJsonFile(file) {
    await createSafetyBackupSnapshot('before-json-import');
    const reader = new FileReader();
    reader.onload = async (e) => {
        try {
            const data = JSON.parse(e.target.result);
            let stats = { links: 0, prompts: 0, folders: 0, notes: 0, tools: 0, skipped: 0 };

            showToast('Parsing JSON data...', 'info');

            // Handle Full Backup (v2.0+)
            if (data.version && data.version >= '2.0') {

                // 1. Links with Chunking
                if (data.links && Array.isArray(data.links)) {
                    const existingUrls = new Set(links.map(l => l.url));
                    const totalLinks = data.links.length;
                    const BATCH_SIZE = 200;

                    const processLinkChunk = async (startIndex) => {
                        const endIndex = Math.min(startIndex + BATCH_SIZE, totalLinks);

                        for (let i = startIndex; i < endIndex; i++) {
                            const importedLink = data.links[i];
                            if (existingUrls.has(importedLink.url)) {
                                stats.skipped++;
                                continue;
                            }

                            importedLink.id = String(importedLink.id || Date.now() + Math.random());
                            importedLink.favorite = importedLink.favorite || false;
                            importedLink.visitCount = importedLink.visitCount || 0;

                            links.push(importedLink);
                            existingUrls.add(importedLink.url);
                            await saveLinkToDB(importedLink); // This might be slow if awaited individually, but safer for DB consistency
                            stats.links++;
                        }

                        if (endIndex < totalLinks) {
                            const percent = Math.round((endIndex / totalLinks) * 100);
                            const toast = document.querySelector('.toast-notification.info');
                            if (toast) toast.textContent = `Importing links... (${percent}%)`;

                            requestAnimationFrame(() => processLinkChunk(endIndex));
                        } else {
                            // Done links, do rest
                            finishJsonImport(data, stats);
                        }
                    };

                    processLinkChunk(0);
                    return; // Early return, continued in callback
                }
            } else {
                // Legacy Import
                const legacyLinks = Array.isArray(data) ? data : (data.bookmarks || []);
                const existingUrls = new Set(links.map(l => l.url));
                for (const l of legacyLinks) {
                    if (!l.url) continue;
                    if (!existingUrls.has(l.url)) {
                        l.id = String(Date.now() + Math.random());
                        links.push(l);
                        await saveLinkToDB(l);
                        stats.links++;
                    }
                }
                finishGenericJson(stats);
                return;
            }

            // Fallback if no links array in v2 (or if links array was empty)
            finishJsonImport(data, stats);

        } catch (error) {
            console.error('JSON Import Error:', error);
            showToast('Error importing JSON: ' + error.message, 'error');
        }
    };
    reader.readAsText(file);

    // Helper: Finish importing v2+ backup (Prompts, Folders, Notes, Colors, Timeline, etc.)
    async function finishJsonImport(data, stats) {
        // 2. Prompts
        if (data.prompts && Array.isArray(data.prompts)) {
            const existingPromptIds = new Set(prompts.map(p => p.id).filter(Boolean));
            for (const p of data.prompts) {
                p.id = p.id || String(Date.now() + Math.random());
                if (existingPromptIds.has(p.id)) {
                    stats.skipped++;
                    continue;
                }
                existingPromptIds.add(p.id);
                prompts.push(p);
                if (typeof savePromptToDB === 'function') await savePromptToDB(p);
                stats.prompts++;
            }
        }

        // 3. Folders
        if (data.folders && Array.isArray(data.folders)) {
            const existingFolderIds = new Set((window.folders || []).map(f => f.id).filter(Boolean));
            for (const f of data.folders) {
                if (!f?.id || existingFolderIds.has(f.id)) {
                    stats.skipped++;
                    continue;
                }
                existingFolderIds.add(f.id);
                if (typeof saveFolderToDB === 'function') await saveFolderToDB(f);
                if (window.folders) window.folders.push(f);
                stats.folders++;
            }
        }

        // 4. Notes
        if (data.notes && Array.isArray(data.notes)) {
            const existingNoteIds = new Set((window.notes || []).map(n => n.id).filter(Boolean));
            for (const n of data.notes) {
                if (!n?.id || existingNoteIds.has(n.id)) {
                    stats.skipped++;
                    continue;
                }
                existingNoteIds.add(n.id);
                if (typeof saveNoteToDB === 'function') await saveNoteToDB(n);
                if (window.notes) window.notes.push(n);
                stats.notes++;
            }
        }

        // 5. Colors (v4.0+)
        if (data.colors && Array.isArray(data.colors)) {
            const existingIds = new Set((window.colors || []).map(c => c.id).filter(Boolean));
            for (const c of data.colors) {
                if (!c?.id || existingIds.has(c.id)) {
                    stats.skipped++;
                    continue;
                }
                existingIds.add(c.id);
                if (typeof saveToStore === 'function') await saveToStore('colors', c);
                if (window.colors) window.colors.push(c);
            }
        }

        // 6. Snippets (v4.0+)
        if (data.snippets && Array.isArray(data.snippets)) {
            const existingIds = new Set((window.snippets || []).map(s => s.id).filter(Boolean));
            for (const s of data.snippets) {
                if (!s?.id || existingIds.has(s.id)) {
                    stats.skipped++;
                    continue;
                }
                existingIds.add(s.id);
                if (typeof saveToStore === 'function') await saveToStore('snippets', s);
                if (window.snippets) window.snippets.push(s);
            }
        }

        // 7. Todos (v4.0+)
        if (data.todos && Array.isArray(data.todos)) {
            const existingIds = new Set((window.todos || []).map(td => td.id).filter(Boolean));
            for (const td of data.todos) {
                if (!td?.id || existingIds.has(td.id)) {
                    stats.skipped++;
                    continue;
                }
                existingIds.add(td.id);
                if (typeof saveToStore === 'function') await saveToStore('todos', td);
                if (window.todos) window.todos.push(td);
            }
        }

        // 8. Files (v4.0+)
        if (data.files && Array.isArray(data.files)) {
            const existingIds = new Set((window.files || []).map(f => f.id).filter(Boolean));
            for (const f of data.files) {
                if (!f?.id || existingIds.has(f.id)) {
                    stats.skipped++;
                    continue;
                }
                existingIds.add(f.id);
                if (typeof saveToStore === 'function') await saveToStore('files', f);
                if (window.files) window.files.push(f);
            }
        }

        // 9. Timeline (v4.0+)
        if (data.timeline && Array.isArray(data.timeline)) {
            const existingIds = new Set((window.timelineEvents || []).map(t => t.id).filter(Boolean));
            for (const t of data.timeline) {
                if (!t?.id || existingIds.has(t.id)) {
                    stats.skipped++;
                    continue;
                }
                existingIds.add(t.id);
                if (typeof window.saveTimelineEventToDB === 'function') await window.saveTimelineEventToDB(t);
                if (window.timelineEvents) window.timelineEvents.push(t);
            }
        }

        // 9b. Tools (v4.0+)
        if (data.tools && Array.isArray(data.tools)) {
            if (!window.tools) window.tools = [];
            const existingToolIds = new Set((window.tools || []).map(t => t.id));
            for (const t of data.tools) {
                if (!t.id || existingToolIds.has(t.id)) continue;
                existingToolIds.add(t.id);
                window.tools.push(t);
                if (typeof saveToolToDB === 'function') await saveToolToDB(t);
                stats.tools = (stats.tools || 0) + 1;
            }
        }

        // 10. Settings
        if (data.settings) {
            if (data.settings.storagePrompt) {
                await setMetadata('storagePrompt', data.settings.storagePrompt);
            }
        }

        // Finalize UI
        updateAllTags();
        renderLinks();
        if (typeof renderCategoryFilters === 'function') renderCategoryFilters();
        if (typeof renderPrompts === 'function') renderPrompts();
        if (typeof renderSidebar === 'function') renderSidebar();
        if (typeof window.updateToolsView === 'function') window.updateToolsView();

        const msg = [];
        if (stats.links) msg.push(`${stats.links} Links`);
        if (stats.prompts) msg.push(`${stats.prompts} Prompts`);
        if (stats.folders) msg.push(`${stats.folders} Folders`);
        if (stats.notes) msg.push(`${stats.notes} Notes`);
        if (stats.tools) msg.push(`${stats.tools} Tools`);

        if (msg.length > 0) {
            showToast(`✅ Full Restore Complete: ${msg.join(', ')}`, 'success');
        } else {
            showToast(`⚠️ No new data found. ${stats.skipped || 0} duplicates skipped.`, 'warning');
        }
    }

    // Helper: Finish generic/legacy JSON import
    function finishGenericJson(stats) {
        updateAllTags();
        renderLinks();
        if (typeof renderCategoryFilters === 'function') renderCategoryFilters();

        if (stats.links > 0) {
            showToast(`✅ Imported ${stats.links} links`, 'success');
        } else {
            showToast('No new links found to import', 'warning');
        }
    }
}

// ==================== Auto Tag Generation ====================


function generateAutoTags(link) {
    const tags = new Set();
    const urlStr = (link.url || '').toLowerCase();
    const title = (link.title || '').toLowerCase();

    let urlObj;
    try {
        urlObj = new URL(link.url);
    } catch {
        return ['link', 'web', 'resource'];
    }

    const hostname = urlObj.hostname.replace('www.', '');
    const domainParts = hostname.split('.');

    // 1. Core domain tag
    if (domainParts.length >= 2) {
        tags.add(domainParts[domainParts.length - 2]);
    }

    // 2. Rich domain → tag mapping (aligned with LINK_CATEGORIES)
    const domainTags = [
        [/github\.com|gitlab\.com|bitbucket/, 'code'],
        [/stackoverflow|stackexchange|codepen|jsfiddle|codesandbox/, 'programming'],
        [/youtube\.com|youtu\.be|vimeo|twitch|dailymotion/, 'video'],
        [/twitter\.com|x\.com|facebook|instagram|linkedin|tiktok|reddit|discord|pinterest/, 'social'],
        [/medium\.com|dev\.to|substack|hashnode/, 'article'],
        [/figma\.com|dribbble|behance|canva|unsplash|pexels|adobe/, 'design'],
        [/docs\.google|notion\.so|confluence/, 'document'],
        [/openai|chatgpt|claude|anthropic|huggingface|replicate|midjourney/, 'ai'],
        [/udemy|coursera|edx|skillshare|khanacademy|freecodecamp|pluralsight/, 'learning'],
        [/amazon|ebay|shopee|lazada|tiki|aliexpress|shopify/, 'shopping'],
        [/npmjs\.com|npm\./, 'npm'],
        [/vercel|netlify|heroku|railway/, 'hosting'],
        [/stripe|paypal|wise|binance|coinbase/, 'finance'],
        [/trello|asana|monday|clickup|todoist/, 'productivity'],
        [/w3schools|mdn|mozilla\.org\/.*docs/, 'reference']
    ];
    domainTags.forEach(([regex, tag]) => {
        if (regex.test(hostname)) tags.add(tag);
    });

    // 3. Path analysis: meaningful words from path
    const pathWords = urlObj.pathname.split(/[\/\-_]/);
    const stopWords = new Set(['the', 'a', 'in', 'of', 'and', 'for', 'to', 'at', 'by', 'on', 'with', 'index', 'html', 'php', 'aspx', 'jsp', 'id', 'item', 'article', 'post', 'blog', 'news', 'page', 'tag', 'category', 'author', 'page', 'p', 'v', 'api', 'www']);
    pathWords.forEach(word => {
        const clean = word.replace(/[^a-z0-9]/g, '');
        if (clean.length > 2 && isNaN(clean) && !stopWords.has(clean)) tags.add(clean);
    });

    // 4. Title keywords (content type / intent)
    const titleKeywords = ['tutorial', 'guide', 'review', 'howto', 'learn', 'course', 'example', 'demo', 'documentation', 'api', 'cheatsheet', 'reference', 'template', 'boilerplate', 'starter', 'library', 'framework', 'tool', 'generator', 'converter', 'inspiration', 'showcase'];
    titleKeywords.forEach(kw => { if (title.includes(kw)) tags.add(kw); });

    // 5. Fallbacks to reach at least 3 tags
    let result = Array.from(tags);
    if (result.length < 3) {
        if (urlStr.includes('.pdf')) result.push('pdf');
        else if (/video|stream|watch|playlist/.test(urlStr + title)) result.push('video');
        else if (/image|photo|gallery|unsplash|pexels/.test(urlStr + title)) result.push('image');
        else if (/shop|store|buy|cart/.test(urlStr + title)) result.push('shopping');
        if (!result.includes('web')) result.push('web');
        if (result.length < 3 && !result.includes('resource')) result.push('resource');
        if (result.length < 3 && !result.includes('link')) result.push('link');
    }

    if (typeof window.smartMergeTags === 'function') {
        result = window.smartMergeTags(result.slice(0, 10));
    }
    return result.slice(0, 8);
}

// Smart auto-note for links: QoL-optimized, scannable, web-aware (used by Magic Enchant, Add Link, Quick Save)
function generateAutoNoteForLink(link) {
    if (!link || !link.url) return '';
    let domain = '', pathClean = '';
    try {
        const parsed = new URL(link.url);
        domain = parsed.hostname.replace('www.', '');
        const path = parsed.pathname || '';
        const pathParts = path.split('/').filter(p => p.length > 0).slice(0, 4);
        const clean = pathParts
            .map(p => p.replace(/[-_]/g, ' '))
            .filter(p => p.length > 1 && !/^\d+$/.test(p) && !/^[a-f0-9]{8,}$/i.test(p));
        pathClean = clean.length ? clean.join(' → ') : '';
    } catch (e) { return ''; }

    const cat = link.category || getAutoCategory(link.url, link.title);
    const title = (link.title || '').replace(/\s+/g, ' ').trim();
    const text = (title + ' ' + (link.url || '')).toLowerCase();

    const typeHints = [
        [/\btutorial\b|\bguide\b|\bhowto\b|\blearn\b|\bcourse\b/, 'Tutorial / Learning'],
        [/docs?\.|documentation|reference|api\./, 'Docs / API'],
        [/\.pdf\b|pdf\b/, 'PDF document'],
        [/tool|generator|converter|calculator|builder/, 'Tool'],
        [/article|blog|post|read|medium|substack/, 'Article'],
        [/video|watch|youtube|vimeo|stream/, 'Video'],
        [/design|ui|ux|template|theme|icon|font/, 'Design / Template'],
        [/repo|github\.com\/.+\/.+/, 'Repo / Code'],
        [/showcase|inspiration|examples?|demos?/, 'Reference / Demo'],
        [/shop|store|buy|cart|product/, 'Shopping']
    ];
    let contentType = '';
    for (const [regex, label] of typeHints) {
        if (regex.test(text)) { contentType = label; break; }
    }
    if (!contentType) contentType = 'Web page';

    const summaryRaw = title && title.length <= 60 ? title : (pathClean || domain);
    const summary = (summaryRaw || domain).slice(0, 80);
    const dateStr = new Date().toLocaleDateString('en-GB', { day: '2-digit', month: '2-digit', year: 'numeric' });

    return [
        `Content: ${contentType}. ${summary}`,
        `Source: ${domain}` + (pathClean ? ` · ${pathClean}` : ''),
        `Type: ${cat} · Saved: ${dateStr}`
    ].join('\n');
}

// ==================== Quick Save Functions (Bulk) ====================

async function populateQuickSaveFolderSelect() {
    const select = document.getElementById('quickSaveFolderSelect');
    if (!select) return;
    select.innerHTML = '<option value="">-- No Folder --</option>';
    if (!window.folders && typeof getAllFoldersFromDB === 'function') {
        window.folders = await getAllFoldersFromDB();
    }
    if (window.folders) {
        window.folders.forEach(folder => {
            const option = document.createElement('option');
            option.value = folder.id;
            option.textContent = folder.name;
            select.appendChild(option);
        });
    }
}

async function getOrCreateFolderForQuickSave() {
    const select = document.getElementById('quickSaveFolderSelect');
    const newFolderInput = document.getElementById('quickSaveNewFolder');
    let folderId = null;
    let folderTag = null;

    if (newFolderInput && newFolderInput.value.trim() !== '') {
        const folderName = newFolderInput.value.trim();
        const newFolder = {
            id: 'folder_' + Date.now().toString(),
            name: folderName,
            icon: '📁',
            createdAt: new Date().toISOString()
        };
        if (!window.folders) window.folders = [];
        window.folders.push(newFolder);
        if (typeof saveFolderToDB === 'function') await saveFolderToDB(newFolder);
        if (typeof renderFolderSidebar === 'function') renderFolderSidebar();
        folderId = newFolder.id;
        folderTag = folderName;
        newFolderInput.value = '';
    } else if (select && select.value !== '') {
        folderId = select.value;
        const folder = window.folders?.find(f => f.id === folderId);
        if (folder) folderTag = folder.name;
    }
    return { folderId, folderTag };
}

// Open Quick Save modal (single URL + bulk). Supports ?quickSave=URL from extension/query.
function openQuickSave(prefillUrl = '') {
    const modal = document.getElementById('quickSaveModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    // Populate folders
    populateQuickSaveFolderSelect();

    // Single-URL section: reset or prefill from ?quickSave= or extension
    const urlInput = document.getElementById('quickSaveUrl');
    const onePreview = document.getElementById('quickSaveOnePreview');
    if (urlInput) {
        urlInput.value = prefillUrl || '';
        if (onePreview) onePreview.classList.add('hidden');
        if (prefillUrl) setTimeout(() => fetchAndShowQuickSaveOne(), 150);
    }

    // Bulk section
    document.getElementById('quickSaveForm').reset();
    document.getElementById('quickSavePreview').classList.add('hidden');
    document.getElementById('quickSaveCount').textContent = '0 links';

    const newFolderInput = document.getElementById('quickSaveNewFolder');
    if (newFolderInput) newFolderInput.value = '';

    const urlsTextarea = document.getElementById('quickSaveUrls');
    if (urlsTextarea) {
        urlsTextarea.removeEventListener('input', updateQuickSavePreview);
        urlsTextarea.addEventListener('input', updateQuickSavePreview);
        if (!prefillUrl) setTimeout(() => urlsTextarea.focus(), 100);
        else setTimeout(() => urlInput && urlInput.focus(), 100);
    }

    initializeIcons();
}

// Fetch metadata for single-URL quick save and show preview
async function fetchAndShowQuickSaveOne() {
    const urlInput = document.getElementById('quickSaveUrl');
    const preview = document.getElementById('quickSaveOnePreview');
    const titleEl = document.getElementById('quickSaveTitle');
    const descEl = document.getElementById('quickSaveDescription');
    const faviconEl = document.getElementById('quickSaveFavicon');
    if (!urlInput || !preview) return;
    const url = urlInput.value.trim();
    if (!url) {
        preview.classList.add('hidden');
        return;
    }
    try {
        new URL(url);
    } catch {
        preview.classList.add('hidden');
        return;
    }
    titleEl.textContent = 'Fetching...';
    descEl.textContent = '';
    if (faviconEl) {
        faviconEl.src = '';
        faviconEl.classList.add('hidden');
    }
    preview.classList.remove('hidden');
    const meta = await fetchMetadataHelper(url);
    titleEl.textContent = meta.title || url;
    descEl.textContent = meta.description || url;
    if (meta.favicon && faviconEl) {
        faviconEl.src = meta.favicon;
        faviconEl.classList.remove('hidden');
    }
}

// Save one link from single-URL quick save (one-click save)
async function saveQuickSaveOne() {
    const urlInput = document.getElementById('quickSaveUrl');
    if (!urlInput) return;
    const url = urlInput.value.trim();
    if (!url) {
        showToast('Enter a URL first', 'error');
        return;
    }
    try {
        new URL(url);
    } catch {
        showToast('Invalid URL', 'error');
        return;
    }
    if (links.some(l => l.url === url)) {
        showToast('Link already saved', 'warning');
        return;
    }
    const titleEl = document.getElementById('quickSaveTitle');
    const title = (titleEl && titleEl.textContent && titleEl.textContent !== 'Fetching...') ? titleEl.textContent : (await fetchMetadataHelper(url)).title;

    const { folderId, folderTag } = await getOrCreateFolderForQuickSave();

    const category = autoCategorizeUrl(url, title);
    const tags = generateAutoTags({ url, title });
    if (folderTag && !tags.includes(folderTag)) tags.push(folderTag);

    const newLink = {
        id: Date.now().toString() + '_' + Math.random().toString(36).slice(2, 8),
        url,
        title: title || new URL(url).hostname.replace('www.', ''),
        category,
        tags,
        notes: '',
        image: null,
        accentColor: neonColors[Math.floor(Math.random() * neonColors.length)],
        favorite: false,
        visitCount: 0,
        createdAt: new Date().toISOString(),
        lastVisited: null,
        folderId: folderId || null
    };
    newLink.notes = generateAutoNoteForLink(newLink) || '';
    links.push(newLink);
    await saveLinkToDB(newLink);
    updateAllTags();
    renderLinks();
    renderCategoryFilters();
    closeQuickSave();
    showToast('Link saved!', 'success');
}

// Close Quick Save modal
function closeQuickSave() {
    const modal = document.getElementById('quickSaveModal');
    if (modal) modal.classList.add('hidden');
    document.body.style.overflow = '';
    const form = document.getElementById('quickSaveForm');
    if (form) form.reset();
    document.getElementById('quickSavePreview')?.classList.add('hidden');
    const urlInput = document.getElementById('quickSaveUrl');
    if (urlInput) urlInput.value = '';
    document.getElementById('quickSaveOnePreview')?.classList.add('hidden');
}

// Parse URLs from textarea - extract valid URLs
function parseUrlsFromText(text) {
    const lines = text.split('\n');
    const urls = [];

    for (const line of lines) {
        const trimmed = line.trim();
        if (!trimmed) continue;

        // Try to parse as URL
        try {
            const url = new URL(trimmed);
            if (url.protocol === 'http:' || url.protocol === 'https:') {
                urls.push(trimmed);
            }
        } catch {
            // Skip invalid URLs
        }
    }

    return urls;
}

// Update preview with URL count and list
// Update preview with URL count and list
function updateQuickSavePreview() {
    const urlsTextarea = document.getElementById('quickSaveUrls');
    const countEl = document.getElementById('quickSaveCount');
    const preview = document.getElementById('quickSavePreview');
    const previewList = document.getElementById('quickSavePreviewList');
    const submitText = document.getElementById('quickSaveSubmitText');
    const submitBtn = document.getElementById('quickSaveSubmitBtn');

    const urls = parseUrlsFromText(urlsTextarea.value);
    const count = urls.length;
    const limit = 50;
    const isOverLimit = count > limit;

    // Update count
    countEl.textContent = `${count} / ${limit} links`;
    countEl.className = isOverLimit ? 'text-red-400 font-bold' : 'text-gray-400';

    submitText.textContent = count > 1 ? `Save ${count} Links` : 'Save Link';

    // Disable if over limit or empty
    if (count === 0 || isOverLimit) {
        submitBtn.disabled = true;
        submitBtn.classList.add('opacity-50', 'cursor-not-allowed');
    } else {
        submitBtn.disabled = false;
        submitBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    }

    // Show preview if we have URLs
    if (count > 0) {
        const previewHtml = urls.slice(0, 10).map(url => {
            try {
                const hostname = new URL(url).hostname.replace('www.', '');
                return `
                    <div class="flex items-center gap-2 text-sm">
                        <img src="https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${encodeURIComponent(url)}&size=32" class="w-4 h-4" onerror="this.style.display='none'">
                        <span class="text-gray-300 truncate">${hostname}</span>
                        <span class="text-gray-500 truncate text-xs flex-1">${url.substring(0, 50)}${url.length > 50 ? '...' : ''}</span>
                    </div>
                `;
            } catch {
                return '';
            }
        }).join('');

        const moreCount = count - 10;
        previewList.innerHTML = previewHtml + (moreCount > 0 ? `<p class="text-xs text-gray-500">...and ${moreCount} more</p>` : '') + (isOverLimit ? `<p class="text-xs text-red-400 font-bold mt-2">⚠️ Maximum ${limit} links allowed per batch.</p>` : '');
        preview.classList.remove('hidden');
    } else {
        preview.classList.add('hidden');
    }
}

// Legacy function - for backwards compatibility
function fetchUrlMetadata() {
    updateQuickSavePreview();
}

// Handle Quick Save form submission (Bulk)
async function handleQuickSave(e) {
    e.preventDefault();

    const urlsTextarea = document.getElementById('quickSaveUrls');
    const submitBtn = document.getElementById('quickSaveSubmitBtn');
    const submitText = document.getElementById('quickSaveSubmitText');

    const urls = parseUrlsFromText(urlsTextarea.value);
    const limit = 50;

    if (urls.length === 0) {
        showToast('Please enter at least one valid URL.', 'error');
        return;
    }

    if (urls.length > limit) {
        showToast(`Too many links! Please reduce to ${limit} or fewer.`, 'error');
        return;
    }

    // Disable button and show loading
    submitBtn.disabled = true;
    submitText.textContent = 'Saving...';

    const { folderId, folderTag } = await getOrCreateFolderForQuickSave();

    let savedCount = 0;
    let skippedCount = 0;

    for (let i = 0; i < urls.length; i++) {
        const url = urls[i];

        // Check for duplicate URL
        if (links.some(l => l.url === url)) {
            skippedCount++;
            continue; // Skip duplicates silently in bulk mode
        }

        try {
            const validUrl = new URL(url);
            const hostname = validUrl.hostname.replace('www.', '');
            const accentColor = neonColors[Math.floor(Math.random() * neonColors.length)];

            // Get favicon
            const favicon = `https://t3.gstatic.com/faviconV2?client=SOCIAL&type=FAVICON&fallback_opts=TYPE,SIZE,URL&url=${encodeURIComponent(validUrl.href)}&size=64`;

            // Auto-generate tags
            const tempLink = { url, title: hostname };
            const tags = generateAutoTags(tempLink);
            if (folderTag && !tags.includes(folderTag)) tags.push(folderTag);

            const category = autoCategorizeUrl(url, hostname);
            const newLink = {
                id: Date.now().toString() + '_' + i,
                url,
                title: hostname,
                category,
                tags,
                notes: '',
                image: null,
                favicon,
                accentColor,
                favorite: false,
                visitCount: 0,
                createdAt: new Date().toISOString(),
                lastVisited: null,
                folderId: folderId || null
            };

            links.push(newLink);
            await saveLinkToDB(newLink);
            savedCount++;

            // Update progress
            submitText.textContent = `Saving... (${savedCount}/${urls.length})`;
        } catch {
            skippedCount++;
        }
    }

    // Re-enable button
    submitBtn.disabled = false;
    submitText.textContent = 'Save Links';

    updateAllTags();
    renderLinks();
    renderCategoryFilters();
    closeQuickSave();

    // Show result message
    if (savedCount > 0 && skippedCount > 0) {
        showToast(`${savedCount} link(s) saved! (${skippedCount} duplicates skipped)`, 'success');
    } else if (savedCount > 0) {
        showToast(`${savedCount} link(s) saved!`, 'success');
    } else {
        showToast('No new links saved (all duplicates).', 'warning');
    }

    initializeIcons();

    // Update storage stats if modal is open
    updateStorageStatsIfOpen();
}

// Show tag suggestions
function showTagSuggestions() {
    const input = document.getElementById('linkTags');
    const value = input.value.toLowerCase();
    const suggestions = document.getElementById('tagSuggestions');

    if (value.length === 0) {
        suggestions.classList.add('hidden');
        return;
    }

    const matchingTags = Array.from(allTags).filter(tag =>
        tag.includes(value) && !input.value.split(',').some(t => t.trim().toLowerCase() === tag)
    );

    if (matchingTags.length > 0) {
        suggestions.innerHTML = matchingTags.slice(0, 5).map(tag => `
            <button 
                type="button"
                class="tag-suggestion px-3 py-1 rounded-full bg-red-500/20 border border-red-500/30 text-red-300 text-sm hover:bg-red-500/30 transition-colors"
                onclick="addTagSuggestion('${tag}')"
            >
                #${tag}
            </button>
        `).join('');
        suggestions.classList.remove('hidden');
    } else {
        suggestions.classList.add('hidden');
    }
}

// Add tag suggestion
window.addTagSuggestion = function (tag) {
    const input = document.getElementById('linkTags');
    const currentTags = input.value.split(',').map(t => t.trim()).filter(t => t);
    if (!currentTags.includes(tag)) {
        currentTags.push(tag);
        input.value = currentTags.join(', ');
    }
    document.getElementById('tagSuggestions').classList.add('hidden');
    input.focus();
};

// Visit link
async function visitLink(url, id = null, event = null) {
    if (event) event.stopPropagation();
    window.open(url, '_blank', 'noopener,noreferrer');

    // Track visit
    if (id) {
        const link = links.find(l => l.id === id);
        if (link) {
            link.visitCount = (link.visitCount || 0) + 1;
            link.lastVisited = new Date().toISOString();
            await saveSingleLink(link);
        }
    }
}

// Filter and sort links (Optimized with memoization and single-pass filtering)
// Filter and sort links (includes smart filters from filterSelect)
let _filterCache = null;
let _filterCacheKey = null;
let _dataVersion = 0;

function bumpDataVersion() {
    _dataVersion++;
    _filterCache = null;
    _filterCacheKey = null;
}

function _computeFilterCacheKey() {
    const dateFrom = window.linkLumina_dateFrom;
    const dateTo = window.linkLumina_dateTo;
    const visitMin = window.linkLumina_visitMin;
    // currentFolder lives in folders.js (shared global lexical scope). Include it so
    // switching folders invalidates the cached folder-filtered result.
    // Active search is GLOBAL (ignores folder), so drop folder from the key then.
    const searching = searchTerm && searchTerm.trim().length > 0;
    const folder = searching ? '' : (typeof currentFolder !== 'undefined' ? currentFolder : 'all');
    return `${_dataVersion}|${folder}|${showFavoritesOnly}|${selectedCategory}|${searchTerm}|${Array.from(selectedTags).sort().join(',')}|${document.getElementById('filterSelect')?.value || 'all'}|${sortBy}|${dateFrom || ''}|${dateTo || ''}|${visitMin || ''}`;
}

// ==================== POWER SEARCH ENGINE (extracted to search-engine.js) ====================
// Pure engine lives in search-engine.js (UMD — runs in both browser and Node tests).
const SearchEngine = (typeof window !== "undefined" && window.SearchEngine) || globalThis.SearchEngine;
const _normalizeText = (s) => SearchEngine.normalizeText(s);
function parseSearchQuery(raw) { return SearchEngine.parseQuery(raw); }

let _searchIndex = null;
let _searchIndexVersion = null;
function _buildSearchIndex() {
    let folderArr = [];
    try { folderArr = window.folders || []; } catch (e) { }
    _searchIndex = SearchEngine.buildIndex(links, folderArr);
    _searchIndexVersion = _dataVersion;
}
function _getSearchIndex() {
    if (!_searchIndex || _searchIndexVersion !== _dataVersion) _buildSearchIndex();
    return _searchIndex;
}

function searchLinkScore(link, q) { return SearchEngine.score(link, q, _getSearchIndex()); }
function highlightMatches(rawText, terms) { return SearchEngine.highlight(rawText, terms, escapeHtml); }

// ==================== POWER SEARCH UI (suggestions / chips / tips) ====================
let _searchDebounceTimer = null;
let _suggestionActive = -1;
let _suggestItems = [];

const SEARCH_TIPS_HTML = `
<div class="ss-tips-title">Search operators</div>
<div class="ss-tips-body">
  <div><code>react tailwind</code> — all words (AND)</div>
  <div><code>tag:react</code> or <code>#react</code> — by tag</div>
  <div><code>cat:design</code> or <code>@design</code> — by category</div>
  <div><code>domain:github.com</code> — by domain</div>
  <div><code>folder:work</code> — by folder</div>
  <div><code>from:2024-01-01 to:2025-06-30</code> — by date</div>
  <div><code>fav:true</code> · <code>pinned:true</code> · <code>read:false</code></div>
  <div><code>visits:>5</code> — by visit count</div>
  <div><code>-tutorial</code> — exclude · <code>"exact phrase"</code> — exact phrase</div>
  <div class="ss-tips-note">No need to type Vietnamese diacritics — “ca phe” finds “Cà phê”.</div>
</div>`;

let _tagCountMap = null;
let _tagCountVersion = -1;
function _getTagCountMap() {
    if (_tagCountMap && _tagCountVersion === _dataVersion) return _tagCountMap;
    const m = new Map();
    for (const l of links) for (const t of (l.tags || [])) m.set(t, (m.get(t) || 0) + 1);
    _tagCountMap = m;
    _tagCountVersion = _dataVersion;
    return m;
}

function closeSearchSuggestions() {
    const box = document.getElementById('searchSuggestions');
    if (box) { box.classList.add('hidden'); box.innerHTML = ''; }
    _suggestionActive = -1;
}

function _replaceLastToken(raw, newToken) {
    const parts = raw.trimEnd().split(/\s+/);
    if (parts.length <= 1) return newToken + ' ';
    parts[parts.length - 1] = newToken;
    return parts.join(' ') + ' ';
}

function _syncSuggestionActive(box) {
    box.querySelectorAll('.ss-item').forEach((el, i) => el.classList.toggle('active', i === _suggestionActive));
}

function _moveSuggestion(delta) {
    const box = document.getElementById('searchSuggestions');
    const items = box ? box.querySelectorAll('.ss-item') : [];
    if (!items.length) return;
    _suggestionActive = (_suggestionActive + delta + items.length) % items.length;
    _syncSuggestionActive(box);
}

function buildSearchSuggestions() {
    const input = document.getElementById('searchInput');
    const box = document.getElementById('searchSuggestions');
    if (!input || !box) return;
    const raw = input.value;
    const trimmed = raw.trim();
    const lower = raw.toLowerCase();
    const lastToken = (raw.split(/\s+/).pop() || '').toLowerCase();
    const items = [];
    const esc = (s) => escapeHtml(s);

    // 1) Quick filters (appended to current query)
    items.push({ type: 'quick', label: 'Favorites', sub: 'fav:true', apply: (trimmed ? raw.trimEnd() + ' ' : '') + 'fav:true ', icon: 'star' });
    items.push({ type: 'quick', label: 'Pinned', sub: 'pinned:true', apply: (trimmed ? raw.trimEnd() + ' ' : '') + 'pinned:true ', icon: 'pin' });
    items.push({ type: 'quick', label: 'Unread', sub: 'read:false', apply: (trimmed ? raw.trimEnd() + ' ' : '') + 'read:false ', icon: 'book-marked' });

    if (lastToken) {
        // 2) Operator VALUE completion — "tag:" → matching tags, "fav:" → true/false...
        const opValMatch = lastToken.match(/^(tag|cat|category|domain|fav|pinned|read|visits):$/);
        if (opValMatch) {
            const op = opValMatch[1] === 'category' ? 'cat' : opValMatch[1];
            const vals = [];
            if (op === 'tag') { for (const [t, c] of _getTagCountMap()) { vals.push([t, c + ' links']); if (vals.length >= 5) break; } }
            else if (op === 'cat') { for (const c of new Set(links.map(l => l.category).filter(Boolean))) { vals.push([c, 'category']); if (vals.length >= 4) break; } }
            else if (op === 'fav' || op === 'pinned' || op === 'read') vals.push(['true', ''], ['false', '']);
            else if (op === 'visits') vals.push(['>5', 'popular'], ['>0', 'visited'], ['0', 'never']);
            else if (op === 'domain') {
                const doms = new Set();
                for (const l of links) { try { doms.add(new URL(l.url).hostname.replace(/^www\./, '')); } catch {} }
                for (const d of doms) { vals.push([d, 'domain']); if (vals.length >= 4) break; }
            }
            for (const [v, sub] of vals) items.push({ type: 'op', label: lastToken + v, sub, apply: _replaceLastToken(raw, lastToken + v), icon: 'filter' });
        } else if (/^(tag|cat|category|folder|domain|from|to|fav|pinned|read|visits|title|url|notes)$/.test(lastToken)) {
            const ops = { tag: 'tag:', cat: 'cat:', category: 'cat:', folder: 'folder:', domain: 'domain:', from: 'from:', to: 'to:', fav: 'fav:', pinned: 'pinned:', read: 'read:', visits: 'visits:', title: 'title:', url: 'url:', notes: 'notes:' };
            items.push({ type: 'op', label: ops[lastToken], sub: 'operator', apply: _replaceLastToken(raw, ops[lastToken]), icon: 'filter' });
        } else {
            // 3) Tags matching last token
            const prefix = lastToken.startsWith('#') ? lastToken.slice(1) : lastToken;
            let n = 0;
            for (const [tag, count] of _getTagCountMap()) {
                if (n >= 5) break;
                if (tag.toLowerCase().includes(prefix)) {
                    items.push({ type: 'tag', label: '#' + tag, sub: count + ' links', apply: _replaceLastToken(raw, '#' + tag), icon: 'hash' });
                    n++;
                }
            }
            // 4) Categories matching last token
            const cats = [...new Set(links.map(l => l.category).filter(Boolean))];
            let cn = 0;
            for (const c of cats) {
                if (cn >= 4) break;
                if (c.toLowerCase().includes(lastToken.replace(/^@/, ''))) {
                    items.push({ type: 'cat', label: '@' + c, sub: 'category', apply: _replaceLastToken(raw, '@' + c), icon: 'folder' });
                    cn++;
                }
            }
        }
        // 5) Recent searches matching current text
        if (trimmed.length >= 2) {
            const hist = (window.getSearchSuggestions ? window.getSearchSuggestions(lower) : []);
            for (const h of hist.slice(0, 3)) {
                if (h !== lower) items.push({ type: 'recent', label: h, sub: 'recent', apply: h, icon: 'history' });
            }
        }
    } else if (!trimmed) {
        // 6) Recent searches when box is focused but empty
        const hist = (window.getSearchSuggestions ? window.getSearchSuggestions('') : []);
        for (const h of hist.slice(0, 5)) items.push({ type: 'recent', label: h, sub: 'recent', apply: h, icon: 'history' });
    }

    if (!items.length) { box.classList.add('hidden'); box.innerHTML = ''; _suggestionActive = -1; return; }
    _suggestItems = items;
    _suggestionActive = -1;

    let html = '';
    let lastGroup = '';
    items.forEach((it) => {
        const group = it.type === 'quick' ? 'Quick filters' : it.type === 'tag' ? 'Tags' : it.type === 'cat' ? 'Categories' : it.type === 'op' ? 'Operators' : 'Recent searches';
        if (group !== lastGroup) { html += `<div class="ss-group">${esc(group)}</div>`; lastGroup = group; }
        html += `<div class="ss-item" data-apply="${esc(it.apply)}">
            <i data-lucide="${it.icon}" class="w-3.5 h-3.5 shrink-0"></i>
            <span class="ss-label">${esc(it.label)}</span>
            ${it.sub ? `<span class="ss-sub">${esc(it.sub)}</span>` : ''}
        </div>`;
    });
    box.innerHTML = html;
    box.classList.remove('hidden');
    initializeIcons();

    box.querySelectorAll('.ss-item').forEach((el, i) => {
        el.addEventListener('click', () => _applySuggestion(el.dataset.apply));
        el.addEventListener('mousemove', () => { _suggestionActive = i; _syncSuggestionActive(box); });
    });
}

function _applySuggestion(apply) {
    const input = document.getElementById('searchInput');
    if (!input) return;
    input.value = apply;
    closeSearchSuggestions();
    clearTimeout(_searchDebounceTimer);
    searchTerm = apply.toLowerCase().trim();
    if (typeof window.pushSearchHistory === 'function' && searchTerm.length >= 2) window.pushSearchHistory(searchTerm);
    renderSearchChips();
    renderLinks();
    input.focus();
}

function renderSearchChips() {
    const input = document.getElementById('searchInput');
    const wrap = document.getElementById('searchChips');
    if (!input || !wrap) return;
    const raw = input.value;
    if (!raw.trim()) { wrap.classList.add('hidden'); wrap.innerHTML = ''; return; }

    const tokens = [];
    const re = /"([^"]*)"|(\S+)/g;
    let m;
    while ((m = re.exec(raw))) tokens.push(m[0]);

    let html = `<span class="chip-chip chip-global" title="Search is global — finds links across all folders"><i data-lucide="globe" class="w-3 h-3"></i> global</span>`;
    tokens.forEach((tok, i) => {
        html += `<span class="chip-chip"><span class="chip-text">${escapeHtml(tok)}</span><button class="chip-x" data-i="${i}" title="Remove">×</button></span>`;
    });
    html += `<button id="chipClearAll" class="chip-clear">Clear</button>`;
    wrap.innerHTML = html;
    wrap.classList.remove('hidden');
    initializeIcons();

    wrap.querySelectorAll('.chip-x').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = Number(btn.dataset.i);
            tokens.splice(i, 1);
            input.value = tokens.join(' ');
            _commitSearchFromInput();
        });
    });
    const clearAll = wrap.querySelector('#chipClearAll');
    if (clearAll) clearAll.addEventListener('click', () => {
        input.value = '';
        _commitSearchFromInput();
        closeSearchSuggestions();
        document.getElementById('clearSearch').classList.add('hidden');
    });
}

function _commitSearchFromInput() {
    const input = document.getElementById('searchInput');
    clearTimeout(_searchDebounceTimer);
    searchTerm = input.value.toLowerCase();
    if (typeof window.pushSearchHistory === 'function' && searchTerm.length >= 2) window.pushSearchHistory(searchTerm);
    renderSearchChips();
    renderLinks();
    input.focus();
}

function getFilteredLinks() {
    const cacheKey = _computeFilterCacheKey();
    if (_filterCacheKey === cacheKey && _filterCache !== null) {
        return _filterCache;
    }

    const searchActive = !!searchTerm && searchTerm.trim().length > 0;
    let searchQuery = null;
    const searchScores = new Map();
    if (searchActive) {
        searchQuery = parseSearchQuery(searchTerm);
        if (!searchQuery.hasConstraints) {
            // Plain text with no operators → match as one normalized word/phrase set
            searchQuery.words = [_normalizeText(searchTerm)];
            searchQuery.highlightTerms = [searchTerm.toLowerCase().trim()];
        }
    }

    const filterValue = document.getElementById('filterSelect')?.value || 'all';
    const now = new Date();
    const weekAgo = new Date(now);
    weekAgo.setDate(now.getDate() - 7);
    const dateFrom = window.linkLumina_dateFrom ? new Date(window.linkLumina_dateFrom) : null;
    const dateTo = window.linkLumina_dateTo ? new Date(window.linkLumina_dateTo) : null;
    if (dateFrom) dateFrom.setHours(0, 0, 0, 0);
    if (dateTo) dateTo.setHours(23, 59, 59, 999);
    const visitMin = window.linkLumina_visitMin;

    const selectedTagsArr = Array.from(selectedTags);
    const hasSelectedTags = selectedTagsArr.length > 0;

    _filterCache = links.filter(link => {
        // Hoisted: parse createdAt once per link (reused by smart + date-range filters)
        const createdAtDate = link.createdAt ? new Date(link.createdAt) : null;

        // Favorites filter
        if (showFavoritesOnly && !link.favorite) return false;

        // Category filter
        if (selectedCategory !== 'all' && link.category !== selectedCategory) return false;

        // Power Search (accent-insensitive, operators, relevance scored)
        if (searchActive) {
            const score = searchLinkScore(link, searchQuery);
            if (score === 0) return false;
            searchScores.set(link.id, score);
        }

        // Tag filter (multi-select OR)
        if (hasSelectedTags) {
            if (!link.tags || link.tags.length === 0) return false;
            let tagMatch = false;
            for (const tag of link.tags) {
                if (selectedTagsArr.includes(tag)) { tagMatch = true; break; }
            }
            if (!tagMatch) return false;
        }

        // Smart filters
        if (filterValue !== 'all') {
            const visitCount = link.visitCount || 0;
            switch (filterValue) {
                case 'recent':
                    if (!createdAtDate || createdAtDate < weekAgo) return false;
                    break;
                case 'frequent':
                    if (visitCount < 5) return false;
                    break;
                case 'personal':
                    const cat = link.category?.toLowerCase();
                    const hasPersonalTag = link.tags?.some(t => t.toLowerCase() === 'personal');
                    if (!(link.url.includes('localhost') || link.url.includes('127.0.0.1') || cat === 'personal' || hasPersonalTag)) return false;
                    break;
                case 'unused':
                    if (visitCount !== 0 || !createdAtDate || createdAtDate >= weekAgo) return false;
                    break;
                case 'potential':
                    if (visitCount !== 0) return false;
                    break;
                case 'work':
                    const text = (link.title + ' ' + link.url + ' ' + (link.tags || []).join(' ')).toLowerCase();
                    const workKw = ['work', 'study', 'job', 'learn', 'edu', 'course', 'doc', 'github', 'stackoverflow', 'jira', 'figma', 'notion'];
                    let workMatch = false;
                    for (const kw of workKw) {
                        if (text.includes(kw)) { workMatch = true; break; }
                    }
                    if (!workMatch) return false;
                    break;
            }
        }

        // Date range filter
        if (dateFrom && (!createdAtDate || createdAtDate < dateFrom)) return false;
        if (dateTo && (!createdAtDate || createdAtDate > dateTo)) return false;

        // Visit count filter
        if (visitMin != null && visitMin > 0 && (link.visitCount || 0) < visitMin) return false;

        return true;
    });

    // Sort (in-place). Precompute date keys once so the comparator never re-parses dates
    // (new Date() inside a comparator is called O(n log n) times and is a big cost for 5k+ links).
    const _needsDateKeys = sortBy !== 'title' && sortBy !== 'title-desc' &&
        sortBy !== 'visits' && sortBy !== 'visits-asc' && sortBy !== 'category';
    const _dateKeys = _needsDateKeys ? new Map() : null;
    if (_dateKeys) {
        const _useLastVisited = sortBy === 'lastvisited';
        for (const l of _filterCache) {
            const _raw = _useLastVisited ? (l.lastVisited || l.createdAt) : l.createdAt;
            const d = _raw ? new Date(_raw) : null;
            _dateKeys.set(l.id, d && !isNaN(d.getTime()) ? d.getTime() : 0);
        }
    }

    if (searchActive && sortBy === 'newest') {
        // Best matches first (relevance), newest as tiebreak
        _filterCache.sort((a, b) => (searchScores.get(b.id) || 0) - (searchScores.get(a.id) || 0) || _dateKeys.get(b.id) - _dateKeys.get(a.id));
    } else {
        _filterCache.sort((a, b) => {
            switch (sortBy) {
                case 'newest': return _dateKeys.get(b.id) - _dateKeys.get(a.id);
                case 'oldest': return _dateKeys.get(a.id) - _dateKeys.get(b.id);
                case 'lastvisited': return _dateKeys.get(b.id) - _dateKeys.get(a.id);
                case 'title': return a.title.localeCompare(b.title);
                case 'title-desc': return b.title.localeCompare(a.title);
                case 'visits': return (b.visitCount || 0) - (a.visitCount || 0);
                case 'visits-asc': return (a.visitCount || 0) - (b.visitCount || 0);
                case 'category': return a.category.localeCompare(b.category);
                default: return _dateKeys.get(b.id) - _dateKeys.get(a.id);
            }
        });
    }

    // Folder filter (if available) — skipped during search (search is global)
    if (window.filterLinksByFolder && !searchActive) {
        _filterCache = window.filterLinksByFolder(_filterCache);
    }

    _filterCacheKey = cacheKey;
    return _filterCache;
}

// Invalidate cache when data changes
function invalidateFilterCache() {
    _filterCache = null;
    _filterCacheKey = null;
}

// Render links (supports multiple views)
// --- Unified Search & Render Helpers ---

// Tools (PH) haystack for search — name/desc/topics/tags/cat/domain, accent-insensitive
function _toolSearchHay(x) {
    return _normalizeText([x.n, x.d, x.desc, (x.topics || []).join(' '), (x.tags || []).join(' '), x.cat, x.domain, x.u].join(' '));
}

// Tools matching a query (category-aware: respects the active category filter)
function getToolsForQuery(query) {
    const toolsArr = window.tools || [];
    if (!toolsArr.length || !query) return [];
    const qn = _normalizeText(query);
    const cat = selectedCategory && selectedCategory !== 'all' ? selectedCategory : '';
    return toolsArr.filter(x => {
        if (cat && x.cat !== cat) return false;
        return _toolSearchHay(x).indexOf(qn) !== -1;
    }).sort((a, b) => (b.votes || 0) - (a.votes || 0)).slice(0, 8);
}

// Tools of a category (used when filtering by category without a search term)
function getToolsForCategory(cat) {
    const toolsArr = window.tools || [];
    if (!toolsArr.length || !cat || cat === 'all') return [];
    return toolsArr.filter(x => (x.cat || '') === cat)
        .sort((a, b) => (b.votes || 0) - (a.votes || 0)).slice(0, 12);
}

function getUnifiedSearchResults(query) {
    if (!query) return { prompts: [], notes: [], tools: [] }; // Links handled by standard filter

    const lowerQuery = _normalizeText(query);

    // Search Prompts (Global, accent-insensitive)
    const matchedPrompts = window.prompts.filter(p => {
        const hay = _normalizeText([p.title, p.content, (p.tags || []).join(' ')].join(' '));
        return hay.indexOf(lowerQuery) !== -1;
    });

    // Search Notes (Global)
    const matchedNotes = (window.notes || []).filter(n => {
        const hay = _normalizeText([n.title, n.content, (n.tags || []).join(' ')].join(' '));
        return hay.indexOf(lowerQuery) !== -1;
    });

    // Search Tools (Product Hunt) — same grid, category-aware
    const matchedTools = getToolsForQuery(query);

    return { prompts: matchedPrompts, notes: matchedNotes, tools: matchedTools };
}

function createUnifiedCard(type, data) {
    const isPrompt = type === 'prompt';
    const color = isPrompt ? 'text-red-400 border-red-500/30 hover:border-red-500' : 'text-red-400 border-red-500/30 hover:border-red-500';
    const icon = isPrompt ? 'message-square' : 'sticky-note';
    const bg = isPrompt ? 'bg-red-500/10' : 'bg-red-500/10';

    return `
        <div onclick="${isPrompt ? `openPromptModal('${data.id}')` : `openNoteModal('${data.id}')`}" 
             class="group relative glass-card p-5 border ${color} transition-all duration-300 hover:shadow-lg hover:shadow-${isPrompt ? 'red' : 'amber'}-500/10 cursor-pointer animate-in fade-in zoom-in-95 flex flex-col gap-3 min-h-[180px]">
            <div class="flex items-center justify-between mb-2">
                <div class="flex items-center gap-2">
                    <div class="p-2 rounded-lg ${bg} ${color}">
                        <i data-lucide="${icon}" class="w-4 h-4"></i>
                    </div>
                    <h3 class="font-bold text-gray-200 line-clamp-1 group-hover:text-white transition-colors">${escapeHtml(data.title)}</h3>
                </div>
                <span class="text-xs text-gray-500 bg-black/30 px-2 py-1 rounded border border-white/5">${type.toUpperCase()}</span>
            </div>
            
            <p class="text-sm text-gray-400 line-clamp-4 flex-1 leading-relaxed">${escapeHtml(data.content)}</p>
            
            <div class="mt-auto pt-3 flex items-center gap-2 border-t border-white/5 overflow-hidden">
                ${(data.tags || []).slice(0, 2).map(t => `<span class="text-[10px] px-2 py-0.5 bg-gray-800 rounded-full text-gray-500">#${escapeHtml(t)}</span>`).join('')}
                <span class="text-[10px] text-gray-600 ml-auto">${new Date(data.createdAt).toLocaleDateString()}</span>
            </div>
        </div>
    `;
}

// Master Render Function (Unified)
async function renderLinks() {
    // Folder filtering is already applied (and cached) inside getFilteredLinks
    const filteredLinks = getFilteredLinks();
    currentFilteredLinks = filteredLinks;

    // Highlight search matches in card titles/tags (best-effort, exact-case on raw text)
    if (searchTerm && searchTerm.trim().length > 0) {
        _activeHighlightTerms = parseSearchQuery(searchTerm).highlightTerms.filter(t => t.length >= 2);
    } else {
        _activeHighlightTerms = [];
    }

    // 2. Global Search Logic
    let unifiedResults = { prompts: [], notes: [], tools: [] };
    const isGlobalSearch = searchTerm && searchTerm.length > 0;
    const categoryActive = selectedCategory && selectedCategory !== 'all';
    if (isGlobalSearch) {
        unifiedResults = getUnifiedSearchResults(searchTerm);
    } else if (categoryActive) {
        // Shared category filter: no search needed, still shows tools in the same category
        unifiedResults.tools = getToolsForCategory(selectedCategory);
    }

    // Update Counts including unified results (pop animation only when the number changes)
    const linkCountEl = document.getElementById('linkCount');
    if (linkCountEl) {
        const total = filteredLinks.length + unifiedResults.prompts.length + unifiedResults.notes.length + unifiedResults.tools.length;
        if ((Number(linkCountEl.textContent) || 0) !== total) {
            linkCountEl.textContent = total;
            linkCountEl.classList.remove('count-pop');
            void linkCountEl.offsetWidth; // restart the pop animation
            linkCountEl.classList.add('count-pop');
        }
    }

    // 3. Tag Cloud (Debounced — collapses bursts of renders into one aggregation pass)
    scheduleTagCloud();

    // 4. Setup View (Reset Grid)
    const grid = document.getElementById('linksGrid');
    if (grid) {
        // Show Skeleton Loaders briefly for premium feel on initial load
        if (window._initialRenderCompleted === undefined) {
            grid.innerHTML = Array(12).fill('<div class="skeleton-card"></div>').join('');
            window._initialRenderCompleted = true;
            await new Promise(r => setTimeout(r, 150));
        }
        grid.innerHTML = '';
    }
    renderedCount = 0;

    // 5. Render Unified Results (Prompts & Notes) BEFORE Links
    if (isGlobalSearch && (unifiedResults.prompts.length > 0 || unifiedResults.notes.length > 0)) {

        // Prompts Section
        if (unifiedResults.prompts.length > 0) {
            const header = document.createElement('div');
            header.className = 'col-span-full flex items-center gap-2 text-red-400 font-bold text-lg mt-4 mb-2 animate-in slide-in-from-left-2';
            header.innerHTML = `<i data-lucide="sparkles" class="w-5 h-5"></i> <span>Prompts (${unifiedResults.prompts.length})</span><div class="h-px bg-red-500/20 flex-1 ml-2"></div>`;
            grid.appendChild(header);

            unifiedResults.prompts.forEach(p => {
                const div = document.createElement('div');
                div.innerHTML = createUnifiedCard('prompt', p);
                grid.appendChild(div.firstElementChild);
            });
        }

        // Notes Section
        if (unifiedResults.notes.length > 0) {
            const header = document.createElement('div');
            header.className = 'col-span-full flex items-center gap-2 text-red-400 font-bold text-lg mt-8 mb-2 animate-in slide-in-from-left-2';
            header.innerHTML = `<i data-lucide="sticky-note" class="w-5 h-5"></i> <span>Notes (${unifiedResults.notes.length})</span><div class="h-px bg-red-500/20 flex-1 ml-2"></div>`;
            grid.appendChild(header);

            unifiedResults.notes.forEach(n => {
                const div = document.createElement('div');
                div.innerHTML = createUnifiedCard('note', n);
                grid.appendChild(div.firstElementChild);
            });
        }
    }

    // Tools Section (Product Hunt) — standalone: appears for search AND category filter
    if (unifiedResults.tools.length > 0) {
        const header = document.createElement('div');
        header.className = 'col-span-full flex items-center gap-2 text-orange-400 font-bold text-lg mt-8 mb-2 animate-in slide-in-from-left-2';
        header.innerHTML = `<i data-lucide="wrench" class="w-5 h-5"></i> <span>Tools (${unifiedResults.tools.length})</span><div class="h-px bg-orange-500/20 flex-1 ml-2"></div>`;
        grid.appendChild(header);

        unifiedResults.tools.forEach(t => {
            const div = document.createElement('div');
            div.innerHTML = createUnifiedToolCard(t);
            grid.appendChild(div.firstElementChild);
        });
    }

    // Links Section Header (Only if other results exist)
    if (filteredLinks.length > 0 && (isGlobalSearch || categoryActive)) {
        const header = document.createElement('div');
        header.className = 'col-span-full flex items-center gap-2 text-red-400 font-bold text-lg mt-8 mb-2 animate-in slide-in-from-left-2';
        header.innerHTML = `<i data-lucide="link" class="w-5 h-5"></i> <span>Links (${filteredLinks.length})</span><div class="h-px bg-red-500/20 flex-1 ml-2"></div>`;
        grid.appendChild(header);
    } else if (filteredLinks.length === 0 && !isGlobalSearch && unifiedResults.tools.length === 0) {
        // No visible links (either no data yet, or current filters hide everything)
        const gridEl = document.getElementById('linksGrid');
        const emptyState = document.getElementById('emptyState');
        ['linksList', 'linksTimeline', 'linksGallery'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.classList.add('hidden');
        });
        if (window.links && window.links.length === 0) {
            // No data at all -> friendly onboarding state
            if (gridEl) gridEl.classList.add('hidden');
            if (emptyState) emptyState.classList.remove('hidden');
        } else {
            // Data exists but filters hide it all -> explain why
            if (gridEl) {
                gridEl.classList.remove('hidden');
                gridEl.innerHTML = `
                    <div class="col-span-full flex flex-col items-center justify-center py-20 text-gray-500">
                        <div class="w-20 h-20 bg-gray-800/50 rounded-full flex items-center justify-center mb-6">
                            <i data-lucide="filter" class="w-10 h-10 opacity-50"></i>
                        </div>
                        <h3 class="text-xl font-semibold text-gray-300 mb-2">No links match your current filters</h3>
                        <p class="text-gray-500 text-sm mb-4">Try clearing the search, category, or tag filters.</p>
                    </div>`;
                if (typeof initializeIcons === 'function') initializeIcons();
            }
        }
    }

    // 6. Start Link Batch Rendering
    // If Global Search yielded no links but we have filteredLinks (e.g. tag filter), we render them.
    // renderNextBatch will append links to the grid (maintaining our unified headers).
    // Also ensure the active view container is visible + empty state hidden whenever
    // there is content (previously the grid stayed hidden after the first add).
    const _viewContainers = { grid: 'linksGrid', list: 'linksList', timeline: 'linksTimeline', gallery: 'linksGallery' };
    const _hasContent = filteredLinks.length > 0 || unifiedResults.prompts.length > 0 || unifiedResults.notes.length > 0 || unifiedResults.tools.length > 0;
    if (_hasContent) {
        const _activeContainer = document.getElementById(_viewContainers[currentView] || 'linksGrid');
        if (_activeContainer) _activeContainer.classList.remove('hidden');
        const _emptyStateEl = document.getElementById('emptyState');
        if (_emptyStateEl) _emptyStateEl.classList.add('hidden');
    }

    if (filteredLinks.length > 0) {
        renderNextBatch();
    } else if (isGlobalSearch && passedTotalResultCount(unifiedResults) === 0) {
        grid.innerHTML = `
            <div class="col-span-full flex flex-col items-center justify-center py-20 text-gray-500 animate-in fade-in zoom-in-95">
                <div class="w-20 h-20 bg-gray-800/50 rounded-full flex items-center justify-center mb-6">
                    <i data-lucide="search-x" class="w-10 h-10 opacity-50"></i>
                </div>
                <h3 class="text-xl font-semibold text-gray-300 mb-2">No results found</h3>
                <p class="text-gray-500 text-sm">We couldn't find anything matching "${escapeHtml(searchTerm)}"</p>
                <p class="search-empty-tip">Tip: try <code>tag:xxx</code>, <code>cat:xxx</code>, <code>domain:xxx</code>, <code>visits:>5</code> or <code>"exact phrase"</code> — press <code>?</code> next to the search box for the full list of operators.</p>
                <button onclick="document.getElementById('searchInput').value=''; searchTerm=''; renderLinks();" class="mt-6 px-6 py-2 bg-gray-800 hover:bg-white/10 rounded-full transition-all border border-white/5 hover:border-white/20 text-gray-300">
                    Clear Search
                </button>
            </div>
        `;
        if (typeof initializeIcons === 'function') initializeIcons();
    }
}

function passedTotalResultCount(unified) {
    return (unified.prompts ? unified.prompts.length : 0) + (unified.notes ? unified.notes.length : 0) + (unified.tools ? unified.tools.length : 0);
}

function createUnifiedToolCard(t) {
    const accent = (typeof getCategoryColor === 'function' && getCategoryColor(t.cat)) || '#f59e0b';
    const votes = t.votes || 0;
    const tags = (t.tags || t.topics || []).slice(0, 2);
    const img = t.img
        ? `<div class="relative shrink-0"><img src="${escapeHtml(t.img)}" alt="" loading="lazy" decoding="async" class="w-full h-28 object-cover" onerror="this.parentElement.innerHTML='<div class=\\'w-full h-28 flex items-center justify-center text-white/25 bg-gray-800/40\\'><i data-lucide=\\'package\\' class=\\'w-8 h-8\\'></i></div>'"></div>`
        : `<div class="w-full h-28 flex items-center justify-center text-white/25 shrink-0" style="background:linear-gradient(135deg,${accent}45,${accent}15)"><i data-lucide="package" class="w-8 h-8"></i></div>`;
    return `
        <div class="group relative glass-card p-0 overflow-hidden border border-white/10 hover:border-red-500/40 transition-all duration-300 hover:shadow-lg hover:shadow-red-500/10 cursor-pointer flex flex-col animate-in fade-in zoom-in-95" onclick="window.open('${escapeHtml(t.u)}','_blank')" title="Open ${escapeHtml(t.n)}">
            ${img}
            ${votes ? `<span class="absolute top-2 left-2 z-10 text-[10px] px-2 py-0.5 rounded-full bg-black/60 backdrop-blur-md border border-white/10 text-amber-300"><i data-lucide="trending-up" class="w-3 h-3"></i> ${votes}</span>` : ''}
            <div class="p-3 flex flex-col flex-1 min-w-0">
                <div class="flex items-center gap-2">
                    <span class="w-2 h-2 rounded-full shrink-0" style="background:${accent}"></span>
                    <h3 class="font-bold text-gray-200 text-sm truncate">${escapeHtml(t.n)}</h3>
                </div>
                <p class="text-xs text-gray-400 line-clamp-2 mt-1 leading-relaxed min-h-[2rem]">${escapeHtml((t.desc || t.d || '').slice(0, 160))}</p>
                <div class="mt-auto pt-2 flex items-center gap-2 border-t border-white/5 mt-2">
                    ${tags.map(tg => `<span class="text-[10px] px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/20 text-red-300">${escapeHtml(tg)}</span>`).join('')}
                    <span class="text-[10px] text-gray-500 ml-auto">Tool · ${escapeHtml(t.cat || '')}</span>
                </div>
            </div>
        </div>
    `;
}

// Create link card HTML
function createLinkCard(link) {
    const hasImage = link.image;
    // Category drives the card's accent hue; fall back to the legacy per-link
    // accent color for links without a mapped category.
    const accent = getCategoryColor(link.category) || link.accentColor || neonColors[0];
    // Images lazy-load via data-bg (swapped in by observeLazyImages); no-image
    // cards keep a category-tinted gradient placeholder.
    const thumbStyle = hasImage
        ? `data-bg="${escapeHtml(link.image)}" style="background-color: rgba(255,255,255,0.04); background-size: cover; background-position: center;"`
        : `style="background: linear-gradient(135deg, ${accent}60, ${accent}30, ${accent}10);"`;

    const tagsHtml = link.tags.length > 0
        ? link.tags.map(tag => `<span class="tag">#${highlightMatches(tag, _activeHighlightTerms)}</span>`).join('')
        : '';

    // Format date
    const date = new Date(link.createdAt);
    const formattedDate = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

    const isBatchSelected = batchSelectedLinks.has(link.id);
    const visitCount = link.visitCount || 0;

    // Selection Mode UI
    // If in Selection Mode:
    // - Click anywhere on card -> Toggles Selection
    // - Checkbox is always visible
    // If NOT in Selection Mode:
    // - Click -> Open Link
    // - Checkbox hidden

    const clickAction = isSelectionMode
        ? `handleCardSelect('${link.id}', event)`
        : `visitLink('${escapeHtml(link.url)}', '${link.id}', event)`;

    return `
        <div id="link-card-${link.id}" 
             class="link-card glass-card p-0 overflow-hidden group relative transition-all duration-300 ${isBatchSelected ? 'ring-2 ring-red-500 scale-[0.98]' : 'hover:scale-[1.02] hover:shadow-2xl hover:shadow-red-500/20'}" 
             style="--accent-color: ${accent}; --cat-color: ${accent}" 
             draggable="true"
             ondragstart="window.handleLinkDragStart && window.handleLinkDragStart(event, '${link.id}')"
             onclick="${clickAction}">
            
            <!-- Batch Selection Overlay & Checkbox -->
            <div class="${isSelectionMode ? 'absolute' : 'hidden'} top-3 left-3 z-30">
                 <div class="w-6 h-6 rounded-md bg-black/50 backdrop-blur-md border border-white/20 flex items-center justify-center transition-all ${isBatchSelected ? 'bg-red-500 border-red-500' : 'hover:border-white/50'}">
                    ${isBatchSelected ? '<i data-lucide="check" class="w-4 h-4 text-white"></i>' : ''}
                 </div>
            </div>

            <div class="cat-accent" aria-hidden="true"></div>

            <div class="card-thumb relative h-48 ${hasImage ? '' : 'flex items-center justify-center'} overflow-hidden" ${thumbStyle}>
                ${!hasImage ? `
                    <div class="relative z-10 animate-float">
                        <i data-lucide="link" class="w-16 h-16 text-white/40"></i>
                    </div>
                ` : ''}
                
                <!-- Hover Overlay (Only if NOT in selection mode) -->
                <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-black/20 to-transparent opacity-0 ${isSelectionMode ? '' : 'group-hover:opacity-100'} transition-opacity duration-300"></div>
                
                <!-- Action Buttons Desktop (hidden on mobile) -->
                <div class="link-card-actions absolute top-3 right-3 flex items-center gap-0.5 z-20 ${isSelectionMode ? 'hidden' : 'opacity-0 group-hover:opacity-100 transition-all duration-300 transform translate-y-2 group-hover:translate-y-0'} rounded-full bg-black/40 backdrop-blur-xl border border-white/10 p-1 shadow-2xl" onclick="event.stopPropagation()">
                    <button onclick="copyLink('${escapeHtml(link.url)}', event)" class="p-1.5 rounded-full text-gray-300 hover:text-white hover:bg-white/20 transition-all" title="Copy"><i data-lucide="copy" class="w-3.5 h-3.5"></i></button>
                    <button onclick="openMoveToFolderModal('${link.id}', event)" class="p-1.5 rounded-full text-gray-300 hover:text-white hover:bg-white/20 transition-all" title="Move"><i data-lucide="folder-input" class="w-3.5 h-3.5"></i></button>
                    <button onclick="openModal('${link.id}')" class="p-1.5 rounded-full text-gray-300 hover:text-white hover:bg-white/20 transition-all" title="Edit"><i data-lucide="edit" class="w-3.5 h-3.5"></i></button>
                    <button onclick="openTranscriptModal('${link.id}', '${escapeHtml(link.url)}')" class="p-1.5 rounded-full text-gray-300 hover:text-white hover:bg-white/20 transition-all" title="Transcript"><i data-lucide="file-text" class="w-3.5 h-3.5"></i></button>
                    ${typeof window.findSimilarLinks === 'function' ? `<button onclick="showSimilarLinksModal('${link.id}')" class="p-1.5 rounded-full text-gray-300 hover:text-white hover:bg-white/20 transition-all" title="Similar links"><i data-lucide="git-branch" class="w-3.5 h-3.5"></i></button>` : ''}
                    <button onclick="window.openSidePeek('${escapeHtml(link.title)}', '${escapeHtml(link.url)}')" class="p-1.5 rounded-full text-gray-300 hover:text-white hover:bg-red-500/50 transition-all" title="Side-Peek"><i data-lucide="eye" class="w-3.5 h-3.5"></i></button>
                    <button onclick="visitLink('${escapeHtml(link.url)}', '${link.id}', event)" class="p-1.5 rounded-full text-gray-300 hover:text-white hover:bg-green-500/50 transition-all" title="Visit"><i data-lucide="external-link" class="w-3.5 h-3.5"></i></button>
                    <div class="w-px h-3 bg-white/20 mx-1"></div>
                    <button onclick="deleteLink('${link.id}', event)" class="p-1.5 rounded-full text-gray-300 hover:text-red-400 hover:bg-red-500/20 transition-all" title="Delete"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>
                </div>

                <!-- Mobile: Visit, Favorite, More (More opens dropdown) -->
                <div class="link-card-actions-mobile absolute top-3 right-3 flex gap-2 z-20 opacity-100" onclick="event.stopPropagation()">
                    <button onclick="visitLink('${escapeHtml(link.url)}', '${link.id}', event)" class="p-2 rounded-lg bg-black/50 backdrop-blur-md text-white hover:bg-green-500 shadow-lg min-touch" title="Visit">
                        <i data-lucide="external-link" class="w-4 h-4"></i>
                    </button>
                    <button onclick="toggleFavorite('${link.id}', event)" class="p-2 rounded-lg backdrop-blur-md shadow-lg min-touch ${link.favorite ? 'bg-red-500 text-white' : 'bg-black/50 text-gray-400 hover:text-red-400'}" title="${link.favorite ? 'Unfavorite' : 'Favorite'}">
                        <i data-lucide="star" class="w-4 h-4 ${link.favorite ? 'fill-current' : ''}"></i>
                    </button>
                    <div class="relative link-card-more-wrap">
                        <button type="button" class="link-card-more-btn p-2 rounded-lg bg-black/50 backdrop-blur-md text-white hover:bg-red-500 shadow-lg min-touch" title="More" aria-haspopup="true" aria-expanded="false">
                            <i data-lucide="more-horizontal" class="w-4 h-4"></i>
                        </button>
                        <div class="link-card-more-dropdown hidden absolute right-0 top-full mt-1 py-1 glass-card border border-white/10 rounded-xl min-w-[160px]">
                            <button type="button" onclick="copyLink('${escapeHtml(link.url)}', event); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="copy" class="w-4 h-4"></i> Copy</button>
                            <button type="button" onclick="copyLinkTitleUrl('${link.id}', event); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="clipboard-copy" class="w-4 h-4"></i> Copy title + URL</button>
                            <button type="button" onclick="openMoveToFolderModal('${link.id}', event); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="folder-input" class="w-4 h-4"></i> Move</button>
                            <button type="button" onclick="openModal('${link.id}'); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="edit" class="w-4 h-4"></i> Edit</button>
                            <button type="button" onclick="openTranscriptModal('${link.id}', '${escapeHtml(link.url)}'); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="file-text" class="w-4 h-4"></i> Transcript</button>
                            <button type="button" onclick="duplicateLink('${link.id}', event); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="copy-plus" class="w-4 h-4"></i> Duplicate</button>
                            <button type="button" onclick="window.openSidePeek('${escapeHtml(link.title)}', '${escapeHtml(link.url)}'); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="eye" class="w-4 h-4"></i> Side-Peek</button>
                            ${typeof window.openTranslateModalForLink === 'function' ? `<button type="button" onclick="window.openTranslateModalForLink('${link.id}'); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="languages" class="w-4 h-4"></i> Translate</button>` : ''}
                            ${typeof window.findSimilarLinks === 'function' ? `<button type="button" onclick="showSimilarLinksModal('${link.id}'); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-gray-200 hover:bg-white/10 flex items-center gap-2"><i data-lucide="git-branch" class="w-4 h-4"></i> Similar</button>` : ''}
                            <button type="button" onclick="deleteLink('${link.id}', event); this.closest('.link-card-more-dropdown').classList.add('hidden')" class="w-full text-left px-3 py-2.5 text-sm text-red-400 hover:bg-red-500/20 flex items-center gap-2"><i data-lucide="trash-2" class="w-4 h-4"></i> Delete</button>
                        </div>
                    </div>
                </div>

                <!-- Selection Mode Favorite Button (Visible ONLY in Selection Mode) -->
                ${isSelectionMode ? `
                <div class="absolute top-3 right-3 z-30">
                    <button 
                        onclick="toggleFavorite('${link.id}', event)" 
                        class="p-2 rounded-lg backdrop-blur-md transition-all shadow-lg ${link.favorite ? 'bg-red-500 text-white shadow-red-500/20' : 'bg-black/50 text-gray-400 hover:text-red-400 hover:bg-black/70 border border-white/10'}"
                        title="${link.favorite ? 'Unfavorite' : 'Favorite'}"
                    >
                        <i data-lucide="star" class="w-5 h-5 ${link.favorite ? 'fill-current' : ''}"></i>
                    </button>
                </div>
                ` : ''}

                <!-- Favorite Badge (Visible in Normal Mode if favorite) -->
                ${link.favorite && !isSelectionMode ? `
                <div class="absolute top-3 left-3 z-10">
                    <div class="p-1.5 rounded-full bg-red-500/20 backdrop-blur-md border border-red-500/50 shadow-[0_0_10px_rgba(234,179,8,0.3)]">
                        <i data-lucide="star" class="w-3 h-3 text-red-400 fill-red-400"></i>
                    </div>
                </div>
                ` : ''}

                <!-- Pinned badge -->
                ${link.pinned && !isSelectionMode ? `
                <div class="absolute bottom-3 left-3 z-10">
                    <div class="p-1 rounded-full bg-amber-500/25 backdrop-blur-md border border-amber-400/40" title="Pinned">
                        <i data-lucide="pin" class="w-3 h-3 text-amber-300"></i>
                    </div>
                </div>
                ` : ''}

                <!-- Unread dot -->
                ${!link.isRead ? `
                <div class="absolute bottom-3 right-3 z-10">
                    <span class="block w-2 h-2 rounded-full bg-sky-400 shadow-[0_0_8px_rgba(56,189,248,0.8)]" title="Unread"></span>
                </div>
                ` : ''}
            </div>
            <div class="card-body p-6">
                <div class="flex items-start justify-between mb-3">
                    <div class="flex items-center gap-3 flex-1 min-w-0">
                        ${link.favicon ? `<img src="${link.favicon}" alt="" class="w-5 h-5 flex-shrink-0 opacity-90" onerror="this.style.display='none'">` : ''}
                        <h3 class="text-white font-medium text-lg leading-tight line-clamp-2 flex-1 group-hover:text-red-300 transition-colors tracking-wide">${highlightMatches(link.title, _activeHighlightTerms)}</h3>
                    </div>
                </div>
                <p class="text-gray-400/80 text-sm mb-4 line-clamp-1 truncate font-light">${escapeHtml(link.url)}</p>
                ${link.description ? `<p class="card-desc text-gray-500/90 text-xs mb-3 line-clamp-2 leading-relaxed">${escapeHtml(link.description)}</p>` : ''}
                ${link.notes ? `<p class="card-notes text-gray-500/80 text-xs mb-4 line-clamp-2 italic font-light">${escapeHtml(link.notes)}</p>` : ''}
                <div class="flex items-center justify-between mb-3">
                    <div class="flex items-center gap-2">
                        <span class="category-badge"><span class="cat-dot" style="background:${accent}"></span>${escapeHtml(link.category)}</span>
                        ${visitCount > 0 ? `<span class="text-xs text-gray-500 flex items-center gap-1"><i data-lucide="eye" class="w-3 h-3"></i> ${visitCount}</span>` : ''}
                        ${link.healthStatus === 'healthy' ? `<span class="text-xs text-green-400 flex items-center gap-1" title="Link is healthy"><i data-lucide="check-circle" class="w-3 h-3"></i></span>` : ''}
                        ${link.healthStatus === 'broken' ? `<span class="text-xs text-red-400 flex items-center gap-1" title="Link may be broken"><i data-lucide="alert-circle" class="w-3 h-3"></i></span>` : ''}
                    </div>
                    <span class="text-xs text-gray-500">${formattedDate}</span>
                </div>
                ${tagsHtml ? `<div class="flex flex-wrap gap-2">${tagsHtml}</div>` : ''}
            </div>
        </div>
    `;
}

// Render category filters (links + Product Hunt tool categories, shared)
function renderCategoryFilters() {
    const container = document.getElementById('categoryFilters');
    const toolCats = (window.tools || []).map(t => t.cat).filter(Boolean);
    const categories = ['all', ...new Set([...links.map(link => link.category), ...toolCats])];

    container.innerHTML = categories.map(category => {
        const isActive = category === selectedCategory;
        const displayName = category === 'all' ? 'All' : category;
        return `
            <button 
                class="category-filter px-3 py-1.5 text-xs rounded-lg whitespace-nowrap glass-button ${isActive ? 'active' : ''}" 
                data-category="${category}"
            >
                ${escapeHtml(displayName)}
            </button>
        `;
    }).join('');

    // Add event listeners
    container.querySelectorAll('.category-filter').forEach(btn => {
        btn.addEventListener('click', () => {
            selectedCategory = btn.dataset.category;
            renderCategoryFilters();
            renderLinks();
        });
    });
}


// Debounced tag-cloud scheduler: a burst of renderLinks() calls (search keystrokes,
// selection toggles) collapses into a single aggregation pass.
let _tagCloudTimer = null;
function scheduleTagCloud() {
    if (_tagCloudTimer) return;
    _tagCloudTimer = setTimeout(() => {
        _tagCloudTimer = null;
        if (typeof renderTagCloud === 'function') renderTagCloud();
    }, 200);
}

// Render Tag Cloud (deferred to idle time for large datasets)
function renderTagCloud() {
    const tagContainer = document.getElementById('tagFilters');
    if (!tagContainer) return;

    const doRender = () => {
        // Aggregate tags
        const tagsMap = new Map();
        const searchInput = document.getElementById('searchInput');
        // Show tags from filtered links if search is active, otherwise all links
        const hasSearch = searchInput && searchInput.value.trim().length > 0;
        const sourceLinks = hasSearch ? currentFilteredLinks : links;

        // Safety check sourceLinks
        if (!Array.isArray(sourceLinks)) return;

        sourceLinks.forEach(link => {
            if (Array.isArray(link.tags)) {
                link.tags.forEach(tag => {
                    tagsMap.set(tag, (tagsMap.get(tag) || 0) + 1);
                });
            }
        });

        // Convert to array and sort
        const sortedTags = Array.from(tagsMap.entries())
            .sort((a, b) => b[1] - a[1]); // Sort by count desc (Show ALL tags)

        if (sortedTags.length === 0) {
            tagContainer.classList.add('hidden');
            return;
        }

        tagContainer.classList.remove('hidden');

        // Add "Clear All" if tags selected
        let html = '';

        if (selectedTags.size > 0) {
            html += `
                <button onclick="clearTagFilters()" 
                    class="px-2.5 py-1 rounded-full text-xs font-medium transition-all bg-red-500/20 text-red-300 border border-red-500/30 hover:bg-red-500/30 flex items-center shrink-0 whitespace-nowrap gap-1">
                    <i data-lucide="x" class="w-3 h-3"></i> Clear (${selectedTags.size})
                </button>
                <div class="w-px h-5 bg-white/10 mx-1 shrink-0"></div>
            `;
        }

        html += sortedTags.map(([tag, count]) => {
            const isSelected = selectedTags.has(tag);
            return `
                <button onclick="selectTagFilter('${tag}')" 
                    class="px-2.5 py-1 rounded-full text-[11px] font-medium transition-all flex items-center gap-1 shrink-0 whitespace-nowrap
                    ${isSelected
                    ? 'bg-red-500 text-white shadow-lg shadow-red-500/30 ring-1 ring-white/20'
                    : 'bg-white/5 text-gray-400 border border-white/10 hover:bg-white/10 hover:text-white hover:border-white/20'}">
                ${isSelected ? '<i data-lucide="check" class="w-3 h-3"></i>' : '#'}
                ${tag}
                <span class="${isSelected ? 'text-white/70' : 'text-gray-600'} text-[10px] ml-0.5">${count}</span>
            </button>
        `;
        }).join('');

        tagContainer.innerHTML = html;
        if (typeof lucide !== 'undefined') lucide.createIcons();
    };

    // Always defer the aggregation to idle time so a large tag scan never
    // blocks the calling frame (setTimeout/rAF violation).
    if (typeof requestIdleCallback !== 'undefined') {
        requestIdleCallback(doRender, { timeout: 250 });
    } else {
        setTimeout(doRender, 0);
    }
}

// Select Tag Filter (Toggle)
function selectTagFilter(tag) {
    if (selectedTags.has(tag)) {
        selectedTags.delete(tag);
    } else {
        selectedTags.add(tag);
    }
    renderLinks();
}

// Clear all tag filters
function clearTagFilters() {
    selectedTags.clear();
    renderLinks();
}

// Phase 2/6: Show similar links modal (Find similar)
function showSimilarLinksModal(linkId) {
    const link = links.find(l => l.id === linkId);
    if (!link) return;
    const similar = typeof window.findSimilarLinks === 'function' ? window.findSimilarLinks(link, 8) : [];
    const existing = document.getElementById('similarLinksModal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'similarLinksModal';
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm';
    modal.innerHTML = `
        <div class="glass-card w-full max-w-md max-h-[80vh] overflow-hidden flex flex-col">
            <div class="p-4 border-b border-white/10 flex items-center justify-between">
                <h3 class="text-lg font-bold text-white flex items-center gap-2"><i data-lucide="git-branch" class="w-5 h-5 text-red-400"></i> Similar to "${escapeHtml(link.title)}"</h3>
                <button type="button" onclick="this.closest('#similarLinksModal').remove()" class="text-gray-400 hover:text-white"><i data-lucide="x" class="w-5 h-5"></i></button>
            </div>
            <div class="p-4 overflow-y-auto flex-1">
                ${similar.length > 0 ? similar.map(l => `
                    <a href="${escapeHtml(l.url)}" target="_blank" rel="noopener" onclick="visitLink('${escapeHtml(l.url)}', '${l.id}', event); this.closest('#similarLinksModal').remove();" class="block p-3 rounded-lg bg-white/5 hover:bg-white/10 border border-white/5 mb-2 transition-colors">
                        <div class="font-medium text-white truncate">${escapeHtml(l.title)}</div>
                        <div class="text-xs text-gray-500 truncate">${escapeHtml(l.url)}</div>
                    </a>
                `).join('') : '<p class="text-gray-500 text-sm">No similar links found.</p>'}
            </div>
        </div>
    `;
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    document.body.appendChild(modal);
    initializeIcons();
}

// Escape HTML to prevent XSS — regex-based (no DOM element allocation per call)
const _ESCAPE_HTML_RE = /[&<>"]/g;
const _ESCAPE_HTML_MAP = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' };
function escapeHtml(text) {
    if (text == null) return '';
    return String(text).replace(_ESCAPE_HTML_RE, c => _ESCAPE_HTML_MAP[c]);
}

// Toast notification system
const toastQueue = [];
let isToastActive = false;

function showToast(message, type = 'success') {
    toastQueue.push({ message, type });
    if (!isToastActive) {
        processToastQueue();
    }
}

function processToastQueue() {
    if (toastQueue.length === 0) {
        isToastActive = false;
        return;
    }

    isToastActive = true;
    const { message, type } = toastQueue.shift();

    const toast = document.getElementById('toast');
    const toastMessage = document.getElementById('toastMessage');
    const toastIcon = document.getElementById('toastIcon');

    if (!toast || !toastMessage || !toastIcon) {
        isToastActive = false;
        return;
    }

    toastMessage.textContent = message;

    const iconName = type === 'success' ? 'check-circle' : type === 'error' ? 'x-circle' : type === 'warning' ? 'alert-circle' : 'info';
    toastIcon.setAttribute('data-lucide', iconName);

    const colors = {
        success: 'text-green-400',
        error: 'text-red-400',
        info: 'text-blue-400',
        warning: 'text-red-400'
    };

    toastIcon.className = 'w-5 h-5 ' + (colors[type] || colors.success);

    // Hide first in case it's lingering
    toast.classList.remove('show');

    // Force reflow
    void toast.offsetWidth;

    // Show new toast
    toast.classList.add('show');
    if (window.initializeIcons) initializeIcons();

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(processToastQueue, 400); // wait for exit animation
    }, 3000);
}

// ==================== Infinite Scroll & Performance ====================

function setupSentinel() {
    // Remove existing sentinel
    const existingSentinel = document.getElementById('scrollSentinel');
    if (existingSentinel) existingSentinel.remove();

    // If we have rendered all links, don't add sentinel
    if (renderedCount >= currentFilteredLinks.length) return;

    // Create new sentinel
    const sentinel = document.createElement('div');
    sentinel.id = 'scrollSentinel';
    sentinel.className = 'h-20 w-full flex items-center justify-center'; // height for easier intersection
    sentinel.innerHTML = '<div class="w-6 h-6 border-2 border-red-500 border-t-transparent rounded-full animate-spin"></div>';

    // Append to current view container
    let container = null;
    if (currentView === 'grid') container = document.getElementById('linksGrid');
    else if (currentView === 'list') container = document.getElementById('linksList');
    else if (currentView === 'timeline') container = document.getElementById('linksTimeline');
    else if (currentView === 'gallery') container = document.getElementById('linksGallery');

    if (container) {
        container.appendChild(sentinel);

        // Setup observer
        if (infiniteScrollObserver) infiniteScrollObserver.disconnect();

        infiniteScrollObserver = new IntersectionObserver((entries) => {
            if (entries[0].isIntersecting) {
                // Remove sentinel before rendering next batch to avoid duplicate triggering
                sentinel.remove();
                renderNextBatch();
            }
        }, { rootMargin: '200px' }); // Preload when 200px away

        infiniteScrollObserver.observe(sentinel);
    }
}

function renderNextBatch() {
    const batch = currentFilteredLinks.slice(renderedCount, renderedCount + BATCH_SIZE);
    if (batch.length === 0) return;

    let container = null;
    let html = '';

    if (currentView === 'grid') {
        container = document.getElementById('linksGrid');
        html = batch.map(link => createLinkCard(link)).join('');
    } else if (currentView === 'list') {
        container = document.getElementById('linksList');
        html = batch.map(link => createListCard(link)).join('');
    } else if (currentView === 'timeline') {
        container = document.getElementById('linksTimeline');
        // Timeline logic is complex (grouped by date), simply appending might break group structure.
        // For timeline, we might fallback to full render OR optimized group appending.
        // For now, let's treat timeline as non-virtualized or simple append (which might look weird if dates split).
        // Strategy: Just render all for timeline to avoid complexity, OR implement smart grouping.
        // Let's implement smart grouping for the batch.
        // Actually, simple append works providing we handle headers.
        // But headers might be duplicated if we blindly append. 
        // Let's Skip virtualization for Timeline for now to ensure correctness, or redo timeline render logic.
        // Plan: Only virtualize Grid and List and Gallery for now.
        // Fallback:
        renderTimelineBatch(batch);
        renderedCount += batch.length;
        setupSentinel();
        return;
    } else if (currentView === 'gallery') {
        container = document.getElementById('linksGallery');
        html = batch.map(link => createGalleryCard(link)).join('');
    }

    if (container) {
        // Parse the batch off-DOM, then move nodes in. This lets icon init touch
        // ONLY the new nodes instead of re-scanning every already-rendered card
        // (which becomes O(n^2) as thousands of cards accumulate).
        const holder = document.createElement('div');
        holder.innerHTML = html;
        const newIcons = Array.from(holder.querySelectorAll('[data-lucide]'));
        const newThumbs = Array.from(holder.querySelectorAll('[data-bg]'));
        while (holder.firstChild) container.appendChild(holder.firstChild);
        renderedCount += batch.length;

        // Defer thumbnail image loads until they approach the viewport
        if (newThumbs.length > 0) observeLazyTargets(newThumbs);

        if (newIcons.length > 0 && typeof lucide !== 'undefined') {
            requestAnimationFrame(() => lucide.createIcons({ nodes: newIcons }));
        }

        setupSentinel();
    }
}

// Track rendered timeline dates to avoid DOM queries
let _renderedTimelineDates = new Set();

function resetTimelineDateTracking() {
    _renderedTimelineDates.clear();
}

function renderTimelineBatch(batch) {
    const container = document.getElementById('linksTimeline');

    // Group this batch by date
    const grouped = {};
    batch.forEach(link => {
        const date = new Date(link.createdAt).toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric' });
        if (!grouped[date]) grouped[date] = [];
        grouped[date].push(link);
    });

    // Sort dates descending (for this batch)
    const sortedDates = Object.keys(grouped).sort((a, b) => new Date(b) - new Date(a));

    sortedDates.forEach(date => {
        if (_renderedTimelineDates.has(date)) {
            // Date group already rendered, append to its grid
            const grid = container.querySelector(`[data-timeline-date="${date}"] .grid`);
            if (grid) {
                const holder = document.createElement('div');
                holder.innerHTML = grouped[date].map(link => createLinkCard(link)).join('');
                const thumbs = Array.from(holder.querySelectorAll('[data-bg]'));
                while (holder.firstChild) grid.appendChild(holder.firstChild);
                observeLazyTargets(thumbs);
            }
            return;
        }

        // First time rendering this date - create new group
        _renderedTimelineDates.add(date);
        const holder = document.createElement('div');
        holder.innerHTML = `
        <div class="mb-8 fade-in" data-timeline-date="${date}">
            <h3 class="text-xl font-semibold text-white mb-4 flex items-center gap-2">
                <i data-lucide="calendar" class="w-5 h-5"></i>
                ${date}
            </h3>
            <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                ${grouped[date].map(link => createLinkCard(link)).join('')}
            </div>
        </div>`;
        const thumbs = Array.from(holder.querySelectorAll('[data-bg]'));
        while (holder.firstChild) container.appendChild(holder.firstChild);
        observeLazyTargets(thumbs);
    });

    // Initialize icons only for new elements
    requestAnimationFrame(() => {
        if (typeof lucide !== 'undefined') {
            const newElements = container.querySelectorAll('[data-lucide]:not([data-lucide-initialized])');
            newElements.forEach(el => el.setAttribute('data-lucide-initialized', 'true'));
            if (newElements.length > 0) {
                lucide.createIcons({ nodes: Array.from(newElements) });
            }
        }
    });
}

// Reset tracking when view changes or full re-render
function resetTimelineDateTracking() {
    _renderedTimelineDates.clear();
}


// ==================== Storage Management ====================

// Open storage modal
async function openStorageModal() {
    const modal = document.getElementById('storageModal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    await updateStorageStats();
    await loadStoragePrompt();
    renderPrompts();
    initializeIcons();
    updateLastBackupDate();
}

// Close storage modal
function closeStorageModal() {
    const modal = document.getElementById('storageModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
    saveStoragePrompt();
}

// Update storage statistics
async function updateStorageStats() {
    const totalLinks = links.length;
    const linksWithImages = links.filter(l => l.image).length;
    const totalPrompts = prompts.length;

    // Calculate estimated storage size
    let estimatedSize = 0;
    links.forEach(link => {
        estimatedSize += JSON.stringify(link).length;
        if (link.image) {
            estimatedSize += link.image.length;
        }
    });

    prompts.forEach(prompt => {
        estimatedSize += JSON.stringify(prompt).length;
    });

    const sizeInKB = (estimatedSize / 1024).toFixed(2);
    const sizeInMB = (estimatedSize / (1024 * 1024)).toFixed(2);
    const sizeInGB = (estimatedSize / (1024 * 1024 * 1024)).toFixed(4);

    let displaySize;
    if (sizeInGB >= 1) {
        displaySize = `${sizeInGB} GB`;
    } else if (sizeInMB >= 1) {
        displaySize = `${sizeInMB} MB`;
    } else {
        displaySize = `${sizeInKB} KB`;
    }

    // 10GB limit
    const limitGB = 10;
    const limitBytes = limitGB * 1024 * 1024 * 1024;
    const percentage = Math.min((estimatedSize / limitBytes) * 100, 100).toFixed(2);

    document.getElementById('storageTotalLinks').textContent = totalLinks;
    document.getElementById('storageLinksWithImages').textContent = linksWithImages;
    document.getElementById('storageTotalPrompts').textContent = totalPrompts;
    document.getElementById('storageSize').textContent = displaySize;
    document.getElementById('storagePercentage').textContent = `${percentage}%`;
    document.getElementById('storageBar').style.width = `${percentage}%`;

    const lastBackupEl = document.getElementById('lastBackupDate');
    if (lastBackupEl) {
        const last = localStorage.getItem('linkLumina_lastExport');
        lastBackupEl.textContent = last ? new Date(last).toLocaleString() : 'Never';
    }
}

// Load storage prompt
async function loadStoragePrompt() {
    const prompt = await getMetadata('storagePrompt');
    if (prompt) {
        document.getElementById('storagePrompt').value = prompt;
    }
}

// Save storage prompt
async function saveStoragePrompt() {
    const prompt = document.getElementById('storagePrompt').value;
    await setMetadata('storagePrompt', prompt);
}

// Optimize storage by removing images from old/unused links
async function optimizeStorage() {
    if (!confirm('This will remove images from links that haven\'t been visited recently. Continue?')) {
        return;
    }

    const thirtyDaysAgo = new Date();
    thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

    let removed = 0;
    for (const link of links) {
        if (link.image && (!link.lastVisited || new Date(link.lastVisited) < thirtyDaysAgo)) {
            link.image = null;
            await saveSingleLink(link);
            removed++;
        }
    }

    if (removed > 0) {
        renderLinks();
        await updateStorageStats();
        showToast(`Removed images from ${removed} unused link(s)`, 'success');
    } else {
        showToast('No images to optimize', 'info');
    }
}

// Clear all images
async function clearAllImages() {
    if (!confirm('This will remove ALL cover images from all links. This action cannot be undone. Continue?')) {
        return;
    }

    let removed = 0;
    for (const link of links) {
        if (link.image) {
            link.image = null;
            await saveSingleLink(link);
            removed++;
        }
    }

    if (removed > 0) {
        renderLinks();
        await updateStorageStats();
        showToast(`Removed images from ${removed} link(s)`, 'success');
    } else {
        showToast('No images to remove', 'info');
    }
}

// Export backup
async function exportBackup() {
    const storagePrompt = await getMetadata('storagePrompt') || '';
    const backup = {
        links: links,
        prompts: prompts,
        storagePrompt: storagePrompt,
        exportDate: new Date().toISOString(),
        version: '2.0'
    };

    const dataStr = JSON.stringify(backup, null, 2);
    const dataBlob = new Blob([dataStr], { type: 'application/json' });
    const url = URL.createObjectURL(dataBlob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `linklumina-backup-${new Date().toISOString().split('T')[0]}.json`;
    link.click();
    URL.revokeObjectURL(url);
    showToast('Backup created successfully!', 'success');
}

// Clear all data
async function clearAllData() {
    if (!confirm('WARNING: This will permanently delete ALL links, prompts, and data. This cannot be undone! Type "DELETE" to confirm.')) {
        return;
    }

    const confirmation = prompt('Type "DELETE" to confirm permanent deletion:');
    if (confirmation !== 'DELETE') {
        showToast('Deletion cancelled', 'info');
        return;
    }

    // Delete all links from IndexedDB
    for (const link of links) {
        await deleteLinkFromDB(link.id);
    }

    // Delete all prompts from IndexedDB
    for (const prompt of prompts) {
        await deletePromptFromDB(prompt.id);
    }

    links = [];
    prompts = [];
    selectedLinks.clear();
    bumpDataVersion();

    renderLinks();
    renderCategoryFilters();
    renderPrompts();
    await updateStorageStats();
    closeStorageModal();
    showToast('All data cleared', 'success');
}

// ==================== View Rendering Functions ====================

// Switch view mode
function switchView(view) {
    currentView = view;
    localStorage.setItem('linkLumina_view', view);

    // Reset timeline tracking when switching views
    if (typeof resetTimelineDateTracking === 'function') resetTimelineDateTracking();

    // Update button states (segmented control; active style comes from .seg-btn.active)
    document.querySelectorAll('[data-view]').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.view === view);
    });

    // Hide all views
    document.getElementById('linksGrid').classList.add('hidden');
    document.getElementById('linksList').classList.add('hidden');
    document.getElementById('linksTimeline').classList.add('hidden');
    document.getElementById('linksGallery').classList.add('hidden');

    // Show selected view
    const viewMap = { grid: 'linksGrid', list: 'linksList', timeline: 'linksTimeline', gallery: 'linksGallery' };
    const container = document.getElementById(viewMap[view]);
    if (container) container.classList.remove('hidden');

    renderLinks();
    initializeIcons();
}

// Show keyboard shortcuts help
function showKeyboardShortcuts() {
    const shortcuts = [
        { key: 'Ctrl + N', action: 'Add new link' },
        { key: 'Ctrl + F', action: 'Focus search' },
        { key: 'Ctrl + S', action: 'Quick save' },
        { key: 'Ctrl + K', action: 'Command palette' },
        { key: 'Escape', action: 'Close modal / Exit selection' },
        { key: '?', action: 'Show this help' },
    ];

    const html = shortcuts.map(s =>
        `<div class="flex justify-between py-2 border-b border-white/10">
            <kbd class="px-2 py-1 bg-white/10 rounded text-red-300 font-mono text-sm">${s.key}</kbd>
            <span class="text-gray-300">${s.action}</span>
        </div>`
    ).join('');

    showToast('⌨️ Keyboard Shortcuts', 'info', 5000);

    // Create a mini popup
    const popup = document.createElement('div');
    popup.id = 'shortcutsPopup';
    popup.className = 'fixed top-1/2 left-1/2 transform -translate-x-1/2 -translate-y-1/2 z-[100] glass-card p-6 w-80 animate-fadeIn';
    popup.innerHTML = `
        <div class="flex justify-between items-center mb-4">
            <h3 class="text-lg font-bold text-white">⌨️ Keyboard Shortcuts</h3>
            <button onclick="this.parentElement.parentElement.remove()" class="text-gray-400 hover:text-white">
                <i data-lucide="x" class="w-5 h-5"></i>
            </button>
        </div>
        ${html}
    `;

    // Remove existing popup if any
    document.getElementById('shortcutsPopup')?.remove();
    document.body.appendChild(popup);
    initializeIcons();

    // Auto close after 5 seconds
    setTimeout(() => popup.remove(), 5000);
}

// Render grid view (existing)
// Setup grid view
function setupGridView(count) {
    const grid = document.getElementById('linksGrid');
    const emptyState = document.getElementById('emptyState');

    // Hide other views
    document.getElementById('linksList').classList.add('hidden');
    document.getElementById('linksTimeline').classList.add('hidden');
    document.getElementById('linksGallery').classList.add('hidden');

    if (count === 0) {
        grid.classList.add('hidden');
        emptyState.classList.remove('hidden');
        initializeIcons();
        return;
    }

    grid.classList.remove('hidden');
    emptyState.classList.add('hidden');

    // Clear content for fresh render
    grid.innerHTML = '';
}

// Render list view
// Setup list view
function setupListView(count) {
    const list = document.getElementById('linksList');
    const emptyState = document.getElementById('emptyState');

    // Hide other views
    document.getElementById('linksGrid').classList.add('hidden');
    document.getElementById('linksTimeline').classList.add('hidden');
    document.getElementById('linksGallery').classList.add('hidden');

    if (count === 0) {
        list.classList.add('hidden');
        emptyState.classList.remove('hidden');
        initializeIcons();
        return;
    }

    list.classList.remove('hidden');
    emptyState.classList.add('hidden');

    // Clear content
    list.innerHTML = '';
}

// Render timeline view
// Setup timeline view
function setupTimelineView(count) {
    const timeline = document.getElementById('linksTimeline');
    const emptyState = document.getElementById('emptyState');

    // Hide other views
    document.getElementById('linksGrid').classList.add('hidden');
    document.getElementById('linksList').classList.add('hidden');
    document.getElementById('linksGallery').classList.add('hidden');

    if (count === 0) {
        timeline.classList.add('hidden');
        emptyState.classList.remove('hidden');
        initializeIcons();
        return;
    }

    timeline.classList.remove('hidden');
    emptyState.classList.add('hidden');

    // Clear content
    timeline.innerHTML = '';
}

// Render gallery view
// Setup gallery view
function setupGalleryView(count) {
    const gallery = document.getElementById('linksGallery');
    const emptyState = document.getElementById('emptyState');

    // Hide other views
    document.getElementById('linksGrid').classList.add('hidden');
    document.getElementById('linksList').classList.add('hidden');
    document.getElementById('linksTimeline').classList.add('hidden');

    if (count === 0) {
        gallery.classList.add('hidden');
        emptyState.classList.remove('hidden');
        initializeIcons();
        return;
    }

    gallery.classList.remove('hidden');
    emptyState.classList.add('hidden');

    // Clear content
    gallery.innerHTML = '';
}

// Create list card
function createListCard(link) {
    const tagsHtml = link.tags.length > 0
        ? link.tags.map(tag => `<span class="tag">#${highlightMatches(tag, _activeHighlightTerms)}</span>`).join('')
        : '';

    const accent = getCategoryColor(link.category) || link.accentColor || neonColors[0];
    const thumbStyle = link.image
        ? `data-bg="${escapeHtml(link.image)}" style="background-color: rgba(255,255,255,0.04); background-size: cover; background-position: center;"`
        : `style="background: linear-gradient(135deg, ${accent}60, ${accent}30);"`;

    return `
        <div class="glass-card p-4 flex items-center gap-4 hover:bg-white/10 transition-all group" style="--cat-color: ${accent}">
            <div class="w-16 h-16 rounded-lg overflow-hidden flex-shrink-0" ${thumbStyle}>
                ${!link.image ? `<div class="w-full h-full flex items-center justify-center"><i data-lucide="link" class="w-8 h-8 text-white/40"></i></div>` : ''}
            </div>
            <div class="flex-1 min-w-0">
                <h3 class="text-white font-semibold truncate">${highlightMatches(link.title, _activeHighlightTerms)}</h3>
                <p class="text-gray-400 text-sm truncate">${escapeHtml(link.url)}</p>
                <div class="flex items-center gap-2 mt-2">
                    <span class="category-badge"><span class="cat-dot" style="background:${accent}"></span>${escapeHtml(link.category)}</span>
                    ${tagsHtml ? `<div class="flex flex-wrap gap-1">${tagsHtml}</div>` : ''}
                </div>
            </div>
            <div class="flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onclick="visitLink('${escapeHtml(link.url)}', '${link.id}', event)" class="p-2 rounded-lg bg-green-500/20 hover:bg-green-500/30 text-green-300">
                    <i data-lucide="external-link" class="w-4 h-4"></i>
                </button>
                <button onclick="openModal('${link.id}')" class="p-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300">
                    <i data-lucide="edit" class="w-4 h-4"></i>
                </button>
                <button onclick="deleteLink('${link.id}', event)" class="p-2 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300">
                    <i data-lucide="trash-2" class="w-4 h-4"></i>
                </button>
            </div>
        </div>
    `;
}

// Create gallery card
function createGalleryCard(link) {
    const accent = getCategoryColor(link.category) || link.accentColor || neonColors[0];
    const media = link.image
        ? `<img src="${escapeHtml(link.image)}" alt="${escapeHtml(link.title)}" loading="lazy" decoding="async" class="w-full h-full object-cover transition-transform duration-300 group-hover:scale-110">`
        : `<div class="w-full h-full flex items-center justify-center" style="background: linear-gradient(135deg, ${accent}60, ${accent}30, ${accent}10);"><i data-lucide="link" class="w-12 h-12 text-white/40"></i></div>`;
    return `
        <div class="glass-card p-0 overflow-hidden group cursor-pointer relative" style="--cat-color: ${accent}" onclick="visitLink('${escapeHtml(link.url)}', '${link.id}', event)">
            <div class="cat-accent" aria-hidden="true"></div>
            <div class="aspect-square relative overflow-hidden">
                ${media}
                <div class="absolute inset-0 bg-gradient-to-t from-black/80 via-transparent to-transparent opacity-0 group-hover:opacity-100 transition-opacity">
                    <div class="absolute bottom-0 left-0 right-0 p-3">
                        <h4 class="text-white font-semibold text-sm line-clamp-1">${highlightMatches(link.title, _activeHighlightTerms)}</h4>
                    </div>
                </div>
            </div>
        </div>
    `;
}

// ==================== Link Health Monitoring ====================

// Check link health
async function checkLinkHealth(url) {
    if (linkHealthCache.has(url)) {
        return linkHealthCache.get(url);
    }

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);

        await fetch(url, {
            method: 'HEAD',
            mode: 'no-cors',
            signal: controller.signal
        });

        clearTimeout(timeoutId);
        linkHealthCache.set(url, 'healthy');
        return 'healthy';
    } catch (error) {
        linkHealthCache.set(url, 'unknown');
        return 'unknown';
    }
}

// Batch check link health
async function batchCheckLinkHealth() {
    if (!confirm('This will check all links for accessibility. This may take a while. Continue?')) {
        return;
    }

    showToast('Checking link health... This may take a while.', 'info');
    let checked = 0;
    let healthy = 0;

    for (const link of links) {
        try {
            const controller = new AbortController();
            const timeoutId = setTimeout(() => controller.abort(), 5000);

            try {
                await fetch(link.url, {
                    method: 'HEAD',
                    mode: 'no-cors',
                    signal: controller.signal
                });
                link.healthStatus = 'healthy';
                healthy++;
            } catch (error) {
                link.healthStatus = 'broken';
            }

            clearTimeout(timeoutId);
        } catch (error) {
            link.healthStatus = 'broken';
        }

        await saveLinkToDB(link);
        checked++;

        if (checked % 10 === 0) {
            renderLinks();
        }
    }

    renderLinks();
    showToast(`Health check complete: ${checked} links checked (${healthy} healthy)`, 'success');
}

// ==================== Collections (Basic Implementation) ====================

// Collections are stored as tags/categories for now
// Full collection system can be added later if needed

// ==================== New Features ====================

// Random Link - "I'm Feeling Lucky"
function openRandomLink() {
    if (links.length === 0) {
        showToast('No links available!', 'error');
        return;
    }

    const randomIndex = Math.floor(Math.random() * links.length);
    const randomLink = links[randomIndex];

    visitLink(randomLink.url, randomLink.id);
    showToast(`Opening: ${randomLink.title}`, 'success');
}

// Keyboard Shortcuts Modal
function openShortcutsModal() {
    const modal = document.getElementById('shortcutsModal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    initializeIcons();
}

function closeShortcutsModal() {
    const modal = document.getElementById('shortcutsModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

// Duplicates Finder
function openDuplicatesModal() {
    const modal = document.getElementById('duplicatesModal');
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    renderDuplicates();
    initializeIcons();
}

function closeDuplicatesModal() {
    const modal = document.getElementById('duplicatesModal');
    modal.classList.add('hidden');
    document.body.style.overflow = '';
}

function findDuplicates() {
    const urlMap = new Map();
    const duplicates = [];

    links.forEach(link => {
        // Normalize URL (remove trailing slashes, www, etc.)
        const normalizedUrl = link.url
            .toLowerCase()
            .replace(/^https?:\/\//, '')
            .replace(/^www\./, '')
            .replace(/\/$/, '');

        if (urlMap.has(normalizedUrl)) {
            const existing = urlMap.get(normalizedUrl);
            if (!duplicates.includes(existing)) {
                duplicates.push(existing);
            }
            duplicates.push(link);
        } else {
            urlMap.set(normalizedUrl, link);
        }
    });

    return duplicates;
}

function renderDuplicates() {
    const content = document.getElementById('duplicatesContent');
    const duplicates = findDuplicates();

    if (duplicates.length === 0) {
        content.innerHTML = `
            <div class="text-center py-8">
                <i data-lucide="check-circle" class="w-16 h-16 mx-auto text-green-400 mb-4"></i>
                <p class="text-xl font-semibold text-white mb-2">No Duplicates Found!</p>
                <p class="text-gray-400">Your link collection is clean.</p>
            </div>
        `;
        initializeIcons();
        return;
    }

    // Group duplicates by normalized URL
    const groups = new Map();
    duplicates.forEach(link => {
        const normalizedUrl = link.url
            .toLowerCase()
            .replace(/^https?:\/\//, '')
            .replace(/^www\./, '')
            .replace(/\/$/, '');

        if (!groups.has(normalizedUrl)) {
            groups.set(normalizedUrl, []);
        }
        groups.get(normalizedUrl).push(link);
    });

    content.innerHTML = `
        <div class="mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
            <p class="text-red-300 text-sm">
                <i data-lucide="alert-triangle" class="inline w-4 h-4 mr-1"></i>
                Found ${duplicates.length} duplicate links in ${groups.size} group(s)
            </p>
        </div>
        <div class="space-y-4">
            ${Array.from(groups.entries()).map(([url, group]) => `
                <div class="p-4 rounded-lg bg-white/5 border border-white/10">
                    <p class="text-gray-400 text-sm mb-3 truncate">${url}</p>
                    <div class="space-y-2">
                        ${group.map(link => `
                            <div class="flex items-center justify-between p-2 rounded bg-white/5">
                                <div class="flex items-center gap-2 flex-1 min-w-0">
                                    <img src="${link.favicon || ''}" class="w-4 h-4" onerror="this.style.display='none'">
                                    <span class="text-white truncate">${escapeHtml(link.title)}</span>
                                    <span class="text-xs text-gray-500">${new Date(link.createdAt).toLocaleDateString()}</span>
                                </div>
                                <button 
                                    onclick="deleteDuplicateLink('${link.id}')"
                                    class="p-1.5 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300 ml-2"
                                    title="Delete this duplicate"
                                >
                                    <i data-lucide="trash-2" class="w-4 h-4"></i>
                                </button>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `).join('')}
        </div>
    `;

    initializeIcons();
}

async function deleteDuplicateLink(id) {
    if (confirm('Delete this duplicate link?')) {
        links = links.filter(link => link.id !== id);
        await deleteLinkFromDB(id);
        renderDuplicates();
        renderLinks();
        showToast('Duplicate removed!', 'success');
    }
}

// Toggle Pin Link
async function togglePinLink(id, event = null) {
    if (event) event.stopPropagation();

    const link = links.find(l => l.id === id);
    if (link) {
        link.pinned = !link.pinned;
        await saveSingleLink(link);
        renderLinks();
        showToast(link.pinned ? 'Link pinned!' : 'Link unpinned!', 'success');
    }
}

// Toggle Read Status (Reading List)
async function toggleReadStatus(id, event = null) {
    if (event) event.stopPropagation();

    const link = links.find(l => l.id === id);
    if (link) {
        link.isRead = !link.isRead;
        await saveSingleLink(link);
        renderLinks();
        showToast(link.isRead ? 'Marked as read' : 'Marked as unread', 'success');
    }
}

// Setup new feature event listeners
function setupNewFeatureListeners() {
    // Random Link
    document.getElementById('randomLinkBtn').addEventListener('click', openRandomLink);

    // Keyboard Shortcuts
    document.getElementById('keyboardShortcutsBtn').addEventListener('click', openShortcutsModal);
    document.getElementById('closeShortcuts').addEventListener('click', closeShortcutsModal);
    document.getElementById('shortcutsOverlay').addEventListener('click', closeShortcutsModal);

    // Duplicates
    document.getElementById('findDuplicatesBtn').addEventListener('click', openDuplicatesModal);
    document.getElementById('closeDuplicates').addEventListener('click', closeDuplicatesModal);
    document.getElementById('duplicatesOverlay').addEventListener('click', closeDuplicatesModal);

    // Decision Modal Listeners
    document.getElementById('closeDecisionModal').addEventListener('click', closeDecisionModal);
    document.getElementById('decisionOverlay').addEventListener('click', closeDecisionModal);
    document.getElementById('cancelDecisionBtn').addEventListener('click', closeDecisionModal);
    document.getElementById('saveDecisionBtn').addEventListener('click', handleSaveDecision);

    // Import/Export Listeners
    // Export Excel (labeled as CSV in UI for now)
    const exportCsvBtn = document.getElementById('exportCsvBtn');
    if (exportCsvBtn) exportCsvBtn.addEventListener('click', exportLinks);

    // Export/import buttons are bound in setupEventListeners/setupDataTransferListeners.

    // Tools & Data Listeners
    // Analytics (real dashboard is bound in setupEventListeners; removed stale alert stub here)
    // Feature Hub button
    const featureHubBtn = document.getElementById('featureHubBtn');
    if (featureHubBtn && window.AppFeatures) {
        featureHubBtn.addEventListener('click', () => window.AppFeatures.openHub());
    }

    // Link card "More" dropdown (mobile): toggle on button click, close on outside click
    document.addEventListener('click', (e) => {
        document.querySelectorAll('.link-card-more-dropdown').forEach(el => el.classList.add('hidden'));
        const btn = e.target.closest('.link-card-more-btn');
        if (btn) {
            e.stopPropagation();
            const wrap = btn.closest('.link-card-more-wrap');
            const dd = wrap && wrap.querySelector('.link-card-more-dropdown');
            if (dd) dd.classList.toggle('hidden');
        }
    });

    // Batch "More" dropdown (mobile floating bar)
    const batchMoreBtn = document.getElementById('batchMoreBtn');
    const floatingBarMore = document.getElementById('floatingBarMoreDropdown');
    if (batchMoreBtn && floatingBarMore) {
        batchMoreBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            floatingBarMore.classList.toggle('hidden');
            if (!floatingBarMore.classList.contains('hidden') && window.lucide) lucide.createIcons();
        });
    }
    document.addEventListener('click', (e) => {
        const floatingBarMore = document.getElementById('floatingBarMoreDropdown');
        if (floatingBarMore && !e.target.closest('#floatingBarMoreDropdown') && !e.target.closest('#batchMoreBtn')) {
            floatingBarMore.classList.add('hidden');
        }
    });
    document.addEventListener('click', (e) => {
        const btn = e.target.closest('.batch-more-action');
        if (!btn) return;
        const action = btn.getAttribute('data-action');
        document.getElementById('floatingBarMoreDropdown').classList.add('hidden');
        if (action === 'move') document.getElementById('batchMoveBtn').click();
        else if (action === 'magic') bulkMagicEnhance();
        else if (action === 'favorite') bulkFavoriteAll();
        else if (action === 'category') bulkSetCategory();
        else if (action === 'bulkedit') openBulkEditModal();
        else if (action === 'delete') bulkDelete();
    });

    // Neural Web
    const neuralWebBtn = document.getElementById('neuralWebBtn');
    if (neuralWebBtn && typeof window.initNeuralWeb === 'function') {
        neuralWebBtn.addEventListener('click', window.initNeuralWeb); // Ensure initNeuralWeb is attached to window in neural.js or implicitly global
    } else if (neuralWebBtn) {
        // Fallback if neural.js isn't ready
        neuralWebBtn.addEventListener('click', () => {
            if (typeof initNeuralWeb === 'function') initNeuralWeb();
            else showToast('Neural Web module loading...', 'info');
        });
    }

    // Storage Info
    const storageBtn = document.getElementById('storageBtn');
    if (storageBtn) {
        storageBtn.addEventListener('click', () => {
            const usage = (JSON.stringify(localStorage).length / 1024).toFixed(2);
            alert(`💾 Storage Info:\n\nLocal Storage Usage: ~${usage} KB\nIndexedDB: Active\n\nCloud Sync: ${localStorage.getItem('syncRoomCode') ? 'Active' : 'Inactive'}`);
        });
    }


    // Advisory Listener
    document.getElementById('decisionTitle').addEventListener('input', debounce((e) => {
        checkDecisionAdvisory(e.target.value);
    }, 500));
}

// Decision Advisory Logic
function checkDecisionAdvisory(query) {
    if (!window.findSimilarDecisions) return;

    const container = document.getElementById('decisionAdvisory');
    const list = document.getElementById('decisionAdvisoryList');

    const similar = window.findSimilarDecisions(query);

    if (similar.length > 0) {
        container.classList.remove('hidden');
        list.innerHTML = similar.map(e => {
            const status = e.context?.snapshot?.status || 'pending';
            const color = status === 'success' ? 'text-green-400' : status === 'failure' ? 'text-red-400' : 'text-red-400';
            return `
                <div class="text-sm p-2 rounded bg-black/20 border border-white/5 hover:bg-white/5 transition-colors cursor-pointer" onclick="showTimelineEventDetail('${e.id}')">
                    <div class="flex items-center justify-between">
                        <span class="text-gray-300 font-medium">${e.title}</span>
                        <span class="text-xs ${color} capitalize">${status}</span>
                    </div>
                    <p class="text-xs text-gray-500 truncate">${e.context?.snapshot?.lessons || e.context?.snapshot?.reasoning || 'No details'}</p>
                </div>
            `;
        }).join('');
    } else {
        container.classList.add('hidden');
    }
}

// Decision Modal Logic
window.openDecisionModal = function () {
    const modal = document.getElementById('decisionModal');
    const content = document.getElementById('decisionModalContent');
    modal.classList.remove('hidden');
    requestAnimationFrame(() => {
        content.classList.remove('scale-95', 'opacity-0');
        content.classList.add('scale-100', 'opacity-100');
    });
    document.getElementById('decisionTitle').focus();
};

window.closeDecisionModal = function () {
    const modal = document.getElementById('decisionModal');
    const content = document.getElementById('decisionModalContent');
    content.classList.remove('scale-100', 'opacity-100');
    content.classList.add('scale-95', 'opacity-0');
    setTimeout(() => {
        modal.classList.add('hidden');
        // Reset form
        document.getElementById('decisionTitle').value = '';
        document.getElementById('decisionReasoning').value = '';
        document.getElementById('decisionContext').value = '';
        document.getElementById('decisionOutcome').value = '';
    }, 300);
};

window.handleSaveDecision = async function () {
    const title = document.getElementById('decisionTitle').value.trim();
    const reasoning = document.getElementById('decisionReasoning').value.trim();
    const contextStr = document.getElementById('decisionContext').value.trim();
    const outcome = document.getElementById('decisionOutcome').value.trim();

    if (!title || !reasoning) {
        showToast('Please provide a title and reasoning.', 'error');
        return;
    }

    const contextFactors = contextStr.split(',').map(s => s.trim()).filter(s => s);

    if (window.trackDecision) {
        await window.trackDecision(title, contextFactors, reasoning, outcome);
        showToast('Strategic Decision Logged!', 'success');
        closeDecisionModal();
    } else {
        console.error('trackDecision function not found in timeline.js');
    }
};

// Extended keyboard shortcuts
function setupExtendedKeyboardShortcuts() {
    document.addEventListener('keydown', (e) => {
        const inInput = e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.isContentEditable;

        // Esc - Close topmost modal
        if (e.key === 'Escape') {
            if (document.getElementById('commandPalette') && !document.getElementById('commandPalette').classList.contains('hidden')) {
                closeCommandPalette();
                e.preventDefault();
                return;
            }
            if (document.getElementById('addLinkModal') && !document.getElementById('addLinkModal').classList.contains('hidden')) {
                closeModal();
                e.preventDefault();
                return;
            }
            if (document.getElementById('quickSaveModal') && !document.getElementById('quickSaveModal').classList.contains('hidden')) {
                if (typeof closeQuickSave === 'function') closeQuickSave();
                e.preventDefault();
                return;
            }
            if (document.getElementById('translateModal') && !document.getElementById('translateModal').classList.contains('hidden')) {
                if (typeof closeTranslateModal === 'function') closeTranslateModal();
                e.preventDefault();
                return;
            }
            if (document.getElementById('batchMoveModal') && !document.getElementById('batchMoveModal').classList.contains('hidden')) {
                closeBatchMoveModal();
                e.preventDefault();
                return;
            }
            if (document.getElementById('bulkEditModal') && !document.getElementById('bulkEditModal').classList.contains('hidden')) {
                closeBulkEditModal();
                e.preventDefault();
                return;
            }
        }

        if (inInput) return;

        // ? - Show shortcuts
        if (e.key === '?' && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            openShortcutsModal();
        }

        // N - Add new link (when not in input)
        if (e.key === 'N' && !e.ctrlKey && !e.metaKey) {
            e.preventDefault();
            openModal(null);
        }

        // Ctrl+N - Add new link
        if ((e.ctrlKey || e.metaKey) && e.key === 'n') {
            e.preventDefault();
            openModal(null);
        }

        // Ctrl+R - Random link (override browser refresh)
        if ((e.ctrlKey || e.metaKey) && e.key === 'r') {
            e.preventDefault();
            openRandomLink();
        }
    });
}

// Make functions globally available for onclick handlers
window.deleteLink = deleteLink;
window.visitLink = visitLink;
window.openTranscriptModal = openTranscriptModal;
window.renderTranscriptTab = renderTranscriptTab;
window.initializeTranscriptTab = initializeTranscriptTab;
window.toggleFavorite = toggleFavorite;
window.copyLink = copyLink;
window.toggleLinkSelection = toggleLinkSelection;
window.openModal = openModal;
window.togglePinLink = togglePinLink;
window.toggleReadStatus = toggleReadStatus;
window.deleteDuplicateLink = deleteDuplicateLink;

// ==================== NEW FEATURES ====================
// Zen mode · Weekly recap · Activity feed · Trash · Bookmarklet · Duplicate check
// Each is registered in the Feature Hub below (registerAllFeatures).

/* ---------------- Activity Feed (EventBus → localStorage) ---------------- */
const ACTIVITY_KEY = 'linkLumina_activity';
const ACTIVITY_MAX = 200;
const ACTIVITY_ICONS = {
    'link:added': 'plus-circle', 'link:visited': 'eye', 'link:deleted': 'trash-2',
    'link:favorited': 'star', 'folder:created': 'folder-plus', 'decision:logged': 'zap',
    'timeline:event_added': 'git-branch', 'law:triggered': 'scale',
};

function recordActivity(type, label) {
    try {
        const raw = localStorage.getItem(ACTIVITY_KEY);
        const list = raw ? JSON.parse(raw) : [];
        list.unshift({ type, label: String(label || '').slice(0, 160), at: Date.now() });
        if (list.length > ACTIVITY_MAX) list.length = ACTIVITY_MAX;
        localStorage.setItem(ACTIVITY_KEY, JSON.stringify(list));
    } catch (e) { /* storage full — ignore */ }
}

function getActivity() {
    try { const raw = localStorage.getItem(ACTIVITY_KEY); return raw ? JSON.parse(raw) : []; }
    catch { return []; }
}

function setupActivityFeed() {
    if (!window.EventBus || !window.EVENTS) return;
    const E = window.EVENTS;
    const hook = (evt, labelFn) => window.EventBus.on(evt, (d) => {
        const item = d && (d.item || d.link);
        recordActivity(evt, labelFn(item, d));
    });
    hook(E.LINK_ADDED, (item) => (item && item.title) || 'Link added');
    hook(E.LINK_VISITED, (item) => (item && item.title) || 'Link opened');
    hook(E.LINK_DELETED, (item) => (item && item.title) || 'Link deleted');
    hook(E.FOLDER_CREATED, (item) => 'Folder created: ' + ((item && (item.name || item.folder && item.folder.name)) || '?'));
    hook(E.DECISION_LOGGED, (item) => (item && item.title) || 'Decision logged');
    hook(E.TIMELINE_EVENT_ADDED, (item) => 'Timeline event: ' + ((item && item.title) || '?'));
}

function activityLabel(type) {
    return {
        'link:added': 'Link added', 'link:visited': 'Link opened', 'link:deleted': 'Link deleted',
        'link:favorited': 'Favorited', 'folder:created': 'Folder created', 'decision:logged': 'Decision',
        'timeline:event_added': 'Timeline', 'law:triggered': 'Cognitive Law',
    }[type] || 'Activity';
}

function timeAgo(ts) {
    const s = Math.floor((Date.now() - ts) / 1000);
    if (s < 60) return 'just now';
    const m = Math.floor(s / 60); if (m < 60) return m + ' min ago';
    const h = Math.floor(m / 60); if (h < 24) return h + ' hr ago';
    const d = Math.floor(h / 24); return d + ' days ago';
}

function openActivityFeed() {
    const items = getActivity();
    const existing = document.getElementById('activityFeedModal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'activityFeedModal';
    modal.className = 'fixed inset-0 z-[9999] flex items-center justify-center p-4';
    modal.style.background = 'rgba(5,3,3,0.72)';
    modal.style.backdropFilter = 'blur(14px)';
    modal.style.animation = 'featureHubIn 0.25s both';
    modal.innerHTML = `
        <div class="glass-card w-full max-w-lg max-h-[80vh] flex flex-col overflow-hidden" style="animation:hubCardIn 0.3s cubic-bezier(0.16,1,0.3,1) both">
            <div class="p-5 border-b border-white/10 flex items-center justify-between">
                <h3 class="text-lg font-bold text-white flex items-center gap-2">
                    <i data-lucide="activity" class="w-5 h-5 text-red-400"></i> Activity Feed
                </h3>
                <button type="button" id="actFeedClose" class="feat-hub-close"><i data-lucide="x" class="w-5 h-5"></i></button>
            </div>
            <div class="p-4 overflow-y-auto flex-1 custom-scrollbar">
                ${items.length === 0 ? `<p class="text-center text-gray-500 py-10 text-sm">No activity yet. Save or open a link to start tracking.</p>` :
                `<div class="space-y-1">${items.map(a => `
                    <div class="flex items-center gap-3 px-3 py-2 rounded-xl hover:bg-white/5 transition-colors">
                        <span class="flex-shrink-0 grid place-items-center w-8 h-8 rounded-lg" style="background:rgba(239,68,68,0.12);color:#f87171">
                            <i data-lucide="${ACTIVITY_ICONS[a.type] || 'circle'}" class="w-4 h-4"></i>
                        </span>
                        <div class="flex-1 min-w-0">
                            <div class="text-sm text-gray-200 truncate">${escapeHtml(a.label)}</div>
                            <div class="text-[11px] text-gray-500">${activityLabel(a.type)}</div>
                        </div>
                        <span class="text-[11px] text-gray-500 shrink-0">${timeAgo(a.at)}</span>
                    </div>
                `).join('')}</div>`}
            </div>
            ${items.length ? `<div class="p-3 border-t border-white/10 flex justify-end">
                <button id="actFeedClear" class="text-xs text-gray-400 hover:text-red-400 px-3 py-1.5 rounded-lg hover:bg-red-500/10 transition-colors">Clear history</button>
            </div>` : ''}
        </div>
    `;
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    modal.querySelector('#actFeedClose').onclick = () => modal.remove();
    const clearBtn = modal.querySelector('#actFeedClear');
    if (clearBtn) clearBtn.onclick = () => { localStorage.removeItem(ACTIVITY_KEY); modal.remove(); showToast('Activity feed cleared', 'info'); };
    document.body.appendChild(modal);
    initializeIcons();
}

/* ---------------- Trash (soft delete + restore) ---------------- */
const TRASH_KEY = 'linkLumina_trash';

function getTrash() {
    try { const raw = localStorage.getItem(TRASH_KEY); return raw ? JSON.parse(raw) : []; }
    catch { return []; }
}

function saveTrash(list) {
    try { localStorage.setItem(TRASH_KEY, JSON.stringify(list.slice(0, 100))); } catch (e) { /* ignore */ }
}

function addToTrash(link) {
    const t = getTrash();
    t.unshift({ ...link, deletedAt: Date.now() });
    saveTrash(t);
}

async function restoreLinkFromTrash(id) {
    const t = getTrash();
    const idx = t.findIndex(x => x.id === id);
    if (idx === -1) return;
    const link = t[idx];
    delete link.deletedAt;
    t.splice(idx, 1);
    saveTrash(t);
    links.push(link);
    await saveLinkToDB(link);
    renderLinks();
    openTrashModal();
    showToast('Link restored', 'success');
}

async function purgeTrashItem(id) {
    const t = getTrash();
    const link = t.find(x => x.id === id);
    t.splice(t.findIndex(x => x.id === id), 1);
    saveTrash(t);
    if (link) await deleteLinkFromDB(id);
    openTrashModal();
}

function emptyTrash() {
    if (!confirm('Permanently delete all links in Trash?')) return;
    const t = getTrash();
    t.forEach(x => deleteLinkFromDB(x.id));
    localStorage.removeItem(TRASH_KEY);
    openTrashModal();
    showToast('Trash emptied', 'success');
}

function openTrashModal() {
    const items = getTrash();
    const existing = document.getElementById('trashModal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'trashModal';
    modal.className = 'fixed inset-0 z-[9999] flex items-center justify-center p-4';
    modal.style.background = 'rgba(5,3,3,0.72)';
    modal.style.backdropFilter = 'blur(14px)';
    modal.style.animation = 'featureHubIn 0.25s both';
    modal.innerHTML = `
        <div class="glass-card w-full max-w-2xl max-h-[80vh] flex flex-col overflow-hidden" style="animation:hubCardIn 0.3s cubic-bezier(0.16,1,0.3,1) both">
            <div class="p-5 border-b border-white/10 flex items-center justify-between">
                <h3 class="text-lg font-bold text-white flex items-center gap-2">
                    <i data-lucide="trash-2" class="w-5 h-5 text-red-400"></i> Trash <span class="text-sm font-normal text-gray-500">(${items.length})</span>
                </h3>
                <div class="flex items-center gap-2">
                    ${items.length ? `<button id="trashEmpty" class="text-xs text-gray-400 hover:text-red-400 px-3 py-1.5 rounded-lg hover:bg-red-500/10 transition-colors">Empty trash</button>` : ''}
                    <button type="button" id="trashClose" class="feat-hub-close"><i data-lucide="x" class="w-5 h-5"></i></button>
                </div>
            </div>
            <div class="p-4 overflow-y-auto flex-1 custom-scrollbar">
                ${items.length === 0 ? `<p class="text-center text-gray-500 py-10 text-sm">Trash is empty. Deleted links are kept here (latest 100) so you can restore them.</p>` :
                `<div class="space-y-2">${items.map(l => `
                    <div class="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/5 hover:border-white/10 transition-colors">
                        <div class="flex-1 min-w-0">
                            <div class="text-sm text-gray-200 truncate">${escapeHtml(l.title)}</div>
                            <div class="text-[11px] text-gray-500 truncate">${escapeHtml(l.url)} · deleted ${timeAgo(l.deletedAt)}</div>
                        </div>
                        <button onclick="restoreLinkFromTrash('${l.id}')" class="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-green-500/15 text-green-300 hover:bg-green-500/25 transition-colors flex items-center gap-1.5"><i data-lucide="rotate-ccw" class="w-3.5 h-3.5"></i> Restore</button>
                        <button onclick="purgeTrashItem('${l.id}')" class="shrink-0 text-xs px-3 py-1.5 rounded-lg bg-red-500/10 text-red-300 hover:bg-red-500/25 transition-colors">Delete forever</button>
                    </div>
                `).join('')}</div>`}
            </div>
        </div>
    `;
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    modal.querySelector('#trashClose').onclick = () => modal.remove();
    const empty = modal.querySelector('#trashEmpty');
    if (empty) empty.onclick = emptyTrash;
    document.body.appendChild(modal);
    initializeIcons();
}

/* ---------------- Zen Reading Mode ---------------- */
async function openZenMode(linkId) {
    let target = null;
    if (linkId) target = links.find(l => l.id === linkId);
    if (!target && links.length) target = links[0];
    if (!target) { showToast('No links to read yet', 'info'); return; }

    const existing = document.getElementById('zenModal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'zenModal';
    modal.className = 'fixed inset-0 z-[9999] flex items-center justify-center p-4';
    modal.style.background = 'rgba(5,3,3,0.78)';
    modal.style.backdropFilter = 'blur(16px)';
    modal.style.animation = 'featureHubIn 0.25s both';
    modal.innerHTML = `
        <div class="glass-card w-full max-w-3xl max-h-[86vh] flex flex-col overflow-hidden" style="animation:hubCardIn 0.32s cubic-bezier(0.16,1,0.3,1) both">
            <div class="p-5 border-b border-white/10 flex items-center justify-between gap-3">
                <div class="flex-1 min-w-0">
                    <div class="text-[10px] uppercase tracking-widest text-gray-500 flex items-center gap-1"><i data-lucide="book-open" class="w-3 h-3"></i> Zen Mode</div>
                    <h3 class="text-base font-bold text-white truncate mt-0.5">${escapeHtml(target.title)}</h3>
                </div>
                <div class="flex items-center gap-1.5 shrink-0">
                    <button id="zenFontSmall" class="zen-font-btn">A</button>
                    <button id="zenFontMed" class="zen-font-btn active">A</button>
                    <button id="zenFontLarge" class="zen-font-btn">A</button>
                    <span class="w-px h-4 bg-white/10 mx-1"></span>
                    <button id="zenVisit" class="px-3 py-1.5 rounded-lg bg-green-500/15 text-green-300 hover:bg-green-500/25 text-xs transition-colors flex items-center gap-1.5"><i data-lucide="external-link" class="w-3.5 h-3.5"></i> Open original</button>
                    <button id="zenClose" class="feat-hub-close"><i data-lucide="x" class="w-5 h-5"></i></button>
                </div>
            </div>
            <div id="zenBody" class="flex-1 overflow-y-auto p-6 md:p-10 custom-scrollbar">
                <div class="flex items-center justify-center py-16 text-gray-500">
                    <div class="flex flex-col items-center gap-3">
                        <i data-lucide="loader" class="w-8 h-8 animate-spin text-red-400"></i>
                        <span class="text-sm">Extracting content…</span>
                    </div>
                </div>
            </div>
        </div>
    `;
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    modal.querySelector('#zenClose').onclick = () => modal.remove();
    modal.querySelector('#zenVisit').onclick = () => { visitLink(target.url, target.id); modal.remove(); };
    const body = modal.querySelector('#zenBody');
    let size = 17;
    const setSize = (px) => { size = px; body.querySelector('.zen-article').style.fontSize = px + 'px'; };
    modal.querySelector('#zenFontSmall').onclick = () => setSize(15);
    modal.querySelector('#zenFontMed').onclick = () => setSize(17);
    modal.querySelector('#zenFontLarge').onclick = () => setSize(20);

    document.body.appendChild(modal);
    initializeIcons();

    // Extract readable content (best-effort; many sites block CORS)
    try {
        const res = await fetch(target.url, { mode: 'cors', headers: { 'Accept': 'text/html' } });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const html = await res.text();
        const doc = new DOMParser().parseFromString(html, 'text/html');
        doc.querySelectorAll('script, style, noscript, iframe, nav, footer, header, form, aside, .ad, .ads, [class*="ad-"], [id*="ad-"]').forEach(n => n.remove());
        let article = doc.querySelector('article') || doc.querySelector('main') || doc.body;
        const text = (article ? article.innerText : html.replace(/<[^>]*>/g, ' ')).replace(/\s{3,}/g, '\n\n').trim();
        const clipped = text.length > 40000 ? text.slice(0, 40000) + '\n\n…' : text;
        if (!clipped) throw new Error('empty');
        body.innerHTML = `<article class="zen-article" style="font-size:${size}px">${escapeHtml(clipped).split('\n').map(p => p.trim() ? `<p class="mb-4 leading-relaxed text-gray-200">${p.trim()}</p>` : '').join('')}</article>`;
    } catch (err) {
        body.innerHTML = `
            <div class="text-center py-14">
                <i data-lucide="shield-alert" class="w-10 h-10 text-amber-400 mx-auto mb-3"></i>
                <p class="text-gray-300 font-medium mb-1">Could not extract content (CORS blocked or the site doesn't allow it).</p>
                <p class="text-gray-500 text-sm mb-5">${escapeHtml(target.url)}</p>
                <button onclick="document.getElementById('zenVisit').click()" class="px-4 py-2 rounded-lg bg-red-500/20 text-red-300 hover:bg-red-500/30 transition-colors text-sm">Open in a new tab</button>
            </div>`;
        initializeIcons();
    }
}

/* ---------------- Weekly Recap ---------------- */
function openWeeklyRecap() {
    const weekAgo = Date.now() - 7 * 24 * 3600 * 1000;
    const all = links;
    const addedWeek = all.filter(l => l.createdAt && new Date(l.createdAt).getTime() >= weekAgo);
    const visitedWeek = all.filter(l => (l.visitCount || 0) > 0); // visits tracked cumulatively; approximate
    const top = [];
    for (const l of all) {
        if ((l.visitCount || 0) <= 0) continue;
        top.push(l);
        if (top.length > 5) { top.sort((a, b) => (b.visitCount || 0) - (a.visitCount || 0)); top.length = 5; }
    }
    const cats = {};
    for (const l of all) cats[l.category || 'Uncategorized'] = (cats[l.category || 'Uncategorized'] || 0) + 1;
    const topCat = Object.entries(cats).sort((a, b) => b[1] - a[1])[0] || ['—', 0];
    const unread = all.filter(l => !l.isRead).length;

    const existing = document.getElementById('weeklyRecapModal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'weeklyRecapModal';
    modal.className = 'fixed inset-0 z-[9999] flex items-center justify-center p-4';
    modal.style.background = 'rgba(5,3,3,0.72)';
    modal.style.backdropFilter = 'blur(14px)';
    modal.style.animation = 'featureHubIn 0.25s both';
    modal.innerHTML = `
        <div class="glass-card w-full max-w-xl max-h-[84vh] overflow-y-auto custom-scrollbar" style="animation:hubCardIn 0.32s cubic-bezier(0.16,1,0.3,1) both">
            <div class="p-6">
                <div class="flex items-center justify-between mb-1">
                    <h3 class="text-xl font-bold text-white flex items-center gap-2">
                        <i data-lucide="calendar-heart" class="w-5 h-5 text-red-400"></i> Weekly Recap
                    </h3>
                    <button id="weeklyClose" class="feat-hub-close"><i data-lucide="x" class="w-5 h-5"></i></button>
                </div>
                <p class="text-gray-500 text-sm mb-5">Your library's last 7 days at a glance</p>
                <div class="grid grid-cols-3 gap-3 mb-6">
                    <div class="p-4 rounded-2xl bg-white/5 border border-white/10 text-center">
                        <p class="text-2xl font-extrabold text-red-400 count-up" data-v="${addedWeek.length}">0</p>
                        <p class="text-[11px] text-gray-500 mt-1">New links</p>
                    </div>
                    <div class="p-4 rounded-2xl bg-white/5 border border-white/10 text-center">
                        <p class="text-2xl font-extrabold text-amber-400 count-up" data-v="${visitedWeek.length}">0</p>
                        <p class="text-[11px] text-gray-500 mt-1">Links visited</p>
                    </div>
                    <div class="p-4 rounded-2xl bg-white/5 border border-white/10 text-center">
                        <p class="text-2xl font-extrabold text-sky-400 count-up" data-v="${unread}">0</p>
                        <p class="text-[11px] text-gray-500 mt-1">Unread</p>
                    </div>
                </div>
                <div class="p-4 rounded-2xl bg-white/5 border border-white/10 mb-6 flex items-center justify-between">
                    <span class="text-sm text-gray-300">🏆 Top category</span>
                    <span class="text-sm font-bold text-white">${escapeHtml(String(topCat[0]))} <span class="text-gray-500 font-normal">(${topCat[1]})</span></span>
                </div>
                <h4 class="text-xs font-bold text-gray-400 uppercase tracking-wider mb-3 flex items-center gap-1.5">
                    <i data-lucide="flame" class="w-3.5 h-3.5 text-red-400"></i> Most visited links
                </h4>
                <div class="space-y-2">
                    ${top.length ? top.map((l, i) => `
                        <div onclick="visitLink('${escapeHtml(l.url)}','${l.id}',event)" class="flex items-center gap-3 p-3 rounded-xl bg-white/5 border border-white/5 hover:bg-white/10 hover:border-red-500/30 transition-all cursor-pointer">
                            <span class="text-lg font-extrabold w-6 text-center ${i === 0 ? 'text-amber-400' : 'text-gray-500'}">${i + 1}</span>
                            <div class="flex-1 min-w-0">
                                <div class="text-sm text-gray-200 truncate">${escapeHtml(l.title)}</div>
                                <div class="text-[11px] text-gray-500 truncate">${escapeHtml(l.url)}</div>
                            </div>
                            <span class="text-xs text-red-400 shrink-0">${l.visitCount || 0} 👁</span>
                        </div>
                    `).join('') : '<p class="text-gray-500 text-sm">No visit data yet.</p>'}
                </div>
            </div>
        </div>
    `;
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    modal.querySelector('#weeklyClose').onclick = () => modal.remove();
    document.body.appendChild(modal);
    initializeIcons();
    // Count-up animation
    requestAnimationFrame(() => {
        modal.querySelectorAll('.count-up').forEach(el => {
            const target = parseInt(el.dataset.v, 10) || 0;
            const dur = 600; const t0 = performance.now();
            const tick = (t) => {
                const p = Math.min(1, (t - t0) / dur);
                el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
                if (p < 1) requestAnimationFrame(tick);
            };
            requestAnimationFrame(tick);
        });
    });
}

/* ---------------- Bookmarklet Generator ---------------- */
function openBookmarkletModal() {
    const code = `javascript:(function(){var u=location.href,t=document.title;window.open('${location.origin}${location.pathname}#qsave='+encodeURIComponent(u)+'&t='+encodeURIComponent(t),'_blank','width=560,height=700');})();`;
    const existing = document.getElementById('bookmarkletModal');
    if (existing) existing.remove();
    const modal = document.createElement('div');
    modal.id = 'bookmarkletModal';
    modal.className = 'fixed inset-0 z-[9999] flex items-center justify-center p-4';
    modal.style.background = 'rgba(5,3,3,0.72)';
    modal.style.backdropFilter = 'blur(14px)';
    modal.style.animation = 'featureHubIn 0.25s both';
    modal.innerHTML = `
        <div class="glass-card w-full max-w-lg" style="animation:hubCardIn 0.3s cubic-bezier(0.16,1,0.3,1) both">
            <div class="p-6">
                <div class="flex items-center justify-between mb-4">
                    <h3 class="text-lg font-bold text-white flex items-center gap-2">
                        <i data-lucide="bookmark" class="w-5 h-5 text-amber-400"></i> Bookmarklet Generator
                    </h3>
                    <button id="bmClose" class="feat-hub-close"><i data-lucide="x" class="w-5 h-5"></i></button>
                </div>
                <p class="text-gray-400 text-sm mb-4 leading-relaxed">
                    Drag the button below onto your bookmarks bar (or copy the code) — works in <b>any browser</b>.
                    Click it on any page to open Quick Save with the URL pre-filled.
                </p>
                <a id="bookmarkletLink" href="${code}" onclick="return false"
                    class="mb-4 flex items-center justify-center gap-2 w-full py-3 rounded-xl bg-gradient-to-r from-red-600 to-amber-500 text-white font-semibold hover:scale-[1.02] active:scale-95 transition-transform shadow-lg shadow-red-500/25">
                    <i data-lucide="bookmark" class="w-4 h-4"></i> ⭐ Save to LinkLumina
                </a>
                <div class="p-3 rounded-xl bg-black/40 border border-white/10 text-[11px] font-mono text-gray-400 break-all max-h-28 overflow-y-auto mb-4">${escapeHtml(code)}</div>
                <button id="bmCopy" class="w-full py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-sm transition-colors">Copy code</button>
            </div>
        </div>
    `;
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };
    modal.querySelector('#bmClose').onclick = () => modal.remove();
    modal.querySelector('#bmCopy').onclick = () => {
        navigator.clipboard.writeText(code).then(() => showToast('Bookmarklet code copied!', 'success')).catch(() => showToast('Could not copy', 'error'));
    };
    document.body.appendChild(modal);
    initializeIcons();
}

/* ---------------- Bookmarklet deep-link (handle #qsave=URL) ---------------- */
function handleBookmarkletDeepLink() {
    try {
        const h = decodeURIComponent(location.hash || '');
        const m = h.match(/qsave=([^&]+)(?:&t=([^&]*))?/);
        if (m && m[1]) {
            const url = decodeURIComponent(m[1]);
            const title = m[2] ? decodeURIComponent(m[2]) : '';
            // Clear hash so re-running the bookmarklet works
            history.replaceState(null, '', location.pathname + location.search);
            setTimeout(() => openQuickSave(url), 600);
            if (title) showToast('URL filled from bookmarklet: ' + title.slice(0, 60), 'info');
        }
    } catch (e) { /* ignore malformed hash */ }
}

/* ---------------- Duplicate URL check ---------------- */
function findDuplicateUrl(url) {
    const clean = (u) => { try { return new URL(u).href.replace(/^https?:\/\//, '').replace(/\/$/, '').toLowerCase(); } catch { return String(u || '').toLowerCase(); } };
    const target = clean(url);
    for (const l of links) {
        if (clean(l.url) === target) return l;
    }
    return null;
}

// ==================== FEATURE REGISTRY ====================
// One place that links every feature into the AppFeatures Hub (features.js).
// Future features: add one register() call here (or anywhere) and it appears
// in the Hub + Command Palette automatically.
function registerAllFeatures() {
    if (!window.AppFeatures) return;
    const R = window.AppFeatures.register;

    /* ---- Core ---- */
    R({ id: 'add-link', title: 'Add Link', icon: 'plus', category: 'core', desc: 'Create a new link with auto metadata', keywords: ['new', 'create', 'url', 'add'], shortcut: 'Ctrl+N', action: () => openModal(null) });
    R({ id: 'quick-save', title: 'Quick Save (Bulk)', icon: 'zap', category: 'core', desc: 'Paste many URLs, auto-fetch metadata', keywords: ['bulk', 'paste', 'save', 'text'], shortcut: 'Ctrl+S', action: () => openQuickSave() });
    R({ id: 'add-note', title: 'Add New Note', icon: 'file-text', category: 'core', desc: 'Quick markdown notes', keywords: ['note', 'write', 'markdown'], action: () => window.openNoteModal && window.openNoteModal() });
    R({ id: 'transcript', title: 'Transcript Reader', icon: 'file-audio', category: 'core', desc: 'Fetch YouTube subtitles / transcript from a URL', keywords: ['youtube', 'subtitle', 'video', 'captions'], action: () => openTranscriptModal(null) });
    R({ id: 'duplicate-check', title: 'Duplicate URL Check', icon: 'copy-x', category: 'core', desc: 'Warn when adding a URL that already exists', keywords: ['duplicate', 'existing', 'check'], badge: 'NEW' });

    /* ---- View ---- */
    R({ id: 'dense-view', title: 'Dense View', icon: 'rows-3', category: 'view', desc: 'Shrink cards to fit more links', keywords: ['compact', 'dense', 'layout', 'minimal'], action: () => CompactMode.toggle() });
    R({ id: 'power-search', title: 'Power Search', icon: 'search', category: 'view', desc: 'Search 5000+ links fast: tag:, cat:, domain:, visits:>, "phrase", -exclude — works without Vietnamese diacritics', keywords: ['search', 'find', 'query', 'operators', 'filter', 'tim'], badge: 'NEW', action: () => { const el = document.getElementById('searchInput'); if (el) { el.focus(); el.select(); } } });
    R({ id: 'zen-mode', title: 'Zen Reading Mode', icon: 'book-open', category: 'view', desc: 'Read page content cleanly, without clutter', keywords: ['read', 'focus', 'clean', 'reader'], badge: 'NEW', action: () => openZenMode() });
    R({ id: 'pinned-view', title: 'Pinned & Unread Filters', icon: 'pin', category: 'view', desc: 'Quickly filter pinned and unread links from the sidebar', keywords: ['pinned', 'unread', 'filter', 'reading'], badge: 'NEW', action: () => setSidebarQuickFilter('pinned') });

    /* ---- Data ---- */
    R({ id: 'smart-folders', title: 'Smart Folders (Saved Searches)', icon: 'folder-search', category: 'data', desc: 'Save a filter set as a smart folder in the sidebar', keywords: ['preset', 'saved', 'search', 'smart'], badge: 'NEW', action: () => renderSmartFolders(true) });
    R({ id: 'storage', title: 'Storage & Settings', icon: 'database', category: 'data', desc: 'Usage, optimize, delete images, wipe all data', keywords: ['storage', 'settings', 'size', 'space'], action: () => openStorageModal() });
    R({ id: 'cloud-sync', title: 'Cloud Sync', icon: 'refresh-cw', category: 'data', desc: 'Sync across devices via a Supabase Room Code', keywords: ['sync', 'cloud', 'supabase', 'room'], action: () => window.openSyncModal ? window.openSyncModal() : showToast('Cloud Sync not ready yet', 'info') });
    R({ id: 'export-csv', title: 'Export CSV', icon: 'file-spreadsheet', category: 'data', desc: 'Export your links to a CSV file', keywords: ['export', 'csv', 'spreadsheet'], action: () => exportLinks() });
    R({ id: 'export-json', title: 'Export JSON Backup', icon: 'database-backup', category: 'data', desc: 'Back up the whole workspace as JSON', keywords: ['backup', 'json', 'export'], action: () => exportLinksAsJSON() });
    R({ id: 'import-backup', title: 'Import Backup', icon: 'upload-cloud', category: 'data', desc: 'Restore from a JSON backup file', keywords: ['import', 'restore', 'backup'], action: () => document.getElementById('importJsonInput') && document.getElementById('importJsonInput').click() });
    R({ id: 'find-duplicates', title: 'Find Duplicates', icon: 'copy-check', category: 'data', desc: 'Find and remove duplicate links', keywords: ['clean', 'dedupe', 'duplicate'], action: () => openDuplicatesModal() });
    R({ id: 'trash', title: 'Trash & Restore', icon: 'trash-2', category: 'data', desc: 'Soft-delete and restore recently removed links', keywords: ['trash', 'restore', 'delete', 'recover'], badge: 'NEW', action: () => openTrashModal() });

    /* ---- Analysis ---- */
    R({ id: 'analytics', title: 'Analytics Dashboard', icon: 'bar-chart-3', category: 'analysis', desc: 'Charts, categories, and top tags for your whole library', keywords: ['stats', 'dashboard', 'graphs', 'chart'], action: () => openAnalytics() });
    R({ id: 'weekly-recap', title: 'Weekly Recap', icon: 'calendar-heart', category: 'analysis', desc: 'This week at a glance: new links, visits, top links', keywords: ['week', 'recap', 'summary', 'digest'], badge: 'NEW', action: () => openWeeklyRecap() });
    R({ id: 'activity-feed', title: 'Activity Feed', icon: 'activity', category: 'analysis', desc: 'Recent activity log in your workspace', keywords: ['activity', 'feed', 'history', 'log'], badge: 'NEW', action: () => openActivityFeed() });
    R({ id: 'neural-web', title: 'Neural Web', icon: 'share-2', category: 'analysis', desc: 'Explore the connections between your links', keywords: ['neural', 'graph', 'network', 'links'], action: () => window.initNeuralWeb ? window.initNeuralWeb() : showToast('Neural Web is loading…', 'info') });
    R({ id: 'cognitive-laws', title: 'Cognitive Laws', icon: 'scale', category: 'analysis', desc: 'Cognitive rules that support decision-making', keywords: ['laws', 'cognitive', 'brain'], action: () => window.LawEngine && window.LawEngine.renderModal() });
    R({ id: 'strategic-decision', title: 'Log Strategic Decision', icon: 'zap', category: 'analysis', desc: 'Record an important decision with its reasoning', keywords: ['decision', 'strategic', 'log'], action: () => openDecisionModal() });
    R({ id: 'related-links', title: 'Related Links', icon: 'git-branch', category: 'analysis', desc: 'Find similar links by tag & content', keywords: ['similar', 'related', 'find'], badge: 'NEW', action: () => { const l = links[0]; if (l) showSimilarLinksModal(l.id); } });

    /* ---- Automation ---- */
    R({ id: 'link-roulette', title: 'Link Roulette', icon: 'dice-5', category: 'automation', desc: 'Open a random link from your library', keywords: ['random', 'shuffle', 'lucky', 'roulette'], shortcut: 'Ctrl+R', action: () => openRandomLink() });
    R({ id: 'batch-enhance', title: 'Bulk Magic Enhance', icon: 'wand-2', category: 'automation', desc: 'Select many links → auto-tag + bulk-load images', keywords: ['bulk', 'magic', 'enhance', 'auto'], action: () => { if (window.bulkMagicEnhance) window.bulkMagicEnhance(); else { toggleSelectionMode(); showToast('Select links, then click Magic Enhance', 'info'); } } });
    R({ id: 'health-check', title: 'Link Health Check', icon: 'heart-pulse', category: 'automation', desc: 'Check whether links are alive or broken', keywords: ['health', 'check', 'broken', 'alive'], action: () => batchCheckLinkHealth() });

    /* ---- Extras ---- */
    R({ id: 'bookmarklet', title: 'Bookmarklet Generator', icon: 'bookmark', category: 'extras', desc: 'Create a bookmarklet to save links from any browser', keywords: ['bookmarklet', 'browser', 'save', 'javascript'], badge: 'NEW', action: () => openBookmarkletModal() });
    R({ id: 'keyboard-shortcuts', title: 'Keyboard Shortcuts', icon: 'keyboard', category: 'extras', desc: 'View the full list of keyboard shortcuts', keywords: ['help', 'keys', 'shortcut'], action: () => openShortcutsModal() });
    R({ id: 'extension', title: 'Browser Extension', icon: 'puzzle', category: 'extras', desc: 'How to install the Quick Save extension', keywords: ['extension', 'chrome', 'install'], action: () => showToast('Install the extension from the extension/ folder in the project', 'info') });
    R({ id: 'feature-hub', title: 'Feature Hub', icon: 'sparkles', category: 'extras', desc: 'Reopen this feature overview panel', keywords: ['hub', 'features', 'menu', 'all'], shortcut: 'Ctrl+Shift+F', action: () => window.AppFeatures.openHub() });
}

// ==================== Command Palette (Arc Reactor) ====================

const commands = [
    // Actions
    { id: 'add-link', title: 'Add New Link', icon: 'plus', action: () => openModal(null), keywords: ['new', 'create', 'url'] },
    { id: 'quick-save', title: 'Quick Save (Bulk)', icon: 'zap', action: () => openQuickSave(), keywords: ['bulk', 'paste', 'text'] },
    { id: 'add-note', title: 'Add New Note', icon: 'file-text', action: () => window.openNoteModal && window.openNoteModal(), keywords: ['note', 'write', 'markdown'] },
    { id: 'random-link', title: 'I\'m Feeling Lucky', icon: 'dice-5', action: () => openRandomLink(), keywords: ['random', 'shuffle', 'lucky'] },
    { id: 'find-duplicates', title: 'Find Duplicates', icon: 'copy', action: () => openDuplicatesModal(), keywords: ['clean', 'dedupe'] },
    { id: 'export-data', title: 'Export Data (Excel)', icon: 'download', action: () => exportLinks(), keywords: ['backup', 'save', 'xlsx'] },

    // Navigation
    { id: 'nav-links', title: 'Go to Links', icon: 'link', action: () => window.switchTab && window.switchTab('links'), keywords: ['home', 'bookmarks'] },
    { id: 'nav-notes', title: 'Go to Notes', icon: 'file-text', action: () => window.switchTab && window.switchTab('notes'), keywords: ['notepad'] },
    { id: 'nav-prompts', title: 'Go to Prompts', icon: 'message-square', action: () => window.switchTab && window.switchTab('prompts'), keywords: ['ai', 'chatgpt'] },
    { id: 'nav-colors', title: 'Go to Colors', icon: 'palette', action: () => window.switchTab && window.switchTab('colors'), keywords: ['palette', 'theme'] },
    { id: 'nav-files', title: 'Go to Files', icon: 'folder', action: () => window.switchTab && window.switchTab('files'), keywords: ['storage', 'upload'] },
    { id: 'nav-tools', title: 'Go to Tools', icon: 'wrench', action: () => window.switchTab && window.switchTab('tools'), keywords: ['product hunt', 'tools', 'apps'] },

    // Tools
    { id: 'analytics', title: 'View Analytics', icon: 'bar-chart-2', action: () => openAnalytics(), keywords: ['stats', 'dashboard', 'graphs'] },
    { id: 'shortcuts', title: 'Keyboard Shortcuts', icon: 'keyboard', action: () => openShortcutsModal(), keywords: ['help', 'keys'] },
];

let commandSelectedIndex = 0;
let filteredCommands = [];

function setupCommandPalette() {
    const palette = document.getElementById('commandPalette');
    const input = document.getElementById('commandInput');
    if (!palette || !input) return;

    // Open logic is handled by global keyboard listener
    // Close on backdrop click (already in HTML)

    // Input handling
    input.addEventListener('input', (e) => renderCommandResults(e.target.value));

    // Keyboard navigation
    input.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowDown') {
            e.preventDefault();
            commandSelectedIndex = Math.min(commandSelectedIndex + 1, filteredCommands.length - 1);
            updateCommandSelection();
        } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            commandSelectedIndex = Math.max(commandSelectedIndex - 1, 0);
            updateCommandSelection();
        } else if (e.key === 'Enter') {
            e.preventDefault();
            executeSelectedCommand();
        } else if (e.key === 'Escape') {
            closeCommandPalette();
        }
    });

    // Global shortcut Ctrl+K
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
            e.preventDefault();
            openCommandPalette();
        }
    });
}

function openCommandPalette() {
    const palette = document.getElementById('commandPalette');
    const input = document.getElementById('commandInput');
    if (!palette) return;

    palette.classList.remove('hidden');
    input.value = '';
    input.focus();
    commandSelectedIndex = 0;
    renderCommandResults('');
    document.body.style.overflow = 'hidden';
}

function closeCommandPalette() {
    const palette = document.getElementById('commandPalette');
    if (!palette) return;
    palette.classList.add('hidden');
    document.body.style.overflow = '';
}

function renderCommandResults(query) {
    const container = document.getElementById('commandResults');
    const normalizedQuery = query.toLowerCase().trim();

    if (!normalizedQuery) {
        // Show recent or default commands
        filteredCommands = commands;
    } else {
        // Filter commands
        filteredCommands = commands.filter(cmd =>
            cmd.title.toLowerCase().includes(normalizedQuery) ||
            cmd.keywords.some(k => k.includes(normalizedQuery))
        );

        // Can also search links titles here if we want to be fancy
        // const linkMatches = links.filter(...).slice(0, 5);
        // filteredCommands = [...filteredCommands, ...linkMatches];
    }

    if (filteredCommands.length === 0) {
        container.innerHTML = `
            <div class="px-4 py-3 text-center text-gray-500">
                No matching commands found.
            </div>
        `;
        return;
    }

    container.innerHTML = filteredCommands.map((cmd, index) => `
        <div class="command-item flex items-center gap-3 px-4 py-3 cursor-pointer border-l-2 border-transparent hover:bg-white/5 ${index === commandSelectedIndex ? 'bg-white/10 border-red-500' : ''}"
            onclick="executeCommand('${cmd.id}')"
            onmouseover="setCommandIndex(${index})">
            <div class="w-5 h-5 flex items-center justify-center text-gray-400">
                <i data-lucide="${cmd.icon}"></i>
            </div>
            <div class="flex-1">
                <div class="text-white font-medium text-sm">${escapeHtml(cmd.title)}</div>
            </div>
            ${index === commandSelectedIndex ? '<span class="text-xs text-gray-500">Hit Enter</span>' : ''}
        </div>
    `).join('');

    initializeIcons();
}

function updateCommandSelection() {
    const items = document.querySelectorAll('.command-item');
    items.forEach((item, index) => {
        if (index === commandSelectedIndex) {
            item.classList.add('bg-white/10', 'border-red-500');
            item.scrollIntoView({ block: 'nearest' });
        } else {
            item.classList.remove('bg-white/10', 'border-red-500');
        }
    });
}

function setCommandIndex(index) {
    commandSelectedIndex = index;
    updateCommandSelection();
}

function executeSelectedCommand() {
    if (filteredCommands[commandSelectedIndex]) {
        executeCommand(filteredCommands[commandSelectedIndex].id);
    }
}

function executeCommand(id) {
    const cmd = commands.find(c => c.id === id);
    if (cmd) {
        cmd.action();
        closeCommandPalette();
    }
}

// Make functions globally available
window.openCommandPalette = openCommandPalette;
window.closeCommandPalette = closeCommandPalette;
window.executeCommand = executeCommand;
window.setCommandIndex = setCommandIndex;

// ==================== MOBILE FAB ====================
function updateMobileFabVisibility() {
    const fab = document.getElementById('mobileFabAddLink');
    if (!fab) return;
    const isLinksTab = document.getElementById('linksTab') && !document.getElementById('linksTab').classList.contains('hidden');
    const isMobile = window.innerWidth < 769;
    const show = isMobile && isLinksTab && !isSelectionMode;
    fab.classList.toggle('hidden', !show);
    if (!show) return;
    if (window.lucide) lucide.createIcons();
}
window.updateMobileFabVisibility = updateMobileFabVisibility;

// ==================== BATCH MODE FUNCTIONS ====================

function toggleSelectionMode() {
    isSelectionMode = !isSelectionMode;
    const selectBtn = document.getElementById('selectModeBtn');
    const floatingBar = document.getElementById('floatingActionBar');

    if (isSelectionMode) {
        selectBtn.classList.add('active');
        floatingBar.classList.remove('hidden');
        document.body.style.paddingBottom = '100px';
    } else {
        selectBtn.classList.remove('active');
        floatingBar.classList.add('hidden');
        batchSelectedLinks.clear();
        document.body.style.paddingBottom = '0';
    }

    updateBulkActionUI();
    if (typeof updateMobileFabVisibility === 'function') updateMobileFabVisibility();
    renderLinks(); // Re-render to show/hide checkboxes
}

function handleCardSelect(id, event) {
    if (!isSelectionMode) return;
    event.stopPropagation();
    event.preventDefault(); // Prevent link click

    if (batchSelectedLinks.has(id)) {
        batchSelectedLinks.delete(id);
    } else {
        batchSelectedLinks.add(id);
    }

    updateBulkActionUI();
    updateFloatingBar();

    // Visual update (Re-render single card)
    const link = links.find(l => l.id === id);
    const card = document.getElementById(`link-card-${id}`);

    if (link && card) {
        card.outerHTML = createLinkCard(link);
        // Re-initialize Lucide icons for the new HTML
        if (typeof lucide !== 'undefined') {
            lucide.createIcons();
        }
    }
}

function updateFloatingBar() {
    const count = batchSelectedLinks.size;
    const countEl = document.getElementById('selectedCount');
    if (countEl) countEl.textContent = count;

    const moveBtn = document.getElementById('batchMoveBtn');
    const deleteBtn = document.getElementById('batchDeleteBtn');

    if (count > 0) {
        moveBtn.classList.remove('opacity-50', 'cursor-not-allowed');
        deleteBtn.classList.remove('opacity-50', 'cursor-not-allowed');
    } else {
        moveBtn.classList.add('opacity-50', 'cursor-not-allowed');
        deleteBtn.classList.add('opacity-50', 'cursor-not-allowed');
    }
}

async function handleBatchDelete() {
    if (batchSelectedLinks.size === 0) return;

    if (confirm(`Are you sure you want to delete ${batchSelectedLinks.size} links?`)) {
        const idsToDelete = Array.from(batchSelectedLinks);

        for (const id of idsToDelete) {
            links = links.filter(l => l.id !== id);
            await deleteLinkFromDB(id);
        }

        showToast(`Deleted ${idsToDelete.length} links`, 'success');
        batchSelectedLinks.clear();
        if (isSelectionMode) toggleSelectionMode(); // Exit mode
        updateAllTags();
        renderLinks();
        renderCategoryFilters();
        updateStorageStatsIfOpen();
    }
}

// Phase 5: Bulk Favorite all selected
async function bulkFavoriteAll() {
    if (batchSelectedLinks.size === 0) return;
    for (const id of batchSelectedLinks) {
        const link = links.find(l => l.id === id);
        if (link) {
            link.favorite = true;
            await saveLinkToDB(link);
        }
    }
    showToast(`${batchSelectedLinks.size} link(s) marked as favorite`, 'success');
    batchSelectedLinks.clear();
    if (isSelectionMode) toggleSelectionMode();
    renderLinks();
    renderCategoryFilters();
}

// Phase 5: Bulk set category for selected
async function bulkSetCategory() {
    if (batchSelectedLinks.size === 0) return;
    const categories = [...new Set(links.map(l => l.category).filter(Boolean))];
    const name = prompt('Enter category name for all selected links:', categories[0] || 'General');
    if (name == null || name.trim() === '') return;
    const category = name.trim();
    for (const id of batchSelectedLinks) {
        const link = links.find(l => l.id === id);
        if (link) {
            link.category = category;
            await saveLinkToDB(link);
        }
    }
    showToast(`${batchSelectedLinks.size} link(s) moved to "${category}"`, 'success');
    batchSelectedLinks.clear();
    if (isSelectionMode) toggleSelectionMode();
    updateAllTags();
    renderLinks();
    renderCategoryFilters();
}

// Bulk Edit Modal (category + tags for selected)
function openBulkEditModal() {
    if (batchSelectedLinks.size === 0) return;
    const modal = document.getElementById('bulkEditModal');
    const countEl = document.getElementById('bulkEditCount');
    const catSel = document.getElementById('bulkEditCategory');
    const tagsInput = document.getElementById('bulkEditTags');
    if (!modal || !countEl || !catSel) return;
    countEl.textContent = batchSelectedLinks.size;
    catSel.innerHTML = (window.LINK_CATEGORIES || ['General', 'Other']).map(c => `<option value="${escapeHtml(c)}">${escapeHtml(c)}</option>`).join('');
    if (tagsInput) tagsInput.value = '';
    modal.classList.remove('hidden');
    if (typeof lucide !== 'undefined') lucide.createIcons();
}
function closeBulkEditModal() {
    const modal = document.getElementById('bulkEditModal');
    if (modal) modal.classList.add('hidden');
}
async function confirmBulkEdit() {
    const catSel = document.getElementById('bulkEditCategory');
    const tagsInput = document.getElementById('bulkEditTags');
    const category = catSel ? catSel.value : 'General';
    const tagsToAdd = tagsInput && tagsInput.value.trim() ? tagsInput.value.split(',').map(t => t.trim().toLowerCase()).filter(Boolean) : [];

    // Snapshot for Undo
    const snapshot = [];
    for (const id of batchSelectedLinks) {
        const link = links.find(l => l.id === id);
        if (link) snapshot.push({ id: link.id, category: link.category || 'General', tags: (link.tags || []).slice() });
    }

    for (const id of batchSelectedLinks) {
        const link = links.find(l => l.id === id);
        if (link) {
            link.category = category;
            if (tagsToAdd.length) {
                link.tags = link.tags || [];
                tagsToAdd.forEach(t => { if (!link.tags.includes(t)) link.tags.push(t); });
            }
            await saveLinkToDB(link);
        }
    }
    closeBulkEditModal();
    const count = batchSelectedLinks.size;
    batchSelectedLinks.clear();
    if (isSelectionMode) toggleSelectionMode();
    updateAllTags();
    renderLinks();
    renderCategoryFilters();

    showUndoToast(`Bulk edit applied to ${count} link(s)`, async () => {
        for (const { id, category: prevCat, tags: prevTags } of snapshot) {
            const link = links.find(l => l.id === id);
            if (link) {
                link.category = prevCat;
                link.tags = prevTags;
                await saveLinkToDB(link);
            }
        }
        updateAllTags();
        renderLinks();
        renderCategoryFilters();
        showToast('Bulk edit undone.', 'success');
    });
}

let batchTargetTag = '';
let batchTargetFolderId = null;

function openBatchMoveModal() {
    if (batchSelectedLinks.size === 0) return;
    const modal = document.getElementById('batchMoveModal');
    modal.classList.remove('hidden');

    const tagsList = document.getElementById('existingTagsList');
    tagsList.innerHTML = '';

    // Reset selection
    batchTargetFolderId = null;
    batchTargetTag = '';

    // Add Folder Options
    const foldersHeader = document.createElement('div');
    foldersHeader.className = 'w-full text-xs text-gray-500 uppercase font-bold mb-2 mt-2';
    foldersHeader.textContent = '📁 Folders';
    tagsList.appendChild(foldersHeader);

    // Unsorted option
    const unsortedBtn = document.createElement('button');
    unsortedBtn.className = 'px-3 py-1.5 rounded-lg bg-gray-700/50 hover:bg-gray-600/50 text-xs text-gray-300 transition-all border border-white/10 flex items-center gap-2';
    unsortedBtn.innerHTML = '<i data-lucide="inbox" class="w-3 h-3"></i> Unsorted';
    unsortedBtn.onclick = () => {
        batchTargetFolderId = null;
        document.getElementById('batchTagInput').value = '📁 Unsorted';
        highlightSelectedFolder(unsortedBtn);
    };
    tagsList.appendChild(unsortedBtn);

    // Custom folders
    const allFolders = window.folders || [];
    allFolders.forEach(folder => {
        const folderBtn = document.createElement('button');
        folderBtn.className = 'px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 text-xs text-gray-300 transition-all border border-white/5 flex items-center gap-2';
        folderBtn.innerHTML = `<i data-lucide="folder" class="w-3 h-3" style="color: ${folder.color || '#dc2626'}"></i> ${folder.name}`;
        folderBtn.onclick = () => {
            batchTargetFolderId = folder.id;
            document.getElementById('batchTagInput').value = '📁 ' + folder.name;
            highlightSelectedFolder(folderBtn);
        };
        tagsList.appendChild(folderBtn);
    });

    // Divider
    const divider = document.createElement('div');
    divider.className = 'w-full h-px bg-white/10 my-3';
    tagsList.appendChild(divider);

    // Tag Options Header
    const tagsHeader = document.createElement('div');
    tagsHeader.className = 'w-full text-xs text-gray-500 uppercase font-bold mb-2';
    tagsHeader.textContent = '🏷️ Add Tag';
    tagsList.appendChild(tagsHeader);

    // Existing tags
    Array.from(allTags).sort().slice(0, 20).forEach(tag => {
        const tagEl = document.createElement('button');
        tagEl.className = 'px-3 py-1 rounded-full bg-red-500/20 hover:bg-red-500/30 text-xs text-red-300 transition-all border border-red-500/20';
        tagEl.textContent = tag;
        tagEl.onclick = () => {
            batchTargetFolderId = undefined; // Not a folder move
            batchTargetTag = tag;
            document.getElementById('batchTagInput').value = '🏷️ ' + tag;
            highlightSelectedFolder(tagEl);
        };
        tagsList.appendChild(tagEl);
    });

    document.getElementById('batchTagInput').placeholder = 'Select folder or tag above...';
    document.getElementById('batchTagInput').readOnly = true; // Make it display-only

    if (typeof lucide !== 'undefined') lucide.createIcons();
}

function highlightSelectedFolder(selectedBtn) {
    // Remove highlight from all
    const tagsList = document.getElementById('existingTagsList');
    tagsList.querySelectorAll('button').forEach(btn => {
        btn.classList.remove('ring-2', 'ring-red-500');
    });
    // Add highlight to selected
    selectedBtn.classList.add('ring-2', 'ring-red-500');
}

function closeBatchMoveModal() {
    document.getElementById('batchMoveModal').classList.add('hidden');
    document.getElementById('batchTagInput').value = '';
    document.getElementById('batchTagInput').readOnly = false;
    batchTargetTag = '';
    batchTargetFolderId = null;
}

async function confirmBatchMove() {
    // Case 1: Move to Folder
    if (batchTargetFolderId !== undefined) {
        let count = 0;
        for (const id of batchSelectedLinks) {
            if (typeof updateLinkFolder === 'function') {
                await updateLinkFolder(id, batchTargetFolderId);
                count++;
            }
        }
        const folderName = batchTargetFolderId
            ? (window.folders?.find(f => f.id === batchTargetFolderId)?.name || 'Folder')
            : 'Unsorted';
        showToast(`Moved ${count} links to "${folderName}"`, 'success');
        closeBatchMoveModal();
        if (isSelectionMode) toggleSelectionMode();
        if (typeof renderSidebar === 'function') renderSidebar();
        renderLinks();
        return;
    }

    // Case 2: Add Tag
    if (batchTargetTag) {
        let count = 0;
        for (const id of batchSelectedLinks) {
            const link = links.find(l => l.id === id);
            if (link) {
                if (!link.tags.includes(batchTargetTag)) {
                    link.tags.push(batchTargetTag);
                    await saveSingleLink(link);
                    count++;
                }
            }
        }
        showToast(`Added tag "${batchTargetTag}" to ${count} links`, 'success');
        closeBatchMoveModal();
        if (isSelectionMode) toggleSelectionMode();
        updateAllTags();
        renderLinks();
        renderCategoryFilters();
        return;
    }

    showToast('Please select a folder or tag', 'error');
}

// ==================== EXTERNAL MODULES ====================
// Note: Neural Web and Supabase Sync logic have been moved to:
// - neural.js
// - sync.js
// These files are loaded in index.html

// ==================== CREATIVE QoL FEATURES ====================

// Milestone celebration 🎉
function checkMilestone(count) {
    const milestones = [10, 25, 50, 100, 250, 500, 1000];
    if (milestones.includes(count)) {
        triggerConfetti();
        setTimeout(() => {
            showToast(`🎉 Milestone: ${count} links saved!`, 'success');
        }, 500);
    }
}

// Confetti animation
function triggerConfetti() {
    const colors = ['#dc2626', '#b91c1c', '#f59e0b', '#eab308', '#dc2626', '#dc2626'];
    const confettiCount = 100;

    for (let i = 0; i < confettiCount; i++) {
        const confetti = document.createElement('div');
        confetti.className = 'confetti';
        confetti.style.cssText = `
            position: fixed;
            width: ${Math.random() * 10 + 5}px;
            height: ${Math.random() * 10 + 5}px;
            background: ${colors[Math.floor(Math.random() * colors.length)]};
            left: ${Math.random() * 100}vw;
            top: -20px;
            border-radius: ${Math.random() > 0.5 ? '50%' : '0'};
            z-index: 9999;
            pointer-events: none;
            animation: confettiFall ${Math.random() * 3 + 2}s linear forwards;
            transform: rotate(${Math.random() * 360}deg);
        `;
        document.body.appendChild(confetti);

        // Remove after animation
        setTimeout(() => confetti.remove(), 5000);
    }

    // Add confetti animation styles if not exists
    if (!document.getElementById('confettiStyles')) {
        const style = document.createElement('style');
        style.id = 'confettiStyles';
        style.textContent = `
            @keyframes confettiFall {
                0% { transform: translateY(0) rotate(0deg); opacity: 1; }
                100% { transform: translateY(100vh) rotate(720deg); opacity: 0; }
            }
        `;
        document.head.appendChild(style);
    }
}

// Auto-detect category from domain (delegates to getAutoCategory for consistency)
function autoCategoryFromDomain(url) {
    const cat = getAutoCategory(url, '');
    return cat && cat !== 'General' ? cat : null;
}

// Quick copy markdown format
function copyAsMarkdown(title, url) {
    const markdown = `[${title}](${url})`;
    navigator.clipboard.writeText(markdown);
    showToast('📋 Copied as Markdown!', 'success');
}

// End of script.js

// ==================== COGNITIVE LAWS INTEGRATION ====================
document.addEventListener('DOMContentLoaded', () => {
    // Hook into window.visitLink
    if (typeof window.visitLink === 'function') {
        const originalVisitLink = window.visitLink;
        window.visitLink = function (url) {
            originalVisitLink(url);
            if (window.LawEngine) {
                const link = window.links.find(l => l.url === url);
                if (link) window.LawEngine.emit('link_visited', { item: link, eventType: 'link_visited' });
            }
        };
    }
});
// ==================== Folder System Integration ====================

function setupFolderListeners() {
    // Add Folder Button
    const addBtn = document.getElementById('addFolderBtn');
    if (addBtn) {
        // Remove existing listeners to be safe (not easily possible with anon functions, but basic check helps)
        addBtn.onclick = async () => {
            const name = prompt('Enter folder name:');
            if (name && window.createFolder) {
                await window.createFolder(name);
            }
        };
    }

    // Mobile Sidebar Toggle + Overlay
    const toggleBtn = document.getElementById('toggleSidebarBtn');
    const sidebarOverlay = document.getElementById('sidebarOverlay');
    if (toggleBtn) {
        toggleBtn.onclick = () => {
            const sidebar = document.getElementById('folderSidebar');
            if (sidebar) {
                sidebar.classList.toggle('hidden');
                sidebar.classList.toggle('absolute');
                sidebar.classList.toggle('z-50');
                sidebar.classList.toggle('h-full');
                sidebar.classList.toggle('active');
                if (sidebarOverlay) {
                    sidebarOverlay.classList.toggle('hidden', sidebar.classList.contains('hidden'));
                }
                document.body.style.overflow = sidebar.classList.contains('hidden') ? '' : 'hidden';
            }
        };
    }
    if (sidebarOverlay) {
        sidebarOverlay.onclick = () => {
            const sidebar = document.getElementById('folderSidebar');
            if (sidebar && !sidebar.classList.contains('hidden')) {
                sidebar.classList.add('hidden');
                sidebar.classList.remove('absolute', 'z-50', 'h-full', 'active');
                sidebarOverlay.classList.add('hidden');
                document.body.style.overflow = '';
            }
        };
    }
}

function openMoveToFolderModal(linkId, event) {
    if (event) event.stopPropagation();

    if (!window.folders || !window.updateLinkFolder || !window.showGenericModal) {
        console.error('Folder system not initialized');
        return;
    }

    const folders = window.folders;

    const content = `
        <div class="p-6">
            <h3 class="text-xl font-bold text-white mb-4">Move Link to Folder</h3>
            <div class="space-y-2 max-h-[60vh] overflow-y-auto custom-scrollbar">
                <button onclick="handleMoveLink('${linkId}', null)" class="w-full text-left px-4 py-3 rounded-lg bg-white/5 hover:bg-white/10 text-white flex items-center gap-3 transition-colors">
                    <i data-lucide="inbox" class="w-5 h-5 text-gray-400"></i>
                    <span class="font-medium">Unsorted</span>
                </button>
                ${folders.map(f => `
                    <button onclick="handleMoveLink('${linkId}', '${f.id}')" class="w-full text-left px-4 py-3 rounded-lg bg-white/5 hover:bg-white/10 text-white flex items-center gap-3 transition-colors">
                        <i data-lucide="folder" class="w-5 h-5" style="color: ${f.color}"></i>
                        <span class="font-medium">${escapeHtml(f.name)}</span>
                    </button>
                `).join('')}
            </div>
            <button onclick="closeGenericModal()" class="mt-6 w-full py-3 rounded-lg bg-white/5 text-gray-400 hover:text-white hover:bg-white/10 transition-colors">Cancel</button>
        </div>
    `;
    window.showGenericModal(content);
}

window.handleMoveLink = async (linkId, folderId) => {
    if (window.updateLinkFolder) {
        await window.updateLinkFolder(linkId, folderId);
        window.closeGenericModal();
        showToast(`Link moved to ${folderId ? 'folder' : 'Unsorted'}`, 'success');
    }
};

window.openMoveToFolderModal = openMoveToFolderModal;
window.setupFolderListeners = setupFolderListeners;

// ==================== Timeline Integration ====================

function setupTimelineListeners() {
    // Handle timeline tab switching
    document.querySelectorAll('.tab-btn[data-tab="timeline"]').forEach(btn => {
        btn.addEventListener('click', () => {
            // Render analytics dashboard
            const analyticsContainer = document.getElementById('timelineAnalytics');
            if (analyticsContainer && window.renderAnalyticsDashboard) {
                analyticsContainer.innerHTML = window.renderAnalyticsDashboard();
            }
            // Render timeline
            if (window.renderTimelineTab) {
                window.renderTimelineTab();
            }
            lucide.createIcons();
        });
    });

    // Add Event button
    const addEventBtn = document.getElementById('addTimelineEventBtn');
    if (addEventBtn) {
        addEventBtn.addEventListener('click', showAddTimelineEventModal);
    }
}

// Modal to add manual timeline event
function showAddTimelineEventModal() {
    const moodOptions = window.MOOD_OPTIONS || [];
    const content = `
        <div class="p-6">
            <h3 class="text-xl font-bold text-white mb-4 flex items-center gap-2">
                <i data-lucide="plus-circle" class="w-5 h-5 text-red-400"></i>
                Add Cognitive Event
            </h3>
            <form id="addTimelineEventForm" class="space-y-4">
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Type</label>
                    <select id="timelineEventType" class="w-full px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white">
                        <option value="idea">💡 Idea</option>
                        <option value="action">⚡ Action</option>
                        <option value="result">✅ Result</option>
                        <option value="insight">🔮 Insight</option>
                        <option value="decision">🎯 Decision</option>
                    </select>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Title *</label>
                    <input type="text" id="timelineEventTitle" required
                        class="w-full px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500"
                        placeholder="Describe this event...">
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-1">Details (optional)</label>
                    <textarea id="timelineEventContent" rows="3"
                        class="w-full px-4 py-2 rounded-lg bg-white/5 border border-white/10 text-white placeholder-gray-500 resize-none"
                        placeholder="Add notes, use #hashtags for auto-connections..."></textarea>
                </div>
                <div>
                    <label class="block text-sm text-gray-400 mb-2">Current Mood</label>
                    <div class="flex flex-wrap gap-2">
                        ${moodOptions.map(m => `
                            <label class="cursor-pointer">
                                <input type="radio" name="timelineMood" value="${m.id}" class="hidden peer">
                                <span class="px-3 py-1.5 rounded-full bg-white/5 border border-white/10 text-sm peer-checked:bg-red-500/30 peer-checked:border-red-500 transition-all">
                                    ${m.emoji} ${m.label}
                                </span>
                            </label>
                        `).join('')}
                    </div>
                </div>
                <div class="flex gap-2 pt-2">
                    <button type="submit" class="flex-1 px-4 py-2 rounded-lg bg-gradient-to-r from-red-500 to-red-500 text-white font-medium">
                        Add Event
                    </button>
                    <button type="button" onclick="closeGenericModal()" class="px-4 py-2 rounded-lg bg-white/10 text-white">
                        Cancel
                    </button>
                </div>
            </form>
        </div>
    `;

    window.showGenericModal(content);
    lucide.createIcons();

    document.getElementById('addTimelineEventForm').addEventListener('submit', async (e) => {
        e.preventDefault();

        const type = document.getElementById('timelineEventType').value;
        const title = document.getElementById('timelineEventTitle').value.trim();
        const content = document.getElementById('timelineEventContent').value.trim();
        const moodInput = document.querySelector('input[name="timelineMood"]:checked');
        const mood = moodInput ? moodInput.value : null;

        if (!title) {
            showToast('Please enter a title', 'error');
            return;
        }

        if (window.trackCognitiveEvent) {
            await window.trackCognitiveEvent('manual_entry', null, title, content, mood);
            // Override type
            const events = window.timelineEvents || [];
            if (events.length > 0) {
                events[0].type = type;
                await window.saveTimelineEventToDB(events[0]);
            }
        }

        closeGenericModal();
        showToast('Event added to timeline!', 'success');

        // Re-render if on timeline tab
        if (document.getElementById('timelineTab')?.classList.contains('tab-content') &&
            !document.getElementById('timelineTab')?.classList.contains('hidden')) {
            if (window.renderTimelineTab) window.renderTimelineTab();
            const analyticsContainer = document.getElementById('timelineAnalytics');
            if (analyticsContainer && window.renderAnalyticsDashboard) {
                analyticsContainer.innerHTML = window.renderAnalyticsDashboard();
            }
        }
    });
}

window.setupTimelineListeners = setupTimelineListeners;
window.showAddTimelineEventModal = showAddTimelineEventModal;

// Utility: Debounce function
function debounce(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// ==================== Data Export/Import ====================

// Export Full Backup
async function exportFullBackup() {
    try {
        const allTools = (window.tools && window.tools.length) ? window.tools : (typeof getAllToolsFromDB === 'function' ? await getAllToolsFromDB() : []);
        const data = {
            version: '2.0',
            exportedAt: new Date().toISOString(),
            links: window.links || [],
            folders: window.folders || [],
            notes: window.notes || [],
            timeline: window.timelineEvents || [],
            prompts: window.prompts || [],
            tools: Array.isArray(allTools) ? allTools : [],
            customLaws: localStorage.getItem('linkLumina_custom_laws'),
            settings: {
                storagePrompt: localStorage.getItem('linklumina-storage-prompt') || ''
            }
        };

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);

        const a = document.createElement('a');
        a.href = url;
        a.download = `linklumina_backup_${new Date().toISOString().slice(0, 10)}.json`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(url);

        showToast('Backup exported successfully!', 'success');
    } catch (e) {
        console.error('Export failed:', e);
        showToast('Export failed', 'error');
    }
}

// Import Full Backup
async function importFullBackup(e) {
    const file = e.target.files[0];
    if (!file) return;
    if ((file.name || '').toLowerCase().endsWith('.zip')) {
        await importFolderBackup(file);
        e.target.value = '';
        return;
    }
    await createSafetyBackupSnapshot('before-full-backup-import');

    const reader = new FileReader();
    reader.onload = async (event) => {
        try {
            const data = JSON.parse(event.target.result);

            if (!confirm(`Found ${data.links?.length || 0} links, ${data.notes?.length || 0} notes, ${data.tools?.length || 0} tools. Merge with existing data?`)) {
                e.target.value = '';
                return;
            }

            // Import Links
            if (data.links) {
                const existingLinkIds = new Set(window.links.map(l => l.id).filter(Boolean));
                const existingLinkUrls = new Set(window.links.map(l => normalizeUrlForMerge(l.url)).filter(Boolean));
                for (const link of data.links) {
                    // Avoid duplicates by ID or URL
                    const normalizedUrl = normalizeUrlForMerge(link.url);
                    if (!link?.id || existingLinkIds.has(link.id) || (normalizedUrl && existingLinkUrls.has(normalizedUrl))) continue;
                    existingLinkIds.add(link.id);
                    if (normalizedUrl) existingLinkUrls.add(normalizedUrl);
                    await saveLinkToDB(link);
                    window.links.push(link);
                }
            }

            // Import Folders
            if (data.folders) {
                const currentIds = new Set(window.folders.map(f => f.id));
                const tx = db.transaction(['folders'], 'readwrite');
                const store = tx.objectStore('folders');
                for (const folder of data.folders) {
                    if (folder?.id && !currentIds.has(folder.id)) {
                        currentIds.add(folder.id);
                        store.put(folder);
                        window.folders.push(folder);
                    }
                }
            }

            // Import Notes
            if (data.notes) {
                const existingIds = new Set((window.notes || []).map(note => note.id).filter(Boolean));
                for (const note of data.notes) {
                    if (!note?.id || existingIds.has(note.id)) continue;
                    existingIds.add(note.id);
                    await saveNoteToDB(note);
                    if (window.notes) window.notes.push(note);
                }
            }

            // Import Prompts
            if (data.prompts) {
                const existingIds = new Set((window.prompts || []).map(prompt => prompt.id).filter(Boolean));
                for (const prompt of data.prompts) {
                    if (!prompt?.id || existingIds.has(prompt.id)) continue;
                    existingIds.add(prompt.id);
                    await savePromptToDB(prompt);
                    window.prompts.push(prompt);
                }
            }

            // Import Colors / Snippets / Todos / Files
            const storeImports = [
                ['colors', ensureArray(data.colors), window.colors],
                ['snippets', ensureArray(data.snippets), window.snippets],
                ['todos', ensureArray(data.todos), window.todos],
                ['files', ensureArray(data.files), window.files]
            ];
            for (const [storeName, items, target] of storeImports) {
                const existingIds = new Set((target || []).map(item => item.id).filter(Boolean));
                for (const item of items) {
                    if (!item?.id || existingIds.has(item.id)) continue;
                    existingIds.add(item.id);
                    if (typeof saveToStore === 'function') await saveToStore(storeName, item);
                    if (Array.isArray(target)) target.push(item);
                }
            }

            // Import Timeline
            if (data.timeline) {
                const existingIds = new Set((window.timelineEvents || []).map(evt => evt.id).filter(Boolean));
                for (const evt of data.timeline) {
                    if (!evt?.id || existingIds.has(evt.id)) continue;
                    existingIds.add(evt.id);
                    if (typeof window.saveTimelineEventToDB === 'function') await window.saveTimelineEventToDB(evt);
                    if (window.timelineEvents) window.timelineEvents.push(evt);
                }
            }

            // Import Tools
            if (data.tools && Array.isArray(data.tools) && db.objectStoreNames.contains('tools')) {
                if (!window.tools) window.tools = [];
                const existingToolIds = new Set(window.tools.map(t => t.id));
                for (const t of data.tools) {
                    if (!t.id || existingToolIds.has(t.id)) continue;
                    existingToolIds.add(t.id);
                    window.tools.push(t);
                    await saveToolToDB(t);
                }
            }

            // Import Custom Laws
            if (data.customLaws && window.LawEngine) {
                // Merge custom laws logic if needed, or just append
                // specific implementation depends on law engine, for now manual setting if empty could work
                // But let's respect current local storage
            }

            showToast('Backup imported successfully! Please refresh.', 'success');
            setTimeout(() => location.reload(), 1500);

        } catch (err) {
            console.error('Import failed:', err);
            showToast('Invalid JSON file', 'error');
        }
        e.target.value = ''; // Reset input
    };
    reader.readAsText(file);
}

// Initializer for Export/Import Listeners (Legacy/Addon inputs)
function setupDataTransferListeners() {
    // Note: exportJsonBtn listener already attached in setupEventListeners (line 443)
    // Only handle additional input elements here

    const importInput = document.getElementById('importJsonInput');
    if (importInput) importInput.addEventListener('change', importFullBackup);
}

// Call setup at end of loading
document.addEventListener('DOMContentLoaded', setupDataTransferListeners);

// Handle paste in Quick Save to ensure newlines
function handleQuickSavePaste(e) {
    // Prevent default paste
    e.preventDefault();

    // Get pasted data
    const clipboardData = (e.clipboardData || window.clipboardData).getData('text');
    const input = e.target;

    if (!clipboardData) return;

    const cursorStart = input.selectionStart;
    const cursorEnd = input.selectionEnd;
    const textBefore = input.value.substring(0, cursorStart);
    const textAfter = input.value.substring(cursorEnd);

    // Ensure we start on a new line if we are not at the beginning and the previous char is not a newline
    let prefix = '';
    if (cursorStart > 0 && textBefore[cursorStart - 1] !== '\n') {
        prefix = '\n';
    }

    // Always add a newline after the pasted content
    let contentToInsert = clipboardData;
    if (!contentToInsert.endsWith('\n')) {
        contentToInsert += '\n';
    }

    // Update input value
    const newText = textBefore + prefix + contentToInsert + textAfter;
    input.value = newText;

    // Move cursor to end of inserted text
    const newCursorPos = cursorStart + prefix.length + contentToInsert.length;
    input.setSelectionRange(newCursorPos, newCursorPos);

    // Trigger input event
    input.dispatchEvent(new Event('input'));
}

// Global Mouse tracking for 3D Link Card Glow (Optimized with requestAnimationFrame)
let globalMouseX = 0;
let globalMouseY = 0;
let trackingCard = null;
let isTrackingFrameRequested = false;

document.addEventListener('mousemove', e => {
    const card = e.target.closest('.link-card');
    if (!card) {
        trackingCard = null;
        return;
    }

    globalMouseX = e.clientX;
    globalMouseY = e.clientY;
    trackingCard = card;

    if (!isTrackingFrameRequested) {
        requestAnimationFrame(() => {
            if (trackingCard) {
                const rect = trackingCard.getBoundingClientRect();
                const x = globalMouseX - rect.left;
                const y = globalMouseY - rect.top;
                trackingCard.style.setProperty('--mouse-x', `${x}px`);
                trackingCard.style.setProperty('--mouse-y', `${y}px`);
            }
            isTrackingFrameRequested = false;
        });
        isTrackingFrameRequested = true;
    }
});

// Global Search Shortcut (Ctrl+K or /)
document.addEventListener('keydown', e => {
    // Ignore if user is already typing in an input/textarea
    if (['INPUT', 'TEXTAREA', 'SELECT'].includes(e.target.tagName)) return;

    // Check for Ctrl+K or /
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k' || e.key === '/') {
        e.preventDefault();
        const searchInput = document.getElementById('searchInput');
        if (searchInput) {
            // First, switch to Links Tab if not already there since search is primarily for links
            const linksTabObj = document.querySelector('.tab-btn[data-tab="links"]');
            if (linksTabObj && !linksTabObj.classList.contains('active')) {
                linksTabObj.click();
            }
            searchInput.focus();
        }
    }
});

// Back to Top FAB
document.addEventListener('DOMContentLoaded', () => {
    const backToTopBtn = document.getElementById('backToTopBtn');
    if (backToTopBtn) {
        window.addEventListener('scroll', () => {
            if (window.scrollY > 300) {
                backToTopBtn.classList.remove('opacity-0', 'translate-y-10', 'pointer-events-none');
            } else {
                backToTopBtn.classList.add('opacity-0', 'translate-y-10', 'pointer-events-none');
            }
        }, { passive: true });

        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({ top: 0, behavior: 'smooth' });
        });
    }
});

// ==================== LINKLUMINA EXTENSION BRIDGE (two-way) ====================
// Lets the web app talk to the installed extension (via the content script) and
// receive pushed data (e.g. "save all open tabs") without reloading or closing tabs.
(function () {
    'use strict';
    const SOURCE = 'linklumina-page';
    const pending = new Map();

    function postToExt(message) {
        window.postMessage(message, '*');
    }

    function requestExtension(action, payload, timeoutMs = 6000) {
        return new Promise((resolve) => {
            const requestId = 'req_' + Date.now() + '_' + Math.random().toString(36).slice(2, 8);
            pending.set(requestId, resolve);
            postToExt({ source: SOURCE, type: 'request', action, payload, requestId });
            setTimeout(() => {
                if (pending.has(requestId)) {
                    pending.delete(requestId);
                    resolve({ ok: false, reason: 'timeout' });
                }
            }, timeoutMs);
        });
    }

    window.addEventListener('message', (event) => {
        const data = event.data;
        if (!data || data.source !== SOURCE) return;
        if (data.type === 'response') {
            const resolve = pending.get(data.requestId);
            if (resolve) {
                pending.delete(data.requestId);
                resolve(data.result);
            }
        } else if (data.type === 'push' && data.action === 'importOpenTabs') {
            importOpenTabsFromExtension(data.payload && data.payload.links, data.pushId);
        }
    });

    async function importOpenTabsFromExtension(rawLinks, pushId) {
        if (!Array.isArray(rawLinks) || !rawLinks.length) return;
        const list = window.links || (window.links = []);
        const existingUrls = new Set(list.map(l => l && l.url).filter(Boolean));
        let added = 0;
        const now = new Date().toISOString();
        for (const item of rawLinks) {
            const url = String(item && item.url || '').trim();
            if (!/^https?:/i.test(url)) continue;
            if (existingUrls.has(url)) continue;
            existingUrls.add(url);
            const link = {
                id: 'open_' + Date.now() + '_' + Math.random().toString(36).slice(2, 10),
                url,
                title: String(item.title || url).slice(0, 500),
                category: '',
                tags: ['open-tab'],
                folderId: null,
                notes: '',
                favorite: false,
                visitCount: 0,
                lastVisited: null,
                createdAt: now
            };
            list.push(link);
            try {
                await saveLinkToDB(link);
            } catch (e) {
                console.error('Failed saving extension tab link:', e);
            }
            added++;
        }
        if (added) {
            if (typeof renderLinks === 'function') renderLinks();
            if (typeof scheduleImmediateBackupDownload === 'function') scheduleImmediateBackupDownload();
            showToast(`Extension synced ${added} open tab(s).`, 'success');
        }
        if (pushId) {
            postToExt({ source: SOURCE, type: 'done', pushId, count: added });
        }
    }

    window.LinkLuminaExtension = {
        importOpenTabs: importOpenTabsFromExtension,
        listOpenTabs: () => requestExtension('listOpenTabs'),
        openTab: (url) => requestExtension('openTab', { url }),
        isAvailable: false
    };

    requestExtension('listOpenTabs').then(res => {
        window.LinkLuminaExtension.isAvailable = !!(res && res.ok);
    });
})();
