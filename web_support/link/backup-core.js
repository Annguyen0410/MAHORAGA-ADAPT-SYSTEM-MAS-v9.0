/* ==================== LinkLumina BACKUP CORE ====================
   Pure helpers for ZIP folder backup — UMD (browser + Node tests).

   Includes a CORS fallback: when a remote image cannot be fetched
   cross-origin, retry through the images.weserv.nl proxy which
   re-serves the image server-side (bypasses CORS).
======================================================================== */
(function (root, factory) {
    if (typeof module === 'object' && module.exports) module.exports = factory();
    else root.BackupCore = factory();
})(typeof self !== 'undefined' ? self : this, function () {
    'use strict';

    function safeFilename(name) {
        return String(name || 'item').replace(/[^\w\-.]+/g, '_').slice(0, 60);
    }

    function imageExt(url) {
        try {
            const p = (new URL(url).pathname || '').toLowerCase();
            if (p.endsWith('.png')) return 'png';
            if (p.endsWith('.webp')) return 'webp';
            if (p.endsWith('.gif')) return 'gif';
            if (p.endsWith('.svg')) return 'svg';
            if (p.endsWith('.avif')) return 'avif';
        } catch (e) { }
        return 'jpg';
    }

    // MIME type by file name (used when restoring images from a ZIP as dataURL).
    function mimeFromExt(name) {
        const lower = String(name || '').toLowerCase();
        if (lower.endsWith('.png')) return 'image/png';
        if (lower.endsWith('.webp')) return 'image/webp';
        if (lower.endsWith('.gif')) return 'image/gif';
        if (lower.endsWith('.svg')) return 'image/svg+xml';
        if (lower.endsWith('.avif')) return 'image/avif';
        return 'image/jpeg';
    }

    // weserv proxy URL — re-serves any public image, bypassing CORS.
    function weservUrl(url) {
        return 'https://images.weserv.nl/?url=' + encodeURIComponent(url);
    }

    async function _fetchBlob(url, timeoutMs) {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), timeoutMs || 8000);
        try {
            const res = await fetch(url, { mode: 'cors', signal: ctrl.signal });
            if (!res.ok) return null;
            const blob = await res.blob();
            return blob && blob.size > 0 ? blob : null;
        } catch (e) {
            return null;
        } finally {
            clearTimeout(t);
        }
    }

    // Downloads an image, falling back to the weserv proxy on CORS/network failure.
    // Returns a Blob or null. options.useProxy defaults to true.
    async function tryDownloadImage(url, timeoutMs, options) {
        try {
            if (!url) return null;
            if (url.startsWith('data:')) {
                const res = await fetch(url);
                return res.ok ? await res.blob() : null;
            }
            const opts = options || {};
            const direct = await _fetchBlob(url, timeoutMs);
            if (direct) return direct;
            if (opts.useProxy === false) return null;
            // CORS / network failed → retry through server-side proxy
            return _fetchBlob(weservUrl(url), timeoutMs || 12000);
        } catch (e) {
            return null;
        }
    }

    return { safeFilename, imageExt, mimeFromExt, weservUrl, tryDownloadImage };
});
