// Personal cognitive laws: declarative rules, never evaluated JavaScript.
const lawText = value => String(value == null ? '' : value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char]));
const LawEngine = {
    laws: [], customLaws: [],
    defaultLaws: [
        { id: 'law_survival', name: 'Natural Selection Law', description: 'Ideas that are never revisited or used will gradually be forgotten.', trigger: ['link_visited', 'daily_check'], enabled: true,
            execute: async context => {
                const item = context.item;
                if (context.eventType === 'link_visited' && item && item.visitCount < 2 && Date.now() - item.createdAt > 30 * 86400000)
                    return { action: 'tag', item, params: { tag: 'Stale' }, message: 'Applied Law: This idea has gone stale (Natural Selection).' };
                return null;
            } },
        { id: 'law_timeless', name: 'Timeless Connections', description: 'Connecting two ideas far apart in time marks them as Core.', trigger: ['connection_created'], enabled: true,
            execute: async context => {
                const { source, target } = context;
                if (source && target && Math.abs(source.timestamp - target.timestamp) > 180 * 86400000)
                    return { action: 'tag_multiple', targets: [source, target], params: { tag: 'Core' }, message: 'Applied Law: A timeless connection (> 6 months apart) was detected.' };
                return null;
            } },
        { id: 'law_dependencies', name: 'Structural Integrity', description: 'Notes in the "Project" category must have connections.', trigger: ['note_created', 'note_updated'], enabled: true,
            execute: async context => {
                const note = context.item;
                if (note && note.category === 'Project' && (!note.connections || note.connections.length === 0))
                    return { action: 'notify', params: { type: 'warning', text: 'Law Warning: Projects need dependencies (connections).' }, message: 'Applied Law: Structural link missing.' };
                return null;
            } }
    ],
    init() { this.loadLaws(); },
    readStored(key, fallback) {
        try { return JSON.parse(localStorage.getItem(key) || 'null') || fallback; }
        catch (error) { console.warn('Rule settings unavailable; keeping saved bytes', error); return fallback; }
    },
    loadLaws() {
        const stored = this.readStored('linkLumina_laws', {});
        const state = stored && typeof stored === 'object' && !Array.isArray(stored) ? stored : {};
        const custom = this.readStored('linkLumina_custom_laws', []);
        this.customLaws = Array.isArray(custom) ? custom.filter(law => law && typeof law === 'object' &&
            typeof law.id === 'string' && /^[a-zA-Z0-9_-]+$/.test(law.id) &&
            typeof law.name === 'string' && Array.isArray(law.trigger) && law.trigger.every(t => typeof t === 'string') &&
            law.config && ['tag', 'notify'].includes(law.config.actionType)).map(law => ({
                ...law, description: typeof law.description === 'string' ? law.description : '',
                enabled: typeof law.enabled === 'boolean' ? law.enabled : true, isCustom: true, execute: null
            })) : [];
        this.laws = [...this.defaultLaws.map(law => ({ ...law, enabled: typeof state[law.id] === 'boolean' ? state[law.id] : law.enabled })), ...this.customLaws];
    },
    saveLaws() {
        const state = {};
        this.laws.filter(law => !law.isCustom).forEach(law => { state[law.id] = law.enabled; });
        const keys = ['linkLumina_laws', 'linkLumina_custom_laws'];
        let previous;
        try {
            previous = keys.map(key => localStorage.getItem(key));
            localStorage.setItem(keys[0], JSON.stringify(state));
            localStorage.setItem(keys[1], JSON.stringify(this.customLaws));
            return true;
        } catch (error) {
            if (previous) keys.forEach((key, i) => { try { if (previous[i] === null) localStorage.removeItem(key); else localStorage.setItem(key, previous[i]); } catch {} });
            if (window.showToast) window.showToast('Rules could not be saved. Your previous rules are retained.', 'warning');
            console.warn('Rules could not be saved', error);
            return false;
        }
    },
    toggleLaw(id) {
        const law = this.laws.find(item => item.id === id);
        if (!law) return false;
        law.enabled = !law.enabled;
        if (!this.saveLaws()) law.enabled = !law.enabled;
        this.loadLaws(); this.renderModal(); return law.enabled;
    },
    createLaw(name, description, trigger, actionType, actionParam) {
        if (!name || !trigger || !['tag', 'notify'].includes(actionType)) return;
        this.customLaws.push({ id: 'custom_law_' + Date.now() + '_' + Math.random().toString(16).slice(2),
            name, description, trigger: [trigger], enabled: true, isCustom: true,
            config: { trigger, actionType, actionParam }, execute: null });
        if (!this.saveLaws()) this.customLaws.pop();
        this.loadLaws(); this.renderModal();
    },
    deleteLaw(id) {
        if (!confirm('Are you sure you want to delete this law?')) return;
        const previous = this.customLaws;
        this.customLaws = previous.filter(law => law.id !== id);
        if (!this.saveLaws()) this.customLaws = previous;
        this.loadLaws(); this.renderModal();
    },
    async emit(trigger, context = {}) {
        for (const law of this.laws) {
            if (!law.enabled || !law.trigger.includes(trigger)) continue;
            try {
                const result = law.isCustom ? this.evaluateCustomLaw(law, context) : await law.execute({ ...context, eventType: trigger });
                if (result) {
                    await this.enforce(result);
                    if (result.action !== 'notify' && window.showToast) window.showToast(result.message, 'info');
                }
            } catch (error) { console.error('Error executing rule', law.id, error); }
        }
    },
    evaluateCustomLaw(law, context) {
        const { actionType, actionParam } = law.config;
        const message = `Custom law "${law.name}" was activated.`;
        if (actionType === 'notify') return { action: 'notify', params: { type: 'info', text: actionParam || message }, message };
        if (actionType === 'tag') return { action: 'tag', item: context.item, params: { tag: actionParam }, message };
        return null;
    },
    async enforce(result) {
        if (result.action === 'notify') {
            if (window.showToast) window.showToast(result.params.text, result.params.type);
            return;
        }
        if (!result.params || typeof result.params.tag !== 'string' || !result.params.tag) return;
        const targets = result.action === 'tag_multiple' ? result.targets || [] : [result.item];
        for (const item of targets) {
            if (!item) continue;
            const timeline = !!item.eventType || (result.action === 'tag_multiple' && !!item.type);
            if (timeline) {
                if (!item.context || typeof item.context !== 'object') item.context = {};
                if (!Array.isArray(item.context.tags)) item.context.tags = [];
                if (!item.context.tags.includes(result.params.tag)) {
                    item.context.tags.push(result.params.tag);
                    if (window.saveTimelineEventToDB) await window.saveTimelineEventToDB(item);
                }
            } else {
                if (!Array.isArray(item.tags)) item.tags = [];
                if (!item.tags.includes(result.params.tag)) {
                    item.tags.push(result.params.tag);
                    if (item.url && window.saveSingleLink) await window.saveSingleLink(item);
                    if (window.updateAllTags) window.updateAllTags();
                }
            }
        }
    },
    renderModal() {
        const existing = document.getElementById('lawsModal');
        if (existing) existing.remove();
        const modal = document.createElement('div'); modal.id = 'lawsModal';
        modal.className = 'fixed inset-0 z-[60] flex items-center justify-center p-4';
        modal.innerHTML = `<div class="absolute inset-0 bg-black/60" data-close-laws></div>
            <section role="dialog" aria-modal="true" aria-labelledby="lawsTitle" class="glass-card relative w-full max-w-4xl p-6 overflow-y-auto max-h-[85vh]">
            <header class="flex items-center justify-between mb-4"><h2 id="lawsTitle" class="text-xl font-bold">Personal Cognitive Laws</h2><button type="button" data-close-laws aria-label="Close rules" class="p-2">✕</button></header>
            <p class="text-gray-400 mb-4">Simple rules for your saved ideas. Rules run locally.</p>
            <form id="createLawForm" class="grid gap-3 mb-6">
              <label>Law name<input id="newLawName" required class="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10" placeholder="e.g. Focus Law"></label>
              <label>Description<textarea id="newLawDesc" rows="2" class="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10"></textarea></label>
              <label>When<select id="newLawTrigger" class="w-full px-3 py-2 bg-gray-900"><option value="link_visited">Visit a link</option><option value="link_added">Add a link</option><option value="connection_created">Create a connection</option></select></label>
              <label>Then<select id="newLawActionType" class="w-full px-3 py-2 bg-gray-900"><option value="notify">Notify</option><option value="tag">Tag</option></select></label>
              <label>Notification or tag<input id="newLawActionParam" required class="w-full px-3 py-2 rounded-lg bg-white/5 border border-white/10" placeholder="Enter notification text…"></label>
              <button type="submit" class="px-3 py-2 rounded-lg bg-red-600">Save new law</button>
            </form><div class="space-y-3">${this.laws.map(law => `<article class="p-4 rounded-lg border border-white/10">
              <div class="flex items-center justify-between gap-3"><h3 class="font-bold">${lawText(law.name)}</h3><label><input type="checkbox" data-toggle-law="${law.id}" ${law.enabled ? 'checked' : ''}> Enabled</label></div>
              <p class="text-gray-400">${lawText(law.description)}</p><p class="text-sm text-gray-400">${lawText(law.trigger.join(', '))}${law.config ? ' → ' + lawText(law.config.actionType) + ': ' + lawText(law.config.actionParam) : ''}</p>
              ${law.isCustom ? `<button type="button" data-delete-law="${law.id}" class="mt-2 text-red-400">Delete law</button>` : ''}</article>`).join('')}</div></section>`;
        document.body.appendChild(modal);
        modal.querySelectorAll('[data-close-laws]').forEach(button => button.addEventListener('click', () => modal.remove()));
        modal.querySelectorAll('[data-toggle-law]').forEach(input => input.addEventListener('change', () => this.toggleLaw(input.dataset.toggleLaw)));
        modal.querySelectorAll('[data-delete-law]').forEach(button => button.addEventListener('click', () => this.deleteLaw(button.dataset.deleteLaw)));
        modal.querySelector('#createLawForm').addEventListener('submit', event => { event.preventDefault(); window.handleCreateLawSubmit(); });
        modal.querySelector('#newLawActionType').addEventListener('change', window.toggleActionParams);
        modal.addEventListener('keydown', event => {
            if (event.key === 'Escape') modal.remove();
            if (event.key === 'Tab') {
                const controls = [...modal.querySelectorAll('button,input,select,textarea')];
                const first = controls[0], last = controls[controls.length - 1];
                if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
                else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
            }
        });
        modal.querySelector('#newLawName').focus();
    }
};
window.LawEngine = LawEngine;
window.toggleActionParams = function () {
    document.getElementById('newLawActionParam').placeholder = document.getElementById('newLawActionType').value === 'tag' ? 'Enter tag name…' : 'Enter notification text…';
};
window.handleCreateLawSubmit = function () {
    const value = id => document.getElementById(id).value.trim();
    if (value('newLawName') && value('newLawTrigger') && value('newLawActionParam'))
        LawEngine.createLaw(value('newLawName'), value('newLawDesc'), value('newLawTrigger'), value('newLawActionType'), value('newLawActionParam'));
};
