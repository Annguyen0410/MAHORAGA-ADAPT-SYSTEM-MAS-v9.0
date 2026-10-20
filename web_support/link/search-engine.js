/* ==================== LinkLumina SEARCH ENGINE ====================
   Pure, dependency-free, UMD — runs in the browser (window.SearchEngine)
   and in Node tests (module.exports).

   Accent-insensitive (Vietnamese), operator-aware, relevance-scored,
   built for 5000+ links.

   Operators: tag: / #tag, cat: / @cat, folder:, domain:, from:, to:,
              fav:, read:, pinned:, visits:>N, title:, url:, notes:,
              "exact phrase", -exclude. Words are ANDed; Vietnamese
              diacritics are stripped so "ca phe" finds "Cà phê".
======================================================================== */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.SearchEngine = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    const DIACRITICS_RE = /[\u0300-\u036f]/g;

    function normalizeText(s) {
        const str = (s || '').toString().toLowerCase();
        try {
            return str.normalize('NFD').replace(DIACRITICS_RE, '').replace(/\s+/g, ' ').trim();
        } catch (e) {
            return str.replace(/\s+/g, ' ').trim();
        }
    }

    // One normalized haystack per link, rebuilt only when data changes.
    // folders: array of { id, name } — used for folder: operator matching.
    function buildIndex(links, folders) {
        const idx = new Map();
        let folderNameMap = new Map();
        try {
            (folders || []).forEach(f => folderNameMap.set(f.id, normalizeText(f.name)));
        } catch (e) { folderNameMap = new Map(); }
        for (const link of (links || [])) {
            const title = normalizeText(link.title);
            const url = normalizeText(link.url);
            const notes = normalizeText(link.notes || link.description);
            const tags = normalizeText((link.tags || []).join(' '));
            let domain = '';
            try { domain = new URL(link.url).hostname.replace(/^www\./, '').toLowerCase(); } catch (e) { }
            const folderName = folderNameMap.get(link.folderId) || '';
            const hay = [title, url, notes, tags, normalizeText(link.category), folderName, domain]
                .filter(Boolean).join(' ');
            idx.set(link.id, { hay, title, url, notes, tags, domain });
        }
        return idx;
    }

    function _parseVisits(val) {
        const m = val.match(/^([<>]=?|=)?(\d+)$/);
        if (!m) return null;
        return { op: m[1] || '=', n: parseInt(m[2], 10) };
    }

    function parseQuery(raw) {
        const q = {
            words: [], excludeWords: [], phrases: [],
            highlightTerms: [],
            tag: '', category: '', folder: '', domain: '',
            titleWord: '', urlWord: '', notesWord: '',
            from: null, to: null,
            fav: null, read: null, pinned: null,
            visits: null,
            hasConstraints: false,
            raw: (raw || '').trim()
        };
        const input = q.raw;
        if (!input) return q;

        // Quoted phrases first
        let remainder = input.replace(/"([^"]+)"/g, (m, p) => {
            const np = normalizeText(p);
            if (np) { q.phrases.push(np); q.highlightTerms.push(p.toLowerCase()); q.hasConstraints = true; }
            return ' ';
        });

        for (const tokRaw of remainder.split(/\s+/).filter(Boolean)) {
            let neg = false;
            let tok = tokRaw;
            if (tok.startsWith('-') && tok.length > 1) { neg = true; tok = tok.slice(1); }
            const lower = tok.toLowerCase();
            const colon = lower.indexOf(':');
            if (colon > 0) {
                const key = lower.slice(0, colon).trim();
                let val = tok.slice(colon + 1).trim();
                if (!val) continue;
                q.hasConstraints = true;
                const negateStr = (fn) => { if (neg) { q.excludeWords.push(normalizeText(val)); } else fn(); };
                const pushHl = () => q.highlightTerms.push(val.toLowerCase());
                switch (key) {
                    case 'tag': case 'tags': negateStr(() => { q.tag = normalizeText(val); }); pushHl(); break;
                    case 'cat': case 'category': negateStr(() => { q.category = normalizeText(val); }); pushHl(); break;
                    case 'folder': negateStr(() => { q.folder = normalizeText(val); }); pushHl(); break;
                    case 'domain': negateStr(() => { q.domain = val.toLowerCase(); }); pushHl(); break;
                    case 'title': negateStr(() => { q.titleWord = normalizeText(val); }); pushHl(); break;
                    case 'url': negateStr(() => { q.urlWord = normalizeText(val); }); pushHl(); break;
                    case 'notes': negateStr(() => { q.notesWord = normalizeText(val); }); pushHl(); break;
                    case 'fav': case 'favorite': {
                        const b = val === 'true' || val === '1' || val === 'yes';
                        q.fav = neg ? !b : b;
                        break;
                    }
                    case 'read': case 'isread': {
                        const b = val === 'true' || val === '1' || val === 'yes';
                        q.read = neg ? !b : b;
                        break;
                    }
                    case 'pinned': {
                        const b = val === 'true' || val === '1' || val === 'yes';
                        q.pinned = neg ? !b : b;
                        break;
                    }
                    case 'from': { const d = new Date(val); if (!isNaN(d.getTime())) { d.setHours(0, 0, 0, 0); q.from = d; } break; }
                    case 'to': { const d = new Date(val); if (!isNaN(d.getTime())) { d.setHours(23, 59, 59, 999); q.to = d; } break; }
                    case 'visits': { const v = _parseVisits(val); if (v) q.visits = v; break; }
                    default:
                        (neg ? q.excludeWords : q.words).push(normalizeText(tokRaw));
                }
                continue;
            }
            if (lower.startsWith('#')) { q.tag = normalizeText(lower.slice(1)); q.hasConstraints = true; q.highlightTerms.push(lower.slice(1)); continue; }
            if (lower.startsWith('@')) { q.category = normalizeText(lower.slice(1)); q.hasConstraints = true; q.highlightTerms.push(lower.slice(1)); continue; }
            if (neg) { q.excludeWords.push(normalizeText(tok)); q.hasConstraints = true; }
            else { q.words.push(normalizeText(tok)); q.highlightTerms.push(lower); }
        }
        return q;
    }

    // Returns a relevance score (>0 matches, 0 = excluded).
    // index: Map built by buildIndex().
    function score(link, q, index) {
        const entry = index.get(link.id);
        if (!entry) return 0;

        // Cheap boolean / numeric filters
        if (q.fav !== null && !!link.favorite !== q.fav) return 0;
        if (q.read !== null && !!link.isRead !== q.read) return 0;
        if (q.pinned !== null && !!link.pinned !== q.pinned) return 0;
        if (q.visits) {
            const v = link.visitCount || 0;
            const { op, n } = q.visits;
            const ok = op === '>' ? v > n : op === '<' ? v < n : op === '>=' ? v >= n : op === '<=' ? v <= n : v === n;
            if (!ok) return 0;
        }
        if (q.from) { const d = link.createdAt ? new Date(link.createdAt) : null; if (!d || isNaN(d.getTime()) || d < q.from) return 0; }
        if (q.to) { const d = link.createdAt ? new Date(link.createdAt) : null; if (!d || isNaN(d.getTime()) || d > q.to) return 0; }
        if (q.category && entry.hay.indexOf(q.category) === -1) return 0;
        if (q.folder && entry.hay.indexOf(q.folder) === -1) return 0;
        if (q.domain && entry.domain.indexOf(q.domain) === -1) return 0;
        if (q.tag) {
            const found = entry.tags.split(' ').some(t => t === q.tag || t.indexOf(q.tag) !== -1);
            if (!found) return 0;
        }
        if (q.titleWord && entry.title.indexOf(q.titleWord) === -1) return 0;
        if (q.urlWord && entry.url.indexOf(q.urlWord) === -1) return 0;
        if (q.notesWord && entry.notes.indexOf(q.notesWord) === -1) return 0;

        // Free words: AND match, weighted by where they hit
        let scoreVal = 0;
        for (const w of q.words) {
            let s = 0;
            if (entry.title.indexOf(w) !== -1) s = 50;
            else if (entry.tags.indexOf(w) !== -1) s = 30;
            else if (entry.domain.indexOf(w) !== -1) s = 20;
            else if (entry.url.indexOf(w) !== -1) s = 15;
            else if (entry.notes.indexOf(w) !== -1) s = 5;
            else if (entry.hay.indexOf(w) === -1) return 0;
            else s = 2;
            scoreVal += s;
        }
        for (const w of q.excludeWords) {
            if (entry.hay.indexOf(w) !== -1) return 0;
        }
        for (const p of q.phrases) {
            if (entry.hay.indexOf(p) === -1) return 0;
            scoreVal += 20;
        }
        if (link.pinned) scoreVal += 3;
        if (link.favorite) scoreVal += 2;
        // Filter-only match (no free words) is still a match: return a small
        // baseline so callers can tell "matched" from "excluded" (score === 0).
        // e.g. searching "tag:react" must return every link tagged react.
        if (scoreVal === 0) return 1;
        return scoreVal;
    }

    // Escape + wrap matched substrings in <mark class="search-hit">.
    // Accent-insensitive: matches are found on a normalized copy (diacritics stripped),
    // then mapped back to original indices so the raw text (with accents) highlights correctly.
    // escapeHtml: function(string) -> string (DOM escaping hook, browser provides it).
    function highlight(rawText, terms, escapeHtml) {
        if (!rawText || !terms || !terms.length) return escapeHtml ? escapeHtml(rawText) : String(rawText);
        // Build normalized copy with an index map back to the raw string
        let norm = '';
        const map = [];
        let i = 0;
        while (i < rawText.length) {
            const cp = rawText.codePointAt(i);
            const ch = String.fromCodePoint(cp);
            const base = ch.toLowerCase().normalize('NFD').replace(DIACRITICS_RE, '');
            if (base) { map.push(i); norm += base; }
            i += ch.length;
        }
        const ranges = [];
        for (const rawTerm of terms) {
            const t = normalizeText(rawTerm);
            if (!t) continue;
            let idx = norm.indexOf(t);
            while (idx !== -1) {
                const s = map[idx];
                const lastRaw = map[idx + t.length - 1];
                const e = lastRaw + (String.fromCodePoint(rawText.codePointAt(lastRaw)).length || 1);
                ranges.push([s, e]);
                idx = norm.indexOf(t, idx + 1);
            }
        }
        if (!ranges.length) return escapeHtml ? escapeHtml(rawText) : String(rawText);
        ranges.sort((a, b) => a[0] - b[0]);
        const merged = [];
        for (const r of ranges) {
            const last = merged[merged.length - 1];
            if (last && r[0] <= last[1]) last[1] = Math.max(last[1], r[1]);
            else merged.push([r[0], r[1]]);
        }
        const esc = escapeHtml || ((s) => String(s));
        let out = '', pos = 0;
        for (const [s, e] of merged) {
            out += esc(rawText.slice(pos, s));
            out += '<mark class="search-hit">' + esc(rawText.slice(s, e)) + '</mark>';
            pos = e;
        }
        out += esc(rawText.slice(pos));
        return out;
    }

    return { normalizeText, parseQuery, buildIndex, score, highlight };
});
