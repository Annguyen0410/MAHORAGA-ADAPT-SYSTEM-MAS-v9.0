/**
 * LinkLumina Artifact-Level Features
 * Phase 2–6: Auto-tagging, Smart Search, Analytics, Views, Health, Batch, Collections, Relationships
 */
(function () {
    'use strict';

    if (typeof window.links === 'undefined') return;

    // ==================== Phase 2: AI-Powered ====================

    const SEARCH_HISTORY_KEY = 'linkLumina_searchHistory';
    const MAX_SEARCH_HISTORY = 20;

    function getSearchHistory() {
        try {
            const raw = localStorage.getItem(SEARCH_HISTORY_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch { return []; }
    }

    function pushSearchHistory(query) {
        if (!query || query.length < 2) return;
        let arr = getSearchHistory().filter(q => q !== query);
        arr.unshift(query);
        arr = arr.slice(0, MAX_SEARCH_HISTORY);
        localStorage.setItem(SEARCH_HISTORY_KEY, JSON.stringify(arr));
    }

    window.getSearchSuggestions = function (prefix) {
        const history = getSearchHistory();
        const lower = (prefix || '').toLowerCase();
        if (!lower) return history.slice(0, 8);
        return history.filter(q => q.toLowerCase().includes(lower)).slice(0, 8);
    };

    window.pushSearchHistory = pushSearchHistory;

    // Smart tag merging: normalize similar tags
    const TAG_ALIASES = {
        'reactjs': 'react', 'vuejs': 'vue', 'nodejs': 'node', 'javascript': 'js',
        'typescript': 'ts', 'machinelearning': 'ml', 'artificialintelligence': 'ai',
        'tutorials': 'tutorial', 'howto': 'guide', 'docs': 'documentation'
    };

    window.smartMergeTags = function (tags) {
        if (!Array.isArray(tags)) return [];
        const seen = new Set();
        return tags.map(t => {
            const lower = t.toLowerCase().replace(/\s+/g, '');
            const normalized = TAG_ALIASES[lower] || lower;
            if (seen.has(normalized)) return null;
            seen.add(normalized);
            return t.length > 1 ? t : null;
        }).filter(Boolean).slice(0, 8);
    };

    // Find similar links (same domain, shared tags, similar title)
    window.findSimilarLinks = function (link, limit = 5) {
        if (!window.links || !link) return [];
        const url = link.url || '';
        let host = '';
        try { host = new URL(url).hostname.replace('www.', ''); } catch { }
        const linkTags = new Set((link.tags || []).map(t => t.toLowerCase()));
        const titleWords = (link.title || '').toLowerCase().split(/\s+/).filter(w => w.length > 2);

        const scored = window.links
            .filter(l => l.id !== link.id && l.url !== link.url)
            .map(l => {
                let score = 0;
                try {
                    const h = new URL(l.url).hostname.replace('www.', '');
                    if (h === host) score += 3;
                } catch { }
                (l.tags || []).forEach(t => {
                    if (linkTags.has(t.toLowerCase())) score += 2;
                });
                const lTitle = (l.title || '').toLowerCase();
                titleWords.forEach(w => {
                    if (lTitle.includes(w)) score += 1;
                });
                return { link: l, score };
            })
            .filter(x => x.score > 0)
            .sort((a, b) => b.score - a.score)
            .slice(0, limit)
            .map(x => x.link);

        return scored;
    };

    window.getRelatedLinks = window.findSimilarLinks;

    // Extract topics from title + url (heuristic)
    window.extractTopicsFromText = function (title, url) {
        const text = ((title || '') + ' ' + (url || '')).toLowerCase();
        const topics = [];
        const patterns = [
            /\b(react|vue|angular|svelte|node|python|javascript|typescript|rust|go|java)\b/g,
            /\b(tutorial|guide|docs|api|course|learn|howto|example)\b/g,
            /\b(design|ui|ux|css|figma|dribbble)\b/g,
            /\b(github|npm|docker|aws|cloud)\b/g
        ];
        patterns.forEach(re => {
            let m;
            while ((m = re.exec(text)) !== null) {
                if (!topics.includes(m[1])) topics.push(m[1]);
            }
        });
        return topics.slice(0, 5);
    };

    // Detect possible duplicate links (same host + similar title)
    window.detectDuplicateLinks = function (link) {
        if (!window.links || !link) return [];
        let host = '';
        try { host = new URL(link.url).hostname; } catch { return []; }
        const title = (link.title || '').toLowerCase();
        return window.links.filter(l => {
            if (l.id === link.id) return false;
            let h = '';
            try { h = new URL(l.url).hostname; } catch { return false; }
            if (h !== host) return false;
            const t = (l.title || '').toLowerCase();
            const words = title.split(/\s+/).filter(w => w.length > 2);
            const matchCount = words.filter(w => t.includes(w)).length;
            return matchCount >= Math.min(2, words.length);
        });
    };

    // ==================== Phase 5: Link Health ====================

    window.linkHealthCache = window.linkHealthCache || new Map();
    const HEALTH_CACHE_TTL = 1000 * 60 * 30; // 30 min

    window.checkLinkHealth = async function (url) {
        const cached = window.linkHealthCache.get(url);
        if (cached && Date.now() - cached.t < HEALTH_CACHE_TTL) return cached;
        try {
            const res = await fetch(url, { method: 'HEAD', mode: 'no-cors' }).catch(() => null);
            const ok = res ? res.ok : false;
            const status = res ? res.status : 0;
            const result = { ok: ok || status === 0, status: status || 0 };
            window.linkHealthCache.set(url, { ...result, t: Date.now() });
            return result;
        } catch (e) {
            const result = { ok: false, status: 0 };
            window.linkHealthCache.set(url, { ...result, t: Date.now() });
            return result;
        }
    };

    // ==================== Phase 6: Smart Collections ====================

    window.getSmartCollections = function () {
        const now = new Date();
        const weekAgo = new Date(now);
        weekAgo.setDate(now.getDate() - 7);
        const links = window.links || [];
        return {
            recentlyAdded: links.filter(l => l.createdAt && new Date(l.createdAt) >= weekAgo).length,
            mostVisited: links.filter(l => (l.visitCount || 0) >= 3).length,
            unvisited: links.filter(l => (l.visitCount || 0) === 0).length
        };
    };

    // ==================== Filter Presets (Phase 4) ====================

    const FILTER_PRESETS_KEY = 'linkLumina_filterPresets';

    window.getFilterPresets = function () {
        try {
            const raw = localStorage.getItem(FILTER_PRESETS_KEY);
            return raw ? JSON.parse(raw) : [];
        } catch { return []; }
    };

    window.saveFilterPreset = function (name) {
        const presets = window.getFilterPresets();
        const searchInput = document.getElementById('searchInput');
        const categoryFilter = document.querySelector('.category-filter.active');
        const filterSelect = document.getElementById('filterSelect');
        const sortSelect = document.getElementById('sortSelect');
        presets.push({
            id: Date.now().toString(),
            name,
            search: searchInput ? searchInput.value : '',
            category: categoryFilter ? categoryFilter.dataset.category : 'all',
            filter: filterSelect ? filterSelect.value : 'all',
            sort: sortSelect ? sortSelect.value : 'newest',
            createdAt: new Date().toISOString()
        });
        localStorage.setItem(FILTER_PRESETS_KEY, JSON.stringify(presets.slice(-20)));
    };

    window.applyFilterPreset = function (preset) {
        const searchInput = document.getElementById('searchInput');
        if (searchInput) searchInput.value = preset.search || '';
        if (typeof window.searchTerm !== 'undefined') window.searchTerm = (preset.search || '').toLowerCase();
        const catBtn = document.querySelector(`.category-filter[data-category="${preset.category || 'all'}"]`);
        if (catBtn) catBtn.click();
        const filterSelect = document.getElementById('filterSelect');
        if (filterSelect) filterSelect.value = preset.filter || 'all';
        const sortSelect = document.getElementById('sortSelect');
        if (sortSelect) sortSelect.value = preset.sort || 'newest';
        if (typeof window.sortBy !== 'undefined') window.sortBy = preset.sort || 'newest';
        if (typeof window.renderLinks === 'function') window.renderLinks();
    };

    console.log('LinkLumina Artifact features loaded');
})();
