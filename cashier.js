function renderOrders(orders) {
  const preparingList = document.getElementById('preparingList');
  const readyList = document.getElementById('readyList');

  setOrderDensity(preparingList, orders.preparing.length);
  setOrderDensity(readyList, orders.ready.length);

  preparingList.innerHTML = orders.preparing
    .map(
      (order) => `
        <article class="order-card cashier-order-card" data-order-id="${order.id}" aria-label="Preparing order number ${order.orderNumber}">
          <span class="order-label">Preparing</span>
          <span class="order-number">#${order.orderNumber}</span>
        </article>
      `
    )
    .join('');

  readyList.innerHTML = orders.ready
    .map(
      (order) => `
        <article class="order-card cashier-ready-order-card" data-order-id="${order.id}" aria-label="Ready order number ${order.orderNumber}">
          <span class="order-label">Ready</span>
          <span class="order-number">#${order.orderNumber}</span>
        </article>
      `
    )
    .join('');

  document.getElementById('preparingCount').textContent = orders.preparing.length;
  document.getElementById('readyCount').textContent = orders.ready.length;
}

function setOrderDensity(list, count) {
  list.dataset.density =
    count > 14 ? 'tight' : count > 8 ? 'dense' : count > 4 ? 'compact' : 'normal';
}

const syncStatus = document.getElementById('syncStatus');
const orderForm = document.getElementById('orderForm');
const orderInput = document.getElementById('orderNumberInput');
const statsDate = document.getElementById('statsDate');
const exportReportButton = document.getElementById('exportReportButton');
const today = new Date();
statsDate.value = [
  today.getFullYear(),
  String(today.getMonth() + 1).padStart(2, '0'),
  String(today.getDate()).padStart(2, '0'),
].join('-');

function setStatus(message, isError = false) {
  syncStatus.textContent = message;
  syncStatus.classList.toggle('sync-error', isError);
}

async function loadOrders() {
  const response = await fetch('/api/orders');
  if (!response.ok) throw new Error('Unable to load orders.');
  renderOrders(await response.json());
}

function localDayRange(date) {
  const [year, month, day] = date.split('-').map(Number);
  const start = new Date(year, month - 1, day);
  const end = new Date(year, month - 1, day + 1);
  return { start: start.toISOString(), end: end.toISOString() };
}

function formatDuration(seconds) {
  if (seconds === null) return '—';
  const minutes = Math.round(seconds / 60);
  if (minutes < 1) return '<1 min';
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return remainingMinutes ? `${hours} hr ${remainingMinutes} min` : `${hours} hr`;
}

function formatTime(timestamp) {
  if (!timestamp) return '—';
  return new Intl.DateTimeFormat(undefined, {
    hour: 'numeric',
    minute: '2-digit',
  }).format(new Date(timestamp));
}

function renderOrderHistory(orders) {
  const history = document.getElementById('orderHistory');
  document.getElementById('historyCount').textContent = `${orders.length} ${
    orders.length === 1 ? 'order' : 'orders'
  }`;

  if (orders.length === 0) {
    history.innerHTML = '<tr><td class="history-empty" colspan="5">No orders for this day</td></tr>';
    return;
  }

  history.innerHTML = orders
    .map(
      (order) => `
        <tr>
          <td class="history-order-number">#${order.orderNumber}</td>
          <td><span class="history-status history-status-${order.status}">${order.status}</span></td>
          <td>${formatTime(order.createdAt)}</td>
          <td>${formatTime(order.readyAt)}</td>
          <td>${formatTime(order.collectedAt)}</td>
        </tr>
      `
    )
    .join('');
}

const historyToggle = document.getElementById('historyToggle');
const historyContent = document.getElementById('historyContent');

historyToggle.addEventListener('click', () => {
  const isExpanded = historyToggle.getAttribute('aria-expanded') !== 'true';
  historyToggle.setAttribute('aria-expanded', String(isExpanded));
  historyContent.hidden = !isExpanded;
  historyToggle.textContent = isExpanded ? 'Hide history' : 'View history';
});

async function loadStatistics() {
  const date = document.getElementById('statsDate').value;
  const range = localDayRange(date);
  const params = new URLSearchParams(range);
  const [statsResponse, historyResponse] = await Promise.all([
    fetch(`/api/stats?${params}`),
    fetch(`/api/orders/history?${params}`),
  ]);
  if (!statsResponse.ok) throw new Error('Unable to load daily statistics.');
  if (!historyResponse.ok) throw new Error('Unable to load order history.');
  const [stats, history] = await Promise.all([
    statsResponse.json(),
    historyResponse.json(),
  ]);

  document.getElementById('statsTotal').textContent = stats.totalOrders;
  document.getElementById('statsReady').textContent = stats.readyOrders;
  document.getElementById('statsCollected').textContent = stats.collectedOrders;
  document.getElementById('statsPreparationTime').textContent = formatDuration(
    stats.averagePreparationSeconds
  );
  document.getElementById('statsCollectionTime').textContent = formatDuration(
    stats.averageCollectionSeconds
  );
  renderOrderHistory(history.orders);
}

async function refreshDashboard() {
  try {
    await Promise.all([loadOrders(), loadStatistics()]);
    setStatus('Connected. Changes sync with the customer display.');
  } catch (error) {
    setStatus(`Dashboard update failed: ${error.message}`, true);
  }
}

orderForm.addEventListener('submit', async (event) => {
  event.preventDefault();

  const orderNumber = Number(orderInput.value);
  if (!Number.isSafeInteger(orderNumber) || orderNumber < 1) {
    setStatus('Enter a valid order number.', true);
    return;
  }

  if (!window.confirm(`Add order #${orderNumber} to Preparing?`)) return;

  try {
    const response = await fetch('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ orderNumber }),
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to add order.');

    orderInput.value = '';
    setStatus(`Order #${orderNumber} added to Preparing.`);
    orderInput.focus();
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById('preparingList').addEventListener('dblclick', async (event) => {
  const orderCard = event.target.closest('.cashier-order-card');
  if (!orderCard) return;

  try {
    const response = await fetch(`/api/orders/${orderCard.dataset.orderId}/ready`, {
      method: 'POST',
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to mark order ready.');
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
});

document.getElementById('readyList').addEventListener('dblclick', async (event) => {
  const orderCard = event.target.closest('.cashier-ready-order-card');
  if (!orderCard) return;

  await collectReadyOrder(orderCard.dataset.orderId);
});

async function collectReadyOrder(orderId) {
  try {
    const response = await fetch(`/api/orders/${orderId}`, {
      method: 'DELETE',
    });
    const result = await response.json();
    if (!response.ok) throw new Error(result.error || 'Unable to collect order.');
    await refreshDashboard();
  } catch (error) {
    setStatus(error.message, true);
  }
}

statsDate.addEventListener('change', () => {
  loadStatistics().catch((error) => setStatus(error.message, true));
});

exportReportButton.addEventListener('click', async () => {
  const date = statsDate.value;
  if (!date) {
    setStatus('Choose a day to export.', true);
    return;
  }

  exportReportButton.disabled = true;
  try {
    const params = new URLSearchParams({
      ...localDayRange(date),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
    });
    const response = await fetch(`/api/reports/daily.xlsx?${params}`);
    if (!response.ok) {
      const result = await response.json();
      throw new Error(result.error || 'Unable to export daily report.');
    }

    const downloadUrl = URL.createObjectURL(await response.blob());
    const downloadLink = document.createElement('a');
    downloadLink.href = downloadUrl;
    downloadLink.download = `daily-orders-${date}.xlsx`;
    document.body.append(downloadLink);
    downloadLink.click();
    downloadLink.remove();
    window.setTimeout(() => URL.revokeObjectURL(downloadUrl), 1000);
    setStatus(`Excel report for ${date} downloaded.`);
  } catch (error) {
    setStatus(error.message, true);
  } finally {
    exportReportButton.disabled = false;
  }
});

refreshDashboard();
window.setInterval(refreshDashboard, 3000);
