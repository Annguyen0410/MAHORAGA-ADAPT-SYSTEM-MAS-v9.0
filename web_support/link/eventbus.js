// ==================== Global Event Bus ====================
// Central messaging system for all LinkLumina modules

const EventBus = {
    listeners: {},
    history: [], // Keep last 100 events for debugging/analytics
    DEBUG: false, // Set true to see every subscribe/emit in console

    // Subscribe to an event
    on(event, callback) {
        if (!this.listeners[event]) {
            this.listeners[event] = [];
        }
        this.listeners[event].push(callback);
        if (EventBus.DEBUG) console.log(`📡 EventBus: Subscribed to "${event}"`);
        return () => this.off(event, callback); // Return unsubscribe function
    },

    // Unsubscribe from an event
    off(event, callback) {
        if (!this.listeners[event]) return;
        this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    },

    // Emit an event to all subscribers
    emit(event, data = {}) {
        const eventData = {
            type: event,
            timestamp: Date.now(),
            data
        };

        // Store in history
        this.history.push(eventData);
        if (this.history.length > 100) this.history.shift();

        if (EventBus.DEBUG) console.log(`📢 EventBus: Emitting "${event}"`, data);

        // Notify all listeners
        if (this.listeners[event]) {
            this.listeners[event].forEach(callback => {
                try {
                    callback(data, eventData);
                } catch (e) {
                    console.error(`EventBus listener error for "${event}":`, e);
                }
            });
        }

        // Also notify wildcard listeners
        if (this.listeners['*']) {
            this.listeners['*'].forEach(callback => {
                try {
                    callback(data, eventData);
                } catch (e) {
                    console.error(`EventBus wildcard listener error:`, e);
                }
            });
        }
    },

    // Get event history (for debugging/analytics)
    getHistory(eventType = null) {
        if (eventType) {
            return this.history.filter(e => e.type === eventType);
        }
        return [...this.history];
    },

    // Clear all listeners (useful for testing)
    clear() {
        this.listeners = {};
        this.history = [];
    }
};

// ==================== Standard Events ====================
// Define event names as constants for consistency

const EVENTS = {
    // Link Events
    LINK_ADDED: 'link:added',
    LINK_UPDATED: 'link:updated',
    LINK_DELETED: 'link:deleted',
    LINK_VISITED: 'link:visited',
    LINK_FAVORITED: 'link:favorited',
    LINK_MOVED: 'link:moved',

    // Folder Events
    FOLDER_CREATED: 'folder:created',
    FOLDER_DELETED: 'folder:deleted',
    FOLDER_NESTED: 'folder:nested',

    // Decision Events
    DECISION_LOGGED: 'decision:logged',
    DECISION_UPDATED: 'decision:updated',
    DECISION_REVIEWED: 'decision:reviewed',

    // Timeline Events
    TIMELINE_EVENT_ADDED: 'timeline:event_added',
    TIMELINE_CONNECTION_CREATED: 'timeline:connection_created',

    // Law Events
    LAW_TRIGGERED: 'law:triggered',
    LAW_ENFORCED: 'law:enforced',
    LAW_CREATED: 'law:created',

    // System Events
    APP_INITIALIZED: 'app:initialized',
    DATA_EXPORTED: 'data:exported',
    DATA_IMPORTED: 'data:imported',
    SYNC_COMPLETED: 'sync:completed'
};

// ==================== Auto-Connect Modules ====================
// Setup listeners when EventBus loads

document.addEventListener('DOMContentLoaded', () => {
    // Connect to Timeline
    EventBus.on(EVENTS.LINK_ADDED, (data) => {
        if (window.trackCognitiveEvent) {
            window.trackCognitiveEvent('link_added', data.item?.id, data.item?.title, `Added link: ${data.item?.url}`);
        }
    });

    EventBus.on(EVENTS.LINK_VISITED, (data) => {
        if (window.trackCognitiveEvent) {
            window.trackCognitiveEvent('link_visited', data.item?.id, data.item?.title, `Visited: ${data.item?.url}`);
        }
    });

    // Connect to LawEngine
    EventBus.on(EVENTS.LINK_ADDED, (data) => {
        if (window.LawEngine) {
            window.LawEngine.emit('link_added', data);
        }
    });

    EventBus.on(EVENTS.LINK_VISITED, (data) => {
        if (window.LawEngine) {
            window.LawEngine.emit('link_visited', data);
        }
    });

    EventBus.on(EVENTS.DECISION_LOGGED, (data) => {
        if (window.LawEngine) {
            window.LawEngine.emit('decision_logged', data);
        }
    });

    // Connect to Stats/Analytics (future module)
    EventBus.on('*', (data, event) => {
        // Could send to analytics module here
        // window.Analytics?.track(event.type, data);
    });

    if (EventBus.DEBUG) console.log('🚀 EventBus: All modules connected');
});

// Expose globally
window.EventBus = EventBus;
window.EVENTS = EVENTS;
