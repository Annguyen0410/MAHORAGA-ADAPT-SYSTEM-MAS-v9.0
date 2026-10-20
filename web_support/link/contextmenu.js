// ==================== Context Menu System ====================
// Reusable right-click context menu

const ContextMenu = {
    element: null,
    currentTarget: null,
    currentType: null,

    init() {
        this.element = document.getElementById('contextMenu');
        if (!this.element) return;

        // Hide on click outside
        document.addEventListener('click', () => this.hide());
        document.addEventListener('contextmenu', (e) => {
            // Only show custom menu on specific elements
            const linkCard = e.target.closest('[data-link-id]');
            const folderItem = e.target.closest('.folder-item[data-type="custom"]');

            if (linkCard) {
                e.preventDefault();
                this.showForLink(linkCard.dataset.linkId, e.clientX, e.clientY);
            } else if (folderItem) {
                e.preventDefault();
                this.showForFolder(folderItem.dataset.id, e.clientX, e.clientY);
            }
        });

        console.log('📋 ContextMenu: Initialized');
    },

    show(x, y, items) {
        const container = document.getElementById('contextMenuItems');
        if (!container) return;

        container.innerHTML = items.map(item => {
            if (item.divider) {
                return '<div class="h-px bg-white/10 my-1"></div>';
            }
            return `
                <button class="w-full text-left px-3 py-2 rounded hover:bg-white/10 flex items-center gap-2 text-sm ${item.danger ? 'text-red-400' : 'text-gray-200'} transition-colors"
                        onclick="ContextMenu.executeAction('${item.action}')">
                    <i data-lucide="${item.icon}" class="w-4 h-4"></i>
                    ${item.label}
                </button>
            `;
        }).join('');

        // Position menu
        this.element.style.left = `${Math.min(x, window.innerWidth - 200)}px`;
        this.element.style.top = `${Math.min(y, window.innerHeight - 300)}px`;
        this.element.classList.remove('hidden');

        if (typeof lucide !== 'undefined') lucide.createIcons();
    },

    hide() {
        if (this.element) {
            this.element.classList.add('hidden');
        }
        this.currentTarget = null;
        this.currentType = null;
    },

    showForLink(linkId, x, y) {
        this.currentTarget = linkId;
        this.currentType = 'link';

        const link = window.links?.find(l => l.id === linkId);
        if (!link) return;

        const items = [
            { icon: 'external-link', label: 'Open Link', action: 'open' },
            { icon: 'copy', label: 'Copy URL', action: 'copyUrl' },
            { divider: true },
            { icon: 'edit', label: 'Edit', action: 'edit' },
            { icon: link.favorite ? 'star-off' : 'star', label: link.favorite ? 'Remove Favorite' : 'Add to Favorites', action: 'toggleFavorite' },
            { icon: 'folder', label: 'Move...', action: 'move' },
            { icon: 'share-2', label: 'View in Graph', action: 'viewInGraph' },
            { divider: true },
            { icon: 'trash-2', label: 'Delete', action: 'delete', danger: true }
        ];

        this.show(x, y, items);
    },

    showForFolder(folderId, x, y) {
        this.currentTarget = folderId;
        this.currentType = 'folder';

        const items = [
            { icon: 'edit', label: 'Rename', action: 'rename' },
            { icon: 'share-2', label: 'View in Graph', action: 'viewFolderInGraph' },
            { divider: true },
            { icon: 'trash-2', label: 'Delete Folder', action: 'deleteFolder', danger: true }
        ];

        this.show(x, y, items);
    },

    async executeAction(action) {
        const id = this.currentTarget;
        const type = this.currentType;
        this.hide();

        if (type === 'link') {
            const link = window.links?.find(l => l.id === id);
            if (!link) return;

            switch (action) {
                case 'open':
                    window.open(link.url, '_blank');
                    // Track visit
                    link.visitCount = (link.visitCount || 0) + 1;
                    link.lastVisited = new Date().toISOString();
                    if (window.saveSingleLink) await window.saveSingleLink(link);
                    if (window.EventBus) window.EventBus.emit(window.EVENTS.LINK_VISITED, { item: link });
                    break;

                case 'copyUrl':
                    navigator.clipboard.writeText(link.url);
                    if (window.showToast) window.showToast('URL copied!', 'success');
                    break;

                case 'edit':
                    if (window.openModal) window.openModal(id);
                    break;

                case 'toggleFavorite':
                    link.favorite = !link.favorite;
                    if (window.saveSingleLink) await window.saveSingleLink(link);
                    if (window.renderLinks) window.renderLinks();
                    if (window.renderSidebar) window.renderSidebar();
                    if (window.showToast) window.showToast(link.favorite ? 'Added to Favorites' : 'Removed from Favorites', 'success');
                    break;

                case 'move':
                    // Open a simple prompt for now (can be enhanced to modal)
                    const folderNames = (window.folders || []).map(f => f.name).join(', ');
                    const targetName = prompt(`Move to which folder?\nAvailable: ${folderNames || 'No folders yet'}`);
                    if (targetName) {
                        const folder = window.folders.find(f => f.name.toLowerCase() === targetName.toLowerCase());
                        if (folder && window.updateLinkFolder) {
                            await window.updateLinkFolder(id, folder.id);
                            if (window.showToast) window.showToast(`Moved into "${folder.name}"`, 'success');
                        }
                    }
                    break;

                case 'viewInGraph':
                    if (window.openNeuralWeb) window.openNeuralWeb();
                    break;

                case 'delete':
                    if (confirm('Delete this link?')) {
                        if (window.deleteLink) await window.deleteLink(id);
                    }
                    break;
            }
        } else if (type === 'folder') {
            switch (action) {
                case 'rename':
                    const folder = window.folders?.find(f => f.id === id);
                    if (folder) {
                        const newName = prompt('New name:', folder.name);
                        if (newName && newName.trim()) {
                            folder.name = newName.trim();
                            const tx = db.transaction(['folders'], 'readwrite');
                            tx.objectStore('folders').put(folder);
                            if (window.renderSidebar) window.renderSidebar();
                        }
                    }
                    break;

                case 'viewFolderInGraph':
                    if (window.openNeuralWeb) window.openNeuralWeb();
                    break;

                case 'deleteFolder':
                    if (confirm('Delete this folder? Its links will move to Unsorted.')) {
                        if (window.deleteFolder) await window.deleteFolder(id);
                    }
                    break;
            }
        }
    }
};

// Initialize on DOM ready
document.addEventListener('DOMContentLoaded', () => ContextMenu.init());

// Expose globally
window.ContextMenu = ContextMenu;
