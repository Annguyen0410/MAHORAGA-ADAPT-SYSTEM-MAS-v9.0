// Layout customization: bounded sidebar, grid density and graph height.
const LayoutManager = {
    defaults: { sidebarWidth: 256, cardMinWidth: 300, minSidebarWidth: 200, maxSidebarWidth: 600,
        minCardWidth: 200, maxCardWidth: 600, timelineGraphHeight: 600, minGraphHeight: 300, maxGraphHeight: 1200 },
    init() {
        this.loadSettings(); this.initSidebarResizer(); this.initTimelineResizer();
        this.initGridDensityControl(); this.applyLayout();
    },
    loadSettings() {
        this.settings = { ...this.defaults };
        try {
            const saved = JSON.parse(localStorage.getItem('linkLumina_layout') || 'null');
            if (saved && typeof saved === 'object' && !Array.isArray(saved)) {
                for (const key of ['sidebarWidth', 'cardMinWidth', 'timelineGraphHeight']) {
                    if (typeof saved[key] === 'number' && Number.isFinite(saved[key])) this.settings[key] = saved[key];
                }
            }
        } catch (error) { console.warn('Layout settings unavailable; using defaults', error); }
        this.settings.sidebarWidth = Math.max(200, Math.min(600, this.settings.sidebarWidth));
        this.settings.cardMinWidth = Math.max(200, Math.min(600, this.settings.cardMinWidth));
        this.settings.timelineGraphHeight = Math.max(300, Math.min(1200, this.settings.timelineGraphHeight));
    },
    saveSettings() {
        try { localStorage.setItem('linkLumina_layout', JSON.stringify(this.settings)); }
        catch (error) {
            console.warn('Layout could not be saved', error);
            if (window.showToast) window.showToast('Layout could not be saved on this device.', 'warning');
        }
    },
    applyLayout() {
        const root = document.documentElement;
        root.style.setProperty('--sidebar-width', `${this.settings.sidebarWidth}px`);
        root.style.setProperty('--card-min-width', `${this.settings.cardMinWidth}px`);
        root.style.setProperty('--timeline-graph-height', `${this.settings.timelineGraphHeight}px`);
        const slider = document.getElementById('gridDensitySlider');
        if (slider) slider.value = this.settings.cardMinWidth;
        const graph = window.timelineGraphInstance;
        const container = document.getElementById('timelineGraph');
        if (graph && graph.height && container) {
            graph.width(container.clientWidth); graph.height(this.settings.timelineGraphHeight);
        }
    },
    initSidebarResizer() {
        const handle = document.getElementById('sidebarResizer');
        if (!handle || !document.getElementById('folderSidebar')) return;
        let active = false, raf = null;
        handle.addEventListener('mousedown', event => {
            active = true; event.preventDefault();
            document.body.classList.add('resizing-col'); handle.classList.add('active');
        });
        document.addEventListener('mousemove', event => {
            if (!active) return;
            if (raf !== null) cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => {
                raf = null;
                this.settings.sidebarWidth = Math.max(this.settings.minSidebarWidth, Math.min(this.settings.maxSidebarWidth, event.clientX));
                this.applyLayout();
            });
        });
        document.addEventListener('mouseup', () => {
            if (!active) return;
            // Flush the last pointer position before saving, not after it.
            if (raf !== null) { cancelAnimationFrame(raf); raf = null; }
            active = false; document.body.classList.remove('resizing-col'); handle.classList.remove('active'); this.saveSettings();
        });
    },
    initTimelineResizer() {
        const handle = document.getElementById('timelineSplitHandle');
        if (!handle) return;
        let active = false, startY = 0, startHeight = 0, raf = null;
        handle.addEventListener('mousedown', event => {
            const wrapper = document.getElementById('graphWrapper');
            if (!wrapper) return;
            active = true; startY = event.clientY; startHeight = wrapper.offsetHeight;
            event.preventDefault(); document.body.classList.add('resizing-row'); handle.classList.add('active');
        });
        document.addEventListener('mousemove', event => {
            if (!active) return;
            if (raf !== null) cancelAnimationFrame(raf);
            raf = requestAnimationFrame(() => {
                raf = null;
                this.settings.timelineGraphHeight = Math.max(this.settings.minGraphHeight, Math.min(this.settings.maxGraphHeight, startHeight + event.clientY - startY));
                this.applyLayout();
            });
        });
        document.addEventListener('mouseup', () => {
            if (!active) return;
            if (raf !== null) { cancelAnimationFrame(raf); raf = null; }
            active = false; document.body.classList.remove('resizing-row'); handle.classList.remove('active'); this.saveSettings();
        });
    },
    initGridDensityControl() {
        const slider = document.getElementById('gridDensitySlider');
        if (!slider) return;
        slider.min = this.settings.minCardWidth; slider.max = this.settings.maxCardWidth; slider.value = this.settings.cardMinWidth;
        slider.addEventListener('input', event => {
            const width = Number(event.target.value);
            if (Number.isFinite(width)) this.settings.cardMinWidth = Math.max(200, Math.min(600, width));
            this.applyLayout();
        });
        slider.addEventListener('change', () => this.saveSettings());
    }
};
window.LayoutManager = LayoutManager;
window.resetLayout = function () {
    LayoutManager.settings = { ...LayoutManager.defaults }; LayoutManager.saveSettings(); LayoutManager.applyLayout();
};
