// World Ranking - Enhanced Self-Assessment Calculator v2.0
// Calculate your global ranking among 8 billion people

const WORLD_POPULATION = 8000000000;

// Category weights (total = 1.0)
const CATEGORY_WEIGHTS = {
    basic: 0.10,
    health: 0.10,
    influence: 0.12,
    professional: 0.15,
    achievement: 0.12,
    wealth: 0.12,
    lifestyle: 0.08,
    relationships: 0.08,
    network: 0.06,
    impact: 0.07
};

// Tier thresholds
const TIERS = [
    { name: 'Diamond', min: 95, icon: '💎', subtitle: 'Top 5% - Global Elite' },
    { name: 'Platinum', min: 85, icon: '⚪', subtitle: 'Top 15% - World Class' },
    { name: 'Gold', min: 70, icon: '🥇', subtitle: 'Top 30% - High Achiever' },
    { name: 'Silver', min: 50, icon: '🥈', subtitle: 'Top 50% - Above Average' },
    { name: 'Bronze', min: 0, icon: '🥉', subtitle: 'Rising Star' }
];

let radarChart = null;
let historyChart = null;

// DOM Element Cache for performance
const DOM = {};

// Debounce utility for performance
function debounce(fn, delay = 150) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => fn.apply(this, args), delay);
    };
}

// Cache DOM elements on load
function cacheDOMElements() {
    DOM.progressFill = document.getElementById('progress-fill');
    DOM.progressText = document.getElementById('progress-text');
    DOM.results = document.getElementById('results');
    DOM.tierCard = document.getElementById('tier-card');
    DOM.tierIcon = document.getElementById('tier-icon');
    DOM.tierName = document.getElementById('tier-name');
    DOM.tierSubtitle = document.querySelector('.tier-subtitle');
    DOM.rankNumber = document.getElementById('rank-number');
    DOM.percentileFill = document.getElementById('percentile-fill');
    DOM.percentileMarker = document.getElementById('percentile-marker');
    DOM.percentileText = document.getElementById('percentile-text');
    DOM.percentileDesc = document.getElementById('percentile-description');
    DOM.comparisonStats = document.getElementById('comparison-stats');
    DOM.radarChart = document.getElementById('radar-chart');
    DOM.scoreBars = document.getElementById('score-bars');
    DOM.badgesContainer = document.getElementById('badges-container');
    DOM.suggestionsList = document.getElementById('suggestions-list');
    DOM.categoryRankings = document.getElementById('category-rankings-grid');
    DOM.whatifScenarios = document.getElementById('whatif-scenarios');
    DOM.historyChart = document.getElementById('history-chart');
    DOM.historyStats = document.getElementById('history-stats');
    DOM.demographicGrid = document.getElementById('demographic-grid');
    DOM.milestoneCard = document.getElementById('milestone-card');
    DOM.inputFields = document.querySelectorAll('.input-field');
    DOM.categoryTabs = document.querySelectorAll('.category-tab');
    DOM.tabContents = document.querySelectorAll('.tab-content');
}

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    cacheDOMElements();
    setupTabs();
    setupInputListeners();
    setupCalculateButton();
    setupResetButton();
    setupSaveLoadButtons();
    setupQuickFillModal();
    setupShareButtons();
    updateProgress();
    loadAutoSave();
});

// Tab Navigation (optimized with cached elements)
function setupTabs() {
    DOM.categoryTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const tabName = tab.dataset.tab;
            DOM.categoryTabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');
            DOM.tabContents.forEach(c => c.classList.remove('active'));
            document.getElementById(`tab-${tabName}`).classList.add('active');
        });
    });
}

// Input Listeners with debounced auto-save
const debouncedAutoSave = debounce(autoSave, 500);
const debouncedUpdateProgress = debounce(updateProgress, 100);

function setupInputListeners() {
    DOM.inputFields.forEach(input => {
        input.addEventListener('change', () => { updateProgress(); debouncedAutoSave(); });
        input.addEventListener('input', () => { debouncedUpdateProgress(); debouncedAutoSave(); });
    });
}

// Progress Bar (optimized with cached elements)
function updateProgress() {
    let filled = 0;
    DOM.inputFields.forEach(input => {
        if (input.value && input.value !== input.defaultValue) filled++;
    });
    const pct = Math.min(Math.round((filled / DOM.inputFields.length) * 100), 100);
    DOM.progressFill.style.width = `${pct}%`;
    DOM.progressText.textContent = `${pct}% Complete`;
}

// Get Value Helper
function getValue(id) {
    const el = document.getElementById(id);
    const value = el ? Number.parseFloat(el.value) : 0;
    if (!Number.isFinite(value)) return 0;
    const minimum = el && el.min !== undefined && el.min !== '' && Number.isFinite(Number(el.min)) ? Number(el.min) : 0;
    const maximum = el && el.max !== undefined && el.max !== '' && Number.isFinite(Number(el.max)) ? Number(el.max) : 1e15;
    return Math.min(maximum, Math.max(minimum, value));
}

// Score Calculations
function calculateBasicScore() {
    const education = getValue('education');
    const countries = Math.min(Math.log10(getValue('countries') + 1) * 35, 45);
    const languages = Math.min(getValue('languages') * 12, 40);
    const books = Math.min(getValue('books') * 1.5, 30);
    const iq = Math.min((getValue('iq') - 70) * 0.6, 45);
    return Math.min((education * 0.35 + countries + languages + books + iq) / 2, 100);
}

function calculateHealthScore() {
    const fitness = getValue('fitness');
    const workout = getValue('workout');
    const sleep = getValue('sleep');
    const diet = getValue('diet');
    const mental = getValue('mental');
    const habits = getValue('habits');
    return Math.min((fitness + workout + sleep + diet + mental + habits) / 6, 100);
}

function calculateInfluenceScore() {
    const insta = Math.min(Math.log10(getValue('instagram') + 1) * 10, 35);
    const tiktok = Math.min(Math.log10(getValue('tiktok') + 1) * 10, 30);
    const twitter = Math.min(Math.log10(getValue('twitter') + 1) * 9, 25);
    const youtube = Math.min(Math.log10(getValue('youtube') + 1) * 12, 35);
    const linkedin = Math.min(Math.log10(getValue('linkedin') + 1) * 15, 30);
    const website = Math.min(Math.log10(getValue('website') + 1) * 8, 20);
    return Math.min(insta + tiktok + twitter + youtube + linkedin + website, 100);
}

function calculateProfessionalScore() {
    const position = getValue('position');
    const experience = Math.min(getValue('experience') * 4, 40);
    const teamsize = Math.min(Math.log10(getValue('teamsize') + 1) * 18, 35);
    const startups = Math.min(getValue('startups') * 18, 40);
    const certs = Math.min(getValue('certifications') * 4, 25);
    const speaking = Math.min(getValue('speaking') * 3, 25);
    return Math.min((position * 0.4 + experience + teamsize + startups + certs + speaking) / 2, 100);
}

function calculateAchievementScore() {
    const pubs = Math.min(Math.log10(getValue('publications') + 1) * 22, 35);
    const awards = Math.min(getValue('awards') * 6, 35);
    const github = getValue('github');
    const creative = Math.min(getValue('creative') * 4, 30);
    const patents = Math.min(getValue('patents') * 12, 35);
    const recognition = getValue('recognition');
    return Math.min((pubs + awards + github * 0.35 + creative + patents + recognition * 0.35) / 1.8, 100);
}

function calculateWealthScore() {
    const income = getValue('income');
    const networth = getValue('networth');
    const properties = Math.min(getValue('properties') * 12, 35);
    const vehicles = Math.min(getValue('vehicles') * 6, 20);
    const investments = getValue('investments');
    const passive = Math.min(getValue('passive') * 10, 30);
    return Math.min((income * 0.35 + networth * 0.4 + properties + vehicles + investments * 0.3 + passive) / 1.5, 100);
}

function calculateLifestyleScore() {
    const hobbies = Math.min(getValue('hobbies') * 8, 35);
    const instruments = Math.min(getValue('instruments') * 15, 35);
    const sports = Math.min(getValue('sports') * 10, 30);
    const cuisines = Math.min(getValue('cuisines') * 7, 25);
    const skills = Math.min(getValue('skills') * 5, 35);
    const experiences = Math.min(getValue('experiences') * 4, 30);
    return Math.min((hobbies + instruments + sports + cuisines + skills + experiences) / 1.8, 100);
}

function calculateRelationshipsScore() {
    const relationship = getValue('relationship');
    const friends = Math.min(getValue('closefriends') * 5, 35);
    const family = getValue('family');
    const children = Math.min(getValue('children') * 8, 25);
    const mentored = Math.min(getValue('mentored') * 3, 30);
    const social = getValue('sociallife');
    return Math.min((relationship * 0.35 + friends + family * 0.3 + children + mentored + social * 0.3) / 1.6, 100);
}

function calculateNetworkScore() {
    const contacts = Math.min(Math.log10(getValue('contacts') + 1) * 20, 35);
    const vip = Math.min(getValue('vip') * 4, 35);
    const companies = Math.min(getValue('companies') * 6, 30);
    const subscribers = Math.min(Math.log10(getValue('subscribers') + 1) * 10, 30);
    const communities = Math.min(getValue('communities') * 10, 30);
    const media = Math.min(getValue('media') * 3, 30);
    return Math.min((contacts + vip + companies + subscribers + communities + media) / 1.8, 100);
}

function calculateImpactScore() {
    const environment = getValue('environment');
    const charities = Math.min(getValue('charities') * 6, 30);
    const volunteer = Math.min(getValue('volunteer') / 4, 30);
    const courses = Math.min(getValue('courses') * 4, 30);
    const donations = Math.min(Math.log10(getValue('donations') + 1) * 12, 30);
    const lives = Math.min(Math.log10(getValue('livesimpacted') + 1) * 12, 35);
    return Math.min((environment * 0.3 + charities + volunteer + courses + donations + lives) / 1.5, 100);
}

// Main Calculation
function calculateRanking() {
    const scores = {
        basic: calculateBasicScore(),
        health: calculateHealthScore(),
        influence: calculateInfluenceScore(),
        professional: calculateProfessionalScore(),
        achievement: calculateAchievementScore(),
        wealth: calculateWealthScore(),
        lifestyle: calculateLifestyleScore(),
        relationships: calculateRelationshipsScore(),
        network: calculateNetworkScore(),
        impact: calculateImpactScore()
    };

    Object.keys(scores).forEach(key => { scores[key] = Number.isFinite(scores[key]) ? Math.min(100, Math.max(0, scores[key])) : 0; });
    let overall = 0;
    for (const [cat, weight] of Object.entries(CATEGORY_WEIGHTS)) {
        overall += scores[cat] * weight;
    }

    const percentile = calculatePercentile(overall);
    const rank = Math.max(1, Math.round(WORLD_POPULATION * (1 - percentile / 100)));
    const tier = TIERS.find(t => percentile >= t.min);

    return { scores, overall, percentile, rank, tier };
}

function calculatePercentile(score) {
    if (score < 20) return score * 1.5;
    if (score < 40) return 30 + (score - 20) * 1.1;
    if (score < 60) return 52 + (score - 40) * 1.4;
    if (score < 80) return 80 + (score - 60) * 0.7;
    return 94 + (score - 80) * 0.3;
}

// Setup Calculate Button
function setupCalculateButton() {
    document.getElementById('calculate-btn').addEventListener('click', () => {
        const { scores, overall, percentile, rank, tier } = calculateRanking();
        displayResults(scores, overall, percentile, rank, tier);
        autoSave();
    });
}

// Display Results (optimized with cached DOM)
function displayResults(scores, overall, percentile, rank, tier) {
    DOM.results.classList.add('active');
    DOM.results.scrollIntoView({ behavior: 'smooth', block: 'start' });

    // Tier
    DOM.tierCard.className = 'tier-card ' + tier.name.toLowerCase();
    DOM.tierIcon.textContent = tier.icon;
    DOM.tierName.textContent = tier.name;
    DOM.tierSubtitle.textContent = tier.subtitle;

    // Rank with animation
    animateRankNumber(rank);

    // Percentile bar (use requestAnimationFrame for smooth animation)
    requestAnimationFrame(() => {
        DOM.percentileFill.style.width = `${percentile}%`;
        DOM.percentileMarker.style.left = `calc(${percentile}% - 11px)`;
    });

    // Percentile text
    const pctText = percentile >= 99 ? 'Top 1%' :
        percentile >= 95 ? 'Top 5%' :
            percentile >= 90 ? 'Top 10%' :
                percentile >= 75 ? 'Top 25%' :
                    percentile >= 50 ? 'Top 50%' : `Top ${Math.round(100 - percentile)}%`;
    DOM.percentileText.textContent = pctText;

    const peopleBeaten = WORLD_POPULATION - rank;
    DOM.percentileDesc.textContent = `You rank higher than ${formatNumber(peopleBeaten)} people on Earth`;

    // Comparison stats
    displayComparisonStats(scores);

    // Charts & Bars
    displayRadarChart(scores);
    displayScoreBars(scores);

    // Badges & Suggestions
    displayBadges(scores, overall, percentile);

    // Advanced Ranking Features
    displayCategoryRankings(scores);
    displayWhatIfScenarios(scores, rank);
    displayRankHistory(rank, percentile);
    displayDemographicComparisons(percentile, rank);
    displayNextMilestone(percentile, tier);

    // Suggestions last
    displaySuggestions(scores);
}

function animateRankNumber(targetRank) {
    const duration = 900;
    const startTime = performance.now();
    const startRank = WORLD_POPULATION;

    function update(currentTime) {
        const elapsed = currentTime - startTime;
        const progress = Math.min(elapsed / duration, 1);
        const easeProgress = 1 - Math.pow(1 - progress, 3);
        const current = Math.round(startRank - (startRank - targetRank) * easeProgress);
        DOM.rankNumber.textContent = current.toLocaleString();
        if (progress < 1) requestAnimationFrame(update);
    }
    requestAnimationFrame(update);
}

function formatNumber(num) {
    if (num >= 1e9) return (num / 1e9).toFixed(2) + 'B';
    if (num >= 1e6) return (num / 1e6).toFixed(1) + 'M';
    if (num >= 1e3) return (num / 1e3).toFixed(0) + 'K';
    return num.toLocaleString();
}

function displayComparisonStats(scores) {
    const avgScores = { basic: 45, health: 50, influence: 25, professional: 45, achievement: 30, wealth: 40, lifestyle: 35, relationships: 55, network: 30, impact: 25 };

    const comparisons = [
        { label: 'Strongest Area', value: Object.entries(scores).sort((a, b) => b[1] - a[1])[0][0], compare: '' },
        { label: 'Weakest Area', value: Object.entries(scores).sort((a, b) => a[1] - b[1])[0][0], compare: '' },
        { label: 'Above Average In', value: Object.entries(scores).filter(([k, v]) => v > avgScores[k]).length + '/10', compare: 'categories' }
    ];

    DOM.comparisonStats.innerHTML = comparisons.map(c => `
        <div class="comparison-stat">
            <div class="label">${c.label}</div>
            <div class="value">${typeof c.value === 'string' ? capitalize(c.value) : c.value}</div>
            <div class="compare">${c.compare}</div>
        </div>
    `).join('');
}

function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

// Radar Chart (optimized)
function displayRadarChart(scores) {
    const ctx = DOM.radarChart.getContext('2d');
    if (radarChart) radarChart.destroy();

    radarChart = new Chart(ctx, {
        type: 'radar',
        data: {
            labels: ['Basic', 'Health', 'Influence', 'Career', 'Achievement', 'Wealth', 'Lifestyle', 'Relationships', 'Network', 'Impact'],
            datasets: [{
                label: 'Your Scores',
                data: Object.values(scores),
                backgroundColor: 'rgba(255, 215, 0, 0.2)',
                borderColor: '#FFD700',
                borderWidth: 2,
                pointBackgroundColor: '#FFD700',
                pointRadius: 4
            }]
        },
        options: {
            scales: {
                r: {
                    beginAtZero: true,
                    max: 100,
                    ticks: { stepSize: 25, color: 'rgba(255,255,255,0.4)', backdropColor: 'transparent', font: { size: 10 } },
                    grid: { color: 'rgba(255,255,255,0.1)' },
                    pointLabels: { color: 'rgba(255,255,255,0.7)', font: { size: 10, weight: '500' } },
                    angleLines: { color: 'rgba(255,255,255,0.1)' }
                }
            },
            plugins: { legend: { display: false } }
        }
    });
}

// Score Bars (optimized)
function displayScoreBars(scores) {
    const colors = {
        basic: '#4F46E5', health: '#22C55E', influence: '#8B5CF6', professional: '#14B8A6',
        achievement: '#FFD700', wealth: '#F59E0B', lifestyle: '#F43F5E', relationships: '#EC4899',
        network: '#3B82F6', impact: '#06B6D4'
    };
    const labels = {
        basic: '👤 Basic', health: '💪 Health', influence: '📱 Influence', professional: '💼 Career',
        achievement: '🏆 Achievement', wealth: '💎 Wealth', lifestyle: '✨ Lifestyle', relationships: '❤️ Relationships',
        network: '🌐 Network', impact: '🌍 Impact'
    };

    DOM.scoreBars.innerHTML = Object.entries(scores).map(([key, value]) => `
        <div class="score-bar-item">
            <span class="score-bar-label">${labels[key]}</span>
            <div class="score-bar-container">
                <div class="score-bar-fill" style="width: ${value}%; background: ${colors[key]}"></div>
            </div>
            <span class="score-bar-value">${Math.round(value)}</span>
        </div>
    `).join('');
}

// Badges
function displayBadges(scores, overall, percentile) {
    const container = document.getElementById('badges-container');
    const badges = [];

    // Tier badges
    if (percentile >= 95) badges.push({ text: '💎 Diamond Elite', type: 'diamond' });
    else if (percentile >= 85) badges.push({ text: '⚪ Platinum Class', type: 'gold' });
    else if (percentile >= 70) badges.push({ text: '🥇 Gold Status', type: 'gold' });
    else if (percentile >= 50) badges.push({ text: '🥈 Silver Rising', type: 'silver' });

    // Category badges
    if (scores.basic >= 70) badges.push({ text: '🎓 Scholar', type: 'gold' });
    if (scores.health >= 75) badges.push({ text: '💪 Fitness Pro', type: 'gold' });
    if (scores.influence >= 60) badges.push({ text: '📱 Influencer', type: 'gold' });
    if (scores.professional >= 75) badges.push({ text: '💼 Executive', type: 'gold' });
    if (scores.achievement >= 65) badges.push({ text: '🏆 Achiever', type: 'gold' });
    if (scores.wealth >= 70) badges.push({ text: '💎 Wealthy', type: 'gold' });
    if (scores.lifestyle >= 65) badges.push({ text: '✨ Renaissance', type: 'silver' });
    if (scores.relationships >= 70) badges.push({ text: '❤️ Connected', type: 'silver' });
    if (scores.network >= 60) badges.push({ text: '🌐 Networker', type: 'silver' });
    if (scores.impact >= 60) badges.push({ text: '🌍 Change Maker', type: 'gold' });

    // Special badges
    if (getValue('languages') >= 4) badges.push({ text: '🗣️ Polyglot', type: 'gold' });
    if (getValue('countries') >= 25) badges.push({ text: '✈️ World Traveler', type: 'gold' });
    if (getValue('startups') >= 1) badges.push({ text: '🚀 Entrepreneur', type: 'gold' });
    if (getValue('books') >= 24) badges.push({ text: '📚 Bibliophile', type: 'silver' });
    if (getValue('instruments') >= 2) badges.push({ text: '🎸 Musician', type: 'silver' });
    if (getValue('patents') >= 1) badges.push({ text: '💡 Inventor', type: 'gold' });
    if (getValue('volunteer') >= 100) badges.push({ text: '🤝 Volunteer Hero', type: 'silver' });

    if (badges.length === 0) badges.push({ text: '🌱 Getting Started', type: 'bronze' });

    container.innerHTML = badges.slice(0, 12).map(b => `<span class="badge ${b.type}">${b.text}</span>`).join('');
}

// Suggestions
function displaySuggestions(scores) {
    const container = document.getElementById('suggestions-list');
    const sorted = Object.entries(scores).sort((a, b) => a[1] - b[1]).slice(0, 3);
    const suggestions = [];

    const tips = {
        basic: ['📚 Read 2 books per month to boost knowledge', '🌍 Plan a trip to a new country', '💬 Start learning a new language on Duolingo'],
        health: ['🏃 Add 10 minutes of daily exercise', '😴 Improve sleep by going to bed 30min earlier', '🧘 Try 5 minutes of daily meditation'],
        influence: ['📸 Post consistent content on one platform', '📹 Start a YouTube channel in your niche', '🔗 Engage more on LinkedIn'],
        professional: ['📜 Get a certification in your field', '🎤 Apply to speak at a local meetup', '👥 Volunteer to lead a project'],
        achievement: ['✍️ Write and publish an article', '💻 Start an open-source project', '🏆 Apply for an industry award'],
        wealth: ['📈 Open an investment account', '💸 Create a passive income source', '🏠 Start saving for property'],
        lifestyle: ['🎸 Learn a musical instrument', '🎨 Pick up a creative hobby', '⚽ Join a sports team or club'],
        relationships: ['👥 Schedule regular time with close friends', '📞 Call a family member weekly', '👨‍🏫 Mentor someone in your field'],
        network: ['☕ Set up 2 coffee chats per month', '🤝 Attend industry events', '📧 Build an email newsletter'],
        impact: ['🌱 Reduce your carbon footprint', '❤️ Donate to a cause you believe in', '📚 Create free educational content']
    };

    sorted.forEach(([cat]) => {
        const catTips = tips[cat];
        suggestions.push(catTips[Math.floor(Math.random() * catTips.length)]);
    });

    container.innerHTML = suggestions.map(s => `<div class="suggestion-item">${s}</div>`).join('');
}

// Category Rankings - Show rank in each category
function displayCategoryRankings(scores) {
    const container = document.getElementById('category-rankings-grid');
    const icons = {
        basic: '👤', health: '💪', influence: '📱', professional: '💼',
        achievement: '🏆', wealth: '💎', lifestyle: '✨', relationships: '❤️',
        network: '🌐', impact: '🌍'
    };
    const names = {
        basic: 'Basic', health: 'Health', influence: 'Influence', professional: 'Career',
        achievement: 'Achievement', wealth: 'Wealth', lifestyle: 'Lifestyle', relationships: 'Relationships',
        network: 'Network', impact: 'Impact'
    };

    container.innerHTML = Object.entries(scores).map(([key, score]) => {
        const pct = calculatePercentile(score);
        const rank = Math.round(WORLD_POPULATION * (1 - pct / 100));
        return `
            <div class="category-rank-card">
                <div class="cat-icon">${icons[key]}</div>
                <div class="cat-name">${names[key]}</div>
                <div class="cat-rank">#${formatNumber(rank)}</div>
                <div class="cat-percentile">Top ${Math.max(1, Math.round(100 - pct))}%</div>
            </div>
        `;
    }).join('');
}

// What-If Simulator
function displayWhatIfScenarios(scores, currentRank) {
    const container = document.getElementById('whatif-scenarios');
    const scenarios = [];

    // Generate relevant scenarios based on current scores
    if (scores.influence < 50) {
        scenarios.push({
            scenario: '📱 If you got 10K Instagram followers',
            impact: simulateChange('instagram', 10000, currentRank)
        });
    }
    if (getValue('startups') === 0) {
        scenarios.push({
            scenario: '🚀 If you started a business',
            impact: simulateChange('startups', 1, currentRank)
        });
    }
    if (scores.health < 60) {
        scenarios.push({
            scenario: '🏃 If you could run a half marathon',
            impact: simulateSelectChange('fitness', '85', currentRank)
        });
    }
    if (scores.wealth < 60) {
        scenarios.push({
            scenario: '💰 If you had $100K investments',
            impact: simulateSelectChange('investments', '68', currentRank)
        });
    }
    if (getValue('languages') < 3) {
        scenarios.push({
            scenario: '🗣️ If you learned 2 more languages',
            impact: simulateChange('languages', getValue('languages') + 2, currentRank)
        });
    }
    if (scores.professional < 70) {
        scenarios.push({
            scenario: '💼 If you became a Director/VP',
            impact: simulateSelectChange('position', '85', currentRank)
        });
    }

    container.innerHTML = scenarios.slice(0, 5).map(s => `
        <div class="whatif-item">
            <span class="whatif-scenario">${s.scenario}</span>
            <span class="whatif-impact ${s.impact.change > 0 ? 'positive' : 'negative'}">
                ${s.impact.change > 0 ? '↑' : '↓'} ${formatNumber(Math.abs(s.impact.rankDiff))} positions
            </span>
        </div>
    `).join('');
}

function simulateChange(fieldId, newValue, currentRank) {
    const el = document.getElementById(fieldId);
    const originalValue = el.value;
    el.value = newValue;
    const { rank: newRank } = calculateRanking();
    el.value = originalValue;
    return { rankDiff: currentRank - newRank, change: currentRank - newRank };
}

function simulateSelectChange(fieldId, newValue, currentRank) {
    const el = document.getElementById(fieldId);
    const originalValue = el.value;
    el.value = newValue;
    const { rank: newRank } = calculateRanking();
    el.value = originalValue;
    return { rankDiff: currentRank - newRank, change: currentRank - newRank };
}

// Rank History (chart instance is declared once at the top of the file)
function displayRankHistory(currentRank, currentPercentile) {
    // Get history from localStorage
    let history = [];
    let readable = true;
    try {
        const parsed = JSON.parse(localStorage.getItem('worldRankingHistory') || '[]');
        if (!Array.isArray(parsed)) throw Error('Invalid history');
        history = parsed.filter(h => h && typeof h.date === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(h.date) && Number.isFinite(h.rank) && h.rank >= 1 && Number.isFinite(h.percentile) && h.percentile >= 0 && h.percentile <= 100);
    } catch (_) { readable = false; showStorageStatus('History could not be read. Saved bytes are preserved; current results are still available.'); }

    // Add current entry
    const today = new Date().toISOString().slice(0, 10);
    const existingIndex = history.findIndex(h => h.date === today);
    if (existingIndex >= 0) {
        history[existingIndex] = { date: today, rank: currentRank, percentile: currentPercentile };
    } else {
        history.push({ date: today, rank: currentRank, percentile: currentPercentile });
    }

    // Keep last 30 entries
    history = history.slice(-30);
    if (readable) {
        try { localStorage.setItem('worldRankingHistory', JSON.stringify(history)); }
        catch (_) { showStorageStatus('History was not saved. Export your profile to keep a copy.'); }
    }

    // Display chart
    const ctx = document.getElementById('history-chart').getContext('2d');
    if (historyChart) historyChart.destroy();

    historyChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: history.map(h => h.date.slice(5)),
            datasets: [{
                label: 'Percentile',
                data: history.map(h => h.percentile),
                borderColor: '#FFD700',
                backgroundColor: 'rgba(255, 215, 0, 0.1)',
                fill: true,
                tension: 0.4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                y: { min: 0, max: 100, ticks: { color: 'rgba(255,255,255,0.5)' }, grid: { color: 'rgba(255,255,255,0.1)' } },
                x: { ticks: { color: 'rgba(255,255,255,0.5)' }, grid: { display: false } }
            },
            plugins: { legend: { display: false } }
        }
    });

    // Display stats
    const statsContainer = document.getElementById('history-stats');
    const firstEntry = history[0];
    const improvement = currentPercentile - (firstEntry?.percentile || currentPercentile);

    statsContainer.innerHTML = `
        <div class="history-stat">
            <div class="label">Sessions</div>
            <div class="value">${history.length}</div>
        </div>
        <div class="history-stat">
            <div class="label">Best Rank</div>
            <div class="value">#${formatNumber(Math.min(...history.map(h => h.rank)))}</div>
        </div>
        <div class="history-stat">
            <div class="label">Progress</div>
            <div class="value">${improvement >= 0 ? '+' : ''}${improvement.toFixed(1)}%</div>
            <div class="change ${improvement >= 0 ? 'up' : 'down'}">${improvement >= 0 ? '↑ Improving' : '↓ Declining'}</div>
        </div>
    `;
}

// Demographic Comparisons
function displayDemographicComparisons(percentile, rank) {
    const container = document.getElementById('demographic-grid');
    const age = getValue('age');

    // Simulate different population groups
    const demographics = [
        { icon: '🌍', label: 'Global Population', population: WORLD_POPULATION, multiplier: 1 },
        { icon: '🇺🇸', label: 'Among Americans', population: 330000000, multiplier: 1.15 },
        { icon: '👨‍💼', label: 'Working Adults', population: 3500000000, multiplier: 0.9 },
        { icon: '🎓', label: 'College Educated', population: 1200000000, multiplier: 0.7 },
        { icon: age < 30 ? '👦' : age < 50 ? '👨' : '👴', label: `Your Age Group (${age < 30 ? '18-29' : age < 50 ? '30-49' : '50+'})`, population: 2000000000, multiplier: 0.95 },
        { icon: '💻', label: 'Tech Workers', population: 50000000, multiplier: 0.6 }
    ];

    container.innerHTML = demographics.map(d => {
        const adjustedPct = Math.min(percentile * d.multiplier, 99);
        const demoRank = Math.round(d.population * (1 - adjustedPct / 100));
        return `
            <div class="demographic-card">
                <div class="demo-icon">${d.icon}</div>
                <div class="demo-label">${d.label}</div>
                <div class="demo-rank">#${formatNumber(demoRank)}</div>
                <div class="demo-percentile">Top ${Math.max(1, Math.round(100 - adjustedPct))}%</div>
            </div>
        `;
    }).join('');
}

// Next Milestone
function displayNextMilestone(percentile, tier) {
    const container = document.getElementById('milestone-card');

    // Find next tier
    const tierIndex = TIERS.findIndex(t => t.name === tier.name);
    const nextTier = tierIndex > 0 ? TIERS[tierIndex - 1] : null;

    if (!nextTier) {
        container.innerHTML = `
            <div class="milestone-header">
                <div class="milestone-tier">
                    <span class="icon">🏆</span>
                    <span class="name">You've reached the top!</span>
                </div>
            </div>
            <p class="milestone-tips">You're in the <strong>Diamond</strong> tier - the top 5% globally. Keep pushing boundaries!</p>
        `;
        return;
    }

    const progress = ((percentile - tier.min) / (nextTier.min - tier.min)) * 100;
    const pointsNeeded = nextTier.min - percentile;

    container.innerHTML = `
        <div class="milestone-header">
            <div class="milestone-tier">
                <span class="icon">${nextTier.icon}</span>
                <span class="name">${nextTier.name} Tier</span>
            </div>
            <span class="milestone-progress">${progress.toFixed(0)}% there</span>
        </div>
        <div class="milestone-bar">
            <div class="milestone-bar-fill" style="width: ${progress}%"></div>
        </div>
        <p class="milestone-tips">
            You need <strong>+${pointsNeeded.toFixed(1)} percentile points</strong> to reach ${nextTier.name}. 
            Focus on your weakest areas to level up faster!
        </p>
    `;
}

// Save/Load
function setupSaveLoadButtons() {
    document.getElementById('save-btn').addEventListener('click', saveProfile);
    document.getElementById('load-btn').addEventListener('click', loadProfile);
    document.getElementById('clear-btn').addEventListener('click', clearAll);
}

function saveProfile() {
    const data = {};
    document.querySelectorAll('.input-field').forEach(input => {
        data[input.id] = input.value;
    });

    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `world-ranking-profile-${new Date().toISOString().slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
}

function loadProfile() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = (e) => {
        const file = e.target.files[0];
        if (!file) return;
        if (file.size > 1024 * 1024) { alert('Profile is too large (1 MB maximum).'); return; }
        const reader = new FileReader();
        reader.onload = (event) => {
            try {
                const data = JSON.parse(event.target.result);
                applyProfileData(data);
                autoSave();
                updateProgress();
                alert('Profile loaded successfully!');
            } catch (err) {
                alert('Error loading profile. Invalid file.');
            }
        };
        reader.onerror = () => alert('Could not read the profile file. Existing inputs are unchanged.');
        reader.readAsText(file);
    };
    input.click();
}

function clearAll() {
    if (confirm('Clear all inputs and start fresh?')) {
        try { localStorage.removeItem('worldRankingAutoSave'); }
        catch (_) { showStorageStatus('Could not clear saved inputs. Nothing was changed.'); return; }
        document.querySelectorAll('.input-field').forEach(input => {
            if (input.tagName === 'SELECT') {
                input.selectedIndex = [...input.options].findIndex(o => o.defaultSelected);
                if (input.selectedIndex === -1) input.selectedIndex = 0;
            } else {
                input.value = input.defaultValue;
            }
        });
        document.getElementById('results').classList.remove('active');
        updateProgress();
    }
}

function showStorageStatus(message) {
    let status = document.getElementById('profile-storage-status');
    if (!status) {
        status = document.createElement('p');
        status.id = 'profile-storage-status';
        status.setAttribute('role', 'status');
        document.getElementById('progress-text').parentElement.appendChild(status);
    }
    status.textContent = message;
}

function applyProfileData(data) {
    if (!data || typeof data !== 'object' || Array.isArray(data)) throw Error('Invalid profile');
    const updates = [];
    document.querySelectorAll('.input-field').forEach(el => {
        if (!Object.prototype.hasOwnProperty.call(data, el.id)) return;
        const value = data[el.id];
        if (typeof value !== 'string' && typeof value !== 'number') throw Error('Invalid value for ' + el.id);
        if (el.tagName === 'SELECT') {
            if (![...el.options].some(option => option.value === String(value))) throw Error('Invalid choice for ' + el.id);
        } else if (el.type === 'number' && value !== '') {
            const number = Number(value);
            if (!Number.isFinite(number) || number < (el.min === '' ? 0 : Number(el.min)) || el.max !== '' && number > Number(el.max)) throw Error('Invalid number for ' + el.id);
        }
        updates.push([el, String(value)]);
    });
    updates.forEach(([el, value]) => { el.value = value; });
}

function autoSave() {
    const data = {};
    document.querySelectorAll('.input-field').forEach(input => {
        data[input.id] = input.value;
    });
    try { localStorage.setItem('worldRankingAutoSave', JSON.stringify(data)); }
    catch (_) { showStorageStatus('Autosave unavailable. Your inputs are retained; use Save Profile to export them.'); }
}

function loadAutoSave() {
    try {
        const saved = localStorage.getItem('worldRankingAutoSave');
        if (saved) { applyProfileData(JSON.parse(saved)); updateProgress(); }
    } catch (_) { showStorageStatus('Saved inputs could not be read. They were preserved; import a valid profile to recover.'); }
}

// Quick Fill Modal
function setupQuickFillModal() {
    const modal = document.getElementById('quick-fill-modal');
    const openBtn = document.getElementById('quick-fill-btn');
    const closeBtn = document.getElementById('modal-close');
    const cancelBtn = document.getElementById('cancel-btn');
    const analyzeBtn = document.getElementById('analyze-btn');

    openBtn.addEventListener('click', () => modal.classList.add('active'));
    closeBtn.addEventListener('click', () => modal.classList.remove('active'));
    cancelBtn.addEventListener('click', () => modal.classList.remove('active'));
    modal.addEventListener('click', (e) => { if (e.target === modal) modal.classList.remove('active'); });
    analyzeBtn.addEventListener('click', analyzeText);
}

function analyzeText() {
    const text = document.getElementById('quick-fill-text').value.toLowerCase();
    if (!text) return;

    // Parse numbers and keywords
    const patterns = {
        age: /(\d{2,3})\s*(?:years?\s*old|yo|year)/,
        countries: /(?:visited|traveled|been\s*to)\s*(\d+)\s*countr/,
        languages: /(?:speak|fluent|know)\s*(\d+)\s*language/,
        books: /(?:read|reading)\s*(\d+)\s*book/,
        instagram: /(\d+(?:,?\d+)*[km]?)\s*(?:instagram|ig|insta)\s*follower/,
        tiktok: /(\d+(?:,?\d+)*[km]?)\s*tiktok\s*follower/,
        youtube: /(\d+(?:,?\d+)*[km]?)\s*(?:youtube|yt)\s*(?:sub|follower)/,
        linkedin: /(\d+(?:,?\d+)*[km]?)\s*linkedin\s*connection/,
        experience: /(\d+)\s*years?\s*(?:of\s*)?(?:work|experience|career)/,
        teamsize: /(?:lead|manage|team\s*of)\s*(\d+)/,
        properties: /(?:own|have)\s*(\d+)\s*(?:propert|home|house)/,
        vehicles: /(\d+)\s*(?:car|vehicle)/
    };

    Object.entries(patterns).forEach(([field, regex]) => {
        const match = text.match(regex);
        if (match) {
            let value = match[1].replace(/,/g, '').toLowerCase();
            if (value.endsWith('k')) value = parseFloat(value) * 1000;
            else if (value.endsWith('m')) value = parseFloat(value) * 1000000;
            else value = parseFloat(value);

            const el = document.getElementById(field);
            if (el && el.tagName === 'INPUT') el.value = Math.round(value);
        }
    });

    // Keywords for selects
    if (/phd|doctorate|doctoral/.test(text)) document.getElementById('education').value = '92';
    else if (/master/.test(text)) document.getElementById('education').value = '82';
    else if (/bachelor|degree/.test(text)) document.getElementById('education').value = '70';

    if (/ceo|founder|own\s*(?:a\s*)?(?:company|business)/.test(text)) document.getElementById('position').value = '98';
    else if (/c-suite|cto|cfo|coo/.test(text)) document.getElementById('position').value = '92';
    else if (/director|vp|vice\s*president/.test(text)) document.getElementById('position').value = '85';
    else if (/manager|senior\s*manager/.test(text)) document.getElementById('position').value = '78';
    else if (/senior/.test(text)) document.getElementById('position').value = '68';

    if (/marathon/.test(text)) document.getElementById('fitness').value = '95';
    else if (/half\s*marathon/.test(text)) document.getElementById('fitness').value = '85';
    else if (/10k/.test(text)) document.getElementById('fitness').value = '70';
    else if (/5k/.test(text)) document.getElementById('fitness').value = '55';

    if (/married|wife|husband|spouse/.test(text)) document.getElementById('relationship').value = '80';
    else if (/dating|boyfriend|girlfriend|partner/.test(text)) document.getElementById('relationship').value = '55';

    updateProgress();
    document.getElementById('quick-fill-modal').classList.remove('active');
    alert('Fields filled based on your text! Review and adjust as needed.');
}

// Share Buttons
function setupShareButtons() {
    document.getElementById('share-btn')?.addEventListener('click', shareResults);
    document.getElementById('screenshot-btn')?.addEventListener('click', takeScreenshot);
}

function shareResults() {
    const { percentile, rank, tier } = calculateRanking();
    const text = `🌍 My World Ranking: #${formatNumber(rank)} (${tier.name} Tier)\n` +
        `I'm in the top ${Math.round(100 - percentile)}% globally!\n` +
        `Take the test: [Your URL Here]`;

    if (navigator.share) {
        navigator.share({ title: 'My World Ranking', text });
    } else {
        navigator.clipboard.writeText(text);
        alert('Results copied to clipboard!');
    }
}

async function takeScreenshot() {
    const card = document.getElementById('rank-card-capture');
    try {
        const canvas = await html2canvas(card, { backgroundColor: '#12121a', scale: 2 });
        const link = document.createElement('a');
        link.download = `world-ranking-${new Date().toISOString().slice(0, 10)}.png`;
        link.href = canvas.toDataURL();
        link.click();
    } catch (e) {
        alert('Screenshot failed. Try again.');
    }
}

// Reset
function setupResetButton() {
    document.getElementById('reset-btn').addEventListener('click', () => {
        document.getElementById('results').classList.remove('active');
        window.scrollTo({ top: 0, behavior: 'smooth' });
        document.querySelector('.category-tab').click();
    });
}