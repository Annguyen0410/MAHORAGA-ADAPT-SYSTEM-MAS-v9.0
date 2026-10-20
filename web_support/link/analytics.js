// ==================== Cognitive Analytics Dashboard ====================

const Analytics = {
    chart: null,

    init() {
        console.log('📊 Initializing Analytics...');
        const openBtn = document.getElementById('openAnalyticsBtn');
        const closeBtn = document.getElementById('closeAnalytics');
        const modal = document.getElementById('analyticsModal');

        if (openBtn) {
            openBtn.addEventListener('click', () => {
                modal.classList.remove('hidden');
                this.render();
            });
        }

        if (closeBtn) {
            closeBtn.addEventListener('click', () => {
                modal.classList.add('hidden');
            });
        }

        const overlay = document.getElementById('analyticsOverlay');
        if (overlay) {
            overlay.addEventListener('click', () => modal.classList.add('hidden'));
        }
    },

    render() {
        const container = document.getElementById('analyticsContent');
        if (!container) return;

        const links = window.links || [];
        const categories = {};
        const tags = {};
        let healthyCount = 0;
        let brokenCount = 0;

        links.forEach(link => {
            // Category count
            const cat = link.category || 'Uncategorized';
            categories[cat] = (categories[cat] || 0) + 1;

            // Tag count
            (link.tags || []).forEach(tag => {
                tags[tag] = (tags[tag] || 0) + 1;
            });

            // Health
            if (link.status === 'error' || link.status === 'broken') brokenCount++;
            else healthyCount++;
        });

        const sortedTags = Object.entries(tags).sort((a, b) => b[1] - a[1]).slice(0, 10);

        container.innerHTML = `
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
                <!-- Scorecards -->
                <div class="glass-card p-6 border-red-500/20">
                    <h3 class="text-gray-400 text-sm mb-2">Total Knowledge Nodes</h3>
                    <p class="text-4xl font-bold text-white">${links.length + (window.notes?.length || 0)}</p>
                    <div class="mt-4 flex items-center gap-2 text-xs text-green-400">
                        <i data-lucide="trending-up" class="w-3 h-3"></i>
                        <span>Active Growth</span>
                    </div>
                </div>
                <div class="glass-card p-6 border-cyan-500/20">
                    <h3 class="text-gray-400 text-sm mb-2">Library Health</h3>
                    <p class="text-4xl font-bold text-cyan-400">${Math.round((healthyCount / (links.length || 1)) * 100)}%</p>
                    <p class="text-xs text-gray-500 mt-2">${brokenCount} broken links identified</p>
                </div>
                <div class="glass-card p-6 border-purple-500/20">
                    <h3 class="text-gray-400 text-sm mb-2">Top Category</h3>
                    <p class="text-4xl font-bold text-purple-400">${Object.entries(categories).sort((a, b) => b[1] - a[1])[0]?.[0] || 'N/A'}</p>
                </div>

                <!-- Charts -->
                <div class="glass-card p-6 md:col-span-2">
                    <h2 class="text-lg font-bold text-white mb-4">Category Distribution</h2>
                    <div class="h-[300px]">
                        <canvas id="categoryChart"></canvas>
                    </div>
                </div>
                
                <div class="glass-card p-6">
                    <h2 class="text-lg font-bold text-white mb-4">Top 10 Tags</h2>
                    <div class="space-y-3">
                        ${sortedTags.map(([tag, count]) => `
                            <div class="flex items-center justify-between">
                                <span class="text-gray-300 text-sm">#${tag}</span>
                                <div class="flex-1 mx-4 h-1.5 bg-white/5 rounded-full overflow-hidden">
                                    <div class="h-full bg-red-500" style="width: ${(count / sortedTags[0][1]) * 100}%"></div>
                                </div>
                                <span class="text-gray-500 text-xs">${count}</span>
                            </div>
                        `).join('')}
                    </div>
                </div>
            </div>
        `;

        if (window.lucide) window.lucide.createIcons();

        // Render Chart
        this.renderCharts(categories);
    },

    renderCharts(categories) {
        const ctx = document.getElementById('categoryChart');
        if (!ctx) return;

        if (this.chart) this.chart.destroy();

        const dataArr = Object.values(categories);
        const labelsArr = Object.keys(categories);

        this.chart = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: labelsArr,
                datasets: [{
                    label: 'Links',
                    data: dataArr,
                    backgroundColor: 'rgba(239, 68, 68, 0.4)',
                    borderColor: 'rgba(239, 68, 68, 0.8)',
                    borderWidth: 1,
                    borderRadius: 8
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    y: {
                        beginAtZero: true,
                        grid: { color: 'rgba(255,255,255,0.05)' },
                        ticks: { color: 'rgba(255,255,255,0.5)' }
                    },
                    x: {
                        grid: { display: false },
                        ticks: { color: 'rgba(255,255,255,0.5)' }
                    }
                }
            }
        });
    }
};

document.addEventListener('DOMContentLoaded', () => Analytics.init());
