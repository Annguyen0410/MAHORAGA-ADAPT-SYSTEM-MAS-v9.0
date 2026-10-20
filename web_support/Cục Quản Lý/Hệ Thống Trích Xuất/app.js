(function () {
    var BACKUP_KEYS = [
        'an_nguyen_storage_system_v1',
        'an_nguyen_storage_summary_v1',
        'an_nguyen_visualgraph_v1',
        'an_nguyen_visualgraph_summary_v1'
    ];

    function safeParse(key, fallback) {
        try {
            var parsed = JSON.parse(localStorage.getItem(key));
            if (Array.isArray(fallback)) return Array.isArray(parsed) ? parsed.filter(function (item) { return item && typeof item === 'object' && !Array.isArray(item); }) : fallback;
            return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : fallback;
        } catch (error) { return fallback; }
    }

    // Cache parsed dataset so select/export events don't re-parse localStorage every time.
    var dataCache = null;
    var previewCache = null;

    function collectData(options) {
        if (options && options.force === false && dataCache) return dataCache;
        var storageSummary = safeParse('an_nguyen_storage_summary_v1', {
            limitBytes: 10 * 1024 * 1024 * 1024,
            usedBytes: 0,
            remainingBytes: 10 * 1024 * 1024 * 1024,
            count: 0,
            categoryBreakdown: {}
        });
        var storageFiles = safeParse('an_nguyen_storage_system_v1', []).filter(function (file) { return typeof file.name === 'string'; });
        var usedBytes = storageFiles.reduce(function (sum, file) { var size = Number(file.size); return sum + (Number.isFinite(size) && size >= 0 ? size : 0); }, 0);
        storageSummary = Object.assign({}, storageSummary, { count: storageFiles.length, usedBytes: usedBytes, remainingBytes: Math.max(0, 10 * 1024 * 1024 * 1024 - usedBytes) });
        var visualSummary = safeParse('an_nguyen_visualgraph_summary_v1', {
            title: 'None yet',
            nodeCount: 0,
            edgeCount: 0,
            keywordCount: 0,
            summary: 'No data yet'
        });
        var visualTopics = safeParse('an_nguyen_visualgraph_v1', []).filter(function (topic) { return typeof topic.title === 'string'; }).map(function (topic) {
            return Object.assign({}, topic, { keywords: Array.isArray(topic.keywords) ? topic.keywords.filter(function (word) { return typeof word === 'string'; }) : [], nodes: Array.isArray(topic.nodes) ? topic.nodes : [], edges: Array.isArray(topic.edges) ? topic.edges : [] });
        });
        if (!visualTopics.some(function (topic) { return topic.id === visualSummary.activeId; })) {
            var latest = visualTopics[visualTopics.length - 1];
            visualSummary = latest ? { title: latest.title, summary: latest.summary, nodeCount: latest.nodes.length, edgeCount: latest.edges.length, keywordCount: latest.keywords.length } : { title: 'None yet', summary: 'No data yet', nodeCount: 0, edgeCount: 0, keywordCount: 0 };
        }

        var result = {
            exportedAt: new Date().toISOString(),
            energy: {
                name: 'Energy Analysis',
                status: 'online_only',
                path: 'https://personalfrequencys.netlify.app',
                note: 'The energy app is linked online from Management Hub; no local energy dataset is included.'
            },
            storage: {
                summary: storageSummary,
                files: storageFiles
            },
            visualgraph: {
                summary: visualSummary,
                topics: visualTopics
            }
        };

        dataCache = result;
        return result;
    }

    function forceRefreshData() {
        dataCache = null;
        previewCache = null;
        return collectData({ force: false });
    }

    function collectBackupPayload() {
        var storage = {};
        BACKUP_KEYS.forEach(function (key) {
            storage[key] = localStorage.getItem(key);
        });
        return {
            schema: 'cuc-quan-ly-backup-v1',
            exportedAt: new Date().toISOString(),
            source: 'Export Studio',
            keys: BACKUP_KEYS.slice(),
            payload: storage
        };
    }

    function pickScope(data, scope) {
        if (scope === 'all') return data;
        return { exportedAt: data.exportedAt, scope: scope, payload: data[scope] };
    }

    function buildExportObject(data, mode) {
        // Scoped records do not carry the other systems. Keep the same scope
        // contract for every format and report mode instead of dereferencing them.
        if (data.scope) {
            var payload = data.payload;
            if (mode === 'summary' && data.scope !== 'energy') payload = payload.summary;
            if (mode === 'audit' && data.scope === 'storage') {
                payload = { categories: payload.summary.categoryBreakdown || {}, files: payload.files.map(function (file) {
                    return { name: file.name, category: file.category, size: file.size, uploadedAt: file.uploadedAt };
                }) };
            }
            if (mode === 'audit' && data.scope === 'visualgraph') {
                payload = { topics: payload.topics.map(function (topic) {
                    return { title: topic.title, type: topic.type, keywords: (topic.keywords || []).length, nodes: (topic.nodes || []).length, edges: (topic.edges || []).length };
                }) };
            }
            return { exportedAt: data.exportedAt, scope: data.scope, mode: mode, payload: payload };
        }
        if (mode === 'summary') {
            return {
                exportedAt: data.exportedAt,
                executiveSummary: {
                    energy: data.energy.status,
                    storageFiles: data.storage.summary.count,
                    storageUsedBytes: data.storage.summary.usedBytes,
                    visualTopics: data.visualgraph.topics.length,
                    visualHeadline: data.visualgraph.summary.summary || data.visualgraph.summary.title
                }
            };
        }
        if (mode === 'audit') {
            return {
                exportedAt: data.exportedAt,
                audit: {
                    storageCategories: data.storage.summary.categoryBreakdown || {},
                    storageFiles: data.storage.files.map(function (file) {
                        return { name: file.name, category: file.category, size: file.size, uploadedAt: file.uploadedAt };
                    }),
                    visualTopics: data.visualgraph.topics.map(function (topic) {
                        return { title: topic.title, type: topic.type, keywords: (topic.keywords || []).length, nodes: (topic.nodes || []).length, edges: (topic.edges || []).length };
                    }),
                    energy: data.energy
                }
            };
        }
        return data;
    }

    function flattenForCsv(data) {
        var rows = [];
        if (data.executiveSummary || data.audit || data.mode && data.mode !== 'full') {
            var flat = data.payload || data.executiveSummary || data.audit;
            return [['metric', 'value']].concat(Object.keys(flat).map(function (key) {
                return [key, typeof flat[key] === 'object' ? JSON.stringify(flat[key]) : flat[key]];
            }));
        }
        if (data.scope && data.scope === 'energy') return [['system', 'status', 'path', 'note'], ['energy', data.payload.status, data.payload.path, data.payload.note]];
        if (data.scope && data.scope === 'storage') {
            rows.push(['name', 'extension', 'category', 'size', 'uploadedAt']);
            data.payload.files.forEach(function (file) { rows.push([file.name, file.extension, file.category, file.size, file.uploadedAt]); });
            return rows;
        }
        if (data.scope && data.scope === 'visualgraph') {
            rows.push(['title', 'type', 'keywords', 'nodes', 'edges', 'createdAt']);
            data.payload.topics.forEach(function (topic) { rows.push([topic.title, topic.type, (topic.keywords || []).join('|'), (topic.nodes || []).length, (topic.edges || []).length, topic.createdAt]); });
            return rows;
        }
        rows.push(['system', 'metric', 'value']);
        rows.push(['energy', 'status', data.energy.status]);
        rows.push(['storage', 'fileCount', data.storage.summary.count]);
        rows.push(['storage', 'remainingBytes', data.storage.summary.remainingBytes]);
        rows.push(['visualgraph', 'topicCount', data.visualgraph.topics.length]);
        rows.push(['visualgraph', 'activeTitle', data.visualgraph.summary.title]);
        return rows;
    }

    function toCsv(rows) {
        return rows.map(function (row) {
            return row.map(function (cell) { return '"' + String(cell == null ? '' : cell).replace(/"/g, '""') + '"'; }).join(',');
        }).join('\n');
    }

    function toMarkdown(data) {
        return [
            '# Data Export Package',
            '',
            '## Information',
            '- Exported at: ' + data.exportedAt,
            '',
            '```json',
            JSON.stringify(data, null, 2),
            '```'
        ].join('\n');
    }

    function escapeHtml(text) {
        return String(text == null ? '' : text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    }

    function toHtml(data) {
        return '<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Export Package</title><style>body{font-family:Georgia,serif;padding:32px;color:#1f2937}pre{white-space:pre-wrap;background:#f8fafc;padding:16px;border-radius:12px}</style></head><body><h1>Data Export Package</h1><p>Exported at: ' + data.exportedAt + '</p><pre>' + escapeHtml(JSON.stringify(data, null, 2)) + '</pre></body></html>';
    }

    function toDoc(data) {
        return '<html><head><meta charset="utf-8"></head><body><h1>Data Export Package</h1><p>Exported at: ' + data.exportedAt + '</p><pre>' + escapeHtml(JSON.stringify(data, null, 2)) + '</pre></body></html>';
    }

    function triggerDownload(content, extension, mimeType) {
        var blob = new Blob([content], { type: mimeType });
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = 'an-nguyen-export-' + Date.now() + '.' + extension;
        link.click();
        URL.revokeObjectURL(url);
    }

    function renderSummary(data) {
        document.getElementById('summaryGrid').innerHTML = [
            '<article class="summary-card"><span>Energy app status</span><strong>' + data.energy.status + '</strong></article>',
            '<article class="summary-card"><span>Catalog entries</span><strong>' + data.storage.summary.count + '</strong></article>',
            '<article class="summary-card"><span>Target remaining</span><strong>' + ((data.storage.summary.remainingBytes || 0) / (1024 * 1024 * 1024)).toFixed(2) + ' GB</strong></article>',
            '<article class="summary-card"><span>Visualgraph topics</span><strong>' + data.visualgraph.topics.length + '</strong></article>'
        ].join('');
    }

    function previewText(data, format, mode) {
        if (format === 'json') return JSON.stringify(data, null, 2);
        if (format === 'csv') return toCsv(flattenForCsv(data));
        if (format === 'txt') return JSON.stringify(data, null, 2);
        if (format === 'md') return toMarkdown(data);
        if (format === 'html') return toHtml(data);
        if (format === 'doc') return toDoc(data);
        if (format === 'pdf') return 'PDF is created from the HTML preview through the browser print dialog.\n\n' + toHtml(data);
        return JSON.stringify(data, null, 2);
    }

    function tipsText(scope, format, mode) {
        return 'Current scope: ' + scope + '. Format: ' + format + '. Report mode: ' + mode + '. PDF opens the print dialog; CSV flattens data into rows; JSON/MD/HTML/DOC use the selected detail level.';
    }

    function updatePreview(options) {
        var allData = collectData(options || { force: false });
        var scope = document.getElementById('datasetScope').value;
        var format = document.getElementById('formatSelect').value;
        var mode = document.getElementById('reportMode').value;
        var scoped = pickScope(allData, scope);
        var exported = buildExportObject(scoped, mode);

        renderSummary(allData);
        document.getElementById('previewBox').textContent = previewText(exported, format, mode);
        document.getElementById('previewMeta').textContent = 'Preview for ' + scope + ' in format ' + format + ' with mode ' + mode + '.';
        document.getElementById('scopeTag').textContent = scope;
        document.getElementById('formatTag').textContent = format;
        document.getElementById('modeTag').textContent = mode;
        document.getElementById('exportTips').textContent = tipsText(scope, format, mode);
        document.getElementById('restoreTips').textContent = 'Backup includes catalog metadata and Visualgraph topics, not original files. Restore overwrites the selected local data.';

        previewCache = { exported: exported, format: format, mode: mode };
        return previewCache;
    }

    function crc32Table() {
        var table = [];
        for (var i = 0; i < 256; i += 1) {
            var c = i;
            for (var j = 0; j < 8; j += 1) {
                c = ((c & 1) ? (0xEDB88320 ^ (c >>> 1)) : (c >>> 1));
            }
            table[i] = c >>> 0;
        }
        return table;
    }

    var CRC_TABLE = crc32Table();

    function crc32(bytes) {
        var crc = 0 ^ (-1);
        for (var i = 0; i < bytes.length; i += 1) {
            crc = (crc >>> 8) ^ CRC_TABLE[(crc ^ bytes[i]) & 0xFF];
        }
        return (crc ^ (-1)) >>> 0;
    }

    function concatUint8Arrays(parts) {
        var total = parts.reduce(function (sum, part) { return sum + part.length; }, 0);
        var out = new Uint8Array(total);
        var offset = 0;
        parts.forEach(function (part) {
            out.set(part, offset);
            offset += part.length;
        });
        return out;
    }

    function writeUint16(view, offset, value) {
        view.setUint16(offset, value, true);
    }

    function writeUint32(view, offset, value) {
        view.setUint32(offset, value >>> 0, true);
    }

    function createSimpleZip(fileName, text) {
        var encoder = new TextEncoder();
        var nameBytes = encoder.encode(fileName);
        var dataBytes = encoder.encode(text);
        var crc = crc32(dataBytes);

        var localHeader = new Uint8Array(30 + nameBytes.length);
        var lv = new DataView(localHeader.buffer);
        writeUint32(lv, 0, 0x04034b50);
        writeUint16(lv, 4, 20);
        writeUint16(lv, 6, 0);
        writeUint16(lv, 8, 0);
        writeUint16(lv, 10, 0);
        writeUint16(lv, 12, 0);
        writeUint32(lv, 14, crc);
        writeUint32(lv, 18, dataBytes.length);
        writeUint32(lv, 22, dataBytes.length);
        writeUint16(lv, 26, nameBytes.length);
        writeUint16(lv, 28, 0);
        localHeader.set(nameBytes, 30);

        var centralHeader = new Uint8Array(46 + nameBytes.length);
        var cv = new DataView(centralHeader.buffer);
        writeUint32(cv, 0, 0x02014b50);
        writeUint16(cv, 4, 20);
        writeUint16(cv, 6, 20);
        writeUint16(cv, 8, 0);
        writeUint16(cv, 10, 0);
        writeUint16(cv, 12, 0);
        writeUint16(cv, 14, 0);
        writeUint32(cv, 16, crc);
        writeUint32(cv, 20, dataBytes.length);
        writeUint32(cv, 24, dataBytes.length);
        writeUint16(cv, 28, nameBytes.length);
        writeUint16(cv, 30, 0);
        writeUint16(cv, 32, 0);
        writeUint16(cv, 34, 0);
        writeUint16(cv, 36, 0);
        writeUint32(cv, 38, 0);
        writeUint32(cv, 42, 0);
        centralHeader.set(nameBytes, 46);

        var endRecord = new Uint8Array(22);
        var ev = new DataView(endRecord.buffer);
        writeUint32(ev, 0, 0x06054b50);
        writeUint16(ev, 4, 0);
        writeUint16(ev, 6, 0);
        writeUint16(ev, 8, 1);
        writeUint16(ev, 10, 1);
        writeUint32(ev, 12, centralHeader.length);
        writeUint32(ev, 16, localHeader.length + dataBytes.length);
        writeUint16(ev, 20, 0);

        return concatUint8Arrays([localHeader, dataBytes, centralHeader, endRecord]);
    }

    function extractSimpleZipJson(arrayBuffer) {
        if (arrayBuffer.byteLength < 30 || arrayBuffer.byteLength > 20 * 1024 * 1024) throw new Error('Invalid or oversized backup ZIP.');
        var bytes = new Uint8Array(arrayBuffer);
        var view = new DataView(arrayBuffer);
        if (view.getUint32(0, true) !== 0x04034b50) {
            throw new Error('This is not a valid ZIP in the supported simple backup format.');
        }
        var compressionMethod = view.getUint16(8, true);
        if (compressionMethod !== 0) {
            throw new Error('This ZIP uses compression other than STORE and cannot be restored.');
        }
        var nameLength = view.getUint16(26, true);
        var extraLength = view.getUint16(28, true);
        var compressedSize = view.getUint32(18, true);
        var dataOffset = 30 + nameLength + extraLength;
        if (dataOffset + compressedSize > bytes.length) throw new Error('Truncated backup ZIP.');
        var data = bytes.slice(dataOffset, dataOffset + compressedSize);
        if (crc32(data) !== view.getUint32(14, true)) throw new Error('Backup ZIP checksum mismatch.');
        return new TextDecoder('utf-8', { fatal: true }).decode(data);
    }

    function triggerBlobDownload(blob, fileName) {
        var url = URL.createObjectURL(blob);
        var link = document.createElement('a');
        link.href = url;
        link.download = fileName;
        link.click();
        URL.revokeObjectURL(url);
    }

    function exportBackup() {
        var backup = collectBackupPayload();
        var backupFormat = document.getElementById('backupFormat').value;
        var jsonText = JSON.stringify(backup, null, 2);

        if (backupFormat === 'json') {
            triggerDownload(jsonText, 'json', 'application/json');
            return;
        }

        var zipBytes = createSimpleZip('backup.json', jsonText);
        var blob = new Blob([zipBytes], { type: 'application/zip' });
        triggerBlobDownload(blob, 'an-nguyen-backup-' + Date.now() + '.zip');
    }

    function applyRestoreObject(backupObject) {
        if (!backupObject || backupObject.schema !== 'cuc-quan-ly-backup-v1' || !backupObject.payload || typeof backupObject.payload !== 'object' || Array.isArray(backupObject.payload)) {
            throw new Error('The backup does not match the supported restore schema.');
        }

        var changes = BACKUP_KEYS.filter(function (key) { return Object.prototype.hasOwnProperty.call(backupObject.payload, key); });
        changes.forEach(function (key) {
            var value = backupObject.payload[key];
            if (value === null) return;
            if (typeof value !== 'string' || value.length > 20 * 1024 * 1024) throw new Error('Invalid backup value for ' + key);
            var parsed = JSON.parse(value);
            var collection = key === BACKUP_KEYS[0] || key === BACKUP_KEYS[2];
            if (collection ? !Array.isArray(parsed) : !parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Invalid backup data for ' + key);
            if (collection && parsed.some(function (item) { return !item || typeof item !== 'object' || Array.isArray(item); })) throw new Error('Invalid backup records for ' + key);
        });
        var previous = {};
        changes.forEach(function (key) { previous[key] = localStorage.getItem(key); });
        try {
            changes.forEach(function (key) {
                var value = backupObject.payload[key];
                if (value === null) localStorage.removeItem(key);
                else localStorage.setItem(key, value);
            });
        } catch (error) {
            var rollbackFailed = false;
            changes.forEach(function (key) {
                try {
                    if (previous[key] === null) localStorage.removeItem(key);
                    else localStorage.setItem(key, previous[key]);
                } catch (_) { rollbackFailed = true; }
            });
            if (rollbackFailed) throw new Error('Restore failed and rollback was incomplete. Keep your backup and do not close this page.');
            throw new Error('Restore failed; previous data was preserved. ' + error.message);
        }
    }

    function handleRestoreFile(file) {
        if (!file) return;
        if (file.size > 20 * 1024 * 1024) { alert('Backup is too large (20 MB maximum).'); return; }
        if (!confirm('Restore overwrites local catalog and graph data. Continue?')) return;
        var reader = new FileReader();
        reader.onerror = function () { alert('Could not read the backup file.'); };
        reader.onload = function () {
            try {
                var backupObject;
                if (file.name.toLowerCase().endsWith('.zip')) {
                    var jsonText = extractSimpleZipJson(reader.result);
                    backupObject = JSON.parse(jsonText);
                } else {
                    backupObject = JSON.parse(reader.result);
                }
                applyRestoreObject(backupObject);
                dataCache = null;
                previewCache = null;
                updatePreview();
                alert('Restore complete. Local data has been loaded from the backup.');
            } catch (error) {
                alert('Restore failed: ' + error.message);
            }
        };

        if (file.name.toLowerCase().endsWith('.zip')) reader.readAsArrayBuffer(file);
        else reader.readAsText(file);
    }

    document.getElementById('datasetScope').addEventListener('change', function () { updatePreview(); });
    document.getElementById('formatSelect').addEventListener('change', function () { updatePreview(); });
    document.getElementById('reportMode').addEventListener('change', function () { updatePreview(); });
    document.getElementById('refreshBtn').addEventListener('click', function () {
        forceRefreshData();
        updatePreview();
    });
    document.getElementById('backupBtn').addEventListener('click', exportBackup);
    document.getElementById('restoreInput').addEventListener('change', function (event) {
        handleRestoreFile(event.target.files[0]);
        event.target.value = '';
    });

    document.getElementById('exportBtn').addEventListener('click', function () {
        if (!previewCache || previewCache.format !== document.getElementById('formatSelect').value) {
            updatePreview();
        }
        var data = previewCache.exported;
        var format = previewCache.format;
        if (format === 'json') return triggerDownload(JSON.stringify(data, null, 2), 'json', 'application/json');
        if (format === 'csv') return triggerDownload(toCsv(flattenForCsv(data)), 'csv', 'text/csv');
        if (format === 'txt') return triggerDownload(JSON.stringify(data, null, 2), 'txt', 'text/plain');
        if (format === 'md') return triggerDownload(toMarkdown(data), 'md', 'text/markdown');
        if (format === 'html') return triggerDownload(toHtml(data), 'html', 'text/html');
        if (format === 'doc') return triggerDownload(toDoc(data), 'doc', 'application/msword');
        if (format === 'pdf') {
            var win = window.open('', '_blank');
            if (!win) {
                alert('The browser blocked the popup. Allow popups to export a PDF.');
                return;
            }
            var pdfHtml = toHtml(data);
            win.document.open();
            win.document.write(pdfHtml);
            win.document.close();
            win.focus();
            setTimeout(function () { win.print(); }, 300);
        }
    });

    window.addEventListener('storage', function (event) {
        if (event.key === null || BACKUP_KEYS.indexOf(event.key) >= 0) { forceRefreshData(); updatePreview(); }
    });
    updatePreview();
})();
