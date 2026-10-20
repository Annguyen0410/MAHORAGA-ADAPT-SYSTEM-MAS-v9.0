(function () {
    var STORAGE_KEY = 'an_nguyen_visualgraph_v1';
    var canvas = document.getElementById('graphCanvas');
    var ctx = canvas.getContext('2d');
    var animationId = null;
    var currentGraph = null;

    var storeReadable = true;
    var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)');
    function readStore() {
        storeReadable = true;
        try {
            var raw = localStorage.getItem(STORAGE_KEY);
            var items = raw === null ? [] : JSON.parse(raw);
            if (!Array.isArray(items)) throw new Error('Invalid topic collection');
            return items.map(function (item) {
                if (!item || typeof item !== 'object' || Array.isArray(item) || typeof item.id !== 'string' || !item.id || typeof item.title !== 'string' || typeof item.content !== 'string') throw new Error('Invalid topic record');
                // Derive render-only graph fields from content; never trust imported
                // node coordinates, styles or arrays, and never rewrite on read.
                var graph = buildGraph(item.title, ['transcript', 'note', 'idea', 'research'].includes(item.type) ? item.type : 'note', item.content, [12, 18, 24].includes(Number(item.density)) ? Number(item.density) : 18);
                return Object.assign({}, item, graph, { id: item.id, createdAt: typeof item.createdAt === 'string' ? item.createdAt : '' });
            });
        } catch (error) {
            storeReadable = false;
            return [];
        }
    }

    function writeStore(items) {
        if (!storeReadable) throw new Error('Unreadable topic data was preserved. Restore a valid backup before editing.');
        localStorage.setItem(STORAGE_KEY, JSON.stringify(items));
    }

    function escapeHtml(value) {
        return String(value == null ? '' : value).replace(/[&<>"']/g, function (character) {
            return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[character];
        });
    }

    function extractKeywords(text, maxKeywords) {
        var seen = new Set();
        return text.toLowerCase()
            .replace(/[^\p{L}\p{N}\s]/gu, ' ')
            .split(/\s+/)
            .filter(function (word) { return word && word.length > 3; })
            .filter(function (word) {
                if (seen.has(word)) return false;
                seen.add(word);
                return true;
            })
            .slice(0, maxKeywords);
    }

    function summarize(title, keywords) {
        if (!keywords.length) return 'This topic has no clear keywords yet.';
        return title + ' centers on ' + keywords.slice(0, 4).join(', ') + '.';
    }

    function buildGraph(title, type, content, density) {
        var keywords = extractKeywords(content, density);
        var centerX = canvas.width / 2;
        var centerY = canvas.height / 2;
        var radius = 170;
        var nodes = [{
            id: 'core',
            label: title,
            x: centerX,
            y: centerY,
            baseX: centerX,
            baseY: centerY,
            orbit: 0,
            depth: 1,
            role: 'core'
        }];

        keywords.forEach(function (word, index) {
            var angle = (Math.PI * 2 * index) / Math.max(1, keywords.length);
            var orbit = radius + (index % 3) * 32;
            nodes.push({
                id: 'kw-' + index,
                label: word,
                x: centerX + Math.cos(angle) * orbit,
                y: centerY + Math.sin(angle) * orbit,
                baseX: centerX,
                baseY: centerY,
                orbit: orbit,
                phase: angle,
                speed: 0.0022 + (index % 5) * 0.00045,
                depth: 0.35 + Math.abs(Math.sin(angle)),
                role: index % 4 === 0 ? 'link' : 'idea'
            });
        });

        var edges = [];
        for (var i = 1; i < nodes.length; i += 1) {
            edges.push({ from: 'core', to: nodes[i].id, weight: 1 });
            if (i > 1) edges.push({ from: nodes[i - 1].id, to: nodes[i].id, weight: 0.5 });
            if (i > 2 && i % 3 === 0) edges.push({ from: nodes[i - 2].id, to: nodes[i].id, weight: 0.3 });
        }

        return {
            id: Date.now().toString(36) + Math.random().toString(36).slice(2, 7),
            title: title,
            type: type,
            content: content,
            keywords: keywords,
            nodes: nodes,
            edges: edges,
            density: density,
            summary: summarize(title, keywords),
            createdAt: new Date().toISOString()
        };
    }

    // Pre-baked glow sprites (created once, reused every frame) — avoids per-frame shadowBlur
    var glowSprites = {};
    function getGlowSprite(fill) {
        if (!glowSprites[fill]) {
            var size = 96;
            var sprite = document.createElement('canvas');
            sprite.width = size;
            sprite.height = size;
            var sctx = sprite.getContext('2d');
            var g = sctx.createRadialGradient(size / 2, size / 2, 4, size / 2, size / 2, size / 2);
            g.addColorStop(0, fill);
            g.addColorStop(0.25, 'rgba(255,255,255,0.35)');
            g.addColorStop(1, 'rgba(0,0,0,0)');
            sctx.fillStyle = g;
            sctx.fillRect(0, 0, size, size);
            glowSprites[fill] = sprite;
        }
        return glowSprites[fill];
    }

    var bgGlow = null;
    function getBgGlow() {
        if (!bgGlow) {
            bgGlow = ctx.createRadialGradient(canvas.width / 2, canvas.height / 2, 50, canvas.width / 2, canvas.height / 2, 280);
            bgGlow.addColorStop(0, 'rgba(191,136,255,0.16)');
            bgGlow.addColorStop(1, 'rgba(0,0,0,0)');
        }
        return bgGlow;
    }

    function drawGraphFrame(graph, timestamp, nodeIndex) {
        var w = canvas.width;
        var h = canvas.height;
        ctx.setTransform(1, 0, 0, 1, 0, 0);
        ctx.clearRect(0, 0, w, h);

        ctx.fillStyle = getBgGlow();
        ctx.fillRect(0, 0, w, h);

        graph.nodes.forEach(function (node, index) {
            if (node.role === 'core') return;
            var motion = timestamp * node.speed + node.phase;
            node.x = node.baseX + Math.cos(motion) * node.orbit;
            node.y = node.baseY + Math.sin(motion) * (node.orbit * 0.55);
            node.depth = 0.45 + Math.abs(Math.sin(motion));
            if (index % 2 === 0) node.y += Math.sin(motion * 1.5) * 8;
        });

        graph.edges.forEach(function (edge) {
            var from = nodeIndex[edge.from];
            var to = nodeIndex[edge.to];
            if (!from || !to) return;
            ctx.beginPath();
            ctx.moveTo(from.x, from.y);
            ctx.lineTo(to.x, to.y);
            ctx.strokeStyle = 'rgba(255,255,255,' + (0.08 + edge.weight * 0.12) + ')';
            ctx.lineWidth = 1 + edge.weight;
            ctx.stroke();
        });

        graph.nodes.forEach(function (node) {
            var radius = node.role === 'core' ? 30 : 10 + node.depth * 7;
            var fill = '#78dbff';
            if (node.role === 'core') fill = '#f5cf78';
            if (node.role === 'link') fill = '#ff8ed5';

            // Draw pre-baked glow sprite under the node instead of ctx.shadowBlur
            var sprite = getGlowSprite(fill);
            var glowSize = radius * 4;
            ctx.globalAlpha = node.role === 'core' ? 0.9 : 0.65;
            ctx.drawImage(sprite, node.x - glowSize / 2, node.y - glowSize / 2, glowSize, glowSize);
            ctx.globalAlpha = 1;

            ctx.beginPath();
            ctx.arc(node.x, node.y, radius, 0, Math.PI * 2);
            ctx.fillStyle = fill;
            ctx.fill();

            ctx.fillStyle = node.role === 'core' ? '#211129' : '#120f1a';
            ctx.font = node.role === 'core' ? 'bold 14px Trebuchet MS' : '12px Trebuchet MS';
            ctx.textAlign = 'center';
            ctx.fillText(node.label.slice(0, 18), node.x, node.y + 4);
        });
    }

    function startAnimation(graph) {
        currentGraph = graph;
        if (animationId) cancelAnimationFrame(animationId);

        // Build id → node lookup once so per-frame edge rendering is O(E) not O(E*N)
        var timestampIndex = Object.create(null);
        graph.nodes.forEach(function (node) { timestampIndex[node.id] = node; });

        function frame(timestamp) {
            if (currentGraph !== graph) return;
            drawGraphFrame(graph, timestamp, timestampIndex);
            animationId = requestAnimationFrame(frame);
        }

        if (document.hidden) return;
        if (reduceMotion && reduceMotion.matches) { drawGraphFrame(graph, 0, timestampIndex); animationId = null; return; }
        animationId = requestAnimationFrame(frame);
    }

    function renderKeywordCloud(keywords) {
        var cloud = document.getElementById('keywordCloud');
        if (!keywords.length) {
            cloud.innerHTML = '<span>No keywords yet</span>';
            return;
        }
        cloud.innerHTML = keywords.map(function (keyword, index) {
            return '<span style="font-size:' + (0.86 + (index % 5) * 0.08).toFixed(2) + 'rem">' + escapeHtml(keyword) + '</span>';
        }).join('');
    }

    function setActiveGraph(graph) {
        document.getElementById('activeTitle').textContent = graph.title;
        document.getElementById('activeMeta').textContent = graph.type + ' • ' + graph.keywords.length + ' keywords • density ' + graph.density + ' • ' + new Date(graph.createdAt).toLocaleString('en-US');
        document.getElementById('nodeCount').textContent = String(graph.nodes.length);
        document.getElementById('edgeCount').textContent = String(graph.edges.length);
        document.getElementById('keywordCount').textContent = String(graph.keywords.length);
        document.getElementById('summaryLine').textContent = graph.summary;
        renderKeywordCloud(graph.keywords);
        try { localStorage.setItem('an_nguyen_visualgraph_summary_v1', JSON.stringify({
            activeId: graph.id,
            title: graph.title,
            type: graph.type,
            nodeCount: graph.nodes.length,
            edgeCount: graph.edges.length,
            keywordCount: graph.keywords.length,
            summary: graph.summary,
            updatedAt: new Date().toISOString()
        })); } catch (_) { document.getElementById('activeMeta').textContent += ' • Summary cache unavailable; topic is retained.'; }
        startAnimation(graph);
    }

    function renderLibrary() {
        var library = document.getElementById('topicLibrary');
        var items = readStore();
        if (!items.length) {
            library.innerHTML = '<div class="empty-state">' + (storeReadable ? 'No topics saved in Visualgraph yet.' : 'Topic data could not be read. Saved bytes are preserved; restore a valid backup before editing.') + '</div>';
            return;
        }
        library.innerHTML = items.slice().reverse().map(function (item) {
            return [
                '<article class="topic-card">',
                '<div><h3>' + escapeHtml(item.title) + '</h3><p>' + escapeHtml(item.summary) + '</p></div>',
                '<div class="meta">' + escapeHtml(item.type) + '<br>' + item.keywords.length + ' keywords<br>' + item.edges.length + ' links</div>',
                '<button class="secondary-btn" data-view="' + escapeHtml(item.id) + '">View graph</button>',
                '<button class="secondary-btn" data-delete="' + escapeHtml(item.id) + '">Delete</button>',
                '</article>'
            ].join('');
        }).join('');
    }

    function resetComposer() {
        document.getElementById('topicTitle').value = '';
        document.getElementById('topicContent').value = '';
    }

    document.getElementById('generateBtn').addEventListener('click', function () {
        var title = document.getElementById('topicTitle').value.trim();
        var type = document.getElementById('topicType').value;
        var content = document.getElementById('topicContent').value.trim();
        var density = parseInt(document.getElementById('densityLevel').value, 10);
        if (!title || !content) {
            alert('Enter a topic title and content before generating a graph.');
            return;
        }
        if (title.length > 1024 || content.length > 1000000) { alert('Keep the title under 1,024 characters and content under 1 MB. Your draft is retained.'); return; }
        var graph = buildGraph(title, type, content, density);
        var items = readStore();
        items.push(graph);
        try { writeStore(items); }
        catch (error) { alert('Topic was not saved: ' + error.message + ' Your draft is retained.'); return; }
        setActiveGraph(graph);
        renderLibrary();
    });

    document.getElementById('clearBtn').addEventListener('click', resetComposer);

    document.getElementById('topicLibrary').addEventListener('click', function (event) {
        var viewId = event.target.getAttribute('data-view');
        var deleteId = event.target.getAttribute('data-delete');
        var items = readStore();
        if (viewId) {
            var selected = items.find(function (item) { return item.id === viewId; });
            if (selected) setActiveGraph(selected);
            return;
        }
        if (deleteId) {
            try { writeStore(items.filter(function (item) { return item.id !== deleteId; })); }
            catch (error) { alert('Topic was not deleted: ' + error.message); return; }
            renderLibrary();
            if (currentGraph && currentGraph.id === deleteId) {
                if (animationId) cancelAnimationFrame(animationId);
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                document.getElementById('activeTitle').textContent = 'No topic selected';
                document.getElementById('activeMeta').textContent = 'Create a topic to start the Visualgraph simulation.';
                document.getElementById('nodeCount').textContent = '0';
                document.getElementById('edgeCount').textContent = '0';
                document.getElementById('keywordCount').textContent = '0';
                document.getElementById('summaryLine').textContent = 'No data yet';
                renderKeywordCloud([]);
                currentGraph = null;
                try { localStorage.removeItem('an_nguyen_visualgraph_summary_v1'); } catch (_) {}
            }
        }
    });

    if (reduceMotion && reduceMotion.addEventListener) reduceMotion.addEventListener('change', function () { if (currentGraph) startAnimation(currentGraph); });
    window.addEventListener('storage', function (event) {
        if (event.key !== STORAGE_KEY && event.key !== null) return;
        // Reloading preserves an unsaved composer draft and never applies old
        // cached records over a change made by another tab or a restore.
        renderLibrary();
        if (currentGraph) {
            var selected = readStore().find(function (item) { return item.id === currentGraph.id; });
            if (selected) setActiveGraph(selected);
            else {
                if (animationId) cancelAnimationFrame(animationId);
                currentGraph = null;
                ctx.clearRect(0, 0, canvas.width, canvas.height);
                document.getElementById('activeTitle').textContent = 'No topic selected';
                document.getElementById('activeMeta').textContent = 'The active topic was removed or restored in another tab.';
                ['nodeCount', 'edgeCount', 'keywordCount'].forEach(function (id) { document.getElementById(id).textContent = '0'; });
                document.getElementById('summaryLine').textContent = 'No data yet';
                renderKeywordCloud([]);
                try { localStorage.removeItem('an_nguyen_visualgraph_summary_v1'); } catch (_) {}
            }
        }
    });
    renderKeywordCloud([]);
    renderLibrary();

    document.addEventListener('visibilitychange', function () {
        if (document.hidden) {
            if (animationId) { cancelAnimationFrame(animationId); animationId = null; }
        } else if (currentGraph) {
            startAnimation(currentGraph);
        }
    });
})();
