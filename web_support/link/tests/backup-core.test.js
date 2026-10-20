'use strict';
const { test } = require('node:test');
const assert = require('node:assert');
const BC = require('../backup-core.js');

test('safeFilename sanitizes and truncates', () => {
    assert.strictEqual(BC.safeFilename('My Link! @#'), 'My_Link_');
    assert.strictEqual(BC.safeFilename(''), 'item');
    assert.strictEqual(BC.safeFilename(null), 'item');
    const long = 'a'.repeat(100);
    assert.strictEqual(BC.safeFilename(long).length, 60);
});

test('imageExt detects extension by URL path', () => {
    assert.strictEqual(BC.imageExt('https://x.com/a.png'), 'png');
    assert.strictEqual(BC.imageExt('https://x.com/a.webp'), 'webp');
    assert.strictEqual(BC.imageExt('https://x.com/a.gif'), 'gif');
    assert.strictEqual(BC.imageExt('https://x.com/a.svg'), 'svg');
    assert.strictEqual(BC.imageExt('https://x.com/a.avif'), 'avif');
    assert.strictEqual(BC.imageExt('https://x.com/a.jpg'), 'jpg');
    assert.strictEqual(BC.imageExt('https://x.com/noext?w=1'), 'jpg');
    assert.strictEqual(BC.imageExt('data:image/png;base64,xxx'), 'jpg'); // no pathname
});

test('mimeFromExt maps by name', () => {
    assert.strictEqual(BC.mimeFromExt('images/links/a.png'), 'image/png');
    assert.strictEqual(BC.mimeFromExt('images/links/a.webp'), 'image/webp');
    assert.strictEqual(BC.mimeFromExt('images/links/a.GIF'), 'image/gif');
    assert.strictEqual(BC.mimeFromExt('images/links/a.svg'), 'image/svg+xml');
    assert.strictEqual(BC.mimeFromExt('images/links/a.avif'), 'image/avif');
    assert.strictEqual(BC.mimeFromExt('images/links/a.jpg'), 'image/jpeg');
    assert.strictEqual(BC.mimeFromExt('noext'), 'image/jpeg');
});

test('weservUrl encodes the original URL', () => {
    const u = BC.weservUrl('https://example.com/a b.png');
    assert.ok(u.startsWith('https://images.weserv.nl/?url='));
    assert.ok(u.includes(encodeURIComponent('https://example.com/a b.png')));
});

test('tryDownloadImage returns blob on direct fetch success', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = async (url) => ({ ok: true, blob: async () => new Blob(['img']) });
    try {
        const blob = await BC.tryDownloadImage('https://example.com/a.jpg', 2000);
        assert.ok(blob instanceof Blob);
        assert.strictEqual(blob.size, 3);
    } finally {
        globalThis.fetch = origFetch;
    }
});

test('tryDownloadImage falls back to weserv proxy when direct fetch fails', async () => {
    const calls = [];
    const origFetch = globalThis.fetch;
    globalThis.fetch = async (url) => {
        calls.push(String(url));
        if (String(url).startsWith('https://images.weserv.nl/')) {
            return { ok: true, blob: async () => new Blob(['proxied']) };
        }
        return { ok: false, blob: async () => new Blob([]) };
    };
    try {
        const blob = await BC.tryDownloadImage('https://example.com/blocked.jpg', 2000);
        assert.ok(blob instanceof Blob);
        assert.strictEqual(blob.size, 7); // "proxied"
        assert.strictEqual(calls.length, 2, 'direct + proxy retry');
        assert.ok(calls[1].includes('images.weserv.nl'));
    } finally {
        globalThis.fetch = origFetch;
    }
});

test('tryDownloadImage returns null when both direct and proxy fail', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = async () => ({ ok: false, blob: async () => new Blob([]) });
    try {
        const blob = await BC.tryDownloadImage('https://example.com/nope.jpg', 2000);
        assert.strictEqual(blob, null);
    } finally {
        globalThis.fetch = origFetch;
    }
});

test('tryDownloadImage handles data: URLs directly', async () => {
    const origFetch = globalThis.fetch;
    globalThis.fetch = async (url) => ({ ok: true, blob: async () => new Blob(['d']) });
    try {
        const blob = await BC.tryDownloadImage('data:image/png;base64,AAAA', 2000);
        assert.ok(blob instanceof Blob);
    } finally {
        globalThis.fetch = origFetch;
    }
});

test('tryDownloadImage skips proxy when useProxy:false', async () => {
    const calls = [];
    const origFetch = globalThis.fetch;
    globalThis.fetch = async (url) => { calls.push(String(url)); return { ok: false, blob: async () => new Blob([]) }; };
    try {
        const blob = await BC.tryDownloadImage('https://example.com/x.jpg', 2000, { useProxy: false });
        assert.strictEqual(blob, null);
        assert.strictEqual(calls.length, 1);
    } finally {
        globalThis.fetch = origFetch;
    }
});

test('tryDownloadImage returns null for empty url', async () => {
    const blob = await BC.tryDownloadImage('', 2000);
    assert.strictEqual(blob, null);
});
