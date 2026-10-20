// ==================== Tools (Product Hunt style) ====================
// Card grid with images + rich descriptions. Batch-rendered + lazy images +
// IntersectionObserver so 10k+ tools stay smooth.
// Product Hunt sync: rich GraphQL (thumbnail, topics, votes, description),
// cursor pagination for unlimited posts, daily auto-update.

var tools = window.tools = [];
var toolsLoaded = false;
var toolsEditingId = null;
var toolsFiltered = [];
var toolsRenderedCount = 0;
var toolsBatchInFlight = false;
var toolsSentinelObserver = null;
var toolsImgObserver = null;
var toolsListEl = null;

const TOOLS_BATCH_SIZE = 48;
const PH_GRAPHQL_URL = 'https://api.producthunt.com/v2/api/graphql';
const PH_TOKEN_KEY = 'linkLumina_phToken';
const PH_LAST_FETCH_KEY = 'linkLumina_phLastFetch';
const PH_AUTO_6AM_KEY = 'linkLumina_phAuto6am';
const PH_AUTO_LAST_RUN_KEY = 'linkLumina_phAutoLastRun';
const PH_ID_PREFIX = 'ph_';
const MAX_PH_PAGES_PER_RUN = 20; // first * 20 posts max per run (unlimited over time)

function getProductHuntToken() {
    try { return (localStorage.getItem(PH_TOKEN_KEY) || '').trim(); } catch (e) { return ''; }
}
function setProductHuntToken(token) {
    try { localStorage.setItem(PH_TOKEN_KEY, (token || '').trim()); } catch (e) { }
}
function getProductHuntLastFetch() {
    try { return localStorage.getItem(PH_LAST_FETCH_KEY) || ''; } catch (e) { return ''; }
}
function setProductHuntLastFetch(iso) {
    try { localStorage.setItem(PH_LAST_FETCH_KEY, iso || ''); } catch (e) { }
}

function _toolNorm(s) {
    try { return (s || '').toString().toLowerCase().normalize('NFD').replace(/[\u0300-\u036f]/g, ''); }
    catch (e) { return (s || '').toString().toLowerCase(); }
}
function _toolDomain(u) {
    try { return new URL(u).hostname.replace(/^www\./, ''); } catch (e) { return ''; }
}

// --- Auto-tag & categorize (Vietnamese, aligned with link categories) --------
const TOOL_TOPIC_VI = {
    'ai': 'AI', 'artificial intelligence': 'AI', 'machine learning': 'AI', 'llm': 'AI', 'chatgpt': 'AI', 'generative ai': 'AI',
    'design': 'design', 'ui': 'design', 'ux': 'design', 'prototyping': 'design', 'user experience': 'design', 'design tools': 'design',
    'productivity': 'productivity', 'task management': 'productivity', 'calendar': 'productivity', 'time management': 'productivity',
    'developer tools': 'dev-tools', 'development': 'dev-tools', 'programming': 'dev-tools', 'api': 'dev-tools', 'software engineering': 'dev-tools',
    'marketing': 'marketing', 'seo': 'marketing', 'social media': 'marketing', 'email': 'marketing', 'content marketing': 'marketing',
    'collaboration': 'collaboration', 'communication': 'collaboration', 'remote work': 'collaboration', 'team': 'collaboration', 'messaging': 'collaboration',
    'video': 'video', 'audio': 'audio', 'music': 'music', 'gaming': 'gaming', 'video editing': 'video',
    'finance': 'finance', 'crypto': 'finance', 'fintech': 'finance', 'banking': 'finance', 'investing': 'finance', 'accounting': 'finance',
    'e-commerce': 'shopping', 'ecommerce': 'shopping', 'shopping': 'shopping', 'retail': 'shopping',
    'education': 'learning', 'e-learning': 'learning', 'learning': 'learning', 'course': 'learning', 'edtech': 'learning',
    'health': 'health', 'fitness': 'health', 'wellness': 'health', 'mental health': 'health',
    'photography': 'photo', 'writing': 'writing', 'copywriting': 'writing', 'notes': 'notes',
    'analytics': 'analytics', 'data': 'data', 'database': 'data', 'big data': 'data',
    'security': 'security', 'privacy': 'security', 'cybersecurity': 'security',
    'automation': 'automation', 'workflow': 'automation', 'no-code': 'nocode', 'low-code': 'nocode',
    'saas': 'saas', 'chrome extensions': 'chrome-extension', 'extensions': 'chrome-extension',
    'open source': 'opensource', 'blockchain': 'blockchain', 'web3': 'blockchain',
    'customer support': 'support', 'crm': 'crm', 'sales': 'sales', 'recruiting': 'hr', 'human resources': 'hr', 'hiring': 'hr',
    'travel': 'travel', 'food': 'food', 'fashion': 'fashion', 'books': 'books', 'news': 'news', 'career': 'career'
};

const TOOL_TOPIC_CATEGORY = {
    'ai': 'AI Tools', 'artificial intelligence': 'AI Tools', 'machine learning': 'AI Tools', 'llm': 'AI Tools', 'chatgpt': 'AI Tools', 'generative ai': 'AI Tools',
    'developer tools': 'Development', 'development': 'Development', 'programming': 'Development', 'api': 'Development', 'software engineering': 'Development',
    'design': 'Design', 'prototyping': 'Design', 'ui': 'Design', 'ux': 'Design',
    'productivity': 'Productivity', 'task management': 'Productivity', 'time management': 'Productivity',
    'marketing': 'Marketing', 'seo': 'Marketing', 'social media': 'Marketing', 'email': 'Marketing',
    'video': 'Video', 'video editing': 'Video', 'audio': 'Music', 'music': 'Music',
    'finance': 'Finance', 'fintech': 'Finance', 'crypto': 'Finance', 'investing': 'Finance',
    'e-commerce': 'Shopping', 'ecommerce': 'Shopping', 'shopping': 'Shopping', 'retail': 'Shopping',
    'education': 'Learning', 'e-learning': 'Learning', 'course': 'Learning',
    'analytics': 'Analytics', 'data': 'Research', 'big data': 'Research',
    'security': 'Security', 'privacy': 'Security',
    'collaboration': 'Collaboration', 'communication': 'Collaboration', 'remote work': 'Collaboration',
    'health': 'Health', 'fitness': 'Health', 'wellness': 'Health',
    'news': 'News', 'writing': 'Writing', 'photography': 'Photo', 'gaming': 'Gaming',
    'automation': 'Automation', 'workflow': 'Productivity', 'no-code': 'NoCode', 'low-code': 'NoCode',
    'blockchain': 'Blockchain', 'web3': 'Blockchain', 'open source': 'Open Source',
    'crm': 'CRM', 'sales': 'Sales', 'recruiting': 'HR', 'human resources': 'HR',
    'travel': 'Travel', 'food': 'Food', 'books': 'Books'
};

function autoCategorizeTool(item) {
    const text = _toolNorm([item.n, item.d, item.desc, (item.topics || []).join(' ')].join(' '));
    const topics = (item.topics || []).map(_toolNorm);
    let cat = '';
    for (const [kw, c] of Object.entries(TOOL_TOPIC_CATEGORY)) {
        if (topics.some(t => t === kw || t.indexOf(kw) !== -1) || text.indexOf(kw) !== -1) { cat = c; break; }
    }
    if (!cat && typeof getAutoCategory === 'function') cat = getAutoCategory(item.u || '', item.n || '');
    if (!cat || cat === 'General') cat = 'Tools';

    const tags = [];
    const seen = new Set();
    (item.topics || []).forEach(function (t) {
        const key = _toolNorm(t);
        const vi = TOOL_TOPIC_VI[key] || t.toLowerCase().replace(/\s+/g, '-').slice(0, 24);
        if (!seen.has(vi)) { seen.add(vi); tags.push(vi); }
    });
    if (!seen.has(cat.toLowerCase())) tags.push(cat.toLowerCase());
    return { cat: cat, tags: tags.slice(0, 6) };
}

// --- Duplicate detection: tool domain/URL vs saved links ---------------------
let toolDupCache = new Map(); // toolId -> { url, title }
function _buildLinkDupIndex() {
    const byDomain = new Map();
    const byUrl = new Map();
    (window.links || []).forEach(function (l) {
        if (!l.url) return;
        if (!byUrl.has(l.url)) byUrl.set(l.url, l);
        try {
            const d = new URL(l.url).hostname.replace(/^www\./, '').toLowerCase();
            if (!byDomain.has(d)) byDomain.set(d, l);
        } catch (e) { }
    });
    return { byDomain: byDomain, byUrl: byUrl };
}
function checkToolDup(item, dupIndex) {
    const idx = dupIndex || _buildLinkDupIndex();
    let match = null;
    if (item.u && idx.byUrl.has(item.u)) match = idx.byUrl.get(item.u);
    else if (item.domain && idx.byDomain.has(item.domain)) match = idx.byDomain.get(item.domain);
    if (match) {
        item.dup = true;
        item.dupUrl = match.url;
        item.dupTitle = match.title || match.url;
        toolDupCache.set(item.id, { url: match.url, title: match.title || match.url });
        return true;
    }
    toolDupCache.delete(item.id);
    return false;
}

// --- Product Hunt sync ------------------------------------------------------

async function fetchProductHunt(opts) {
    opts = opts || {};
    var deep = !!opts.deep; // deep scan: scan far back in history (max 5000 posts)
    var maxPages = deep ? 50 : MAX_PH_PAGES_PER_RUN;
    var token = (document.getElementById('phTokenInput')?.value || '').trim() || getProductHuntToken();
    if (!token) {
        if (window.showToast) window.showToast('Enter your Product Hunt API token (Developer Token) in the field above.', 'warning');
        return;
    }
    setProductHuntToken(token);
    var first = deep ? 100 : 50;
    var sel = document.getElementById('phFirstCount');
    if (!deep && sel) first = Math.min(100, Math.max(20, parseInt(sel.value, 10) || 50));
    var btn = document.getElementById(deep ? 'phDeepBtn' : 'phFetchBtn');
    var btnOriginal = btn ? btn.innerHTML : '';
    function restoreBtn() {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = btnOriginal || '<i data-lucide="download" class="w-4 h-4"></i> Fetch new tools from Product Hunt';
            if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
        }
    }
    if (btn) { btn.disabled = true; btn.textContent = deep ? 'Deep scanning...' : 'Fetching...'; }

    // NOTE: the PH GraphQL `Post` type has NO `image` field — only `thumbnail`.
    // Querying `image { url }` makes the API reject the whole request with
    // "Field 'image' doesn't exist on type 'Post'", so we only request thumbnail.
    var query = 'query($first: Int!, $after: String) { posts(first: $first, after: $after, order: NEWEST) { ' +
        'nodes { id name tagline description website url votesCount createdAt ' +
        'thumbnail { url } topics { nodes { name } } } ' +
        'pageInfo { endCursor hasNextPage } } }';

    var existingIds = {};
    tools.forEach(function (t) { if (t.id && t.id.indexOf(PH_ID_PREFIX) === 0) existingIds[t.id] = true; });
    var added = 0;
    var newDups = 0;
    var dupIndex = _buildLinkDupIndex();
    var after = null;
    // Rate-limit helper: retry 429 responses with backoff (honors Retry-After).
    async function phFetch(bodyObj) {
        var attempt = 0;
        var maxAttempts = 3;
        for (;;) {
            var r = await fetch(PH_GRAPHQL_URL, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token },
                body: JSON.stringify(bodyObj)
            });
            if (r.status !== 429 || attempt >= maxAttempts) return r;
            attempt++;
            var waitMs = 5000 * Math.pow(2, attempt - 1); // 5s → 10s → 20s
            var retryAfter = parseInt(r.headers.get('Retry-After') || '', 10);
            if (!isNaN(retryAfter) && retryAfter > 0) waitMs = Math.max(waitMs, retryAfter * 1000);
            if (btn) btn.textContent = 'Rate limited — retrying in ' + Math.round(waitMs / 1000) + 's...';
            await new Promise(function (res) { setTimeout(res, waitMs); });
        }
    }

    try {
        for (var page = 0; page < maxPages; page++) {
            if (deep && btn) btn.textContent = 'Deep scanning ' + Math.round((page / maxPages) * 100) + '%...';
            if (deep && page > 0) await new Promise(function (r) { setTimeout(r, 120); });
            var res = await phFetch({ query: query, variables: { first: first, after: after } });
            var data = null;
            try { data = await res.json(); } catch (_) { }
            if (res.status === 401) {
                if (window.showToast) window.showToast('Invalid or expired token. Go to Product Hunt → Developer → OAuth Apps, create an app and generate a new Developer Token.', 'error');
                restoreBtn();
                return;
            }
            if (res.status === 429) {
                if (window.showToast) window.showToast('Product Hunt rate limit reached. Wait a few minutes, then try again.', 'warning');
                restoreBtn();
                return;
            }
            if (!res.ok || (data && data.errors)) {
                var msg = (data && data.errors && data.errors[0] && data.errors[0].message) || (data && data.message) || res.statusText || 'API error';
                if (window.showToast) window.showToast('Product Hunt: ' + msg, 'error');
                restoreBtn();
                return;
            }
            if (!data) data = {};
            var nodes = (data.data && data.data.posts && data.data.posts.nodes) || [];
            var pageInfo = (data.data && data.data.posts && data.data.posts.pageInfo) || {};
            var pageAdded = 0;
            var now = Date.now();
            for (var i = 0; i < nodes.length; i++) {
                var node = nodes[i];
                var id = PH_ID_PREFIX + (node.id || '');
                if (existingIds[id]) continue;
                var name = (node.name || '').trim().slice(0, 120);
                var website = (node.website || node.url || '').trim().slice(0, 2048);
                if (!name || !website) continue;
                var topics = ((node.topics && node.topics.nodes) || []).map(function (t) { return (t.name || '').slice(0, 60); }).filter(Boolean);
                var item = {
                    id: id,
                    n: name,
                    d: (node.tagline || '').trim().slice(0, 240),
                    desc: (node.description || node.tagline || '').trim().slice(0, 1200),
                    u: website,
                    t: now,
                    img: (node.thumbnail && node.thumbnail.url) || '',
                    topics: topics,
                    votes: node.votesCount || 0,
                    phUrl: 'https://www.producthunt.com/posts/' + (node.id || ''),
                    domain: _toolDomain(website)
                };
                var auto = autoCategorizeTool(item);
                item.cat = auto.cat;
                item.tags = auto.tags;
                if (checkToolDup(item, dupIndex)) newDups++;
                tools.unshift(item);
                existingIds[id] = true;
                if (window.saveToolToDB) await window.saveToolToDB(item);
                added++;
                pageAdded++;
            }
            if (!nodes.length || !pageInfo.hasNextPage || !after && pageAdded === 0) break;
            after = pageInfo.endCursor || null;
            if (pageAdded === 0 && page > 0) break; // no new posts anywhere → stop early
            if (page > 0 && pageAdded === 0) break;
        }
        tools.sort(function (a, b) { return (b.t || 0) - (a.t || 0); });
        setProductHuntLastFetch(new Date().toISOString());
        if (window.showToast) {
            var msg = 'Fetched ' + added + ' new tools from Product Hunt.';
            if (newDups) msg += ' ⚠ ' + newDups + ' match a saved link (domain/URL).';
            window.showToast(msg, added ? (newDups ? 'warning' : 'success') : 'info');
        }
        updateToolsView();
        updateProductHuntUI();
        renderToolDupBadge();
    } catch (e) {
        if (window.showToast) window.showToast('Error: ' + (e.message || 'Network'), 'error');
    }
    restoreBtn();
}

// Auto-update: run once per day when data is older than 24h (on load + hourly).
function runAutoDailyIfNeeded() {
    try {
        if (localStorage.getItem(PH_AUTO_6AM_KEY) !== 'true') return;
        if (!getProductHuntToken()) return;
        var last = getProductHuntLastFetch();
        var stale = !last || (Date.now() - new Date(last).getTime()) > 24 * 3600 * 1000;
        if (!stale) return;
        var today = new Date().toDateString();
        if (localStorage.getItem(PH_AUTO_LAST_RUN_KEY) === today) return; // already tried today
        localStorage.setItem(PH_AUTO_LAST_RUN_KEY, today);
        fetchProductHunt();
    } catch (e) { }
}

function updateProductHuntUI() {
    var inp = document.getElementById('phTokenInput');
    if (inp && !inp.value && getProductHuntToken()) inp.placeholder = '•••••••• (saved)';
    var last = document.getElementById('phLastFetch');
    if (last) {
        var t = getProductHuntLastFetch();
        last.textContent = t ? 'Last fetch: ' + new Date(t).toLocaleString() : '';
    }
    var autoCb = document.getElementById('phAuto6am');
    if (autoCb) {
        try { autoCb.checked = localStorage.getItem(PH_AUTO_6AM_KEY) === 'true'; } catch (_) { }
    }
    var stats = document.getElementById('toolsStats');
    if (stats) stats.textContent = tools.length ? tools.length.toLocaleString() + ' tools' : '';
}

// Hide-duplicates toggle state (persisted)
let toolsHideDups = false;
const TOOLS_HIDE_DUPS_KEY = 'linkLumina_toolsHideDups';
try { toolsHideDups = localStorage.getItem(TOOLS_HIDE_DUPS_KEY) === 'true'; } catch (e) { }

function toggleToolsHideDups() {
    const cb = document.getElementById('toolsHideDups');
    toolsHideDups = !!(cb && cb.checked);
    try { localStorage.setItem(TOOLS_HIDE_DUPS_KEY, toolsHideDups ? 'true' : 'false'); } catch (e) { }
    updateToolsView();
}

// --- Filtering & rendering (card grid, batch + lazy images) -----------------

function getFilteredTools() {
    let arr = tools;
    if (toolsHideDups) arr = arr.filter(function (x) { return !x.dup; });
    const q = (document.getElementById('toolsSearch')?.value || '').trim().toLowerCase();
    if (q) {
        const qn = _toolNorm(q);
        arr = arr.filter(function (x) {
            const hay = _toolNorm([x.n, x.d, x.desc, (x.topics || []).join(' '), (x.tags || []).join(' '), x.cat, x.domain || _toolDomain(x.u)].join(' '));
            return hay.indexOf(qn) !== -1;
        });
    }
    const topic = document.getElementById('toolsTopicFilter')?.value || '';
    if (topic) {
        arr = arr.filter(function (x) {
            return (x.cat || '') === topic || (x.topics || []).some(function (t) { return t === topic; }) || (x.tags || []).indexOf(topic) !== -1;
        });
    }
    const sort = document.getElementById('toolsSort')?.value || 'newest';
    const sorted = arr.slice();
    if (sort === 'popular') sorted.sort(function (a, b) { return ((b.votes || 0) - (a.votes || 0)) || ((b.t || 0) - (a.t || 0)); });
    else if (sort === 'name') sorted.sort(function (a, b) { return (a.n || '').localeCompare(b.n || ''); });
    else sorted.sort(function (a, b) { return (b.t || 0) - (a.t || 0); });
    return sorted;
}

// Rebuild the topic/category filter dropdown from live tool data
function rebuildToolsTopicOptions() {
    const sel = document.getElementById('toolsTopicFilter');
    if (!sel) return;
    const counts = new Map();
    tools.forEach(function (x) {
        (x.topics || []).forEach(function (t) { counts.set(t, (counts.get(t) || 0) + 1); });
        if (x.cat) counts.set(x.cat, (counts.get(x.cat) || 0) + 1);
    });
    const entries = [...counts.entries()].sort(function (a, b) { return b[1] - a[1]; }).slice(0, 40);
    const cur = sel.value;
    let html = '<option value="">All topics</option>';
    entries.forEach(function (e) {
        html += '<option value="' + escapeHtml(e[0]) + '"' + (e[0] === cur ? ' selected' : '') + '>' + escapeHtml(e[0]) + ' (' + e[1] + ')</option>';
    });
    sel.innerHTML = html;
}

// --- Duplicate tools vs saved links UI --------------------------------------
function renderToolDupBadge() {
    const btn = document.getElementById('phDupBtn');
    if (btn) {
        const count = toolDupCache.size;
        btn.classList.toggle('hidden', count === 0);
        btn.querySelector('span').textContent = String(count);
    }
    const delBtn = document.getElementById('phDupDeleteBtn');
    if (delBtn) delBtn.classList.toggle('hidden', toolDupCache.size === 0);
}

function toggleToolDupList() {
    const list = document.getElementById('phDupList');
    if (!list) return;
    const willShow = list.classList.contains('hidden');
    list.classList.toggle('hidden');
    if (willShow) {
        let html = '<div class="flex items-center justify-between gap-2 mb-2">' +
            '<div class="text-xs text-gray-400 font-semibold">Tools matching a saved link:</div>' +
            '<div class="flex items-center gap-1.5">' +
            '<button type="button" id="phDupMergeAll" class="text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/30">Merge all into links</button>' +
            '<button type="button" id="phDupDeleteAll" class="text-[11px] px-2 py-0.5 rounded-full bg-red-500/15 border border-red-500/30 text-red-300 hover:bg-red-500/30">Delete all</button>' +
            '</div></div>';
        toolDupCache.forEach(function (info, id) {
            const t = tools.find(function (x) { return x.id === id; });
            html += '<div class="flex items-center gap-2 py-1 border-b border-white/5 last:border-0">' +
                '<span class="flex-1 min-w-0 truncate text-white text-xs" title="' + (t ? escapeHtml(t.n) : id) + '">' + (t ? escapeHtml(t.n) : id) + '</span>' +
                '<a href="' + escapeHtml(info.url) + '" target="_blank" rel="noopener" class="shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-red-500/15 border border-red-500/30 text-red-300 hover:bg-red-500/30">Open link</a>' +
                '<button type="button" class="dup-merge shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-emerald-500/15 border border-emerald-500/30 text-emerald-300 hover:bg-emerald-500/30" data-id="' + escapeHtml(id) + '">Merge</button>' +
                '<button type="button" class="dup-del shrink-0 text-[11px] px-2 py-0.5 rounded-full bg-white/5 border border-white/10 text-gray-300 hover:bg-red-500/30 hover:text-red-300" data-id="' + escapeHtml(id) + '">Delete</button>' +
                '</div>';
        });
        list.innerHTML = html;
        const mergeAll = list.querySelector('#phDupMergeAll');
        if (mergeAll) mergeAll.addEventListener('click', function () { mergeAllDupTools(); });
        const delAll = list.querySelector('#phDupDeleteAll');
        if (delAll) delAll.addEventListener('click', function () { deleteAllDupTools(); });
        list.querySelectorAll('.dup-merge').forEach(function (b) {
            b.addEventListener('click', function () { mergeDupToolIntoLink(b.getAttribute('data-id')); });
        });
        list.querySelectorAll('.dup-del').forEach(function (b) {
            b.addEventListener('click', function () { deleteDupTool(b.getAttribute('data-id')); });
        });
        if (window.lucide && window.lucide.createIcons) window.lucide.createIcons();
    }
}

// Delete one duplicate tool (from list + DB + cache) and refresh the UI
async function deleteDupTool(id) {
    if (!toolDupCache.has(id)) return;
    tools = tools.filter(function (x) { return x.id !== id; });
    window.tools = tools;
    toolDupCache.delete(id);
    if (window.deleteToolFromDB) await window.deleteToolFromDB(id);
    updateToolsView();
    renderToolDupBadge();
    if (window.showToast) window.showToast('Duplicate tool deleted.', 'success');
}

// Merge ONE duplicate tool into its matching saved link: enrich the link with
// the tool's description/image/tags/category, then remove the tool.
async function mergeDupToolIntoLink(id) {
    if (!toolDupCache.has(id)) return;
    const t = tools.find(function (x) { return x.id === id; });
    if (!t) return;
    const info = toolDupCache.get(id);
    // Locate the matching link (URL first, then domain)
    let link = (window.links || []).find(function (l) { return l.url === info.url; });
    if (!link && t.domain) {
        link = (window.links || []).find(function (l) {
            try { return new URL(l.url).hostname.replace(/^www\./, '').toLowerCase() === t.domain; } catch (e) { return false; }
        });
    }
    if (!link) {
        if (window.showToast) window.showToast('Could not find the matching link to merge into.', 'error');
        return;
    }
    const changed = {};
    if (!link.notes && (t.desc || t.d)) {
        link.notes = (t.desc || t.d).slice(0, 2000);
        changed.notes = true;
    }
    if (!link.image && t.img) { link.image = t.img; changed.image = true; }
    if (!link.category || link.category === 'General' || link.category === 'Other' || link.category === 'Uncategorized') {
        if (t.cat && t.cat !== 'Tools') { link.category = t.cat; changed.category = true; }
    }
    const extraTags = [];
    (t.tags || []).concat(t.topics || []).forEach(function (tag) {
        const tg = String(tag).toLowerCase().trim();
        if (tg && !(link.tags || []).includes(tg) && !extraTags.includes(tg)) extraTags.push(tg);
    });
    if (extraTags.length) {
        link.tags = (link.tags || []).concat(extraTags);
        changed.tags = true;
    }
    if (Object.keys(changed).length && window.saveLinkToDB) {
        await window.saveLinkToDB(link);
    }
    // Remove the tool now that it lives inside the link
    tools = tools.filter(function (x) { return x.id !== id; });
    window.tools = tools;
    toolDupCache.delete(id);
    if (window.deleteToolFromDB) await window.deleteToolFromDB(id);
    updateToolsView();
    renderToolDupBadge();
    if (typeof renderLinks === 'function') renderLinks();
    const merged = Object.keys(changed).length ? ' (description/image/tags merged)' : '';
    if (window.showToast) window.showToast('Merged "' + (t.n || 'tool') + '" into its saved link' + merged + '.', 'success');
}

// Merge ALL duplicate tools into their matching saved links.
async function mergeAllDupTools() {
    const ids = Array.from(toolDupCache.keys());
    if (!ids.length) return;
    let merged = 0;
    for (const id of ids.slice()) {
        try { await mergeDupToolIntoLink(id); merged++; } catch (e) { }
    }
    if (window.showToast) window.showToast('Merged ' + merged + ' duplicate tools into saved links. 🧬', 'success');
}

// Delete ALL duplicate tools (one tap after a PH fetch)
async function deleteAllDupTools() {
    const count = toolDupCache.size;
    if (!count) return;
    if (!confirm('Delete ' + count + ' tools that already exist as saved links?')) return;
    const ids = Array.from(toolDupCache.keys());
    const removed = [];
    for (const id of ids) {
        tools = tools.filter(function (x) { return x.id !== id; });
        removed.push(id);
        if (window.deleteToolFromDB) { try { await window.deleteToolFromDB(id); } catch (e) { } }
    }
    window.tools = tools;
    toolDupCache.clear();
    const list = document.getElementById('phDupList');
    if (list) list.classList.add('hidden');
    updateToolsView();
    renderToolDupBadge();
    if (window.showToast) window.showToast('Deleted ' + removed.length + ' duplicate tools. 🗑', 'success');
}

function openToolModal(editId) {
    toolsEditingId = editId || null;
    var title = document.getElementById('toolModalTitle');
    var nameInp = document.getElementById('toolName');
    var descInp = document.getElementById('toolDesc');
    var urlInp = document.getElementById('toolUrl');
    var imgInp = document.getElementById('toolImg');
    if (title) title.textContent = editId ? 'Edit tool' : 'Add tool';
    if (nameInp) nameInp.value = '';
    if (descInp) descInp.value = '';
    if (urlInp) urlInp.value = '';
    if (imgInp) imgInp.value = '';
    if (editId) {
        var t = tools.find(function (x) { return x.id === editId; });
        if (t) {
            if (nameInp) nameInp.value = t.n || '';
            if (descInp) descInp.value = t.d || '';
            if (urlInp) urlInp.value = t.u || '';
            if (imgInp) imgInp.value = t.img || '';
        }
    }
    document.getElementById('toolModal').classList.remove('hidden');
    if (window.initializeIcons) window.initializeIcons();
    setTimeout(function () { (nameInp || document.getElementById('toolName')).focus(); }, 100);
}

function closeToolModal() {
    toolsEditingId = null;
    document.getElementById('toolModal').classList.add('hidden');
}

function escapeHtml(s) {
    if (!s) return '';
    var div = document.createElement('div');
    div.textContent = s;
    return div.innerHTML;
}

function renderToolCard(x) {
    var n = escapeHtml((x.n || '').slice(0, 120));
    var desc = escapeHtml(((x.desc || x.d || '')).slice(0, 260));
    var u = (x.u || '').trim();
    var safeUrl = u.slice(0, 2000);
    var img = x.img || '';
    var topics = (x.topics || []).slice(0, 2);
    var votes = x.votes || 0;
    var phUrl = x.phUrl || '';
    var dom = escapeHtml((x.domain || _toolDomain(u)).slice(0, 60));
    var cat = x.cat || '';
    var tags = (x.tags && x.tags.length ? x.tags : topics).slice(0, 3);
    var catColor = (typeof getCategoryColor === 'function' && getCategoryColor(cat)) || '#f59e0b';

    var thumb = img
        ? '<img data-src="' + escapeHtml(img) + '" alt="' + n + '" loading="lazy" decoding="async" class="w-full h-full object-cover tool-img" onerror="this.closest(\'.tool-thumb\').classList.add(\'no-img\');this.remove()">'
        : '<div class="tool-thumb-fallback"><i data-lucide="package" class="w-8 h-8"></i></div>';

    // Note: duplicate tools are surfaced via the "Matches" badge + hide toggle,
    // not a badge on the card itself (keeps cards clean).
    var dupMark = x.dup ? ' tool-dup-item' : '';

    return '<div class="tool-card glass-card overflow-hidden rounded-xl border border-white/10 hover:border-red-500/40 hover:shadow-xl hover:shadow-red-500/10 transition-all duration-300 group flex flex-col' + dupMark + '">' +
        '<div class="tool-thumb relative h-28 overflow-hidden bg-gray-800/40 shrink-0">' + thumb +
        (votes ? '<span class="absolute top-2 left-2 z-10 flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full bg-black/60 backdrop-blur-md border border-white/10 text-amber-300"><i data-lucide="trending-up" class="w-3 h-3"></i> ' + votes + '</span>' : '') +
        (phUrl ? '<a href="' + escapeHtml(phUrl) + '" target="_blank" rel="noopener" class="absolute top-2 right-2 z-10 p-1.5 rounded-full bg-black/60 backdrop-blur-md text-orange-400 hover:bg-orange-500 hover:text-white transition-all" title="View on Product Hunt" onclick="event.stopPropagation()"><i data-lucide="flame" class="w-3.5 h-3.5"></i></a>' : '') +
        '</div>' +
        '<div class="p-3 flex flex-col flex-1 min-w-0">' +
        '<div class="flex items-center gap-2">' +
        '<span class="w-2 h-2 rounded-full shrink-0" style="background:' + catColor + '" title="' + escapeHtml(cat) + '"></span>' +
        '<h3 class="text-sm font-semibold text-white truncate" title="' + n + '">' + n + '</h3>' +
        '</div>' +
        '<p class="text-xs text-gray-400 line-clamp-2 mt-1 leading-relaxed min-h-[2rem]">' + desc + '</p>' +
        (tags.length ? '<div class="flex flex-wrap gap-1 mt-2">' + tags.map(function (t) { return '<span class="text-[10px] px-2 py-0.5 rounded-full bg-red-500/10 border border-red-500/20 text-red-300">' + escapeHtml(t) + '</span>'; }).join('') + '</div>' : '') +
        '<div class="mt-auto pt-2 flex items-center gap-1 border-t border-white/5 mt-2">' +
        '<span class="text-[10px] text-gray-500 truncate flex-1" title="' + dom + '">' + dom + '</span>' +
        '<a href="' + escapeHtml(safeUrl) + '" target="_blank" rel="noopener" class="shrink-0 p-1 rounded text-red-400 hover:bg-red-500/20" title="Open website"><i data-lucide="external-link" class="w-3.5 h-3.5"></i></a>' +
        '<button type="button" class="tools-edit shrink-0 p-1 rounded text-gray-400 hover:bg-white/10 hover:text-white" data-id="' + escapeHtml(x.id) + '" title="Edit"><i data-lucide="pencil" class="w-3.5 h-3.5"></i></button>' +
        '<button type="button" class="tools-delete shrink-0 p-1 rounded text-gray-400 hover:bg-red-500/20 hover:text-red-400" data-id="' + escapeHtml(x.id) + '" title="Delete"><i data-lucide="trash-2" class="w-3.5 h-3.5"></i></button>' +
        '</div></div></div>';
}

function renderToolsBatch() {
    if (toolsBatchInFlight) return;
    toolsBatchInFlight = true;
    requestAnimationFrame(function () {
        toolsBatchInFlight = false;
        var grid = document.getElementById('toolsGrid');
        if (!grid) return;
        var end = Math.min(toolsRenderedCount + TOOLS_BATCH_SIZE, toolsFiltered.length);
        var html = '';
        for (var i = toolsRenderedCount; i < end; i++) html += renderToolCard(toolsFiltered[i]);
        // Parse off-DOM and scope icon init to ONLY the new nodes — avoids
        // re-scanning every already-rendered card (O(n^2) as cards accumulate).
        var holder = document.createElement('div');
        holder.innerHTML = html;
        var newIcons = Array.from(holder.querySelectorAll('[data-lucide]'));
        while (holder.firstChild) grid.appendChild(holder.firstChild);
        toolsRenderedCount = end;
        if (newIcons.length && window.lucide && window.lucide.createIcons) {
            window.lucide.createIcons({ nodes: newIcons });
        }
        observeToolsImages(grid);
        updateToolsSentinel();
    });
}

function updateToolsSentinel() {
    var sentinel = document.getElementById('toolsSentinel');
    if (!sentinel) return;
    if (toolsRenderedCount < toolsFiltered.length) {
        sentinel.classList.remove('hidden');
        if (!toolsSentinelObserver && toolsListEl && 'IntersectionObserver' in window) {
            toolsSentinelObserver = new IntersectionObserver(function (entries) {
                if (entries.some(function (e) { return e.isIntersecting; })) renderToolsBatch();
            }, { root: toolsListEl, rootMargin: '500px' });
        }
        if (toolsSentinelObserver) toolsSentinelObserver.observe(sentinel);
    } else {
        sentinel.classList.add('hidden');
        if (toolsSentinelObserver) { toolsSentinelObserver.disconnect(); toolsSentinelObserver = null; }
    }
}

function observeToolsImages(grid) {
    if (!grid) return;
    var imgs = grid.querySelectorAll('img[data-src]');
    if (!imgs.length) return;
    if (!('IntersectionObserver' in window)) {
        imgs.forEach(function (img) { img.src = img.dataset.src; img.removeAttribute('data-src'); });
        return;
    }
    if (!toolsImgObserver) {
        toolsImgObserver = new IntersectionObserver(function (entries) {
            entries.forEach(function (e) {
                if (e.isIntersecting) {
                    var img = e.target;
                    if (img.dataset.src) { img.src = img.dataset.src; img.removeAttribute('data-src'); }
                    toolsImgObserver.unobserve(img);
                }
            });
        }, { rootMargin: '300px' });
    }
    imgs.forEach(function (img) { toolsImgObserver.observe(img); });
}

function updateToolsView() {
    rebuildToolsTopicOptions();
    if (typeof renderCategoryFilters === 'function') renderCategoryFilters();
    toolsFiltered = getFilteredTools();
    var container = document.getElementById('toolsListContainer');
    var emptyEl = document.getElementById('toolsEmpty');
    var grid = document.getElementById('toolsGrid');
    if (!container || !grid) return;

    if (toolsFiltered.length === 0) {
        if (emptyEl) emptyEl.classList.remove('hidden');
        grid.innerHTML = '';
        container.style.display = 'none';
        toolsRenderedCount = 0;
        return;
    }
    if (emptyEl) emptyEl.classList.add('hidden');
    container.style.display = '';
    toolsRenderedCount = 0;
    grid.innerHTML = '';
    renderToolsBatch();
    updateProductHuntUI();
}

async function loadTools() {
    if (!window.db || !window.getAllToolsFromDB) return;
    tools = await window.getAllToolsFromDB();
    if (!Array.isArray(tools)) tools = [];
    tools.sort(function (a, b) { return (b.t || 0) - (a.t || 0); });
    window.tools = tools;
    toolsLoaded = true;
    // Rebuild the duplicate index against saved links so the "Matches" count
    // and the "Hide duplicates" toggle work correctly after a reload.
    const dupIndex = _buildLinkDupIndex();
    tools.forEach(function (x) { checkToolDup(x, dupIndex); });
    // Merge tool categories into the shared category filter
    if (typeof renderCategoryFilters === 'function') renderCategoryFilters();
}

function renderToolsTab() {
    var container = document.getElementById('toolsListContainer');
    if (!container) return;
    toolsListEl = container;
    if (!toolsLoaded) {
        loadTools().then(function () { renderToolsTab(); });
        return;
    }
    updateToolsView();
    updateProductHuntUI();
}

async function saveToolFromModal() {
    var nameInp = document.getElementById('toolName');
    var descInp = document.getElementById('toolDesc');
    var urlInp = document.getElementById('toolUrl');
    var imgInp = document.getElementById('toolImg');
    var n = (nameInp && nameInp.value.trim()) || '';
    var d = (descInp && descInp.value.trim()) || '';
    var u = (urlInp && urlInp.value.trim()) || '';
    var img = (imgInp && imgInp.value.trim()) || '';
    if (!n || !u) {
        if (window.showToast) window.showToast('Enter a name and link.', 'warning');
        return;
    }
    var id = toolsEditingId || (Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8));
    var item = {
        id: id, n: n.slice(0, 120), d: d.slice(0, 240),
        desc: d.slice(0, 1200), u: u.slice(0, 2048),
        img: img.slice(0, 2048), t: Date.now(),
        domain: _toolDomain(u)
    };
    var auto = autoCategorizeTool(item);
    item.cat = auto.cat;
    item.tags = auto.tags;
    checkToolDup(item);
    if (toolsEditingId) {
        var idx = tools.findIndex(function (x) { return x.id === toolsEditingId; });
        if (idx !== -1) tools[idx] = item;
    } else {
        tools.unshift(item);
    }
    if (window.saveToolToDB) await window.saveToolToDB(item);
    closeToolModal();
    if (window.showToast) window.showToast(item.dup ? 'Tool saved. ⚠ It matches a saved link.' : 'Tool saved.', item.dup ? 'warning' : 'success');
    updateToolsView();
    renderToolDupBadge();
    if (window.initializeIcons) window.initializeIcons();
}

async function deleteTool(id) {
    tools = tools.filter(function (x) { return x.id !== id; });
    window.tools = tools;
    if (window.deleteToolFromDB) await window.deleteToolFromDB(id);
    if (window.showToast) window.showToast('Tool deleted.', 'success');
    updateToolsView();
    renderToolDupBadge();
}

function setupToolsTab() {
    document.getElementById('addToolBtn')?.addEventListener('click', function () { openToolModal(); });
    document.getElementById('closeToolModal')?.addEventListener('click', closeToolModal);
    document.getElementById('cancelToolBtn')?.addEventListener('click', closeToolModal);
    document.getElementById('saveToolBtn')?.addEventListener('click', function () { saveToolFromModal(); });
    document.getElementById('toolModal')?.addEventListener('click', function (e) {
        if (e.target.id === 'toolModal') closeToolModal();
    });
    document.getElementById('toolsSearch')?.addEventListener('input', function () { updateToolsView(); });
    document.getElementById('toolsSearch')?.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') { this.value = ''; updateToolsView(); }
    });
    document.getElementById('toolsTopicFilter')?.addEventListener('change', function () { updateToolsView(); });
    document.getElementById('toolsSort')?.addEventListener('change', function () { updateToolsView(); });

    // Delegate card actions (edit/delete) on the grid container
    var grid = document.getElementById('toolsGrid');
    if (grid) {
        grid.addEventListener('click', function (e) {
            var edit = e.target.closest('.tools-edit');
            var del = e.target.closest('.tools-delete');
            if (edit) { e.stopPropagation(); openToolModal(edit.getAttribute('data-id')); }
            else if (del) { e.stopPropagation(); if (confirm('Delete this tool?')) deleteTool(del.getAttribute('data-id')); }
        });
    }
    var phToggle = document.getElementById('phPanelToggle');
    var phBody = document.getElementById('phPanelBody');
    var phChevron = document.getElementById('phPanelChevron');
    if (phToggle && phBody) {
        phToggle.addEventListener('click', function () {
            const open = phBody.classList.toggle('hidden');
            if (phChevron) phChevron.classList.toggle('rotate-180', !open);
        });
    }
    var dupBtn = document.getElementById('phDupBtn');
    if (dupBtn) dupBtn.addEventListener('click', function () { toggleToolDupList(); });
    var dupDelBtn = document.getElementById('phDupDeleteBtn');
    if (dupDelBtn) dupDelBtn.addEventListener('click', function () { deleteAllDupTools(); });
    var hideDupsCb = document.getElementById('toolsHideDups');
    if (hideDupsCb) {
        hideDupsCb.checked = toolsHideDups;
        hideDupsCb.addEventListener('change', toggleToolsHideDups);
    }

    document.getElementById('phTokenInput')?.addEventListener('blur', function () {
        var v = (this.value || '').trim();
        if (v) setProductHuntToken(v);
    });
    document.getElementById('phFetchBtn')?.addEventListener('click', function () { fetchProductHunt(); });
    document.getElementById('phDeepBtn')?.addEventListener('click', function () {
        if (getProductHuntToken() || document.getElementById('phTokenInput')?.value.trim()) {
            fetchProductHunt({ deep: true });
        } else if (window.showToast) {
            window.showToast('Enter a Product Hunt API token before deep scanning.', 'warning');
        }
    });
    var autoCb = document.getElementById('phAuto6am');
    if (autoCb) {
        autoCb.addEventListener('change', function () {
            try { localStorage.setItem(PH_AUTO_6AM_KEY, this.checked ? 'true' : 'false'); } catch (_) { }
            if (window.showToast) window.showToast(this.checked ? 'Enabled: auto-update Product Hunt daily (24h).' : 'Disabled auto-update.', 'info');
        });
        try { autoCb.checked = localStorage.getItem(PH_AUTO_6AM_KEY) === 'true'; } catch (_) { }
    }
    setInterval(runAutoDailyIfNeeded, 3600000);
    runAutoDailyIfNeeded();
}

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', setupToolsTab);
} else {
    setupToolsTab();
}

window.tools = tools;
window.renderToolsTab = renderToolsTab;
window.openToolModal = openToolModal;
window.loadTools = loadTools;
window.fetchProductHunt = fetchProductHunt;
window.updateProductHuntUI = updateProductHuntUI;
window.updateToolsView = updateToolsView;
window.toggleToolDupList = toggleToolDupList;
window.renderToolDupBadge = renderToolDupBadge;
window.deleteAllDupTools = deleteAllDupTools;
window.deleteDupTool = deleteDupTool;
window.mergeDupToolIntoLink = mergeDupToolIntoLink;
window.mergeAllDupTools = mergeAllDupTools;
window.toggleToolsHideDups = toggleToolsHideDups;
window.autoCategorizeTool = autoCategorizeTool;
