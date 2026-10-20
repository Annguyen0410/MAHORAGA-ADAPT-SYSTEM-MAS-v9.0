(function () {
    var STORAGE_KEY = 'an_nguyen_storage_system_v1';
    var LIMIT_BYTES = 10 * 1024 * 1024 * 1024;
    var supportedExtensions = new Set(['md','txt','rtf','pdf','doc','docx','xls','xlsx','ppt','pptx','csv','json','xml','zip','rar','7z','tar','gz','mp3','wav','flac','midi','mid','flm','ogg','aac','m4a','png','jpg','jpeg','gif','webp','svg','mp4','mov','avi','mkv','js','ts','jsx','tsx','html','css','scss','py','java','kt','c','cpp','cs','php','go','rs','swift','sql','sh','bat','ps1','vue','dart','rb','lua','yml','yaml','ini','toml']);
    var nodes = {
        fileInput: document.getElementById('fileInput'),
        fileList: document.getElementById('fileList'),
        usedDisplay: document.getElementById('usedDisplay'),
        remainingDisplay: document.getElementById('remainingDisplay'),
        limitDisplay: document.getElementById('limitDisplay'),
        countDisplay: document.getElementById('countDisplay'),
        storageFill: document.getElementById('storageFill'),
        storageCaption: document.getElementById('storageCaption'),
        storageHealth: document.getElementById('storageHealth'),
        searchInput: document.getElementById('searchInput'),
        categoryFilter: document.getElementById('categoryFilter'),
        sortFilter: document.getElementById('sortFilter'),
        categoryStats: document.getElementById('categoryStats'),
        largestFile: document.getElementById('largestFile'),
        latestUpload: document.getElementById('latestUpload'),
        resultsMeta: document.getElementById('resultsMeta'),
        dropzone: document.getElementById('dropzone')
    };

    var storeReadable = true;
    function readStore() {
        storeReadable = true;
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            var items = raw === null ? [] : JSON.parse(raw);
            if (!Array.isArray(items)) throw new Error('Invalid catalog');
            return items.map(function (item) {
                if (!item || typeof item !== 'object' || Array.isArray(item) || typeof item.id !== 'string' || !item.id || typeof item.name !== 'string') throw new Error('Invalid catalog record');
                var size = Number(item.size);
                if (!Number.isFinite(size) || size < 0) throw new Error('Invalid file size');
                var type = typeof item.type === 'string' ? item.type : 'application/octet-stream';
                var timestamp = Date.parse(item.uploadedAt);
                return Object.assign({}, item, { size: size, type: type, extension: getExtension(item.name), category: getCategory(item.name, type), uploadedAtMs: Number.isFinite(timestamp) ? timestamp : 0, uploadedAtFormatted: getFormattedDate(item.uploadedAt) });
            });
        } catch (error) {
            storeReadable = false;
            nodes.storageHealth.textContent = 'Catalog data could not be read. Saved bytes are preserved; restore a valid backup before editing.';
            return [];
        }
    }

    function writeStore(items) {
        if (!storeReadable) throw new Error('Unreadable catalog data was preserved. Restore a valid backup before editing.');
        localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    }

    function commitItems(items) {
        try { writeStore(items); }
        catch (error) { alert('Catalog was not changed: ' + error.message); return false; }
        storeCache = items;
        summaryDirty = true;
        render();
        return true;
    }

    var dateCache = Object.create(null);
    var storeCache = readStore();
    var summaryDirty = true;

    function getFormattedDate(uploadedAt) {
        if (!(uploadedAt in dateCache)) {
            dateCache[uploadedAt] = new Date(uploadedAt).toLocaleString('en-US');
        }
        return dateCache[uploadedAt];
    }

    function formatBytes(bytes) {
        var gb = bytes / (1024 * 1024 * 1024);
        if (gb >= 1) return gb.toFixed(2) + ' GB';
        var mb = bytes / (1024 * 1024);
        if (mb >= 1) return mb.toFixed(2) + ' MB';
        var kb = bytes / 1024;
        if (kb >= 1) return kb.toFixed(2) + ' KB';
        return bytes + ' B';
    }

    function getExtension(name) {
        var parts = name.toLowerCase().split('.');
        return parts.length > 1 ? parts.pop() : 'unknown';
    }

    function escapeHtml(str) {
        return String(str == null ? '' : str)
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;');
    }

    function getCategory(fileName, type) {
        var ext = getExtension(fileName);
        if (['md','txt','pdf','doc','docx','xls','xlsx','ppt','pptx','rtf'].includes(ext)) return 'document';
        if (['mp3','wav','flac','midi','mid','flm','ogg','aac','m4a'].includes(ext) || type.indexOf('audio/') === 0) return 'audio';
        if (['js','ts','jsx','tsx','html','css','scss','py','java','kt','c','cpp','cs','php','go','rs','swift','sql','sh','bat','ps1','vue','dart','rb','lua','yml','yaml','ini','toml'].includes(ext)) return 'code';
        if (['zip','rar','7z','tar','gz'].includes(ext)) return 'archive';
        if (['png','jpg','jpeg','gif','webp','svg'].includes(ext) || type.indexOf('image/') === 0) return 'image';
        if (['mp4','mov','avi','mkv'].includes(ext) || type.indexOf('video/') === 0) return 'video';
        if (['csv','json','xml'].includes(ext)) return 'data';
        return 'other';
    }

    function normalizeFiles(fileList) {
        return Array.from(fileList).map(function (file) {
            var ext = getExtension(file.name);
            var uploadedAt = new Date().toISOString();
            return {
                id: Date.now().toString(36) + Math.random().toString(36).slice(2, 8),
                name: file.name,
                extension: ext,
                size: file.size || 0,
                type: file.type || 'application/octet-stream',
                category: getCategory(file.name, file.type || ''),
                accepted: supportedExtensions.has(ext) || file.type !== '',
                uploadedAt: uploadedAt,
                uploadedAtMs: Date.parse(uploadedAt),
                uploadedAtFormatted: getFormattedDate(uploadedAt)
            };
        });
    }

    function usageMessage(percent) {
        if (percent === 0) return 'The catalog is empty and ready.';
        if (percent < 35) return 'Cataloged files are well below your planning target.';
        if (percent < 70) return 'Cataloged size is increasing; keep an eye on large files.';
        if (percent < 90) return 'You are nearing the planning target; review old or large entries.';
        return 'The catalog is near its planning target; review your entries.';
    }

    function syncSummary(items) {
        var used = items.reduce(function (sum, item) { return sum + item.size; }, 0);
        var remaining = Math.max(0, LIMIT_BYTES - used);
        var usedPercent = Math.min(100, (used / LIMIT_BYTES) * 100);
        var largest = items.slice().sort(function (a, b) { return b.size - a.size; })[0];
        var latest = items.slice().sort(function (a, b) { return b.uploadedAtMs - a.uploadedAtMs; })[0];

        nodes.limitDisplay.textContent = formatBytes(LIMIT_BYTES);
        nodes.usedDisplay.textContent = formatBytes(used);
        nodes.remainingDisplay.textContent = formatBytes(remaining);
        nodes.countDisplay.textContent = String(items.length);
        nodes.storageFill.style.width = usedPercent.toFixed(2) + '%';
        nodes.storageCaption.textContent = usedPercent.toFixed(2) + '% of target cataloged, remaining ' + formatBytes(remaining) + '.';
        if (storeReadable) nodes.storageHealth.textContent = usageMessage(Number(usedPercent.toFixed(2)));
        nodes.largestFile.textContent = largest ? largest.name + ' • ' + formatBytes(largest.size) : 'None yet';
        nodes.latestUpload.textContent = latest ? latest.name + ' • ' + (latest.uploadedAtFormatted || getFormattedDate(latest.uploadedAt)) : 'None yet';

        if (summaryDirty && storeReadable) {
            try { localStorage.setItem('an_nguyen_storage_summary_v1', JSON.stringify({
                limitBytes: LIMIT_BYTES,
                usedBytes: used,
                remainingBytes: remaining,
                count: items.length,
                categoryBreakdown: buildCategoryBreakdown(items),
                updatedAt: new Date().toISOString()
            }));
            summaryDirty = false;
            } catch (_) { nodes.storageHealth.textContent += ' Summary could not be cached; catalog entries are unchanged.'; }
        }
    }

    function buildCategoryBreakdown(items) {
        var counts = Object.create(null);
        items.forEach(function (item) {
            if (!counts[item.category]) counts[item.category] = { count: 0, bytes: 0 };
            counts[item.category].count += 1;
            counts[item.category].bytes += item.size;
        });
        return counts;
    }

    function renderCategoryStats(items) {
        var breakdown = buildCategoryBreakdown(items);
        var labels = Object.keys(breakdown);
        if (!labels.length) {
            nodes.categoryStats.innerHTML = '<div class="empty-state">No category data yet.</div>';
            return;
        }
        nodes.categoryStats.innerHTML = labels.map(function (label) {
            var data = breakdown[label];
            return '<div class="insight-item"><strong>' + escapeHtml(label) + '</strong><span>' + data.count + ' files • ' + formatBytes(data.bytes) + '</span></div>';
        }).join('');
    }

    function getFilteredItems(items) {
        var query = nodes.searchInput.value.trim().toLowerCase();
        var category = nodes.categoryFilter.value;
        var sort = nodes.sortFilter.value;

        var filtered = items.filter(function (item) {
            var matchQuery = !query || item.name.toLowerCase().includes(query) || item.extension.toLowerCase().includes(query);
            var matchCategory = category === 'all' || item.category === category;
            return matchQuery && matchCategory;
        });

        filtered.sort(function (a, b) {
            if (sort === 'latest') return (b.uploadedAtMs || Date.parse(b.uploadedAt)) - (a.uploadedAtMs || Date.parse(a.uploadedAt));
            if (sort === 'oldest') return (a.uploadedAtMs || Date.parse(a.uploadedAt)) - (b.uploadedAtMs || Date.parse(b.uploadedAt));
            if (sort === 'largest') return b.size - a.size;
            if (sort === 'smallest') return a.size - b.size;
            return a.name.localeCompare(b.name, 'en');
        });

        return filtered;
    }

    function render() {
        var items = storeCache;
        var filtered = getFilteredItems(items);

        syncSummary(items);
        renderCategoryStats(items);
        nodes.resultsMeta.textContent = 'Showing ' + filtered.length + ' / ' + items.length + ' entries.';

        if (!filtered.length) {
            nodes.fileList.innerHTML = '<div class="empty-state">No entries match the current filters.</div>';
            return;
        }

        nodes.fileList.innerHTML = filtered.map(function (item) {
            return [
                '<article class="file-card">',
                '<div class="file-main">',
                '<h3>' + escapeHtml(item.name) + '</h3>',
                '<p>' + escapeHtml(getFormattedDate(item.uploadedAt)) + '</p>',
                '<div class="file-tags">',
                '<span class="file-chip">.' + escapeHtml(item.extension) + '</span>',
                '<span class="file-chip">' + escapeHtml(item.category) + '</span>',
                '<span class="file-status">' + (item.accepted ? 'Recognized type' : 'Metadata only') + '</span>',
                '</div>',
                '</div>',
                '<div class="file-meta-grid">',
                '<div>Size: ' + formatBytes(item.size) + '</div>',
                '<div>MIME type: ' + escapeHtml(item.type) + '</div>',
                '<div>Target share: ' + ((item.size / LIMIT_BYTES) * 100).toFixed(4) + '% of target</div>',
                '</div>',
                '<div class="file-actions">',
                '<button class="delete-btn" data-id="' + escapeHtml(item.id) + '">Remove entry</button>',
                '</div>',
                '</article>'
            ].join('');
        }).join('');
    }

    function ingestFiles(fileList) {
        storeCache = readStore();
        var items = storeCache;
        var normalized = normalizeFiles(fileList);
        var currentUsed = items.reduce(function (sum, item) { return sum + item.size; }, 0);
        var incomingSize = normalized.reduce(function (sum, item) { return sum + item.size; }, 0);
        if (currentUsed + incomingSize > LIMIT_BYTES) {
            alert('The catalog exceeds its 10 GB planning target. Remove entries or select fewer files. Originals are not deleted.');
            return;
        }
        return commitItems(items.concat(normalized));
    }

    nodes.fileInput.addEventListener('change', function (event) {
        ingestFiles(event.target.files);
        event.target.value = '';
    });
    var searchTimer = null;
    nodes.searchInput.addEventListener('input', function () {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(render, 180);
    });
    nodes.categoryFilter.addEventListener('change', render);
    nodes.sortFilter.addEventListener('change', render);
    nodes.fileList.addEventListener('click', function (event) {
        var id = event.target.getAttribute('data-id');
        if (!id) return;
        storeCache = readStore();
        commitItems(storeCache.filter(function (item) { return item.id !== id; }));
    });
    ['dragenter'].forEach(function (type) {
        nodes.dropzone.addEventListener(type, function (event) {
            event.preventDefault();
            nodes.dropzone.classList.add('dragging');
        });
    });
    nodes.dropzone.addEventListener('dragover', function (event) {
        event.preventDefault();
        if (!nodes.dropzone.classList.contains('dragging')) {
            nodes.dropzone.classList.add('dragging');
        }
    });
    ['dragleave', 'drop'].forEach(function (type) {
        nodes.dropzone.addEventListener(type, function (event) {
            event.preventDefault();
            nodes.dropzone.classList.remove('dragging');
        });
    });
    nodes.dropzone.addEventListener('drop', function (event) {
        ingestFiles(event.dataTransfer.files);
    });

    window.addEventListener('storage', function (event) {
        if (event.key === STORAGE_KEY || event.key === null) {
            dateCache = Object.create(null);
            storeCache = readStore();
            summaryDirty = true;
            render();
        }
    });
    render();
})();
