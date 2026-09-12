// Prostock Dashboard Logic
const API_BASE = '/api';
let currentSymbol = 'NIFTY 50';
const REVIEW_STORAGE_KEY = 'prostock-reviewed-option-signals';

// Initialize Chart
function initChart() {
    const data = [{
        x: [],
        y: [],
        type: 'scatter',
        mode: 'lines',
        name: 'Price',
        line: { color: '#8b5cf6', width: 2, shape: 'spline' },
        fill: 'tozeroy',
        fillcolor: 'rgba(139, 92, 246, 0.05)'
    }];

    const layout = {
        paper_bgcolor: 'rgba(0,0,0,0)',
        plot_bgcolor: 'rgba(0,0,0,0)',
        font: { color: '#94a3b8', family: 'Outfit' },
        xaxis: { gridcolor: 'rgba(255,255,255,0.05)', showgrid: true },
        yaxis: { gridcolor: 'rgba(255,255,255,0.05)', showgrid: true },
        margin: { t: 20, r: 20, b: 40, l: 40 },
        hovermode: 'x unified'
    };

    const config = { responsive: true, displayModeBar: false };
    Plotly.newPlot('main-chart', data, layout, config);
}

// Fetch and Update Signals
async function updateSignals() {
    try {
        const response = await fetch(`${API_BASE}/predictions?symbol=${currentSymbol}`);
        const data = await response.json();

        if (data.status === "error") return;

        const tbody = document.querySelector('#signals-table tbody');
        tbody.innerHTML = `
            <tr>
                <td>${data.symbol}</td>
                <td><span class="badge ${data.signal === 'BUY' ? 'badge-buy' : 'badge-sell'}">${data.signal}</span></td>
                <td>₹${data.price.toFixed(2)}</td>
                <td style="color: #ef4444; font-weight: 700;">₹${data.stop_loss}</td>
                <td style="color: #22c55e; font-weight: 700;">₹${data.target}</td>
                <td><button class="btn-sm active" onclick='recordReviewedSignal(${JSON.stringify(data).replace(/'/g, "&#39;")})'>REVIEW</button></td>
            </tr>
        `;

        // Update hero prediction
        document.getElementById('ai-signal').textContent = data.signal === 'BUY' ? 'BULLISH' : 'BEARISH';
        const aiCard = document.getElementById('ai-signal').parentElement;
        aiCard.style.background = data.signal === 'BUY' ? 'linear-gradient(135deg, #22c55e, #10b981)' : 'linear-gradient(135deg, #ef4444, #f43f5e)';
        aiCard.querySelector('.metric-change').textContent = `Target: ${currentSymbol}`;
    } catch (e) {
        console.error("Error fetching signals", e);
    }
}

async function loadBacktest() {
    try {
        const response = await fetch(`${API_BASE}/backtest`);
        const data = await response.json();

        if (data.status === "error") {
            console.error(data.message);
            return;
        }

        document.getElementById('bt-strategy-return').textContent = `${data.total_return.toFixed(2)}%`;
        document.getElementById('bt-market-return').textContent = `${data.market_return.toFixed(2)}%`;
        document.getElementById('bt-sharpe').textContent = data.sharpe_ratio.toFixed(2);
        document.getElementById('bt-drawdown').textContent = `${data.max_drawdown.toFixed(2)}%`;

        // Color coding
        document.getElementById('bt-strategy-return').style.color = data.total_return >= 0 ? '#22c55e' : '#ef4444';
    } catch (e) {
        console.error("Error loading backtest", e);
    }
}

// Fetch and Update Portfolio
async function updatePortfolio() {
    try {
        const response = await fetch(`${API_BASE}/portfolio`);
        const result = await response.json();

        const rows = result.data.map(item => `
            <tr>
                <td>${item.symbol}</td>
                <td>${item.qty}</td>
                <td>₹${item.avg_price}</td>
                <td style="color: ${item.pnl >= 0 ? '#22c55e' : '#ef4444'}">
                    ₹${item.pnl.toFixed(2)}
                </td>
            </tr>
        `).join('');

        // Populate Dashboard Table
        const miniTable = document.querySelector('#portfolio-table tbody');
        if (miniTable) miniTable.innerHTML = rows;

        // Populate Dedicated Table
        const dedicatedTable = document.querySelector('#portfolio-table-dedicated tbody');
        if (dedicatedTable) dedicatedTable.innerHTML = rows;

    } catch (e) {
        console.error("Error fetching portfolio", e);
    }
}

// Fetch and Update Orders
async function updateOrders() {
    try {
        const response = await fetch(`${API_BASE}/orders`);
        const result = await response.json();

        const tbody = document.querySelector('#orders-table tbody');
        if (!tbody) return;

        tbody.innerHTML = result.map(order => `
            <tr>
                <td>${order.order_id}</td>
                <td>${order.symbol}</td>
                <td><span class="badge ${order.side === 'BUY' ? 'badge-buy' : 'badge-sell'}">${order.side}</span></td>
                <td>${order.status}</td>
                <td>${order.qty || '--'}</td>
            </tr>
        `).join('');
    } catch (e) {
        console.error("Error fetching orders", e);
    }
}

// Mock chart update
let timeCount = 0;
function simulateLiveChart() {
    const time = new Date();
    const price = 21000 + Math.random() * 100;

    Plotly.extendTraces('main-chart', {
        x: [[time]],
        y: [[price]]
    }, [0]);

    if (timeCount > 50) {
        Plotly.relayout('main-chart', {
            xaxis: {
                range: [new Date(time.getTime() - 50 * 1000), time]
            }
        });
    }
    timeCount++;
}

// Search Logic
async function handleSearch(query) {
    if (!query) return;
    try {
        const response = await fetch(`${API_BASE}/search?query=${query}`);
        const result = await response.json();

        if (result.results && result.results.length > 0) {
            currentSymbol = result.results[0];
            console.log(`Switched to: ${currentSymbol}`);

            // Clear current chart and re-init
            Plotly.purge('main-chart');
            initChart();

            // Immediate updates
            updateSignals();
            updateLiveMetrics();

            // Update UI feedback
            document.querySelector('.chart-header h3').textContent = `${currentSymbol} Real-time Analysis`;
        } else {
            alert("No matching symbol found. Try 'NIFTY 50', 'BANKNIFTY', or 'SENSEX'.");
        }
    } catch (e) {
        console.error("Search failed", e);
    }
}

// Tab Switching Logic
function initTabs() {
    const navItems = document.querySelectorAll('.sidebar nav li');

    navItems.forEach((item, index) => {
        item.addEventListener('click', () => {
            navItems.forEach(i => i.classList.remove('active'));
            item.classList.add('active');

            const viewName = item.textContent.trim().toLowerCase();
            showView(viewName);
        });
    });
}

// Broker Switching Logic
async function handleBrokerSwitch(broker) {
    try {
        const response = await fetch(`${API_BASE}/config/switch?broker=${broker}`, {
            method: 'POST'
        });
        const result = await response.json();

        if (result.status === "success") {
            updateUIWithConfig(result.active_broker);
            updateProfile(); // Refresh profile for new broker
        }
    } catch (e) {
        console.error("Error switching broker", e);
    }
}

async function updateUIWithConfig(activeBroker) {
    const display = document.getElementById('active-broker-display');
    const selector = document.getElementById('broker-selector');

    const name = activeBroker === 'indstocks' ? 'Indstocks' : 'Kotak Neo';
    display.textContent = `${name} Connected`;
    if (selector) selector.value = activeBroker;
}

async function loadConfig() {
    try {
        const response = await fetch(`${API_BASE}/config`);
        const config = await response.json();
        updateUIWithConfig(config.active_broker);
    } catch (e) {
        console.error("Error loading config", e);
    }
}

function showView(name) {
    const views = document.querySelectorAll('.tab-content');
    views.forEach(v => v.classList.remove('active'));

    if (name.includes('dashboard')) document.getElementById('dashboard-view').classList.add('active');
    else if (name.includes('portfolio')) document.getElementById('portfolio-view').classList.add('active');
    else if (name.includes('options review')) {
        document.getElementById('options-review-view').classList.add('active');
        refreshOptionIdeas();
    }
    else if (name.includes('orders')) document.getElementById('orders-view').classList.add('active');
    else if (name.includes('models')) document.getElementById('models-view').classList.add('active');
    else if (name.includes('settings')) document.getElementById('settings-view').classList.add('active');
}

function optionIdeaMarkup(data) {
    if (data.status === 'error') {
        return `<article class="option-card"><h4>${data.symbol || 'Index'}</h4><p class="section-copy">${data.message}</p></article>`;
    }

    const directionClass = data.signal === 'BUY' ? 'badge-buy' : 'badge-sell';
    return `<article class="option-card">
        <div class="option-card-header"><h4>${data.symbol}</h4><span class="badge ${directionClass}">${data.option_side}</span></div>
        <p class="section-copy">${data.signal_type}</p>
        <dl class="option-levels">
            <div><dt>Index reference</dt><dd>₹${data.price.toFixed(2)}</dd></div>
            <div><dt>Confidence</dt><dd>${(data.confidence * 100).toFixed(0)}%</dd></div>
            <div><dt>Stop reference</dt><dd>₹${data.stop_loss}</dd></div>
            <div><dt>Target reference</dt><dd>₹${data.target}</dd></div>
        </dl>
        <p class="risk-note">These levels refer to the index, not an option premium. Choose strike, expiry, liquidity, and position size independently.</p>
        <div class="option-actions">
            <button class="btn-sm" onclick='recordReviewedSignal(${JSON.stringify(data).replace(/'/g, "&#39;")})'>Mark reviewed</button>
            <button class="btn-sm active" onclick='sendTelegramAlert(${JSON.stringify(data).replace(/'/g, "&#39;")})'>Send alert</button>
        </div>
    </article>`;
}

async function refreshOptionIdeas() {
    const container = document.getElementById('options-ideas');
    if (!container) return;
    container.innerHTML = '<p class="metric-label">Refreshing educational observations...</p>';
    try {
        const responses = await Promise.all(['NIFTY 50', 'SENSEX'].map(symbol =>
            fetch(`${API_BASE}/options-signals?symbol=${encodeURIComponent(symbol)}`).then(response => response.json())
        ));
        container.innerHTML = responses.map(optionIdeaMarkup).join('');
    } catch (error) {
        console.error('Could not load options observations', error);
        container.innerHTML = '<p class="metric-label">Observations are unavailable. Start the FastAPI service or deploy its API separately.</p>';
    }
}

function getReviewedSignals() {
    return JSON.parse(localStorage.getItem(REVIEW_STORAGE_KEY) || '[]');
}

function recordReviewedSignal(signal) {
    const reviewed = getReviewedSignals();
    const entry = { ...signal, reviewed_at: new Date().toISOString() };
    localStorage.setItem(REVIEW_STORAGE_KEY, JSON.stringify([entry, ...reviewed].slice(0, 100)));
    renderReviewedSignals();
}

function renderReviewedSignals() {
    const tbody = document.querySelector('#reviewed-signals-table tbody');
    if (!tbody) return;
    const rows = getReviewedSignals();
    tbody.innerHTML = rows.length ? rows.map(entry => `<tr>
        <td>${new Date(entry.reviewed_at).toLocaleString('en-IN')}</td>
        <td>${entry.symbol}</td>
        <td><span class="badge ${entry.signal === 'BUY' ? 'badge-buy' : 'badge-sell'}">${entry.option_side}</span></td>
        <td>₹${Number(entry.price).toFixed(2)}</td>
        <td>₹${entry.stop_loss}</td>
        <td>Reviewed</td>
    </tr>`).join('') : '<tr><td colspan="6" class="empty-state">No signals reviewed yet.</td></tr>';
}

function clearReviewedSignals() {
    localStorage.removeItem(REVIEW_STORAGE_KEY);
    renderReviewedSignals();
}

async function sendTelegramAlert(signal) {
    const alertKey = document.getElementById('alert-api-key')?.value;
    if (!alertKey) {
        alert('Enter the alert access key in Settings before sending an alert.');
        return;
    }

    const message = `Prostock educational observation\n\n${signal.symbol}: ${signal.option_side}\nIndex reference: ₹${signal.price.toFixed(2)}\nStop reference: ₹${signal.stop_loss}\nTarget reference: ₹${signal.target}\nConfidence: ${(signal.confidence * 100).toFixed(0)}%\n\nManual review required. No trade is executed by this alert.`;
    try {
        const response = await fetch('/api/telegram-alert', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${alertKey}`
            },
            body: JSON.stringify({ message })
        });
        const result = await response.json();
        if (!response.ok) throw new Error(result.error || 'Unable to send Telegram alert');
        alert('Telegram alert sent. No trade was placed.');
    } catch (error) {
        console.error('Telegram alert failed', error);
        alert(error.message);
    }
}

// Fetch and Update User Profile from Indstocks
async function updateProfile() {
    try {
        const response = await fetch(`${API_BASE}/profile`);
        const result = await response.json();

        if (result.status === "success") {
            const user = result.data;
            // Update profile section if we have a name/id field
            console.log(`Connected to Indstocks as ${user.first_name}`);
            // You could update a name label in header if present
        }
    } catch (e) {
        console.error("Error fetching profile", e);
    }
}

// Live Clock Logic
function refreshClock() {
    const now = new Date();
    const timeStr = now.toLocaleTimeString('en-IN', { hour12: false });
    const dateStr = now.toLocaleDateString('en-IN', { day: '2-digit', month: 'short' });
    document.getElementById('live-clock').textContent = `${dateStr} | ${timeStr}`;
}

// Fetch Real Live Data for all Indices
async function updateLiveMetrics() {
    try {
        // 1. Update Index Cards & Status
        const indexResponse = await fetch(`${API_BASE}/indices`);
        const result = await indexResponse.json();

        if (result.status === "error") {
            console.warn("Index API Error:", result.message);
            return;
        }

        // Update Market Status Badge
        const statusObj = result.market;
        if (statusObj) {
            const statusBadge = document.getElementById('market-status-badge');
            statusBadge.textContent = statusObj.status.toUpperCase();
            statusBadge.className = `market-status ${statusObj.open ? 'open' : 'closed'}`;
        }

        const cardMap = {
            "NIFTY 50": 1,
            "BANKNIFTY": 2,
            "SENSEX": 3
        };

        for (const [name, data] of Object.entries(result)) {
            if (name === "market") continue;

            const cardIdx = cardMap[name];
            if (cardIdx) {
                const card = document.querySelector(`.metrics-grid .metric-card:nth-child(${cardIdx})`);
                card.querySelector('.metric-value').textContent = `₹${data.price.toFixed(2)}`;
                const changeEl = card.querySelector('.metric-change');
                changeEl.textContent = `${data.change >= 0 ? '+' : ''}${data.change.toFixed(2)} (${data.change_pct.toFixed(2)}%)`;
                changeEl.className = `metric-change ${data.change >= 0 ? 'positive' : 'negative'}`;
            }
        }

        // 2. Update Main Chart (using active symbol)
        const symbolData = result[currentSymbol];
        if (symbolData) {
            const time = new Date();
            Plotly.extendTraces('main-chart', {
                x: [[time]],
                y: [[symbolData.price]]
            }, [0]);
        }

    } catch (e) {
        console.error("Error updating live metrics", e);
    }
}

// Global Init
document.addEventListener('DOMContentLoaded', () => {
    initChart();
    initTabs();
    loadConfig();
    updateSignals();
    updatePortfolio();
    updateOrders();
    updateProfile();
    loadBacktest();
    renderReviewedSignals();
    refreshClock();

    // Refresh loop
    setInterval(refreshClock, 1000); // Live Clock
    setInterval(updateSignals, 10000); // AI Prediction refresh
    setInterval(updateLiveMetrics, 2000); // Live index refresh (including BankNifty/Sensex)
    setInterval(updatePortfolio, 30000);
    setInterval(updateOrders, 30000);
});
