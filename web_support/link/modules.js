// ==================== Knowledge Hub Modules ====================
// Notes, Snippets, Colors, Todos, Files

// State for new modules
var notes = window.notes = window.notes || [];
var snippets = window.snippets = window.snippets || [];
var colors = window.colors = window.colors || [];
var todos = window.todos = window.todos || [];
var files = window.files = window.files || [];
var currentTab = window.currentTab = 'links';

// Expose variables for Neural Web (Global Access)
if (!Object.getOwnPropertyDescriptor(window, 'notes')) {
    Object.defineProperty(window, 'notes', { get: () => notes, configurable: true });
}
if (!Object.getOwnPropertyDescriptor(window, 'uniqueTags')) {
    Object.defineProperty(window, 'uniqueTags', {
        get: () => {
            // Helper to get all tags from links
            const tags = new Set();
            if (typeof links !== 'undefined') links.forEach(l => l.tags.forEach(t => tags.add(t)));
            return Array.from(tags);
        },
        configurable: true
    });
}

// Polyfill initializeIcons until script.js loads
window.initializeIcons = window.initializeIcons || function () { };

// ==================== Tab Navigation ====================

function setupTabNavigation() {
    const tabBtns = document.querySelectorAll('.tab-btn');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            const tabName = btn.dataset.tab;
            switchTab(tabName);
        });
    });
}

function switchTab(tabName) {
    currentTab = tabName;

    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    // Hide all tab contents
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.add('hidden');
    });

    // Show selected tab
    const tabContent = document.getElementById(`${tabName}Tab`);
    if (tabContent) {
        tabContent.classList.remove('hidden');
    }

    if (typeof window.updateMobileFabVisibility === 'function') window.updateMobileFabVisibility();

    // Scroll to top of page
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Render content for the tab
    switch (tabName) {
        case 'prompts':
            renderPromptsTab();
            break;
        case 'notes':
            renderNotesTab();
            break;
        case 'snippets':
            renderSnippetsTab();
            break;
        case 'colors':
            renderColorsTab();
            break;
        case 'todos':
            renderTodosTab();
            break;
        case 'files':
            renderFilesTab();
            break;
        case 'transcript':
            if (window.renderTranscriptTab) window.renderTranscriptTab();
            break;
        case 'tools':
            if (window.renderToolsTab) window.renderToolsTab();
            break;
    }

    initializeIcons();
}

// ==================== IndexedDB for New Modules ====================

async function initNewStores() {
    // Handled by script.js (IndexedDB v4)
    return;
}

// Generic store helpers
async function saveToStore(storeName, item) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([storeName], 'readwrite');
        const store = transaction.objectStore(storeName);
        const request = store.put(item);
        request.onsuccess = () => {
            if (typeof window.scheduleRecoverySnapshot === 'function') {
                window.scheduleRecoverySnapshot(`${storeName}:save`);
            }
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function deleteFromStore(storeName, id) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction([storeName], 'readwrite');
        const store = transaction.objectStore(storeName);
        const request = store.delete(id);
        request.onsuccess = () => {
            if (typeof window.scheduleRecoverySnapshot === 'function') {
                window.scheduleRecoverySnapshot(`${storeName}:delete`);
            }
            resolve();
        };
        request.onerror = () => reject(request.error);
    });
}

async function getAllFromStore(storeName) {
    return new Promise((resolve, reject) => {
        if (!db.objectStoreNames.contains(storeName)) {
            resolve([]);
            return;
        }
        const transaction = db.transaction([storeName], 'readonly');
        const store = transaction.objectStore(storeName);
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result || []);
        request.onerror = () => reject(request.error);
    });
}

// Load all new module data (waits for db from script.js)
async function loadNewModuleData() {
    let wait = 0;
    while ((!window.db || !window.db.objectStoreNames) && wait < 50) {
        await new Promise(r => setTimeout(r, 100));
        wait++;
    }
    if (!window.db) return;
    try {
        notes = await getAllFromStore('notes');
        snippets = await getAllFromStore('snippets');
        colors = await getAllFromStore('colors');
        todos = await getAllFromStore('todos');
        files = await getAllFromStore('files');
        window.notes = notes;
        window.snippets = snippets;
        window.colors = colors;
        window.todos = todos;
        window.files = files;
    } catch (e) {
        console.warn('Module data load:', e.message || 'stores not ready');
    }
}

window.loadNewModuleData = loadNewModuleData;
window.saveToStore = saveToStore;
window.deleteFromStore = deleteFromStore;

// ==================== Notes Module (Enhanced) ====================

function formatNoteSize(content) {
    const chars = content.length;
    const words = content.trim().split(/\s+/).filter(w => w.length > 0).length;
    if (chars > 1000) {
        return `${(chars / 1000).toFixed(1)}K chars · ${words} words`;
    }
    return `${chars} chars · ${words} words`;
}

function renderNotesTab() {
    const grid = document.getElementById('notesGrid');
    const empty = document.getElementById('notesEmpty');

    if (notes.length === 0) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    grid.innerHTML = notes.map(note => `
        <div class="glass-card note-card p-4 cursor-pointer" onclick="editNote('${note.id}')">
            <div class="flex items-start justify-between mb-2">
                <h3 class="text-white font-semibold truncate flex-1">${escapeHtml(note.title)}</h3>
                ${note.pinned ? '<i data-lucide="pin" class="w-4 h-4 text-red-400"></i>' : ''}
            </div>
            <p class="text-gray-400 text-sm line-clamp-3 mb-3">${escapeHtml(note.content.substring(0, 25000))}${note.content.length > 25000 ? '...' : ''}</p>
            <div class="flex items-center justify-between">
                <div class="flex items-center gap-2">
                    <span class="text-xs text-gray-500">${new Date(note.createdAt).toLocaleDateString()}</span>
                    <span class="text-xs text-red-400">${formatNoteSize(note.content)}</span>
                </div>
                <div class="flex gap-1">
                    <button onclick="event.stopPropagation(); openTranslateModalWithNoteId('${note.id}')" class="p-1.5 rounded hover:bg-cyan-500/20 text-cyan-400" title="Translate note content">
                        <i data-lucide="languages" class="w-4 h-4"></i>
                    </button>
                    <button onclick="event.stopPropagation(); downloadNoteAsMarkdown('${note.id}')" class="p-1.5 rounded hover:bg-blue-500/20 text-blue-400" title="Download as Markdown">
                        <i data-lucide="download" class="w-4 h-4"></i>
                    </button>
                    <button onclick="event.stopPropagation(); deleteNote('${note.id}')" class="p-1.5 rounded hover:bg-red-500/20 text-red-400" title="Delete">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');

    initializeIcons();
}

function openNoteModal(noteId = null) {
    const note = noteId ? notes.find(n => n.id === noteId) : null;
    const title = note ? 'Edit Note' : 'Add Note';
    const charCount = note ? note.content.length : 0;
    const wordCount = note ? note.content.trim().split(/\s+/).filter(w => w.length > 0).length : 0;

    const content = `
        <div class="p-6 max-h-[90vh] overflow-y-auto">
            <h2 class="text-2xl font-bold text-white mb-4">${title}</h2>
            <p class="text-sm text-gray-400 mb-4">Supports unlimited length. Content will be saved as Markdown.</p>
            <form id="noteForm" class="space-y-4">
                <input type="hidden" id="noteId" value="${note?.id || ''}">
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Title</label>
                    <input type="text" id="noteTitle" required value="${escapeHtml(note?.title || '')}"
                        class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:ring-2 focus:ring-red-500"
                        placeholder="Note title...">
                </div>
                <div>
                    <div class="flex items-center justify-between mb-2">
                        <label class="text-sm font-medium text-gray-300">Content (Markdown)</label>
                        <span id="noteCharCount" class="text-xs text-red-400">${charCount.toLocaleString()} chars · ${wordCount} words</span>
                    </div>
                    <textarea id="noteContent" rows="15" required
                        class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:ring-2 focus:ring-red-500 resize-y font-mono text-sm leading-relaxed"
                        placeholder="Write your note here... Supports Markdown formatting."
                        style="min-height: 300px; max-height: 60vh;">${escapeHtml(note?.content || '')}</textarea>
                </div>
                <div class="flex items-center gap-4">
                    <div class="flex items-center gap-2">
                        <input type="checkbox" id="notePinned" ${note?.pinned ? 'checked' : ''} class="rounded">
                        <label for="notePinned" class="text-gray-300">Pin this note</label>
                    </div>
                </div>
                <div class="flex gap-3 flex-wrap">
                    <button type="submit" class="flex-1 min-w-[120px] px-6 py-3 rounded-lg bg-gradient-to-r from-green-500 to-teal-500 text-white font-medium">
                        <i data-lucide="save" class="inline w-4 h-4 mr-2"></i>Save Note
                    </button>
                    ${note ? `<button type="button" onclick="downloadNoteAsMarkdown('${note.id}')" class="px-6 py-3 rounded-lg bg-blue-500/20 text-blue-300 hover:bg-blue-500/30">
                        <i data-lucide="download" class="inline w-4 h-4 mr-2"></i>Download .md
                    </button>` : ''}
                    <button type="button" onclick="closeGenericModal()" class="px-6 py-3 rounded-lg bg-white/5 text-white">Cancel</button>
                </div>
            </form>
        </div>
    `;
    showGenericModal(content);

    // Setup character/word counter
    const textarea = document.getElementById('noteContent');
    const counter = document.getElementById('noteCharCount');
    textarea.addEventListener('input', () => {
        const chars = textarea.value.length;
        const words = textarea.value.trim().split(/\s+/).filter(w => w.length > 0).length;
        counter.textContent = `${chars.toLocaleString()} chars · ${words.toLocaleString()} words`;
    });

    document.getElementById('noteForm').addEventListener('submit', handleNoteSave);
    initializeIcons();
}

// Download note as Markdown file
function downloadNoteAsMarkdown(id) {
    const note = notes.find(n => n.id === id);
    if (!note) return;

    // Create markdown content with frontmatter
    const frontmatter = `---
title: ${note.title}
created: ${note.createdAt}
updated: ${note.updatedAt || note.createdAt}
---

`;
    const markdownContent = frontmatter + note.content;

    // Create blob and download
    const blob = new Blob([markdownContent], { type: 'text/markdown;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = `${note.title.replace(/[^a-zA-Z0-9]/g, '_')}.md`;
    link.click();
    URL.revokeObjectURL(url);

    showToast(`Downloaded: ${note.title}.md`, 'success');
}

window.downloadNoteAsMarkdown = downloadNoteAsMarkdown;

async function handleNoteSave(e) {
    e.preventDefault();

    const id = document.getElementById('noteId').value || Date.now().toString();
    const note = {
        id,
        title: document.getElementById('noteTitle').value.trim(),
        content: document.getElementById('noteContent').value,
        pinned: document.getElementById('notePinned').checked,
        createdAt: notes.find(n => n.id === id)?.createdAt || new Date().toISOString(),
        updatedAt: new Date().toISOString()
    };

    const existingIndex = notes.findIndex(n => n.id === id);
    if (existingIndex >= 0) {
        notes[existingIndex] = note;
    } else {
        notes.push(note);
    }

    await saveToStore('notes', note);
    closeGenericModal();
    renderNotesTab();
    showToast('Note saved!', 'success');
}

async function deleteNote(id) {
    if (confirm('Delete this note?')) {
        notes = notes.filter(n => n.id !== id);
        await deleteFromStore('notes', id);
        renderNotesTab();
        showToast('Note deleted!', 'success');
    }
}

window.editNote = (id) => openNoteModal(id);
window.deleteNote = deleteNote;

// ==================== Translate Modal (4 panels: top fixed, bottom editable) ====================

function openTranslateModal(initialText = '') {
    const modal = document.getElementById('translateModal');
    if (!modal) return;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    const topOriginal = document.getElementById('translateTopOriginal');
    const topTranslated = document.getElementById('translateTopTranslated');
    const bottomOriginal = document.getElementById('translateBottomOriginal');
    const bottomTranslated = document.getElementById('translateBottomTranslated');
    const lockLabel = document.getElementById('translateLockLabel');
    const lockIcon = document.getElementById('translateLockIcon');
    const topOriginalLabel = document.getElementById('translateTopOriginalLabel');
    const topTranslatedLabel = document.getElementById('translateTopTranslatedLabel');

    // By default the top two panels are editable (not locked)
    topOriginal.readOnly = false;
    topTranslated.readOnly = false;
    if (lockLabel) lockLabel.textContent = 'Lock top 2 panels';
    if (lockIcon) lockIcon.setAttribute('data-lucide', 'lock');
    if (topOriginalLabel) topOriginalLabel.textContent = 'Original (type or paste, then Translate)';
    if (topTranslatedLabel) topTranslatedLabel.textContent = 'Translation';

    if (initialText) {
        topOriginal.value = initialText;
        bottomOriginal.value = initialText;
        topTranslated.value = '';
        bottomTranslated.value = '';
    } else {
        topOriginal.value = '';
        topTranslated.value = '';
        bottomOriginal.value = '';
        bottomTranslated.value = '';
    }
    initializeIcons();
}

function closeTranslateModal() {
    const modal = document.getElementById('translateModal');
    if (modal) modal.classList.add('hidden');
    document.body.style.overflow = '';
}

/** Max characters per chunk (MyMemory: MAX ALLOWED QUERY 500 CHARS – measured on the encoded query) */
const TRANSLATE_MAX_QUERY_CHARS = 500;

/**
 * Split text into chunks so encodeURIComponent(chunk).length <= maxEncodedChars; prefer cutting at word/sentence ends.
 * @param {string} text
 * @param {number} maxEncodedChars
 * @returns {string[]}
 */
function splitTextIntoChunks(text, maxEncodedChars) {
    const t = (text || '').trim();
    if (!t) return [];
    if (encodeURIComponent(t).length <= maxEncodedChars) return [t];

    const chunks = [];
    let start = 0;

    while (start < t.length) {
        let end = start;
        let bestEnd = start;
        while (end < t.length) {
            const candidate = t.slice(start, end + 1);
            if (encodeURIComponent(candidate).length > maxEncodedChars) break;
            bestEnd = end + 1;
            end++;
        }
        end = bestEnd;
        if (end <= start) {
            // A single character already exceeds the limit (e.g. long emoji) – hard cut
            end = start + 1;
        }
        if (end < t.length) {
            // Cut at the whitespace or sentence end (., !, ?) nearest to end
            let cut = -1;
            for (let i = end - 1; i >= start && i >= end - 80; i--) {
                const c = t[i];
                if (/\s/.test(c) || /[.!?]/.test(c)) {
                    cut = i + 1;
                    break;
                }
            }
            if (cut > start) end = cut;
        }
        chunks.push(t.slice(start, end).trim());
        start = end;
        while (start < t.length && /\s/.test(t[start])) start++;
    }
    return chunks.filter(Boolean);
}

async function translateText(text, fromLang, toLang) {
    if (!text || !text.trim()) return '';
    const q = encodeURIComponent(text.trim());
    const langpair = `${fromLang}|${toLang}`;
    try {
        const res = await fetch(`https://api.mymemory.translated.net/get?q=${q}&langpair=${langpair}`);
        const data = await res.json();
        if (data.responseStatus === 200 && data.responseData && data.responseData.translatedText) {
            return data.responseData.translatedText;
        }
        return data.responseData?.translatedText || '';
    } catch (e) {
        console.error('Translate error:', e);
        return '';
    }
}

/**
 * Translate long text by splitting it into chunks of up to 500 chars, translating each in turn, then joining.
 * @param {string} text
 * @param {string} fromLang
 * @param {string} toLang
 * @param {(current: number, total: number, partialResult: string) => void} onProgress Called after each chunk completes (current, total, partialResult).
 * @returns {Promise<string>}
 */
async function translateTextLong(text, fromLang, toLang, onProgress) {
    const t = (text || '').trim();
    if (!t) return '';

    const chunks = splitTextIntoChunks(t, TRANSLATE_MAX_QUERY_CHARS);
    if (chunks.length === 1) {
        const result = await translateText(t, fromLang, toLang);
        if (onProgress) onProgress(1, 1, result);
        return result;
    }

    const parts = [];
    for (let i = 0; i < chunks.length; i++) {
        const translated = await translateText(chunks[i], fromLang, toLang);
        parts.push(translated || '');
        const partialResult = parts.join('\n\n');
        if (onProgress) onProgress(i + 1, chunks.length, partialResult);
        // Brief pause between requests to avoid API rate-limiting
        if (i < chunks.length - 1) await new Promise(r => setTimeout(r, 300));
    }
    return parts.join('\n\n');
}

async function doTranslateUpdateTop() {
    const topOriginal = document.getElementById('translateTopOriginal');
    const topTranslated = document.getElementById('translateTopTranslated');
    const fromLang = document.getElementById('translateLangFrom')?.value || 'en';
    const toLang = document.getElementById('translateLangTo')?.value || 'vi';

    const sourceText = (topOriginal?.value || '').trim();
    if (!sourceText) {
        showToast('Type or paste text into the original panel (top), then hit Translate.', 'warning');
        return;
    }

    const totalChunks = splitTextIntoChunks(sourceText, TRANSLATE_MAX_QUERY_CHARS).length;
    if (totalChunks > 1) {
        topTranslated.value = `Translating (${totalChunks} chunks, each ≤ ${TRANSLATE_MAX_QUERY_CHARS} chars)...`;
    } else {
        topTranslated.value = 'Translating...';
    }

    const translated = await translateTextLong(sourceText, fromLang, toLang, (current, total, partialResult) => {
        if (total > 1 && topTranslated) {
            topTranslated.value = partialResult + (current < total ? `\n\n[Translating chunk ${current}/${total}...]` : '');
        }
    });

    topTranslated.value = translated || '';
    showToast(translated ? (totalChunks > 1 ? `Translated ${totalChunks} chunks.` : 'Translated.') : 'Translation failed.', translated ? 'success' : 'error');
    initializeIcons();
}

async function doTranslateAgainBottomOnly() {
    const bottomOriginal = document.getElementById('translateBottomOriginal');
    const bottomTranslated = document.getElementById('translateBottomTranslated');
    const fromLang = document.getElementById('translateLangFrom')?.value || 'en';
    const toLang = document.getElementById('translateLangTo')?.value || 'vi';

    const sourceText = (bottomOriginal?.value || '').trim();
    if (!sourceText) {
        showToast('Type text into the bottom original panel.', 'warning');
        return;
    }

    const totalChunks = splitTextIntoChunks(sourceText, TRANSLATE_MAX_QUERY_CHARS).length;
    if (totalChunks > 1) {
        bottomTranslated.value = `Translating (${totalChunks} chunks, each ≤ ${TRANSLATE_MAX_QUERY_CHARS} chars)...`;
    } else {
        bottomTranslated.value = 'Translating...';
    }

    const translated = await translateTextLong(sourceText, fromLang, toLang, (current, total, partialResult) => {
        if (total > 1 && bottomTranslated) {
            bottomTranslated.value = partialResult + (current < total ? `\n\n[Translating chunk ${current}/${total}...]` : '');
        }
    });

    bottomTranslated.value = translated || '';
    showToast(translated ? (totalChunks > 1 ? `Translated ${totalChunks} chunks.` : 'Bottom translation updated.') : 'Translation failed.', translated ? 'success' : 'error');
}

function copyTranslateBottomToClipboard() {
    const bottomTranslated = document.getElementById('translateBottomTranslated');
    const text = bottomTranslated?.value || '';
    if (!text) {
        showToast('Nothing to copy yet.', 'warning');
        return;
    }
    navigator.clipboard.writeText(text).then(() => showToast('Translation copied (bottom 2 panels).', 'success')).catch(() => showToast('Copy failed.', 'error'));
}

// The top two panels only lock when this button is pressed (read-only)
function toggleTranslateTopLock() {
    const topOriginal = document.getElementById('translateTopOriginal');
    const topTranslated = document.getElementById('translateTopTranslated');
    const bottomOriginal = document.getElementById('translateBottomOriginal');
    const bottomTranslated = document.getElementById('translateBottomTranslated');
    const lockLabel = document.getElementById('translateLockLabel');
    const lockIcon = document.getElementById('translateLockIcon');
    const topOriginalLabel = document.getElementById('translateTopOriginalLabel');
    const topTranslatedLabel = document.getElementById('translateTopTranslatedLabel');

    if (topOriginal.readOnly) {
        // Unlock: the top two panels become editable again
        topOriginal.readOnly = false;
        topTranslated.readOnly = false;
        if (lockLabel) lockLabel.textContent = 'Lock top 2 panels';
        if (lockIcon) lockIcon.setAttribute('data-lucide', 'lock');
        if (topOriginalLabel) topOriginalLabel.textContent = 'Original (type or paste, then Translate)';
        if (topTranslatedLabel) topTranslatedLabel.textContent = 'Translation';
        showToast('Top 2 panels unlocked.', 'info');
    } else {
        // Lock: copy the top two panels down, then make the top two read-only
        if (bottomOriginal) bottomOriginal.value = topOriginal?.value || '';
        if (bottomTranslated) bottomTranslated.value = topTranslated?.value || '';
        topOriginal.readOnly = true;
        topTranslated.readOnly = true;
        if (lockLabel) lockLabel.textContent = 'Unlock top 2 panels';
        if (lockIcon) lockIcon.setAttribute('data-lucide', 'unlock');
        if (topOriginalLabel) topOriginalLabel.textContent = 'Original (locked – read-only)';
        if (topTranslatedLabel) topTranslatedLabel.textContent = 'Translation (locked – read-only)';
        showToast('Top 2 panels locked. Continue editing in the bottom 2.', 'success');
    }
    initializeIcons();
}

function setupTranslateModal() {
    const openBtn = document.getElementById('openTranslateModalBtn');
    const modal = document.getElementById('translateModal');
    const closeBtn = document.getElementById('translateModalClose');
    const doBtn = document.getElementById('translateDoBtn');
    const lockBtn = document.getElementById('translateLockBtn');
    const againBtn = document.getElementById('translateAgainBtn');
    const copyBtn = document.getElementById('translateCopyTranslatedBtn');
    const bodyEl = document.getElementById('translateModalBody');
    const handleEl = document.getElementById('translateResizeHandle');

    if (openBtn) openBtn.addEventListener('click', () => openTranslateModal());
    if (closeBtn) closeBtn.addEventListener('click', closeTranslateModal);
    if (modal) modal.addEventListener('click', (e) => { if (e.target === modal) closeTranslateModal(); });
    if (doBtn) doBtn.addEventListener('click', doTranslateUpdateTop);
    if (lockBtn) lockBtn.addEventListener('click', toggleTranslateTopLock);
    if (againBtn) againBtn.addEventListener('click', doTranslateAgainBottomOnly);
    if (copyBtn) copyBtn.addEventListener('click', copyTranslateBottomToClipboard);

    if (bodyEl && handleEl) {
        handleEl.addEventListener('mousedown', function (e) {
            e.preventDefault();
            const startY = e.clientY;
            const cs = getComputedStyle(bodyEl);
            const h = cs.height;
            const startH = h ? parseFloat(h) : window.innerHeight * 0.5;
            const maxH = Math.min(window.innerHeight * 0.8, 800);
            const minH = 280;

            function onMove(moveEvent) {
                const dy = moveEvent.clientY - startY;
                let newH = startH + dy;
                newH = Math.max(minH, Math.min(maxH, newH));
                bodyEl.style.setProperty('--translate-body-h', newH + 'px');
            }
            function onUp() {
                document.removeEventListener('mousemove', onMove);
                document.removeEventListener('mouseup', onUp);
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
            }
            document.body.style.cursor = 'n-resize';
            document.body.style.userSelect = 'none';
            document.addEventListener('mousemove', onMove);
            document.addEventListener('mouseup', onUp);
        });
    }
}

function openTranslateModalWithNoteId(noteId) {
    const note = notes.find(n => n.id === noteId);
    openTranslateModal(note ? note.content : '');
}

function openTranslateModalForLink(linkId) {
    const link = (window.links || []).find(l => l.id === linkId);
    openTranslateModal(link ? (link.notes || link.title || '') : '');
}
window.openTranslateModal = openTranslateModal;
window.openTranslateModalWithNoteId = openTranslateModalWithNoteId;
window.openTranslateModalForLink = openTranslateModalForLink;

// ==================== Code Snippets Module ====================

var LANGUAGES = window.LANGUAGES = ['javascript', 'python', 'html', 'css', 'sql', 'json', 'bash', 'typescript', 'java', 'cpp', 'php', 'ruby', 'go', 'rust', 'other'];

function renderSnippetsTab() {
    const grid = document.getElementById('snippetsGrid');
    const empty = document.getElementById('snippetsEmpty');

    // Use window.snippets to ensure we have the array
    const snippetList = window.snippets || [];

    if (snippetList.length === 0) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    grid.innerHTML = snippetList.map(snippet => `
        <div class="glass-card snippet-card p-4">
            <div class="flex items-start justify-between mb-2">
                <h3 class="text-white font-semibold truncate flex-1">${escapeHtml(snippet.title)}</h3>
                <span class="px-2 py-1 rounded text-xs bg-blue-500/20 text-blue-300">${snippet.language}</span>
            </div>
            <pre class="text-sm text-gray-300 p-3 mb-3 max-h-40 overflow-auto"><code>${escapeHtml(snippet.code.substring(0, 25000))}${snippet.code.length > 25000 ? '...' : ''}</code></pre>
            <div class="flex items-center justify-between">
                <span class="text-xs text-gray-500">${new Date(snippet.createdAt).toLocaleDateString()}</span>
                <div class="flex gap-2">
                    <button onclick="copySnippet('${snippet.id}')" class="p-1.5 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300" title="Copy">
                        <i data-lucide="copy" class="w-4 h-4"></i>
                    </button>
                    <button onclick="editSnippet('${snippet.id}')" class="p-1.5 rounded bg-blue-500/20 hover:bg-blue-500/30 text-blue-300" title="Edit">
                        <i data-lucide="edit" class="w-4 h-4"></i>
                    </button>
                    <button onclick="deleteSnippet('${snippet.id}')" class="p-1.5 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300" title="Delete">
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </div>
            </div>
        </div>
    `).join('');

    initializeIcons();
}

function openSnippetModal(snippetId = null) {
    const snippet = snippetId ? snippets.find(s => s.id === snippetId) : null;
    const langOptions = LANGUAGES.map(l => `<option value="${l}" ${snippet?.language === l ? 'selected' : ''}>${l}</option>`).join('');

    const content = `
        <div class="p-6">
            <h2 class="text-2xl font-bold text-white mb-6">${snippet ? 'Edit' : 'Add'} Snippet</h2>
            <form id="snippetForm" class="space-y-4">
                <input type="hidden" id="snippetId" value="${snippet?.id || ''}">
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Title</label>
                    <input type="text" id="snippetTitle" required value="${escapeHtml(snippet?.title || '')}"
                        class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:ring-2 focus:ring-blue-500">
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Language</label>
                    <select id="snippetLanguage" class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:ring-2 focus:ring-blue-500">
                        ${langOptions}
                    </select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Code</label>
                    <textarea id="snippetCode" rows="10" required
                        class="w-full px-4 py-3 rounded-lg bg-black/40 border border-white/10 text-green-400 focus:ring-2 focus:ring-blue-500 resize-none font-mono text-sm">${escapeHtml(snippet?.code || '')}</textarea>
                </div>
                <div class="flex gap-3">
                    <button type="submit" class="flex-1 px-6 py-3 rounded-lg bg-gradient-to-r from-blue-500 to-cyan-500 text-white font-medium">
                        Save Snippet
                    </button>
                    <button type="button" onclick="closeGenericModal()" class="px-6 py-3 rounded-lg bg-white/5 text-white">Cancel</button>
                </div>
            </form>
        </div>
    `;
    showGenericModal(content);
    document.getElementById('snippetForm').addEventListener('submit', handleSnippetSave);
}

async function handleSnippetSave(e) {
    e.preventDefault();

    const id = document.getElementById('snippetId').value || Date.now().toString();
    const snippet = {
        id,
        title: document.getElementById('snippetTitle').value.trim(),
        language: document.getElementById('snippetLanguage').value,
        code: document.getElementById('snippetCode').value,
        createdAt: snippets.find(s => s.id === id)?.createdAt || new Date().toISOString()
    };

    const existingIndex = snippets.findIndex(s => s.id === id);
    if (existingIndex >= 0) {
        snippets[existingIndex] = snippet;
    } else {
        snippets.push(snippet);
    }

    await saveToStore('snippets', snippet);
    closeGenericModal();
    renderSnippetsTab();
    showToast('Snippet saved!', 'success');
}

async function copySnippet(id) {
    const snippet = snippets.find(s => s.id === id);
    if (snippet) {
        await navigator.clipboard.writeText(snippet.code);
        showToast('Code copied to clipboard!', 'success');
    }
}

async function deleteSnippet(id) {
    if (confirm('Delete this snippet?')) {
        snippets = snippets.filter(s => s.id !== id);
        await deleteFromStore('snippets', id);
        renderSnippetsTab();
        showToast('Snippet deleted!', 'success');
    }
}

window.editSnippet = (id) => openSnippetModal(id);
window.deleteSnippet = deleteSnippet;
window.copySnippet = copySnippet;

// ==================== Colors Module ====================

function renderColorsTab() {
    const grid = document.getElementById('colorsGrid');
    const empty = document.getElementById('colorsEmpty');

    if (colors.length === 0) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    grid.innerHTML = colors.map(color => `
        <div class="glass-card p-3 text-center group">
            <div class="color-swatch mb-2 border border-white/20" style="background-color: ${color.hex};" onclick="copyColor('${color.hex}')"></div>
            <p class="text-white text-sm font-medium truncate">${escapeHtml(color.name || color.hex)}</p>
            <p class="text-gray-500 text-xs">${color.hex}</p>
            <div class="flex justify-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                <button onclick="copyColor('${color.hex}')" class="p-1 rounded bg-red-500/20 text-red-300" title="Copy HEX">
                    <i data-lucide="copy" class="w-3 h-3"></i>
                </button>
                <button onclick="deleteColor('${color.id}')" class="p-1 rounded bg-red-500/20 text-red-300" title="Delete">
                    <i data-lucide="trash-2" class="w-3 h-3"></i>
                </button>
            </div>
        </div>
    `).join('');

    initializeIcons();
}

function openColorModal() {
    const content = `
        <div class="p-6">
            <h2 class="text-2xl font-bold text-white mb-6">Add Color</h2>
            <form id="colorForm" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Color Picker</label>
                    <div class="flex gap-3">
                        <input type="color" id="colorPicker" value="#dc2626" class="w-20 h-20 rounded-lg cursor-pointer border-0">
                        <div class="flex-1">
                            <input type="text" id="colorHex" value="#dc2626" 
                                class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white font-mono mb-2">
                            <input type="text" id="colorName" placeholder="Color name (optional)"
                                class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white">
                        </div>
                    </div>
                </div>
                <div class="flex gap-3">
                    <button type="submit" class="flex-1 px-6 py-3 rounded-lg bg-gradient-to-r from-red-500 to-red-500 text-white font-medium">
                        Save Color
                    </button>
                    <button type="button" onclick="closeGenericModal()" class="px-6 py-3 rounded-lg bg-white/5 text-white">Cancel</button>
                </div>
            </form>
        </div>
    `;
    showGenericModal(content);

    const picker = document.getElementById('colorPicker');
    const hexInput = document.getElementById('colorHex');

    picker.addEventListener('input', () => hexInput.value = picker.value);
    hexInput.addEventListener('input', () => { if (/^#[0-9A-F]{6}$/i.test(hexInput.value)) picker.value = hexInput.value; });

    document.getElementById('colorForm').addEventListener('submit', handleColorSave);
}

async function handleColorSave(e) {
    e.preventDefault();

    const color = {
        id: Date.now().toString(),
        hex: document.getElementById('colorHex').value.toUpperCase(),
        name: document.getElementById('colorName').value.trim(),
        createdAt: new Date().toISOString()
    };

    colors.push(color);
    await saveToStore('colors', color);
    closeGenericModal();
    renderColorsTab();
    showToast('Color saved!', 'success');
}

async function copyColor(hex) {
    await navigator.clipboard.writeText(hex);
    showToast(`Copied: ${hex}`, 'success');
}

async function deleteColor(id) {
    colors = colors.filter(c => c.id !== id);
    await deleteFromStore('colors', id);
    renderColorsTab();
    showToast('Color deleted!', 'success');
}

window.copyColor = copyColor;
window.deleteColor = deleteColor;

// ==================== Todos Module ====================

function renderTodosTab() {
    const list = document.getElementById('todosList');
    const empty = document.getElementById('todosEmpty');

    if (todos.length === 0) {
        list.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');

    // Sort: incomplete first, then by priority
    const sorted = [...todos].sort((a, b) => {
        if (a.completed !== b.completed) return a.completed ? 1 : -1;
        const priorityOrder = { high: 0, medium: 1, low: 2 };
        return (priorityOrder[a.priority] || 2) - (priorityOrder[b.priority] || 2);
    });

    list.innerHTML = sorted.map(todo => `
        <div class="glass-card todo-item p-4 flex items-center gap-3 ${todo.completed ? 'completed' : ''} priority-${todo.priority}">
            <input type="checkbox" ${todo.completed ? 'checked' : ''} onchange="toggleTodo('${todo.id}')" 
                class="w-5 h-5 rounded border-2 border-white/30 bg-transparent cursor-pointer">
            <div class="flex-1 min-w-0">
                <p class="todo-text text-white ${todo.completed ? 'line-through opacity-50' : ''}">${escapeHtml(todo.title)}</p>
                ${todo.dueDate ? `<p class="text-xs text-gray-500">Due: ${new Date(todo.dueDate).toLocaleDateString()}</p>` : ''}
            </div>
            <button onclick="deleteTodo('${todo.id}')" class="p-1.5 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300">
                <i data-lucide="trash-2" class="w-4 h-4"></i>
            </button>
        </div>
    `).join('');

    initializeIcons();
}

function openTodoModal() {
    const content = `
        <div class="p-6">
            <h2 class="text-2xl font-bold text-white mb-6">Add Todo</h2>
            <form id="todoForm" class="space-y-4">
                <div>
                    <label class="block text-sm font-medium text-gray-300 mb-2">Task</label>
                    <input type="text" id="todoTitle" required
                        class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white focus:ring-2 focus:ring-emerald-500">
                </div>
                <div class="grid grid-cols-2 gap-4">
                    <div>
                        <label class="block text-sm font-medium text-gray-300 mb-2">Priority</label>
                        <select id="todoPriority" class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white">
                            <option value="low">Low</option>
                            <option value="medium" selected>Medium</option>
                            <option value="high">High</option>
                        </select>
                    </div>
                    <div>
                        <label class="block text-sm font-medium text-gray-300 mb-2">Due Date</label>
                        <input type="date" id="todoDueDate"
                            class="w-full px-4 py-3 rounded-lg bg-white/5 border border-white/10 text-white">
                    </div>
                </div>
                <div class="flex gap-3">
                    <button type="submit" class="flex-1 px-6 py-3 rounded-lg bg-gradient-to-r from-emerald-500 to-green-500 text-white font-medium">
                        Add Task
                    </button>
                    <button type="button" onclick="closeGenericModal()" class="px-6 py-3 rounded-lg bg-white/5 text-white">Cancel</button>
                </div>
            </form>
        </div>
    `;
    showGenericModal(content);
    document.getElementById('todoForm').addEventListener('submit', handleTodoSave);
}

async function handleTodoSave(e) {
    e.preventDefault();

    const todo = {
        id: Date.now().toString(),
        title: document.getElementById('todoTitle').value.trim(),
        priority: document.getElementById('todoPriority').value,
        dueDate: document.getElementById('todoDueDate').value || null,
        completed: false,
        createdAt: new Date().toISOString()
    };

    todos.push(todo);
    await saveToStore('todos', todo);
    closeGenericModal();
    renderTodosTab();
    showToast('Task added!', 'success');
}

async function toggleTodo(id) {
    const todo = todos.find(t => t.id === id);
    if (todo) {
        todo.completed = !todo.completed;
        await saveToStore('todos', todo);
        renderTodosTab();
    }
}

async function deleteTodo(id) {
    todos = todos.filter(t => t.id !== id);
    await deleteFromStore('todos', id);
    renderTodosTab();
    showToast('Task deleted!', 'success');
}

window.toggleTodo = toggleTodo;
window.deleteTodo = deleteTodo;

// ==================== Files Module ====================

function renderFilesTab() {
    const grid = document.getElementById('filesGrid');
    const empty = document.getElementById('filesEmpty');

    if (files.length === 0) {
        grid.innerHTML = '';
        empty.classList.remove('hidden');
        return;
    }

    empty.classList.add('hidden');
    grid.innerHTML = files.map(file => {
        const isImage = file.type.startsWith('image/');
        const icon = getFileIcon(file.type);

        return `
            <div class="glass-card file-card p-3 text-center group">
                <div class="aspect-square rounded-lg mb-2 overflow-hidden bg-white/5 flex items-center justify-center">
                    ${isImage ? `<img src="${file.data}" alt="${escapeHtml(file.name)}" class="w-full h-full object-cover">` : `<i data-lucide="${icon}" class="w-12 h-12 text-gray-400"></i>`}
                </div>
                <p class="text-white text-sm font-medium truncate">${escapeHtml(file.name)}</p>
                <p class="text-gray-500 text-xs">${formatFileSize(file.size)}</p>
                <div class="flex justify-center gap-1 mt-2 opacity-0 group-hover:opacity-100 transition-opacity">
                    <button onclick="downloadFile('${file.id}')" class="p-1.5 rounded bg-blue-500/20 text-blue-300" title="Download">
                        <i data-lucide="download" class="w-3 h-3"></i>
                    </button>
                    <button onclick="deleteFile('${file.id}')" class="p-1.5 rounded bg-red-500/20 text-red-300" title="Delete">
                        <i data-lucide="trash-2" class="w-3 h-3"></i>
                    </button>
                </div>
            </div>
        `;
    }).join('');

    initializeIcons();
}

function getFileIcon(type) {
    if (type.startsWith('image/')) return 'image';
    if (type.includes('pdf')) return 'file-text';
    if (type.includes('word') || type.includes('document')) return 'file-text';
    if (type.includes('excel') || type.includes('spreadsheet')) return 'table';
    if (type.includes('zip') || type.includes('rar')) return 'archive';
    return 'file';
}

function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

function openFileModal() {
    const content = `
        <div class="p-6">
            <h2 class="text-2xl font-bold text-white mb-6">Upload File</h2>
            <form id="fileForm" class="space-y-4">
                <div class="border-2 border-dashed border-white/20 rounded-lg p-8 text-center cursor-pointer hover:border-red-500/50 transition-all" id="fileDropZone">
                    <input type="file" id="fileInput" class="hidden" accept="image/*,.pdf,.doc,.docx,.xls,.xlsx,.txt,.json">
                    <i data-lucide="upload" class="w-12 h-12 mx-auto text-gray-400 mb-4"></i>
                    <p class="text-gray-300">Click or drag file here</p>
                    <p class="text-gray-500 text-sm mt-1">Max 10MB • Images, PDFs, Documents</p>
                </div>
                <div id="filePreview" class="hidden p-4 rounded-lg bg-white/5 border border-white/10">
                    <p id="filePreviewName" class="text-white font-medium"></p>
                    <p id="filePreviewSize" class="text-gray-400 text-sm"></p>
                </div>
                <div class="flex gap-3">
                    <button type="submit" id="uploadFileBtn" disabled class="flex-1 px-6 py-3 rounded-lg bg-gradient-to-r from-red-600 to-red-500 text-white font-medium disabled:opacity-50">
                        Upload File
                    </button>
                    <button type="button" onclick="closeGenericModal()" class="px-6 py-3 rounded-lg bg-white/5 text-white">Cancel</button>
                </div>
            </form>
        </div>
    `;
    showGenericModal(content);
    initializeIcons();

    const dropZone = document.getElementById('fileDropZone');
    const fileInput = document.getElementById('fileInput');

    dropZone.addEventListener('click', () => fileInput.click());
    dropZone.addEventListener('dragover', e => { e.preventDefault(); dropZone.classList.add('border-red-500'); });
    dropZone.addEventListener('dragleave', () => dropZone.classList.remove('border-red-500'));
    dropZone.addEventListener('drop', e => {
        e.preventDefault();
        dropZone.classList.remove('border-red-500');
        if (e.dataTransfer.files.length) handleFileSelect(e.dataTransfer.files[0]);
    });
    fileInput.addEventListener('change', e => { if (e.target.files.length) handleFileSelect(e.target.files[0]); });

    document.getElementById('fileForm').addEventListener('submit', handleFileSave);
}

let pendingFile = null;

function handleFileSelect(file) {
    if (file.size > 10 * 1024 * 1024) {
        showToast('File too large! Max 10MB', 'error');
        return;
    }

    pendingFile = file;
    document.getElementById('filePreview').classList.remove('hidden');
    document.getElementById('filePreviewName').textContent = file.name;
    document.getElementById('filePreviewSize').textContent = formatFileSize(file.size);
    document.getElementById('uploadFileBtn').disabled = false;
}

async function handleFileSave(e) {
    e.preventDefault();
    if (!pendingFile) return;

    const reader = new FileReader();
    reader.onload = async (e) => {
        const fileData = {
            id: Date.now().toString(),
            name: pendingFile.name,
            type: pendingFile.type,
            size: pendingFile.size,
            data: e.target.result,
            createdAt: new Date().toISOString()
        };

        files.push(fileData);
        await saveToStore('files', fileData);
        pendingFile = null;
        closeGenericModal();
        renderFilesTab();
        showToast('File uploaded!', 'success');
    };
    reader.readAsDataURL(pendingFile);
}

function downloadFile(id) {
    const file = files.find(f => f.id === id);
    if (file) {
        const link = document.createElement('a');
        link.href = file.data;
        link.download = file.name;
        link.click();
    }
}

async function deleteFile(id) {
    if (confirm('Delete this file?')) {
        files = files.filter(f => f.id !== id);
        await deleteFromStore('files', id);
        renderFilesTab();
        showToast('File deleted!', 'success');
    }
}

window.downloadFile = downloadFile;
window.deleteFile = deleteFile;

// ==================== Prompts Tab Rendering ====================

function renderPromptsTab() {
    const container = document.getElementById('promptsTabList');
    if (!container) return;

    const promptsData = window.prompts || [];

    if (promptsData.length === 0) {
        container.innerHTML = '<p class="text-gray-400 col-span-full text-center py-8">No prompts yet. Click "Add Prompt" to create one.</p>';
        return;
    }

    container.innerHTML = promptsData.map(prompt => `
        <div class="glass-card p-4">
            <h4 class="text-white font-semibold mb-2">${escapeHtml(prompt.title)}</h4>
            <p class="text-gray-400 text-sm line-clamp-3 mb-3">${escapeHtml(prompt.content)}</p>
            <div class="flex items-center justify-between">
                <span class="text-xs px-2 py-1 rounded-full bg-cyan-500/20 text-cyan-300">${escapeHtml(prompt.category)}</span>
                <div class="flex gap-2">
                    <button onclick="copyPrompt('${prompt.id}')" class="p-1.5 rounded bg-blue-500/20 text-blue-300"><i data-lucide="copy" class="w-4 h-4"></i></button>
                    <button onclick="window.openPromptModal && window.openPromptModal('${prompt.id}')" class="p-1.5 rounded bg-red-500/20 text-red-300"><i data-lucide="edit" class="w-4 h-4"></i></button>
                    <button onclick="window.deletePrompt && window.deletePrompt('${prompt.id}')" class="p-1.5 rounded bg-red-500/20 text-red-300"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
                </div>
            </div>
        </div>
    `).join('');

    if (window.initializeIcons) window.initializeIcons();
}

// ==================== Generic Modal ====================

function showGenericModal(content) {
    let modal = document.getElementById('genericModal');
    if (!modal) {
        modal = document.createElement('div');
        modal.id = 'genericModal';
        modal.className = 'fixed inset-0 z-50 flex items-center justify-center p-4';
        modal.innerHTML = `
            <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onclick="closeGenericModal()"></div>
            <div class="glass-card relative z-10 w-full max-w-lg max-h-[90vh] overflow-y-auto" id="genericModalContent"></div>
        `;
        document.body.appendChild(modal);
    }

    document.getElementById('genericModalContent').innerHTML = content;
    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    initializeIcons();
}

function closeGenericModal() {
    const modal = document.getElementById('genericModal');
    if (modal) {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
    }
}

window.closeGenericModal = closeGenericModal;

// ==================== Initialize Knowledge Hub ====================

async function initKnowledgeHub() {
    setupTabNavigation();

    // Setup add buttons for each module
    document.getElementById('addNoteBtn')?.addEventListener('click', () => openNoteModal());
    setupTranslateModal();
    document.getElementById('addSnippetBtn')?.addEventListener('click', () => openSnippetModal());
    document.getElementById('addColorBtn')?.addEventListener('click', openColorModal);
    document.getElementById('addTodoBtn')?.addEventListener('click', openTodoModal);
    document.getElementById('addFileBtn')?.addEventListener('click', openFileModal);
    document.getElementById('addPromptBtnTab')?.addEventListener('click', () => openPromptModal(null));

    // Try to upgrade DB and load data
    try {
        await initNewStores();
        await loadNewModuleData();
        // Run any pending schema migrations (safe: creates a backup first).
        if (typeof window.runDataMigrations === 'function') {
            await window.runDataMigrations();
        }
    } catch (e) {
        console.log('Will initialize new stores on next page load');
    }
}

// Run after main init
setTimeout(initKnowledgeHub, 100);
