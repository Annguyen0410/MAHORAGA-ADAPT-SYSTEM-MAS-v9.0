/* ============================================================================
 * LinkLumina — Feature Registry & Hub (features.js)
 * ----------------------------------------------------------------------------
 * Central registry for EVERY feature in the app. Adding a feature in the
 * future = one `AppFeatures.register({...})` call; it automatically appears
 * in the Feature Hub (Ctrl+Shift+F), the Command Palette (Ctrl+K) and any
 * generated menus. This is the "linking" layer that keeps the app growing
 * in a structured way.
 *
 * Feature shape:
 *   {
 *     id:      string (unique, kebab-case),
 *     title:   string,
 *     icon:    lucide icon name,
 *     category: one of AppFeatures.CATEGORIES,
 *     desc:    one-line description,
 *     keywords: [search aliases],
 *     shortcut: optional display string e.g. "Ctrl+N",
 *     badge:   optional short label (e.g. "NEW"),
 *     action:  () => void  (runs when activated; hub closes first)
 *   }
 * ==========================================================================*/
(function () {
    'use strict';

    const CATEGORIES = [
        { id: 'core',      label: 'Core',      icon: 'zap' },
        { id: 'view',      label: 'View',      icon: 'layout-grid' },
        { id: 'data',      label: 'Data',      icon: 'database' },
        { id: 'analysis',  label: 'Analysis',  icon: 'brain-circuit' },
        { id: 'automation',label: 'Automation',icon: 'bot' },
        { id: 'extras',    label: 'Extras',    icon: 'sparkles' },
    ];

    const features = [];
    const byId = new Map();

    function register(f) {
        if (!f || !f.id || byId.has(f.id)) {
            console.warn('[AppFeatures] Ignoring invalid/duplicate feature', f && f.id);
            return f;
        }
        features.push(f);
        byId.set(f.id, f);
        return f;
    }

    function getAll() { return features.slice(); }
    function getById(id) { return byId.get(id); }
    function count() { return features.length; }

    function getByCategory() {
        const groups = CATEGORIES.map(c => ({ ...c, items: [] }));
        for (const f of features) {
            const g = groups.find(g => g.id === f.category) ||
                      groups.find(g => g.id === 'extras');
            g.items.push(f);
        }
        return groups;
    }

    /* ----------------------------- Command Palette ---------------------------- */
    // Features expose themselves to the Ctrl+K palette.
    function toCommands() {
        return features
            .filter(f => !f.hidden)
            .map(f => ({
                id: 'feature-' + f.id,
                title: f.title,
                icon: f.icon || 'sparkles',
                action: () => { run(f); },
                keywords: ['feature', 'tool', (f.keywords || []).join(' '), f.category],
            }));
    }

    /* ------------------------------- Execution -------------------------------- */
    function run(f) {
        closeHub();
        try {
            if (typeof f.action === 'function') f.action();
        } catch (e) {
            console.error('[AppFeatures] action failed for "' + f.id + '":', e);
            if (typeof window.showToast === 'function') {
                window.showToast('Feature error: ' + (e.message || e), 'error');
            }
        }
    }

    /* ------------------------------- Feature Hub ------------------------------ */
    let hubEl = null;
    let hubSearchValue = '';

    function openHub() {
        if (hubEl) { closeHub(); }
        const groups = getByCategory();
        const total = count();

        hubEl = document.createElement('div');
        hubEl.id = 'featureHub';
        hubEl.className = 'fixed inset-0 z-[99999] flex items-center justify-center p-4';
        hubEl.style.background = 'rgba(5, 3, 3, 0.72)';
        hubEl.style.backdropFilter = 'blur(14px)';
        hubEl.style.animation = 'featureHubIn 0.28s cubic-bezier(0.16, 1, 0.3, 1) both';

        const sectionWrap = (g) => {
            if (!g.items.length) return '';
            const tiles = g.items.map((f, i) => `
                <button type="button" class="feat-tile" data-feat="${f.id}"
                    style="animation-delay:${Math.min(i * 30, 420)}ms">
                    <span class="feat-tile-icon"><i data-lucide="${f.icon || 'sparkles'}" class="w-5 h-5"></i></span>
                    <span class="feat-tile-body">
                        <span class="feat-tile-title">${(f.title || f.id).replace(/</g, '&lt;')}
                            ${f.badge ? `<em class="feat-badge">${f.badge}</em>` : ''}
                            ${f.shortcut ? `<kbd class="feat-kbd">${f.shortcut}</kbd>` : ''}
                        </span>
                        <span class="feat-tile-desc">${(f.desc || '').replace(/</g, '&lt;')}</span>
                    </span>
                </button>`).join('');

            return `
                <section class="feat-group" data-cat="${g.id}">
                    <div class="feat-group-head">
                        <i data-lucide="${g.icon}" class="w-4 h-4"></i> ${g.label}
                        <span class="feat-group-count">${g.items.length}</span>
                    </div>
                    <div class="feat-grid">${tiles}</div>
                </section>`;
        };

        hubEl.innerHTML = `
            <div class="feat-hub glass-card">
                <div class="feat-hub-head">
                    <div>
                        <h2 class="feat-hub-title"><i data-lucide="sparkles" class="w-5 h-5"></i> Feature Hub</h2>
                        <p class="feat-hub-sub">${total} features · all in one place · Ctrl+Shift+F</p>
                    </div>
                    <button type="button" id="featHubClose" class="feat-hub-close" title="Close (Esc)">
                        <i data-lucide="x" class="w-5 h-5"></i>
                    </button>
                </div>
                <div class="feat-hub-search">
                    <i data-lucide="search" class="w-4 h-4"></i>
                    <input id="featHubSearch" type="text" placeholder="Search features… (e.g. analytics, export, zen)"
                        autocomplete="off">
                </div>
                <div class="feat-hub-body">${groups.map(sectionWrap).join('')}</div>
                <div class="feat-hub-empty hidden">
                    <i data-lucide="search-x" class="w-10 h-10"></i>
                    <p>No matching features found</p>
                </div>
            </div>`;

        document.body.appendChild(hubEl);

        const search = hubEl.querySelector('#featHubSearch');
        const groupsEl = hubEl.querySelectorAll('.feat-group');
        const emptyEl = hubEl.querySelector('.feat-hub-empty');
        let searchRaf = null;

        const applyFilter = (q) => {
            q = q.trim().toLowerCase();
            let visibleGroups = 0;
            groupsEl.forEach(group => {
                const tiles = group.querySelectorAll('.feat-tile');
                let visible = 0;
                tiles.forEach(t => {
                    const f = byId.get(t.dataset.feat);
                    const hay = (f.title + ' ' + f.desc + ' ' + (f.keywords || []).join(' ') + ' ' + f.category).toLowerCase();
                    const show = !q || hay.includes(q);
                    t.style.display = show ? '' : 'none';
                    if (show) visible++;
                });
                group.style.display = visible ? '' : 'none';
                if (visible) visibleGroups++;
            });
            emptyEl.classList.toggle('hidden', visibleGroups > 0);
        };

        search.addEventListener('input', () => {
            if (searchRaf) cancelAnimationFrame(searchRaf);
            searchRaf = requestAnimationFrame(() => applyFilter(search.value));
        });

        hubEl.addEventListener('click', (e) => {
            const tile = e.target.closest('.feat-tile');
            if (tile) {
                const f = byId.get(tile.dataset.feat);
                if (f) run(f);
                return;
            }
            if (e.target.closest('#featHubClose') || e.target === hubEl) closeHub();
        });

        const onKey = (e) => {
            if (e.key === 'Escape') { closeHub(); }
            else if (e.key === '/' && document.activeElement !== search) {
                e.preventDefault();
                search.focus();
            }
        };
        hubEl._keyHandler = onKey;
        document.addEventListener('keydown', onKey);

        if (window.lucide) lucide.createIcons();

        // Focus search for instant keyboard use
        setTimeout(() => search && search.focus(), 60);
    }

    function closeHub() {
        if (!hubEl) return;
        if (hubEl._keyHandler) document.removeEventListener('keydown', hubEl._keyHandler);
        hubEl.remove();
        hubEl = null;
    }

    /* ------------------------------ Global handle ----------------------------- */
    window.AppFeatures = {
        CATEGORIES,
        register,
        getAll,
        getById,
        count,
        getByCategory,
        toCommands,
        openHub,
        closeHub,
    };

    // Global shortcut: Ctrl+Shift+F opens the hub
    document.addEventListener('keydown', (e) => {
        if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'F' || e.key === 'f')) {
            e.preventDefault();
            if (hubEl) closeHub(); else openHub();
        }
    });

    // ESC fallback if hub was removed some other way
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && hubEl) closeHub();
    });
})();
