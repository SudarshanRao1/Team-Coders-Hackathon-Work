/**
 * CulinaryOS - Centralized API & Networking Module
 */

const API = {
  async req(url, options = {}) {
    try {
      const res = await fetch(url, options);
      if (!res.ok) {
        let errMessage = `Error ${res.status}`;
        try {
          const errData = await res.json();
          if (errData.detail) errMessage = typeof errData.detail === 'string' ? errData.detail : JSON.stringify(errData.detail);
        } catch (_) {}
        throw new Error(errMessage);
      }
      return await res.json();
    } catch (err) {
      console.error(`API Error on ${url}:`, err);
      showToast(err.message || 'Network request failed', 'danger');
      throw err;
    }
  },

  async createOrder(name = 'Customer', lang = 'en') {
    return await this.req('/api/orders', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, lang })
    });
  },

  async getHealth() {
    const res = await fetch('/api/health');
    return res.ok ? await res.json() : null;
  },

  async getOrders() {
    return await this.req('/api/orders');
  },

  async getOrder(oid) {
    return await this.req(`/api/orders/${oid}`);
  },

  async getAnalytics() {
    return await this.req('/api/analytics');
  },

  async getMessages(oid) {
    return await this.req(`/api/orders/${oid}/messages`);
  },

  async getEvents(oid) {
    return await this.req(`/api/orders/${oid}/events`);
  },

  async sendMessage(oid, sender, text, lang = null) {
    const payload = { sender, text };
    if (lang) payload.lang = lang;
    return await this.req(`/api/orders/${oid}/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
  },

  async updateQuantity(oid, quantity) {
    return await this.req(`/api/orders/${oid}/quantity`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'set', quantity })
    });
  },

  async acknowledgeAllergy(oid) {
    return await this.req(`/api/orders/${oid}/ack`, { method: 'POST' });
  },

  async resolveConflict(oid, address) {
    return await this.req(`/api/orders/${oid}/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ address })
    });
  },

  async advanceStatus(oid, status) {
    return await this.req(`/api/orders/${oid}/advance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(status ? { status } : {})
    });
  },

  async approveModification(oid) {
    return await this.req(`/api/orders/${oid}/approve`, { method: 'POST' });
  },

  async cancelOrder(oid) {
    return await this.req(`/api/orders/${oid}/cancel`, { method: 'POST' });
  },

  // Create a brand-new order from a photo of a handwritten / printed order.
  async createOrderFromImage(file, name = '', lang = 'en') {
    const formData = new FormData();
    formData.append('file', file);
    if (name) formData.append('name', name);
    if (lang) formData.append('lang', lang);
    return await this.postForm('/api/orders/from-image', formData, 'Image upload failed');
  },

  async postForm(url, formData, fallbackMsg) {
    try {
      const res = await fetch(url, { method: 'POST', body: formData });
      if (!res.ok) {
        let msg = `${fallbackMsg} (${res.status})`;
        try { const err = await res.json(); if (err.detail) msg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail); } catch (_) {}
        throw new Error(msg);
      }
      return await res.json();
    } catch (err) {
      showToast(err.message || fallbackMsg, 'danger');
      throw err;
    }
  },

  async uploadFile(oid, sender, file, notes = '', lang = '', opts = {}) {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('sender', sender);
    if (notes) formData.append('notes', notes);
    if (lang) formData.append('lang', lang);
    if (opts.useSample === false) formData.append('use_sample', 'false');

    try {
      const res = await fetch(`/api/orders/${oid}/upload`, { method: 'POST', body: formData });
      if (!res.ok) {
        let msg = `Upload failed (${res.status})`;
        try { const err = await res.json(); if (err.detail) msg = typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail); } catch (_) {}
        throw new Error(msg);
      }
      return await res.json();
    } catch (err) {
      showToast(err.message || 'Upload failed', 'danger');
      throw err;
    }
  },

  async resetSystem() {
    return await this.req('/api/reset', { method: 'POST' });
  },

  async seedDemo() {
    return await this.req('/api/seed', { method: 'POST' });
  },

  async exportData() {
    return await this.req('/api/export');
  },

  async setAiMode(mode) {
    return await this.req('/api/settings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ mode })
    });
  }
};

/**
 * Toast Notification Utility
 */
function esc(v) {
  return String(v ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
}

function showToast(message, type = 'info', duration = 3600) {
  let container = document.getElementById('toast-container');
  if (!container) {
    container = document.createElement('div');
    container.id = 'toast-container';
    document.body.appendChild(container);
  }

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  const icon = type === 'success' ? '✓' :
               type === 'danger' ? '⚠️' :
               type === 'warning' ? '⚡' : 'ℹ️';

  toast.innerHTML = `<span style="font-size:1.1rem">${icon}</span> <span>${esc(message)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.transition = 'all 0.3s ease';
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(40px)';
    setTimeout(() => toast.remove(), 320);
  }, duration);
}

window.API = API;
window.showToast = showToast;
window.esc = esc;
