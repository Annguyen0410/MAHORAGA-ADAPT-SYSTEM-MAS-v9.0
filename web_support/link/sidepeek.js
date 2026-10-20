// ==================== Magic Side-Peek & Focus Timer ====================

const SidePeek = {
    timerInterval: null,
    timeLeft: 25 * 60,
    isRunning: false,
    currentUrl: '',

    init() {
        console.log('🛸 Initializing Side-Peek...');

        const closeBtn = document.getElementById('closeSidePeek');
        const openExt = document.getElementById('openExternal');
        const openExtBtn = document.getElementById('sidePeekOpenExternalBtn');
        const toggleTimerBtn = document.getElementById('toggleTimer');
        const panel = document.getElementById('sidePeekPanel');
        const iframe = document.getElementById('sidePeekIframe');

        if (closeBtn) closeBtn.addEventListener('click', () => this.close());

        const handleOpenExt = () => {
            if (this.currentUrl) window.open(this.currentUrl, '_blank');
        };
        if (openExt) openExt.addEventListener('click', handleOpenExt);
        if (openExtBtn) openExtBtn.addEventListener('click', handleOpenExt);

        if (toggleTimerBtn) {
            toggleTimerBtn.addEventListener('click', () => this.toggleTimer());
        }

        // Handle iframe load errors (best effort)
        if (iframe) {
            iframe.onload = () => {
                // We can't actually detect X-Frame-Options headers from JS in a different domain
                // But we can check if there was some response (not possible for cross-domain)
                // So we rely on a timeout or just letting the user know.
                // However, some sites will just show nothing or a browser error.
                console.log('🛸 Side-Peek iframe loaded');
            };
        }
    },

    open(title, url) {
        this.currentUrl = url;
        const panel = document.getElementById('sidePeekPanel');
        const iframe = document.getElementById('sidePeekIframe');
        const titleEl = document.getElementById('sidePeekTitle');
        const urlEl = document.getElementById('sidePeekUrl');
        const blockedEl = document.getElementById('sidePeekBlocked');

        if (titleEl) titleEl.textContent = title;
        if (urlEl) urlEl.textContent = url;
        if (iframe) iframe.src = url;

        if (panel) panel.classList.remove('translate-x-full');

        // Check for known "un-iframeable" domains (optional heuristic)
        const blockedDomains = ['google.com', 'facebook.com', 'twitter.com', 'github.com', 'linkedin.com', 'youtube.com', 'x.com'];
        const isBlocked = blockedDomains.some(d => url.includes(d));

        if (blockedEl) {
            if (isBlocked) {
                blockedEl.classList.remove('hidden');
                if (iframe) iframe.classList.add('opacity-0');
            } else {
                blockedEl.classList.add('hidden');
                if (iframe) iframe.classList.remove('opacity-0');
            }
        }
    },

    close() {
        const panel = document.getElementById('sidePeekPanel');
        const iframe = document.getElementById('sidePeekIframe');
        if (panel) panel.classList.add('translate-x-full');
        if (iframe) iframe.src = 'about:blank';
    },

    toggleTimer() {
        if (this.isRunning) {
            this.pauseTimer();
        } else {
            this.startTimer();
        }
    },

    startTimer() {
        if (this.isRunning) return;
        this.isRunning = true;
        const btn = document.getElementById('toggleTimer');
        if (btn) btn.innerHTML = '<i data-lucide="pause" class="w-3 h-3"></i>';
        if (window.lucide) window.lucide.createIcons();

        this.timerInterval = setInterval(() => {
            this.timeLeft--;
            this.updateTimerDisplay();
            if (this.timeLeft <= 0) {
                this.completeTimer();
            }
        }, 1000);
    },

    pauseTimer() {
        this.isRunning = false;
        clearInterval(this.timerInterval);
        const btn = document.getElementById('toggleTimer');
        if (btn) btn.innerHTML = '<i data-lucide="play" class="w-3 h-3"></i>';
        if (window.lucide) window.lucide.createIcons();
    },

    completeTimer() {
        this.pauseTimer();
        this.timeLeft = 25 * 60;
        this.updateTimerDisplay();
        if (window.showToast) window.showToast('🚀 Focus time is up! Take a quick break.', 'success');
        // Play notification sound if possible
    },

    updateTimerDisplay() {
        const display = document.getElementById('timerDisplay');
        if (!display) return;
        const mins = Math.floor(this.timeLeft / 60);
        const secs = this.timeLeft % 60;
        display.textContent = `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
    }
};

document.addEventListener('DOMContentLoaded', () => SidePeek.init());
window.openSidePeek = (t, u) => SidePeek.open(t, u);
