// ==================== Neural Web (Knowledge Graph) — v2 ====================
// Performance-first rewrite: O(n) data build (Maps, no nested filters), node
// sampling so 6000+ links / 10k+ tags / PH tools stay at 60fps, glowing nodes,
// starfield background, hub labels, and tool/topic integration.

let NeuralGraph = null;
let highlightedNodes = new Set();
let highlightedLinks = new Set();
let hoverNode = null;
let neuralCaps = { links: 350, tags: 120, tools: 120 };
let neuralAllMode = false;

const NEURAL_GROUP_COLORS = {
    link: '#ef4444',
    note: '#10b981',
    tag: '#38bdf8',
    category: '#f59e0b',
    folder: '#8b5cf6',
    decision: '#ec4899',
    tool: '#fb923c',
    topic: '#facc15'
};

function _hexToRgba(hex, alpha) {
    const h = hex.replace('#', '');
    const r = parseInt(h.substring(0, 2), 16);
    const g = parseInt(h.substring(2, 4), 16);
    const b = parseInt(h.substring(4, 6), 16);
    return 'rgba(' + r + ',' + g + ',' + b + ',' + alpha + ')';
}

// --- Data build (O(n)) ------------------------------------------------------

function buildNeuralData(caps) {
    const savedLinks = window.links || [];
    const savedNotes = window.notes || [];
    const savedFolders = window.folders || [];
    const timelineEvents = window.timelineEvents || [];
    const savedTools = window.tools || [];

    const gData = { nodes: [], links: [] };
    const nodeSet = new Set();
    const addNode = (n) => { if (!nodeSet.has(n.id)) { nodeSet.add(n.id); gData.nodes.push(n); } };
    const addEdge = (s, t) => gData.links.push({ source: s, target: t });

    // Tag frequency (one pass)
    const tagCount = new Map();
    for (const l of savedLinks) {
        for (const t of (l.tags || [])) tagCount.set(t, (tagCount.get(t) || 0) + 1);
    }
    const topTags = [...tagCount.entries()].sort((a, b) => b[1] - a[1]).slice(0, caps.tags);
    const topTagSet = new Set(topTags.map(t => t[0]));
    for (const [t] of topTags) addNode({ id: 'tag-' + t, name: t, group: 'tag', val: 5 + Math.min(10, tagCount.get(t)) });

    // Rank links: visits + favorites/pinned boost + recency (single pass)
    const nowTs = Date.now();
    const ranked = savedLinks.map(l => {
        let s = (l.visitCount || 0) * 2;
        if (l.favorite) s += 6;
        if (l.pinned) s += 4;
        if (l.createdAt) { try { s += Math.max(0, 10 - (nowTs - new Date(l.createdAt).getTime()) / 86400000); } catch (e) { } }
        return { l, s };
    }).sort((a, b) => b.s - a.s);
    const shownLinks = ranked.slice(0, caps.links).map(x => x.l);

    // Categories (single pass)
    const catCount = new Map();
    for (const l of savedLinks) if (l.category) catCount.set(l.category, (catCount.get(l.category) || 0) + 1);
    for (const [c, n] of catCount) addNode({ id: 'cat-' + c, name: c, group: 'category', val: 8 + Math.min(10, n) });

    // Folder → links (single pass)
    const linksByFolder = new Map();
    for (const l of savedLinks) {
        if (!l.folderId) continue;
        if (!linksByFolder.has(l.folderId)) linksByFolder.set(l.folderId, []);
        linksByFolder.get(l.folderId).push(l);
    }

    // Link nodes + edges
    for (const l of shownLinks) addNode({ id: l.id, name: l.title || l.url || 'Untitled', group: 'link', val: 20, data: l });
    for (const l of shownLinks) {
        for (const t of (l.tags || [])) {
            if (topTagSet.has(t)) addEdge(l.id, 'tag-' + t);
        }
        if (l.category) addEdge(l.id, 'cat-' + l.category);
        if (l.folderId) { addNode({ id: 'folder-' + l.folderId, name: '📁', group: 'folder', val: 25, data: null }); addEdge(l.id, 'folder-' + l.folderId); }
    }

    // Folders (labels resolved after node ids exist)
    const folderName = new Map();
    for (const f of savedFolders) folderName.set(f.id, f.name);
    for (const n of gData.nodes) {
        if (n.group === 'folder' && n.id.startsWith('folder-')) {
            const fid = n.id.slice(7);
            const nm = folderName.get(fid);
            if (nm) n.name = '📁 ' + nm;
        }
    }
    for (const f of savedFolders) {
        if (f.parentId) addEdge('folder-' + f.id, 'folder-' + f.parentId);
    }

    // Notes (limited)
    const shownNotes = savedNotes.slice(0, 60);
    for (const note of shownNotes) {
        addNode({ id: 'note-' + note.id, name: note.title || 'Untitled', group: 'note', val: 15, data: note });
        for (const t of (note.tags || [])) {
            if (topTagSet.has(t)) addEdge('note-' + note.id, 'tag-' + t);
        }
    }

    // Tools (top by votes) + topics
    const shownTools = savedTools.slice().sort((a, b) => (b.votes || 0) - (a.votes || 0)).slice(0, caps.tools);
    const topicSet = new Set();
    for (const tool of shownTools) {
        addNode({ id: 'tool-' + tool.id, name: (tool.n || 'Tool').slice(0, 40), group: 'tool', val: 12 + Math.min(10, (tool.votes || 0) / 50), data: tool });
        for (const tp of (tool.topics || []).slice(0, 4)) {
            const topicId = 'topic-' + tp;
            if (!topicSet.has(topicId)) { topicSet.add(topicId); addNode({ id: topicId, name: tp, group: 'topic', val: 4 }); }
            addEdge('tool-' + tool.id, topicId);
        }
    }

    // Strategic decisions → tags
    const decisions = timelineEvents.filter(e => e.type === 'decision');
    for (const decision of decisions.slice(0, 30)) {
        const status = decision.context?.snapshot?.status === 'success' ? '✅' : decision.context?.snapshot?.status === 'failure' ? '❌' : '⏳';
        addNode({ id: 'decision-' + decision.id, name: status + ' ' + (decision.title || 'Decision'), group: 'decision', val: 20, data: decision });
        for (const tag of (decision.context?.tags || [])) {
            if (topTagSet.has(tag)) addEdge('decision-' + decision.id, 'tag-' + tag);
        }
    }

    return { gData, stats: { links: savedLinks.length, shownLinks: shownLinks.length, tags: tagCount.size, tools: savedTools.length, nodes: gData.nodes.length, edges: gData.links.length } };
}

// --- Node visual ------------------------------------------------------------

function makeLabelSprite(node) {
    const color = NEURAL_GROUP_COLORS[node.group] || '#ef4444';
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    canvas.width = 512;
    canvas.height = 128;
    const displayName = node.name.length > 26 ? node.name.substring(0, 23) + '...' : node.name;
    const dimmed = highlightedNodes.size > 0 && !highlightedNodes.has(node.id);
    const bg = _hexToRgba(color, dimmed ? 0.12 : 0.85);
    ctx.fillStyle = bg;
    ctx.beginPath();
    ctx.roundRect(14, 20, canvas.width - 28, canvas.height - 40, 20);
    ctx.fill();
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 34px Inter, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(displayName, canvas.width / 2, canvas.height / 2);
    const tex = new THREE.CanvasTexture(canvas);
    tex.needsUpdate = true;
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false });
    const sprite = new THREE.Sprite(mat);
    const scale = node.group === 'category' ? 20 : node.group === 'folder' ? 22 : 15;
    sprite.scale.set(scale, scale * 0.25, 1);
    return sprite;
}

// Draw a realistic neuron soma (cell body) with radiating dendrites onto a canvas.
// Returns a THREE.Sprite that reads as a living neuron at a glance.
function makeNeuronSprite(node) {
    const color = NEURAL_GROUP_COLORS[node.group] || '#ef4444';
    const dimmed = highlightedNodes.size > 0 && !highlightedNodes.has(node.id);
    const S = 256;
    const c = document.createElement('canvas');
    c.width = c.height = S;
    const ctx = c.getContext('2d');
    const cx = S / 2, cy = S / 2;
    const alpha = dimmed ? 0.22 : 1;

    // Dendrites: short branching fibers radiating from the soma
    const branchCount = 20 + Math.floor(Math.random() * 8);
    ctx.lineCap = 'round';
    for (let i = 0; i < branchCount; i++) {
        const ang = (i / branchCount) * Math.PI * 2 + Math.random() * 0.5;
        const len = 34 + Math.random() * 26;
        const x1 = cx + Math.cos(ang) * 22;
        const y1 = cy + Math.sin(ang) * 22;
        const x2 = cx + Math.cos(ang) * len;
        const y2 = cy + Math.sin(ang) * len;
        // main dendrite branch (fades toward the tip)
        ctx.strokeStyle = _hexToRgba(color, 0.5 * alpha);
        ctx.lineWidth = 2.2;
        ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
        // small secondary branch
        const bAng = ang + (Math.random() - 0.5) * 1.1;
        const bLen = 10 + Math.random() * 12;
        ctx.strokeStyle = _hexToRgba(color, 0.3 * alpha);
        ctx.lineWidth = 1.4;
        ctx.beginPath(); ctx.moveTo(x2, y2); ctx.lineTo(x2 + Math.cos(bAng) * bLen, y2 + Math.sin(bAng) * bLen); ctx.stroke();
    }

    // Soma: layered radial glow + bright nucleus
    const core = ctx.createRadialGradient(cx, cy, 2, cx, cy, 40);
    core.addColorStop(0, _hexToRgba(color, 0.95 * alpha));
    core.addColorStop(0.45, _hexToRgba(color, 0.75 * alpha));
    core.addColorStop(1, _hexToRgba(color, 0));
    ctx.fillStyle = core;
    ctx.beginPath(); ctx.arc(cx, cy, 40, 0, Math.PI * 2); ctx.fill();
    // bright nucleus
    ctx.fillStyle = _hexToRgba('#ffffff', 0.9 * alpha);
    ctx.beginPath(); ctx.arc(cx, cy, 7, 0, Math.PI * 2); ctx.fill();
    ctx.fillStyle = _hexToRgba(color, 0.95 * alpha);
    ctx.beginPath(); ctx.arc(cx, cy, 5, 0, Math.PI * 2); ctx.fill();
    // outer soft halo
    const halo = ctx.createRadialGradient(cx, cy, 20, cx, cy, 88);
    halo.addColorStop(0, _hexToRgba(color, dimmed ? 0.05 : 0.4));
    halo.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = halo;
    ctx.beginPath(); ctx.arc(cx, cy, 88, 0, Math.PI * 2); ctx.fill();

    const tex = new THREE.CanvasTexture(c);
    tex.needsUpdate = true;
    const mat = new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending });
    const sprite = new THREE.Sprite(mat);
    const base = node.group === 'link' ? 11 : node.group === 'note' ? 10 : node.group === 'tool' ? 9 : 8;
    sprite.scale.set(base, base, 1);
    return sprite;
}

// Fallback glowing sphere for groups where a neuron texture is overkill
function makeGlowNode(node) {
    const color = NEURAL_GROUP_COLORS[node.group] || '#ef4444';
    const dimmed = highlightedNodes.size > 0 && !highlightedNodes.has(node.id);
    const group = new THREE.Group();
    const radius = node.group === 'link' ? 3.2 : node.group === 'note' ? 2.8 : 2.6;
    const core = new THREE.Mesh(
        new THREE.SphereGeometry(radius, 12, 12),
        new THREE.MeshBasicMaterial({ color: color, transparent: true, opacity: dimmed ? 0.15 : 0.95 })
    );
    group.add(core);
    // Additive glow halo
    const c = document.createElement('canvas');
    c.width = c.height = 64;
    const ctx = c.getContext('2d');
    const g = ctx.createRadialGradient(32, 32, 2, 32, 32, 32);
    g.addColorStop(0, _hexToRgba(color, dimmed ? 0.05 : 0.55));
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, 64, 64);
    const halo = new THREE.Sprite(new THREE.SpriteMaterial({
        map: new THREE.CanvasTexture(c),
        transparent: true,
        depthWrite: false,
        blending: THREE.AdditiveBlending
    }));
    halo.scale.set(radius * 7, radius * 7, 1);
    group.add(halo);
    return group;
}

// --- Init -------------------------------------------------------------------

function initNeuralWeb() {
    console.log('🧠 Initializing Neural Web v2...');

    const container = document.getElementById('neuralWeb');
    const graphContainer = document.getElementById('neuralGraph');
    if (!container || !graphContainer) return;

    container.classList.remove('hidden');

    if (typeof THREE === 'undefined' || typeof ForceGraph3D === 'undefined') {
        graphContainer.innerHTML = '<div class="flex items-center justify-center h-full text-white"><div class="text-center"><div class="animate-spin w-12 h-12 border-4 border-red-500 border-t-transparent rounded-full mx-auto mb-4"></div><p>Loading 3D library...</p></div></div>';
        const tryAgain = () => initNeuralWeb();
        if (typeof THREE === 'undefined') { setTimeout(tryAgain, 500); return; }
        if (typeof window.loadScript === 'function') {
            window.loadScript('https://unpkg.com/3d-force-graph@1.70.14/dist/3d-force-graph.min.js').then(tryAgain);
        } else { setTimeout(tryAgain, 2000); }
        return;
    }

    const { gData, stats } = buildNeuralData(neuralCaps);
    window._neuralGData = gData; // for focus helpers
    const statsEl = document.getElementById('neuralStats');
    if (statsEl) {
        statsEl.innerHTML = (neuralAllMode ? '<span class="text-amber-300 font-semibold">🪐 full view</span> · ' : '') + '<span class="text-white font-semibold">' + stats.shownLinks + '/' + stats.links + ' links</span> · <span class="text-sky-300">' + stats.tags + ' tags</span> · <span class="text-orange-300">' + stats.tools + ' tools</span> · ' + stats.nodes + ' nodes · ' + stats.edges + ' connections';
    }

    if (!NeuralGraph) {
        // Per-link pulse color — a neuron's signal travels at the color of its source node
        const linkPulseColor = (link) => {
            if (highlightedLinks.has(link)) return '#fde68a';
            const sid = typeof link.source === 'object' ? link.source.id : link.source;
            const srcNode = gData.nodes.find(n => n.id === sid);
            return (srcNode && NEURAL_GROUP_COLORS[srcNode.group]) || '#fbbf24';
        };

        NeuralGraph = ForceGraph3D()(graphContainer)
            .graphData(gData)
            .nodeThreeObject(node => {
                // Link/note/tool/decision = neuron cell bodies; tags/cats/folders/topics = labeled hubs
                if (node.group === 'link' || node.group === 'note' || node.group === 'tool' || node.group === 'decision') {
                    return makeNeuronSprite(node);
                }
                return makeLabelSprite(node);
            })
            .nodeLabel(node => node.name)
            .nodeResolution(8)
            // Curved, organic axon-like connections
            .linkCurvature(0.35)
            .linkWidth(link => highlightedLinks.has(link) ? 2.4 : 0.9)
            .linkOpacity(link => highlightedNodes.size > 0 && !highlightedLinks.has(link) ? 0.05 : 0.28)
            .linkColor(link => highlightedLinks.has(link) ? '#fbbf24' : 'rgba(255,255,255,0.35)')
            // Synaptic transmission: pulses that travel along the connections
            .linkDirectionalParticles(2)
            .linkDirectionalParticleSpeed(() => 0.006)
            .linkDirectionalParticleWidth(() => 1.8)
            .linkDirectionalParticleColor(linkPulseColor)
            .backgroundColor('#050505')
            .onNodeHover(node => {
                if (node === hoverNode) return;
                hoverNode = node;
                graphContainer.style.cursor = node ? 'pointer' : '';
            })
            .onNodeClick(node => {
                highlightedNodes.clear();
                highlightedLinks.clear();
                if (node) {
                    highlightedNodes.add(node.id);
                    gData.links.forEach(link => {
                        const sid = typeof link.source === 'object' ? link.source.id : link.source;
                        const tid = typeof link.target === 'object' ? link.target.id : link.target;
                        if (sid === node.id) { highlightedNodes.add(tid); highlightedLinks.add(link); }
                        else if (tid === node.id) { highlightedNodes.add(sid); highlightedLinks.add(link); }
                    });
                }
                NeuralGraph.refresh();

                const distance = 90;
                const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);
                NeuralGraph.cameraPosition(
                    { x: node.x * distRatio, y: node.y * distRatio, z: node.z * distRatio },
                    node, 2500
                );

                if (node.group === 'link' && node.data && node.data.url) {
                    setTimeout(() => window.open(node.data.url, '_blank'), 500);
                } else if (node.group === 'note') {
                    setTimeout(() => { closeNeuralWeb(); if (window.switchTab) window.switchTab('notes'); }, 1000);
                } else if (node.group === 'tool' && node.data) {
                    showNeuralToolPopup(node.data);
                } else if (node.group === 'topic') {
                    neuralFocusTopic(node);
                } else if (node.group === 'tag' || node.group === 'category') {
                    const searchInput = document.getElementById('searchInput');
                    if (searchInput) {
                        searchInput.value = (node.group === 'category' ? '@' : '#') + node.name;
                        searchInput.dispatchEvent(new Event('input'));
                        closeNeuralWeb();
                    }
                }
            })
            .onBackgroundClick(() => {
                highlightedNodes.clear();
                highlightedLinks.clear();
                closeNeuralToolPopup();
                NeuralGraph.refresh();
            });

        // Ambient lights + starfield (best-effort; scene() may be unavailable)
        try {
            const scene = NeuralGraph.scene();
            if (scene) {
                scene.add(new THREE.AmbientLight(0xffffff, 0.7));
                scene.add(new THREE.DirectionalLight(0xffffff, 0.6));
                const starCount = 700;
                const geo = new THREE.BufferGeometry();
                const pos = new Float32Array(starCount * 3);
                for (let i = 0; i < starCount; i++) {
                    pos[i * 3] = (Math.random() - 0.5) * 900;
                    pos[i * 3 + 1] = (Math.random() - 0.5) * 900;
                    pos[i * 3 + 2] = (Math.random() - 0.5) * 900;
                }
                geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
                scene.add(new THREE.Points(geo, new THREE.PointsMaterial({ color: 0xffffff, size: 0.7, transparent: true, opacity: 0.45 })));
            }
        } catch (e) { /* ignore */ }
    } else {
        NeuralGraph.graphData(gData);
    }

    setTimeout(() => {
        if (NeuralGraph) {
            try { NeuralGraph.width(container.clientWidth).height(container.clientHeight); } catch (e) { }
            NeuralGraph.refresh();
            try { NeuralGraph.zoomToFit(400, 40); } catch (e) { }
        }
    }, 150);
}

function _neuralFocusIds(ids) {
    highlightedNodes.clear();
    highlightedLinks.clear();
    ids.forEach(function (id) { highlightedNodes.add(id); });
    const gData = window._neuralGData || { links: [] };
    gData.links.forEach(function (l) {
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        if (highlightedNodes.has(sid) && highlightedNodes.has(tid)) highlightedLinks.add(l);
    });
    if (NeuralGraph) NeuralGraph.refresh();
}

function _neuralCameraTo(ids) {
    if (!NeuralGraph) return;
    const nodes = NeuralGraph.graphData().nodes.filter(function (n) { return ids.has(n.id); });
    if (!nodes.length) return;
    let cx = 0, cy = 0, cz = 0;
    nodes.forEach(function (n) { cx += n.x || 0; cy += n.y || 0; cz += n.z || 0; });
    cx /= nodes.length; cy /= nodes.length; cz /= nodes.length;
    const distance = 220;
    const distRatio = 1 + distance / Math.hypot(cx, cy, cz || 1);
    NeuralGraph.cameraPosition({ x: cx * distRatio, y: cy * distRatio, z: cz * distRatio }, { x: cx, y: cy, z: cz }, 2200);
}

// Focus the whole tool/topic cluster (button in the toolbar)
function neuralFocusTools() {
    const gData = window._neuralGData || { nodes: [] };
    const ids = new Set();
    gData.nodes.forEach(function (n) {
        if (n.group === 'tool' || n.group === 'topic') ids.add(n.id);
    });
    if (!ids.size) { if (window.showToast) window.showToast('No tools to view yet.', 'info'); return; }
    _neuralFocusIds(ids);
    _neuralCameraTo(ids);
}

// Zoom into one topic + the tools tagged with it
function neuralFocusTopic(topicNode) {
    const gData = window._neuralGData || { nodes: [], links: [] };
    const ids = new Set([topicNode.id]);
    gData.links.forEach(function (l) {
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        if (sid === topicNode.id && tid.indexOf('tool-') === 0) ids.add(tid);
        else if (tid === topicNode.id && sid.indexOf('tool-') === 0) ids.add(sid);
    });
    _neuralFocusIds(ids);
    _neuralCameraTo(ids);
}

// --- Tool detail popup (image + description, open website on demand) ---------
function _neuralEsc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function showNeuralToolPopup(tool) {
    const popup = document.getElementById('neuralToolPopup');
    if (!popup || !tool) return;
    const imgEl = document.getElementById('neuralToolPopupImg');
    if (imgEl) {
        imgEl.innerHTML = tool.img
            ? '<img src="' + _neuralEsc(tool.img) + '" alt="" class="w-full h-full object-cover" onerror="this.remove()">'
            : '<div class="w-full h-full flex items-center justify-center text-white/25" style="background:linear-gradient(135deg,rgba(251,146,60,0.35),rgba(250,204,21,0.12))"><i data-lucide="package" class="w-10 h-10"></i></div>';
    }
    const catEl = document.getElementById('neuralToolPopupCat');
    if (catEl) {
        const c = (typeof getCategoryColor === 'function' && getCategoryColor(tool.cat)) || '#f59e0b';
        catEl.style.background = c;
        catEl.title = tool.cat || '';
    }
    const nameEl = document.getElementById('neuralToolPopupName');
    if (nameEl) nameEl.textContent = tool.n || 'Tool';
    const descEl = document.getElementById('neuralToolPopupDesc');
    if (descEl) descEl.textContent = (tool.desc || tool.d || 'No description yet.').slice(0, 320);
    const topicsEl = document.getElementById('neuralToolPopupTopics');
    if (topicsEl) {
        topicsEl.innerHTML = (tool.topics || []).slice(0, 4).map(function (t) {
            return '<span class="text-[10px] px-2 py-0.5 rounded-full bg-orange-500/10 border border-orange-500/20 text-orange-300">' + _neuralEsc(t) + '</span>';
        }).join('');
    }
    const openBtn = document.getElementById('neuralToolPopupOpen');
    if (openBtn) openBtn.onclick = function () { if (tool.u) window.open(tool.u, '_blank'); };
    const phBtn = document.getElementById('neuralToolPopupPH');
    if (phBtn) phBtn.onclick = function () { if (tool.phUrl) window.open(tool.phUrl, '_blank'); };
    popup.classList.remove('hidden');
    if (typeof initializeIcons === 'function') initializeIcons();
}

function closeNeuralToolPopup() {
    const popup = document.getElementById('neuralToolPopup');
    if (popup) popup.classList.add('hidden');
}

function closeNeuralWeb() {
    closeNeuralToolPopup();
    document.getElementById('neuralWeb').classList.add('hidden');
}

function neuralRebuild(delta) {
    neuralAllMode = false;
    neuralCaps.links = Math.min(2000, Math.max(80, neuralCaps.links + delta));
    NeuralGraph = null;
    initNeuralWeb();
    if (window.showToast) window.showToast('Detail level changed: showing up to ' + neuralCaps.links + ' links.', 'info');
}

// Full view: skip sampling — draw ALL links + tools (tags capped at 500 for readability).
// With 6000+ links this is heavier; use − / + to return to a lower detail level.
function neuralShowAll() {
    neuralAllMode = true;
    neuralCaps.links = 100000; // effectively unlimited
    neuralCaps.tools = 100000;
    neuralCaps.tags = 500;
    NeuralGraph = null;
    initNeuralWeb();
    const total = (window.links || []).length;
    if (window.showToast) window.showToast('🪐 Full view: showing all ' + total + ' links. Press − to reduce load if it lags.', 'info');
}

// Event Listeners
document.addEventListener('DOMContentLoaded', () => {
    const btn = document.getElementById('neuralWebBtn');
    if (btn) btn.addEventListener('click', () => {
        if (typeof ForceGraph3D === 'undefined' && typeof window.loadScript === 'function') {
            window.loadScript('https://unpkg.com/3d-force-graph@1.70.14/dist/3d-force-graph.min.js').then(() => initNeuralWeb());
        } else {
            initNeuralWeb();
        }
    });

    const moreBtn = document.getElementById('neuralMoreBtn');
    if (moreBtn) moreBtn.addEventListener('click', () => neuralRebuild(200));
    const fewerBtn = document.getElementById('neuralFewerBtn');
    if (fewerBtn) fewerBtn.addEventListener('click', () => neuralRebuild(-150));
    const focusBtn = document.getElementById('neuralFocusBtn');
    if (focusBtn) focusBtn.addEventListener('click', () => neuralFocusTools());
    const allBtn = document.getElementById('neuralAllBtn');
    if (allBtn) allBtn.addEventListener('click', () => neuralShowAll());

    const neuralSearch = document.getElementById('neuralSearch');
    if (neuralSearch) {
        neuralSearch.addEventListener('input', (e) => {
            const val = e.target.value.toLowerCase();
            if (!NeuralGraph) return;
            const nodes = NeuralGraph.graphData().nodes;
            const target = nodes.find(n => n.name.toLowerCase().includes(val));
            if (target && val.length > 2) {
                const distance = 100;
                const distRatio = 1 + distance / Math.hypot(target.x, target.y, target.z);
                NeuralGraph.cameraPosition(
                    { x: target.x * distRatio, y: target.y * distRatio, z: target.z * distRatio },
                    target, 2000
                );
                highlightedNodes.clear();
                highlightedLinks.clear();
                highlightedNodes.add(target.id);
                NeuralGraph.graphData().links.forEach(l => {
                    const sid = typeof l.source === 'object' ? l.source.id : l.source;
                    const tid = typeof l.target === 'object' ? l.target.id : l.target;
                    if (sid === target.id || tid === target.id) {
                        highlightedNodes.add(sid === target.id ? tid : sid);
                        highlightedLinks.add(l);
                    }
                });
                NeuralGraph.refresh();
            }
        });
    }
});

window.openNeuralWeb = initNeuralWeb;
window.closeNeuralWeb = closeNeuralWeb;
window.neuralRebuild = neuralRebuild;
window.neuralShowAll = neuralShowAll;
window.neuralFocusTools = neuralFocusTools;
window.neuralFocusTopic = neuralFocusTopic;
window.showNeuralToolPopup = showNeuralToolPopup;
window.closeNeuralToolPopup = closeNeuralToolPopup;
