/**
 * CulinaryOS - Main Application Controller
 * Handles View Switching, Truth Matrix, KDS, Fleet Radar, Analytics,
 * Direct Quantity Controls with Waste Prevention Modal, and Automated Scenarios.
 */

const App = {
  currentOrderId: null,
  orders: [],
  analytics: {},
  activeTab: 'tower',
  pollTimer: null,
  pendingQtyChange: null,
  lastSig: null,
  busy: false,
  pendingImage: null,
  pendingImageUrl: null,
  health: null,
  ALLOWED_IMAGES: ['image/png', 'image/jpeg', 'image/webp'],
  MAX_IMAGE_BYTES: 5_000_000,

  async init() {
    this.setupEventListeners();
    VoiceStudio.init();
    this.setupImageOrder();
    this.loadHealth();
    await this.loadAllData();
    this.startPolling();
  },

  setupEventListeners() {
    // Navigation Tabs
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.addEventListener('click', () => {
        this.switchTab(btn.dataset.tab);
      });
    });

    // Chat form is re-rendered dynamically, so listen via delegation (a listener bound at
    // startup would never fire and the browser would do a native form submit / page reload).
    document.addEventListener('submit', (e) => {
      if (e.target && e.target.id === 'chat-send-form') {
        e.preventDefault();
        this.handleSendMessage();
      }
    });

    // Modal Cancel Button
    const cancelModalBtn = document.getElementById('btn-modal-cancel');
    if (cancelModalBtn) {
      cancelModalBtn.addEventListener('click', () => this.closeModal());
    }

    // Modal Confirm Button
    const confirmModalBtn = document.getElementById('btn-modal-confirm');
    if (confirmModalBtn) {
      confirmModalBtn.addEventListener('click', () => this.executePendingQtyChange());
    }
  },

  switchTab(tabName) {
    this.activeTab = tabName;
    document.querySelectorAll('.tab-btn').forEach(btn => {
      btn.classList.toggle('active', btn.dataset.tab === tabName);
    });

    document.querySelectorAll('.view-panel').forEach(panel => {
      panel.classList.toggle('active', panel.id === `view-${tabName}`);
    });

    if (tabName === 'kds') this.renderKDS();
    if (tabName === 'radar') this.renderRadar();
    if (tabName === 'analytics') this.renderAnalytics();
    if (tabName === 'voice') VoiceStudio.setLanguage(VoiceStudio.activeLang);
  },

  startPolling() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = setInterval(() => {
      this.refreshDataSilent();
    }, 3000);
  },

  async loadAllData() {
    try {
      this.orders = await API.getOrders();
      this.analytics = await API.getAnalytics();
      this.renderKPIs();
      this.renderOrderList();

      if (this.orders.length > 0) {
        if (!this.currentOrderId || !this.orders.some(o => o.order_id === this.currentOrderId)) {
          this.currentOrderId = this.orders[0].order_id;
        }
        await this.refreshCurrentOrder();
      } else {
        this.currentOrderId = null;
        this.renderEmptyState();
      }

      if (this.activeTab === 'kds') this.renderKDS();
      if (this.activeTab === 'radar') this.renderRadar();
      if (this.activeTab === 'analytics') this.renderAnalytics();
    } catch (err) {
      console.error('Initial load failed:', err);
    }
  },

  async refreshDataSilent() {
    if (this.busy || document.hidden) return;
    try {
      this.orders = await API.getOrders();
      this.analytics = await API.getAnalytics();
      this.renderKPIs();
      this.renderOrderList();

      if (this.currentOrderId) {
        const cur = this.orders.find(o => o.order_id === this.currentOrderId);
        if (cur) {
          const detail = await API.getOrder(this.currentOrderId);
          this.renderControlTower(detail);
        }
      }

      if (this.activeTab === 'kds') this.renderKDS();
      if (this.activeTab === 'radar') this.renderRadar();
      if (this.activeTab === 'analytics') this.renderAnalytics();
    } catch (e) {
      // silent background poll failure
    }
  },

  async refreshCurrentOrder() {
    if (!this.currentOrderId) return;
    try {
      const order = await API.getOrder(this.currentOrderId);
      this.renderControlTower(order);
    } catch (err) {
      console.error('Failed to load order details:', err);
    }
  },

  renderKPIs() {
    const a = this.analytics || {};
    document.getElementById('kpi-active-orders').innerText = a.active_orders ?? 0;
    document.getElementById('kpi-total-meals').innerText = a.total_meals ?? 0;
    document.getElementById('kpi-active-allergens').innerText = a.active_allergens_tracked ?? 0;
    document.getElementById('kpi-waste-prevention').innerText = a.waste_prevention_triggers ?? 0;

    // Badges on tabs
    const kdsBadge = document.getElementById('badge-kds-count');
    if (kdsBadge) kdsBadge.innerText = a.active_orders ?? 0;

    const radarBadge = document.getElementById('badge-radar-count');
    if (radarBadge) {
      const outCount = this.orders.filter(o => o.status === 'OUT_FOR_DELIVERY').length;
      radarBadge.innerText = outCount;
    }
  },

  renderOrderList() {
    const list = document.getElementById('orders-selector-list');
    if (!list) return;

    if (this.orders.length === 0) {
      list.innerHTML = `<div style="text-align:center; padding:1.5rem; color:var(--text-dim); font-size:0.8rem;">No orders currently active.<br><button class="btn-pill btn-pill-seed" style="margin-top:0.75rem;" onclick="App.handleSeedDemo()">+ Seed Demo Orders</button></div>`;
      return;
    }

    list.innerHTML = this.orders.map(o => {
      const isSelected = o.order_id === this.currentOrderId;
      const statusClass = o.status || 'RECEIVED';
      const langBadge = (o.customer && o.customer.lang) ? o.customer.lang.toUpperCase() : 'EN';
      const hasAllergy = o.allergies && o.allergies.length > 0;
      const oid = esc(o.order_id);

      return `
        <div class="order-selector-item ${isSelected ? 'selected' : ''}" onclick="App.selectOrder('${oid}')">
          <div class="order-item-header">
            <span class="order-item-id">${oid}</span>
            <span class="status-badge ${esc(statusClass)}">${esc(statusClass.replace(/_/g, ' '))}</span>
          </div>
          <div class="order-item-dish">${esc(o.dish || 'Chef Special Meal Box')}</div>
          <div class="order-item-footer">
            <span>👤 ${esc(o.customer?.name || 'Customer')}</span>
            <span>🍽️ <strong>${o.quantity}</strong> meals</span>
            <span style="font-family:var(--font-mono); font-size:0.7rem; color:var(--text-muted);">${langBadge}</span>
            ${hasAllergy ? '<span title="Critical Allergen" style="color:var(--danger)">⚠️</span>' : ''}
          </div>
        </div>
      `;
    }).join('');
  },

  async selectOrder(oid) {
    this.currentOrderId = oid;
    this.lastSig = null;
    this.renderOrderList();
    await this.refreshCurrentOrder();
  },

  renderEmptyState() {
    const right = document.getElementById('tower-right-pipeline');
    if (right) right.innerHTML = '';
    const box = document.getElementById('tower-center-content');
    if (box) {
      box.innerHTML = `
        <div class="glass-card" style="text-align:center; padding:3rem 1.5rem;">
          <div style="font-size:2.5rem; margin-bottom:1rem;">🍳</div>
          <h3 style="font-size:1.2rem; margin-bottom:0.5rem;">Clean Slate: No Active Orders</h3>
          <p style="color:var(--text-muted); max-width:450px; margin:0 auto 1.5rem; font-size:0.85rem;">
            The Kitchen Control Tower is clean and awaiting orders. You can place real orders via chat/voice or seed realistic demonstration orders.
          </p>
          <div style="display:flex; justify-content:center; gap:0.75rem;">
            <button class="btn-pill btn-pill-seed" onclick="App.handleSeedDemo()">🌱 Seed Realistic Enterprise Orders</button>
            <button class="btn-pill" onclick="App.createNewBlankOrder()">➕ Create New Order</button>
            <button class="btn-pill" onclick="App.openImageOrder()">📷 Order from Image</button>
          </div>
        </div>
      `;
    }
  },

  renderControlTower(order, force = false) {
    const box = document.getElementById('tower-center-content');
    if (!box || !order) return;

    // Skip redundant re-renders (the 3s poll would otherwise wipe what the user is typing).
    const sig = JSON.stringify(order);
    if (!force && sig === this.lastSig && box.querySelector('.truth-matrix-card')) return;
    this.lastSig = sig;

    // Preserve chat draft, sender role and focus across re-renders
    const prevInput = document.getElementById('chat-text-input');
    const draft = prevInput ? prevInput.value : '';
    const hadFocus = prevInput && document.activeElement === prevInput;
    const prevRole = document.getElementById('chat-sender-role');
    const role = prevRole ? prevRole.value : 'customer';
    const prevChat = document.getElementById('chat-history-box');
    const wasAtBottom = !prevChat || (prevChat.scrollHeight - prevChat.scrollTop - prevChat.clientHeight < 40);

    const oid = esc(order.order_id);
    const status = order.status || 'RECEIVED';
    const terminal = status === 'CANCELLED' || status === 'DELIVERED';
    const isMissingQty = (!order.quantity || order.quantity === 0);
    const addr = order.delivery && order.delivery.address ? String(order.delivery.address).trim() : '';
    const isMissingAddr = !addr;
    const hasMissingWarning = !terminal && (isMissingQty || isMissingAddr);

    const alerts = order.alerts || [];
    const wasteAlert = alerts.find(a => a[1] && (a[1].includes('Food Waste') || a[1].includes('Quantity changed')));
    const otherAlerts = alerts.filter(a => a !== wasteAlert && !(a[1] || '').includes('Incomplete order'));
    const openConflicts = (order.conflicts || []).filter(c => !c.resolved);
    const pending = order.pending_approvals || [];
    const allergies = order.allergies || [];

    box.innerHTML = `
      ${hasMissingWarning ? `
        <div class="missing-warning-banner">
          <div>
            <div class="warning-info-title">⚠️ Incomplete Order Warning: Required Details Missing</div>
            <div class="warning-info-sub">
              ${isMissingQty && isMissingAddr ? 'Both meal quantity and delivery address details must be provided to proceed.' :
                isMissingQty ? 'Meal quantity has not been specified yet.' :
                'Delivery address is missing from customer request.'}
            </div>
          </div>
          <div class="warning-action-buttons">
            ${isMissingQty ? `<button class="btn-pill" style="font-size:0.75rem;" onclick="App.quickPromptQuantity('${oid}')">+ Add 2 Meals</button>` : ''}
            ${isMissingAddr ? `<button class="btn-pill" style="font-size:0.75rem;" onclick="App.quickPromptAddress('${oid}')">+ Add Address</button>` : ''}
          </div>
        </div>
      ` : ''}

      ${wasteAlert ? `
        <div class="waste-alert-banner">
          <span style="font-size:1.3rem;">⚡</span>
          <div>
            <strong>Food Waste Prevention Triggered:</strong>
            <span>${esc(wasteAlert[1])}</span>
          </div>
        </div>
      ` : ''}

      ${openConflicts.length > 0 ? `
        <div class="conflict-card">
          <div style="font-weight:700; color:#ef4444; font-size:0.9rem;">⚠️ Address Ambiguity Detected by Delivery Agent</div>
          <div style="font-size:0.8rem; color:#fca5a5;">Multiple destination addresses detected. Dispatch is blocked until the correct delivery location is confirmed:</div>
          <div style="display:flex; flex-direction:column; gap:0.4rem;">
            ${(openConflicts[0].options || []).map(opt => `
              <button class="conflict-option-btn" data-addr="${esc(opt)}" onclick="App.resolveAddressConflict('${oid}', this.dataset.addr)">
                📍 Confirm Address: <strong>${esc(opt)}</strong>
              </button>
            `).join('')}
          </div>
        </div>
      ` : ''}

      ${pending.length > 0 ? `
        <div class="conflict-card">
          <div style="font-weight:700; color:#ef4444; font-size:0.9rem;">🔴 Late Modification Awaiting Kitchen Approval (${pending.length})</div>
          <div style="font-size:0.8rem; color:#fca5a5;">The customer asked for a change after the order was packed. Approve to apply it, or leave it queued.</div>
          <div><button class="btn-pill btn-pill-seed" onclick="App.approvePending('${oid}')">✔ Approve Next Modification</button></div>
        </div>
      ` : ''}

      ${otherAlerts.length > 0 ? `
        <div class="glass-card" style="padding:0.75rem 1rem;">
          <div class="card-title" style="margin-bottom:0.5rem;">🚦 Live Alerts</div>
          ${otherAlerts.map(a => `<div style="font-size:0.8rem; margin-bottom:0.3rem; color:${a[0] === 'crit' ? '#fca5a5' : a[0] === 'ok' ? 'var(--success)' : '#fde68a'};">${esc(a[1])}</div>`).join('')}
        </div>
      ` : ''}

      <!-- Ground Truth Matrix -->
      <div class="glass-card truth-matrix-card">
        <div class="card-title-bar">
          <div class="card-title">
            <span>🛡️ AI Ground Truth Matrix</span>
            <span style="font-family:var(--font-mono); font-size:0.75rem; color:var(--text-muted); font-weight:normal;">Order #${oid}</span>
          </div>
          <div style="display:flex; align-items:center; gap:0.5rem;">
            <span class="status-badge ${esc(status)}">${esc(status.replace(/_/g, ' '))}</span>
            <button class="btn-pill" style="padding:0.2rem 0.5rem; font-size:0.75rem;" onclick="App.readOrderTruthAloud()">🔊 Read Out</button>
          </div>
        </div>

        <div class="truth-grid">
          <!-- Quantity Tile -->
          <div class="truth-tile">
            <div class="truth-tile-label">
              <span>Meal Quantity</span>
              <span style="color:var(--primary); font-family:var(--font-mono);">SYNCED</span>
            </div>
            <div style="display:flex; align-items:baseline; justify-content:space-between;">
              <span class="truth-tile-value" style="font-size:1.4rem;">${order.quantity} <span style="font-size:0.8rem; color:var(--text-muted);">meals</span></span>
              ${terminal ? '' : `
              <div class="quantity-control-group">
                <button class="btn-qty" title="Reduce by 1 meal" onclick="App.promptQuantityChange('${oid}', ${order.quantity - 1})">-</button>
                <button class="btn-qty" title="Add 1 meal" onclick="App.promptQuantityChange('${oid}', ${order.quantity + 1})">+</button>
                <button class="btn-qty btn-qty-danger" title="Clear all meals" onclick="App.promptQuantityChange('${oid}', 0)">🗑️</button>
              </div>`}
            </div>
          </div>

          <!-- Allergies Tile -->
          <div class="truth-tile">
            <div class="truth-tile-label">
              <span>Allergen Safeguards</span>
              ${allergies.length > 0 ? '<span style="color:var(--danger); font-weight:700;">ACTIVE HAZARD</span>' : '<span style="color:var(--success);">SAFE</span>'}
            </div>
            <div class="truth-tile-value">
              ${allergies.length > 0 ?
                allergies.map(a => `
                  <div style="margin-bottom:0.25rem; font-size:0.825rem; color:#fca5a5;">
                    ⚠️ <strong>${esc(a.ingredient)}</strong> (${esc(a.applies_to)})
                    ${a.acked ? '<span style="color:var(--success); font-size:0.7rem;"> [Ack ✓]</span>' : `<button class="btn-pill" style="font-size:0.65rem; padding:0.1rem 0.3rem;" onclick="App.ackAllergy('${oid}')">Ack</button>`}
                  </div>
                `).join('') : '<span style="color:var(--text-muted); font-size:0.8rem;">No known allergens</span>'}
            </div>
          </div>

          <!-- Special Preferences Tile -->
          <div class="truth-tile">
            <div class="truth-tile-label">
              <span>Special Instructions</span>
            </div>
            <div class="truth-tile-value" style="font-size:0.8rem; color:#fde68a;">
              ${(order.special && order.special.length > 0) ?
                order.special.map(sp => `<div>• ${esc(sp.requirement)} ${sp.recipient ? `(for ${esc(sp.recipient)})` : ''}${sp.meal ? ` (Meal #${esc(sp.meal)})` : ''}</div>`).join('') :
                '<span style="color:var(--text-muted);">Standard preparation</span>'}
            </div>
          </div>

          <!-- Delivery Address & Slot Tile -->
          <div class="truth-tile">
            <div class="truth-tile-label">
              <span>Delivery Slot & Address</span>
            </div>
            <div class="truth-tile-value" style="font-size:0.8rem;">
              <div style="color:var(--text-main); font-weight:600; margin-bottom:0.15rem;">📍 ${esc(addr || 'Address Pending')}</div>
              <div style="color:var(--primary); font-size:0.75rem;">⏰ After: ${esc(order.delivery?.after || 'ASAP')}</div>
              ${order.delivery_est && order.delivery_est.km ? `<div style="color:var(--text-muted); font-size:0.72rem; margin-top:0.2rem;">🛣️ ${order.delivery_est.km} km · ETA ${order.delivery_est.eta_min} min · ₹${order.delivery_est.charge}</div>` : ''}
            </div>
          </div>
        </div>
      </div>

      <!-- Customer Interaction Stream & Chat -->
      <div class="glass-card">
        <div class="card-title-bar">
          <div class="card-title">
            <span>💬 Conversation Stream</span>
            <span style="font-size:0.75rem; color:var(--agent-customer); font-weight:normal;">(${esc(order.customer?.name || 'Customer')} - ${esc((order.customer?.lang || 'en').toUpperCase())})</span>
          </div>
          <button class="btn-pill" style="font-size:0.75rem;" onclick="App.switchToVoiceStudio('${oid}')">🎙️ Open Voice Studio</button>
        </div>

        <div class="chat-container">
          <div class="chat-history" id="chat-history-box">
            ${(order.messages || []).map(m => {
              const isAi = m.who && String(m.who).includes('AI');
              return `
                <div class="chat-bubble ${isAi ? 'ai' : 'customer'}">
                  <div class="chat-meta">
                    <span class="chat-sender">${esc(m.who)}</span>
                    <span>${esc(m.ts)}</span>
                  </div>
                  <div>${esc(m.text)}</div>
                  ${m.image && /^\/media\/[\w.-]+$/.test(m.image) ? `<a href="${esc(m.image)}" target="_blank" rel="noopener"><img class="chat-thumb" src="${esc(m.image)}" alt="Uploaded order image" /></a>` : ''}
                </div>
              `;
            }).join('')}
          </div>

          <form class="chat-input-bar" id="chat-send-form">
            <select id="chat-sender-role" class="chat-input" style="max-width:110px;" title="Send as">
              ${['customer', 'owner', 'kitchen', 'delivery'].map(r => `<option value="${r}" ${r === role ? 'selected' : ''}>${r[0].toUpperCase() + r.slice(1)}</option>`).join('')}
            </select>
            <label class="btn-pill chat-attach-btn" for="chat-image-input" title="Attach a photo of an order or note">📎</label>
            <input type="file" id="chat-image-input" accept="image/png,image/jpeg,image/webp" hidden onchange="App.handleChatImage(this)" />
            <input type="text" id="chat-text-input" class="chat-input" placeholder="Type a message (Telugu, Hindi, Tamil, Kannada or English)..." required autocomplete="off" maxlength="2000" />
            <button type="submit" class="btn-pill btn-pill-seed">Send</button>
          </form>
        </div>
      </div>
    `;

    // Restore the draft the user was typing
    const input = document.getElementById('chat-text-input');
    if (input && draft) {
      input.value = draft;
      if (hadFocus) { input.focus(); input.setSelectionRange(draft.length, draft.length); }
    }

    this.renderPipelineAndAudit(order);

    const chatBox = document.getElementById('chat-history-box');
    if (chatBox && wasAtBottom) chatBox.scrollTop = chatBox.scrollHeight;
  },

  renderPipelineAndAudit(order) {
    const pipelineBox = document.getElementById('tower-right-pipeline');
    if (!pipelineBox) return;

    const FLOW = ["RECEIVED", "CONFIRMED", "PREPARING", "READY_FOR_PACKAGING", "PACKAGING", "PACKED", "OUT_FOR_DELIVERY", "DELIVERED"];
    const curIdx = FLOW.indexOf(order.status);
    const oid = esc(order.order_id);
    const canAdvance = curIdx >= 0 && curIdx < FLOW.length - 1;
    const canCancel = !['PACKED', 'OUT_FOR_DELIVERY', 'DELIVERED', 'CANCELLED'].includes(order.status);

    pipelineBox.innerHTML = `
      <div class="glass-card" style="margin-bottom:1.25rem;">
        <div class="card-title-bar">
          <div class="card-title">⚡ Lifecycle Pipeline</div>
          <div style="display:flex; gap:0.4rem;">
            ${canCancel ? `<button class="btn-pill btn-pill-reset" style="font-size:0.7rem; padding:0.2rem 0.5rem;" onclick="App.cancelOrder('${oid}')">Cancel</button>` : ''}
            ${canAdvance ? `<button class="btn-pill" style="font-size:0.7rem; padding:0.2rem 0.5rem;" onclick="App.advanceNextStatus('${oid}')">Advance ⏭️</button>` : ''}
          </div>
        </div>
        ${order.status === 'CANCELLED' ? '<div style="color:var(--danger); font-weight:700; font-size:0.8rem; padding:0.25rem 0;">🚫 This order was cancelled.</div>' : ''}
        <div class="pipeline-flow">
          ${FLOW.map((st, i) => {
            let cls = '';
            if (i === curIdx) cls = 'active';
            else if (i < curIdx) cls = 'passed';
            return `
              <div class="flow-step ${cls}">
                <div class="flow-dot"></div>
                <span>${st.replace(/_/g, ' ')}</span>
              </div>
            `;
          }).join('')}
        </div>
      </div>

      <div class="glass-card">
        <div class="card-title-bar">
          <div class="card-title">📜 Immutable Audit Log</div>
          <span style="font-size:0.7rem; color:var(--text-dim); font-family:var(--font-mono);">SQLITE WAL</span>
        </div>
        <div class="audit-events-box">
          ${(order.events || []).slice().reverse().map(e => `
            <div class="audit-event-item">
              <div style="display:flex; justify-content:space-between;">
                <span class="audit-event-type">${esc(e.type)}</span>
                <span style="color:var(--text-dim);">${esc(e.ts)}</span>
              </div>
              <div class="audit-event-detail">${esc(e.detail)}</div>
            </div>
          `).join('')}
        </div>
      </div>
    `;
  },

  // ==========================================
  // VIEW 2: KDS (Kitchen Display System)
  // ==========================================
  renderKDS() {
    const container = document.getElementById('kds-orders-grid');
    if (!container) return;

    const kitchenOrders = this.orders.filter(o => o.status !== 'DELIVERED' && o.status !== 'CANCELLED');
    if (kitchenOrders.length === 0) {
      container.innerHTML = `<div style="grid-column: 1 / -1; text-align:center; padding:3rem; color:var(--text-dim);">No active kitchen orders. Everything is prepped!</div>`;
      return;
    }

    container.innerHTML = kitchenOrders.map(o => {
      const hasAllergy = o.allergies && o.allergies.length > 0;
      const unacknowledgedAllergy = hasAllergy && o.allergies.some(a => !a.acked);
      const oid = esc(o.order_id);

      return `
        <div class="kds-card ${unacknowledgedAllergy ? 'hazard-allergy' : ''}">
          <div class="kds-card-header">
            <span class="kds-order-num">${oid}</span>
            <span class="status-badge ${esc(o.status)}">${esc(o.status.replace(/_/g, ' '))}</span>
          </div>

          <div>
            <div class="kds-dish-title">${esc(o.dish || 'Special Combo Meal')}</div>
            <div style="margin-top:0.35rem;">
              <span class="kds-qty-badge">🍽️ ${o.quantity} Meals</span>
              <span style="font-size:0.75rem; color:var(--text-muted); margin-left:0.5rem;">Due: ${esc(o.delivery?.after || 'ASAP')}</span>
            </div>
          </div>

          ${hasAllergy ? `
            <div class="allergy-alert-box">
              <div class="allergy-title">🚨 ALLERGY SAFETY HAZARD:</div>
              <div>${o.allergies.map(a => `<strong>${esc(a.ingredient)}</strong> (${esc(a.applies_to)})`).join(', ')}</div>
              ${unacknowledgedAllergy ? `
                <button class="btn-ack-allergy" onclick="App.ackAllergy('${oid}')">
                  ✋ Chef Sign-off & Acknowledge
                </button>
              ` : '<div style="color:var(--success); font-weight:600; font-size:0.75rem;">✓ Hazard Confirmed & Signed-off by Chef</div>'}
            </div>
          ` : ''}

          ${(o.special && o.special.length > 0) ? `
            <div class="kds-instructions">
              <strong>Custom Cook Instructions:</strong>
              ${o.special.map(sp => `<div>• ${esc(sp.requirement)}${sp.recipient ? ` (for ${esc(sp.recipient)})` : ''}</div>`).join('')}
            </div>
          ` : ''}

          <div class="kds-actions-bar">
            ${o.status === 'RECEIVED' && o.quantity > 0 ? `
              <button class="btn-kds-advance btn-kds-prep" onclick="App.advanceStatusDirect('${oid}', 'CONFIRMED')">
                ✔ Confirm Order
              </button>
            ` : ''}
            ${o.status === 'CONFIRMED' ? `
              <button class="btn-kds-advance btn-kds-prep" onclick="App.advanceStatusDirect('${oid}', 'PREPARING')">
                🔥 Start Preparing
              </button>
            ` : ''}
            ${o.status === 'PREPARING' ? `
              <button class="btn-kds-advance btn-kds-pack" onclick="App.advanceStatusDirect('${oid}', 'READY_FOR_PACKAGING')">
                📦 Ready for Packaging
              </button>
            ` : ''}
            ${o.status === 'READY_FOR_PACKAGING' ? `
              <button class="btn-kds-advance btn-kds-pack" onclick="App.advanceStatusDirect('${oid}', 'PACKAGING')">
                🏷️ Begin Packaging
              </button>
            ` : ''}
            ${o.status === 'PACKAGING' ? `
              <button class="btn-kds-advance" style="background:var(--success); color:#000;" onclick="App.advanceStatusDirect('${oid}', 'PACKED')">
                ✅ Mark as Packed
              </button>
            ` : ''}
            ${o.status === 'PACKED' ? `
              <button class="btn-kds-advance" style="background:var(--agent-delivery); color:#000;" onclick="App.advanceStatusDirect('${oid}', 'OUT_FOR_DELIVERY')">
                🛵 Hand Over to Fleet
              </button>
            ` : ''}
          </div>
        </div>
      `;
    }).join('');
  },

  // ==========================================
  // VIEW 3: Logistics & Fleet Radar
  // ==========================================
  renderRadar() {
    const list = document.getElementById('radar-deliveries-list');
    if (!list) return;

    const fleetOrders = this.orders.filter(o => o.status === 'OUT_FOR_DELIVERY' || o.status === 'PACKED');
    this.renderRadarPins(fleetOrders);
    if (fleetOrders.length === 0) {
      list.innerHTML = `<div style="text-align:center; padding:2rem; color:var(--text-dim);">No orders currently out on the road.</div>`;
      return;
    }

    list.innerHTML = fleetOrders.map(o => `
      <div class="glass-card" style="padding:0.9rem; margin-bottom:0.75rem;">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:0.35rem;">
          <span style="font-weight:700; color:var(--primary); font-family:var(--font-mono);">${esc(o.order_id)}</span>
          <span class="status-badge ${esc(o.status)}">${esc(o.status.replace(/_/g, ' '))}</span>
        </div>
        <div style="font-size:0.8rem; margin-bottom:0.3rem;">📍 ${esc(o.delivery?.address || 'Address Pending')}${o.delivery_assignment ? ` · 🛵 ${esc(o.delivery_assignment)}` : ''}</div>
        <div style="display:flex; justify-content:space-between; font-size:0.75rem; color:var(--text-muted);">
          <span>Due: ${esc(o.delivery?.after || 'ASAP')}</span>
          <span>${o.quantity} meals</span>
        </div>
        ${o.status === 'OUT_FOR_DELIVERY' ? `
          <button class="btn-pill" style="width:100%; margin-top:0.6rem; justify-content:center; background:rgba(16,185,129,0.15); border-color:var(--success); color:var(--success);" onclick="App.advanceStatusDirect('${esc(o.order_id)}', 'DELIVERED')">
            🏁 Confirm Delivery Completion
          </button>
        ` : ''}
      </div>
    `).join('');
  },

  renderRadarPins(fleetOrders) {
    const map = document.querySelector('.map-radar-mock');
    if (!map) return;
    map.querySelectorAll('.fleet-pin').forEach(n => n.remove());
    const spots = [[35, 42], [25, 68], [50, 30], [70, 50], [20, 25], [55, 75]];
    const pins = fleetOrders.map((o, i) => {
      const [top, left] = spots[i % spots.length];
      const lbl = `${o.order_id} • ${(o.delivery?.address || 'Address Pending').split(',')[0]} (${o.status === 'OUT_FOR_DELIVERY' ? 'On Route' : 'Packed'})`;
      return `<div class="fleet-pin" style="top:${top}%; left:${left}%;"><div class="fleet-pin-dot">🛵</div><div class="fleet-pin-label">${esc(lbl)}</div></div>`;
    });
    pins.push(`<div class="fleet-pin" style="top:60%; left:65%;"><div class="fleet-pin-dot" style="background:var(--primary);">🏪</div><div class="fleet-pin-label">Central Kitchen Hub</div></div>`);
    map.insertAdjacentHTML('beforeend', pins.join(''));
  },

  // ==========================================
  // VIEW 4: Operations Analytics
  // ==========================================
  renderAnalytics() {
    const langsBox = document.getElementById('analytics-lang-breakdown');
    if (!langsBox) return;

    const langs = this.analytics?.language_distribution || {};
    const total = this.analytics?.total_orders || 1;

    const langNames = {
      te: 'Telugu (తెలుగు)',
      hi: 'Hindi (हिन्दी)',
      en: 'English',
      ta: 'Tamil (தமிழ்)',
      kn: 'Kannada (ಕನ್ನಡ)'
    };

    if (Object.keys(langs).length === 0) {
      langsBox.innerHTML = '<div style="color:var(--text-dim); font-size:0.85rem;">No orders yet.</div>';
      return;
    }
    langsBox.innerHTML = Object.entries(langs).map(([code, count]) => {
      const pct = Math.round((count / total) * 100);
      return `
        <div>
          <div class="lang-bar-row">
            <span>${esc(langNames[code] || String(code).toUpperCase())}</span>
            <span style="font-family:var(--font-mono); font-weight:700;">${count} orders (${pct}%)</span>
          </div>
          <div class="progress-track">
            <div class="progress-fill" style="width: ${pct}%;"></div>
          </div>
        </div>
      `;
    }).join('');
  },

  // ==========================================
  // Quantity Adjustment with Waste Prevention Modal
  // ==========================================
  promptQuantityChange(orderId, newQty) {
    if (newQty < 0) return;
    const order = this.orders.find(o => o.order_id === orderId);
    if (!order) return;

    const oldQty = order.quantity;
    if (newQty < oldQty) {
      // Trigger Food Waste Prevention Warning Modal
      this.pendingQtyChange = { orderId, oldQty, newQty };
      this.showWasteModal(oldQty, newQty);
    } else {
      // Direct increase
      this.executeQuantityUpdate(orderId, newQty);
    }
  },

  showWasteModal(oldQty, newQty) {
    const modal = document.getElementById('modal-waste-confirm');
    const desc = document.getElementById('modal-waste-desc');
    if (desc) {
      if (newQty === 0) {
        desc.innerHTML = `You are reducing the quantity from <strong>${oldQty} to 0 meals</strong> (clearing all meals).<br><br>The Kitchen Agent will be alerted immediately to prevent pre-portioned ingredient spoilage and cancel cook sheets.`;
      } else {
        desc.innerHTML = `You are reducing the quantity from <strong>${oldQty} to ${newQty} meals</strong> (-${oldQty - newQty} meals).<br><br>This will log a <strong>Food Waste Prevention Alert</strong> and immediately update kitchen station cook batch sizes.`;
      }
    }
    if (modal) modal.classList.add('open');
  },

  closeModal() {
    const modal = document.getElementById('modal-waste-confirm');
    if (modal) modal.classList.remove('open');
    this.pendingQtyChange = null;
  },

  async executePendingQtyChange() {
    if (!this.pendingQtyChange) return;
    const { orderId, newQty } = this.pendingQtyChange;
    this.closeModal();
    await this.executeQuantityUpdate(orderId, newQty);
  },

  // Runs an action with the poller paused, then fully refreshes the UI.
  async act(fn, okMsg) {
    this.busy = true;
    try {
      const res = await fn();
      if (okMsg) showToast(okMsg, 'success');
      return res;
    } catch (err) {
      return null; // API layer already showed a toast
    } finally {
      this.busy = false;
      this.lastSig = null;
      await this.loadAllData();
    }
  },

  async executeQuantityUpdate(orderId, newQty) {
    const before = ((this.orders.find(o => o.order_id === orderId) || {}).pending_approvals) || 0;
    const res = await this.act(() => API.updateQuantity(orderId, newQty));
    if (!res) return;
    if ((res.pending_approvals || []).length > before) showToast('Order is already packed - the change is queued for kitchen approval.', 'warning', 6000);
    else showToast(`Quantity set to ${newQty} meals`, 'success');
  },

  // ==========================================
  // Customer Chat & Quick Fix Handlers
  // ==========================================
  async handleSendMessage() {
    const input = document.getElementById('chat-text-input');
    const roleSel = document.getElementById('chat-sender-role');
    if (!input || !input.value.trim() || !this.currentOrderId) return;

    const text = input.value.trim();
    const role = roleSel ? roleSel.value : 'customer';
    input.value = '';
    const ok = await this.act(() => API.sendMessage(this.currentOrderId, role, text));
    if (!ok) input.value = text; // keep the message if sending failed
  },

  async quickPromptQuantity(orderId) {
    await this.act(() => API.sendMessage(orderId, 'customer', 'I want 2 meals please.'), 'Sent: "I want 2 meals please."');
  },

  async quickPromptAddress(orderId) {
    await this.act(() => API.sendMessage(orderId, 'customer', 'Deliver to 42 Residency Road.'), 'Sent: "Deliver to 42 Residency Road."');
  },

  async ackAllergy(orderId) {
    await this.act(() => API.acknowledgeAllergy(orderId), 'Chef acknowledged the allergy safety instruction!');
  },

  async resolveAddressConflict(orderId, chosenAddress) {
    await this.act(() => API.resolveConflict(orderId, chosenAddress), `Address resolved to: ${chosenAddress}`);
  },

  async approvePending(orderId) {
    await this.act(() => API.approveModification(orderId), 'Late modification approved and applied');
  },

  async cancelOrder(orderId) {
    if (!confirm(`Cancel order ${orderId}?`)) return;
    await this.act(() => API.cancelOrder(orderId), `Order ${orderId} cancelled`);
  },

  async advanceNextStatus(orderId) {
    const order = this.orders.find(o => o.order_id === orderId);
    if (!order) return;
    const FLOW = ["RECEIVED", "CONFIRMED", "PREPARING", "READY_FOR_PACKAGING", "PACKAGING", "PACKED", "OUT_FOR_DELIVERY", "DELIVERED"];
    const idx = FLOW.indexOf(order.status);
    if (idx >= 0 && idx < FLOW.length - 1) {
      await this.advanceStatusDirect(orderId, FLOW[idx + 1]);
    }
  },

  async advanceStatusDirect(orderId, status) {
    await this.act(() => API.advanceStatus(orderId, status), `Status updated to ${status.replace(/_/g, ' ')}!`);
  },

  switchToVoiceStudio(orderId) {
    this.switchTab('voice');
    const order = this.orders.find(o => o.order_id === orderId);
    if (order && order.customer && order.customer.lang) {
      VoiceStudio.setLanguage(order.customer.lang);
    }
  },

  readOrderTruthAloud() {
    const order = this.orders.find(o => o.order_id === this.currentOrderId);
    if (!order) return;

    const lang = order.customer?.lang || 'en';
    const text = `Order ${order.order_id}. ${order.quantity} meals. Status is ${order.status.replace(/_/g, ' ')}. Delivery address is ${order.delivery?.address}.`;
    VoiceStudio.speakText(text, lang);
  },

  // ==========================================
  // New order from an image (photo of a handwritten / printed order)
  // ==========================================
  async loadHealth() {
    try {
      this.health = await API.getHealth();
      const badge = document.getElementById('mode-badge-text');
      const toggle = document.getElementById('ai-mode-toggle');
      if (badge && this.health) {
        const live = this.health.ai_mode === 'live';
        const ready = !!this.health.live_ready;
        const prov = this.health.providers || {};
        const name = prov.anthropic ? 'Claude' : prov.gemini ? 'Gemini' : null;
        badge.textContent = live && ready ? `LIVE · ${name || 'LLM'} · 3 AGENTS` : 'MOCK MODE · 3 AGENTS';
        if (toggle) {
          toggle.title = ready
            ? `Click to switch to ${live ? 'mock' : 'live'} AI mode`
            : 'Add GEMINI_API_KEY or ANTHROPIC_API_KEY to .env to enable live mode';
        }
      }
    } catch (_) {}
  },

  async toggleAIMode() {
    const current = this.health?.ai_mode || 'mock';
    const target = current === 'live' ? 'mock' : 'live';
    if (target === 'live' && !this.health?.live_ready) {
      showToast('Live mode needs GEMINI_API_KEY or ANTHROPIC_API_KEY in your .env file.', 'danger');
      return;
    }
    try {
      await API.setAiMode(target);
      await this.loadHealth();
      showToast(`AI mode switched to ${target.toUpperCase()}.`, 'success');
      await this.refresh();
    } catch (e) {
      showToast(e.message || `Could not switch to ${target} mode.`, 'danger');
    }
  },

  setupImageOrder() {
    const input = document.getElementById('image-order-input');
    const zone = document.getElementById('image-dropzone');
    if (input) input.addEventListener('change', () => this.setPendingImage(input.files && input.files[0]));
    if (zone) {
      ['dragenter', 'dragover'].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.add('dragover'); }));
      ['dragleave', 'drop'].forEach(ev => zone.addEventListener(ev, e => { e.preventDefault(); zone.classList.remove('dragover'); }));
      zone.addEventListener('drop', e => this.setPendingImage(e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files[0]));
    }
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape') this.closeImageOrder();
    });
  },

  validateImage(file) {
    if (!file) return false;
    if (!this.ALLOWED_IMAGES.includes(file.type)) {
      showToast('Please choose a PNG, JPEG or WEBP image.', 'danger');
      return false;
    }
    if (file.size > this.MAX_IMAGE_BYTES) {
      showToast('That image is over 5 MB - please choose a smaller one.', 'danger');
      return false;
    }
    return true;
  },

  async openImageOrder() {
    await this.loadHealth();
    const note = document.getElementById('image-order-mode-note');
    if (note) {
      const live = this.health && this.health.ai_mode === 'live' && this.health.live_key_present;
      note.textContent = live
        ? 'Live AI will read the dishes, quantities, address and instructions. Always review what it extracted before confirming.'
        : 'Mock mode cannot read photos: the image will be attached to a new order and you will need to type the details. Switch to live AI mode (AI_MODE=live + an API key) for automatic reading.';
    }
    const lang = document.getElementById('image-order-lang');
    if (lang && window.VoiceStudio && VoiceStudio.activeLang) lang.value = VoiceStudio.activeLang === 'te' ? 'en' : VoiceStudio.activeLang;
    const modal = document.getElementById('modal-image-order');
    if (modal) modal.classList.add('open');
  },

  setPendingImage(file) {
    if (!this.validateImage(file)) return;
    if (this.pendingImageUrl) URL.revokeObjectURL(this.pendingImageUrl);
    this.pendingImage = file;
    this.pendingImageUrl = URL.createObjectURL(file);
    const img = document.getElementById('image-order-preview');
    const hint = document.getElementById('image-dropzone-hint');
    if (img) { img.src = this.pendingImageUrl; img.style.display = 'block'; }
    if (hint) hint.style.display = 'none';
    const btn = document.getElementById('btn-image-submit');
    if (btn) btn.disabled = false;
  },

  closeImageOrder() {
    const modal = document.getElementById('modal-image-order');
    if (modal) modal.classList.remove('open');
    if (this.pendingImageUrl) URL.revokeObjectURL(this.pendingImageUrl);
    this.pendingImage = null;
    this.pendingImageUrl = null;
    const input = document.getElementById('image-order-input'); if (input) input.value = '';
    const img = document.getElementById('image-order-preview'); if (img) { img.removeAttribute('src'); img.style.display = 'none'; }
    const hint = document.getElementById('image-dropzone-hint'); if (hint) hint.style.display = '';
    const btn = document.getElementById('btn-image-submit'); if (btn) { btn.disabled = true; btn.textContent = 'Create Order'; }
  },

  async submitImageOrder() {
    if (!this.pendingImage) return;
    const btn = document.getElementById('btn-image-submit');
    if (btn) { btn.disabled = true; btn.textContent = 'Reading image…'; }
    const name = (document.getElementById('image-order-name') || {}).value || '';
    const lang = (document.getElementById('image-order-lang') || {}).value || 'en';
    this.busy = true;
    let res = null;
    try {
      res = await API.createOrderFromImage(this.pendingImage, name.trim(), lang);
    } catch (_) {
      if (btn) { btn.disabled = false; btn.textContent = 'Create Order'; }   // API layer already toasted; let them retry
      this.busy = false;
      return;
    }
    this.busy = false;
    this.closeImageOrder();
    const nameInput = document.getElementById('image-order-name'); if (nameInput) nameInput.value = '';
    this.currentOrderId = res.order_id;
    this.lastSig = null;
    this.switchTab('tower');
    await this.loadAllData();
    await this.selectOrder(res.order_id);
    if (res.image_read) showToast(`Order ${res.order_id} created from the image - please review the details.`, 'success', 5000);
    else showToast(`Order ${res.order_id} created, but the image could not be read (${res.image_note}). Type the details in the chat.`, 'warning', 9000);
  },

  async handleChatImage(input) {
    const file = input && input.files && input.files[0];
    if (input) input.value = '';
    if (!file || !this.currentOrderId || !this.validateImage(file)) return;
    const role = (document.getElementById('chat-sender-role') || {}).value || 'customer';
    showToast('Uploading image…', 'info');
    const res = await this.act(() => API.uploadFile(this.currentOrderId, role, file));
    if (!res) return;
    const types = (res.events || []).slice(-6).map(e => e.type);
    if (types.includes('IMAGE_PARSED')) showToast('Image read - order details updated.', 'success');
    else if (types.includes('IMAGE_NOT_READ')) showToast('Image attached, but it could not be read automatically. Type the details in the chat.', 'warning', 8000);
  },

  async createNewBlankOrder() {
    try {
      showToast('Creating new order thread...', 'info');
      const lang = (window.VoiceStudio && VoiceStudio.activeLang) ? VoiceStudio.activeLang : 'en';
      const created = await API.createOrder('Customer', lang);
      this.currentOrderId = created.order_id;
      showToast(`Created order thread ${created.order_id}!`, 'success');
      this.lastSig = null;
      await this.loadAllData();
      await this.selectOrder(created.order_id);
    } catch (err) {
      console.error('Failed to create order:', err);
    }
  },

  // ==========================================
  // System Actions: Reset, Seed, Export
  // ==========================================
  async confirmResetSystem() {
    if (!confirm('Are you sure you want to reset the entire system and clean all orders, messages, and events? This will start from a completely clean slate.')) {
      return;
    }

    try {
      await API.resetSystem();
      showToast('System completely cleared! Starting on a fresh slate.', 'success');
      this.currentOrderId = null;
      this.lastSig = null;
      await this.loadAllData();
    } catch (err) {}
  },

  async handleSeedDemo() {
    try {
      showToast('Seeding enterprise demonstration orders across Telugu, Hindi, and English...', 'info');
      await API.seedDemo();
      showToast('Demo orders seeded successfully!', 'success');
      this.currentOrderId = 'ORD-901';
      this.lastSig = null;
      await this.loadAllData();
    } catch (err) {}
  },

  async handleExport() {
    try {
      const data = await API.exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `culinaryos_audit_export_${Date.now()}.json`;
      a.click();
      URL.revokeObjectURL(url);
      showToast('Audit JSON exported successfully!', 'success');
    } catch (err) {}
  },

  // ==========================================
  // Interactive Demonstration Scenarios
  // ==========================================
  async runScenario(type) {
    showToast(`Executing Scenario: ${type}...`, 'info');
    this.busy = true;
    const step = async (fn) => { try { return await fn(); } catch (_) { return null; } };
    try {
      let lang = 'en';
      let name = 'Customer';
      if (type === 'telugu_peanut') { lang = 'te'; name = 'Ananya Rao'; }
      else if (type === 'hindi_voice') { lang = 'hi'; name = 'Vikram Sharma'; }

      const created = await API.createOrder(name, lang);
      const id = created.order_id;
      this.currentOrderId = id;
      const say = (t, l = 'en') => API.sendMessage(id, 'customer', t, l);

      if (type === 'telugu_peanut') {
        await say('నమస్కారం, రేపు 3 భోజనాలు కావాలి, ఒకదాంట్లో వేరుశెనగలు అస్సలు ఉండకూడదు. 42 రెసిడెన్సీ రోడ్డుకి పంపండి.', 'te');
        showToast('Telugu Peanut Allergy order processed autonomously!', 'success');
      } else if (type === 'quantity_waste') {
        await say('I need 4 meals delivered to 10 Park Street.');
        await API.advanceStatus(id, 'CONFIRMED');
        await say('Please reduce the order to 2 meals.');
        showToast('Quantity reduced from 4 to 2: Food Waste Alert generated!', 'warning');
      } else if (type === 'address_conflict') {
        await say('2 meals tomorrow. Deliver to 12 Brigade Rd or 88 MG Road.');
        showToast('Address Conflict detected: intervention required!', 'danger');
      } else if (type === 'allergy_lock') {
        await say('3 meals with strict shellfish allergy. Deliver to 55 Beach Road.');
        await API.advanceStatus(id, 'CONFIRMED');
        await API.advanceStatus(id, 'PREPARING');
        await API.advanceStatus(id, 'READY_FOR_PACKAGING');
        await step(() => API.advanceStatus(id, 'PACKAGING')); // expected to be blocked by the safety lock
        showToast('Safety Lock: advancing to PACKAGING is blocked until the chef signs off the allergy!', 'warning');
      } else if (type === 'hindi_voice') {
        await say('नमस्ते, कल दोपहर 4 थाली चाहिए, 12:30 के बाद 12 मालवीय नगर पर डिलीवर करवा दें। बच्चों के लिए मिर्च कम रखिएगा।', 'hi');
        showToast('Hindi order with mild spice preference processed!', 'success');
      }
    } catch (err) {
      console.error('Scenario execution error:', err);
    } finally {
      this.busy = false;
      this.lastSig = null;
      await this.loadAllData();
      if (this.currentOrderId) await this.selectOrder(this.currentOrderId);
    }
  }
};

window.App = App;
document.addEventListener('DOMContentLoaded', () => App.init());
