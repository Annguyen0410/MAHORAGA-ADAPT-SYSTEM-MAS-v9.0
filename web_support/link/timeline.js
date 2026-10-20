// ==================== Cognitive Timeline ====================
// Tracks idea development, decisions, and thinking patterns over time

// Timeline state
let timelineEvents = [];
let timelineView = 'timeline'; // 'timeline' or 'graph'

// ==================== Database Operations ====================

async function saveTimelineEventToDB(event) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['timeline'], 'readwrite');
        const store = transaction.objectStore('timeline');
        const request = store.put(event);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

async function getAllTimelineEventsFromDB() {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['timeline'], 'readonly');
        const store = transaction.objectStore('timeline');
        const request = store.getAll();
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
    });
}

async function deleteTimelineEventFromDB(id) {
    return new Promise((resolve, reject) => {
        const transaction = db.transaction(['timeline'], 'readwrite');
        const store = transaction.objectStore('timeline');
        const request = store.delete(id);
        request.onsuccess = () => resolve();
        request.onerror = () => reject(request.error);
    });
}

async function loadTimelineEvents() {
    try {
        timelineEvents = await getAllTimelineEventsFromDB();
        timelineEvents.sort((a, b) => b.timestamp - a.timestamp); // Newest first
    } catch (e) {
        console.error('Error loading timeline:', e);
        timelineEvents = [];
    }
}

// ==================== Event Tracking ====================

// Mood options for tracking
const MOOD_OPTIONS = [
    { id: 'focused', emoji: '🎯', label: 'Focused' },
    { id: 'creative', emoji: '💡', label: 'Creative' },
    { id: 'productive', emoji: '⚡', label: 'Productive' },
    { id: 'relaxed', emoji: '😌', label: 'Relaxed' },
    { id: 'tired', emoji: '😴', label: 'Tired' },
    { id: 'stressed', emoji: '😰', label: 'Stressed' }
];

// Event type icons and colors
const EVENT_TYPES = {
    idea: { icon: '💡', color: '#dc2626', label: 'Idea' },
    action: { icon: '⚡', color: '#3b82f6', label: 'Action' },
    result: { icon: '✅', color: '#10b981', label: 'Result' },
    insight: { icon: '🔮', color: '#b91c1c', label: 'Insight' },
    decision: { icon: '♟️', color: '#ffb300', label: 'Decision' } // Strategic Memory
};

// Auto-detect event type based on source
function detectEventType(eventType) {
    switch (eventType) {
        case 'link_added':
        case 'prompt_saved':
            return 'idea';
        case 'note_created':
        case 'snippet_added':
            return 'action';
        case 'link_visited':
        case 'task_completed':
            return 'result';
        case 'connection_made':
            return 'insight';
        default:
            return 'idea';
    }
}

// Extract tags from content
function extractTagsFromContent(content) {
    if (!content) return [];
    const hashtags = content.match(/#\w+/g) || [];
    return hashtags.map(t => t.slice(1));
}

// Track a cognitive event
async function trackCognitiveEvent(eventType, sourceId, title, content = '', mood = null) {
    const type = detectEventType(eventType);

    const event = {
        id: Date.now().toString() + Math.random().toString(36).substr(2, 9),
        timestamp: Date.now(),
        type,
        eventType,
        sourceId,
        title: title.substring(0, 100),
        content: content.substring(0, 25000),
        mood,
        context: {
            hour: new Date().getHours(),
            dayOfWeek: new Date().getDay(),
            tags: extractTagsFromContent(content)
        },
        connections: []
    };

    // Auto-detect connections based on recent events with similar tags
    const recentEvents = timelineEvents.slice(0, 20);
    for (const recent of recentEvents) {
        if (recent.context?.tags?.some(t => event.context.tags.includes(t))) {
            event.connections.push(recent.id);

            // Cognitive Law Hook: Connection Created
            if (window.LawEngine) {
                window.LawEngine.emit('connection_created', {
                    source: event,
                    target: recent,
                    eventType: 'connection_created'
                });
            }

            // Limit to 3 auto-connections
            if (event.connections.length >= 3) break;
        }
    }

    await saveTimelineEventToDB(event);
    timelineEvents.unshift(event);

    console.log('📝 Tracked cognitive event:', event.title);
    return event;
}

// Find similar past decisions for advisory
function findSimilarDecisions(query) {
    if (!query || query.length < 3) return [];

    const terms = query.toLowerCase().split(' ');

    return timelineEvents
        .filter(e => e.type === 'decision' && e.id.indexOf('decision_') !== -1) // Ensure it's a decision
        .map(e => {
            let score = 0;
            const text = (e.title + ' ' + (e.context?.snapshot?.reasoning || '')).toLowerCase();

            terms.forEach(term => {
                if (text.includes(term)) score += 1;
            });

            return { event: e, score };
        })
        .filter(item => item.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 3)
        .map(item => item.event);
}

// Track a strategic decision snapshot
async function trackDecision(title, context, reasoning, expectedOutcome) {
    const event = {
        id: 'decision_' + Date.now(),
        timestamp: Date.now(),
        type: 'decision', // Explicit type
        eventType: 'strategic_decision',
        title: title,
        content: reasoning, // Main content is the reasoning
        mood: 'focused', // Default mood for decisions
        sourceId: null, // No specific source item, self-contained
        context: {
            hour: new Date().getHours(),
            dayOfWeek: new Date().getDay(),
            tags: [], // Extract tags later if needed
            // Decision Snapshot Data
            snapshot: {
                reasoning: reasoning,
                contextFactors: context, // Array of strings or text
                expectedOutcome: expectedOutcome,
                actualOutcome: '',
                status: 'pending', // pending, success, failure
                lessons: ''
            }
        },
        connections: []
    };

    // Auto-connect to recent relevant events (advisory/context)
    // For now simple recency
    const recentEvents = timelineEvents.slice(0, 5);
    event.connections = recentEvents.map(e => e.id);

    await saveTimelineEventToDB(event);
    timelineEvents.unshift(event);

    // Emit via EventBus
    if (window.EventBus && window.EVENTS) {
        window.EventBus.emit(window.EVENTS.DECISION_LOGGED, { item: event });
    } else if (window.LawEngine) {
        window.LawEngine.emit('decision_logged', { item: event });
    }

    console.log('♟️ Tracked Strategic Decision:', title);
    return event;
}

// ==================== Timeline Rendering ====================

function renderTimelineTab() {
    const listContainer = document.getElementById('timelineGrid');
    const graphContainer = document.getElementById('timelineContainer');
    const splitHandle = document.getElementById('timelineSplitHandle');

    if (!listContainer || !graphContainer) return;

    // Reset visibility
    graphContainer.innerHTML = '';
    graphContainer.classList.add('hidden');
    splitHandle.classList.add('hidden');

    if (timelineEvents.length === 0) {
        listContainer.innerHTML = `
            <div class="text-center py-20 col-span-full">
                <i data-lucide="git-branch" class="w-16 h-16 mx-auto text-gray-600 mb-4"></i>
                <p class="text-xl text-gray-300 mb-2">Your cognitive timeline is empty</p>
                <p class="text-gray-500">Start adding links, notes, and prompts to build your thinking history</p>
            </div>
        `;
        lucide.createIcons();
        return;
    }

    // Always render list at bottom
    renderCognitiveTimeline(listContainer);

    // If graph view is active, render graph at top and show split handle
    if (timelineView === 'graph') {
        graphContainer.classList.remove('hidden');
        splitHandle.classList.remove('hidden');
        renderCognitiveGraph(graphContainer);

        // Re-init resizer if needed
        if (window.LayoutManager && window.LayoutManager.initTimelineResizer) {
            window.LayoutManager.initTimelineResizer();
        }
    }
}

function renderCognitiveTimeline(container) {
    // ... existing list rendering code ...
    // Reuse existing logic but ensure it targets the list container

    const grouped = {};
    for (const event of timelineEvents) {
        const date = new Date(event.timestamp);
        const dateKey = date.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' });
        if (!grouped[dateKey]) grouped[dateKey] = [];
        grouped[dateKey].push(event);
    }

    let html = '<div class="timeline-container space-y-8">';
    // ... rest of list generation ...
    for (const [date, events] of Object.entries(grouped)) {
        html += `
            <div class="timeline-day">
                <h3 class="text-lg font-bold text-red-400 mb-4 flex items-center gap-2">
                    <i data-lucide="calendar" class="w-5 h-5"></i>
                    ${date}
                </h3>
                <div class="space-y-3 pl-6 border-l-2 border-red-500/30">
        `;
        for (const event of events) {
            const typeInfo = EVENT_TYPES[event.type] || EVENT_TYPES.idea;
            const time = new Date(event.timestamp).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
            const moodEmoji = event.mood ? MOOD_OPTIONS.find(m => m.id === event.mood)?.emoji || '' : '';

            html += `
                <div class="timeline-event glass-card p-4 relative ml-4 hover:scale-[1.02] transition-transform cursor-pointer" 
                     onclick="showTimelineEventDetail('${event.id}')"
                     style="border-left: 3px solid ${typeInfo.color}">
                    <div class="absolute -left-[27px] w-4 h-4 rounded-full bg-gray-900 border-2" 
                         style="border-color: ${typeInfo.color}"></div>
                    <div class="flex items-start justify-between gap-2">
                        <div class="flex-1">
                            <div class="flex items-center gap-2 mb-1">
                                <span class="text-lg">${typeInfo.icon}</span>
                                <span class="text-sm font-medium text-white">${escapeHtml(event.title)}</span>
                                ${moodEmoji ? `<span class="text-sm">${moodEmoji}</span>` : ''}
                            </div>
                            <p class="text-xs text-gray-400">${time} • ${typeInfo.label}</p>
                            ${event.connections.length > 0 ? `
                                <p class="text-xs text-red-400 mt-1">
                                    <i data-lucide="link" class="w-3 h-3 inline"></i>
                                    ${event.connections.length} connection(s)
                                </p>
                            ` : ''}
                        </div>
                        <span class="text-xs px-2 py-1 rounded-full bg-white/10 text-gray-400">${event.eventType.replace('_', ' ')}</span>
                    </div>
                </div>
            `;
        }
        html += '</div></div>';
    }
    html += '</div>';
    container.innerHTML = html;
    lucide.createIcons();
}

function renderCognitiveGraph(container) {
    const graphContainerId = 'timelineGraph';

    // Resolve a valid container element; bail out if none exists
    container = typeof container === 'string' ? document.getElementById(container) : container;
    container = container || document.getElementById('timelineContainer') || document.getElementById(graphContainerId)?.parentElement;
    if (!container) return;

    // Use CSS variable for height
    container.innerHTML = `
        <div class="relative w-full glass-card overflow-hidden transition-all duration-300" id="graphWrapper" style="height: var(--timeline-graph-height, 600px);">
            <div id="${graphContainerId}" class="w-full h-full"></div>
            
            <!-- Legend -->
            <div class="absolute bottom-4 left-4 pointer-events-none bg-black/40 backdrop-blur rounded-lg p-3 border border-white/10">
                <div class="flex items-center gap-2 mb-2">
                    <span class="w-3 h-3 rounded-full bg-red-500 shadow-[0_0_10px_#dc2626]"></span>
                    <span class="text-xs text-red-200">Idea</span>
                </div>
                <div class="flex items-center gap-2 mb-2">
                    <span class="w-3 h-3 rounded-full bg-blue-500 shadow-[0_0_10px_#3b82f6]"></span>
                    <span class="text-xs text-blue-200">Action</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="w-3 h-3 rounded-full bg-green-500 shadow-[0_0_10px_#10b981]"></span>
                    <span class="text-xs text-green-200">Result</span>
                </div>
            </div>

            <!-- Controls Overlay -->
            <div class="absolute top-4 right-4 flex gap-2">
                <button onclick="toggleGraphFullScreen()" class="p-2 rounded-lg bg-white/10 hover:bg-white/20 text-white transition-colors" title="Toggle Full Screen">
                    <i data-lucide="maximize-2" class="w-5 h-5"></i>
                </button>
            </div>

            <div class="absolute bottom-4 right-4 text-xs text-gray-400 pointer-events-none text-right">
                Scroll to zoom • Drag to rotate<br>Click to focus
            </div>
        </div>
    `;

    lucide.createIcons();

    if (typeof ForceGraph3D === 'undefined') {
        const el = document.getElementById(graphContainerId);
        if (el) el.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400"><p>Loading 3D library...</p></div>';
        if (typeof window.loadScript === 'function') {
            window.loadScript('https://unpkg.com/3d-force-graph@1.70.14/dist/3d-force-graph.min.js').then(function () {
                renderCognitiveGraph(container);
            }).catch(function () {
                if (el) el.innerHTML = '<div class="flex items-center justify-center h-full text-gray-400"><p>Could not load the 3D library.</p></div>';
            });
        }
        return;
    }

    const graphData = buildGraphData();

    // Ordinal Layout: Sort by time and space evenly
    // This removes gaps caused by time periods with no activity
    const sortedEvents = timelineEvents.slice().sort((a, b) => a.timestamp - b.timestamp);
    const spacing = 100; // Space between nodes in units

    graphData.nodes.forEach(node => {
        const index = sortedEvents.findIndex(e => e.id === node.id);
        if (index !== -1) {
            // Position along X axis based on rank (order), not raw timestamp
            // Centered around 0
            node.fx = (index - (sortedEvents.length - 1) / 2) * spacing;
            // Free Y/Z
        }
    });

    // Initialize Graph
    const elem = document.getElementById(graphContainerId);
    window.timelineGraphInstance = ForceGraph3D()(elem)
        .backgroundColor('rgba(0,0,0,0)')
        .graphData(graphData)
        .nodeLabel('title')
        .nodeRelSize(6)
        .nodeOpacity(0.9)
        .linkWidth(1.5)
        .linkColor(() => 'rgba(100, 100, 255, 0.2)')
        .linkDirectionalParticles(2)
        .linkDirectionalParticleWidth(2)
        .linkDirectionalParticleSpeed(0.005)
        .nodeThreeObject(node => {
            const typeInfo = EVENT_TYPES[node.type] || EVENT_TYPES.idea;
            const color = typeInfo.color;

            const group = new THREE.Group();

            // Decision Nodes = CUBES ♟️
            if (node.type === 'decision') {
                const geometry = new THREE.BoxGeometry(node.val * 3, node.val * 3, node.val * 3);
                const material = new THREE.MeshLambertMaterial({
                    color: node.context?.snapshot?.status === 'success' ? '#10b981' :
                        node.context?.snapshot?.status === 'failure' ? '#ef4444' :
                            color, // Pending = Default Amber
                    transparent: true,
                    opacity: 0.95
                });
                const cube = new THREE.Mesh(geometry, material);
                group.add(cube);

                // Add a glow ring
                if (typeof document !== 'undefined') {
                    const canvas = document.createElement('canvas');
                    canvas.width = 64; canvas.height = 64;
                    const ctx = canvas.getContext('2d');
                    ctx.beginPath();
                    ctx.arc(32, 32, 28, 0, 2 * Math.PI);
                    ctx.strokeStyle = hexToRgba(color, 0.8);
                    ctx.lineWidth = 4;
                    ctx.stroke();
                    const texture = new THREE.CanvasTexture(canvas);
                    const spriteMat = new THREE.SpriteMaterial({ map: texture });
                    const ring = new THREE.Sprite(spriteMat);
                    ring.scale.set(node.val * 5, node.val * 5, 1);
                    group.add(ring);
                }
            } else {
                // Sphere for others
                const geometry = new THREE.SphereGeometry(node.val * 2, 16, 16);
                const material = new THREE.MeshLambertMaterial({
                    color: color,
                    transparent: true,
                    opacity: 0.9
                });
                const sphere = new THREE.Mesh(geometry, material);
                group.add(sphere);
            }

            // Glow Sprite (Common)
            if (typeof document !== 'undefined') {
                const canvas = document.createElement('canvas');
                canvas.width = 64;
                canvas.height = 64;
                const context = canvas.getContext('2d');
                const gradient = context.createRadialGradient(32, 32, 0, 32, 32, 32);
                const glowColor = node.color || color;
                gradient.addColorStop(0, hexToRgba(glowColor, 1));
                gradient.addColorStop(0.2, hexToRgba(glowColor, 0.6));
                gradient.addColorStop(0.5, hexToRgba(glowColor, 0.2));
                gradient.addColorStop(1, 'rgba(0,0,0,0)');
                context.fillStyle = gradient;
                context.fillRect(0, 0, 64, 64);

                const texture = new THREE.CanvasTexture(canvas);
                const spriteMaterial = new THREE.SpriteMaterial({ map: texture, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false });
                const sprite = new THREE.Sprite(spriteMaterial);
                sprite.scale.set(20 + node.val * 2, 20 + node.val * 2, 1);
                group.add(sprite);
            }

            return group;
        })
        .onNodeClick(node => {
            const distance = 60;
            const distRatio = 1 + distance / Math.hypot(node.x, node.y, node.z);

            window.timelineGraphInstance.cameraPosition(
                { x: node.x, y: node.y + 20, z: node.z + distance }, // Fly to offset position
                node, // Look at node
                1500  // Duration
            );

            showTimelineEventDetail(node.id);
        });

    // Lights
    const ambientLight = new THREE.AmbientLight(0xcccccc);
    window.timelineGraphInstance.scene().add(ambientLight);
    const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
    directionalLight.position.set(0, 50, 50);
    window.timelineGraphInstance.scene().add(directionalLight);
}

// Global toggle function
window.toggleGraphFullScreen = function () {
    const wrapper = document.getElementById('graphWrapper');
    const isFull = wrapper.classList.contains('fixed');
    const container = document.getElementById('timelineGraph');

    if (!isFull) {
        // Enter Full Screen
        wrapper.classList.remove('relative', 'w-full', 'h-[600px]');
        wrapper.classList.add('fixed', 'inset-0', 'z-50', 'bg-gray-950/95', 'backdrop-blur-md', 'h-screen');
        // Update icon
        wrapper.querySelector('button i').setAttribute('data-lucide', 'minimize-2');
    } else {
        // Exit Full Screen
        wrapper.classList.add('relative', 'w-full', 'h-[600px]');
        wrapper.classList.remove('fixed', 'inset-0', 'z-50', 'bg-gray-950/95', 'backdrop-blur-md', 'h-screen');
        wrapper.querySelector('button i').setAttribute('data-lucide', 'maximize-2');
    }

    lucide.createIcons();

    // Resize graph
    setTimeout(() => {
        if (window.timelineGraphInstance) {
            const width = container.clientWidth;
            const height = container.clientHeight;
            window.timelineGraphInstance.width(width);
            window.timelineGraphInstance.height(height);
        }
    }, 300); // Wait for transition
};

// Helper to convert hex to rgba
function hexToRgba(hex, alpha) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function buildGraphData() {
    const nodes = timelineEvents.map(e => ({
        id: e.id,
        title: e.title,
        type: e.type,
        val: e.connections.length + 1
    }));

    const links = [];
    for (const event of timelineEvents) {
        for (const connId of event.connections) {
            if (timelineEvents.some(e => e.id === connId)) {
                links.push({ source: event.id, target: connId });
            }
        }
    }

    return { nodes, links };
}

// ==================== Analytics ====================

function calculateTimelineAnalytics() {
    if (timelineEvents.length === 0) return null;

    // Peak hours
    const hourCounts = {};
    for (const e of timelineEvents) {
        const hour = e.context?.hour ?? new Date(e.timestamp).getHours();
        hourCounts[hour] = (hourCounts[hour] || 0) + 1;
    }
    const peakHour = Object.entries(hourCounts).sort((a, b) => b[1] - a[1])[0]?.[0];

    // Core ideas (frequent tags)
    const tagCounts = {};
    for (const e of timelineEvents) {
        for (const tag of e.context?.tags || []) {
            tagCounts[tag] = (tagCounts[tag] || 0) + 1;
        }
    }
    const coreIdeas = Object.entries(tagCounts)
        .filter(([_, count]) => count >= 3)
        .sort((a, b) => b[1] - a[1])
        .slice(0, 5)
        .map(([tag]) => tag);

    // Type distribution
    const typeCounts = {};
    for (const e of timelineEvents) {
        typeCounts[e.type] = (typeCounts[e.type] || 0) + 1;
    }

    // Mood distribution
    const moodCounts = {};
    for (const e of timelineEvents) {
        if (e.mood) {
            moodCounts[e.mood] = (moodCounts[e.mood] || 0) + 1;
        }
    }

    // Activity streak
    const dates = [...new Set(timelineEvents.map(e =>
        new Date(e.timestamp).toDateString()
    ))].sort((a, b) => new Date(b) - new Date(a));

    let streak = 0;
    let checkDate = new Date();
    for (const dateStr of dates) {
        const eventDate = new Date(dateStr);
        const diff = Math.floor((checkDate - eventDate) / (1000 * 60 * 60 * 24));
        if (diff <= 1) {
            streak++;
            checkDate = eventDate;
        } else {
            break;
        }
    }

    return {
        totalEvents: timelineEvents.length,
        peakHour: peakHour ? `${peakHour}:00` : 'N/A',
        coreIdeas,
        typeCounts,
        moodCounts,
        streak,
        avgConnectionsPerEvent: (timelineEvents.reduce((sum, e) => sum + e.connections.length, 0) / timelineEvents.length).toFixed(1)
    };
}

function renderAnalyticsDashboard() {
    const analytics = calculateTimelineAnalytics();
    if (!analytics) return '';

    return `
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
            <div class="glass-card p-4 text-center">
                <p class="text-3xl font-bold text-white">${analytics.totalEvents}</p>
                <p class="text-xs text-gray-400">Total Events</p>
            </div>
            <div class="glass-card p-4 text-center">
                <p class="text-3xl font-bold text-red-400">${analytics.peakHour}</p>
                <p class="text-xs text-gray-400">Peak Hour</p>
            </div>
            <div class="glass-card p-4 text-center">
                <p class="text-3xl font-bold text-green-400">${analytics.streak}</p>
                <p class="text-xs text-gray-400">Day Streak</p>
            </div>
            <div class="glass-card p-4 text-center">
                <p class="text-3xl font-bold text-red-400">${analytics.avgConnectionsPerEvent}</p>
                <p class="text-xs text-gray-400">Avg Connections</p>
            </div>
        </div>
        ${analytics.coreIdeas.length > 0 ? `
            <div class="mb-4">
                <p class="text-sm text-gray-400 mb-2">Core Ideas:</p>
                <div class="flex flex-wrap gap-2">
                    ${analytics.coreIdeas.map(tag => `
                        <span class="px-3 py-1 rounded-full bg-red-500/20 text-red-300 text-sm">#${tag}</span>
                    `).join('')}
                </div>
            </div>
        ` : ''}
    `;
}

// ==================== Event Details Modal & Review ====================

window.updateDecisionSnapshot = async function (id) {
    const event = timelineEvents.find(e => e.id === id);
    if (!event || !event.context.snapshot) return;

    const newStatus = document.getElementById('reviewStatus').value;
    const newOutcome = document.getElementById('reviewActually').value;
    const newLessons = document.getElementById('reviewLessons').value;

    event.context.snapshot.status = newStatus;
    event.context.snapshot.actualOutcome = newOutcome;
    event.context.snapshot.lessons = newLessons;

    // Change event color based on status if needed (re-rendering graph handles node color)

    await saveTimelineEventToDB(event);

    // Emit Decision Reviewed event
    if (window.EventBus && window.EVENTS) {
        window.EventBus.emit(window.EVENTS.DECISION_REVIEWED, {
            item: event,
            status: newStatus,
            lessons: newLessons
        });
    }

    showToast('Decision Review Updated!', 'success');

    // Suggest creating a Law if decision has lessons learned
    if ((newStatus === 'success' || newStatus === 'failure') && newLessons && newLessons.length > 10) {
        setTimeout(() => {
            const suggestion = confirm(`💡 You drew a lesson: "${newLessons.substring(0, 50)}..."\n\n` +
`Want to turn this lesson into a Cognitive Law that reminds you automatically in the future?`
            );
            if (suggestion && window.LawEngine && window.LawEngine.renderModal) {
                window.LawEngine.renderModal();
                // Pre-fill suggestion (could be enhanced later)
            }
        }, 500);
    }

    // Refresh Modal
    showTimelineEventDetail(id);

    // Refresh Graph if open
    if (timelineView === 'graph') {
        const elem = document.getElementById('timelineGraph');
        if (elem) renderCognitiveGraph(document.getElementById('timelineContainer') || elem);
    }
}

function showTimelineEventDetail(eventId) {
    const event = timelineEvents.find(e => e.id === eventId);
    if (!event) return;

    const typeInfo = EVENT_TYPES[event.type] || EVENT_TYPES.idea;
    const moodInfo = event.mood ? MOOD_OPTIONS.find(m => m.id === event.mood) : null;
    const isDecision = event.type === 'decision';

    const modal = document.createElement('div');
    modal.className = 'fixed inset-0 z-50 flex items-center justify-center p-4';
    modal.innerHTML = `
        <div class="absolute inset-0 bg-black/60 backdrop-blur-sm" onclick="this.parentElement.remove()"></div>
        <div class="glass-card relative z-10 w-full max-w-lg p-6 max-h-[90vh] overflow-y-auto">
            <div class="flex items-center gap-3 mb-4">
                <span class="text-3xl">${typeInfo.icon}</span>
                <div>
                    <h3 class="text-xl font-bold text-white">${escapeHtml(event.title)}</h3>
                    <p class="text-sm text-gray-400">
                        ${typeInfo.label} • ${new Date(event.timestamp).toLocaleString('en-US')}
                        ${isDecision && event.context?.snapshot?.status ?
            `<span class="ml-2 px-2 py-0.5 rounded text-xs uppercase font-bold
                                ${event.context.snapshot.status === 'success' ? 'bg-green-500/20 text-green-300' :
                event.context.snapshot.status === 'failure' ? 'bg-red-500/20 text-red-300' :
                    'bg-red-500/20 text-red-300'}">
                                ${event.context.snapshot.status}
                            </span>` : ''}
                    </p>
                </div>
            </div>
            
            ${event.content ? `
                <div class="mb-4 p-3 rounded-lg bg-white/5">
                    <p class="text-gray-300 text-sm whitespace-pre-wrap">${escapeHtml(event.content)}</p>
                </div>
            ` : ''}

            <!-- Strategic Memory Section -->
            ${isDecision && event.context?.snapshot ? `
                <div class="mb-6 border-t border-white/10 pt-4">
                    <h4 class="text-red-500 font-bold mb-3 flex items-center gap-2">
                        <i data-lucide="brain-circuit" class="w-4 h-4"></i> Strategic Snapshot
                    </h4>
                    
                    <div class="grid gap-3 mb-4">
                        <div class="bg-black/30 p-3 rounded-lg border border-white/5">
                            <span class="text-xs text-gray-500 block mb-1">REASONING (Why)</span>
                            <p class="text-sm text-gray-200">${escapeHtml(event.context.snapshot.reasoning)}</p>
                        </div>
                        <div class="bg-black/30 p-3 rounded-lg border border-white/5">
                            <span class="text-xs text-gray-500 block mb-1">EXPECTED OUTCOME</span>
                            <p class="text-sm text-gray-200">${escapeHtml(event.context.snapshot.expectedOutcome)}</p>
                        </div>
                        <div class="bg-black/30 p-3 rounded-lg border border-white/5">
                            <span class="text-xs text-gray-500 block mb-1">CONTEXT FACTORS</span>
                            <div class="flex flex-wrap gap-1">
                                ${event.context.snapshot.contextFactors?.map(f => `<span class="px-2 py-0.5 bg-white/10 rounded text-xs text-gray-300">${escapeHtml(f)}</span>`).join('') || '-'}
                            </div>
                        </div>
                    </div>

                    <!-- Review Form -->
                    <div class="bg-red-500/5 p-4 rounded-xl border border-red-500/20">
                        <h5 class="text-sm font-bold text-red-200 mb-3">Review & Learn</h5>
                        
                        <div class="space-y-3">
                            <div>
                                <label class="text-xs text-gray-400 block mb-1">Status</label>
                                <select id="reviewStatus" class="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-sm text-white focus:border-red-500 disabled:opacity-50">
                                    <option value="pending" ${event.context.snapshot.status === 'pending' ? 'selected' : ''}>⏳ Pending</option>
                                    <option value="success" ${event.context.snapshot.status === 'success' ? 'selected' : ''}>🟢 Success</option>
                                    <option value="failure" ${event.context.snapshot.status === 'failure' ? 'selected' : ''}>🔴 Failure</option>
                                </select>
                            </div>
                            <div>
                                <label class="text-xs text-gray-400 block mb-1">Actual Outcome</label>
                                <textarea id="reviewActually" rows="2" class="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-sm text-white focus:border-red-500" placeholder="What actually happened?">${escapeHtml(event.context.snapshot.actualOutcome || '')}</textarea>
                            </div>
                            <div>
                                <label class="text-xs text-gray-400 block mb-1">Lessons Learned</label>
                                <textarea id="reviewLessons" rows="2" class="w-full bg-black/40 border border-white/10 rounded px-2 py-1 text-sm text-white focus:border-red-500" placeholder="What to avoid/repeat next time?">${escapeHtml(event.context.snapshot.lessons || '')}</textarea>
                            </div>
                            <button onclick="window.updateDecisionSnapshot('${event.id}')" class="w-full py-2 bg-red-500/20 hover:bg-red-500/30 text-red-300 rounded text-sm font-medium transition-colors">
                                Update Review
                            </button>
                        </div>
                    </div>
                </div>
            ` : ''}
            
            ${moodInfo ? `
                <div class="mb-4">
                    <span class="text-gray-400 text-sm">Mood:</span>
                    <span class="ml-2">${moodInfo.emoji} ${moodInfo.label}</span>
                </div>
            ` : ''}
            
            ${event.context?.tags?.length > 0 ? `
                <div class="mb-4">
                    <span class="text-gray-400 text-sm">Tags:</span>
                    <div class="flex flex-wrap gap-1 mt-1">
                        ${event.context.tags.map(t => `<span class="px-2 py-0.5 rounded bg-red-500/20 text-red-300 text-xs">#${t}</span>`).join('')}
                    </div>
                </div>
            ` : ''}
            
            ${event.connections.length > 0 ? `
                <div class="mb-4">
                    <span class="text-gray-400 text-sm">Connected to:</span>
                    <div class="space-y-1 mt-1">
                        ${event.connections.map(cid => {
                        const conn = timelineEvents.find(e => e.id === cid);
                        return conn ? `<p class="text-sm text-blue-400 cursor-pointer hover:underline" onclick="this.closest('.fixed').remove(); showTimelineEventDetail('${cid}')">${EVENT_TYPES[conn.type]?.icon || '•'} ${escapeHtml(conn.title)}</p>` : '';
                    }).join('')}
                    </div>
                </div>
            ` : ''}
            
            <div class="flex gap-2 mt-6 border-t border-white/10 pt-4">
                <button onclick="deleteTimelineEvent('${event.id}')" class="px-4 py-2 rounded-lg bg-red-500/20 text-red-400 hover:bg-red-500/30 transition-colors">
                    <i data-lucide="trash-2" class="w-4 h-4 inline"></i> Delete
                </button>
                <button onclick="this.closest('.fixed').remove()" class="flex-1 px-4 py-2 rounded-lg bg-white/10 text-white hover:bg-white/20 transition-colors">
                    Close
                </button>
            </div>
        </div>
    `;
    document.body.appendChild(modal);
    lucide.createIcons();
}

async function deleteTimelineEvent(id) {
    if (!confirm('Delete this timeline event?')) return;

    await deleteTimelineEventFromDB(id);
    timelineEvents = timelineEvents.filter(e => e.id !== id);

    // Remove modal
    document.querySelector('.fixed.z-50')?.remove();

    renderTimelineTab();
    showToast('Event deleted', 'success');
}

// ==================== View Toggle ====================

function toggleTimelineView() {
    timelineView = timelineView === 'timeline' ? 'graph' : 'timeline';
    renderTimelineTab();

    // Update toggle button
    const btn = document.getElementById('timelineViewToggle');
    if (btn) {
        btn.innerHTML = timelineView === 'timeline'
            ? '<i data-lucide="share-2" class="w-4 h-4"></i> Graph View'
            : '<i data-lucide="list" class="w-4 h-4"></i> Timeline View';
        lucide.createIcons();
    }
}

// ==================== Expose Globally ====================

window.trackCognitiveEvent = trackCognitiveEvent;
window.loadTimelineEvents = loadTimelineEvents;
window.renderTimelineTab = renderTimelineTab;
window.showTimelineEventDetail = showTimelineEventDetail;
window.deleteTimelineEvent = deleteTimelineEvent;
window.toggleTimelineView = toggleTimelineView;
window.renderAnalyticsDashboard = renderAnalyticsDashboard;
window.MOOD_OPTIONS = MOOD_OPTIONS;
window.saveTimelineEventToDB = saveTimelineEventToDB;
window.findSimilarDecisions = findSimilarDecisions;

// Expose timelineEvents array getter/setter
Object.defineProperty(window, 'timelineEvents', {
    get: function () { return timelineEvents; },
    set: function (val) { timelineEvents = val; }
});
