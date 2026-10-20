// ==================== Folder System ====================

let folders = window.folders = [];
let currentFolder = 'all'; // 'all', 'favorites', 'unsorted', or folder UUID

// Initialize Folders
async function initFolders() {
    console.log('📂 Initializing Folder System...');
    await loadFolders();
    renderSidebar();
    setupDragAndDrop();

    // Attach Add Folder Button Listener
    const addBtn = document.getElementById('addFolderBtn');
    if (addBtn) {
        // Remove old listener if any (by cloning) - though init runs once usually
        const newBtn = addBtn.cloneNode(true);
        addBtn.parentNode.replaceChild(newBtn, addBtn);

        newBtn.addEventListener('click', openCreateFolderModal);
    }

    // Setup Folder Modal Listeners
    setupFolderModalListeners();
}

// Open Create Folder Modal
function openCreateFolderModal() {
    const modal = document.getElementById('createFolderModal');
    const content = document.getElementById('createFolderModalContent');
    const input = document.getElementById('newFolderName');

    if (!modal) return;

    modal.classList.remove('hidden');
    document.body.style.overflow = 'hidden';

    // Animate in
    setTimeout(() => {
        content.classList.remove('scale-95', 'opacity-0');
        content.classList.add('scale-100', 'opacity-100');
    }, 10);

    // Focus input
    setTimeout(() => input?.focus(), 100);
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

// Close Create Folder Modal
function closeCreateFolderModal() {
    const modal = document.getElementById('createFolderModal');
    const content = document.getElementById('createFolderModalContent');
    const input = document.getElementById('newFolderName');

    if (!modal) return;

    content.classList.add('scale-95', 'opacity-0');
    content.classList.remove('scale-100', 'opacity-100');

    setTimeout(() => {
        modal.classList.add('hidden');
        document.body.style.overflow = '';
        if (input) input.value = '';
    }, 200);
}

// Setup Modal Listeners
function setupFolderModalListeners() {
    document.getElementById('closeCreateFolderModal')?.addEventListener('click', closeCreateFolderModal);
    document.getElementById('createFolderOverlay')?.addEventListener('click', closeCreateFolderModal);
    document.getElementById('cancelCreateFolderBtn')?.addEventListener('click', closeCreateFolderModal);

    document.getElementById('confirmCreateFolderBtn')?.addEventListener('click', async () => {
        const input = document.getElementById('newFolderName');
        const name = input?.value?.trim();
        if (name) {
            await createFolder(name);
            closeCreateFolderModal();
        } else {
            input?.focus();
        }
    });

    // Enter key to submit
    document.getElementById('newFolderName')?.addEventListener('keydown', async (e) => {
        if (e.key === 'Enter') {
            const name = e.target.value?.trim();
            if (name) {
                await createFolder(name);
                closeCreateFolderModal();
            }
        }
    });
}

// Load Folders from DB
async function loadFolders() {
    try {
        if (!db) {
            console.warn('DB not initialized yet, retrying in 100ms...');
            setTimeout(loadFolders, 100);
            return;
        }

        const transaction = db.transaction(['folders'], 'readonly');
        const store = transaction.objectStore('folders');
        const request = store.getAll();

        return new Promise((resolve, reject) => {
            request.onsuccess = () => {
                folders = request.result || [];
                // Sort by name for now, or createdAt
                folders.sort((a, b) => a.name.localeCompare(b.name));
                window.folders = folders;
                resolve(folders);
            };
            request.onerror = () => reject(request.error);
        });
    } catch (e) {
        console.error('Error loading folders:', e);
        folders = [];
    }
}

// Create Folder (Nested support)
async function createFolder(name, parentId = null) {
    if (!name || !name.trim()) return;

    const folder = {
        id: crypto.randomUUID(),
        name: name.trim(),
        color: neonColors[Math.floor(Math.random() * neonColors.length)],
        createdAt: new Date().toISOString(),
        parentId: parentId || null
    };

    try {
        const transaction = db.transaction(['folders'], 'readwrite');
        const store = transaction.objectStore('folders');
        await new Promise((resolve, reject) => {
            const request = store.add(folder);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });

        folders.push(folder);
        renderSidebar();
        showToast(`Folder "${folder.name}" created!`);
        return folder;
    } catch (e) {
        console.error('Error creating folder:', e);
        showToast('Failed to create folder', true);
    }
}

// Delete Folder
async function deleteFolder(folderId) {
    if (!confirm('Delete this folder? Links inside will be moved to Unsorted.')) return;

    try {
        // 1. Delete Folder
        const transaction = db.transaction(['folders'], 'readwrite');
        const store = transaction.objectStore('folders');
        await new Promise((resolve, reject) => {
            const request = store.delete(folderId);
            request.onsuccess = () => resolve();
            request.onerror = () => reject(request.error);
        });

        // 2. Remove folderId from links (Move to Unsorted)
        // This effectively creates a "move to unsorted" effect because un-categorized links go there
        const linksToUpdate = window.links.filter(l => l.folderId === folderId);

        for (const link of linksToUpdate) {
            link.folderId = null;
            // Update in DB (reusing saveLink from script.js logic would be ideal, but direct update for batch efficiency)
            await updateLinkFolder(link.id, null);
        }

        folders = folders.filter(f => f.id !== folderId);
        window.folders = folders;

        if (currentFolder === folderId) {
            selectFolder('all');
        } else {
            renderSidebar();
        }

        showToast('Folder deleted');
    } catch (e) {
        console.error('Error deleting folder:', e);
        showToast('Failed to delete folder', true);
    }
}

// Update Link Folder
async function updateLinkFolder(linkId, folderId) {
    const link = window.links.find(l => l.id === linkId);
    if (!link) return;

    link.folderId = folderId;

    // Save to DB
    const transaction = db.transaction(['links'], 'readwrite');
    const store = transaction.objectStore('links');
    store.put(link);

    // Refresh view if needed
    // re-render links if we are viewing the source or destination folder
    if (currentFolder === 'all' || currentFolder === 'unsorted' || currentFolder === folderId || (link.folderId === currentFolder)) {
        renderLinks();
    }
}

// Update Folder Parent (Nesting)
async function updateFolderParent(folderId, newParentId) {
    // Prevent circular dependency
    if (folderId === newParentId) return;

    // Check if newParentId is a child of folderId (would cause cycle)
    let check = folders.find(f => f.id === newParentId);
    while (check && check.parentId) {
        if (check.parentId === folderId) {
            showToast('Cannot move a folder into its own child', true);
            return;
        }
        check = folders.find(f => f.id === check.parentId);
    }

    const folder = folders.find(f => f.id === folderId);
    if (!folder) return;

    folder.parentId = newParentId;

    const transaction = db.transaction(['folders'], 'readwrite');
    const store = transaction.objectStore('folders');
    store.put(folder);

    renderSidebar();
}

// Build Tree Structure
function buildFolderTree(flatFolders) {
    const root = [];
    const map = {};

    flatFolders.forEach(f => {
        map[f.id] = { ...f, children: [] };
    });

    flatFolders.forEach(f => {
        if (f.parentId && map[f.parentId]) {
            map[f.parentId].children.push(map[f.id]);
        } else {
            root.push(map[f.id]);
        }
    });

    return root;
}

// Render Sidebar (Recursive)
function renderSidebar() {
    const container = document.getElementById('folderList');
    if (!container) return;

    container.innerHTML = '';

    // Standard Items
    const now = Date.now();
    const weekMs = 1000 * 60 * 60 * 24 * 7;
    const standardItems = [
        { id: 'all', name: 'All Links', icon: 'layers', count: window.links.length },
        { id: 'favorites', name: 'Favorites', icon: 'star', count: window.links.filter(l => l.favorite).length },
        { id: 'pinned', name: 'Pinned', icon: 'pin', count: window.links.filter(l => l.pinned).length },
        { id: 'unread', name: 'Unread', icon: 'book-marked', count: window.links.filter(l => !l.isRead).length },
        { id: 'unsorted', name: 'Unsorted', icon: 'inbox', count: window.links.filter(l => !l.folderId).length },
        {
            id: 'recent', name: 'Recent', icon: 'clock', count: window.links.filter(l => {
                const date = l.lastVisited || l.createdAt;
                return (now - new Date(date).getTime()) < weekMs; // Last 7 days
            }).length
        }
    ];

    standardItems.forEach(item => {
        const el = createFolderElement(item, true);
        container.appendChild(el);
    });

    // Divider
    const divider = document.createElement('div');
    divider.className = 'h-px bg-white/10 my-2 mx-4';
    container.appendChild(divider);

    // ==================== Smart Folders (Saved Searches) ====================
    renderSmartFolders(container);

    // ==================== Intelligence Panel ====================
    renderIntelligencePanel(container);

    // Custom Folders Tree
    const tree = buildFolderTree(folders);
    renderFolderTree(tree, container, 0);
}

// Render Intelligence Panel (Smart Widgets)
function renderIntelligencePanel(container) {
    const panel = document.createElement('div');
    panel.className = 'px-3 py-2 space-y-2';
    panel.id = 'intelligencePanel';

    // Hot This Week (Top 3 most visited) — single pass, avoids a full O(n log n) sort
    const hotLinks = [];
    for (const l of window.links || []) {
        if ((l.visitCount || 0) <= 0) continue;
        hotLinks.push(l);
        if (hotLinks.length > 3) {
            hotLinks.sort((a, b) => (b.visitCount || 0) - (a.visitCount || 0));
            hotLinks.length = 3;
        }
    }

    if (hotLinks.length > 0) {
        const hotWidget = document.createElement('div');
        hotWidget.className = 'mb-3';
        hotWidget.innerHTML = `
            <h4 class="text-xs font-bold text-gray-500 uppercase mb-1 flex items-center gap-1">
                <i data-lucide="flame" class="w-3 h-3 text-red-400"></i> Hot
            </h4>
            <div class="space-y-1">
                ${hotLinks.map(l => `
                    <div class="flex items-center gap-2 px-2 py-1 rounded hover:bg-white/10 cursor-pointer text-xs text-gray-300 truncate" 
                         onclick="window.open('${l.url}', '_blank')">
                        <span class="truncate">${l.title || 'Untitled'}</span>
                        <span class="text-red-400 text-[10px] ml-auto shrink-0">${l.visitCount}</span>
                    </div>
                `).join('')}
            </div>
        `;
        panel.appendChild(hotWidget);
    }

    // Stale Alert (Links not visited in 30+ days)
    const thirtyDaysAgo = Date.now() - (1000 * 60 * 60 * 24 * 30);
    const staleLinks = (window.links || [])
        .filter(l => {
            const date = l.lastVisited ? new Date(l.lastVisited).getTime() : new Date(l.createdAt).getTime();
            return date < thirtyDaysAgo;
        })
        .slice(0, 3);

    if (staleLinks.length > 0) {
        const staleWidget = document.createElement('div');
        staleWidget.className = 'mb-3';
        staleWidget.innerHTML = `
            <h4 class="text-xs font-bold text-gray-500 uppercase mb-1 flex items-center gap-1">
                <i data-lucide="archive" class="w-3 h-3 text-gray-400"></i> Old
            </h4>
            <div class="space-y-1">
                ${staleLinks.map(l => `
                    <div class="flex items-center gap-2 px-2 py-1 rounded hover:bg-white/10 cursor-pointer text-xs text-gray-400 truncate"
                         onclick="openModal('${l.id}')">
                        <span class="truncate">${l.title || 'Untitled'}</span>
                    </div>
                `).join('')}
            </div>
        `;
        panel.appendChild(staleWidget);
    }

    // Pending Decisions
    const pendingDecisions = (window.timelineEvents || [])
        .filter(e => e.type === 'decision' && e.context?.snapshot?.status === 'pending')
        .slice(0, 3);

    if (pendingDecisions.length > 0) {
        const decisionWidget = document.createElement('div');
        decisionWidget.className = 'mb-3';
        decisionWidget.innerHTML = `
            <h4 class="text-xs font-bold text-gray-500 uppercase mb-1 flex items-center gap-1">
                <i data-lucide="zap" class="w-3 h-3 text-red-400"></i> Pending
            </h4>
            <div class="space-y-1">
                ${pendingDecisions.map(d => `
                    <div class="flex items-center gap-2 px-2 py-1 rounded hover:bg-red-500/10 cursor-pointer text-xs text-red-300/80 truncate"
                         onclick="if(window.showTimelineEventDetail) window.showTimelineEventDetail('${d.id}')">
                        <span class="truncate">${d.title || 'Decision'}</span>
                    </div>
                `).join('')}
            </div>
        `;
        panel.appendChild(decisionWidget);
    }

    // Only add panel if it has content
    if (panel.children.length > 0) {
        const panelDivider = document.createElement('div');
        panelDivider.className = 'h-px bg-white/10 my-2 mx-4';
        container.appendChild(panel);
        container.appendChild(panelDivider);
    }

    // Refresh icons
    if (typeof lucide !== 'undefined') lucide.createIcons();
}

// Recursive Helper
function renderFolderTree(nodes, container, depth) {
    nodes.forEach(node => {
        // Count links in folder + subfolders logic if needed? 
        // For now just immediate links count for simplicity
        const count = window.links.filter(l => l.folderId === node.id).length;
        const el = createFolderElement({ ...node, count }, false, depth);
        container.appendChild(el);

        if (node.children && node.children.length > 0) {
            const childContainer = document.createElement('div');
            // Basic indentation visual or toggle? 
            // For now, simple indentation container, always expanded for simplicity
            childContainer.className = 'ml-3 border-l border-white/10';
            renderFolderTree(node.children, childContainer, depth + 1);
            container.appendChild(childContainer);
        }
    });
}

// Helper: Create Folder Element
function createFolderElement(item, isStandard, depth = 0) {
    const div = document.createElement('div');
    div.className = `folder-item group flex items-center justify-between px-4 py-2 mx-2 rounded-lg cursor-pointer transition-all ${currentFolder === item.id ? 'active bg-white/15 text-white' : 'text-gray-400 hover:bg-white/10 hover:text-gray-200'}`;
    div.dataset.id = item.id;
    div.dataset.type = isStandard ? 'standard' : 'custom';

    // Indentation if depth > 0 (handled by container margin, but extra padding looks nice)
    // Removed literal padding in favor of nested container margin above

    // Allow dropping on folders
    if (item.id !== 'all' && item.id !== 'favorites' && item.id !== 'recent') {
        div.classList.add('droppable');
        if (!isStandard) div.draggable = true; // Allow dragging folders
    }

    const left = document.createElement('div');
    left.className = 'flex items-center gap-3 truncate';

    const icon = document.createElement('i');
    icon.dataset.lucide = item.icon || 'folder';
    if (item.color) icon.style.color = item.color;
    icon.className = 'w-4 h-4';

    const span = document.createElement('span');
    span.className = 'truncate text-sm font-medium';
    span.textContent = item.name;

    left.appendChild(icon);
    left.appendChild(span);

    const right = document.createElement('div');
    right.className = 'flex items-center gap-2';

    if (item.count > 0 || isStandard) {
        const countBadge = document.createElement('span');
        countBadge.className = 'text-xs opacity-50 bg-black/20 px-2 py-0.5 rounded-full';
        countBadge.textContent = item.id === 'recent' ? '' : item.count;
        if (item.id === 'recent') countBadge.style.display = 'none';
        right.appendChild(countBadge);
    }

    // Delete button for custom folders
    if (!isStandard) {
        const delBtn = document.createElement('button');
        delBtn.className = 'opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity';
        delBtn.innerHTML = '<i data-lucide="trash-2" class="w-3 h-3"></i>';
        delBtn.onclick = (e) => {
            e.stopPropagation();
            deleteFolder(item.id);
        };
        right.appendChild(delBtn);
    }

    div.appendChild(left);
    div.appendChild(right);

    div.addEventListener('click', () => selectFolder(item.id));

    // Drag Events for Folders
    if (!isStandard) {
        div.addEventListener('dragstart', (e) => {
            e.stopPropagation(); // Avoid triggering parent
            e.dataTransfer.setData('text/plain', item.id);
            e.dataTransfer.setData('type', 'folder');
            e.dataTransfer.effectAllowed = 'move';
            div.classList.add('opacity-50');
            window.draggedFolderId = item.id;
        });

        div.addEventListener('dragend', () => {
            div.classList.remove('opacity-50');
            window.draggedFolderId = null;
        });
    }

    return div;
}

// Select Folder
function selectFolder(folderId) {
    currentFolder = folderId;
    renderSidebar(); // Update active state
    renderLinks();   // Filter links

    // Update header/breadcrumb if needed
    const folderName = folderId === 'all' ? 'All Links' :
        folderId === 'favorites' ? 'Favorites' :
            folderId === 'pinned' ? 'Pinned' :
                folderId === 'unread' ? 'Unread' :
                    folderId === 'unsorted' ? 'Unsorted' :
                        folderId === 'recent' ? 'Recent' :
                            folders.find(f => f.id === folderId)?.name || 'Folder';

    const st = document.getElementById('sectionTitle');
    if (st) st.textContent = folderName;
}

// Filter Links by Folder (Called by renderLinks in script.js)
function filterLinksByFolder(linksToFilter) {
    if (currentFolder === 'all') return linksToFilter;
    if (currentFolder === 'favorites') return linksToFilter.filter(l => l.favorite);
    if (currentFolder === 'pinned') return linksToFilter.filter(l => l.pinned);
    if (currentFolder === 'unread') return linksToFilter.filter(l => !l.isRead);
    if (currentFolder === 'unsorted') return linksToFilter.filter(l => !l.folderId);
    if (currentFolder === 'recent') {
        return linksToFilter
            .filter(l => {
                const date = l.lastVisited || l.createdAt;
                return (Date.now() - new Date(date).getTime()) < 1000 * 60 * 60 * 24 * 7;
            })
            .sort((a, b) => new Date(b.lastVisited || b.createdAt) - new Date(a.lastVisited || a.createdAt));
    }

    return linksToFilter.filter(l => l.folderId === currentFolder);
}

// ==================== Smart Folders (Saved Searches) ====================
// Renders saved filter presets as clickable sidebar items that "link"
// the Filters bar (save preset) into the Library navigation.
let activeSmartFolder = null;

function renderSmartFolders(container, focus = false) {
    const list = container || document.getElementById('folderList');
    if (!list) return;

    // Remove old smart-folder block if present
    const old = document.getElementById('smartFolderList');
    if (old && old.parentNode === list) old.remove();

    let presets = [];
    try { presets = window.getFilterPresets ? window.getFilterPresets() : []; } catch { presets = []; }

    const wrap = document.createElement('div');
    wrap.id = 'smartFolderList';

    if (presets.length === 0) {
        // Only show a subtle entry point so users discover the feature
        if (!focus) { return; }
        wrap.innerHTML = `<div class="px-4 py-2 text-xs text-gray-500">No Smart Folders yet.
Use <b>Filters → Save preset</b> to save a filter set as a smart folder.</div>`;
        list.appendChild(wrap);
        return;
    }

    const header = document.createElement('div');
    header.className = 'px-3 pt-2 pb-1 flex items-center justify-between';
    header.innerHTML = `
        <span class="text-[10px] font-bold text-gray-500 uppercase tracking-wider flex items-center gap-1">
            <i data-lucide="folder-search" class="w-3 h-3 text-amber-400"></i> Smart Folders
        </span>
        <button id="smartFolderAdd" class="p-0.5 hover:bg-white/10 rounded transition-colors text-gray-400 hover:text-amber-300"
            title="Save the current filter as a Smart Folder">
            <i data-lucide="plus" class="w-3 h-3"></i>
        </button>`;
    wrap.appendChild(header);

    presets.forEach((p) => {
        const div = document.createElement('div');
        div.className = `folder-item group flex items-center gap-3 px-4 py-2 mx-2 rounded-lg cursor-pointer transition-all ${activeSmartFolder === p.id ? 'active bg-amber-500/15 text-amber-200' : 'text-gray-400 hover:bg-white/10 hover:text-gray-200'}`;
        div.dataset.id = 'smart-' + p.id;
        div.dataset.type = 'smart';

        const icon = document.createElement('i');
        icon.dataset.lucide = 'search-check';
        icon.className = 'w-4 h-4 text-amber-400';

        const span = document.createElement('span');
        span.className = 'truncate text-sm font-medium';
        span.textContent = p.name || 'Untitled';

        const delBtn = document.createElement('button');
        delBtn.className = 'opacity-0 group-hover:opacity-100 p-1 hover:text-red-400 transition-opacity ml-auto shrink-0';
        delBtn.innerHTML = '<i data-lucide="trash-2" class="w-3 h-3"></i>';
        delBtn.title = 'Delete smart folder';
        delBtn.onclick = (e) => {
            e.stopPropagation();
            let ps = [];
            try { ps = window.getFilterPresets(); } catch { ps = []; }
            ps = ps.filter(x => x.id !== p.id);
            localStorage.setItem('linkLumina_filterPresets', JSON.stringify(ps));
            if (activeSmartFolder === p.id) activeSmartFolder = null;
            renderSmartFolders();
            renderLinks();
            showToast('Smart folder deleted', 'info');
        };

        div.appendChild(icon);
        div.appendChild(span);
        div.appendChild(delBtn);

        div.addEventListener('click', () => {
            activeSmartFolder = p.id;
            currentFolder = 'all';
            if (window.applyFilterPreset) window.applyFilterPreset(p);
            renderSidebar();
            const st = document.getElementById('sectionTitle');
            if (st) st.textContent = '🔍 ' + (p.name || 'Smart Folder');
            showToast(`Smart Folder: ${p.name}`, 'info');
        });

        wrap.appendChild(div);
    });

    const addBtn = wrap.querySelector('#smartFolderAdd');
    if (addBtn) {
        addBtn.onclick = (e) => {
            e.stopPropagation();
if (typeof window.saveFilterPreset !== 'function') { showToast('No Filters to save yet', 'info'); return; }
const name = prompt('Smart Folder name (the current filter will be saved):');
            if (name && name.trim()) {
                window.saveFilterPreset(name.trim());
                renderSmartFolders();
                showToast('Saved Smart Folder: ' + name.trim(), 'success');
            }
        };
    }

    list.appendChild(wrap);
    if (window.lucide) lucide.createIcons();
}

// ==================== Drag & Drop ====================

let draggedLinkId = null;

function setupDragAndDrop() {
    const list = document.getElementById('folderList');

    list.addEventListener('dragover', (e) => {
        e.preventDefault();
        const target = e.target.closest('.droppable');
        if (target) {
            target.classList.add('bg-white/20'); // Highlight
        }
    });

    list.addEventListener('dragleave', (e) => {
        const target = e.target.closest('.droppable');
        if (target) {
            target.classList.remove('bg-white/20');
        }
    });

    list.addEventListener('drop', async (e) => {
        e.preventDefault();
        const target = e.target.closest('.droppable');
        if (target) {
            target.classList.remove('bg-white/20');
            const targetFolderId = target.dataset.id;

            // Handle Link Drop
            if (draggedLinkId) {
                // If dropping on 'unsorted', folderId is null
                const actualTargetId = targetFolderId === 'unsorted' ? null : targetFolderId;
                await updateLinkFolder(draggedLinkId, actualTargetId);

                showToast(`Link moved to ${actualTargetId ? 'folder' : 'Unsorted'}`);
                draggedLinkId = null;
                renderSidebar(); // Update counts
            }

            // Handle Folder Drop (Nesting)
            if (window.draggedFolderId) {
                if (targetFolderId === 'unsorted') {
                    // Move to root
                    await updateFolderParent(window.draggedFolderId, null);
                    showToast('Folder moved to root');
                } else if (targetFolderId !== 'all' && targetFolderId !== 'favorites') {
                    await updateFolderParent(window.draggedFolderId, targetFolderId);
                    showToast('Folder nested successfully');
                }
                window.draggedFolderId = null;
            }
        }
    });
}

// Handle Drag Start (Attached to Link Cards in script.js)
function handleLinkDragStart(e, linkId) {
    draggedLinkId = linkId;
    e.dataTransfer.effectAllowed = 'move';
    // Create a ghost image if needed, or default
}


// Expose globally
window.initFolders = initFolders;
window.renderSidebar = renderSidebar;
window.filterLinksByFolder = filterLinksByFolder;
window.handleLinkDragStart = handleLinkDragStart;
window.createFolder = createFolder;
window.updateLinkFolder = updateLinkFolder;
window.selectFolder = selectFolder;
window.deleteFolder = deleteFolder;

// Add 'sectionTitle' to index.html HTML structure update
