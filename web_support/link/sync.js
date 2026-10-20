// ==================== SUPABASE SYNC MODULE ====================

let syncRoomCode = null;
let syncSubscription = null;
let syncEnabled = false;
let supabaseInstance = null;

function syncArray(value) {
    return Array.isArray(value) ? value : [];
}

function normalizeSyncUrl(url) {
    return String(url || '').trim().replace(/\/+$/, '').toLowerCase();
}

function collectSyncData() {
    return {
        links: syncArray(window.links),
        prompts: syncArray(window.prompts),
        notes: syncArray(window.notes),
        snippets: syncArray(window.snippets),
        colors: syncArray(window.colors),
        todos: syncArray(window.todos),
        files: syncArray(window.files),
        folders: syncArray(window.folders),
        timeline: syncArray(window.timelineEvents),
        tools: syncArray(window.tools),
        updatedAt: new Date().toISOString()
    };
}

async function persistMergedRecords(storeName, items, saveFnName, targetArray) {
    if (!Array.isArray(items) || items.length === 0) return 0;
    const target = Array.isArray(targetArray) ? targetArray : [];
    const existingIds = new Set(target.map(item => item && item.id).filter(Boolean));
    let added = 0;

    for (const item of items) {
        if (!item || typeof item !== 'object' || !item.id || existingIds.has(item.id)) continue;
        existingIds.add(item.id);
        target.push(item);
        if (saveFnName && typeof window[saveFnName] === 'function') {
            await window[saveFnName](item);
        } else if (typeof window.saveToStore === 'function') {
            await window.saveToStore(storeName, item);
        }
        added++;
    }
    return added;
}

// Initialize Supabase
function initSupabase() {
    // Check if supabaseClient is ready (created in index.html ES module)
    if (window.supabaseReady && window.supabaseClient) {
        supabaseInstance = window.supabaseClient;
        console.log('Supabase connected');
        return true;
    }

    console.error('Supabase SDK not ready yet. Waiting...');
    return false;
}

function generateRoomCode() {
    const chars = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'; // Avoid confusing chars
    let code = '';
    for (let i = 0; i < 6; i++) {
        code += chars.charAt(Math.floor(Math.random() * chars.length));
    }
    return code;
}

async function createSyncRoom() {
    // Wait for SDK to load (ES module is async)
    let retries = 0;
    while (!window.supabaseReady && retries < 10) {
        await new Promise(r => setTimeout(r, 300));
        retries++;
    }

    if (!initSupabase()) {
        showToast('Supabase SDK not loaded yet. Try again in 2 seconds...', 'error');
        return;
    }

    const code = generateRoomCode();

    // Prepare all data for sync
    const syncData = collectSyncData();

    try {
        const { data, error } = await supabaseInstance
            .from('sync_rooms')
            .insert({
                room_code: code,
                data: syncData
            })
            .select()
            .single();

        if (error) throw error;

        syncRoomCode = code;
        localStorage.setItem('syncRoomCode', code);

        document.getElementById('generatedCode').textContent = code;
        document.getElementById('roomCodeDisplay').classList.remove('hidden');

        updateSyncStatus('connected', `Connected to room: ${code}`);
        subscribeToRoom(code);

        showToast(`Room created! Code: ${code}`, 'success');

    } catch (error) {
        console.error('Failed to create room:', error);
        showToast('Failed to create room: ' + error.message, 'error');
    }
}

async function joinSyncRoom(code) {
    if (!code || code.length !== 6) {
        showToast('Please enter a valid 6-character room code', 'error');
        return;
    }

    // Wait for SDK to load
    let retries = 0;
    while (!window.supabaseReady && retries < 10) {
        await new Promise(r => setTimeout(r, 300));
        retries++;
    }

    if (!initSupabase()) {
        showToast('Supabase SDK not loaded yet. Try again...', 'error');
        return;
    }

    code = code.toUpperCase();

    try {
        const { data, error } = await supabaseInstance
            .from('sync_rooms')
            .select('*')
            .eq('room_code', code)
            .single();

        if (error) throw error;
        if (!data) throw new Error('Room not found');

        syncRoomCode = code;
        localStorage.setItem('syncRoomCode', code);

        // Merge remote data with local
        await mergeRemoteData(data.data);

        updateSyncStatus('connected', `Connected to room: ${code}`);
        subscribeToRoom(code);

        showToast('Connected to sync room!', 'success');

    } catch (error) {
        console.error('Failed to join room:', error);
        showToast('Failed to join room: ' + error.message, 'error');
    }
}

async function mergeRemoteData(remoteData) {
    if (!remoteData) return;

    if (!window.links) window.links = [];
    if (!window.prompts) window.prompts = [];
    if (!window.notes) window.notes = [];
    if (!window.snippets) window.snippets = [];
    if (!window.colors) window.colors = [];
    if (!window.todos) window.todos = [];
    if (!window.files) window.files = [];
    if (!window.folders) window.folders = [];
    if (!window.timelineEvents) window.timelineEvents = [];
    if (!window.tools) window.tools = [];

    if (remoteData.links && Array.isArray(remoteData.links)) {
        const localIds = new Set(window.links.map(l => l.id).filter(Boolean));
        const localUrls = new Set(window.links.map(l => normalizeSyncUrl(l.url)).filter(Boolean));
        for (const remoteLink of remoteData.links) {
            if (!remoteLink?.id) continue;
            const normalizedUrl = normalizeSyncUrl(remoteLink.url);
            if (localIds.has(remoteLink.id) || (normalizedUrl && localUrls.has(normalizedUrl))) continue;
            localIds.add(remoteLink.id);
            if (normalizedUrl) localUrls.add(normalizedUrl);
            window.links.push(remoteLink);
            if (typeof window.saveLinkToDB === 'function') await window.saveLinkToDB(remoteLink);
        }
    }

    await persistMergedRecords('prompts', remoteData.prompts, 'savePromptToDB', window.prompts);
    await persistMergedRecords('notes', remoteData.notes, 'saveNoteToDB', window.notes);
    await persistMergedRecords('snippets', remoteData.snippets, null, window.snippets);
    await persistMergedRecords('colors', remoteData.colors, null, window.colors);
    await persistMergedRecords('todos', remoteData.todos, null, window.todos);
    await persistMergedRecords('files', remoteData.files, null, window.files);
    await persistMergedRecords('folders', remoteData.folders, 'saveFolderToDB', window.folders);
    await persistMergedRecords('timeline', remoteData.timeline, 'saveTimelineEventToDB', window.timelineEvents);
    await persistMergedRecords('tools', remoteData.tools, 'saveToolToDB', window.tools);

    if (typeof window.updateAllTags === 'function') window.updateAllTags();
    if (typeof window.renderLinks === 'function') window.renderLinks();
    if (typeof window.renderPrompts === 'function') window.renderPrompts();
    if (typeof window.renderSidebar === 'function') window.renderSidebar();
    if (typeof window.renderTimelineTab === 'function' && !document.getElementById('timelineTab')?.classList.contains('hidden')) {
        window.renderTimelineTab();
    }
    if (typeof window.updateToolsView === 'function') window.updateToolsView();

    showToast('Data synced from cloud!', 'success');
}

function subscribeToRoom(code) {
    if (!supabaseInstance) return;

    // Unsubscribe from previous
    if (syncSubscription) {
        syncSubscription.unsubscribe();
    }

    syncSubscription = supabaseInstance
        .channel(`room:${code}`)
        .on('postgres_changes',
            { event: 'UPDATE', schema: 'public', table: 'sync_rooms', filter: `room_code=eq.${code}` },
            (payload) => {
                console.log('Sync update received:', payload);
                mergeRemoteData(payload.new.data);
            }
        )
        .subscribe((status) => {
            if (status === 'SUBSCRIBED') {
                syncEnabled = true;
                console.log('Subscription status: SUBSCRIBED');
            } else if (status === 'CHANNEL_ERROR' || status === 'TIMED_OUT') {
                if (!syncSubscription._realtimeErrorLogged) {
                    syncSubscription._realtimeErrorLogged = true;
                    console.warn('Realtime subscription failed (network or Realtime disabled). Sync will work without live updates.');
                }
            }
        });
}

async function pushToCloud() {
    if (!supabaseInstance || !syncRoomCode) return;

    const syncData = collectSyncData();

    try {
        const { error } = await supabaseInstance
            .from('sync_rooms')
            .update({ data: syncData, updated_at: new Date().toISOString() })
            .eq('room_code', syncRoomCode);

        if (error) throw error;
        console.log('Data pushed to cloud');

    } catch (error) {
        console.error('Push to cloud failed:', error);
    }
}

function updateSyncStatus(status, text) {
    const icon = document.getElementById('syncStatusIcon');
    const textEl = document.getElementById('syncStatusText');

    if (!icon || !textEl) return;

    if (status === 'connected') {
        icon.className = 'w-3 h-3 rounded-full bg-green-500 animate-pulse';
        document.getElementById('disconnectSyncBtn')?.classList.remove('hidden');
    } else {
        icon.className = 'w-3 h-3 rounded-full bg-gray-500';
        document.getElementById('disconnectSyncBtn')?.classList.add('hidden');
    }

    textEl.textContent = text;
}

function disconnectSync() {
    if (syncSubscription) {
        syncSubscription.unsubscribe();
        syncSubscription = null;
    }
    syncRoomCode = null;
    syncEnabled = false;
    localStorage.removeItem('syncRoomCode');

    updateSyncStatus('disconnected', 'Not connected');
    document.getElementById('roomCodeDisplay')?.classList.add('hidden');

    showToast('Disconnected from sync', 'success');
}

// Sync Modal UI
function openSyncModal() {
    document.getElementById('syncModal').classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    if (typeof window.initializeIcons === 'function') window.initializeIcons();

    // Check for existing connection
    const savedCode = localStorage.getItem('syncRoomCode');
    if (savedCode) {
        syncRoomCode = savedCode;
        updateSyncStatus('connected', `Connected to room: ${savedCode}`);
        document.getElementById('generatedCode').textContent = savedCode;
        document.getElementById('roomCodeDisplay').classList.remove('hidden');

        // Re-subscribe
        if (initSupabase()) {
            subscribeToRoom(savedCode);
        }
    }
}

function closeSyncModal() {
    document.getElementById('syncModal').classList.add('hidden');
    document.body.style.overflow = '';
}

// Setup sync event listeners
document.addEventListener('DOMContentLoaded', () => {
    // Sync button
    const syncBtn = document.getElementById('syncBtn');
    if (syncBtn) syncBtn.addEventListener('click', openSyncModal);

    // Modal controls
    document.getElementById('closeSyncModal')?.addEventListener('click', closeSyncModal);
    document.getElementById('syncModalOverlay')?.addEventListener('click', closeSyncModal);

    // Create room
    document.getElementById('createRoomBtn')?.addEventListener('click', createSyncRoom);

    // Join room
    document.getElementById('joinRoomBtn')?.addEventListener('click', () => {
        const code = document.getElementById('joinRoomCode').value.trim();
        joinSyncRoom(code);
    });

    // Copy code
    document.getElementById('copyRoomCode')?.addEventListener('click', () => {
        const code = document.getElementById('generatedCode').textContent;
        navigator.clipboard.writeText(code);
        showToast('Room code copied!', 'success');
    });

    // Disconnect
    document.getElementById('disconnectSyncBtn')?.addEventListener('click', disconnectSync);

    // Restore saved room code for UI only; do not auto-subscribe (avoids WebSocket on load and Realtime errors when disabled)
    const savedCode = localStorage.getItem('syncRoomCode');
    if (savedCode) syncRoomCode = savedCode;
});

// Hook into save functions to auto-push (delayed to ensure modules.js loaded)
setTimeout(() => {
    const hookTargets = [
        'saveLinks',
        'saveLinkToDB',
        'savePromptToDB',
        'saveNoteToDB',
        'saveFolderToDB',
        'saveToolToDB',
        'saveTimelineEventToDB',
        'saveToStore',
        'deleteFromStore',
        'deleteLinkFromDB',
        'deletePromptFromDB'
    ];

    hookTargets.forEach(fnName => {
        if (typeof window[fnName] !== 'function' || window[fnName].__syncWrapped) return;
        const originalFn = window[fnName];
        const wrapped = async function () {
            const result = await originalFn.apply(this, arguments);
            if (syncEnabled) pushToCloud();
            return result;
        };
        wrapped.__syncWrapped = true;
        window[fnName] = wrapped;
    });
}, 2000); // 2 seconds delay to ensure main scripts are ready

// Expose sync functions
window.openSyncModal = openSyncModal;
window.closeSyncModal = closeSyncModal;
window.pushToCloud = pushToCloud; // Expose for manual sync if needed
