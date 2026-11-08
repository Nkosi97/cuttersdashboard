function renderOrders(orders) {
  const preparingList = document.getElementById('preparingList');
  const readyList = document.getElementById('readyList');

  setOrderDensity(preparingList, orders.preparing.length);
  setOrderDensity(readyList, orders.ready.length);

  preparingList.innerHTML = orders.preparing
    .map(
      (order) => `
        <article class="order-card" aria-label="Preparing order number ${order.orderNumber}">
          <span class="order-label">Preparing</span>
          <span class="order-number">#${order.orderNumber}</span>
        </article>
      `
    )
    .join('');

  readyList.innerHTML = orders.ready
    .map(
      (order) => `
        <article class="order-card" aria-label="Ready order number ${order.orderNumber}">
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

async function refreshOrders() {
  try {
    const response = await fetch('/api/orders', { cache: 'no-store' });
    if (!response.ok) throw new Error('Unable to load orders.');
    renderOrders(await response.json());
    syncStatus.textContent = 'Live customer display';
    syncStatus.classList.remove('sync-error');
  } catch (error) {
    syncStatus.textContent = `Unable to connect to the order board: ${error.message}`;
    syncStatus.classList.add('sync-error');
  }
}

refreshOrders();
window.setInterval(refreshOrders, 3000);
