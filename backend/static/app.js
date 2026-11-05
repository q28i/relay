/**
 * WhatsApp Messenger - Simple, Production-Grade Single Page Application
 * Built on the clean, accessible Tabler dashboard foundation (MIT License).
 * Provides focused local messaging: Dashboard, Contacts, Messages, Campaigns, Activity, Settings.
 */

class WhatsAppDashboardApp {
  constructor() {
    this.currentTab = 'templates';
    this.activeTemplateId = null;
    this.activeTemplate = null;
    this.templateSelectedContactIds = new Set();
    this.templateSelectedMediaIds = new Set();
    this.selectedMediaLibraryIds = new Set();
    this.mediaLibraryFilter = 'all';
    this.cachedTemplates = [];
    this.activeAssignments = [];
    this.viewingSuppression = false;
    this.activityFilter = 'ALL';
    this.selectedDraftId = null;
    this.selectedPersona = 'standard';

    this.ws = null;
    this.wsReconnectTimer = null;
    this.activeJob = null;
    this.searchTimer = null;
    this.previewTimer = null;

    this.selectedContactIds = new Set();
    this.allContactItems = [];
    this.availableGroups = [];
    this.selectedMediaAssetId = null;
    this.selectedMediaAsset = null;
    this.editingContactInitialConsent = null;
    this.lastCheckedContactIndex = null;
    this.currentMessagesSubView = 'sets';

    this.textSets = [];
    this.mediaSets = [];
    this.activeTextSetId = null;
    this.activeMediaSetId = null;
    this.activeTextSet = null;
    this.activeMediaSet = null;
    this.selectedTextSetItemIds = new Set();
    this.selectedMediaSetItemIds = new Set();
    this.cachedVariablesInfo = null;
    this.previewingTextItem = null;
    this.campaignContentSource = 'sets';

    this.theme = localStorage.getItem('theme') || 'light';
    this.privacyMode = localStorage.getItem('privacy_mode') === 'true';
    this.installedBrowsers = [];
    this.connectionState = null;
    this.connPollTimer = null;
    this.activeJobPollTimer = null;
    this.isExecutingConnAction = false;

    this.isTemplateDirty = false;
    this.recipientActivityFilter = 'ALL';
    this.recipientActivitySearch = '';
    this.activeDrawerItemId = null;
    this.renamingMediaId = null;

    this.initTheme();
    this.initNavigation();
    this.initModalListeners();
    this.initKeyboardShortcuts();
    this.initDraftRecovery();
    this.initCampaignDraftRecovery();
    this.initPrivacyMode();
    this.initDropzones();
    this.initWebSocket();
    this.initRadioCardFocus();
    this.loadInitialData();
    this.startConnectionPolling();
    this.startActiveJobPolling();
  }

  initKeyboardShortcuts() {
    window.addEventListener('keydown', (e) => {
      const confirmModal = document.getElementById('modal-confirm-dialog');
      const isConfirmActive = confirmModal && confirmModal.classList.contains('active');

      if (e.key === 'Escape') {
        if (isConfirmActive) {
          e.preventDefault();
          this.closeConfirmDialog(false);
          return;
        }
      }

      if (e.key === 'Enter' && isConfirmActive) {
        if (document.activeElement && document.activeElement.id === 'btn-confirm-cancel') {
          return;
        }
        e.preventDefault();
        this.closeConfirmDialog(true);
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 's') {
        const editorView = document.getElementById('template-editor-view');
        if (this.activeTemplateId && editorView && editorView.style.display !== 'none') {
          e.preventDefault();
          this.saveActiveTemplate();
        }
      }
    });
  }

  initRadioCardFocus() {
    document.addEventListener('focusin', (e) => {
      if (e.target && e.target.classList && e.target.classList.contains('radio-card-input')) {
        const parentCard = e.target.closest('.radio-card');
        if (parentCard) parentCard.classList.add('has-focus');
      }
    });
    document.addEventListener('focusout', (e) => {
      if (e.target && e.target.classList && e.target.classList.contains('radio-card-input')) {
        const parentCard = e.target.closest('.radio-card');
        if (parentCard) parentCard.classList.remove('has-focus');
      }
    });
    document.addEventListener('keydown', (e) => {
      if ((e.key === ' ' || e.key === 'Enter') && e.target && e.target.classList && e.target.classList.contains('radio-card')) {
        e.preventDefault();
        e.target.click();
      }
    });
  }

  startConnectionPolling() {
    if (this.connPollTimer) clearInterval(this.connPollTimer);
    this.connPollTimer = setInterval(() => {
      if (!this.isExecutingConnAction) {
        this.loadBrowserConnection();
      }
    }, 2000);
  }

  startActiveJobPolling() {
    if (this.activeJobPollTimer) clearInterval(this.activeJobPollTimer);
    this.activeJobPollTimer = setInterval(() => {
      this.refreshActiveJob();
    }, 2000);
  }

  initPrivacyMode() {
    const toggle = document.getElementById('privacy-mode-toggle');
    if (toggle) toggle.checked = this.privacyMode;
  }

  togglePrivacyMode() {
    const toggle = document.getElementById('privacy-mode-toggle');
    this.privacyMode = toggle ? toggle.checked : false;
    localStorage.setItem('privacy_mode', this.privacyMode ? 'true' : 'false');
    if (this.currentTab === 'activity') {
      this.loadActivityData();
    }
  }

  formatPhone(phone) {
    if (!phone) return '';
    const clean = String(phone).trim();
    if (!this.privacyMode) return clean;
    const digits = clean.replace(/\D/g, '');
    if (digits.length <= 4) return '••••';
    const head = digits.slice(0, Math.min(3, digits.length - 4));
    const tail = digits.slice(-4);
    return `${head}••••${tail}`;
  }

  escapeHtml(str) {
    if (str === null || str === undefined) return '';
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  initDraftRecovery() {
    const titleInput = document.getElementById('msg-title-input');
    const contentInput = document.getElementById('msg-content-input');
    const banner = document.getElementById('draft-recovered-banner');

    if (titleInput && contentInput) {
      // Restore draft if inputs are empty
      const savedTitle = localStorage.getItem('wa_draft_title') || '';
      const savedContent = localStorage.getItem('wa_draft_content') || '';
      if ((savedTitle || savedContent) && !titleInput.value && !contentInput.value) {
        titleInput.value = savedTitle;
        contentInput.value = savedContent;
        if (banner) banner.style.display = 'flex';
        this.onMessageEditorChange();
      }

      // Persist draft on user typing
      const saveToLocal = () => {
        const editId = document.getElementById('msg-edit-id')?.value;
        if (!editId) {
          localStorage.setItem('wa_draft_title', titleInput.value);
          localStorage.setItem('wa_draft_content', contentInput.value);
        }
      };
      titleInput.addEventListener('input', saveToLocal);
      contentInput.addEventListener('input', saveToLocal);
    }
  }

  clearDraftStorage() {
    localStorage.removeItem('wa_draft_title');
    localStorage.removeItem('wa_draft_content');
    const banner = document.getElementById('draft-recovered-banner');
    if (banner) banner.style.display = 'none';
    this.resetMessageEditor();
    this.showToast('Unsaved draft discarded', 'info');
  }

  initCampaignDraftRecovery() {
    const nameInput = document.getElementById('camp-name-input');
    const banner = document.getElementById('camp-draft-recovered-banner');
    if (nameInput) {
      const savedName = localStorage.getItem('wa_camp_draft_name') || '';
      if (savedName && !nameInput.value) {
        nameInput.value = savedName;
        if (banner) banner.style.display = 'flex';
      }
      nameInput.addEventListener('input', () => {
        localStorage.setItem('wa_camp_draft_name', nameInput.value);
      });
    }
  }

  onCampaignEditorChange() {
    const nameInput = document.getElementById('camp-name-input');
    if (nameInput) {
      localStorage.setItem('wa_camp_draft_name', nameInput.value);
    }
    this.updateCampaignReview();
  }

  clearCampaignDraftStorage() {
    localStorage.removeItem('wa_camp_draft_name');
    const nameInput = document.getElementById('camp-name-input');
    if (nameInput) nameInput.value = '';
    const banner = document.getElementById('camp-draft-recovered-banner');
    if (banner) banner.style.display = 'none';
    this.updateCampaignReview();
    this.showToast('Campaign draft discarded', 'info');
  }

  // --- Modal Keyboard & Backdrop Listeners ---
  initModalListeners() {
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.closeAllModals();
    });
    document.querySelectorAll('.modal-backdrop').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) modal.classList.remove('active');
      });
    });
  }

  closeAllModals() {
    document.querySelectorAll('.modal-backdrop.active').forEach(m => m.classList.remove('active'));
  }

  // --- Theme Management (System, Light, Void) ---
  initTheme() {
    this.theme = localStorage.getItem('theme') || 'system';
    this.applyTheme(this.theme, false);

    // Synchronize with OS system preference changes if 'system' is chosen
    if (window.matchMedia) {
      window.matchMedia('(prefers-color-scheme: dark)').addEventListener('change', () => {
        if (this.theme === 'system') {
          this.applyTheme('system', false);
        }
      });
    }
  }

  setTheme(themeName) {
    if (!['system', 'light', 'void'].includes(themeName)) return;
    this.theme = themeName;
    localStorage.setItem('theme', themeName);
    this.applyTheme(themeName, true);
  }

  applyTheme(themeName, notify = false) {
    let effective = themeName;
    if (themeName === 'system') {
      const prefersDark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
      effective = prefersDark ? 'void' : 'light';
    }

    // Set attribute on html element
    document.documentElement.setAttribute('data-theme', effective);

    // Update settings cards & badge
    const badge = document.getElementById('current-theme-badge');
    if (badge) {
      badge.textContent = themeName.charAt(0).toUpperCase() + themeName.slice(1);
      badge.className = effective === 'void' ? 'badge badge-primary' : 'badge badge-neutral';
    }

    ['system', 'light', 'void'].forEach(t => {
      const card = document.getElementById(`theme-card-${t}`);
      const radio = document.getElementById(`radio-theme-${t}`);
      const isSelected = (t === themeName);
      if (card) {
        card.classList.toggle('active', isSelected);
        card.classList.toggle('selected', isSelected);
      }
      if (radio) {
        radio.checked = isSelected;
      }
    });

    if (notify) {
      const label = themeName === 'void' ? 'Void' : (themeName === 'light' ? 'Light' : 'System');
      this.showToast(`${label} theme applied.`, 'info');
    }
  }

  // --- Navigation & Routing ---
  initNavigation() {
    const navButtons = document.querySelectorAll('.app-sidebar .nav-link');
    navButtons.forEach(btn => {
      btn.addEventListener('click', () => {
        const tab = btn.getAttribute('data-tab');
        if (tab) this.navigate(tab);
      });
    });
  }

  navigate(tabName) {
    if (tabName === 'dashboard' || tabName === 'messages') tabName = 'templates';
    if (tabName === 'activity') tabName = 'campaigns';
    this.currentTab = tabName;
    document.querySelectorAll('.app-sidebar .nav-link').forEach(btn => {
      btn.classList.toggle('active', btn.getAttribute('data-tab') === tabName);
    });
    document.querySelectorAll('.page-container').forEach(el => {
      el.classList.toggle('active', el.id === `tab-${tabName}`);
    });

    const titles = {
      templates: 'Templates',
      contacts: 'Contacts',
      media: 'Media Library',
      campaigns: 'Campaigns',
      settings: 'Settings'
    };
    const heading = document.getElementById('page-heading');
    if (heading) heading.textContent = titles[tabName] || 'Templates';

    // Lazy load tab contents
    if (tabName === 'templates') this.loadTemplates();
    if (tabName === 'contacts') this.loadContacts();
    if (tabName === 'media') this.loadMediaLibrary();
    if (tabName === 'campaigns') this.loadCampaignsData();
    if (tabName === 'settings') this.loadSettingsData();
  }

  // --- Toast Notifications with Deduplication ---
  showToast(message, type = 'info') {
    if (!message) return;
    const cleanMsg = String(message).trim();
    const now = Date.now();
    this.toastHistory = this.toastHistory || {};
    const toastKey = `${type}:${cleanMsg}`;

    // Deduplicate identical toasts within 2500ms
    if (this.toastHistory[toastKey] && (now - this.toastHistory[toastKey] < 2500)) {
      return;
    }
    this.toastHistory[toastKey] = now;

    const shelf = document.getElementById('toast-shelf');
    if (!shelf) return;

    // Suppress if an identical message is currently active in the shelf
    for (const existing of shelf.children) {
      if (existing.textContent === cleanMsg) {
        return;
      }
    }

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.textContent = cleanMsg;
    shelf.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.2s ease';
      setTimeout(() => toast.remove(), 250);
    }, 3200);
  }

  showToastWithAction(message, actionLabel, onAction, type = 'info', duration = 5500) {
    if (!message) return;
    const shelf = document.getElementById('toast-shelf');
    if (!shelf) return;

    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.style.display = 'flex';
    toast.style.alignItems = 'center';
    toast.style.justifyContent = 'space-between';
    toast.style.gap = '0.75rem';

    const span = document.createElement('span');
    span.textContent = message;
    toast.appendChild(span);

    if (actionLabel && typeof onAction === 'function') {
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'btn btn-subtle btn-xs';
      btn.textContent = actionLabel;
      btn.style.fontWeight = '700';
      btn.style.textDecoration = 'underline';
      btn.style.cursor = 'pointer';
      btn.onclick = (e) => {
        e.stopPropagation();
        try { onAction(); } catch (err) { console.error(err); }
        toast.remove();
      };
      toast.appendChild(btn);
    }

    shelf.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transition = 'opacity 0.2s ease';
      setTimeout(() => toast.remove(), 250);
    }, duration);
  }

  confirmDialog({ title, message, details, confirmText = 'Confirm', cancelText = 'Cancel', isDestructive = false }) {
    return new Promise(resolve => {
      this._confirmResolver = resolve;
      const titleEl = document.getElementById('confirm-dialog-title');
      const msgEl = document.getElementById('confirm-dialog-message');
      const detEl = document.getElementById('confirm-dialog-details');
      const okBtn = document.getElementById('btn-confirm-proceed');
      const cancelBtn = document.getElementById('btn-confirm-cancel');

      if (titleEl) titleEl.textContent = title || 'Confirm Action';
      if (msgEl) msgEl.textContent = message || 'Are you sure you want to proceed?';
      if (detEl) {
        if (details) {
          detEl.textContent = details;
          detEl.style.display = 'block';
        } else {
          detEl.style.display = 'none';
        }
      }
      if (okBtn) {
        okBtn.textContent = confirmText;
        okBtn.className = isDestructive ? 'btn btn-danger btn-sm' : 'btn btn-primary btn-sm';
      }
      if (cancelBtn) cancelBtn.textContent = cancelText;

      this.openModal('modal-confirm-dialog');
      setTimeout(() => {
        if (cancelBtn) cancelBtn.focus();
      }, 50);
    });
  }

  closeConfirmDialog(confirmed) {
    this.closeModal('modal-confirm-dialog');
    if (this._confirmResolver) {
      const resolve = this._confirmResolver;
      this._confirmResolver = null;
      resolve(Boolean(confirmed));
    }
  }

  formatSafeTime(val) {
    if (!val) return '—';
    if (typeof val === 'string' && /^\d{2}:\d{2}(:\d{2})?$/.test(val.trim())) {
      return val.trim();
    }
    try {
      const d = new Date(val);
      if (!isNaN(d.getTime())) {
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
      }
    } catch (e) {}
    return '—';
  }

  // --- WebSocket Live Updates ---
  initWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    try {
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        const el = document.getElementById('ws-indicator');
        if (el) el.textContent = 'Connected';
        clearInterval(this.wsReconnectTimer);
        this.wsReconnectTimer = null;
      };

      this.ws.onclose = () => {
        const el = document.getElementById('ws-indicator');
        if (el) el.textContent = 'Disconnected';
        if (!this.wsReconnectTimer) {
          this.wsReconnectTimer = setInterval(() => this.initWebSocket(), 3500);
        }
      };

      this.ws.onerror = (err) => {
        console.debug('WS error:', err);
      };

      this.ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          this.handleWsEvent(msg);
        } catch (e) {}
      };
    } catch (e) {}
  }

  handleWsEvent(msg) {
    if (msg.type === 'connection_established') {
      if (msg.active_job) this.updateActiveJobBanner(msg.active_job);
    } else if (msg.type === 'job_started') {
      this.updateActiveJobBanner(msg.job);
      this.showToast(`Campaign '${msg.job.campaign_name}' started`, 'info');
      this.loadDashboardData();
    } else if (msg.type === 'job_progress') {
      this.updateJobProgress(msg);
    } else if (msg.type === 'job_finished') {
      this.showToast(`Campaign '${this.activeJob ? this.activeJob.campaign_name : ''}' finished`, 'success');
      this.updateActiveJobBanner(null);
      this.loadDashboardData();
      if (this.currentTab === 'activity') this.loadActivityData();
    } else if (msg.type === 'job_paused' || msg.type === 'job_resumed' || msg.type === 'job_cancelled') {
      this.refreshActiveJob();
    }
  }

  // --- API Helper ---
  async api(endpoint, options = {}) {
    const isSilent = options.silent === true;
    try {
      const res = await fetch(endpoint, options);
      if (!res.ok) {
        const errData = await res.json().catch(() => ({ detail: res.statusText }));
        const message = errData.message || errData.detail || 'Request failed';
        const error = new Error(message);
        error.code = errData.code;
        error.action = errData.action;
        error.status = res.status;
        error.detail = errData.detail;
        throw error;
      }
      return await res.json();
    } catch (e) {
      if (!isSilent) {
        let displayMsg = e.action ? `${e.message} ${e.action}` : (e.message || 'Request failed');
        if (e.name === 'TypeError' && (e.message.includes('fetch') || e.message.includes('NetworkError') || e.message.includes('Failed to fetch'))) {
          displayMsg = 'Cannot reach Relay server at http://127.0.0.1:8000. Please check if the web server is running.';
        }
        this.showToast(displayMsg, 'error');
      }
      throw e;
    }
  }

  // --- Initial Data Load ---
  async loadInitialData() {
    await this.loadBrowserConnection();
    await this.loadTemplates();
  }

  // ==========================================================================
  // SECTION 1: DASHBOARD
  // ==========================================================================
  async loadDashboardData() {
    try {
      // 1. Fetch KPIs
      const kpis = await this.api('/api/logs/kpis', { silent: true });
      const totalContacts = kpis.total_contacts || 0;
      const totalTemplates = kpis.total_templates || 0;
      const totalJobs = kpis.total_jobs || 0;

      // 2. Active Job Banner
      await this.refreshActiveJob();

      // 3. Readiness Hero Summary
      const headingEl = document.getElementById('dash-ready-heading');
      const subEl = document.getElementById('dash-ready-sub');
      const badgeEl = document.getElementById('dash-conn-badge');
      const heroBtn = document.getElementById('dash-hero-action-btn');
      const conn = await this.loadBrowserConnection();
      const isSigned = conn.status === 'Signed in' || conn.state === 'connected';

      if (badgeEl) {
        badgeEl.textContent = conn.status || 'Not checked';
        badgeEl.className = `badge ${isSigned ? 'badge-success' : conn.status === 'Needs QR sign-in' ? 'badge-warning' : 'badge-neutral'}`;
      }

      if (!isSigned) {
        if (headingEl) headingEl.textContent = 'Browser Connection Needed';
        if (subEl) {
          subEl.textContent = conn.status === 'Needs QR sign-in'
            ? 'Browser opened. Please scan the QR code to finish linking your session.'
            : 'Select and link an existing browser profile with WhatsApp Web to begin.';
        }
        if (heroBtn) {
          heroBtn.textContent = 'Connect Browser';
          heroBtn.onclick = () => this.navigate('settings');
        }
      } else if (totalContacts === 0) {
        if (headingEl) headingEl.textContent = 'Audience Needed';
        if (subEl) subEl.textContent = 'Import a contact spreadsheet or paste numbers to prepare your first broadcast.';
        if (heroBtn) {
          heroBtn.textContent = 'Add Contacts';
          heroBtn.onclick = () => this.navigate('contacts');
        }
      } else if (totalTemplates === 0) {
        if (headingEl) headingEl.textContent = 'Message Draft Needed';
        if (subEl) subEl.textContent = 'Compose your first message draft with personalizing variables.';
        if (heroBtn) {
          heroBtn.textContent = 'Create Message';
          heroBtn.onclick = () => this.navigate('messages');
        }
      } else {
        if (headingEl) headingEl.textContent = 'Ready to Dispatch';
        if (subEl) subEl.textContent = `Connected via ${conn.profile_name || 'browser'}. You have ${totalContacts} contact${totalContacts === 1 ? '' : 's'} available across ${kpis.total_groups || 1} groups.`;
        if (heroBtn) {
          heroBtn.textContent = 'Start Campaign';
          heroBtn.onclick = () => this.navigate('campaigns');
        }
      }

      // Update 3-step Get-Started Panel (collapses when complete)
      this.updateFirstRunGuide(kpis, conn);

      // 4. Update Stats Numbers
      const statContacts = document.getElementById('dash-stat-contacts');
      const statMessages = document.getElementById('dash-stat-messages');
      const statCampaigns = document.getElementById('dash-stat-campaigns');
      if (statContacts) statContacts.textContent = totalContacts;
      if (statMessages) statMessages.textContent = totalTemplates;
      if (statCampaigns) statCampaigns.textContent = totalJobs;

      // 5. Update Connection Card in Dashboard
      const pName = document.getElementById('dash-browser-profile-name');
      const bDetails = document.getElementById('dash-browser-details');
      const sBadge = document.getElementById('dash-conn-status-badge');
      const sSummary = document.getElementById('dash-conn-summary-text');

      if (pName) pName.textContent = conn.profile_name || 'Dedicated Session';
      if (bDetails) bDetails.textContent = `${(conn.browser || 'chrome').toUpperCase()} · WhatsApp Web`;
      if (sBadge) {
        sBadge.textContent = conn.status || 'Not checked';
        sBadge.className = `badge ${isSigned ? 'badge-success' : 'badge-neutral'}`;
      }
      if (sSummary) {
        sSummary.textContent = isSigned
          ? 'Session linked and ready. Outbound messages will dispatch through this profile.'
          : (conn.message || 'Browser profile is not currently verified.');
      }

      // 6. Recent Campaigns List (Compact within page flow)
      const jobs = await this.api('/api/jobs?limit=4', { silent: true });
      const recentBody = document.getElementById('dash-recent-body');
      if (recentBody) {
        if (!jobs || jobs.length === 0) {
          recentBody.innerHTML = `
            <div style="padding: 1.25rem 1rem; color: var(--text-muted); font-size: 0.8125rem; text-align: center;">
              No campaigns sent yet. Recent campaign dispatches and progress will display here.
            </div>
          `;
        } else {
          recentBody.innerHTML = `
            <div class="activity-feed-list">
              ${jobs.map(j => {
                const statusClass = j.status === 'COMPLETED' ? 'badge-success' : j.status === 'FAILED' ? 'badge-danger' : 'badge-warning';
                return `
                  <div class="activity-feed-item">
                    <div class="activity-feed-main">
                      <span class="badge ${statusClass}">${j.status}</span>
                      <div>
                        <div class="activity-feed-desc">${j.campaign_name}</div>
                        <div class="activity-feed-time">${j.sent_count} / ${j.total_count} sent · ${(j.started_at || '').slice(0, 16).replace('T', ' ')}</div>
                      </div>
                    </div>
                    <button class="btn btn-subtle btn-sm" onclick="app.viewCampaignDetail('${j.id}')">View</button>
                  </div>
                `;
              }).join('')}
            </div>
          `;
        }
      }
    } catch (e) {}
  }

  async refreshActiveJob() {
    try {
      const activeRes = await this.api('/api/jobs/active', { silent: true });
      this.updateActiveJobBanner(activeRes && activeRes.active_job ? activeRes.active_job : null);
    } catch (e) {}
  }

  updateActiveJobBanner(job) {
    this.activeJob = job;
    const banner = document.getElementById('active-job-banner');
    const liveCard = document.getElementById('act-live-card');

    if (!job || job.status === 'COMPLETED' || job.status === 'FAILED' || job.status === 'CANCELLED') {
      if (banner) banner.style.display = 'none';
      if (liveCard) liveCard.style.display = 'none';
      return;
    }

    // 1. Top Bar Global Banner
    if (banner) {
      banner.style.display = 'block';
      const nameEl = document.getElementById('banner-campaign-name');
      if (nameEl) nameEl.textContent = job.campaign_name;
      const statusEl = document.getElementById('banner-job-status');
      if (statusEl) statusEl.textContent = job.status.replace(/_/g, ' ');
      const countsEl = document.getElementById('banner-progress-counts');
      if (countsEl) countsEl.textContent = `${job.sent_count} / ${job.total_count} sent`;

      const pauseBtn = document.getElementById('btn-banner-pause');
      if (pauseBtn) {
        pauseBtn.textContent = job.status === 'PAUSED' ? 'Resume' : 'Pause';
      }

      const pct = job.total_count > 0 ? (job.sent_count / job.total_count) * 100 : 0;
      const fill = document.getElementById('banner-progress-fill');
      if (fill) fill.style.width = `${pct}%`;
    }

    // 2. Live Activity Campaign Card
    if (liveCard) {
      liveCard.style.display = 'block';

      const campName = document.getElementById('act-live-camp-name');
      if (campName) campName.textContent = job.campaign_name;

      const badge = document.getElementById('act-live-camp-badge');
      if (badge) {
        if (job.status === 'WAITING_FOR_CONNECTION') {
          badge.className = 'badge badge-warning';
          badge.textContent = 'Waiting for connection';
        } else if (job.status === 'RUNNING') {
          badge.className = 'badge badge-success';
          badge.textContent = 'Running';
        } else if (job.status === 'PAUSED') {
          badge.className = 'badge badge-neutral';
          badge.textContent = 'Paused';
        } else if (job.status === 'SCHEDULED') {
          badge.className = 'badge badge-primary';
          badge.textContent = 'Scheduled';
        } else {
          badge.className = 'badge badge-neutral';
          badge.textContent = job.status;
        }
      }

      const recipEl = document.getElementById('act-live-current-recipient');
      if (recipEl) {
        if (job.status === 'WAITING_FOR_CONNECTION') {
          recipEl.textContent = 'Browser not ready. Campaign will automatically begin once WhatsApp Web is connected.';
        } else if (job.status === 'PAUSED') {
          recipEl.textContent = 'Campaign paused by operator. Outbound sends are halted.';
        } else if (job.status === 'SCHEDULED') {
          recipEl.textContent = `Scheduled to run at: ${job.scheduled_at ? new Date(job.scheduled_at).toLocaleString() : 'specified time'}`;
        } else if (job.current_recipient) {
          const masked = this.formatPhone(job.current_recipient.phone);
          recipEl.textContent = `Currently processing: ${masked} (${job.current_recipient.name || 'Recipient'})`;
        } else {
          recipEl.textContent = 'Processing recipient queue...';
        }
      }

      const pct = job.total_count > 0 ? Math.round((job.sent_count / job.total_count) * 100) : 0;
      const fillBar = document.getElementById('act-live-progress-bar');
      if (fillBar) fillBar.style.width = `${pct}%`;

      const statPct = document.getElementById('act-live-stat-pct');
      if (statPct) statPct.textContent = `${pct}%`;

      const statSent = document.getElementById('act-live-stat-sent');
      if (statSent) statSent.textContent = job.sent_count || 0;

      const statPending = document.getElementById('act-live-stat-pending');
      if (statPending) {
        const pending = Math.max(0, (job.total_count || 0) - (job.sent_count || 0) - (job.failed_count || 0) - (job.skipped_count || 0));
        statPending.textContent = pending;
      }

      const statFailed = document.getElementById('act-live-stat-failed');
      if (statFailed) statFailed.textContent = job.failed_count || 0;

      const statSkipped = document.getElementById('act-live-stat-skipped');
      if (statSkipped) statSkipped.textContent = job.skipped_count || 0;

      const lastAct = document.getElementById('act-live-last-action');
      if (lastAct) {
        lastAct.textContent = `Last action: ${job.last_action || 'Initialized campaign queue'}`;
      }

      const lastErr = document.getElementById('act-live-last-error');
      if (lastErr) {
        if (job.last_error) {
          lastErr.style.display = 'inline';
          lastErr.textContent = `Issue: ${job.last_error}`;
        } else {
          lastErr.style.display = 'none';
        }
      }

      const btnPause = document.getElementById('btn-live-pause');
      const btnResume = document.getElementById('btn-live-resume');
      if (btnPause && btnResume) {
        if (job.status === 'PAUSED') {
          btnPause.style.display = 'none';
          btnResume.style.display = 'inline-block';
        } else {
          btnPause.style.display = 'inline-block';
          btnResume.style.display = 'none';
        }
      }
    }
  }

  async pauseActiveJob() {
    if (!this.activeJob) return;
    try {
      await this.api(`/api/jobs/${this.activeJob.id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'pause' })
      });
      this.showToast('Campaign paused', 'info');
      await this.refreshActiveJob();
    } catch (e) {
      this.showToast(e.message || 'Failed to pause campaign', 'error');
    }
  }

  async resumeActiveJob() {
    if (!this.activeJob) return;
    try {
      await this.api(`/api/jobs/${this.activeJob.id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'resume' })
      });
      this.showToast('Campaign resumed', 'info');
      await this.refreshActiveJob();
    } catch (e) {
      this.showToast(e.message || 'Failed to resume campaign', 'error');
    }
  }

  async inspectActiveJobDrawer(jobId) {
    const id = jobId || this.activeJob?.id;
    if (!id) {
      this.showToast('No active campaign to inspect', 'info');
      return;
    }

    const titleEl = document.getElementById('drawer-job-title');
    const subtitleEl = document.getElementById('drawer-job-subtitle');
    const bodyEl = document.getElementById('drawer-recipients-body');

    if (titleEl) {
      titleEl.textContent = `Queue Inspection: ${this.activeJob?.campaign_name || 'Campaign #' + id}`;
    }
    if (subtitleEl) {
      subtitleEl.textContent = `Live status: ${this.activeJob?.status || 'Active'} · Inspecting per-recipient states and failure reasons`;
    }
    if (bodyEl) {
      bodyEl.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">Loading queue items...</td></tr>`;
    }

    this.openModal('modal-job-drawer');

    try {
      const items = await this.api(`/api/jobs/${id}/queue`, { silent: true });
      if (!items || items.length === 0) {
        if (bodyEl) {
          bodyEl.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No recipients in this queue yet.</td></tr>`;
        }
        return;
      }

      if (bodyEl) {
        bodyEl.innerHTML = items.map(item => {
          const maskedPhone = this.formatPhone(item.phone);
          const badgeClass = item.status === 'SENT' ? 'badge-success' : (item.status === 'FAILED' ? 'badge-danger' : (item.status === 'SKIPPED' ? 'badge-warning' : (item.status === 'PROCESSING' ? 'badge-primary' : 'badge-neutral')));
          const msgPreview = (item.personalized_content || '').substring(0, 45) + ((item.personalized_content || '').length > 45 ? '...' : '');
          const safeMsg = msgPreview.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
          const safeName = (item.recipient_name || 'Unknown').replace(/</g, '&lt;');
          const detail = item.error_reason ? `<span style="color: var(--danger);">${item.error_reason}</span>` : (item.status === 'SENT' ? 'Dispatched' : 'Pending');

          return `
            <tr>
              <td><strong>${safeName}</strong></td>
              <td><code>${maskedPhone}</code></td>
              <td style="font-size: 0.75rem; color: var(--text-secondary); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${safeMsg}</td>
              <td><span class="badge ${badgeClass}">${item.status}</span></td>
              <td>${item.attempts || 0} / ${item.max_retries || 3}</td>
              <td style="font-size: 0.75rem;">${detail}</td>
            </tr>
          `;
        }).join('');
      }
    } catch (e) {
      if (bodyEl) {
        bodyEl.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--danger); padding: 1.5rem;">Failed to load queue items: ${e.message}</td></tr>`;
      }
    }
  }

  updateJobProgress(msg) {
    const banner = document.getElementById('active-job-banner');
    if (banner) banner.style.display = 'block';

    const counts = document.getElementById('banner-progress-counts');
    if (counts) counts.textContent = `${msg.sent} / ${msg.total} sent`;

    const fill = document.getElementById('banner-progress-fill');
    if (fill) fill.style.width = `${msg.percentage}%`;
  }

  async toggleActiveJobPause() {
    if (!this.activeJob) return;
    const action = this.activeJob.status === 'PAUSED' ? 'resume' : 'pause';
    try {
      await this.api(`/api/jobs/${this.activeJob.id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action })
      });
      this.showToast(`Campaign ${action}d`, 'info');
      await this.refreshActiveJob();
    } catch (e) {}
  }

  async cancelActiveJob() {
    if (!this.activeJob) return;
    const ok = await this.confirmDialog({
      title: 'Stop Campaign',
      message: 'Are you sure you want to stop this campaign?',
      details: 'Outgoing dispatches will cease immediately. Completed messages will remain logged.',
      confirmText: 'Stop Campaign',
      cancelText: 'Continue Sending',
      isDestructive: true
    });
    if (!ok) return;
    try {
      await this.api(`/api/jobs/${this.activeJob.id}/action`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'cancel' })
      });
      this.showToast('Campaign stopped', 'warning');
      this.updateActiveJobBanner(null);
      this.loadDashboardData();
    } catch (e) {}
  }

  // ==========================================================================
  // SECTION 2: CONTACTS
  // ==========================================================================
  toggleSuppressionView() {
    this.viewingSuppression = !this.viewingSuppression;
    const btn = document.getElementById('btn-show-optouts');
    if (btn) {
      btn.textContent = this.viewingSuppression ? '← Back to Active Contacts' : 'View Blocked / Opt-Outs';
    }
    this.loadContacts();
  }

  async loadContacts() {
    const body = document.getElementById('contacts-view-body');
    if (!body) return;

    if (this.viewingSuppression) {
      const bulkBar = document.getElementById('contacts-bulk-bar');
      if (bulkBar) bulkBar.style.display = 'none';
      await this.loadSuppressionContacts(body);
      return;
    }

    try {
      // Refresh groups dropdown
      const groups = await this.api('/api/contacts/groups');
      this.availableGroups = groups || [];
      const groupFilter = document.getElementById('contacts-group-filter');
      if (groupFilter) {
        const cur = groupFilter.value;
        groupFilter.innerHTML = '<option value="All">All Groups</option>' +
          groups.map(g => `<option value="${g.name}">${g.name} (${g.contact_count})</option>`).join('');
        if (cur) groupFilter.value = cur;
      }

      // Also refresh bulk move group dropdown
      const bulkMoveSelect = document.getElementById('bulk-move-group-select');
      if (bulkMoveSelect) {
        bulkMoveSelect.innerHTML = groups.map(g => `<option value="${g.name}">${g.name}</option>`).join('');
      }

      // Check demo fixture records and toggle banner
      this.api('/api/contacts/demo-records', { silent: true })
        .then(res => {
          const banner = document.getElementById('contacts-demo-banner');
          const countEl = document.getElementById('demo-records-count');
          if (banner && countEl) {
            if (res && res.count > 0) {
              countEl.textContent = res.count;
              banner.style.display = 'flex';
            } else {
              banner.style.display = 'none';
            }
          }
        })
        .catch(() => {});

      // Check duplicate phone numbers and toggle banner
      this.api('/api/contacts/duplicates', { silent: true })
        .then(res => {
          const banner = document.getElementById('contacts-duplicates-banner');
          const countEl = document.getElementById('duplicates-count');
          if (banner && countEl) {
            const clusters = (res && res.duplicates) || [];
            if (clusters.length > 0) {
              countEl.textContent = clusters.length;
              banner.style.display = 'flex';
            } else {
              banner.style.display = 'none';
            }
          }
        })
        .catch(() => {});

      const selectedGroup = groupFilter && groupFilter.value !== 'All' ? groupFilter.value : '';
      const search = (document.getElementById('contacts-search-input')?.value || '').trim();
      const consentFilter = document.getElementById('contacts-consent-filter')?.value || 'All';

      const query = new URLSearchParams({ limit: 200, offset: 0 });
      if (selectedGroup) query.append('group', selectedGroup);
      if (search) query.append('search', search);

      const res = await this.api(`/api/contacts?${query.toString()}`);
      let items = res.items || [];
      this.totalContactsMatchingFilter = res.total || items.length;
      if (consentFilter !== 'All') {
        items = items.filter(c => (c.consent_status || 'opted_in') === consentFilter);
      }
      this.allContactItems = items;

      // Prune any selectedContactIds that are no longer in items
      const validIds = new Set(items.map(c => c.id));
      for (const id of this.selectedContactIds) {
        if (!validIds.has(id)) this.selectedContactIds.delete(id);
      }
      this.updateBulkBar();

      const countLabel = document.getElementById('contacts-count-label');
      if (countLabel) countLabel.textContent = `${items.length} contact${items.length === 1 ? '' : 's'}`;

      if (items.length === 0) {
        body.innerHTML = `
          <div class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path><circle cx="9" cy="7" r="4"></circle></svg>
            <div class="empty-title">No contacts yet — import a CSV or paste numbers</div>
            <div class="empty-description">Build your audience by importing contacts with consent tracking. Genuine contacts will appear here.</div>
            <div style="display: flex; gap: 0.5rem;">
              <button class="btn btn-primary btn-sm" onclick="app.openImportModal()">Import CSV / Excel</button>
              <button class="btn btn-secondary btn-sm" onclick="app.openPasteModal()">Paste Numbers</button>
              <button class="btn btn-secondary btn-sm" onclick="app.openAddContactModal()">+ Add Contact</button>
            </div>
          </div>
        `;
        return;
      }

      const allSelected = items.length > 0 && items.every(c => this.selectedContactIds.has(c.id));

      body.innerHTML = `
        <div class="table-container" style="border: none; border-radius: 0;">
          <table>
            <thead>
              <tr>
                <th style="width: 44px; text-align: center;">
                  <input type="checkbox" id="chk-select-all-contacts" ${allSelected ? 'checked' : ''} onchange="app.toggleSelectAllContacts(this.checked)" title="Select All Visible" style="cursor: pointer; width: 16px; height: 16px; accent-color: var(--primary);">
                </th>
                <th>Name</th>
                <th>Phone Number</th>
                <th>Group</th>
                <th>Tier</th>
                <th>Lang</th>
                <th>Consent Status</th>
                <th style="text-align: right;">Actions</th>
              </tr>
            </thead>
            <tbody>
              ${items.map(c => {
                const isSelected = this.selectedContactIds.has(c.id);
                const isOptedOut = c.consent_status === 'opted_out';
                const statusBadge = isOptedOut ? '<span class="badge badge-danger">OPTED OUT</span>' : '<span class="badge badge-success">OPTED IN</span>';
                const tier = c.customer_tier || 'Regular';
                const tierBadgeClass = tier === 'VIP' ? 'badge-primary' : (tier === 'Enterprise' ? 'badge-warning' : 'badge-neutral');
                const lang = c.language || 'en';

                return `
                  <tr class="${isSelected ? 'row-selected' : ''}" style="${isSelected ? 'background-color: var(--primary-subtle);' : ''}" id="contact-row-${c.id}">
                    <td style="text-align: center; width: 44px;">
                      <input type="checkbox" class="contact-row-chk" value="${c.id}" ${isSelected ? 'checked' : ''} onchange="app.onContactSelectToggle(${c.id}, this.checked, event)" style="cursor: pointer; width: 16px; height: 16px; accent-color: var(--primary);">
                    </td>
                    <td>
                      <div style="display: flex; align-items: center; gap: 0.35rem;">
                        <strong>${c.name}</strong>
                        <button class="btn btn-subtle btn-xs" onclick="app.startInlineEditName(${c.id}, '${(c.name || '').replace(/'/g, "\\'")}', event)" title="Edit name" style="padding: 0 0.25rem; font-size: 0.65rem; opacity: 0.6; cursor: pointer;">✏️</button>
                      </div>
                    </td>
                    <td><span style="font-family: var(--font-mono); font-size: 0.78rem;">+${this.formatPhone(c.phone)}</span></td>
                    <td><span class="badge badge-neutral">${c.group_name}</span></td>
                    <td><span class="badge ${tierBadgeClass}">${tier}</span></td>
                    <td><code style="font-size: 0.75rem;">${lang}</code></td>
                    <td>${statusBadge}</td>
                    <td style="text-align: right;">
                      <div style="display: inline-flex; gap: 0.25rem;">
                        <button class="btn btn-subtle btn-sm" onclick="app.openEditContactModal(${c.id})">Edit</button>
                        <button class="btn btn-subtle btn-sm" onclick="app.toggleConsent(${c.id}, '${c.consent_status}')">
                          ${isOptedOut ? 'Re-Opt In' : 'Opt Out'}
                        </button>
                        <button class="btn btn-subtle btn-sm" onclick="app.deleteContact(${c.id})" style="color: var(--danger);">Delete</button>
                      </div>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    } catch (e) {}
  }

  // --- Contact Multi-Select & Shift+Click Continuous Selection ---
  toggleSelectAllContacts(checked) {
    const items = this.allContactItems || [];
    if (items.length === 0) return;

    if (checked) {
      items.forEach(c => this.selectedContactIds.add(c.id));
    } else {
      if (this.selectedContactIds.size > 0 && this.selectedContactIds.size < items.length) {
        items.forEach(c => this.selectedContactIds.add(c.id));
      } else {
        this.selectedContactIds.clear();
      }
    }

    // Check if more contacts exist across pages matching filter
    const banner = document.getElementById('contacts-filter-select-all-banner');
    const textEl = document.getElementById('contacts-filter-select-all-text');
    if (banner && textEl) {
      if (this.selectedContactIds.size === items.length && this.totalContactsMatchingFilter > items.length) {
        textEl.textContent = `All ${items.length} contacts on this page are selected.`;
        banner.style.display = 'flex';
      } else {
        banner.style.display = 'none';
      }
    }

    this.updateBulkBar();
  }

  async selectAllFilteredContacts() {
    const groupFilter = document.getElementById('contacts-group-filter')?.value;
    const selectedGroup = groupFilter && groupFilter !== 'All' ? groupFilter : '';
    const search = (document.getElementById('contacts-search-input')?.value || '').trim();

    const query = new URLSearchParams({ limit: 10000, offset: 0 });
    if (selectedGroup) query.append('group', selectedGroup);
    if (search) query.append('search', search);

    try {
      const res = await this.api(`/api/contacts?${query.toString()}`);
      const items = res.items || [];
      items.forEach(c => this.selectedContactIds.add(c.id));
      const textEl = document.getElementById('contacts-filter-select-all-text');
      if (textEl) {
        textEl.textContent = `All ${this.selectedContactIds.size} matching contacts across all pages are selected.`;
      }
      this.updateBulkBar();
      this.showToast(`Selected all ${this.selectedContactIds.size} matching contacts`, 'info');
    } catch (e) {
      this.showToast('Failed to select all filtered contacts', 'error');
    }
  }

  onContactSelectToggle(id, checked, event) {
    const items = this.allContactItems || [];
    const currentIndex = items.findIndex(c => c.id === id);

    if (event && event.shiftKey && this.lastCheckedContactIndex !== null && currentIndex !== -1) {
      const start = Math.min(this.lastCheckedContactIndex, currentIndex);
      const end = Math.max(this.lastCheckedContactIndex, currentIndex);
      for (let i = start; i <= end; i++) {
        const item = items[i];
        if (checked) {
          this.selectedContactIds.add(item.id);
        } else {
          this.selectedContactIds.delete(item.id);
        }
      }
    } else {
      if (checked) {
        this.selectedContactIds.add(id);
      } else {
        this.selectedContactIds.delete(id);
      }
      if (currentIndex !== -1) {
        this.lastCheckedContactIndex = currentIndex;
      }
    }
    this.updateBulkBar();
  }

  updateBulkBar() {
    const count = this.selectedContactIds.size;
    const totalVisible = (this.allContactItems || []).length;
    const isAllSelected = (totalVisible > 0 && count === totalVisible);
    const isIndeterminate = (count > 0 && count < totalVisible);

    const normalHeader = document.getElementById('contacts-header-normal');
    const bulkHeader = document.getElementById('contacts-header-bulk');
    const bulkBar = document.getElementById('contacts-bulk-bar');

    const chkMaster = document.getElementById('chk-master-contacts');
    const chkMasterBulk = document.getElementById('chk-master-contacts-bulk');
    const chkAll = document.getElementById('chk-select-all-contacts');

    const countEl = document.getElementById('bulk-selected-count');
    const countBadge = document.getElementById('bulk-selected-count-badge');
    const deleteBtn = document.getElementById('btn-bulk-delete');
    const deleteBtnTop = document.getElementById('btn-bulk-delete-top');

    if (count > 0) {
      if (normalHeader) normalHeader.style.display = 'none';
      if (bulkHeader) bulkHeader.style.display = 'flex';
      if (bulkBar) bulkBar.style.display = 'flex';
    } else {
      if (normalHeader) normalHeader.style.display = 'flex';
      if (bulkHeader) bulkHeader.style.display = 'none';
      if (bulkBar) bulkBar.style.display = 'none';
    }

    const countText = `${count} selected`;
    if (countEl) countEl.textContent = countText;
    if (countBadge) countBadge.textContent = countText;

    const deleteText = `Delete (${count})`;
    if (deleteBtn) deleteBtn.textContent = deleteText;
    if (deleteBtnTop) deleteBtnTop.textContent = deleteText;

    [chkMaster, chkMasterBulk, chkAll].forEach(chk => {
      if (chk) {
        chk.checked = isAllSelected;
        chk.indeterminate = isIndeterminate;
      }
    });

    // Authoritative state synchronization to all row checkboxes and tr styles in DOM
    const checkboxes = document.querySelectorAll('.contact-row-chk');
    checkboxes.forEach(chk => {
      const cid = parseInt(chk.value, 10);
      const isSel = this.selectedContactIds.has(cid);
      chk.checked = isSel;
      const tr = chk.closest('tr');
      if (tr) {
        tr.classList.toggle('row-selected', isSel);
        tr.style.backgroundColor = isSel ? 'var(--primary-subtle, rgba(0, 168, 132, 0.12))' : '';
      }
    });
  }

  clearContactSelection() {
    this.selectedContactIds.clear();
    this.lastCheckedContactIndex = null;
    const banner = document.getElementById('contacts-filter-select-all-banner');
    if (banner) banner.style.display = 'none';
    this.updateBulkBar();
  }

  async promptBulkMove() {
    const count = this.selectedContactIds.size;
    if (count === 0) return;
    const groups = (this.availableGroups || []).map(g => g.name || g).filter(Boolean);
    const defaultSuggestion = groups.find(g => g !== 'Default') || 'VIP';
    const groupName = prompt(`Move ${count} selected contact(s) to group:\n(Available: ${groups.join(', ') || 'Default'})\n\nEnter group name:`, defaultSuggestion);
    if (!groupName || !groupName.trim()) return;
    await this.executeBulkMoveToGroup(groupName.trim());
  }

  async promptBulkCopy() {
    const count = this.selectedContactIds.size;
    if (count === 0) return;
    const groups = (this.availableGroups || []).map(g => g.name || g).filter(Boolean);
    const defaultSuggestion = groups.find(g => g !== 'Default') || 'VIP';
    const groupName = prompt(`Copy ${count} selected contact(s) into group:\n(Available: ${groups.join(', ') || 'Default'})\n\nEnter target group name:`, defaultSuggestion);
    if (!groupName || !groupName.trim()) return;
    await this.executeBulkCopyToGroup(groupName.trim());
  }

  async promptBulkAddToGroup() {
    const count = this.selectedContactIds.size;
    if (count === 0) return;
    const groups = (this.availableGroups || []).map(g => g.name || g).filter(Boolean);
    const groupName = prompt(`Add ${count} selected contact(s) to group (enter existing or new group name):\n(Existing: ${groups.join(', ') || 'Default'})\n\nEnter group name:`, 'VIP');
    if (!groupName || !groupName.trim()) return;
    await this.executeBulkMoveToGroup(groupName.trim());
  }

  async executeBulkMoveToGroup(targetGroup) {
    const count = this.selectedContactIds.size;
    if (count === 0 || !targetGroup) return;
    try {
      const res = await this.api('/api/contacts/bulk-move', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_ids: Array.from(this.selectedContactIds),
          target_group: targetGroup
        })
      });
      this.showToast(res.message || `Successfully moved ${res.updated_count || count} contact(s) to group "${targetGroup}"`, 'success');
      this.clearContactSelection();
      await this.loadContacts();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to move contacts', 'error');
    }
  }

  async executeBulkCopyToGroup(targetGroup) {
    const count = this.selectedContactIds.size;
    if (count === 0 || !targetGroup) return;
    try {
      const res = await this.api('/api/contacts/bulk-copy', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_ids: Array.from(this.selectedContactIds),
          target_group: targetGroup
        })
      });
      this.showToast(res.message || `Successfully copied ${res.copied_count || count} contact(s) to group "${targetGroup}"`, 'success');
      this.clearContactSelection();
      await this.loadContacts();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to copy contacts', 'error');
    }
  }

  async executeBulkMove() {
    const select = document.getElementById('bulk-move-group-select');
    const targetGroup = select ? select.value : 'Default';
    if (!targetGroup) return;
    await this.executeBulkMoveToGroup(targetGroup);
  }

  async executeBulkCopy() {
    const select = document.getElementById('bulk-move-group-select');
    const targetGroup = select ? select.value : 'Default';
    if (!targetGroup) return;
    await this.executeBulkCopyToGroup(targetGroup);
  }

  async executeBulkTier() {
    if (this.selectedContactIds.size === 0) return;
    const select = document.getElementById('bulk-set-tier-select');
    const targetTier = select ? select.value : 'Regular';

    try {
      const res = await this.api('/api/contacts/bulk-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_ids: Array.from(this.selectedContactIds),
          customer_tier: targetTier
        })
      });
      this.showToast(res.message || `Updated tier to ${targetTier}`, 'success');
      this.clearContactSelection();
      await this.loadContacts();
    } catch (e) {
      this.showToast(e.message || 'Failed to update customer tier', 'error');
    }
  }

  async executeBulkLanguage() {
    if (this.selectedContactIds.size === 0) return;
    const select = document.getElementById('bulk-set-lang-select');
    const targetLang = select ? select.value : 'en';

    try {
      const res = await this.api('/api/contacts/bulk-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_ids: Array.from(this.selectedContactIds),
          language: targetLang
        })
      });
      this.showToast(res.message || `Updated language to ${targetLang}`, 'success');
      this.clearContactSelection();
      await this.loadContacts();
    } catch (e) {
      this.showToast(e.message || 'Failed to update language', 'error');
    }
  }

  async executeBulkSuppress() {
    if (this.selectedContactIds.size === 0) return;
    const ok = await this.confirmDialog({
      title: 'Suppress Contacts',
      message: `Suppress / opt out ${this.selectedContactIds.size} selected contact(s)?`,
      details: 'These contacts will be excluded from all upcoming automated broadcasts.',
      confirmText: 'Suppress Contacts',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    try {
      const res = await this.api('/api/contacts/bulk-edit', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_ids: Array.from(this.selectedContactIds),
          consent_status: 'opted_out'
        })
      });
      this.showToast(res.message || `Suppressed ${this.selectedContactIds.size} contacts`, 'success');
      this.clearContactSelection();
      await this.loadContacts();
    } catch (e) {
      this.showToast(e.message || 'Failed to suppress contacts', 'error');
    }
  }

  async executeBulkDelete() {
    const count = this.selectedContactIds.size;
    if (count === 0) return;
    const ok = await this.confirmDialog({
      title: 'Delete Contacts',
      message: `Are you sure you want to permanently delete ${count} selected contact${count === 1 ? '' : 's'}?`,
      details: 'This will remove the contacts from your database completely.',
      confirmText: `Delete ${count} Contact${count === 1 ? '' : 's'}`,
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    try {
      const res = await this.api('/api/contacts/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          contact_ids: Array.from(this.selectedContactIds)
        })
      });
      this.showToast(res.message || `Deleted ${res.deleted_count} contacts`, 'success');
      this.clearContactSelection();
      await this.loadContacts();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to delete contacts', 'error');
    }
  }

  exportSelectedContacts() {
    if (this.selectedContactIds.size === 0) {
      this.showToast('No contacts selected for export', 'warning');
      return;
    }
    const selected = (this.allContactItems || []).filter(c => this.selectedContactIds.has(c.id));
    if (selected.length === 0) return;

    const headers = ['id', 'name', 'phone', 'group_name', 'customer_tier', 'language', 'consent_status'];
    const rows = [headers.join(',')];
    selected.forEach(c => {
      rows.push([
        c.id,
        `"${(c.name || '').replace(/"/g, '""')}"`,
        `"${c.phone || ''}"`,
        `"${(c.group_name || '').replace(/"/g, '""')}"`,
        c.customer_tier || 'Regular',
        c.language || 'en',
        c.consent_status || 'opted_in'
      ].join(','));
    });

    const blob = new Blob([rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `contacts_export_${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    this.showToast(`Exported ${selected.length} contact(s) to CSV`, 'success');
  }

  startInlineEditName(contactId, currentName, event) {
    if (event) event.stopPropagation();
    const btn = event.target;
    const container = btn.closest('div');
    if (!container || container.querySelector('input')) return;

    container.innerHTML = `
      <input type="text" class="form-input form-input-sm" value="${currentName.replace(/"/g, '&quot;')}" style="font-size: 0.8125rem; padding: 0.15rem 0.4rem; width: 100%; max-width: 180px;">
    `;
    const input = container.querySelector('input');
    input.focus();
    input.select();

    const saveEdit = async () => {
      const newName = input.value.trim();
      if (!newName || newName === currentName) {
        container.innerHTML = `<strong>${currentName}</strong> <button class="btn btn-subtle btn-xs" onclick="app.startInlineEditName(${contactId}, '${currentName.replace(/'/g, "\\'")}', event)" title="Edit name" style="padding: 0 0.25rem; font-size: 0.65rem; opacity: 0.6; cursor: pointer;">✏️</button>`;
        return;
      }
      try {
        await this.api(`/api/contacts/${contactId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name: newName })
        });
        this.showToast('Contact updated', 'success');
        this.loadContacts();
      } catch (e) {
        this.showToast(e.message || 'Failed to update contact', 'error');
        this.loadContacts();
      }
    };

    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') {
        input.blur();
      } else if (e.key === 'Escape') {
        container.innerHTML = `<strong>${currentName}</strong> <button class="btn btn-subtle btn-xs" onclick="app.startInlineEditName(${contactId}, '${currentName.replace(/'/g, "\\'")}', event)" title="Edit name" style="padding: 0 0.25rem; font-size: 0.65rem; opacity: 0.6; cursor: pointer;">✏️</button>`;
      }
    });
    input.addEventListener('blur', saveEdit, { once: true });
  }

  // --- Add Contact Modal ---
  openAddContactModal() {
    const nameInput = document.getElementById('new-contact-name');
    const phoneInput = document.getElementById('new-contact-phone');
    const gSelect = document.getElementById('new-contact-group');
    if (nameInput) nameInput.value = '';
    if (phoneInput) phoneInput.value = '';
    if (gSelect) {
      gSelect.innerHTML = (this.availableGroups || [{ name: 'Default' }]).map(g =>
        `<option value="${g.name}">${g.name}</option>`
      ).join('');
    }
    this.openModal('modal-add-contact');
  }

  async confirmAddSingleContact() {
    const name = (document.getElementById('new-contact-name')?.value || '').trim();
    const phone = (document.getElementById('new-contact-phone')?.value || '').trim();
    const group = document.getElementById('new-contact-group')?.value || 'Default';
    const tier = document.getElementById('new-contact-tier')?.value || 'Regular';
    const lang = document.getElementById('new-contact-lang')?.value || 'en';
    const deduplicate = document.getElementById('new-contact-deduplicate')?.checked ?? true;

    if (!name) {
      this.showToast('Please enter a contact name', 'error');
      return;
    }
    if (!phone) {
      this.showToast('Please enter a phone number', 'error');
      return;
    }

    try {
      const url = `/api/contacts?deduplicate=${deduplicate ? 'true' : 'false'}`;
      const res = await this.api(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name,
          phone: phone,
          group_name: group,
          customer_tier: tier,
          language: lang,
          consent_status: 'opted_in'
        })
      });
      this.showToast(`Added contact: ${name}`, 'success');
      this.closeModal('modal-add-contact');
      await this.loadContacts();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to add contact', 'error');
    }
  }

  // --- Demo Records Modal ---
  async openDemoRecordsModal() {
    try {
      const res = await this.api('/api/contacts/demo-records');
      const tbody = document.getElementById('demo-records-table-body');
      const statusText = document.getElementById('demo-modal-status-text');
      const delBtn = document.getElementById('btn-confirm-delete-demos');

      if (tbody) {
        const records = res.demo_records || [];
        if (records.length === 0) {
          tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; padding: 1.5rem; color: var(--text-muted);">No demo or test records detected. All contacts are genuine.</td></tr>`;
          if (delBtn) delBtn.disabled = true;
          if (statusText) statusText.textContent = 'All 0 detected records are genuine.';
        } else {
          tbody.innerHTML = records.map(r => `
            <tr>
              <td><code>${r.id}</code></td>
              <td><strong>${r.name}</strong></td>
              <td><span style="font-family: var(--font-mono); font-size: 0.78rem;">+${r.phone}</span></td>
              <td><span class="badge badge-neutral">${r.group_name}</span></td>
              <td><span class="badge badge-warning">${r.reason || 'Test fixture pattern'}</span></td>
            </tr>
          `).join('');
          if (delBtn) delBtn.disabled = false;
          if (statusText) statusText.textContent = `Found ${records.length} synthetic test record(s). Genuine contacts (e.g. Gaurav, Me) will NOT be touched.`;
        }
      }
      this.openModal('modal-demo-records');
    } catch (e) {
      this.showToast(e.message || 'Failed to inspect demo records', 'error');
    }
  }

  async confirmDeleteDemoRecords() {
    try {
      const res = await this.api('/api/contacts/demo-records/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true })
      });
      this.showToast(`Safely removed ${res.removed_count} test fixture records. Genuine contacts preserved.`, 'success');
      this.closeModal('modal-demo-records');
      await this.loadContacts();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to remove test records', 'error');
    }
  }

  // --- Duplicate Clusters & Merge Modal ---
  async openMergeDuplicatesModal() {
    try {
      const res = await this.api('/api/contacts/duplicates');
      const body = document.getElementById('merge-duplicates-body');
      const clusters = (res && res.duplicates) || [];

      if (!body) return;
      if (clusters.length === 0) {
        body.innerHTML = `
          <div style="padding: 2rem; text-align: center; color: var(--text-muted);">
            No duplicate phone numbers found. Every contact number is unique.
          </div>
        `;
      } else {
        body.innerHTML = clusters.map((cl) => {
          const phone = cl.phone;
          const records = cl.records || [];
          const primaryId = records[0]?.id;
          const dupIds = records.slice(1).map(r => r.id);

          return `
            <div class="card" style="margin-bottom: 1rem; border: 1px solid var(--border-color);">
              <div class="card-header" style="padding: 0.5rem 0.75rem; background: var(--surface-subtle); display: flex; justify-content: space-between; align-items: center;">
                <span style="font-weight: 600; font-size: 0.8125rem;">Phone: +${phone} (${records.length} records)</span>
                <button type="button" class="btn btn-primary btn-sm" onclick="app.mergeDuplicateCluster(${primaryId}, [${dupIds.join(',')}])">
                  Keep Earliest (#${primaryId}) & Merge Duplicates
                </button>
              </div>
              <div class="card-body" style="padding: 0;">
                <table style="width: 100%; font-size: 0.75rem;">
                  <thead>
                    <tr>
                      <th style="padding: 0.35rem 0.5rem;">ID</th>
                      <th style="padding: 0.35rem 0.5rem;">Name</th>
                      <th style="padding: 0.35rem 0.5rem;">Group</th>
                      <th style="padding: 0.35rem 0.5rem;">Tier</th>
                      <th style="padding: 0.35rem 0.5rem;">Consent</th>
                    </tr>
                  </thead>
                  <tbody>
                    ${records.map((r, rIdx) => `
                      <tr style="${rIdx === 0 ? 'font-weight: 600; background: var(--primary-subtle);' : ''}">
                        <td style="padding: 0.35rem 0.5rem;">#${r.id} ${rIdx === 0 ? '<span class="badge badge-primary">Primary</span>' : ''}</td>
                        <td style="padding: 0.35rem 0.5rem;">${r.name}</td>
                        <td style="padding: 0.35rem 0.5rem;">${r.group_name}</td>
                        <td style="padding: 0.35rem 0.5rem;">${r.customer_tier || 'Regular'}</td>
                        <td style="padding: 0.35rem 0.5rem;">${r.consent_status}</td>
                      </tr>
                    `).join('')}
                  </tbody>
                </table>
              </div>
            </div>
          `;
        }).join('');
      }
      this.openModal('modal-merge-duplicates');
    } catch (e) {
      this.showToast(e.message || 'Failed to inspect duplicate contacts', 'error');
    }
  }

  async mergeDuplicateCluster(primaryId, duplicateIds) {
    try {
      const res = await this.api('/api/contacts/merge', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ primary_id: primaryId, duplicate_ids: duplicateIds })
      });
      this.showToast(`Merged ${duplicateIds.length} duplicate(s) into primary contact #${primaryId}`, 'success');
      await this.openMergeDuplicatesModal();
      await this.loadContacts();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to merge duplicates', 'error');
    }
  }

  // --- Real Contact Editing with Strict Consent Protection ---
  async openEditContactModal(contactId) {
    try {
      const c = await this.api(`/api/contacts/${contactId}`);
      document.getElementById('edit-contact-id').value = c.id;
      document.getElementById('edit-contact-name').value = c.name || '';
      document.getElementById('edit-contact-phone').value = c.phone || '';

      // Populate group select
      const gSelect = document.getElementById('edit-contact-group');
      if (gSelect) {
        gSelect.innerHTML = (this.availableGroups || [{ name: 'Default' }]).map(g =>
          `<option value="${g.name}">${g.name}</option>`
        ).join('');
        gSelect.value = c.group_name || 'Default';
      }

      document.getElementById('edit-contact-tier').value = c.customer_tier || 'Regular';
      document.getElementById('edit-contact-lang').value = c.language || 'en';

      const initialConsent = c.consent_status || 'opted_in';
      this.editingContactInitialConsent = initialConsent;
      const consentSelect = document.getElementById('edit-contact-consent');
      if (consentSelect) consentSelect.value = initialConsent;

      const overrideBox = document.getElementById('edit-contact-override-box');
      const overrideChk = document.getElementById('edit-contact-consent-override');
      if (overrideBox) overrideBox.style.display = 'none';
      if (overrideChk) overrideChk.checked = false;

      const optOutGroup = document.getElementById('edit-contact-optout-reason-group');
      const optOutInput = document.getElementById('edit-contact-optout-reason');
      if (optOutGroup) optOutGroup.style.display = initialConsent === 'opted_out' ? 'block' : 'none';
      if (optOutInput) optOutInput.value = c.opt_out_reason || '';

      const customInput = document.getElementById('edit-contact-custom-fields');
      if (customInput) {
        customInput.value = c.custom_fields && Object.keys(c.custom_fields).length > 0
          ? JSON.stringify(c.custom_fields, null, 2)
          : '';
      }

      this.openModal('modal-edit-contact');
    } catch (e) {
      this.showToast(e.message || 'Failed to load contact details', 'error');
    }
  }

  onEditConsentChange() {
    const sel = document.getElementById('edit-contact-consent');
    const val = sel ? sel.value : 'opted_in';
    const overrideBox = document.getElementById('edit-contact-override-box');
    const optOutGroup = document.getElementById('edit-contact-optout-reason-group');

    // Strict Opt-Out Protection: Require explicit override checkbox if previously opted_out
    if (this.editingContactInitialConsent === 'opted_out' && val === 'opted_in') {
      if (overrideBox) overrideBox.style.display = 'block';
    } else {
      if (overrideBox) overrideBox.style.display = 'none';
    }

    if (optOutGroup) {
      optOutGroup.style.display = val === 'opted_out' ? 'block' : 'none';
    }
  }

  async saveContactEdit() {
    const id = document.getElementById('edit-contact-id').value;
    const name = document.getElementById('edit-contact-name').value.trim();
    const phone = document.getElementById('edit-contact-phone').value.trim();
    const groupName = document.getElementById('edit-contact-group').value;
    const tier = document.getElementById('edit-contact-tier').value;
    const lang = document.getElementById('edit-contact-lang').value;
    const consentStatus = document.getElementById('edit-contact-consent').value;
    const optOutReason = document.getElementById('edit-contact-optout-reason').value.trim();
    const overrideChk = document.getElementById('edit-contact-consent-override');
    const customStr = document.getElementById('edit-contact-custom-fields').value.trim();

    if (!name || !phone) {
      this.showToast('Name and phone number are required', 'error');
      return;
    }

    // Strict Opt-Out Safety Check
    if (this.editingContactInitialConsent === 'opted_out' && consentStatus === 'opted_in') {
      if (!overrideChk || !overrideChk.checked) {
        this.showToast('Explicit consent override confirmation is required to re-opt in a previously opted-out contact.', 'error');
        return;
      }
    }

    let customFields = null;
    if (customStr) {
      try {
        customFields = JSON.parse(customStr);
        if (typeof customFields !== 'object' || Array.isArray(customFields)) {
          throw new Error('Custom fields must be a JSON object');
        }
      } catch (e) {
        this.showToast('Invalid JSON format for custom fields: ' + e.message, 'error');
        return;
      }
    }

    const payload = {
      name,
      phone,
      group_name: groupName,
      customer_tier: tier,
      language: lang,
      consent_status: consentStatus,
      opt_out_reason: consentStatus === 'opted_out' ? optOutReason : null,
      consent_override: overrideChk ? overrideChk.checked : false,
      custom_fields: customFields
    };

    try {
      await this.api(`/api/contacts/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      this.closeModal('modal-edit-contact');
      this.showToast('Contact updated successfully', 'success');
      await this.loadContacts();
    } catch (e) {
      this.showToast(e.message || 'Failed to update contact', 'error');
    }
  }

  // --- Audience Group Management ---
  async openManageGroupsModal() {
    try {
      const groups = await this.api('/api/contacts/groups');
      this.availableGroups = groups || [];
      const tbody = document.getElementById('manage-groups-table-body');
      if (tbody) {
        tbody.innerHTML = groups.map(g => {
          const isDefault = g.name.toLowerCase() === 'default';
          return `
            <tr>
              <td><strong>${g.name}</strong></td>
              <td><span class="badge badge-neutral">${g.contact_count} contacts</span></td>
              <td style="text-align: right;">
                <div style="display: inline-flex; gap: 0.25rem;">
                  <button class="btn btn-subtle btn-sm" onclick="app.startRenameGroup('${g.name}')">Rename</button>
                  ${isDefault ? '' : `<button class="btn btn-subtle btn-sm text-danger" onclick="app.startDeleteGroup('${g.name}')" style="color: var(--danger);">Delete</button>`}
                </div>
              </td>
            </tr>
          `;
        }).join('');
      }

      document.getElementById('mg-rename-box').style.display = 'none';
      document.getElementById('mg-delete-box').style.display = 'none';
      this.openModal('modal-manage-groups');
    } catch (e) {
      this.showToast('Failed to load groups: ' + e.message, 'error');
    }
  }

  async createGroupFromManage() {
    const input = document.getElementById('mg-new-group-name');
    const name = input ? input.value.trim() : '';
    if (!name) {
      this.showToast('Please enter a group name', 'error');
      return;
    }
    try {
      await this.api('/api/contacts/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description: '' })
      });
      input.value = '';
      this.showToast(`Group '${name}' created`, 'success');
      await this.openManageGroupsModal();
      await this.loadContacts();
    } catch (e) {
      this.showToast(e.message || 'Failed to create group', 'error');
    }
  }

  startRenameGroup(oldName) {
    document.getElementById('mg-rename-old-name').value = oldName;
    document.getElementById('mg-rename-new-name').value = oldName;
    document.getElementById('mg-rename-label').textContent = `Rename Group '${oldName}'`;
    document.getElementById('mg-rename-box').style.display = 'block';
    document.getElementById('mg-delete-box').style.display = 'none';
  }

  async confirmRenameGroup() {
    const oldName = document.getElementById('mg-rename-old-name').value;
    const newName = document.getElementById('mg-rename-new-name').value.trim();
    if (!newName) {
      this.showToast('New group name cannot be empty', 'error');
      return;
    }
    try {
      const res = await this.api(`/api/contacts/groups/${encodeURIComponent(oldName)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_name: newName })
      });
      this.showToast(res.message || `Renamed '${oldName}' to '${newName}'`, 'success');
      document.getElementById('mg-rename-box').style.display = 'none';
      await this.openManageGroupsModal();
      await this.loadContacts();
    } catch (e) {
      this.showToast(e.message || 'Failed to rename group', 'error');
    }
  }

  startDeleteGroup(groupName) {
    document.getElementById('mg-delete-target-group').value = groupName;
    document.getElementById('mg-delete-title').textContent = `Delete Group: ${groupName}`;
    const fallbackSelect = document.getElementById('mg-delete-fallback-select');
    if (fallbackSelect) {
      const otherGroups = (this.availableGroups || []).filter(g => g.name !== groupName);
      fallbackSelect.innerHTML = otherGroups.map(g => `<option value="${g.name}">${g.name}</option>`).join('');
      if (otherGroups.some(g => g.name.toLowerCase() === 'default')) {
        fallbackSelect.value = 'Default';
      }
    }
    document.getElementById('mg-delete-box').style.display = 'block';
    document.getElementById('mg-rename-box').style.display = 'none';
  }

  async confirmDeleteGroupWithMigration() {
    const targetGroup = document.getElementById('mg-delete-target-group').value;
    const fallbackSelect = document.getElementById('mg-delete-fallback-select');
    const fallbackGroup = fallbackSelect ? fallbackSelect.value : 'Default';

    try {
      const res = await this.api(`/api/contacts/groups/${encodeURIComponent(targetGroup)}?fallback_group=${encodeURIComponent(fallbackGroup)}`, {
        method: 'DELETE'
      });
      this.showToast(res.message || `Group '${targetGroup}' deleted. Contacts moved to '${fallbackGroup}'.`, 'success');
      document.getElementById('mg-delete-box').style.display = 'none';
      await this.openManageGroupsModal();
      await this.loadContacts();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to delete group', 'error');
    }
  }

  async loadSuppressionContacts(container) {
    try {
      const res = await this.api('/api/contacts/suppression?limit=100');
      const countLabel = document.getElementById('contacts-count-label');
      if (countLabel) countLabel.textContent = `${res.total} blocked / opted-out number${res.total === 1 ? '' : 's'}`;

      if (!res.items || res.items.length === 0) {
        container.innerHTML = `
          <div class="empty-state">
            <div class="empty-title">No blocked numbers</div>
            <div class="empty-description">Numbers on the suppression list are automatically excluded from campaigns.</div>
          </div>
        `;
        return;
      }

      container.innerHTML = `
        <div class="table-container" style="border: none; border-radius: 0;">
          <table>
            <thead>
              <tr>
                <th>Blocked Phone Number</th>
                <th>Reason</th>
                <th>Date Blocked</th>
                <th style="text-align: right;">Action</th>
              </tr>
            </thead>
            <tbody>
              ${res.items.map(item => `
                <tr>
                  <td><span style="font-family: var(--font-mono); font-size: 0.78rem;">+${item.phone}</span></td>
                  <td>${item.reason || 'Requested opt-out'}</td>
                  <td style="color: var(--text-muted); font-size: 0.78rem;">${(item.created_at || '').slice(0, 16).replace('T', ' ')}</td>
                  <td style="text-align: right;">
                    <button class="btn btn-secondary btn-sm" onclick="app.removeSuppression(${item.id})">Unblock</button>
                  </td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    } catch (e) {}
  }

  onContactsSearch() {
    clearTimeout(this.searchTimer);
    this.searchTimer = setTimeout(() => this.loadContacts(), 300);
  }

  onContactsFilterChange() {
    this.loadContacts();
  }

  async toggleConsent(id, currentStatus) {
    const nextStatus = currentStatus === 'opted_out' ? 'opted_in' : 'opted_out';
    const reason = nextStatus === 'opted_out' ? prompt('Reason for opt-out:', 'Customer requested STOP') : '';
    if (nextStatus === 'opted_out' && reason === null) return;

    try {
      await this.api(`/api/contacts/${id}/consent`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ consent_status: nextStatus, opt_out_reason: reason || '' })
      });
      this.showToast(`Contact consent set to ${nextStatus}`, 'success');
      this.loadContacts();
    } catch (e) {}
  }

  async deleteContact(id) {
    const ok = await this.confirmDialog({
      title: 'Delete Contact',
      message: 'Are you sure you want to delete this contact?',
      details: 'This contact will be permanently removed from your address book.',
      confirmText: 'Delete Contact',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;
    try {
      await this.api(`/api/contacts/${id}`, { method: 'DELETE' });
      this.showToast('Contact deleted', 'success');
      this.loadContacts();
    } catch (e) {}
  }

  async removeSuppression(id) {
    try {
      await this.api(`/api/contacts/suppression/${id}`, { method: 'DELETE' });
      this.showToast('Number unblocked', 'success');
      this.loadContacts();
    } catch (e) {}
  }

  exportContactsCSV() {
    window.location.href = '/api/contacts/export';
  }

  exportContacts() {
    this.exportContactsCSV();
  }

  initDropzones() {
    // 1. Contacts Import Dropzone
    const importDropzone = document.getElementById('import-dropzone');
    if (importDropzone) {
      ['dragenter', 'dragover'].forEach(evt => {
        importDropzone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          importDropzone.classList.add('dragover');
        });
      });
      ['dragleave', 'drop'].forEach(evt => {
        importDropzone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          importDropzone.classList.remove('dragover');
        });
      });
      importDropzone.addEventListener('drop', e => {
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          const fileInput = document.getElementById('import-file-input');
          fileInput.files = e.dataTransfer.files;
          this.onImportFileChosen();
        }
      });
    }

    // 2. Message Attachment Dropzone
    const mediaDropzone = document.getElementById('msg-media-dropzone');
    if (mediaDropzone) {
      ['dragenter', 'dragover'].forEach(evt => {
        mediaDropzone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          mediaDropzone.classList.add('drag-active');
        });
      });
      ['dragleave', 'drop'].forEach(evt => {
        mediaDropzone.addEventListener(evt, e => {
          e.preventDefault();
          e.stopPropagation();
          mediaDropzone.classList.remove('drag-active');
        });
      });
      mediaDropzone.addEventListener('drop', e => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
          this.onMediaFileSelected(e.dataTransfer.files[0]);
        }
      });
    }
  }

  onImportFileChosen() {
    const fileInput = document.getElementById('import-file-input');
    const selectedCard = document.getElementById('import-file-selected');
    const nameEl = document.getElementById('import-chosen-filename');
    const sizeEl = document.getElementById('import-chosen-filesize');
    if (fileInput && fileInput.files && fileInput.files.length > 0) {
      const f = fileInput.files[0];
      if (nameEl) nameEl.textContent = f.name;
      if (sizeEl) sizeEl.textContent = `${(f.size / 1024).toFixed(1)} KB`;
      if (selectedCard) selectedCard.style.display = 'flex';
    } else {
      if (selectedCard) selectedCard.style.display = 'none';
    }
  }

  // --- Import Modal Handlers ---
  async openImportModal() {
    const groups = await this.api('/api/contacts/groups');
    const sel = document.getElementById('import-group-select');
    if (sel) {
      sel.innerHTML = groups.map(g => `<option value="${g.name}">${g.name}</option>`).join('');
    }
    document.getElementById('import-step-file').style.display = 'block';
    document.getElementById('import-step-map').style.display = 'none';
    document.getElementById('btn-confirm-import').style.display = 'none';
    const fileInput = document.getElementById('import-file-input');
    if (fileInput) fileInput.value = '';
    const selectedCard = document.getElementById('import-file-selected');
    if (selectedCard) selectedCard.style.display = 'none';
    this.openModal('modal-import');
  }

  async previewImportFile() {
    const fileInput = document.getElementById('import-file-input');
    if (!fileInput.files || fileInput.files.length === 0) {
      this.showToast('Please select a spreadsheet file (.csv or .xlsx)', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('file', fileInput.files[0]);

    try {
      const res = await fetch('/api/contacts/upload-preview', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Failed to read spreadsheet');
      }
      const data = await res.json();

      document.getElementById('import-temp-file-id').value = data.temp_file_id;
      const phoneCol = document.getElementById('import-phone-col');
      const nameCol = document.getElementById('import-name-col');

      phoneCol.innerHTML = data.columns.map(c =>
        `<option value="${c}" ${c === data.detected_mappings.phone ? 'selected' : ''}>${c}</option>`
      ).join('');

      nameCol.innerHTML = '<option value="">-- None (Default "Customer") --</option>' +
        data.columns.map(c =>
          `<option value="${c}" ${c === data.detected_mappings.name ? 'selected' : ''}>${c}</option>`
        ).join('');

      if (data.preview_stats) {
        const stats = data.preview_stats;
        const statsEl = document.getElementById('import-audit-stats-text');
        if (statsEl) {
          statsEl.innerHTML = `<strong>${stats.total} total rows</strong> · ~${stats.valid} valid numbers · ${stats.invalid} invalid/empty (will skip) · ${stats.duplicates} duplicates in file`;
        }
      }

      // Render detected columns badges
      const colTags = document.getElementById('import-columns-tags');
      if (colTags && data.columns) {
        colTags.innerHTML = data.columns.map(c => `<span class="badge badge-neutral" style="font-size: 0.72rem;">${c}</span>`).join('');
      }

      // Render sample preview table (first 3-4 rows)
      const sampleContainer = document.getElementById('import-sample-rows-container');
      if (sampleContainer && data.sample_preview && data.sample_preview.length > 0) {
        const previewCols = data.columns.slice(0, 4);
        sampleContainer.innerHTML = `
          <table style="width: 100%; border-collapse: collapse; font-size: 0.72rem;">
            <thead>
              <tr style="background: var(--surface-subtle); border-bottom: 1px solid var(--border-color);">
                ${previewCols.map(c => `<th style="padding: 0.35rem 0.5rem; text-align: left; font-weight: 600;">${c}</th>`).join('')}
              </tr>
            </thead>
            <tbody>
              ${data.sample_preview.slice(0, 3).map(row => `
                <tr style="border-bottom: 1px solid var(--border-color);">
                  ${previewCols.map(c => `<td style="padding: 0.35rem 0.5rem;">${row[c] || ''}</td>`).join('')}
                </tr>
              `).join('')}
            </tbody>
          </table>
        `;
      }

      document.getElementById('import-step-file').style.display = 'none';
      document.getElementById('import-step-map').style.display = 'block';
      document.getElementById('btn-confirm-import').style.display = 'inline-flex';
      this.showToast(`Spreadsheet read: ${data.total_rows} rows found`, 'info');
    } catch (e) {
      this.showToast(e.message, 'error');
    }
  }

  async confirmImport() {
    const consentConfirmed = document.getElementById('import-consent-confirm')?.checked;
    if (!consentConfirmed) {
      this.showToast('Please confirm that contacts have consented before importing', 'error');
      return;
    }

    const tempFileId = document.getElementById('import-temp-file-id').value;
    const groupName = document.getElementById('import-group-select').value;
    const phoneCol = document.getElementById('import-phone-col').value;
    const nameCol = document.getElementById('import-name-col').value;
    const countryCode = document.getElementById('import-country-code').value.trim();

    const formData = new FormData();
    formData.append('temp_file_id', tempFileId);
    formData.append('group_name', groupName);
    formData.append('phone_col', phoneCol);
    if (nameCol) formData.append('name_col', nameCol);
    if (countryCode) formData.append('default_country_code', countryCode);

    try {
      const res = await fetch('/api/contacts/commit-upload', { method: 'POST', body: formData });
      const data = await res.json();
      this.closeModal('modal-import');
      this.showToast(`Imported ${data.inserted} contacts successfully`, 'success');
      this.loadContacts();
      this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message, 'error');
    }
  }

  // --- Quick Paste Modal Handlers ---
  async openPasteModal() {
    const groups = await this.api('/api/contacts/groups');
    const sel = document.getElementById('paste-group-select');
    if (sel) {
      sel.innerHTML = groups.map(g => `<option value="${g.name}">${g.name}</option>`).join('');
    }
    document.getElementById('paste-text-input').value = '';
    this.openModal('modal-paste');
  }

  async confirmPasteContacts() {
    const groupName = document.getElementById('paste-group-select').value;
    const text = document.getElementById('paste-text-input').value.trim();
    if (!text) {
      this.showToast('Please paste at least one contact line', 'error');
      return;
    }

    const lines = text.split('\n').map(l => l.trim()).filter(Boolean);
    let added = 0;
    for (const line of lines) {
      const parts = line.split(/[,;\t]/);
      const phone = parts[0].trim();
      const name = parts.length > 1 ? parts[1].trim() : 'Customer';
      try {
        await this.api('/api/contacts', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, phone, group_name: groupName, consent_status: 'opted_in' })
        });
        added++;
      } catch (e) {}
    }

    this.closeModal('modal-paste');
    this.showToast(`Added ${added} contacts to '${groupName}'`, 'success');
    this.loadContacts();
    this.loadDashboardData();
  }

  // --- New Group Modal ---
  openNewGroupModal() {
    document.getElementById('new-group-name').value = '';
    document.getElementById('new-group-desc').value = '';
    this.openModal('modal-group');
  }

  async confirmCreateGroup() {
    const name = document.getElementById('new-group-name').value.trim();
    const desc = document.getElementById('new-group-desc').value.trim();
    if (!name) {
      this.showToast('Please enter a group name', 'error');
      return;
    }

    try {
      await this.api('/api/contacts/groups', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, description: desc })
      });
      this.closeModal('modal-group');
      this.showToast(`Group '${name}' created`, 'success');
      this.loadContacts();
    } catch (e) {}
  }

  // ==========================================================================
  // SECTION 3: MESSAGES, REAL ASSET LIBRARY & CONTENT COLLECTIONS
  // ==========================================================================
  switchMessagesSubView(view) {
    this.currentMessagesSubView = view;
    const btnSets = document.getElementById('subnav-msg-sets');
    const btnLib = document.getElementById('subnav-msg-library');
    const btnComp = document.getElementById('subnav-msg-composer');
    const viewSets = document.getElementById('msg-subview-sets');
    const viewLib = document.getElementById('msg-subview-library');
    const viewComp = document.getElementById('msg-subview-composer');
    const setsTopActions = document.getElementById('sets-top-actions');
    const libraryTopActions = document.getElementById('library-top-actions');

    if (btnSets) btnSets.classList.toggle('active', view === 'sets');
    if (btnLib) btnLib.classList.toggle('active', view === 'library');
    if (btnComp) btnComp.classList.toggle('active', view === 'composer');

    if (viewSets) viewSets.style.display = (view === 'sets') ? 'block' : 'none';
    if (viewLib) viewLib.style.display = (view === 'library') ? 'block' : 'none';
    if (viewComp) viewComp.style.display = (view === 'composer') ? 'block' : 'none';

    if (setsTopActions) setsTopActions.style.display = (view === 'sets') ? 'flex' : 'none';
    if (libraryTopActions) libraryTopActions.style.display = (view === 'library') ? 'flex' : 'none';

    if (view === 'sets') {
      this.loadContentSets();
    } else if (view === 'library') {
      this.loadLibraryAssets('all');
      this.loadLibraryCollections();
    }
  }

  // ==========================================================================
  // CONTENT SETS BUILDER (SPLIT WIREFRAME VIEW)
  // ==========================================================================

  async loadContentSets() {
    try {
      const [tSets, mSets] = await Promise.all([
        this.api('/api/sets?type=text', { silent: true }).catch(() => []),
        this.api('/api/sets?type=media', { silent: true }).catch(() => [])
      ]);
      this.textSets = tSets || [];
      this.mediaSets = mSets || [];

      // Populate Text Sets Dropdown
      const tSel = document.getElementById('text-set-select');
      if (tSel) {
        if (this.textSets.length === 0) {
          tSel.innerHTML = '<option value="">No Text Sets (Create one)</option>';
        } else {
          tSel.innerHTML = this.textSets.map(s => `
            <option value="${s.id}" ${s.id === this.activeTextSetId ? 'selected' : ''}>
              ${this.escapeHtml(s.name)} (${s.items_count || 0})
            </option>
          `).join('');
          if (!this.activeTextSetId || !this.textSets.some(s => s.id === this.activeTextSetId)) {
            this.activeTextSetId = this.textSets[0].id;
          }
          tSel.value = this.activeTextSetId;
        }
      }

      // Populate Media Sets Dropdown
      const mSel = document.getElementById('media-set-select');
      if (mSel) {
        if (this.mediaSets.length === 0) {
          mSel.innerHTML = '<option value="">No Media Sets (Create one)</option>';
        } else {
          mSel.innerHTML = this.mediaSets.map(s => `
            <option value="${s.id}" ${s.id === this.activeMediaSetId ? 'selected' : ''}>
              ${this.escapeHtml(s.name)} (${s.items_count || 0})
            </option>
          `).join('');
          if (!this.activeMediaSetId || !this.mediaSets.some(s => s.id === this.activeMediaSetId)) {
            this.activeMediaSetId = this.mediaSets[0].id;
          }
          mSel.value = this.activeMediaSetId;
        }
      }

      // Update Campaign tab dropdowns if elements exist
      const campTSel = document.getElementById('camp-text-set-select');
      if (campTSel) {
        campTSel.innerHTML = this.textSets.map(s => `
          <option value="${s.id}">${this.escapeHtml(s.name)} (${s.items_count || 0} messages)</option>
        `).join('');
      }
      const campMSel = document.getElementById('camp-media-set-select');
      if (campMSel) {
        campMSel.innerHTML = '<option value="">-- No media set (Text only) --</option>' +
          this.mediaSets.map(s => `
            <option value="${s.id}">${this.escapeHtml(s.name)} (${s.items_count || 0} assets)</option>
          `).join('');
      }

      await Promise.all([
        this.loadActiveTextSet(),
        this.loadActiveMediaSet()
      ]);
    } catch (e) {
      console.error('Failed to load content sets:', e);
    }
  }

  async onTextSetSelected(idVal) {
    const id = parseInt(idVal);
    if (!id) return;
    this.activeTextSetId = id;
    this.selectedTextSetItemIds.clear();
    await this.loadActiveTextSet();
  }

  async onMediaSetSelected(idVal) {
    const id = parseInt(idVal);
    if (!id) return;
    this.activeMediaSetId = id;
    this.selectedMediaSetItemIds.clear();
    await this.loadActiveMediaSet();
  }

  async loadActiveTextSet() {
    const list = document.getElementById('text-set-items-list');
    const badge = document.getElementById('text-set-stats-badge');
    if (!list) return;

    if (!this.activeTextSetId) {
      list.innerHTML = `
        <div class="empty-state" style="padding: 2rem 1rem;">
          <div class="empty-title">No Text Set Selected</div>
          <div class="empty-description">Create a new Text Set or select one from the dropdown.</div>
          <button type="button" class="btn btn-primary btn-sm" onclick="app.openNewSetModal('text')">+ Create Text Set</button>
        </div>
      `;
      if (badge) badge.textContent = '0 messages';
      this.updateSetBulkBar('text');
      return;
    }

    try {
      const set = await this.api(`/api/sets/${this.activeTextSetId}`);
      this.activeTextSet = set;
      const items = set.items || [];

      const includedCount = items.filter(i => i.is_included).length;
      const excludedCount = items.length - includedCount;
      if (badge) {
        badge.textContent = `${items.length} message${items.length === 1 ? '' : 's'} (${includedCount} included, ${excludedCount} excluded)`;
      }

      if (items.length === 0) {
        list.innerHTML = `
          <div class="empty-state" style="padding: 2rem 1rem;">
            <div class="empty-title">No messages in this set</div>
            <div class="empty-description">Type a message below or import from CSV/JSON to populate this set.</div>
          </div>
        `;
        this.updateSetBulkBar('text');
        return;
      }

      list.innerHTML = items.map((item, idx) => {
        const isSelected = this.selectedTextSetItemIds.has(item.id);
        const isIncluded = !!item.is_included;
        const snippet = item.content || '';
        const highlighted = this.escapeHtml(snippet).replace(/\{([a-zA-Z0-9_.|]+)\}/g, '<span class="variable-token-chip">{$1}</span>');

        return `
          <div class="text-set-row ${isSelected ? 'selected' : ''} ${!isIncluded ? 'excluded' : ''}" id="text-set-item-${item.id}">
            <input type="checkbox" class="set-item-checkbox" data-id="${item.id}" ${isSelected ? 'checked' : ''} onchange="app.toggleSelectSetItem('text', ${item.id}, this.checked)" style="cursor: pointer; width: 16px; height: 16px; accent-color: var(--primary);">
            
            <div class="text-set-content-box">
              <div class="text-set-title">
                <span>${this.escapeHtml(item.title || `Message ${idx + 1}`)}</span>
                <span class="${isIncluded ? 'badge-included' : 'badge-excluded'}">
                  ${isIncluded ? '✓ Included' : '✕ Excluded'}
                </span>
              </div>
              <div class="text-set-snippet" title="${this.escapeHtml(snippet)}">
                ${highlighted}
              </div>
            </div>

            <div class="text-set-actions">
              <button type="button" class="btn btn-secondary btn-xs" onclick="app.toggleSetItemIncluded('text', ${item.id})" title="${isIncluded ? 'Temporarily exclude from campaign' : 'Include in campaign'}">
                ${isIncluded ? 'Hide' : 'Include'}
              </button>
              <button type="button" class="btn btn-subtle btn-xs" onclick="app.openTextItemPreviewModal(${item.id})" title="View simulated message with real contact tags">
                View
              </button>
              <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.removeSetItem('text', ${item.id})" title="Remove from this set">
                ✕
              </button>
            </div>
          </div>
        `;
      }).join('');

      this.updateSetBulkBar('text');
    } catch (e) {
      console.error('Failed to load active text set:', e);
    }
  }

  async loadActiveMediaSet() {
    const grid = document.getElementById('media-set-items-grid');
    const badge = document.getElementById('media-set-stats-badge');
    if (!grid) return;

    if (!this.activeMediaSetId) {
      grid.innerHTML = `
        <div class="empty-state" style="padding: 2rem 1rem;">
          <div class="empty-title">No Media Set Selected</div>
          <div class="empty-description">Create a new Media Set or select one from the dropdown.</div>
          <button type="button" class="btn btn-primary btn-sm" onclick="app.openNewSetModal('media')">+ Create Media Set</button>
        </div>
      `;
      if (badge) badge.textContent = '0 assets';
      this.updateSetBulkBar('media');
      return;
    }

    try {
      const set = await this.api(`/api/sets/${this.activeMediaSetId}`);
      this.activeMediaSet = set;
      const items = set.items || [];

      const includedCount = items.filter(i => i.is_included).length;
      const excludedCount = items.length - includedCount;
      if (badge) {
        badge.textContent = `${items.length} asset${items.length === 1 ? '' : 's'} (${includedCount} included, ${excludedCount} excluded)`;
      }

      if (items.length === 0) {
        grid.innerHTML = `
          <div class="empty-state" style="padding: 2rem 1rem;">
            <div class="empty-title">No assets in this set</div>
            <div class="empty-description">Upload images, PDFs, or videos, or pick from your Asset Library.</div>
            <div style="display: flex; gap: 0.5rem; justify-content: center; margin-top: 0.5rem;">
              <button type="button" class="btn btn-primary btn-sm" onclick="document.getElementById('media-set-file-upload-input').click()">Upload File</button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="app.openAddMediaToSetModal()">Browse Library</button>
            </div>
          </div>
        `;
        this.updateSetBulkBar('media');
        return;
      }

      grid.innerHTML = `
        <div class="media-set-grid">
          ${items.map(item => {
            const isSelected = this.selectedMediaSetItemIds.has(item.id);
            const isIncluded = !!item.is_included;
            const sizeStr = item.file_size_formatted || (item.file_size ? `${(item.file_size / 1024).toFixed(1)} KB` : '0 B');
            const mime = item.mime_type || item.media_type || 'image/jpeg';
            const isImg = mime.startsWith('image/');
            const thumbUrl = item.asset_id ? `/api/media/${item.asset_id}/file` : (item.file_path ? `/api/media/file/${item.filename}` : '');

            return `
              <div class="media-set-card-item ${isSelected ? 'selected' : ''} ${!isIncluded ? 'excluded' : ''}" id="media-set-item-${item.id}">
                <div class="media-set-card-header">
                  <input type="checkbox" class="set-item-checkbox" data-id="${item.id}" ${isSelected ? 'checked' : ''} onchange="app.toggleSelectSetItem('media', ${item.id}, this.checked)" style="cursor: pointer; width: 15px; height: 15px; accent-color: var(--primary);">
                  <span class="${isIncluded ? 'badge-included' : 'badge-excluded'}" style="font-size: 0.65rem; padding: 0.1rem 0.35rem;">
                    ${isIncluded ? '✓ Included' : '✕ Excluded'}
                  </span>
                </div>

                <div class="media-set-thumb-box">
                  ${isImg && thumbUrl ? `
                    <img src="${thumbUrl}" alt="${this.escapeHtml(item.filename || item.title)}" loading="lazy" onerror="this.parentElement.innerHTML='<span style=\\'font-size:1.75rem;\\'>🖼️</span>'">
                  ` : `
                    <span style="font-size: 2rem;">${mime.includes('pdf') ? '📄' : (mime.includes('video') ? '🎬' : '📎')}</span>
                  `}
                </div>

                <div class="media-set-card-title" title="${this.escapeHtml(item.filename || item.title)}">
                  ${this.escapeHtml(item.filename || item.title)}
                </div>

                <div class="media-set-card-meta">
                  <span>${sizeStr}</span>
                  <span style="font-family: var(--font-mono); font-size: 0.65rem;">${mime.split('/')[1] || mime}</span>
                </div>

                <div class="media-set-card-actions">
                  <button type="button" class="btn btn-secondary btn-xs" onclick="app.toggleSetItemIncluded('media', ${item.id})" style="padding: 0.15rem 0.35rem; font-size: 0.7rem;">
                    ${isIncluded ? 'Hide' : 'Include'}
                  </button>
                  <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.removeSetItem('media', ${item.id})" title="Remove from set" style="padding: 0.15rem 0.35rem; font-size: 0.7rem;">
                    ✕
                  </button>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `;

      this.updateSetBulkBar('media');
    } catch (e) {
      console.error('Failed to load active media set:', e);
    }
  }

  // --- Multi-Selection & Contextual Bulk Toolbars ---

  toggleSelectSetItem(setType, itemId, checked) {
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;
    if (checked) {
      selectedSet.add(itemId);
    } else {
      selectedSet.delete(itemId);
    }

    const el = document.getElementById(`${setType}-set-item-${itemId}`);
    if (el) el.classList.toggle('selected', checked);

    this.updateSetBulkBar(setType);
  }

  toggleSelectAllSetItems(setType, checked) {
    const activeSet = (setType === 'text') ? this.activeTextSet : this.activeMediaSet;
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;
    const items = activeSet?.items || [];

    selectedSet.clear();
    if (checked) {
      items.forEach(i => selectedSet.add(i.id));
    }

    const container = document.getElementById(setType === 'text' ? 'text-set-items-list' : 'media-set-items-grid');
    if (container) {
      container.querySelectorAll('.set-item-checkbox').forEach(cb => {
        cb.checked = checked;
        const parent = cb.closest(setType === 'text' ? '.text-set-row' : '.media-set-card-item');
        if (parent) parent.classList.toggle('selected', checked);
      });
    }

    this.updateSetBulkBar(setType);
  }

  clearSetSelection(setType) {
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;
    selectedSet.clear();

    const masterChk = document.getElementById(`chk-master-${setType}-set`);
    if (masterChk) {
      masterChk.checked = false;
      masterChk.indeterminate = false;
    }

    const container = document.getElementById(setType === 'text' ? 'text-set-items-list' : 'media-set-items-grid');
    if (container) {
      container.querySelectorAll('.set-item-checkbox').forEach(cb => {
        cb.checked = false;
        const parent = cb.closest(setType === 'text' ? '.text-set-row' : '.media-set-card-item');
        if (parent) parent.classList.remove('selected');
      });
    }

    this.updateSetBulkBar(setType);
  }

  updateSetBulkBar(setType) {
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;
    const activeSet = (setType === 'text') ? this.activeTextSet : this.activeMediaSet;
    const items = activeSet?.items || [];
    const bulkBar = document.getElementById(`${setType}-set-bulk-bar`);
    const bulkCount = document.getElementById(`${setType}-set-bulk-count`);
    const masterChk = document.getElementById(`chk-master-${setType}-set`);

    const count = selectedSet.size;

    if (bulkBar) {
      bulkBar.style.display = count > 0 ? 'flex' : 'none';
    }
    if (bulkCount) {
      bulkCount.textContent = `${count} item${count === 1 ? '' : 's'} selected`;
    }

    if (masterChk) {
      if (items.length === 0 || count === 0) {
        masterChk.checked = false;
        masterChk.indeterminate = false;
      } else if (count === items.length) {
        masterChk.checked = true;
        masterChk.indeterminate = false;
      } else {
        masterChk.checked = false;
        masterChk.indeterminate = true;
      }
    }
  }

  // --- Inclusion Toggling ---

  async toggleSetItemIncluded(setType, itemId) {
    const setId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    if (!setId) return;

    try {
      const res = await this.api(`/api/sets/${setId}/items/${itemId}/toggle`, { method: 'PUT' });
      const statusLabel = res.is_included ? 'Included in Campaign' : 'Excluded (Hidden from Campaign)';
      this.showToast(`Item ${statusLabel}`, 'info');
      if (setType === 'text') {
        await this.loadActiveTextSet();
      } else {
        await this.loadActiveMediaSet();
      }
    } catch (e) {
      this.showToast(e.message || 'Failed to toggle item inclusion', 'error');
    }
  }

  async bulkToggleSetItems(setType, isIncluded) {
    const setId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;
    if (!setId || selectedSet.size === 0) {
      this.showToast('No items selected', 'warning');
      return;
    }

    try {
      const itemIds = Array.from(selectedSet);
      await this.api(`/api/sets/${setId}/items/bulk-toggle`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_ids: itemIds, is_included: isIncluded ? 1 : 0 })
      });

      const label = isIncluded ? 'included in campaign' : 'excluded from campaign';
      this.showToast(`${itemIds.length} item(s) ${label}`, 'success');
      this.clearSetSelection(setType);
      if (setType === 'text') {
        await this.loadActiveTextSet();
      } else {
        await this.loadActiveMediaSet();
      }
    } catch (e) {
      this.showToast(e.message || 'Failed to update items', 'error');
    }
  }

  // --- Inline Message Adding ---

  async addInlineMessageToActiveSet() {
    if (!this.activeTextSetId) {
      this.showToast('Please select or create a Text Set first', 'error');
      return;
    }

    const titleInput = document.getElementById('inline-msg-title');
    const contentInput = document.getElementById('inline-msg-content');
    const title = titleInput ? titleInput.value.trim() : '';
    const content = contentInput ? contentInput.value.trim() : '';

    if (!content) {
      this.showToast('Please enter message text content', 'warning');
      return;
    }

    try {
      await this.api(`/api/sets/${this.activeTextSetId}/new-message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          title: title || `Message ${(this.activeTextSet?.items?.length || 0) + 1}`,
          content: content
        })
      });

      if (titleInput) titleInput.value = '';
      if (contentInput) contentInput.value = '';
      this.showToast('Message added to Text Set', 'success');
      await this.loadActiveTextSet();
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to add message to set', 'error');
    }
  }

  insertInlineVar(token) {
    const input = document.getElementById('inline-msg-content');
    if (!input) return;
    const start = input.selectionStart || input.value.length;
    const end = input.selectionEnd || input.value.length;
    const val = input.value;
    input.value = val.substring(0, start) + token + val.substring(end);
    input.focus();
    input.selectionStart = input.selectionEnd = start + token.length;
  }

  // --- Media Set Uploading ---

  async onMediaSetFilesSelected(event) {
    const files = event.target?.files;
    if (!files || files.length === 0) return;
    if (!this.activeMediaSetId) {
      this.showToast('Please create or select a Media Set first', 'error');
      return;
    }

    this.showToast(`Uploading ${files.length} file(s)...`, 'info');
    let uploadedCount = 0;

    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name || 'Image');
      try {
        const uploadRes = await fetch('/api/media/upload', {
          method: 'POST',
          body: formData
        });
        if (uploadRes.ok) {
          const asset = await uploadRes.json();
          await this.api(`/api/sets/${this.activeMediaSetId}/items`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ asset_ids: [asset.id] })
          });
          uploadedCount++;
        }
      } catch (err) {
        console.error('Upload error:', err);
      }
    }

    event.target.value = '';
    this.showToast(`Successfully added ${uploadedCount} asset(s) to Media Set`, 'success');
    await this.loadActiveMediaSet();
    await this.loadContentSets();
  }

  // --- Set Removal & Transfers ---

  async removeSetItem(setType, itemId) {
    const setId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    if (!setId) return;

    try {
      await this.api(`/api/sets/${setId}/items`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_ids: [itemId] })
      });
      this.showToast('Item removed from set', 'info');
      if (setType === 'text') {
        this.selectedTextSetItemIds.delete(itemId);
        await this.loadActiveTextSet();
      } else {
        this.selectedMediaSetItemIds.delete(itemId);
        await this.loadActiveMediaSet();
      }
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to remove item', 'error');
    }
  }

  async bulkRemoveSetItems(setType) {
    const setId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;
    if (!setId || selectedSet.size === 0) return;

    const ok = await this.confirmDialog({
      title: 'Remove Items from Set',
      message: `Remove ${selectedSet.size} selected item(s) from this set?`,
      details: 'The items will remain available in your library and templates.',
      confirmText: 'Remove Items',
      cancelText: 'Cancel',
      isDestructive: false
    });
    if (!ok) return;

    try {
      const itemIds = Array.from(selectedSet);
      await this.api(`/api/sets/${setId}/items`, {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_ids: itemIds })
      });
      this.showToast(`Removed ${itemIds.length} item(s) from set`, 'success');
      this.clearSetSelection(setType);
      if (setType === 'text') {
        await this.loadActiveTextSet();
      } else {
        await this.loadActiveMediaSet();
      }
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to remove items', 'error');
    }
  }

  promptMoveSetItems(setType) {
    this.openMoveCopyModal(setType, 'move');
  }

  promptCopySetItems(setType) {
    this.openMoveCopyModal(setType, 'copy');
  }

  openMoveCopyModal(setType, action) {
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;
    if (selectedSet.size === 0) {
      this.showToast('Please select items first', 'warning');
      return;
    }

    const setsList = (setType === 'text') ? this.textSets : this.mediaSets;
    const currentSetId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    const targetSets = setsList.filter(s => s.id !== currentSetId);

    if (targetSets.length === 0) {
      this.showToast(`No other ${setType} sets available to ${action} items to. Create another set first.`, 'warning');
      return;
    }

    document.getElementById('move-copy-action-type').value = action;
    document.getElementById('move-copy-set-type').value = setType;
    document.getElementById('move-copy-modal-title').textContent = (action === 'move') ? 'Move Items to Set' : 'Copy Items to Set';
    document.getElementById('move-copy-modal-sub').textContent = `${action === 'move' ? 'Transfer' : 'Duplicate'} ${selectedSet.size} item(s) into another set`;
    document.getElementById('btn-confirm-move-copy').textContent = (action === 'move') ? 'Move Items' : 'Copy Items';

    const sel = document.getElementById('move-copy-target-set-select');
    if (sel) {
      sel.innerHTML = targetSets.map(s => `<option value="${s.id}">${this.escapeHtml(s.name)} (${s.items_count || 0} items)</option>`).join('');
    }

    this.openModal('modal-move-copy-set-items');
  }

  async confirmMoveCopySetItems() {
    const action = document.getElementById('move-copy-action-type').value;
    const setType = document.getElementById('move-copy-set-type').value;
    const currentSetId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    const targetSetId = parseInt(document.getElementById('move-copy-target-set-select').value);
    const selectedSet = (setType === 'text') ? this.selectedTextSetItemIds : this.selectedMediaSetItemIds;

    if (!targetSetId || selectedSet.size === 0) return;

    try {
      const itemIds = Array.from(selectedSet);
      const endpoint = action === 'move' ? `/api/sets/${currentSetId}/items/move` : `/api/sets/${currentSetId}/items/copy`;
      await this.api(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ item_ids: itemIds, target_set_id: targetSetId })
      });

      this.closeModal('modal-move-copy-set-items');
      this.showToast(`Successfully ${action === 'move' ? 'moved' : 'copied'} ${itemIds.length} item(s)`, 'success');
      this.clearSetSelection(setType);
      if (setType === 'text') {
        await this.loadActiveTextSet();
      } else {
        await this.loadActiveMediaSet();
      }
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Operation failed', 'error');
    }
  }

  // --- Set CRUD Operations ---

  openNewSetModal(type = 'text') {
    document.getElementById('set-editor-id').value = '';
    document.getElementById('set-editor-type').value = type;
    document.getElementById('set-editor-title').textContent = `New ${type === 'text' ? 'Text' : 'Media'} Set`;
    document.getElementById('set-editor-name').value = '';
    document.getElementById('set-editor-desc').value = '';
    document.getElementById('set-editor-mode').value = 'random';
    this.openModal('modal-set-editor');
  }

  async saveSetFromEditor() {
    const id = document.getElementById('set-editor-id').value;
    const setType = document.getElementById('set-editor-type').value || 'text';
    const name = document.getElementById('set-editor-name').value.trim();
    const desc = document.getElementById('set-editor-desc').value.trim();
    const mode = document.getElementById('set-editor-mode').value || 'random';

    if (!name) {
      this.showToast('Please enter a set name', 'warning');
      return;
    }

    try {
      if (id) {
        await this.api(`/api/sets/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, description: desc, allocation_mode: mode })
        });
        this.showToast('Set updated', 'success');
      } else {
        const created = await this.api('/api/sets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, set_type: setType, description: desc, allocation_mode: mode })
        });
        this.showToast(`Created new ${setType} set`, 'success');
        if (setType === 'text') {
          this.activeTextSetId = created.id;
        } else {
          this.activeMediaSetId = created.id;
        }
      }

      this.closeModal('modal-set-editor');
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to save set', 'error');
    }
  }

  async duplicateActiveSet(setType) {
    const setId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    if (!setId) return;

    try {
      const duplicated = await this.api(`/api/sets/${setId}/duplicate`, { method: 'POST' });
      this.showToast(`Duplicated as "${duplicated.name}"`, 'success');
      if (setType === 'text') {
        this.activeTextSetId = duplicated.id;
      } else {
        this.activeMediaSetId = duplicated.id;
      }
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to duplicate set', 'error');
    }
  }

  async deleteActiveSet(setType) {
    const setId = (setType === 'text') ? this.activeTextSetId : this.activeMediaSetId;
    const activeSet = (setType === 'text') ? this.activeTextSet : this.activeMediaSet;
    if (!setId) return;

    const ok = await this.confirmDialog({
      title: 'Delete Content Set',
      message: `Delete set "${activeSet?.name || 'this set'}"?`,
      details: 'Assets and templates in your library will NOT be deleted.',
      confirmText: 'Delete Set',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    try {
      await this.api(`/api/sets/${setId}`, { method: 'DELETE' });
      this.showToast('Set deleted', 'info');
      if (setType === 'text') {
        this.activeTextSetId = null;
      } else {
        this.activeMediaSetId = null;
      }
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to delete set', 'error');
    }
  }

  // --- Add From Library Modals ---

  async openAddMediaToSetModal() {
    if (!this.activeMediaSetId) {
      this.showToast('Please select a Media Set first', 'warning');
      return;
    }
    const pickerList = document.getElementById('add-media-picker-list');
    if (!pickerList) return;

    try {
      const allAssets = await this.api('/api/media', { silent: true }).catch(() => []);
      const currentItemAssetIds = new Set((this.activeMediaSet?.items || []).map(i => i.asset_id));
      const available = allAssets.filter(a => a.is_available && !currentItemAssetIds.has(a.id));

      if (available.length === 0) {
        pickerList.innerHTML = `
          <div class="empty-state" style="padding: 1.5rem;">
            <div class="empty-title">All library assets are already in this set</div>
            <div class="empty-description">Upload new assets to add them.</div>
          </div>
        `;
      } else {
        pickerList.innerHTML = `
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 0.5rem;">
            ${available.map(a => `
              <label style="border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.5rem; display: flex; flex-direction: column; gap: 0.35rem; cursor: pointer; background: var(--bg-surface);">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <input type="checkbox" class="add-media-picker-cb" value="${a.id}" onchange="app.updateAddMediaPickerCount()" style="accent-color: var(--primary);">
                  <span style="font-size: 0.65rem; color: var(--text-muted);">${a.file_size_formatted || ''}</span>
                </div>
                <div style="font-size: 0.75rem; font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
                  ${this.escapeHtml(a.filename || a.title)}
                </div>
                <div style="font-size: 0.68rem; color: var(--text-muted);">${a.media_type || ''}</div>
              </label>
            `).join('')}
          </div>
        `;
      }

      this.updateAddMediaPickerCount();
      this.openModal('modal-add-media-to-set');
    } catch (e) {
      this.showToast('Failed to load media library', 'error');
    }
  }

  updateAddMediaPickerCount() {
    const checked = document.querySelectorAll('.add-media-picker-cb:checked');
    const badge = document.getElementById('add-media-picker-selected-count');
    if (badge) badge.textContent = `${checked.length} selected`;
  }

  async confirmAddMediaToSet() {
    const checked = Array.from(document.querySelectorAll('.add-media-picker-cb:checked')).map(cb => parseInt(cb.value));
    if (checked.length === 0) {
      this.showToast('Please select at least one asset', 'warning');
      return;
    }

    try {
      await this.api(`/api/sets/${this.activeMediaSetId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_ids: checked })
      });
      this.closeModal('modal-add-media-to-set');
      this.showToast(`Added ${checked.length} asset(s) to Media Set`, 'success');
      await this.loadActiveMediaSet();
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to add assets', 'error');
    }
  }

  async openAddTemplatesToSetModal() {
    if (!this.activeTextSetId) {
      this.showToast('Please select a Text Set first', 'warning');
      return;
    }
    const pickerList = document.getElementById('add-templates-picker-list');
    if (!pickerList) return;

    try {
      const templates = await this.api('/api/templates', { silent: true }).catch(() => []);
      const currentItemTemplateIds = new Set((this.activeTextSet?.items || []).map(i => i.template_id));
      const available = templates.filter(t => !currentItemTemplateIds.has(t.id));

      if (available.length === 0) {
        pickerList.innerHTML = `
          <div class="empty-state" style="padding: 1.5rem;">
            <div class="empty-title">All saved templates are already in this set</div>
            <div class="empty-description">Create new templates in the composer or use the inline input below.</div>
          </div>
        `;
      } else {
        pickerList.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 0.5rem;">
            ${available.map(t => `
              <label style="border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.6rem 0.75rem; display: flex; align-items: center; gap: 0.75rem; cursor: pointer; background: var(--bg-surface);">
                <input type="checkbox" class="add-templates-picker-cb" value="${t.id}" onchange="app.updateAddTemplatesPickerCount()" style="accent-color: var(--primary);">
                <div style="flex: 1; min-width: 0;">
                  <div style="font-size: 0.8125rem; font-weight: 600;">${this.escapeHtml(t.name)}</div>
                  <div style="font-size: 0.75rem; color: var(--text-muted); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                    ${this.escapeHtml(t.content || '')}
                  </div>
                </div>
              </label>
            `).join('')}
          </div>
        `;
      }

      this.updateAddTemplatesPickerCount();
      this.openModal('modal-add-templates-to-set');
    } catch (e) {
      this.showToast('Failed to load templates library', 'error');
    }
  }

  updateAddTemplatesPickerCount() {
    const checked = document.querySelectorAll('.add-templates-picker-cb:checked');
    const badge = document.getElementById('add-templates-picker-selected-count');
    if (badge) badge.textContent = `${checked.length} selected`;
  }

  async confirmAddTemplatesToSet() {
    const checked = Array.from(document.querySelectorAll('.add-templates-picker-cb:checked')).map(cb => parseInt(cb.value));
    if (checked.length === 0) {
      this.showToast('Please select at least one template', 'warning');
      return;
    }

    try {
      await this.api(`/api/sets/${this.activeTextSetId}/items`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ template_ids: checked })
      });
      this.closeModal('modal-add-templates-to-set');
      this.showToast(`Added ${checked.length} message(s) to Text Set`, 'success');
      await this.loadActiveTextSet();
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Failed to add messages', 'error');
    }
  }

  // --- Searchable Variables & Shortcuts Help Modal ---

  async openVariablesHelpModal() {
    const list = document.getElementById('var-help-list');
    if (!list) return;

    try {
      if (!this.cachedVariablesInfo) {
        this.cachedVariablesInfo = await this.api('/api/templates/variables-info', { silent: true }).catch(() => null);
      }

      const standardVars = [
        { token: '{name}', desc: 'Recipient full name (from Contact name)', sample: 'Gaurav' },
        { token: '{first_name}', desc: 'Recipient first name only (split by space)', sample: 'Gaurav' },
        { token: '{phone}', desc: 'Normalized WhatsApp phone number', sample: '+919876543210' },
        { token: '{group}', desc: 'Assigned contact group / audience tag', sample: 'VIP' },
        { token: '{language}', desc: 'Contact preferred language code', sample: 'en' },
        { token: '{tier}', desc: 'Customer loyalty or account tier', sample: 'Gold' },
        { token: '{custom.attribute}', desc: 'Any custom property mapped during CSV import', sample: 'Premium' }
      ];

      this.renderedVariablesList = standardVars;
      this.filterVariablesHelp('');
      this.openModal('modal-variables-help');
    } catch (e) {
      this.openModal('modal-variables-help');
    }
  }

  filterVariablesHelp(query) {
    const list = document.getElementById('var-help-list');
    if (!list || !this.renderedVariablesList) return;

    const q = (query || '').toLowerCase().trim();
    const filtered = this.renderedVariablesList.filter(v => 
      !q || v.token.toLowerCase().includes(q) || v.desc.toLowerCase().includes(q) || v.sample.toLowerCase().includes(q)
    );

    if (filtered.length === 0) {
      list.innerHTML = '<div style="font-size: 0.78rem; color: var(--text-muted); padding: 0.5rem;">No matching variables found</div>';
      return;
    }

    list.innerHTML = filtered.map(v => `
      <div class="var-help-item">
        <div style="flex: 1; min-width: 0;">
          <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.15rem;">
            <code class="variable-token-chip" style="font-size: 0.78rem;">${v.token}</code>
            <span style="font-size: 0.72rem; color: var(--text-muted);">Sample: "${v.sample}"</span>
          </div>
          <div style="font-size: 0.75rem; color: var(--text-secondary);">${v.desc}</div>
        </div>
        <div style="display: flex; gap: 0.25rem;">
          <button type="button" class="btn btn-secondary btn-xs" onclick="app.insertVar('${v.token}')">Insert</button>
          <button type="button" class="btn btn-subtle btn-xs" onclick="navigator.clipboard.writeText('${v.token}'); app.showToast('Copied ${v.token}', 'info');">Copy</button>
        </div>
      </div>
    `).join('');
  }

  insertVar(token) {
    const composerInput = document.getElementById('msg-content-input');
    const inlineInput = document.getElementById('inline-msg-content');
    const target = (this.currentMessagesSubView === 'composer' || (composerInput && composerInput.offsetParent !== null)) ? composerInput : inlineInput;

    if (target) {
      const start = target.selectionStart || target.value.length;
      const end = target.selectionEnd || target.value.length;
      const val = target.value;
      target.value = val.substring(0, start) + token + val.substring(end);
      target.focus();
      target.selectionStart = target.selectionEnd = start + token.length;
      if (target === composerInput) this.onMessageEditorChange();
      this.showToast(`Inserted ${token}`, 'info');
    } else {
      navigator.clipboard.writeText(token);
      this.showToast(`Copied ${token} to clipboard`, 'info');
    }
  }

  // --- Live Personalization Preview Modal ---

  async openTextItemPreviewModal(itemId) {
    const item = (this.activeTextSet?.items || []).find(i => i.id === itemId);
    if (!item) return;
    this.previewingTextItem = item;

    document.getElementById('preview-text-item-title').textContent = `Preview: ${item.title || 'Message'}`;
    document.getElementById('preview-raw-template-box').textContent = item.content || '';

    const sel = document.getElementById('preview-recipient-select');
    if (sel) {
      try {
        const contacts = await this.api('/api/contacts?limit=25', { silent: true }).catch(() => []);
        if (contacts.length === 0) {
          sel.innerHTML = '<option value="">No contacts (Using default simulation)</option>';
        } else {
          sel.innerHTML = contacts.map(c => `
            <option value="${c.id}" data-name="${this.escapeHtml(c.name)}" data-phone="${c.phone}" data-group="${this.escapeHtml(c.group_name || 'Default')}">
              ${this.escapeHtml(c.name)} (+${this.formatPhone(c.phone)}) - ${c.group_name || 'Default'}
            </option>
          `).join('');
        }
      } catch (e) {}
    }

    this.renderLiveTextItemPreview();
    this.openModal('modal-preview-text-item');
  }

  renderLiveTextItemPreview() {
    if (!this.previewingTextItem) return;
    const content = this.previewingTextItem.content || '';
    const bubble = document.getElementById('preview-interpolated-bubble');
    if (!bubble) return;

    const sel = document.getElementById('preview-recipient-select');
    const opt = sel?.selectedOptions?.[0];

    const contactName = opt?.getAttribute('data-name') || 'Gaurav';
    const contactPhone = opt?.getAttribute('data-phone') || '919876543210';
    const contactGroup = opt?.getAttribute('data-group') || 'VIP';
    const firstName = contactName.split(' ')[0] || contactName;

    let rendered = content
      .replace(/\{first_name\}/gi, firstName)
      .replace(/\{name\}/gi, contactName)
      .replace(/\{phone\}/gi, `+${contactPhone}`)
      .replace(/\{group\}/gi, contactGroup)
      .replace(/\{tier\}/gi, 'Gold')
      .replace(/\{language\}/gi, 'en');

    rendered = rendered.replace(/\{([a-zA-Z0-9_]+)\|([^}]+)\}/g, (match, p1, fallback) => {
      if (p1.toLowerCase() === 'name') return contactName || fallback;
      if (p1.toLowerCase() === 'first_name') return firstName || fallback;
      if (p1.toLowerCase() === 'phone') return contactPhone || fallback;
      return fallback;
    });

    rendered = rendered.replace(/\{([^{}]+)\|([^{}]+)\}/g, (match, a, b) => a);

    bubble.innerHTML = this.escapeHtml(rendered).replace(/\n/g, '<br>');
  }

  // --- Export & Import ---

  exportActiveTextSet(format = 'json') {
    if (!this.activeTextSetId) {
      this.showToast('Please select a Text Set first', 'warning');
      return;
    }
    const url = `/api/sets/${this.activeTextSetId}/export?format=${format}`;
    window.open(url, '_blank');
    this.showToast(`Exporting Text Set as ${format.toUpperCase()}...`, 'info');
  }

  openImportTextSetModal() {
    const sel = document.getElementById('import-text-target-set');
    if (sel) {
      sel.innerHTML = this.textSets.map(s => `
        <option value="${s.id}" ${s.id === this.activeTextSetId ? 'selected' : ''}>${this.escapeHtml(s.name)} (${s.items_count || 0} messages)</option>
      `).join('') + '<option value="new">+ Create New Set from Import</option>';
    }
    document.getElementById('import-text-paste').value = '';
    document.getElementById('import-text-file-input').value = '';
    document.getElementById('import-validation-box').style.display = 'none';
    this.openModal('modal-import-text-set');
  }

  async onImportFileChosen(event) {
    const file = event.target?.files?.[0];
    if (!file) return;

    try {
      const text = await file.text();
      const pasteArea = document.getElementById('import-text-paste');
      if (pasteArea) {
        pasteArea.value = text;
        const fmtSel = document.getElementById('import-text-format');
        if (fmtSel) {
          if (file.name.endsWith('.json')) fmtSel.value = 'json';
          else if (file.name.endsWith('.csv')) fmtSel.value = 'csv';
          else if (file.name.endsWith('.txt')) fmtSel.value = 'txt';
        }
        this.validateImportSyntax();
      }
    } catch (e) {
      this.showToast('Could not read file', 'error');
    }
  }

  validateImportSyntax() {
    const raw = document.getElementById('import-text-paste')?.value || '';
    const fmt = document.getElementById('import-text-format')?.value || 'auto';
    const box = document.getElementById('import-validation-box');
    if (!box) return;

    if (!raw.trim()) {
      box.style.display = 'none';
      return;
    }

    let parsedCount = 0;
    let detectedVars = new Set();
    let hasErrors = false;
    let errMessage = '';

    if (fmt === 'json' || (fmt === 'auto' && raw.trim().startsWith('['))) {
      try {
        const arr = JSON.parse(raw);
        if (Array.isArray(arr)) {
          parsedCount = arr.length;
          arr.forEach(item => {
            const str = (item.content || item.text || item.message || JSON.stringify(item));
            const matches = str.match(/\{([a-zA-Z0-9_.|]+)\}/g) || [];
            matches.forEach(m => detectedVars.add(m));
          });
        }
      } catch (err) {
        hasErrors = true;
        errMessage = 'Invalid JSON array: ' + err.message;
      }
    } else if (fmt === 'csv' || (fmt === 'auto' && raw.includes(','))) {
      const lines = raw.split(/\r?\n/).filter(l => l.trim().length > 0);
      parsedCount = Math.max(0, lines.length - 1);
      const matches = raw.match(/\{([a-zA-Z0-9_.|]+)\}/g) || [];
      matches.forEach(m => detectedVars.add(m));
    } else {
      const lines = raw.split(/\r?\n/).filter(l => l.trim().length > 0);
      parsedCount = lines.length;
      const matches = raw.match(/\{([a-zA-Z0-9_.|]+)\}/g) || [];
      matches.forEach(m => detectedVars.add(m));
    }

    box.style.display = 'block';
    if (hasErrors) {
      box.style.borderColor = 'var(--danger)';
      box.style.color = 'var(--danger)';
      box.innerHTML = `<strong>Syntax Error:</strong> ${this.escapeHtml(errMessage)}`;
    } else {
      box.style.borderColor = 'var(--primary)';
      box.style.color = 'var(--text-primary)';
      const varArray = Array.from(detectedVars);
      box.innerHTML = `
        <div style="font-weight: 600; color: var(--primary); margin-bottom: 0.2rem;">
          ✓ Validated: ${parsedCount} message(s) recognized
        </div>
        <div style="font-size: 0.72rem; color: var(--text-secondary);">
          Detected variables: ${varArray.length > 0 ? varArray.map(v => `<span class="variable-token-chip">${this.escapeHtml(v)}</span>`).join(' ') : 'None (static text)'}
        </div>
      `;
    }
  }

  async submitImportTextSet() {
    const raw = document.getElementById('import-text-paste')?.value || '';
    const fmt = document.getElementById('import-text-format')?.value || 'auto';
    const targetVal = document.getElementById('import-text-target-set')?.value;

    if (!raw.trim()) {
      this.showToast('Please paste content or choose a file to import', 'warning');
      return;
    }

    let targetSetId = parseInt(targetVal);
    try {
      if (targetVal === 'new' || !targetSetId) {
        const newSet = await this.api('/api/sets', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            name: `Imported Text Set (${new Date().toLocaleDateString()})`,
            set_type: 'text',
            allocation_mode: 'random'
          })
        });
        targetSetId = newSet.id;
        this.activeTextSetId = newSet.id;
      }

      const res = await this.api(`/api/sets/${targetSetId}/import`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          raw_text: raw,
          format: fmt
        })
      });

      this.closeModal('modal-import-text-set');
      this.showToast(res.message || `Imported ${res.imported_count || 0} messages successfully`, 'success');
      this.activeTextSetId = targetSetId;
      await this.loadActiveTextSet();
      await this.loadContentSets();
    } catch (e) {
      this.showToast(e.message || 'Import failed', 'error');
    }
  }

  async loadLibraryAssets(filterType = 'all') {
    const grid = document.getElementById('library-media-grid');
    const countLabel = document.getElementById('library-media-count-label');
    if (!grid) return;

    try {
      const url = filterType && filterType !== 'all' ? `/api/media?type=${filterType}` : '/api/media';
      const assets = await this.api(url);
      this.libraryAssets = assets || [];

      if (countLabel) {
        countLabel.textContent = `${assets.length} asset${assets.length === 1 ? '' : 's'} stored`;
      }

      if (assets.length === 0) {
        grid.innerHTML = `
          <div class="empty-state" style="padding: 2rem 1rem;">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
            <div class="empty-title">No media assets in library</div>
            <div class="empty-description">Upload images, PDFs, or videos. Files are SHA-256 deduplicated and stored durably.</div>
            <button type="button" class="btn btn-primary btn-sm" onclick="document.getElementById('lib-workspace-upload-input').click()">+ Upload Media</button>
          </div>
        `;
        return;
      }

      grid.innerHTML = `
        <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 0.75rem;">
          ${assets.map(a => {
            const sizeKb = (a.file_size / 1024).toFixed(1);
            const isImage = a.media_type === 'image';
            const hashShort = a.content_hash ? a.content_hash.slice(0, 8) : '';
            return `
              <div class="card" style="padding: 0.5rem; display: flex; flex-direction: column; gap: 0.35rem; border: 1px solid var(--border-color); background: var(--surface-card);">
                <div style="height: 110px; background: var(--surface-subtle); border-radius: var(--radius-sm); overflow: hidden; display: flex; align-items: center; justify-content: center; position: relative;">
                  ${isImage ? `
                    <img src="/api/media/${a.id}/file" alt="${a.original_filename}" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.src='/static/icons/file.svg'">
                  ` : `
                    <div style="font-size: 2rem; color: var(--text-muted);">📄</div>
                  `}
                  <span class="badge badge-neutral" style="position: absolute; bottom: 4px; right: 4px; font-size: 0.65rem; background: rgba(0,0,0,0.6); color: white;">
                    ${sizeKb} KB
                  </span>
                </div>
                <div style="font-size: 0.75rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${a.original_filename}">
                  ${a.original_filename || a.title}
                </div>
                <div style="display: flex; justify-content: space-between; align-items: center; font-size: 0.68rem; color: var(--text-muted);">
                  <code title="SHA-256 hash: ${a.content_hash}">${hashShort}…</code>
                  <span>${a.media_type}</span>
                </div>
                <div style="display: flex; gap: 0.25rem; margin-top: auto;">
                  <button type="button" class="btn btn-subtle btn-xs" style="flex: 1;" onclick="app.previewMediaInNewTab('/api/media/${a.id}/file')">Preview</button>
                  <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.deleteLibraryAsset(${a.id})" style="color: var(--danger);">Delete</button>
                </div>
              </div>
            `;
          }).join('')}
        </div>
      `;
    } catch (e) {}
  }

  previewMediaInNewTab(url) {
    window.open(url, '_blank');
  }

  async onLibraryUploadSelected(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);
    formData.append('title', file.name);

    try {
      const res = await this.api('/api/media/upload', {
        method: 'POST',
        body: formData
      });
      this.showToast(`Saved ${file.name} to Library (SHA-256 deduplicated)`, 'success');
      event.target.value = '';
      await this.loadLibraryAssets('all');
    } catch (e) {
      this.showToast(e.message || 'Failed to upload media', 'error');
    }
  }

  async deleteLibraryAsset(assetId) {
    const ok = await this.confirmDialog({
      title: 'Delete Media Asset',
      message: 'Are you sure you want to delete this media asset?',
      details: 'This will remove the file from your library.',
      confirmText: 'Delete Asset',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;
    try {
      await this.api(`/api/media/${assetId}`, { method: 'DELETE' });
      this.showToast('Media asset removed', 'success');
      await this.loadLibraryAssets('all');
    } catch (e) {
      this.showToast(e.message || 'Cannot delete asset (it may be used in an active campaign)', 'error');
    }
  }

  async loadLibraryCollections() {
    const list = document.getElementById('library-collections-list');
    if (!list) return;

    try {
      const collections = await this.api('/api/collections');
      this.cachedCollections = collections || [];

      if (collections.length === 0) {
        list.innerHTML = `
          <div class="empty-state" style="padding: 2rem 1rem;">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="2" y="7" width="20" height="14" rx="2" ry="2"></rect><path d="M16 21V5a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16"></path></svg>
            <div class="empty-title">No content collections yet</div>
            <div class="empty-description">Create a collection to bundle saved messages and media assets with pairing rules.</div>
            <button type="button" class="btn btn-primary btn-sm" onclick="app.openNewCollectionModal()">+ Create Collection</button>
          </div>
        `;
        return;
      }

      list.innerHTML = collections.map(c => {
        const modeBadge = c.pairing_mode === 'fixed_pair'
          ? '<span class="badge badge-primary">Fixed Pair</span>'
          : (c.pairing_mode === 'approved_combinations'
            ? '<span class="badge badge-warning">Approved Combos</span>'
            : '<span class="badge badge-neutral">Balanced Rotation</span>');

        const msgCount = (c.messages || []).length;
        const mediaCount = (c.media || []).length;

        return `
          <div class="card" style="margin-bottom: 0.75rem; padding: 0.75rem; border: 1px solid var(--border-color);">
            <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.35rem;">
              <div>
                <strong style="font-size: 0.875rem;">${c.name}</strong>
                <div style="font-size: 0.75rem; color: var(--text-muted);">${c.description || 'No description'}</div>
              </div>
              ${modeBadge}
            </div>
            <div style="display: flex; gap: 0.5rem; align-items: center; font-size: 0.75rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
              <span><strong>${msgCount}</strong> message${msgCount === 1 ? '' : 's'}</span>
              <span>•</span>
              <span><strong>${mediaCount}</strong> media asset${mediaCount === 1 ? '' : 's'}</span>
            </div>
            <div style="display: flex; justify-content: flex-end; gap: 0.35rem;">
              <button type="button" class="btn btn-secondary btn-xs" onclick="app.openNewCollectionModal(${c.id})">Edit</button>
              <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.deleteCollection(${c.id})" style="color: var(--danger);">Delete</button>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {}
  }

  async openNewCollectionModal(colId = null) {
    try {
      const templates = await this.api('/api/templates');
      const mediaList = await this.api('/api/media', { silent: true }).catch(() => []);

      const titleEl = document.getElementById('col-editor-title');
      const idInput = document.getElementById('col-editor-id');
      const nameInput = document.getElementById('col-editor-name');
      const descInput = document.getElementById('col-editor-desc');
      const modeSelect = document.getElementById('col-editor-mode');
      const msgList = document.getElementById('col-editor-messages-list');
      const medList = document.getElementById('col-editor-media-list');

      let col = null;
      if (colId) {
        col = await this.api(`/api/collections/${colId}`);
        if (titleEl) titleEl.textContent = 'Edit Content Collection';
        if (idInput) idInput.value = col.id;
        if (nameInput) nameInput.value = col.name;
        if (descInput) descInput.value = col.description || '';
        if (modeSelect) modeSelect.value = col.pairing_mode || 'fixed_pair';
      } else {
        if (titleEl) titleEl.textContent = 'New Content Collection';
        if (idInput) idInput.value = '';
        if (nameInput) nameInput.value = '';
        if (descInput) descInput.value = '';
        if (modeSelect) modeSelect.value = 'fixed_pair';
      }

      const selectedMsgIds = new Set((col?.messages || []).map(m => m.id));
      const selectedMediaIds = new Set((col?.media || []).map(m => m.id));

      if (msgList) {
        if (!templates || templates.length === 0) {
          msgList.innerHTML = '<div style="font-size: 0.75rem; color: var(--text-muted);">No saved message drafts.</div>';
        } else {
          msgList.innerHTML = templates.map(t => `
            <label style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.78rem; margin-bottom: 0.25rem; cursor: pointer;">
              <input type="checkbox" class="col-msg-chk" value="${t.id}" ${selectedMsgIds.has(t.id) ? 'checked' : ''}>
              <span>${t.name}</span>
            </label>
          `).join('');
        }
      }

      if (medList) {
        if (!mediaList || mediaList.length === 0) {
          medList.innerHTML = '<div style="font-size: 0.75rem; color: var(--text-muted);">No media assets in library.</div>';
        } else {
          medList.innerHTML = mediaList.filter(m => m.is_available).map(m => `
            <label style="display: flex; align-items: center; gap: 0.4rem; font-size: 0.78rem; margin-bottom: 0.25rem; cursor: pointer;">
              <input type="checkbox" class="col-med-chk" value="${m.id}" ${selectedMediaIds.has(m.id) ? 'checked' : ''}>
              <span>${m.original_filename || m.title} (${(m.file_size / 1024).toFixed(0)} KB)</span>
            </label>
          `).join('');
        }
      }

      this.openModal('modal-collection-editor');
    } catch (e) {
      this.showToast(e.message || 'Failed to prepare collection editor', 'error');
    }
  }

  async saveCollectionFromEditor() {
    const colId = document.getElementById('col-editor-id')?.value;
    const name = (document.getElementById('col-editor-name')?.value || '').trim();
    const desc = (document.getElementById('col-editor-desc')?.value || '').trim();
    const mode = document.getElementById('col-editor-mode')?.value || 'fixed_pair';

    if (!name) {
      this.showToast('Please enter a collection name', 'error');
      return;
    }

    const msgCheckboxes = document.querySelectorAll('.col-msg-chk:checked');
    const templateIds = Array.from(msgCheckboxes).map(c => parseInt(c.value));

    const medCheckboxes = document.querySelectorAll('.col-med-chk:checked');
    const mediaAssetIds = Array.from(medCheckboxes).map(c => parseInt(c.value));

    const payload = {
      name: name,
      description: desc,
      pairing_mode: mode,
      template_ids: templateIds,
      media_asset_ids: mediaAssetIds
    };

    try {
      if (colId) {
        await this.api(`/api/collections/${colId}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        this.showToast(`Updated collection: ${name}`, 'success');
      } else {
        await this.api('/api/collections', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        this.showToast(`Created collection: ${name}`, 'success');
      }
      this.closeModal('modal-collection-editor');
      await this.loadLibraryCollections();
    } catch (e) {
      this.showToast(e.message || 'Failed to save collection', 'error');
    }
  }

  async deleteCollection(colId) {
    const ok = await this.confirmDialog({
      title: 'Delete Collection',
      message: 'Are you sure you want to delete this content collection?',
      details: 'Items within the collection will not be deleted from your library.',
      confirmText: 'Delete Collection',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;
    try {
      await this.api(`/api/collections/${colId}`, { method: 'DELETE' });
      this.showToast('Collection deleted', 'success');
      await this.loadLibraryCollections();
    } catch (e) {
      this.showToast(e.message || 'Failed to delete collection', 'error');
    }
  }

  async loadMessages() {
    try {
      this.switchMessagesSubView(this.currentMessagesSubView || 'sets');
      if (this.currentMessagesSubView === 'sets') {
        await this.loadContentSets();
      }
      const templates = await this.api('/api/templates', { silent: true }).catch(() => []);
      const listBody = document.getElementById('messages-list-body');

      if (listBody) {
        if (!templates || templates.length === 0) {
          listBody.innerHTML = `
            <div class="empty-state" style="padding: 1.5rem;">
              <div class="empty-title">No message drafts yet</div>
              <div class="empty-description">Create your first message draft using the composer above.</div>
            </div>
          `;
        } else {
          listBody.innerHTML = `
            <div class="table-container" style="border: none; border-radius: 0;">
              <table>
                <thead>
                  <tr>
                    <th>Title</th>
                    <th>Versions</th>
                    <th style="text-align: right;">Action</th>
                  </tr>
                </thead>
                <tbody>
                  ${templates.map(t => `
                    <tr style="cursor: pointer;" onclick="app.selectMessageDraft(${t.id})">
                      <td><strong>${t.name}</strong></td>
                      <td><span class="badge badge-neutral">${(t.variants || []).length}</span></td>
                      <td style="text-align: right;">
                        <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); app.selectMessageDraft(${t.id})">Edit</button>
                        <button class="btn btn-subtle btn-sm" onclick="event.stopPropagation(); app.deleteMessageDraft(${t.id})" style="color: var(--danger);">Delete</button>
                      </td>
                    </tr>
                  `).join('')}
                </tbody>
              </table>
            </div>
          `;
        }
      }

      if (this.selectedDraftId) {
        await this.selectMessageDraft(this.selectedDraftId);
      } else if (templates && templates.length > 0) {
        await this.selectMessageDraft(templates[0].id);
      } else {
        this.resetMessageEditor();
      }
    } catch (e) {}
  }

  async selectMessageDraft(id) {
    this.selectedDraftId = id;
    try {
      const t = await this.api(`/api/templates/${id}`);
      document.getElementById('msg-edit-id').value = t.id;
      document.getElementById('msg-title-input').value = t.name;
      document.getElementById('msg-content-input').value = t.content;
      document.getElementById('message-editor-title').textContent = `Edit Message: ${t.name}`;

      this.renderVersionsList(t.variants || []);
      this.updateConversationPreview();
    } catch (e) {}
  }

  renderVersionsList(variants) {
    const list = document.getElementById('message-versions-list');
    if (!list) return;

    if (!variants || variants.length === 0) {
      list.innerHTML = '<span style="font-size: 0.78rem; color: var(--text-muted);">Standard version applies to all contacts.</span>';
      return;
    }

    list.innerHTML = variants.map(v => {
      let appliesText = 'Applies to: All recipients (Default)';
      if (v.audience_filter_field && v.audience_filter_field !== 'all') {
        appliesText = `Applies when: ${v.audience_filter_field} is "${v.audience_filter_value}"`;
      }
      return `
        <div style="background-color: var(--surface-subtle); padding: 0.5rem 0.65rem; border-radius: var(--radius-sm); border: 1px solid var(--border-color); display: flex; justify-content: space-between; align-items: center; font-size: 0.8125rem;">
          <div>
            <strong>${v.variant_name}</strong>
            <span style="display: block; font-size: 0.72rem; color: var(--text-muted);">${appliesText}</span>
          </div>
          <div style="display: flex; gap: 0.25rem;">
            <button class="btn btn-subtle btn-sm" onclick="app.openEditVersionModal(${v.id})">Edit</button>
            <button class="btn btn-subtle btn-sm" onclick="app.deleteVersion(${v.id})" style="color: var(--danger);">✕</button>
          </div>
        </div>
      `;
    }).join('');
  }

  onMessageEditorChange() {
    clearTimeout(this.previewTimer);
    this.checkMessageContent();
    this.previewTimer = setTimeout(() => this.updateConversationPreview(), 250);
  }

  checkMessageContent() {
    const content = document.getElementById('msg-content-input')?.value || '';
    const charCounter = document.getElementById('msg-char-counter');
    const warningEl = document.getElementById('msg-validation-warning');

    if (charCounter) {
      charCounter.textContent = `${content.length} / 1024 characters`;
      charCounter.style.color = content.length > 1024 ? 'var(--danger)' : 'var(--text-muted)';
    }

    if (warningEl) {
      const issues = [];
      if (content.length > 1024) {
        issues.push('Message exceeds recommended length limit (1024 chars).');
      }

      const matches = content.match(/\{([a-zA-Z0-9_|]+)\}/g) || [];
      const standardVars = ['{name}', '{first_name}', '{phone}'];
      const nonStandard = matches.filter(m => !standardVars.includes(m.split('|')[0] + '}'));
      if (nonStandard.length > 0) {
        issues.push(`Note: Variable ${nonStandard.join(', ')} will be blank if not present in contact attributes.`);
      }

      if (issues.length > 0) {
        warningEl.textContent = issues.join(' ');
        warningEl.style.display = 'block';
      } else {
        warningEl.style.display = 'none';
      }
    }
  }

  setPreviewViewport(mode) {
    this.previewViewport = mode;
    const shell = document.getElementById('chat-preview-shell');
    const btnDesk = document.getElementById('btn-preview-desktop');
    const btnMob = document.getElementById('btn-preview-mobile');

    if (btnDesk) btnDesk.classList.toggle('active', mode === 'desktop');
    if (btnMob) btnMob.classList.toggle('active', mode === 'mobile');

    if (shell) {
      shell.classList.toggle('preview-mode-mobile', mode === 'mobile');
    }
  }

  getPersonas() {
    return {
      standard: {
        name: 'Alice Smith',
        first_name: 'Alice',
        phone: '+1 (415) 555-2671',
        initials: 'AS',
        status: 'online · WhatsApp Web',
        tag: 'Standard Contact',
        language: 'en',
        tier: 'Standard',
        company: 'Acme Corp'
      },
      spanish: {
        name: 'Carlos Gomez',
        first_name: 'Carlos',
        phone: '+34 612 345 678',
        initials: 'CG',
        status: 'online · WhatsApp Web',
        tag: 'Spanish Audience (es)',
        language: 'es',
        tier: 'Standard',
        company: 'Iberia Logistics'
      },
      vip: {
        name: 'Victoria Stone',
        first_name: 'Victoria',
        phone: '+44 7911 123456',
        initials: 'VS',
        status: 'active 5m ago · WhatsApp Web',
        tag: 'VIP Tier Client',
        language: 'en',
        tier: 'VIP',
        company: 'Apex Global'
      },
      new_lead: {
        name: 'David Lee',
        first_name: 'David',
        phone: '+1 (212) 555-0199',
        initials: 'DL',
        status: 'online · WhatsApp Web',
        tag: 'New Lead / Trial',
        language: 'en',
        tier: 'Trial',
        company: 'Beacon Tech'
      }
    };
  }

  onPreviewPersonaChange() {
    const sel = document.getElementById('preview-persona-select');
    this.selectedPersona = sel ? sel.value : 'standard';
    const persona = this.getPersonas()[this.selectedPersona] || this.getPersonas().standard;

    const avatarEl = document.getElementById('preview-contact-avatar');
    const nameEl = document.getElementById('preview-contact-name');
    const statusEl = document.getElementById('preview-contact-status');
    const tagEl = document.getElementById('preview-audience-tag');

    if (avatarEl) avatarEl.textContent = persona.initials;
    if (nameEl) nameEl.textContent = persona.name;
    if (statusEl) statusEl.textContent = persona.status;
    if (tagEl) tagEl.textContent = persona.tag;

    this.updateConversationPreview();
  }

  async updateConversationPreview() {
    const rawContent = document.getElementById('msg-content-input')?.value?.trim();
    const persona = this.getPersonas()[this.selectedPersona || 'standard'] || this.getPersonas().standard;
    const templateId = this.selectedDraftId;

    const emptyNotice = document.getElementById('preview-empty-state');
    const outgoingBubble = document.getElementById('chat-bubble-outgoing');
    const bubbleText = document.getElementById('preview-bubble-text');
    const bubbleTime = document.getElementById('preview-bubble-time');

    // Update current timestamp
    if (bubbleTime) {
      const now = new Date();
      bubbleTime.textContent = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
    }

    // Media elements
    const mediaContainer = document.getElementById('preview-media-container');
    const imgWrap = document.getElementById('preview-media-image-wrap');
    const imgEl = document.getElementById('preview-media-img');
    const docWrap = document.getElementById('preview-media-doc-wrap');
    const docName = document.getElementById('preview-doc-name');
    const docMeta = document.getElementById('preview-doc-meta');
    const mediaLoading = document.getElementById('preview-media-loading');
    const mediaFailed = document.getElementById('preview-media-failed');
    const mediaUnsupported = document.getElementById('preview-media-unsupported');

    const hideAllMediaStates = () => {
      if (imgWrap) imgWrap.style.display = 'none';
      if (docWrap) docWrap.style.display = 'none';
      if (mediaLoading) mediaLoading.style.display = 'none';
      if (mediaFailed) mediaFailed.style.display = 'none';
      if (mediaUnsupported) mediaUnsupported.style.display = 'none';
    };

    // If completely empty (no text and no media)
    if (!rawContent && !this.selectedMediaFile && !this.selectedMediaAssetId) {
      if (emptyNotice) emptyNotice.style.display = 'flex';
      if (outgoingBubble) outgoingBubble.style.display = 'none';
      if (mediaContainer) mediaContainer.style.display = 'none';
      return;
    }

    if (emptyNotice) emptyNotice.style.display = 'none';
    if (outgoingBubble) outgoingBubble.style.display = 'block';

    let renderedText = rawContent || '';

    // Live variable interpolation
    try {
      if (templateId) {
        const res = await this.api('/api/templates/preview-resolve', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            template_id: templateId,
            contact_data: persona,
            fallback_content: rawContent || ''
          })
        });
        renderedText = res.rendered_content;

        const ruleText = document.getElementById('preview-version-rule-text');
        if (ruleText) {
          ruleText.textContent = res.eligibility_reason
            ? `Active Version: ${res.variant_name} (${res.eligibility_reason})`
            : 'Active Version: Default template';
        }

        if (res.media_asset && res.media_asset.filename) {
          hideAllMediaStates();
          if (mediaContainer) mediaContainer.style.display = 'block';
          const mime = res.media_asset.mime_type || '';
          if (mime.startsWith('image/')) {
            if (imgWrap) imgWrap.style.display = 'block';
            if (imgEl) imgEl.src = `/api/media/file/${res.media_asset.filename}`;
          } else if (mime === 'application/pdf' || res.media_asset.filename.endsWith('.pdf')) {
            if (docWrap) docWrap.style.display = 'flex';
            if (docName) docName.textContent = res.media_asset.title || res.media_asset.filename;
            if (docMeta) docMeta.textContent = 'PDF Document · Attachment';
          }
        }
      } else {
        // Direct local token interpolation
        renderedText = (rawContent || '')
          .replace(/{name}/gi, persona.name)
          .replace(/{first_name}/gi, persona.first_name)
          .replace(/{phone}/gi, persona.phone)
          .replace(/{company}/gi, persona.company)
          .replace(/{tier}/gi, persona.tier);

        const ruleText = document.getElementById('preview-version-rule-text');
        if (ruleText) {
          ruleText.textContent = `Applies to: All recipients (Default draft for ${persona.name})`;
        }
      }
    } catch (e) {
      renderedText = (rawContent || '')
        .replace(/{name}/gi, persona.name)
        .replace(/{first_name}/gi, persona.first_name)
        .replace(/{phone}/gi, persona.phone);
    }

    if (bubbleText) {
      bubbleText.textContent = renderedText || (this.selectedMediaFile ? '' : 'Empty message content');
    }

    // Check user-attached file locally
    if (this.selectedMediaFile) {
      hideAllMediaStates();
      if (mediaContainer) mediaContainer.style.display = 'block';
      const file = this.selectedMediaFile;
      const fName = file.name || 'attachment';
      const fType = file.type || '';
      const fSizeKb = (file.size / 1024).toFixed(1);

      if (fType.startsWith('image/') || /\.(png|jpe?g|gif|webp)$/i.test(fName)) {
        if (imgWrap) imgWrap.style.display = 'block';
        if (imgEl) {
          imgEl.src = URL.createObjectURL(file);
        }
      } else if (fType === 'application/pdf' || /\.pdf$/i.test(fName) || /\.(docx?|xlsx?)$/i.test(fName)) {
        if (docWrap) docWrap.style.display = 'flex';
        if (docName) docName.textContent = fName;
        if (docMeta) docMeta.textContent = `${fSizeKb} KB · Document`;
      } else {
        if (mediaUnsupported) mediaUnsupported.style.display = 'flex';
      }
    } else if (!templateId) {
      if (mediaContainer) mediaContainer.style.display = 'none';
      hideAllMediaStates();
    }
  }

  onPreviewMediaError() {
    const imgWrap = document.getElementById('preview-media-image-wrap');
    const mediaFailed = document.getElementById('preview-media-failed');
    if (imgWrap) imgWrap.style.display = 'none';
    if (mediaFailed) mediaFailed.style.display = 'flex';
  }

  insertVar(varName) {
    const area = document.getElementById('msg-content-input');
    if (!area) return;
    const start = area.selectionStart;
    const end = area.selectionEnd;
    area.value = area.value.substring(0, start) + varName + area.value.substring(end);
    area.focus();
    area.selectionStart = area.selectionEnd = start + varName.length;
    this.updateConversationPreview();
  }

  async saveMessageDraft() {
    const id = document.getElementById('msg-edit-id').value;
    const name = document.getElementById('msg-title-input').value.trim();
    const content = document.getElementById('msg-content-input').value.trim();

    if (!name || !content) {
      this.showToast('Please provide a message title and text body', 'error');
      return;
    }

    try {
      if (id) {
        await this.api(`/api/templates/${id}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, content })
        });
        this.showToast('Message updated', 'success');
      } else {
        const res = await this.api('/api/templates', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ name, content })
        });
        this.selectedDraftId = res.id;
        this.showToast('Message created', 'success');
      }
      this.loadMessages();
      this.loadDashboardData();
    } catch (e) {}
  }

  resetMessageEditor() {
    this.selectedDraftId = null;
    document.getElementById('msg-edit-id').value = '';
    document.getElementById('msg-title-input').value = '';
    document.getElementById('msg-content-input').value = '';
    document.getElementById('message-editor-title').textContent = 'New Message Draft';
    this.clearMediaSelection();
    this.renderVersionsList([]);
    this.updateConversationPreview();
  }

  async onMediaFileSelected(event) {
    const file = event.target ? (event.target.files && event.target.files[0]) : event;
    if (!file) return;

    // Check size limit: max 16 MB
    const maxSize = 16 * 1024 * 1024;
    if (file.size > maxSize) {
      this.showToast('Selected file exceeds 16 MB limit. Please choose a smaller file.', 'error');
      return;
    }

    try {
      this.showToast('Uploading and hashing media asset...', 'info');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name);

      const asset = await this.api('/api/media/upload', {
        method: 'POST',
        body: formData
      });

      this.selectedMediaAssetId = asset.id;
      this.selectedMediaAsset = asset;
      this.selectedMediaFile = file;

      // Update custom file upload area
      const dropzone = document.getElementById('msg-media-dropzone');
      const card = document.getElementById('msg-media-selected-card');
      const nameEl = document.getElementById('msg-media-selected-name');
      const sizeEl = document.getElementById('msg-media-selected-size');
      const hashBadge = document.getElementById('msg-media-hash-badge');
      const thumbImg = document.getElementById('msg-media-thumb-img');
      const thumbIcon = document.getElementById('msg-media-thumb-icon');

      if (dropzone) dropzone.style.display = 'none';
      if (card) card.style.display = 'flex';
      if (nameEl) nameEl.textContent = asset.original_filename || asset.title;
      if (sizeEl) sizeEl.textContent = `${(asset.file_size / (1024 * 1024)).toFixed(2)} MB · ${asset.mime_type || 'file'}`;
      if (hashBadge) {
        hashBadge.style.display = 'inline-block';
        hashBadge.textContent = `SHA: ${(asset.content_hash || '').substring(0, 12)}...`;
        hashBadge.title = `Full SHA-256: ${asset.content_hash}`;
      }

      if (asset.mime_type && asset.mime_type.startsWith('image/')) {
        const url = `/api/media/file/${asset.filename}`;
        if (thumbImg) {
          thumbImg.src = url;
          thumbImg.style.display = 'block';
        }
        if (thumbIcon) thumbIcon.style.display = 'none';
      } else {
        if (thumbImg) thumbImg.style.display = 'none';
        if (thumbIcon) {
          thumbIcon.style.display = 'inline-block';
          thumbIcon.textContent = (asset.filename || '').endsWith('.pdf') ? '📄' : (asset.filename || '').endsWith('.mp4') ? '🎬' : '📎';
        }
      }

      this.showToast(`Media saved to durable library: ${asset.title}`, 'success');
      this.updateConversationPreview();
    } catch (e) {
      this.showToast(e.message || 'Failed to upload media file', 'error');
    }
  }

  clearMediaSelection() {
    this.selectedMediaFile = null;
    this.selectedMediaAssetId = null;
    this.selectedMediaAsset = null;
    const input = document.getElementById('msg-media-file-input');
    if (input) input.value = '';

    const dropzone = document.getElementById('msg-media-dropzone');
    const card = document.getElementById('msg-media-selected-card');
    if (dropzone) dropzone.style.display = 'flex';
    if (card) card.style.display = 'none';

    this.updateConversationPreview();
  }

  // --- Durable Media Library Methods ---
  async openMediaLibraryModal() {
    try {
      const assets = await this.api('/api/media');
      const countLabel = document.getElementById('media-library-count-label');
      if (countLabel) countLabel.textContent = `${assets.length} durable asset${assets.length === 1 ? '' : 's'} stored`;

      const bodyEl = document.getElementById('media-library-body');
      if (bodyEl) {
        if (!assets || assets.length === 0) {
          bodyEl.innerHTML = `
            <div class="empty-state">
              <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><rect x="3" y="3" width="18" height="18" rx="2" ry="2"></rect><circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline></svg>
              <div class="empty-title">Media library is empty</div>
              <div class="empty-description">Upload images or documents to store them durably and reuse them in campaigns.</div>
              <button type="button" class="btn btn-primary btn-sm" onclick="document.getElementById('media-library-upload-input').click()">Upload First Asset</button>
            </div>
          `;
        } else {
          bodyEl.innerHTML = `
            <div class="media-asset-grid">
              ${assets.map(a => {
                const isSelected = (this.selectedMediaAssetId === a.id);
                const isImg = a.mime_type && a.mime_type.startsWith('image/');
                const isPdf = a.mime_type === 'application/pdf' || (a.filename || '').endsWith('.pdf');
                const isVid = a.mime_type && a.mime_type.startsWith('video/');
                const sizeKb = (a.file_size / 1024).toFixed(1);
                const sizeText = a.file_size > 1024 * 1024 ? `${(a.file_size / (1024 * 1024)).toFixed(2)} MB` : `${sizeKb} KB`;
                const hashShort = (a.content_hash || '').substring(0, 16);
                const usageCount = a.usage_count || 0;
                const usedByList = (a.used_by || []).join(', ');

                return `
                  <div class="media-asset-card ${isSelected ? 'active-attached' : ''}">
                    <div>
                      <div class="media-asset-preview">
                        ${isImg
                          ? `<img src="/api/media/file/${a.filename}" alt="${a.title}" onerror="this.onerror=null; this.src=''; this.style.display='none'; this.nextElementSibling.style.display='block';"><span style="display: none; font-size: 2rem;">🖼️</span>`
                          : `<span style="font-size: 2rem;">${isPdf ? '📄' : (isVid ? '🎬' : '📎')}</span>`
                        }
                        ${!a.is_available ? '<span class="badge badge-danger" style="position: absolute; top: 4px; right: 4px;">FILE MISSING</span>' : ''}
                        ${isSelected ? '<span class="badge badge-primary" style="position: absolute; top: 4px; left: 4px;">ATTACHED</span>' : ''}
                      </div>
                      <div class="media-asset-meta" style="margin-top: 0.5rem;">
                        <div class="media-asset-title" title="${a.original_filename || a.title}">${a.original_filename || a.title}</div>
                        <div class="media-asset-sub">
                          <span>${sizeText}</span>
                          <span style="font-family: var(--font-mono); font-size: 0.68rem;">${a.mime_type ? a.mime_type.split('/')[1] : 'file'}</span>
                        </div>
                        <div class="media-asset-hash" title="Full SHA-256: ${a.content_hash}">
                          SHA: ${hashShort}...
                        </div>
                        <div class="media-asset-usage">
                          <span class="badge badge-neutral" title="${usedByList || 'Not currently referenced'}">
                            Used in ${usageCount} place${usageCount === 1 ? '' : 's'}
                          </span>
                        </div>
                      </div>
                    </div>
                    <div style="display: flex; gap: 0.35rem; margin-top: 0.5rem; justify-content: space-between;">
                      <button type="button" class="btn ${isSelected ? 'btn-secondary' : 'btn-primary'} btn-sm" style="flex: 1;" onclick="app.selectMediaFromLibrary(${a.id})">
                        ${isSelected ? 'Attached' : 'Attach'}
                      </button>
                      <button type="button" class="btn btn-subtle btn-sm text-danger" onclick="app.deleteMediaAsset(${a.id}, ${usageCount})" style="color: var(--danger);" title="Delete asset">
                        🗑️
                      </button>
                    </div>
                  </div>
                `;
              }).join('')}
            </div>
          `;
        }
      }

      this.openModal('modal-media-library');
    } catch (e) {
      this.showToast('Failed to load media library: ' + e.message, 'error');
    }
  }

  async onLibraryUploadSelected(event) {
    const file = event.target ? (event.target.files && event.target.files[0]) : null;
    if (!file) return;

    const maxSize = 16 * 1024 * 1024;
    if (file.size > maxSize) {
      this.showToast('Selected file exceeds 16 MB limit.', 'error');
      return;
    }

    try {
      this.showToast('Uploading asset to durable storage...', 'info');
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name);

      const asset = await this.api('/api/media/upload', {
        method: 'POST',
        body: formData
      });

      this.showToast(`Asset "${asset.title}" added to library`, 'success');
      await this.openMediaLibraryModal();
    } catch (e) {
      this.showToast(e.message || 'Failed to upload asset', 'error');
    }
  }

  async selectMediaFromLibrary(assetId) {
    try {
      const asset = await this.api(`/api/media/${assetId}`);
      if (!asset.is_available) {
        this.showToast('This media asset file is missing on disk and cannot be attached.', 'error');
        return;
      }

      this.selectedMediaAssetId = asset.id;
      this.selectedMediaAsset = asset;
      this.selectedMediaFile = null;

      const dropzone = document.getElementById('msg-media-dropzone');
      const card = document.getElementById('msg-media-selected-card');
      const nameEl = document.getElementById('msg-media-selected-name');
      const sizeEl = document.getElementById('msg-media-selected-size');
      const hashBadge = document.getElementById('msg-media-hash-badge');
      const thumbImg = document.getElementById('msg-media-thumb-img');
      const thumbIcon = document.getElementById('msg-media-thumb-icon');

      if (dropzone) dropzone.style.display = 'none';
      if (card) card.style.display = 'flex';
      if (nameEl) nameEl.textContent = asset.original_filename || asset.title;
      if (sizeEl) sizeEl.textContent = `${(asset.file_size / (1024 * 1024)).toFixed(2)} MB · ${asset.mime_type || 'file'}`;
      if (hashBadge) {
        hashBadge.style.display = 'inline-block';
        hashBadge.textContent = `SHA: ${(asset.content_hash || '').substring(0, 12)}...`;
        hashBadge.title = `Full SHA-256: ${asset.content_hash}`;
      }

      if (asset.mime_type && asset.mime_type.startsWith('image/')) {
        const url = `/api/media/file/${asset.filename}`;
        if (thumbImg) {
          thumbImg.src = url;
          thumbImg.style.display = 'block';
        }
        if (thumbIcon) thumbIcon.style.display = 'none';
      } else {
        if (thumbImg) thumbImg.style.display = 'none';
        if (thumbIcon) {
          thumbIcon.style.display = 'inline-block';
          thumbIcon.textContent = (asset.filename || '').endsWith('.pdf') ? '📄' : (asset.filename || '').endsWith('.mp4') ? '🎬' : '📎';
        }
      }

      this.closeModal('modal-media-library');
      this.showToast(`Attached "${asset.title}"`, 'success');
      this.updateConversationPreview();
    } catch (e) {
      this.showToast(e.message || 'Failed to select media asset', 'error');
    }
  }

  async deleteMediaAsset(assetId, usageCount) {
    const ok = await this.confirmDialog({
      title: 'Delete Media Asset',
      message: usageCount > 0
        ? `Warning: This asset is referenced by ${usageCount} item(s). Deleting it will cause future media dispatches to fail permanently. Do you wish to force delete?`
        : 'Are you sure you want to delete this media asset?',
      details: 'The file will be permanently removed from your storage and library.',
      confirmText: 'Delete Asset',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    try {
      const url = usageCount > 0 ? `/api/media/${assetId}?force=true` : `/api/media/${assetId}`;
      await this.api(url, { method: 'DELETE' });
      this.showToast('Media asset deleted', 'success');

      if (this.selectedMediaAssetId === assetId) {
        this.clearMediaSelection();
      }
      await this.openMediaLibraryModal();
    } catch (e) {
      this.showToast(e.message || 'Failed to delete asset', 'error');
    }
  }

  async deleteMessageDraft(id) {
    const ok = await this.confirmDialog({
      title: 'Delete Message Draft',
      message: 'Are you sure you want to delete this message draft?',
      details: 'This draft will be removed from your message library.',
      confirmText: 'Delete Draft',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;
    try {
      await this.api(`/api/templates/${id}`, { method: 'DELETE' });
      this.showToast('Message deleted', 'success');
      if (this.selectedDraftId === id) this.selectedDraftId = null;
      this.loadMessages();
      this.loadDashboardData();
    } catch (e) {}
  }

  // --- Version Modal Handlers ---
  openAddVersionModal() {
    if (!this.selectedDraftId) {
      this.showToast('Please save or select a message first', 'error');
      return;
    }
    document.getElementById('ver-edit-id').value = '';
    document.getElementById('version-modal-title').textContent = 'Add Message Version';
    document.getElementById('ver-name-input').value = '';
    document.getElementById('ver-filter-field').value = 'language';
    document.getElementById('ver-filter-value').value = 'es';
    document.getElementById('ver-content-input').value = document.getElementById('msg-content-input').value;
    this.onVersionFieldChange();
    this.openModal('modal-version');
  }

  async openEditVersionModal(versionId) {
    try {
      const v = await this.api(`/api/templates/variants/${versionId}`);
      document.getElementById('ver-edit-id').value = v.id;
      document.getElementById('version-modal-title').textContent = `Edit Version: ${v.variant_name}`;
      document.getElementById('ver-name-input').value = v.variant_name;
      document.getElementById('ver-filter-field').value = v.audience_filter_field || 'all';
      document.getElementById('ver-filter-value').value = v.audience_filter_value || '';
      document.getElementById('ver-content-input').value = v.content;
      this.onVersionFieldChange();
      this.openModal('modal-version');
    } catch (e) {}
  }

  onVersionFieldChange() {
    const f = document.getElementById('ver-filter-field').value;
    const group = document.getElementById('ver-filter-val-group');
    if (group) group.style.display = f === 'all' ? 'none' : 'block';
  }

  async confirmSaveVersion() {
    const vid = document.getElementById('ver-edit-id').value;
    const templateId = this.selectedDraftId;
    const variantName = document.getElementById('ver-name-input').value.trim();
    const filterField = document.getElementById('ver-filter-field').value;
    const filterVal = document.getElementById('ver-filter-value').value.trim();
    const content = document.getElementById('ver-content-input').value.trim();

    if (!variantName || !content) {
      this.showToast('Please provide a version title and text body', 'error');
      return;
    }

    const payload = {
      template_id: templateId,
      variant_name: variantName,
      purpose: filterField === 'language' ? 'Language version' : filterField === 'tier' ? 'Group version' : 'Custom version',
      audience_filter_field: filterField,
      audience_filter_value: filterVal,
      content: content,
      approval_status: 'approved'
    };

    try {
      if (vid) {
        await this.api(`/api/templates/variants/${vid}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        this.showToast('Version updated', 'success');
      } else {
        await this.api(`/api/templates/${templateId}/variants`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        this.showToast('Version created', 'success');
      }
      this.closeModal('modal-version');
      await this.selectMessageDraft(templateId);
    } catch (e) {}
  }

  async deleteVersion(vid) {
    const ok = await this.confirmDialog({
      title: 'Delete Message Version',
      message: 'Delete this message version?',
      details: 'This variation will be removed from the draft template.',
      confirmText: 'Delete Version',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;
    try {
      await this.api(`/api/templates/variants/${vid}`, { method: 'DELETE' });
      this.showToast('Version deleted', 'success');
      if (this.selectedDraftId) await this.selectMessageDraft(this.selectedDraftId);
    } catch (e) {}
  }

  // ==========================================================================
  // SECTION 4: CAMPAIGNS
  // ==========================================================================
  onCampaignContentSourceChange(source) {
    this.campaignContentSource = source;
    ['sets', 'single', 'collection'].forEach(s => {
      const label = document.getElementById(`source-label-${s}`);
      const isMatch = (s === source);
      if (label) {
        label.classList.toggle('active', isMatch);
        label.classList.toggle('selected', isMatch);
      }
      const radio = document.getElementById(`source-radio-${s}`);
      if (radio) radio.checked = isMatch;

      const container = document.getElementById(`camp-source-container-${s}`);
      if (container) container.style.display = isMatch ? 'block' : 'none';
    });

    this.updateCampaignReview();
    this.refreshAllocationPreview();
  }

  onCampaignContentChange() {
    this.updateCampaignReview();
    this.refreshAllocationPreview();
  }

  async loadCampaignSetup() {
    try {
      const groups = await this.api('/api/contacts/groups');
      const gSel = document.getElementById('camp-group-select');
      if (gSel) {
        gSel.innerHTML = groups.map(g => `<option value="${g.name}">${g.name} (${g.contact_count} contacts)</option>`).join('');
      }

      // Load Content Sets for Campaigns
      const [tSets, mSets] = await Promise.all([
        this.api('/api/sets?type=text', { silent: true }).catch(() => []),
        this.api('/api/sets?type=media', { silent: true }).catch(() => [])
      ]);
      this.textSets = tSets || [];
      this.mediaSets = mSets || [];

      const campTSel = document.getElementById('camp-text-set-select');
      if (campTSel) {
        campTSel.innerHTML = this.textSets.map(s => `
          <option value="${s.id}">${this.escapeHtml(s.name)} (${s.items_count || 0} messages)</option>
        `).join('');
      }
      const campMSel = document.getElementById('camp-media-set-select');
      if (campMSel) {
        campMSel.innerHTML = '<option value="">-- No media set (Text only) --</option>' +
          this.mediaSets.map(s => `
            <option value="${s.id}">${this.escapeHtml(s.name)} (${s.items_count || 0} assets)</option>
          `).join('');
      }

      const templates = await this.api('/api/templates', { silent: true }).catch(() => []);
      this.cachedTemplates = templates || [];
      const tSel = document.getElementById('camp-template-select');
      if (tSel) {
        tSel.innerHTML = '<option value="">-- Choose saved message --</option>' +
          templates.map(t => `<option value="${t.id}">${this.escapeHtml(t.name)}</option>`).join('');
      }

      const collections = await this.api('/api/collections', { silent: true }).catch(() => []);
      this.cachedCollections = collections || [];
      const colSel = document.getElementById('camp-collection-select');
      if (colSel) {
        colSel.innerHTML = '<option value="">-- Choose collection --</option>' +
          collections.map(c => `<option value="${c.id}">${this.escapeHtml(c.name)} (${c.pairing_mode || 'fixed'})</option>`).join('');
      }

      const mediaList = await this.api('/api/media', { silent: true }).catch(() => []);
      const mSel = document.getElementById('camp-media-select');
      if (mSel) {
        mSel.innerHTML = '<option value="">-- No media attachment (Text only) --</option>' +
          mediaList.filter(m => m.is_available).map(m => `<option value="${m.id}">${this.escapeHtml(m.original_filename || m.title)} (${m.file_size_formatted || ''})</option>`).join('');
      }

      await this.updateCampaignReview();
      await this.refreshAllocationPreview();
    } catch (e) {}
  }

  onAllocationMethodChange() {
    const method = document.getElementById('camp-allocation-method')?.value;
    const seedBox = document.getElementById('camp-ab-seed-box');
    if (seedBox) {
      seedBox.style.display = (method === 'ab_test') ? 'block' : 'none';
    }
    this.refreshAllocationPreview();
  }

  onCampaignAudienceChange() {
    this.updateCampaignReview();
    this.refreshAllocationPreview();
  }

  onCampaignMessageChange() {
    this.updateCampaignReview();
    this.refreshAllocationPreview();
  }

  onCampaignCollectionChange() {
    this.updateCampaignReview();
    this.refreshAllocationPreview();
  }

  onCampaignEditorChange() {
    this.updateCampaignReview();
  }

  async refreshAllocationPreview() {
    const body = document.getElementById('camp-allocation-preview-body');
    if (!body) return;

    const group = document.getElementById('camp-group-select')?.value || 'Default';
    const source = this.campaignContentSource || 'sets';
    const allocationMethod = document.getElementById('camp-allocation-method')?.value || 'explicit_default';

    let payload = {
      group_name: group,
      allocation_mode: allocationMethod
    };

    if (source === 'sets') {
      const textSetIdVal = document.getElementById('camp-text-set-select')?.value;
      const mediaSetIdVal = document.getElementById('camp-media-set-select')?.value;
      if (!textSetIdVal) {
        body.innerHTML = `
          <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.8125rem;">
            Select a Text Set to generate pre-send allocation preview.
          </div>
        `;
        return;
      }
      payload.text_set_id = parseInt(textSetIdVal);
      payload.media_set_id = mediaSetIdVal ? parseInt(mediaSetIdVal) : null;
    } else if (source === 'single') {
      const templateIdVal = document.getElementById('camp-template-select')?.value;
      const mediaIdVal = document.getElementById('camp-media-select')?.value;
      if (!templateIdVal) {
        body.innerHTML = `
          <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.8125rem;">
            Select a message template to generate pre-send allocation preview.
          </div>
        `;
        return;
      }
      payload.template_id = parseInt(templateIdVal);
      payload.media_asset_id = mediaIdVal ? parseInt(mediaIdVal) : null;
    } else {
      const colIdVal = document.getElementById('camp-collection-select')?.value;
      if (!colIdVal) {
        body.innerHTML = `
          <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.8125rem;">
            Select a content collection to generate pre-send allocation preview.
          </div>
        `;
        return;
      }
      payload.collection_id = parseInt(colIdVal);
    }

    try {
      const res = await this.api('/api/campaigns/allocation-preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      const allocs = res.allocations || [];
      if (allocs.length === 0) {
        body.innerHTML = `
          <div style="padding: 1.5rem; text-align: center; color: var(--text-muted); font-size: 0.8125rem;">
            No eligible contacts found in group "${group}" (or all contacts are opted out).
          </div>
        `;
        return;
      }

      body.innerHTML = `
        <div class="table-container" style="border: none; border-radius: 0;">
          <table>
            <thead>
              <tr>
                <th style="width: 40px; text-align: center;">#</th>
                <th>Recipient</th>
                <th>Phone</th>
                <th>Assigned Message</th>
                <th>Attached Media</th>
                <th>Pairing Mode / Rule</th>
              </tr>
            </thead>
            <tbody>
              ${allocs.map((a, idx) => `
                <tr>
                  <td style="text-align: center; font-size: 0.75rem; color: var(--text-muted);">${idx + 1}</td>
                  <td><strong>${this.escapeHtml(a.recipient_name)}</strong></td>
                  <td><span style="font-family: var(--font-mono); font-size: 0.78rem;">+${this.formatPhone(a.recipient_phone)}</span></td>
                  <td>
                    <div style="font-size: 0.75rem; font-weight: 600;">${this.escapeHtml(a.message_title || 'Message')}</div>
                    <div style="font-size: 0.72rem; color: var(--text-muted); max-width: 240px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
                      ${this.escapeHtml(a.rendered_message || '')}
                    </div>
                  </td>
                  <td>
                    ${a.media_asset_id ? `
                      <div style="display: flex; align-items: center; gap: 0.35rem; font-size: 0.75rem;">
                        <span>📎</span>
                        <span style="font-weight: 500;">${this.escapeHtml(a.media_title || 'Media')}</span>
                      </div>
                    ` : `
                      <span class="badge badge-neutral" style="font-size: 0.7rem;">Text only</span>
                    `}
                  </td>
                  <td><span class="badge badge-primary" style="font-size: 0.7rem;">${this.escapeHtml(a.pairing_mode || 'Set Allocation')}</span></td>
                </tr>
              `).join('')}
            </tbody>
          </table>
        </div>
      `;
    } catch (e) {
      body.innerHTML = `
        <div style="padding: 1rem; color: var(--danger); font-size: 0.8125rem;">
          Failed to generate allocation preview: ${this.escapeHtml(e.message || 'Server error')}
        </div>
      `;
    }
  }

  setCampaignPace(pace) {
    const paceMap = {
      'balanced': { key: 'normal', min: 8, max: 15 },
      'safe': { key: 'relaxed', min: 12, max: 20 },
      'fast': { key: 'fast', min: 4, max: 8 }
    };
    const activeInfo = paceMap[pace] || paceMap['balanced'];

    ['normal', 'relaxed', 'fast'].forEach(p => {
      const label = document.getElementById(`pace-label-${p}`);
      const isMatch = (p === activeInfo.key);
      if (label) {
        label.classList.toggle('active', isMatch);
        label.classList.toggle('selected', isMatch);
      }
      const radio = document.getElementById(`pace-radio-${p}`);
      if (radio) radio.checked = isMatch;
    });

    const minInput = document.getElementById('camp-min-delay');
    const maxInput = document.getElementById('camp-max-delay');
    if (minInput) minInput.value = activeInfo.min;
    if (maxInput) maxInput.value = activeInfo.max;

    this.updateCampaignReview();
  }

  toggleScheduleMode(mode) {
    const box = document.getElementById('camp-schedule-box');
    const btn = document.getElementById('btn-start-campaign');
    if (mode === 'later') {
      if (box) box.style.display = 'block';
      if (btn) btn.textContent = 'Schedule Campaign';
      const dtInput = document.getElementById('camp-schedule-datetime');
      if (dtInput && !dtInput.value) {
        const nextHour = new Date(Date.now() + 3600 * 1000);
        const offset = nextHour.getTimezoneOffset() * 60000;
        const localISOTime = (new Date(nextHour - offset)).toISOString().slice(0, 16);
        dtInput.value = localISOTime;
      }
    } else {
      if (box) box.style.display = 'none';
      if (btn) btn.textContent = 'Start Campaign';
    }
  }

  async updateCampaignReview() {
    const groupName = document.getElementById('camp-group-select')?.value || 'Default';
    const campName = (document.getElementById('camp-name-input')?.value || '').trim();
    const source = this.campaignContentSource || 'sets';

    const msgNameEl = document.getElementById('camp-summary-msg-name');
    const msgSnippetEl = document.getElementById('camp-summary-msg-snippet');

    let hasValidContent = false;

    if (source === 'sets') {
      const textSetIdVal = document.getElementById('camp-text-set-select')?.value;
      const mediaSetIdVal = document.getElementById('camp-media-set-select')?.value;
      const chosenTextSet = (this.textSets || []).find(s => String(s.id) === String(textSetIdVal));
      const chosenMediaSet = (this.mediaSets || []).find(s => String(s.id) === String(mediaSetIdVal));

      if (chosenTextSet) {
        hasValidContent = true;
        if (msgNameEl) msgNameEl.textContent = `Text Set: ${chosenTextSet.name}`;
        const mediaNote = chosenMediaSet ? ` + Media: ${chosenMediaSet.name}` : ' (Text only)';
        if (msgSnippetEl) msgSnippetEl.textContent = `${chosenTextSet.items_count || 0} messages • Allocation: ${chosenTextSet.allocation_mode || 'random'}${mediaNote}`;
      } else {
        if (msgNameEl) msgNameEl.textContent = 'No Text Set selected';
        if (msgSnippetEl) msgSnippetEl.textContent = 'Select a Text Set to distribute messages across recipients.';
      }
    } else if (source === 'single') {
      const templateId = document.getElementById('camp-template-select')?.value;
      const chosenTemplate = (this.cachedTemplates || []).find(t => String(t.id) === String(templateId));
      if (chosenTemplate) {
        hasValidContent = true;
        if (msgNameEl) msgNameEl.textContent = chosenTemplate.name;
        if (msgSnippetEl) msgSnippetEl.textContent = chosenTemplate.content ? `"${chosenTemplate.content.slice(0, 90)}..."` : 'Single draft';
      } else {
        if (msgNameEl) msgNameEl.textContent = 'None selected';
        if (msgSnippetEl) msgSnippetEl.textContent = 'Choose a message template to review content.';
      }
    } else {
      const collectionId = document.getElementById('camp-collection-select')?.value;
      const chosenCollection = (this.cachedCollections || []).find(c => String(c.id) === String(collectionId));
      if (chosenCollection) {
        hasValidContent = true;
        if (msgNameEl) msgNameEl.textContent = `Collection: ${chosenCollection.name}`;
        if (msgSnippetEl) msgSnippetEl.textContent = `${chosenCollection.description || 'Collection pairing active'} (${chosenCollection.pairing_mode})`;
      } else {
        if (msgNameEl) msgNameEl.textContent = 'None selected';
        if (msgSnippetEl) msgSnippetEl.textContent = 'Choose a collection to review content.';
      }
    }

    try {
      const res = await this.api(`/api/contacts?group=${encodeURIComponent(groupName)}&limit=500`, { silent: true });
      const seenPhones = new Set();
      let duplicates = 0;
      let excluded = 0;
      let eligible = 0;

      (res.items || []).forEach(c => {
        const p = String(c.phone || '').trim();
        if (c.consent_status === 'opted_out') {
          excluded++;
        } else if (seenPhones.has(p)) {
          duplicates++;
        } else {
          seenPhones.add(p);
          eligible++;
        }
      });

      const minDelay = parseFloat(document.getElementById('camp-min-delay')?.value || 8);
      const maxDelay = parseFloat(document.getElementById('camp-max-delay')?.value || 15);

      const selEl = document.getElementById('camp-rev-selected');
      const excEl = document.getElementById('camp-rev-excluded');
      const dupEl = document.getElementById('camp-rev-duplicates');
      const timeEl = document.getElementById('camp-rev-time');

      if (selEl) selEl.textContent = `${eligible} contacts`;
      if (excEl) excEl.textContent = `${excluded} excluded`;
      if (dupEl) dupEl.textContent = `${duplicates} duplicate`;

      if (timeEl) {
        if (eligible === 0) {
          timeEl.textContent = '—';
        } else {
          const minMins = Math.max(1, Math.round((eligible * minDelay) / 60));
          const maxMins = Math.max(1, Math.round((eligible * maxDelay) / 60));
          timeEl.textContent = minMins === maxMins ? `~${minMins} min` : `~${minMins}–${maxMins} mins`;
        }
      }

      // Validation Gate & Explanation
      const startBtn = document.getElementById('btn-start-campaign');
      const hintEl = document.getElementById('camp-validation-hint');

      let missing = '';
      if (!campName) {
        missing = 'Please enter a campaign name.';
      } else if (!hasValidContent) {
        missing = (source === 'sets') ? 'Please select a Text Set.' : 'Please select a message template or collection.';
      } else if (eligible === 0) {
        missing = 'Selected audience has 0 eligible contacts.';
      }

      if (startBtn) startBtn.disabled = Boolean(missing);
      if (hintEl) {
        if (missing) {
          hintEl.textContent = missing;
          hintEl.style.display = 'block';
        } else {
          hintEl.style.display = 'none';
        }
      }
    } catch (e) {}
  }

  async startCampaign() {
    const name = document.getElementById('camp-name-input')?.value.trim() || 'WhatsApp Campaign';
    const groupName = document.getElementById('camp-group-select')?.value || 'Default';
    const source = this.campaignContentSource || 'sets';

    let textSetId = null;
    let mediaSetId = null;
    let templateId = null;
    let collectionId = null;
    let mediaAssetId = null;

    if (source === 'sets') {
      const tVal = document.getElementById('camp-text-set-select')?.value;
      const mVal = document.getElementById('camp-media-set-select')?.value;
      textSetId = tVal ? parseInt(tVal) : null;
      mediaSetId = mVal ? parseInt(mVal) : null;
      if (!textSetId) {
        this.showToast('Please select a Text Set to launch the campaign', 'error');
        return;
      }
    } else if (source === 'single') {
      const templateIdVal = document.getElementById('camp-template-select')?.value;
      const mediaVal = document.getElementById('camp-media-select')?.value;
      templateId = templateIdVal ? parseInt(templateIdVal) : null;
      mediaAssetId = mediaVal ? parseInt(mediaVal) : null;
      if (!templateId) {
        this.showToast('Please select a message draft to send', 'error');
        return;
      }
    } else {
      const colVal = document.getElementById('camp-collection-select')?.value;
      collectionId = colVal ? parseInt(colVal) : null;
      if (!collectionId) {
        this.showToast('Please select a content collection to send', 'error');
        return;
      }
    }

    const minDelay = parseFloat(document.getElementById('camp-min-delay')?.value || 8);
    const maxDelay = parseFloat(document.getElementById('camp-max-delay')?.value || 15);
    const dailyCap = parseInt(document.getElementById('camp-daily-cap')?.value || 100);
    const maxRetries = parseInt(document.getElementById('camp-max-retries')?.value || 3);
    const useMock = document.getElementById('camp-use-mock')?.checked || false;

    const scheduleMode = document.querySelector('input[name="camp-schedule-mode"]:checked')?.value || 'now';
    let scheduledAt = null;
    if (scheduleMode === 'later') {
      const dtVal = document.getElementById('camp-schedule-datetime')?.value;
      if (!dtVal) {
        this.showToast('Please select a scheduled date and time', 'error');
        return;
      }
      const targetDate = new Date(dtVal);
      if (targetDate <= new Date()) {
        this.showToast('Scheduled time must be in the future', 'error');
        return;
      }
      scheduledAt = targetDate.toISOString();
    }

    const allocationMethod = document.getElementById('camp-allocation-method')?.value || 'explicit_default';
    const allocationSeed = parseInt(document.getElementById('camp-allocation-seed')?.value || 42);

    try {
      const res = await this.api('/api/campaigns/launch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          campaign_name: name,
          group_name: groupName,
          text_set_id: textSetId,
          media_set_id: mediaSetId,
          template_id: templateId,
          collection_id: collectionId,
          media_asset_id: mediaAssetId,
          allocation_method: allocationMethod,
          allocation_seed: allocationSeed,
          min_delay: minDelay,
          max_delay: maxDelay,
          daily_cap: dailyCap,
          max_retries: maxRetries,
          use_mock: useMock,
          scheduled_at: scheduledAt
        })
      });

      if (res.status === 'WAITING_FOR_CONNECTION') {
        this.showToast('Campaign queued in WAITING FOR CONNECTION — will auto-start when WhatsApp Web connects', 'warning');
      } else if (res.status === 'SCHEDULED') {
        this.showToast(`Campaign scheduled for ${new Date(scheduledAt).toLocaleString()}`, 'success');
      } else {
        this.showToast(`Campaign started with ${res.total_recipients} recipient(s)`, 'success');
      }
      this.navigate('activity');
      await this.refreshActiveJob();
    } catch (e) {}
  }

  // ==========================================================================
  // SECTION 5: ACTIVITY
  // ==========================================================================
  setActivityFilter(filter) {
    this.activityFilter = filter;
    ['all', 'active', 'scheduled', 'completed', 'paused', 'failed'].forEach(f => {
      const btn = document.getElementById(`act-filter-${f}`);
      if (btn) {
        const isMatch = (f.toUpperCase() === filter);
        btn.classList.toggle('active', isMatch);
        btn.setAttribute('aria-pressed', isMatch ? 'true' : 'false');
      }
    });
    this.loadActivityData();
  }

  async loadActivityData() {
    const body = document.getElementById('activity-table-body');
    if (!body) return;

    try {
      const jobs = await this.api('/api/jobs');
      const countLabel = document.getElementById('activity-count-label');
      if (countLabel) countLabel.textContent = `${jobs.length} run${jobs.length === 1 ? '' : 's'}`;

      if (!jobs || jobs.length === 0) {
        body.innerHTML = `
          <div class="empty-state">
            <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor"><polyline points="22 12 18 12 15 21 9 3 6 12 2 12"></polyline></svg>
            <div class="empty-title">No activity to show</div>
            <div class="empty-description">When you launch a campaign, dispatches and delivery outcomes will appear here.</div>
          </div>
        `;
        return;
      }

      // Filter jobs
      let filtered = jobs;
      if (this.activityFilter === 'ACTIVE') filtered = jobs.filter(j => j.status === 'RUNNING' || j.status === 'QUEUED');
      if (this.activityFilter === 'SCHEDULED') filtered = jobs.filter(j => j.status === 'SCHEDULED');
      if (this.activityFilter === 'COMPLETED') filtered = jobs.filter(j => j.status === 'COMPLETED');
      if (this.activityFilter === 'PAUSED') filtered = jobs.filter(j => j.status === 'PAUSED');
      if (this.activityFilter === 'FAILED') filtered = jobs.filter(j => j.status === 'FAILED');

      body.innerHTML = `
        <div class="table-container" style="border: none; border-radius: 0;">
          <table>
            <thead>
              <tr>
                <th>Campaign</th>
                <th>Status</th>
                <th>Dispatched / Total</th>
                <th>Started / Scheduled</th>
                <th>Ended</th>
                <th style="text-align: right;">Details</th>
              </tr>
            </thead>
            <tbody>
              ${filtered.map(j => {
                const statusBadge = j.status === 'COMPLETED' ? 'badge-success' : j.status === 'FAILED' ? 'badge-danger' : j.status === 'SCHEDULED' ? 'badge-neutral' : 'badge-warning';
                const timeStr = j.status === 'SCHEDULED' && j.scheduled_at ? `Scheduled: ${j.scheduled_at.replace('T', ' ').slice(0, 16)}` : (j.started_at || '').slice(0, 16).replace('T', ' ');
                return `
                  <tr>
                    <td><strong>${j.campaign_name}</strong></td>
                    <td><span class="badge ${statusBadge}">${j.status}</span></td>
                    <td>${j.sent_count} / ${j.total_count}</td>
                    <td style="color: var(--text-muted); font-size: 0.78rem;">${timeStr}</td>
                    <td style="color: var(--text-muted); font-size: 0.78rem;">${(j.completed_at || '-').slice(0, 16).replace('T', ' ')}</td>
                    <td style="text-align: right;">
                      <button class="btn btn-secondary btn-sm" onclick="app.viewCampaignDetail('${j.id}')">View</button>
                    </td>
                  </tr>
                `;
              }).join('')}
            </tbody>
          </table>
        </div>
      `;
    } catch (e) {}
  }

  async viewCampaignDetail(jobId) {
    try {
      const job = await this.api(`/api/jobs/${jobId}`);
      const queueRes = await this.api(`/api/jobs/${jobId}/queue?limit=100`);

      document.getElementById('act-detail-camp').textContent = job.campaign_name;
      const statusBadge = document.getElementById('act-detail-status');
      statusBadge.textContent = job.status;
      statusBadge.className = `badge ${job.status === 'COMPLETED' ? 'badge-success' : job.status === 'FAILED' ? 'badge-danger' : 'badge-warning'}`;

      document.getElementById('act-detail-counts').textContent = `${job.sent_count} sent, ${job.failed_count} failed (${job.total_count} total)`;
      document.getElementById('act-detail-started').textContent = (job.started_at || '').replace('T', ' ');
      document.getElementById('act-detail-completed').textContent = (job.completed_at || 'In progress').replace('T', ' ');

      const errBox = document.getElementById('act-detail-error-box');
      if (job.error_message) {
        errBox.style.display = 'block';
        document.getElementById('act-detail-error').textContent = job.error_message;
      } else {
        errBox.style.display = 'none';
      }

      // Populate recipient delivery rows
      const tbody = document.getElementById('act-detail-recipients-tbody');
      const items = queueRes.items || [];
      if (items.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted);">No per-recipient records found.</td></tr>';
      } else {
        tbody.innerHTML = items.map(item => `
          <tr>
            <td><strong>${item.recipient_name}</strong></td>
            <td><span style="font-family: var(--font-mono); font-size: 0.78rem;">+${this.formatPhone(item.phone_masked || item.recipient_phone)}</span></td>
            <td><span class="badge ${item.status === 'DISPATCHED' ? 'badge-success' : item.status === 'SUPPRESSED' ? 'badge-neutral' : 'badge-danger'}">${item.status}</span></td>
            <td style="font-size: 0.75rem; color: var(--text-muted);">${item.error_message || item.variant_purpose || 'Delivered'}</td>
          </tr>
        `).join('');
      }

      this.activeDetailJobId = jobId;
      const failedItems = items.filter(it => it.status === 'FAILED' || it.status === 'FAILED_PERMANENT');
      const retryBtn = document.getElementById('btn-retry-failed-job');
      if (retryBtn) {
        if (failedItems.length > 0) {
          retryBtn.style.display = 'inline-flex';
          retryBtn.textContent = `Retry Failed (${failedItems.length})`;
        } else {
          retryBtn.style.display = 'none';
        }
      }

      document.getElementById('btn-export-act-csv').onclick = () => {
        window.location.href = `/api/jobs/${jobId}/export`;
      };

      this.openModal('modal-activity-detail');
    } catch (e) {}
  }

  async retryFailedJob() {
    if (!this.activeDetailJobId) return;
    try {
      this.showToast('Queuing retry campaign for failed recipients...', 'info');
      const res = await this.api(`/api/jobs/${this.activeDetailJobId}/retry-failed`, { method: 'POST' });
      this.closeModal('modal-activity-detail');
      this.showToast(res.message || 'Retry campaign queued', 'success');
      this.loadActivityData();
      this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to retry recipients', 'error');
    }
  }

  exportActivityCSV() {
    window.location.href = '/api/logs/export';
  }

  downloadBackupJSON() {
    window.location.href = '/api/config/backup';
  }

  async onRestoreBackupSelected(event) {
    const file = event.target.files?.[0];
    if (!file) return;

    const formData = new FormData();
    formData.append('file', file);

    try {
      this.showToast('Restoring backup data...', 'info');
      const res = await fetch('/api/config/restore', { method: 'POST', body: formData });
      if (!res.ok) {
        const err = await res.json();
        throw new Error(err.detail || 'Restore failed');
      }
      const data = await res.json();
      this.showToast(data.message || 'Backup restored successfully!', 'success');
      await this.loadSettingsData();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to restore backup', 'error');
    } finally {
      event.target.value = '';
    }
  }

  // ==========================================================================
  // SECTION 6: SETTINGS & MESSAGING CONNECTION
  // ==========================================================================
  async loadSettingsData() {
    try {
      this.applyTheme(this.theme, false);
      const cfgRes = await this.api('/api/config');
      if (cfgRes && cfgRes.config) {
        const c = cfgRes.config;
        document.getElementById('cfg-country-code').value = c.default_country_code || '';
        document.getElementById('cfg-min-delay').value = c.min_delay;
        document.getElementById('cfg-max-delay').value = c.max_delay;
        document.getElementById('cfg-daily-cap').value = c.daily_cap;
      }
      await this.loadBrowserConnection();
    } catch (e) {}
  }

  async loadBrowserConnection() {
    this.connPollGen = (this.connPollGen || 0) + 1;
    const currentGen = this.connPollGen;
    if (this.isSavingProfile || this.isSelectingModel) {
      return this.connectionState;
    }
    try {
      const data = await this.api('/api/browser-connection/live', { silent: true });
      if (currentGen !== this.connPollGen) {
        // Discard stale response
        return this.connectionState;
      }
      const state = data.state || 'not_checked';
      const stateLabel = data.state_label || 'Not checked';
      const isConnected = state === 'connected';
      const isWaitingQr = state === 'waiting_for_qr';
      const isLocked = state === 'profile_locked';
      const isStaleLock = state === 'stale_lock';
      const isLaunchFailed = state === 'launch_failed';
      const isDedicated = Boolean(data.mode === 'dedicated' || data.is_dedicated);
      const browserName = data.browser_name || (data.browser ? data.browser.charAt(0).toUpperCase() + data.browser.slice(1) : 'Chrome');
      const profileName = data.profile_name || (isDedicated ? 'Dedicated WhatsApp Session' : 'Default Profile');
      const activityText = data.current_activity || data.activity || (isConnected ? 'WhatsApp Web connected and ready' : 'No active messaging task');
      const lastCheckedVal = data.last_checked_at || data.last_checked;

      // Update persistence checkboxes if present
      const chkRem = document.getElementById('chk-remember-profile');
      if (chkRem && data.remember_profile !== undefined) {
        chkRem.checked = Boolean(data.remember_profile);
      }
      const chkAuto = document.getElementById('chk-auto-connect');
      if (chkAuto && data.auto_connect !== undefined) {
        chkAuto.checked = Boolean(data.auto_connect);
      }

      // Backwards-compatible status
      const conn = {
        ...data,
        status: isConnected ? 'Signed in' : (isWaitingQr ? 'Needs QR sign-in' : (isLocked ? 'Profile in use' : (isStaleLock ? 'Stale lock detected' : (state === 'unsupported_profile' ? 'Cannot be automated' : (isLaunchFailed ? 'Launch failed' : (state === 'browser_closed' ? 'Browser unavailable' : stateLabel))))))
      };
      this.connectionState = conn;
      this.isWhatsAppConnected = Boolean(isConnected);
      this.currentSessionState = state;
      this.updateTemplateEditorConnectionPill();

      const prefProfile = data.preferred_profile || {};
      const isUnsupported = state === 'unsupported_profile' || (prefProfile.is_supported === false && !isConnected);
      const prefDisplayName = prefProfile.profile_name || profileName;
      const prefBrowserName = prefProfile.browser_name || browserName;

      let displayTitle = profileName;
      let displaySub = `Browser: ${browserName} · Profile: ${isDedicated ? 'Dedicated Isolated Session' : profileName}`;
      let displayReason = activityText;

      if (isConnected) {
        displayTitle = 'Active session: Relay Automation';
        displaySub = `Browser: Google Chrome (Persistent Session) · Last verified: ${new Date().toLocaleTimeString()}`;
        displayReason = 'WhatsApp Web connected and ready';
      } else if (isWaitingQr) {
        displayTitle = 'Active session: Relay Automation';
        displaySub = 'Device pairing required — scan QR code in WhatsApp';
        displayReason = 'Scan the QR code displayed in the browser window';
      } else if (isUnsupported) {
        displayTitle = `Saved profile: ${prefBrowserName} — ${prefDisplayName}`;
        displaySub = `Reason: Selected ${prefBrowserName} profile cannot be automated with the current configuration.`;
        displayReason = prefProfile.unsupported_reason || 'Chrome 136+ security restrictions prevent remote debugging against Chrome\'s default user-data directory.';
      } else if (isLocked) {
        displayTitle = `Saved profile: ${browserName} — ${profileName}`;
        displaySub = 'Selected profile is currently open in a personal browser window.';
        displayReason = activityText;
      }

      // 1. Update Dashboard Card
      const dashModePill = document.getElementById('dash-mode-pill');
      if (dashModePill) {
        if (isConnected) {
          dashModePill.textContent = 'Active: Relay Automation';
          dashModePill.className = 'badge badge-success';
        } else if (isWaitingQr) {
          dashModePill.textContent = 'Active: Relay Automation';
          dashModePill.className = 'badge badge-warning';
        } else if (isUnsupported) {
          dashModePill.textContent = `Saved: ${prefBrowserName} — ${prefDisplayName}`;
          dashModePill.className = 'badge badge-neutral';
        } else {
          dashModePill.textContent = isDedicated ? 'Dedicated Relay Session' : 'Existing Browser Profile';
          dashModePill.className = isDedicated ? 'badge badge-primary' : 'badge badge-neutral';
        }
      }

      const dashLiveBadge = document.getElementById('dash-live-badge');
      if (dashLiveBadge) {
        dashLiveBadge.className = `conn-live-badge state-${state}`;
      }
      const dashPulseDot = document.getElementById('dash-pulse-dot');
      if (dashPulseDot) {
        dashPulseDot.className = `conn-pulse-dot ${isConnected || isWaitingQr || state.includes('starting') ? 'pulse' : ''}`;
      }
      const dashStateLabel = document.getElementById('dash-state-label');
      if (dashStateLabel) dashStateLabel.textContent = isConnected ? 'Connected' : (isUnsupported ? 'Cannot be automated' : stateLabel);

      const dashProfileTitle = document.getElementById('dash-profile-title');
      if (dashProfileTitle) dashProfileTitle.textContent = displayTitle;

      const dashProfileBrowser = document.getElementById('dash-profile-browser');
      if (dashProfileBrowser) {
        dashProfileBrowser.textContent = displaySub;
      }

      const dashLastChecked = document.getElementById('dash-last-checked');
      if (dashLastChecked) {
        const timeStr = lastCheckedVal ? new Date(lastCheckedVal).toLocaleTimeString() : 'Just now';
        dashLastChecked.textContent = `Last checked: ${timeStr}`;
      }

      const dashActivityText = document.getElementById('dash-activity-text');
      if (dashActivityText) dashActivityText.textContent = displayReason;

      // Update Steppers
      this.updateTimelineStepper('dash', data.timeline || []);
      this.renderConnectionActions('dash-conn-actions', data.actions || []);

      // 2. Update Settings Card
      const settingsModeBadge = document.getElementById('settings-mode-badge');
      if (settingsModeBadge) {
        if (isConnected) {
          settingsModeBadge.textContent = 'Active: Relay Automation';
          settingsModeBadge.className = 'badge badge-success';
        } else if (isWaitingQr) {
          settingsModeBadge.textContent = 'Active: Relay Automation';
          settingsModeBadge.className = 'badge badge-warning';
        } else if (isUnsupported) {
          settingsModeBadge.textContent = `Saved: ${prefBrowserName} — ${prefDisplayName}`;
          settingsModeBadge.className = 'badge badge-neutral';
        } else {
          settingsModeBadge.textContent = isDedicated ? 'Dedicated Relay Session' : 'Existing Browser Profile';
          settingsModeBadge.className = isDedicated ? 'badge badge-primary' : 'badge badge-neutral';
        }
      }

      const settingsLiveBadge = document.getElementById('settings-live-badge');
      if (settingsLiveBadge) {
        settingsLiveBadge.className = `conn-live-badge state-${state}`;
      }
      const settingsPulseDot = document.getElementById('settings-pulse-dot');
      if (settingsPulseDot) {
        settingsPulseDot.className = `conn-pulse-dot ${isConnected || isWaitingQr || state.includes('starting') ? 'pulse' : ''}`;
      }
      const settingsStateLabel = document.getElementById('settings-state-label');
      if (settingsStateLabel) settingsStateLabel.textContent = isConnected ? 'Connected' : (isUnsupported ? 'Cannot be automated' : stateLabel);

      const connProfileName = document.getElementById('conn-profile-name');
      if (connProfileName) connProfileName.textContent = displayTitle;

      const connBrowserDetails = document.getElementById('conn-browser-details');
      if (connBrowserDetails) {
        connBrowserDetails.textContent = displaySub;
      }

      const connLastChecked = document.getElementById('conn-last-checked');
      if (connLastChecked) {
        const timeStr = lastCheckedVal ? new Date(lastCheckedVal).toLocaleTimeString() : 'Just now';
        connLastChecked.textContent = `Last checked: ${timeStr}`;
      }

      const connStatusMessage = document.getElementById('conn-status-message');
      if (connStatusMessage) connStatusMessage.textContent = displayReason;

      this.updateTimelineStepper('settings', data.timeline || []);
      this.renderConnectionActions('settings-conn-actions', data.actions || []);

      // 3. Highlight Connection Models in Settings
      const isExplicitDedicated = this.selectedConnectionModel ? (this.selectedConnectionModel === 'dedicated') : isDedicated;
      const modelCardDedicated = document.getElementById('model-card-dedicated');
      const modelCardExisting = document.getElementById('model-card-existing');
      const radDedicated = document.getElementById('radio-model-dedicated');
      const radExisting = document.getElementById('radio-model-existing');
      const pillDedicated = document.getElementById('model-dedicated-selected-pill');
      const pillExisting = document.getElementById('model-existing-selected-pill');
      const actionsDedicated = document.getElementById('model-dedicated-actions');
      const actionsExisting = document.getElementById('model-existing-actions');
      const existingSummary = document.getElementById('model-existing-profile-summary');

      if (radDedicated) radDedicated.checked = isExplicitDedicated;
      if (radExisting) radExisting.checked = !isExplicitDedicated;

      if (modelCardDedicated) {
        modelCardDedicated.classList.toggle('active', isExplicitDedicated);
        modelCardDedicated.classList.toggle('selected', isExplicitDedicated);
      }
      if (modelCardExisting) {
        modelCardExisting.classList.toggle('active', !isExplicitDedicated);
        modelCardExisting.classList.toggle('selected', !isExplicitDedicated);
      }

      if (pillDedicated) pillDedicated.style.display = isExplicitDedicated ? 'inline-flex' : 'none';
      if (pillExisting) pillExisting.style.display = !isExplicitDedicated ? 'inline-flex' : 'none';

      if (actionsDedicated) actionsDedicated.style.display = isExplicitDedicated ? 'flex' : 'none';
      if (actionsExisting) actionsExisting.style.display = !isExplicitDedicated ? 'flex' : 'none';

      if (existingSummary) {
        existingSummary.textContent = isExplicitDedicated
          ? 'Profile: Dedicated session active'
          : `Active Profile: ${browserName} · ${profileName}`;
      }

      // 4. Update Topbar Session Indicator Pill
      const dot = document.getElementById('topbar-session-dot');
      const text = document.getElementById('topbar-session-text');
      if (dot && text) {
        if (isConnected) {
          dot.className = 'status-indicator online';
          text.textContent = 'WhatsApp Connected';
        } else if (isWaitingQr) {
          dot.className = 'status-indicator warning';
          text.textContent = 'Needs QR Scan';
        } else if (isUnsupported) {
          dot.className = 'status-indicator offline';
          text.textContent = 'Cannot be automated';
        } else if (isLocked) {
          dot.className = 'status-indicator offline';
          text.textContent = 'Profile in Use';
        } else if (state === 'starting_browser' || state === 'opening_whatsapp') {
          dot.className = 'status-indicator warning';
          text.textContent = 'Connecting...';
        } else {
          dot.className = 'status-indicator offline';
          text.textContent = 'WhatsApp Not Connected';
        }
      }

      // 5. Update Hero Pill
      const heroConnBadge = document.getElementById('dash-conn-badge');
      if (heroConnBadge) {
        if (isConnected) {
          heroConnBadge.textContent = 'Connected';
          heroConnBadge.className = 'badge badge-success';
        } else if (isWaitingQr) {
          heroConnBadge.textContent = 'Needs QR';
          heroConnBadge.className = 'badge badge-warning';
        } else if (isLocked) {
          heroConnBadge.textContent = 'Profile in use';
          heroConnBadge.className = 'badge badge-danger';
        } else if (isStaleLock) {
          heroConnBadge.textContent = 'Stale lock';
          heroConnBadge.className = 'badge badge-warning';
        } else if (isLaunchFailed) {
          heroConnBadge.textContent = 'Launch failed';
          heroConnBadge.className = 'badge badge-danger';
        } else {
          heroConnBadge.textContent = stateLabel;
          heroConnBadge.className = 'badge badge-neutral';
        }
      }

      return conn;
    } catch (e) {
      return { browser: 'chrome', profile_dir: '__dedicated__', status: 'Not checked', state: 'not_checked', is_dedicated: true };
    }
  }

  updateTimelineStepper(prefix, timeline) {
    if (!timeline || !Array.isArray(timeline)) return;
    timeline.forEach(step => {
      const stepEl = document.getElementById(`${prefix}-step-${step.id}`);
      if (stepEl) {
        const stepStatus = step.status || step.state;
        const stateClass = stepStatus === 'completed' ? 'completed' : (stepStatus === 'current' ? 'current' : (stepStatus === 'failed' ? 'failed' : ''));
        stepEl.className = `stepper-step ${stateClass}`.trim();

        const iconEl = stepEl.querySelector('.stepper-icon');
        if (iconEl) {
          if (stepStatus === 'completed') iconEl.textContent = '✓';
          else if (stepStatus === 'current') iconEl.textContent = '●';
          else if (stepStatus === 'failed') iconEl.textContent = '✕';
          else iconEl.textContent = '○';
        }

        const timeEl = document.getElementById(`${prefix}-time-${step.id}`);
        if (timeEl) {
          timeEl.textContent = this.formatSafeTime(step.timestamp);
        }
      }
    });
  }

  renderConnectionActions(containerId, actions) {
    const container = document.getElementById(containerId);
    if (!container) return;
    if (!actions || actions.length === 0) {
      container.innerHTML = '';
      return;
    }

    container.innerHTML = actions.map(act => {
      const isSec = (act.variant || act.style) === 'secondary';
      const btnClass = act.primary ? 'btn btn-primary btn-sm' : (isSec ? 'btn btn-secondary btn-sm' : 'btn btn-subtle btn-sm');
      const escapedId = act.id.replace(/'/g, "\\'");
      const escapedLabel = act.label.replace(/'/g, "\\'");
      return `<button class="${btnClass}" onclick="app.executeConnectionAction('${escapedId}', '${escapedLabel}')">${act.label}</button>`;
    }).join(' ');
  }

  async executeConnectionAction(actionId, label) {
    if (this.isExecutingConnAction) return;

    if (actionId === 'change_profile') {
      this.openProfilePickerModal();
      return;
    }

    if (actionId === 'confirm_personal_restart') {
      this.openModal('modal-confirm-browser-restart');
      return;
    }

    if (actionId === 'start_session') {
      await this.startBrowserSession();
      return;
    }

    if (actionId === 'test_connection') {
      await this.testBrowserConnection();
      return;
    }

    if (actionId === 'view_details') {
      await this.openDiagnosticDetailsModal();
      return;
    }

    if (actionId === 'disconnect') {
      this.isExecutingConnAction = true;
      try {
        await this.api('/api/browser-connection/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'disconnect' }),
          silent: true
        });
        this.showToast('Disconnected messaging session.', 'info');
        await this.loadBrowserConnection();
        await this.loadDashboardData();
      } catch (e) {
        this.showToast(e.message || 'Disconnect failed', 'error');
      } finally {
        this.isExecutingConnAction = false;
      }
      return;
    }

    this.isExecutingConnAction = true;
    this.showToast(`Action: ${label}...`, 'info');

    try {
      const res = await this.api('/api/browser-connection/action', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: actionId }),
        silent: true
      });
      if (res.message) {
        this.showToast(res.message, res.status === 'ok' ? 'success' : 'info');
      }
      await this.loadBrowserConnection();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || `Failed to execute ${label}`, 'error');
    } finally {
      this.isExecutingConnAction = false;
    }
  }

  async openDiagnosticDetailsModal() {
    try {
      let details = this.connectionState && this.connectionState.diagnostic_details ? this.connectionState.diagnostic_details : null;
      if (!details) {
        const res = await this.api('/api/browser-connection/action', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ action: 'view_details' }),
          silent: true
        });
        details = res && res.details ? res.details : {};
      }

      const condEl = document.getElementById('diag-condition-badge');
      if (condEl) {
        condEl.textContent = details.condition || 'AVAILABLE';
        if (details.condition === 'ACTIVE_VISIBLE_PROCESS' || details.condition === 'ACTIVE_BACKGROUND_PROCESS') {
          condEl.className = 'badge badge-danger';
        } else if (details.condition === 'STALE_LOCK_ARTIFACT') {
          condEl.className = 'badge badge-warning';
        } else if (details.condition === 'MISSING_EXECUTABLE' || details.condition === 'LAUNCH_FAILED') {
          condEl.className = 'badge badge-danger';
        } else {
          condEl.className = 'badge badge-success';
        }
      }

      const reasonEl = document.getElementById('diag-safe-reason');
      if (reasonEl) {
        reasonEl.textContent = details.safe_error_reason || 'No errors or locks detected on this profile.';
      }

      const bNameEl = document.getElementById('diag-browser-name');
      if (bNameEl) {
        bNameEl.textContent = details.browser_name || 'Google Chrome';
      }

      const exeStatusEl = document.getElementById('diag-exe-status');
      if (exeStatusEl) {
        exeStatusEl.textContent = details.browser_exe_exists ? 'Verified on disk' : 'Executable not found';
        exeStatusEl.style.color = details.browser_exe_exists ? 'var(--text-primary)' : 'var(--danger)';
      }

      const pidsEl = document.getElementById('diag-pids');
      if (pidsEl) {
        if (details.matching_pids && details.matching_pids.length > 0) {
          pidsEl.textContent = `PID ${details.matching_pids.join(', ')}`;
          pidsEl.style.color = 'var(--danger)';
        } else {
          pidsEl.textContent = 'None detected';
          pidsEl.style.color = 'var(--text-muted)';
        }
      }

      const winVisEl = document.getElementById('diag-window-vis');
      if (winVisEl) {
        if (details.has_visible_window) {
          winVisEl.textContent = 'Visible desktop window active';
          winVisEl.style.color = 'var(--danger)';
        } else if (details.matching_pids && details.matching_pids.length > 0) {
          winVisEl.textContent = 'Background process (no window)';
          winVisEl.style.color = 'var(--warning)';
        } else {
          winVisEl.textContent = 'No process running';
          winVisEl.style.color = 'var(--text-muted)';
        }
      }

      const pathEl = document.getElementById('diag-profile-path');
      if (pathEl) {
        pathEl.textContent = details.profile_path || 'Default';
      }

      this.openModal('modal-connection-details');
    } catch (e) {
      this.showToast('Could not load diagnostic details.', 'error');
    }
  }

  // --- Connection Model Selection ---
  async selectConnectionModel(modelType) {
    if (this.isSelectingModel) return;

    if (this.activeJob && (this.activeJob.status === 'RUNNING' || this.activeJob.status === 'WAITING_FOR_CONNECTION')) {
      const confirmChange = await this.confirmDialog({
        title: 'Change Connection Model',
        message: 'A campaign is currently active or queued. Changing the connection model may interrupt sending. Do you wish to continue?',
        confirmText: 'Change Model',
        cancelText: 'Keep Current',
        isDestructive: false
      });
      if (!confirmChange) {
        const isDed = this.selectedConnectionModel ? (this.selectedConnectionModel === 'dedicated') : Boolean(this.connectionState?.is_dedicated || this.connectionState?.mode === 'dedicated');
        const radDed = document.getElementById('radio-model-dedicated');
        const radExist = document.getElementById('radio-model-existing');
        if (radDed) radDed.checked = isDed;
        if (radExist) radExist.checked = !isDed;
        return;
      }
    }

    this.isSelectingModel = true;
    this.selectedConnectionModel = modelType;
    this.connPollGen = (this.connPollGen || 0) + 1;

    const isDed = (modelType === 'dedicated');
    const radDed = document.getElementById('radio-model-dedicated');
    const radExist = document.getElementById('radio-model-existing');
    if (radDed) radDed.checked = isDed;
    if (radExist) radExist.checked = !isDed;

    const cardDed = document.getElementById('model-card-dedicated');
    const cardExist = document.getElementById('model-card-existing');
    if (cardDed) { cardDed.classList.toggle('active', isDed); cardDed.classList.toggle('selected', isDed); }
    if (cardExist) { cardExist.classList.toggle('active', !isDed); cardExist.classList.toggle('selected', !isDed); }

    const pillDed = document.getElementById('model-dedicated-selected-pill');
    const pillExist = document.getElementById('model-existing-selected-pill');
    if (pillDed) pillDed.style.display = isDed ? 'inline-flex' : 'none';
    if (pillExist) pillExist.style.display = !isDed ? 'inline-flex' : 'none';

    const actDed = document.getElementById('model-dedicated-actions');
    const actExist = document.getElementById('model-existing-actions');
    if (actDed) actDed.style.display = isDed ? 'flex' : 'none';
    if (actExist) actExist.style.display = !isDed ? 'flex' : 'none';

    try {
      if (modelType === 'dedicated') {
        await this.api('/api/browser-profile/dedicated', { method: 'POST', silent: true });
        this.showToast('Switched to Dedicated Relay Session (Isolated)', 'info');
        await this.loadBrowserConnection();
        await this.loadDashboardData();
      } else if (modelType === 'existing') {
        this.showToast('Selected Existing Browser Profile mode', 'info');
        await this.openProfilePickerModal();
      }
    } catch (e) {
      this.showToast(e.message || 'Failed to switch connection model', 'error');
    } finally {
      this.isSelectingModel = false;
    }
  }

  // --- Profile Picker Modal ---
  async openProfilePickerModal() {
    if (this.isLoadingBrowsers) return;
    this.isLoadingBrowsers = true;

    try {
      const data = await this.api('/api/browser-profiles', { silent: true });
      this.allDiscoveredBrowsers = data.browsers || [];
      const installed = this.allDiscoveredBrowsers.filter(b => b.installed);

      const emptyEl = document.getElementById('picker-empty-state');
      const discEl = document.getElementById('picker-discovered-container');
      const saveBtn = document.getElementById('btn-save-profile-selection');

      if (installed.length === 0) {
        if (emptyEl) emptyEl.style.display = 'block';
        if (discEl) discEl.style.display = 'none';
        if (saveBtn) saveBtn.disabled = true;
      } else {
        if (emptyEl) emptyEl.style.display = 'none';
        if (discEl) discEl.style.display = 'block';

        const bSelect = document.getElementById('picker-browser-select');
        if (bSelect) {
          bSelect.innerHTML = installed.map(b => `
            <option value="${b.key}">
              ${b.name} (${b.total_profiles || (b.profiles || []).length} profiles)
            </option>
          `).join('');

          const currentBrowser = this.connectionState?.browser || 'chrome';
          const hasCurrent = installed.some(b => b.key === currentBrowser);
          bSelect.value = hasCurrent ? currentBrowser : installed[0].key;
        }

        await this.onPickerBrowserChange();
      }

      // Reset confirmation checkbox
      const confirmChk = document.getElementById('picker-owner-confirm');
      if (confirmChk) confirmChk.checked = false;
      if (saveBtn && installed.length > 0) saveBtn.disabled = true;

      // Populate persistence checkboxes from connection state
      const chkRemPicker = document.getElementById('picker-remember-profile');
      if (chkRemPicker) chkRemPicker.checked = this.connectionState?.remember_profile !== false;
      const chkAutoPicker = document.getElementById('picker-auto-connect');
      if (chkAutoPicker) chkAutoPicker.checked = Boolean(this.connectionState?.auto_connect);

      this.openModal('modal-profile-picker');
    } catch (e) {
      const msg = e.action ? `${e.message} ${e.action}` : (e.message || 'Failed to load installed browsers');
      this.showToast(msg, 'error');
    } finally {
      this.isLoadingBrowsers = false;
    }
  }

  async onPickerBrowserChange() {
    const bSelect = document.getElementById('picker-browser-select');
    const pSelect = document.getElementById('picker-profile-select');
    if (!bSelect || !pSelect) return;

    const browserKey = bSelect.value;
    const browserObj = (this.allDiscoveredBrowsers || []).find(b => b.key === browserKey);
    const profiles = browserObj ? (browserObj.profiles || []) : [];

    this.currentPickerProfiles = profiles;

    pSelect.innerHTML = profiles.map(p => {
      const availLabel = p.availability === 'in_use' ? 'In Use' : 'Available';
      return `
        <option value="${p.dir}" data-name="${p.display_name || p.name}" data-shortpath="${p.short_path || p.dir}" data-avail="${p.availability || 'available'}">
          ${p.display_name || p.name} [${p.short_path || p.dir}] — ${availLabel}
        </option>
      `;
    }).join('');

    const curDir = this.connectionState?.profile_dir || '__dedicated__';
    const hasCur = profiles.some(p => p.dir === curDir);
    if (hasCur) pSelect.value = curDir;
    else if (profiles.length > 0) pSelect.value = profiles[0].dir;

    this.onPickerProfileChange();
  }

  onPickerProfileChange() {
    const pSelect = document.getElementById('picker-profile-select');
    if (!pSelect) return;

    const opt = pSelect.options[pSelect.selectedIndex];
    const nameEl = document.getElementById('picker-detail-name');
    const pathEl = document.getElementById('picker-detail-path');
    const availEl = document.getElementById('picker-detail-avail');
    const hintEl = document.getElementById('picker-profile-hint');

    if (!opt) return;

    const name = opt.getAttribute('data-name') || opt.text;
    const shortPath = opt.getAttribute('data-shortpath') || opt.value;
    const avail = opt.getAttribute('data-avail') || 'available';

    const lockedNoteEl = document.getElementById('picker-detail-locked-note');

    if (nameEl) nameEl.textContent = name;
    if (pathEl) pathEl.textContent = shortPath;
    if (availEl) {
      if (avail === 'in_use') {
        availEl.textContent = 'In Use by window';
        availEl.className = 'badge badge-warning';
        if (lockedNoteEl) lockedNoteEl.style.display = 'block';
      } else {
        availEl.textContent = 'Available';
        availEl.className = 'badge badge-success';
        if (lockedNoteEl) lockedNoteEl.style.display = 'none';
      }
    }

    if (hintEl) {
      if (opt.value === '__dedicated__') {
        hintEl.textContent = 'Dedicated session keeps WhatsApp data completely isolated (Recommended).';
        hintEl.style.color = 'var(--text-muted)';
      } else if (avail === 'in_use') {
        hintEl.textContent = 'This profile is currently open in another browser window. Close that window or choose Dedicated Session.';
        hintEl.style.color = 'var(--warning)';
      } else {
        hintEl.textContent = 'Profile is available for controlled messaging.';
        hintEl.style.color = 'var(--text-muted)';
      }
    }
  }

  onPickerConfirmChange() {
    const chk = document.getElementById('picker-owner-confirm');
    const btn = document.getElementById('btn-save-profile-selection');
    if (btn) btn.disabled = !chk || !chk.checked;
  }

  async saveProfileSelection() {
    if (this.isSavingProfile) return;

    const bSelect = document.getElementById('picker-browser-select');
    const pSelect = document.getElementById('picker-profile-select');
    const chk = document.getElementById('picker-owner-confirm');
    const btn = document.getElementById('btn-save-profile-selection');

    if (!chk || !chk.checked) {
      this.showToast('Please confirm account ownership to proceed.', 'error');
      return;
    }

    this.isSavingProfile = true;
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Saving...';
    }

    const browserKey = bSelect.value;
    const profileDir = pSelect.value;
    const selectedOption = pSelect.options[pSelect.selectedIndex];
    const profileName = selectedOption ? (selectedOption.getAttribute('data-name') || selectedOption.text) : profileDir;

    const chkRemPicker = document.getElementById('picker-remember-profile');
    const chkAutoPicker = document.getElementById('picker-auto-connect');
    const rememberProfile = chkRemPicker ? chkRemPicker.checked : true;
    const autoConnect = chkAutoPicker ? chkAutoPicker.checked : false;

    this.connPollGen = (this.connPollGen || 0) + 1;

    try {
      const res = await this.api('/api/browser-profile/selection', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          browser: browserKey,
          profile_dir: profileDir,
          profile_name: profileName,
          owner_confirmed: true,
          remember_profile: rememberProfile,
          auto_connect: autoConnect
        }),
        silent: true
      });

      this.closeModal('modal-profile-picker');
      this.showToast(res.message || 'Messaging profile selected and saved.', 'success');
      await this.loadBrowserConnection();
      await this.loadDashboardData();
    } catch (e) {
      const msg = e.action ? `${e.message} ${e.action}` : (e.message || 'Failed to select profile');
      this.showToast(msg, 'error');
    } finally {
      this.isSavingProfile = false;
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Save & Apply Profile';
      }
    }
  }

  async updateProfilePreferences() {
    const chkRem = document.getElementById('chk-remember-profile');
    const chkAuto = document.getElementById('chk-auto-connect');
    const remember = chkRem ? chkRem.checked : true;
    const auto = chkAuto ? chkAuto.checked : false;

    try {
      await this.api('/api/browser-profile/preferences', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          remember_profile: remember,
          auto_connect: auto
        }),
        silent: true
      });
      this.showToast('Profile preferences updated.', 'success');
    } catch (e) {
      this.showToast('Failed to update profile preferences.', 'error');
    }
  }

  async testBrowserConnection() {
    if (this.isTestingConnection) return;
    this.isTestingConnection = true;

    const spinner = document.getElementById('test-conn-spinner');
    const btn = document.getElementById('btn-test-connection');
    const dashBtn = document.getElementById('btn-dash-test-conn');
    const statusMsgEl = document.getElementById('conn-status-message');

    if (spinner) spinner.style.display = 'inline-block';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '<span style="display: inline-block; margin-right: 4px;">⟳</span> Testing session...';
    }
    if (dashBtn) {
      dashBtn.disabled = true;
      dashBtn.textContent = 'Testing...';
    }
    if (statusMsgEl) {
      statusMsgEl.textContent = 'Status: Probing WhatsApp Web session...';
      statusMsgEl.style.color = 'var(--text-secondary)';
    }

    try {
      // Test Connection STRICTLY probes browser session and WhatsApp Web login state.
      // It never queues or dispatches any message.
      const res = await this.api('/api/browser-profile/test', { method: 'POST', silent: true });
      await this.loadBrowserConnection();
      await this.loadDashboardData();

      const isLocked = Boolean(res.is_locked || res.lock_state === 'locked' || res.status === 'Profile in use');
      if (res.prompt_required) {
        this.openModal('modal-confirm-browser-restart');
      } else if (isLocked) {
        // When profile is locked, the connection card displays the inline recovery box.
        // Avoid generic error toast spam.
      } else if (res.reused_session) {
        this.showToast('Active WhatsApp Web session verified and ready!', 'success');
      } else if (res.status === 'Signed in') {
        this.showToast('WhatsApp Web is signed in and ready!', 'success');
      } else if (res.status === 'Needs QR sign-in') {
        this.showToast('Profile needs QR sign-in. Click "Start Session" to scan.', 'warning');
      } else if (res.status === 'Browser unavailable') {
        this.showToast(res.detail || 'Browser executable is unavailable.', 'error');
      } else {
        this.showToast(res.detail || `Connection status: ${res.status}`, 'warning');
      }
    } catch (e) {
      const isLockErr = (e.code === 'PROFILE_IN_USE' || (e.message && e.message.toLowerCase().includes('open in another window')));
      if (e.detail && e.detail.prompt_required) {
        this.openModal('modal-confirm-browser-restart');
      } else if (isLockErr) {
        await this.loadBrowserConnection();
      } else {
        const msg = e.action ? `${e.message} ${e.action}` : (e.message || 'Connection test failed');
        this.showToast(msg, 'error');
      }
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = '<span id="test-conn-spinner" style="display: none; margin-right: 4px;">⟳</span> Test Connection';
      }
      if (dashBtn) {
        dashBtn.disabled = false;
        dashBtn.textContent = 'Test';
      }
      this.isTestingConnection = false;
    }
  }

  async startBrowserSession(forceRestart = false) {
    if (this.isStartingSession) return;
    this.isStartingSession = true;

    const btn = document.getElementById('btn-start-session') || document.getElementById('btn-open-browser');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Starting session...';
    }

    try {
      const res = await this.api('/api/browser-session/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ force_restart: forceRestart }),
        silent: true
      });

      if (res.prompt_required) {
        this.openModal('modal-confirm-browser-restart');
      } else {
        this.showToast(res.message || 'Browser session established.', 'success');
      }
      await this.loadBrowserConnection();
      await this.loadDashboardData();
    } catch (e) {
      if (e.detail && e.detail.prompt_required) {
        this.openModal('modal-confirm-browser-restart');
      } else {
        const msg = e.action ? `${e.message} ${e.action}` : (e.message || 'Failed to start browser session');
        this.showToast(msg, 'error');
      }
      await this.loadBrowserConnection();
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Start Session';
      }
      this.isStartingSession = false;
    }
  }

  async confirmPersonalBrowserRestart() {
    const btn = document.getElementById('btn-confirm-browser-restart');
    if (btn) {
      btn.disabled = true;
      btn.textContent = 'Closing window & starting...';
    }

    try {
      const res = await this.api('/api/browser-session/confirm-restart', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ confirmed: true }),
        silent: true
      });

      this.closeModal('modal-confirm-browser-restart');
      if (res.success) {
        this.showToast('Personal window closed. WhatsApp Web session started!', 'success');
      } else {
        this.showToast(res.message || 'Could not close browser window cleanly.', 'warning');
      }
      await this.loadBrowserConnection();
      await this.loadDashboardData();
    } catch (e) {
      this.showToast(e.message || 'Failed to restart personal browser window', 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.textContent = 'Confirm & Close Window';
      }
    }
  }

  rejectPersonalRestartAndUseDedicated() {
    this.closeModal('modal-confirm-browser-restart');
    this.showToast('Switching to isolated Dedicated WhatsApp Session...', 'info');
    this.disconnectProfile();
  }

  async openSelectedProfile() {
    return this.startBrowserSession();
  }

  async disconnectProfile() {
    if (this.isResettingProfile) return;
    this.isResettingProfile = true;
    this.connPollGen = (this.connPollGen || 0) + 1;

    try {
      const res = await this.api('/api/browser-profile/dedicated', { method: 'POST', silent: true });
      this.showToast('Switched to Dedicated WhatsApp Session (Isolated)', 'info');
      await this.loadBrowserConnection();
      await this.loadDashboardData();
    } catch (e) {
      const msg = e.action ? `${e.message} ${e.action}` : (e.message || 'Failed to switch to dedicated session');
      this.showToast(msg, 'error');
    } finally {
      this.isResettingProfile = false;
    }
  }

  createDedicatedFromEmpty() {
    this.closeModal('modal-profile-picker');
    this.disconnectProfile();
  }

  // --- First-Run Setup Guide ---
  updateFirstRunGuide(kpis, connStatus) {
    const card = document.getElementById('first-run-guide-card');
    if (!card) return;

    if (localStorage.getItem('hide_first_run_guide') === 'true') {
      card.style.display = 'none';
      return;
    }

    // Must be selected and verified (not 'Not checked')
    const isSigned = connStatus?.status === 'Signed in' || connStatus?.status === 'Active';
    const hasProfile = Boolean(connStatus?.profile_dir) && (isSigned || connStatus?.status === 'Needs QR sign-in' || (connStatus?.is_selected && connStatus?.status !== 'Not checked'));
    const hasContacts = (kpis?.total_contacts || 0) > 0;
    const hasTemplate = (kpis?.total_templates || 0) > 0;

    // If all 3 steps are complete, hide the setup guide automatically
    if (hasProfile && hasContacts && hasTemplate) {
      card.style.display = 'none';
      return;
    }

    card.style.display = 'block';

    const setCheck = (stepId, iconId, stepNum, isDone) => {
      const stepEl = document.getElementById(stepId);
      const iconEl = document.getElementById(iconId);
      if (stepEl) {
        stepEl.classList.toggle('done', isDone);
        stepEl.classList.toggle('completed', isDone);
      }
      if (iconEl) {
        if (isDone) {
          iconEl.innerHTML = '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>';
        } else {
          iconEl.textContent = String(stepNum);
        }
      }
    };

    setCheck('chk-step-profile', 'chk-icon-profile', 1, hasProfile);
    setCheck('chk-step-contacts', 'chk-icon-contacts', 2, hasContacts);
    setCheck('chk-step-template', 'chk-icon-template', 3, hasTemplate);
  }

  dismissFirstRunGuide() {
    const card = document.getElementById('first-run-guide-card');
    if (card) card.style.display = 'none';
    localStorage.setItem('hide_first_run_guide', 'true');
    this.showToast('First-run checklist hidden', 'info');
  }

  // --- Test-Send Modal ---
  openTestSendModal() {
    const isConn = this.connectionState && (this.connectionState.status === 'Signed in' || this.connectionState.state === 'connected');
    if (!isConn) {
      this.showToast('Please connect and verify WhatsApp Web is "Signed in" before sending a test message.', 'warning');
      return;
    }
    const content = document.getElementById('msg-content-input')?.value?.trim();
    if (!content && !this.selectedMediaAsset && !this.selectedMediaFile) {
      this.showToast('Please compose a message draft or attach media before sending a test.', 'warning');
      return;
    }
    const previewEl = document.getElementById('test-send-message-preview');
    if (previewEl) previewEl.textContent = content || '(No text body - media only)';

    // Media attachment preview in test send
    const mediaBox = document.getElementById('test-send-media-box');
    const mediaTitle = document.getElementById('test-send-media-title');
    const mediaMeta = document.getElementById('test-send-media-meta');
    const mediaImg = document.getElementById('test-send-media-img');
    const mediaIcon = document.getElementById('test-send-media-icon');

    if (this.selectedMediaAsset) {
      if (mediaBox) mediaBox.style.display = 'flex';
      if (mediaTitle) mediaTitle.textContent = this.selectedMediaAsset.original_filename || this.selectedMediaAsset.title;
      if (mediaMeta) mediaMeta.textContent = `Attached · Dispatched with text caption (${(this.selectedMediaAsset.file_size / 1024).toFixed(0)} KB)`;
      if (this.selectedMediaAsset.mime_type && this.selectedMediaAsset.mime_type.startsWith('image/')) {
        if (mediaImg) {
          mediaImg.src = `/api/media/file/${this.selectedMediaAsset.filename}`;
          mediaImg.style.display = 'block';
        }
        if (mediaIcon) mediaIcon.style.display = 'none';
      } else {
        if (mediaImg) mediaImg.style.display = 'none';
        if (mediaIcon) {
          mediaIcon.style.display = 'inline-block';
          mediaIcon.textContent = (this.selectedMediaAsset.filename || '').endsWith('.pdf') ? '📄' : '📎';
        }
      }
    } else {
      if (mediaBox) mediaBox.style.display = 'none';
    }

    const phoneInput = document.getElementById('test-send-phone');
    if (phoneInput && !phoneInput.value) {
      const cfgCode = document.getElementById('cfg-country-code')?.value?.trim();
      if (cfgCode) phoneInput.value = `+${cfgCode}`;
    }

    this.openModal('modal-test-send');
  }

  async confirmTestSend() {
    const phoneInput = document.getElementById('test-send-phone');
    const phone = phoneInput ? phoneInput.value.trim() : '';
    const content = document.getElementById('msg-content-input')?.value?.trim();

    if (!phone) {
      this.showToast('Please enter a test phone number with country code.', 'error');
      return;
    }
    if (!content && !this.selectedMediaAssetId) {
      this.showToast('Message content or media attachment cannot be empty.', 'error');
      return;
    }

    const spinner = document.getElementById('test-send-spinner');
    const btn = document.getElementById('btn-confirm-test-send');
    if (spinner) spinner.style.display = 'inline-block';
    if (btn) btn.disabled = true;

    try {
      const payload = {
        phone,
        message: content || '',
        media_id: this.selectedMediaAssetId || undefined
      };

      const res = await this.api('/api/browser-profile/test-send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      this.closeModal('modal-test-send');
      const sentDetail = res.media_sent ? 'Test message with media dispatched successfully!' : (res.message || 'Test message dispatched successfully!');
      this.showToast(sentDetail, 'success');
      await this.loadDashboardData();
      if (this.currentTab === 'activity') this.loadActivityData();
    } catch (e) {
      this.showToast(e.message || 'Failed to dispatch test message', 'error');
    } finally {
      if (spinner) spinner.style.display = 'none';
      if (btn) btn.disabled = false;
    }
  }

  async saveSettings() {
    const code = document.getElementById('cfg-country-code').value.trim();
    const minDelay = parseFloat(document.getElementById('cfg-min-delay').value);
    const maxDelay = parseFloat(document.getElementById('cfg-max-delay').value);
    const dailyCap = parseInt(document.getElementById('cfg-daily-cap').value);

    if (maxDelay < minDelay) {
      this.showToast('Max delay must be greater than or equal to min delay', 'error');
      return;
    }

    try {
      await this.api('/api/config', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          default_country_code: code,
          min_delay: minDelay,
          max_delay: maxDelay,
          daily_cap: dailyCap
        })
      });
      this.showToast('Settings saved', 'success');
    } catch (e) {}
  }

  // --- Modal Helpers ---
  openModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.add('active');
  }

  closeModal(modalId) {
    const el = document.getElementById(modalId);
    if (el) el.classList.remove('active');
  }

  // ==========================================================================
  // SECTION: UNIFIED TEMPLATES & BULK MESSAGING WORKFLOW
  // ==========================================================================

  // --- Format file size helper ---
  formatBytes(bytes) {
    if (!bytes || isNaN(bytes) || bytes <= 0) return '0 KB';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
  }

  // --- Load all templates ---
  async loadTemplates(search = '') {
    try {
      const templates = await this.api('/api/templates', { silent: true }).catch(() => []);
      this.cachedTemplates = templates || [];
      this.renderTemplatesGrid(this.cachedTemplates, search);
    } catch (e) {
      console.error('Failed to load templates:', e);
    }
  }

  filterTemplatesList(query = '') {
    const q = (query || (document.getElementById('tpl-search-input') ? document.getElementById('tpl-search-input').value : '')).toLowerCase().trim();
    const grpFilter = document.getElementById('tpl-group-filter') ? document.getElementById('tpl-group-filter').value : 'All';

    let filtered = this.cachedTemplates || [];
    if (q) {
      filtered = filtered.filter(t => (t.name || '').toLowerCase().includes(q) || (t.description || '').toLowerCase().includes(q));
    }
    if (grpFilter && grpFilter !== 'All') {
      filtered = filtered.filter(t => (t.target_group || 'All') === grpFilter);
    }
    this.renderTemplatesGrid(filtered, q, false);
  }

  renderTemplatesGrid(templates, searchQuery = '', updateFilterOptions = true) {
    const emptyState = document.getElementById('templates-empty-state');
    const grid = document.getElementById('templates-grid');
    const groupSelect = document.getElementById('tpl-group-filter');

    if (updateFilterOptions && groupSelect) {
      const groups = new Set(['All']);
      (this.cachedTemplates || []).forEach(t => {
        if (t.target_group) groups.add(t.target_group);
      });
      const cur = groupSelect.value;
      groupSelect.innerHTML = Array.from(groups).map(g => `<option value="${this.escapeHtml(g)}">${this.escapeHtml(g === 'All' ? 'All Audiences' : g)}</option>`).join('');
      if (groups.has(cur)) groupSelect.value = cur;
    }

    if (!templates || templates.length === 0) {
      if (grid) grid.innerHTML = '';
      if (emptyState) {
        emptyState.style.display = 'flex';
        if (searchQuery) {
          emptyState.querySelector('.clean-empty-title').textContent = 'No matching templates';
          emptyState.querySelector('.clean-empty-subtitle').textContent = `No templates match '${searchQuery}'.`;
        } else {
          emptyState.querySelector('.clean-empty-title').textContent = 'No templates yet.';
          emptyState.querySelector('.clean-empty-subtitle').textContent = 'Create your first template to add contacts, images, and messages.';
        }
      }
      return;
    }

    if (emptyState) emptyState.style.display = 'none';
    if (!grid) return;

    grid.innerHTML = templates.map(t => {
      const isMix = t.content_selection_mode === 'mix_variations';
      const modeLabel = isMix ? 'Mix Variations (Randomiser)' : 'Same for Everyone';
      const modeBadgeClass = isMix ? 'badge-primary' : 'badge-neutral';
      const activeTexts = t.active_texts_count !== undefined ? t.active_texts_count : (t.text_variations ? t.text_variations.filter(x => x.is_active).length : 0);
      const activeMedia = t.active_media_count !== undefined ? t.active_media_count : (t.media_assets ? t.media_assets.filter(x => x.is_active).length : 0);
      const eligibleContacts = t.eligible_recipients_count !== undefined ? t.eligible_recipients_count : (t.recipients_count || 0);

      return `
        <div class="template-card" data-template-id="${t.id}">
          <div class="template-card-header">
            <div>
              <h3 class="template-card-title">${this.escapeHtml(t.name || 'Untitled Template')}</h3>
              <p class="template-card-desc">${this.escapeHtml(t.description || 'No description provided')}</p>
            </div>
            <span class="badge ${modeBadgeClass}" style="font-size: 0.72rem;">${modeLabel}</span>
          </div>

          <div class="template-card-stats">
            <div class="template-stat-item" title="Active message variations">
              <span>💬</span>
              <strong>${activeTexts}</strong> variations
            </div>
            <div class="template-stat-item" title="Attached media files">
              <span>📎</span>
              <strong>${activeMedia}</strong> media
            </div>
            <div class="template-stat-item" title="Eligible contacts in audience">
              <span>👥</span>
              <strong>${eligibleContacts}</strong> contacts (${this.escapeHtml(t.target_group || 'All')})
            </div>
          </div>

          <div class="template-card-footer">
            <div style="display: flex; gap: 0.35rem;">
              <button type="button" class="btn btn-primary btn-sm" onclick="app.openTemplateEditor(${t.id})">
                Open / Edit
              </button>
              <button type="button" class="btn btn-secondary btn-sm" onclick="app.openReviewSendModal(${t.id})" title="Review and launch broadcast">
                Review & Send
              </button>
            </div>
            <div style="display: flex; gap: 0.25rem;">
              <button type="button" class="btn btn-subtle btn-xs" onclick="app.duplicateTemplate(${t.id})" title="Duplicate template">
                Copy
              </button>
              <button type="button" class="btn btn-subtle btn-xs" onclick="app.exportTemplate(${t.id})" title="Export template JSON">
                Export
              </button>
              <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.deleteTemplate(${t.id}, '${this.escapeHtml(t.name)}')" title="Delete template">
                Delete
              </button>
            </div>
          </div>
        </div>
      `;
    }).join('');
  }

  // --- Create New Template Modal ---
  openNewTemplateModal() {
    const nameInput = document.getElementById('new-tpl-name');
    const descInput = document.getElementById('new-tpl-desc');
    const modeSelect = document.getElementById('new-tpl-mode');
    const groupSelect = document.getElementById('new-tpl-group');

    if (nameInput) nameInput.value = '';
    if (descInput) descInput.value = '';
    if (modeSelect) modeSelect.value = 'mix_variations';

    if (groupSelect && this.availableGroups) {
      groupSelect.innerHTML = '<option value="All">All Contacts</option>' +
        this.availableGroups.map(g => `<option value="${this.escapeHtml(g.name)}">${this.escapeHtml(g.name)}</option>`).join('');
    }

    this.openModal('modal-new-template');
    setTimeout(() => { if (nameInput) nameInput.focus(); }, 100);
  }

  async submitNewTemplate() {
    const nameInput = document.getElementById('new-tpl-name');
    const descInput = document.getElementById('new-tpl-desc');
    const modeSelect = document.getElementById('new-tpl-mode');
    const groupSelect = document.getElementById('new-tpl-group');

    const name = nameInput ? nameInput.value.trim() : '';
    if (!name) {
      this.showToast('Please enter a template name', 'warning');
      return;
    }

    try {
      const payload = {
        name: name,
        description: descInput ? descInput.value.trim() : '',
        content: 'Hello {first_name}, ',
        content_selection_mode: modeSelect ? modeSelect.value : 'mix_variations',
        target_group: groupSelect ? groupSelect.value : 'All'
      };

      const res = await this.api('/api/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      this.closeModal('modal-new-template');
      this.showToast(`Template '${name}' created!`, 'success');
      await this.loadTemplates();
      if (res && res.id) {
        await this.openTemplateEditor(res.id);
      }
    } catch (e) {
      console.error('Failed to create template:', e);
    }
  }

  // --- Import Template ---
  openImportTemplateModal() {
    const fileInput = document.getElementById('import-tpl-file');
    const jsonInput = document.getElementById('import-tpl-json');
    if (fileInput) fileInput.value = '';
    if (jsonInput) jsonInput.value = '';
    this.openModal('modal-import-template');
  }

  onTemplateFileSelected(event) {
    const file = event.target.files && event.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      const jsonInput = document.getElementById('import-tpl-json');
      if (jsonInput) jsonInput.value = e.target.result;
    };
    reader.readAsText(file);
  }

  async submitImportTemplate() {
    const jsonInput = document.getElementById('import-tpl-json');
    const raw = jsonInput ? jsonInput.value.trim() : '';
    if (!raw) {
      this.showToast('Please select a JSON file or paste JSON content', 'warning');
      return;
    }

    try {
      const parsed = JSON.parse(raw);
      const res = await this.api('/api/templates/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(parsed)
      });

      this.closeModal('modal-import-template');
      this.showToast(`Template '${res.name}' imported successfully!`, 'success');
      await this.loadTemplates();
      if (res.id) {
        await this.openTemplateEditor(res.id);
      }
    } catch (e) {
      this.showToast(`Import failed: ${e.message}`, 'error');
    }
  }

  // --- Export Template ---
  async exportTemplate(templateId) {
    try {
      const t = await this.api(`/api/templates/${templateId}/export`);
      const blob = new Blob([JSON.stringify(t, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `template_${(t.name || 'export').replace(/\s+/g, '_').toLowerCase()}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      this.showToast(`Exported template '${t.name}'`, 'info');
    } catch (e) {
      console.error('Failed to export template:', e);
    }
  }

  // --- Duplicate Template ---
  async duplicateTemplate(templateId) {
    try {
      const res = await this.api(`/api/templates/${templateId}/duplicate`, { method: 'POST' });
      this.showToast(`Duplicated to '${res.name}'`, 'success');
      await this.loadTemplates();
      if (res.id) {
        await this.openTemplateEditor(res.id);
      }
    } catch (e) {
      console.error('Failed to duplicate template:', e);
    }
  }

  // --- Delete Template ---
  async deleteTemplate(templateId, name) {
    const ok = await this.confirmDialog({
      title: 'Delete Template',
      message: `Are you sure you want to delete template '${name}'?`,
      details: 'Historical campaign reports and sent message logs will be safely preserved.',
      confirmText: 'Delete Template',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    try {
      await this.api(`/api/templates/${templateId}`, { method: 'DELETE' });
      this.showToast(`Template '${name}' deleted`, 'info');
      await this.loadTemplates();
      if (this.activeTemplateId === templateId) {
        this.closeTemplateEditor();
      }
    } catch (e) {
      console.error('Failed to delete template:', e);
    }
  }

  // --- Open Template Editor ---
  async openTemplateEditor(templateId) {
    try {
      this.activeTemplateId = templateId;
      const t = await this.api(`/api/templates/${templateId}`);
      this.activeTemplate = t;

      const listView = document.getElementById('template-list-view');
      const editorView = document.getElementById('template-editor-view');
      if (listView) listView.style.display = 'none';
      if (editorView) editorView.style.display = 'block';

      // 1. Populate topbar
      const nameInput = document.getElementById('tpl-edit-name-input');
      if (nameInput) nameInput.value = t.name || '';

      const formatSelect = document.getElementById('tpl-message-format-select');
      if (formatSelect) formatSelect.value = t.message_format || 'image_with_caption';

      const mode = t.content_selection_mode || 'mix_variations';
      const btnMix = document.getElementById('btn-mode-mix');
      const btnSame = document.getElementById('btn-mode-same');
      if (btnMix) btnMix.classList.toggle('active', mode === 'mix_variations');
      if (btnSame) btnSame.classList.toggle('active', mode === 'same_for_everyone');

      this.isTemplateDirty = false;
      this.setTemplateSaveStatus('saved');
      this.updateTemplateEditorConnectionPill();

      // 2. Render Sections
      await this.renderTemplateContacts(t);
      this.renderTemplateMedia(t);
      this.renderTemplateTexts(t);

      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e) {
      console.error('Failed to open template editor:', e);
      this.showToast('Could not load template details', 'error');
    }
  }

  closeTemplateEditor() {
    this.activeTemplateId = null;
    this.activeTemplate = null;
    this.isTemplateDirty = false;
    const listView = document.getElementById('template-list-view');
    const editorView = document.getElementById('template-editor-view');
    if (listView) listView.style.display = 'block';
    if (editorView) editorView.style.display = 'none';
    this.loadTemplates();
  }

  updateTemplateEditorConnectionPill() {
    const pill = document.getElementById('tpl-editor-conn-pill');
    const dot = document.getElementById('tpl-editor-conn-dot');
    const text = document.getElementById('tpl-editor-conn-text');
    if (!pill || !dot || !text) return;

    const conn = this.connectionState || {};
    const state = conn.state || this.currentSessionState || 'not_checked';
    const isConnected = state === 'connected' || this.isWhatsAppConnected;

    if (isConnected) {
      dot.className = 'status-indicator online';
      text.textContent = 'WhatsApp: Connected';
      pill.style.borderColor = 'rgba(16, 185, 129, 0.4)';
      pill.title = 'WhatsApp Web is authenticated and ready. Click to view Settings.';
    } else if (state === 'waiting_for_qr') {
      dot.className = 'status-indicator warning';
      text.textContent = 'WhatsApp: Scan QR';
      pill.style.borderColor = 'rgba(245, 158, 11, 0.4)';
      pill.title = 'WhatsApp requires device pairing QR scan. Click to view Settings.';
    } else if (state === 'unsupported_profile' || (conn.preferred_profile && conn.preferred_profile.is_supported === false && !isConnected)) {
      dot.className = 'status-indicator offline';
      text.textContent = 'Cannot be automated';
      pill.style.borderColor = 'rgba(239, 68, 68, 0.4)';
      pill.title = 'Selected profile cannot be automated under Chrome 136+ security rules. Use persistent Relay session.';
    } else if (state === 'profile_locked' || state === 'browser_running') {
      dot.className = 'status-indicator warning';
      text.textContent = 'Browser: Open elsewhere';
      pill.style.borderColor = 'rgba(245, 158, 11, 0.4)';
      pill.title = 'Selected profile is running in another window. Click to view Settings.';
    } else if (state === 'not_checked' || !this.connectionState) {
      dot.className = 'status-indicator neutral';
      text.textContent = 'Checking connection...';
      pill.style.borderColor = 'var(--border-color)';
      pill.title = 'Verifying WhatsApp Web connection status...';
    } else {
      dot.className = 'status-indicator offline';
      text.textContent = 'WhatsApp: Not connected';
      pill.style.borderColor = 'rgba(239, 68, 68, 0.4)';
      pill.title = 'WhatsApp session is not active. Click to configure in Settings.';
    }
  }

  markTemplateDirty() {
    this.isTemplateDirty = true;
    this.setTemplateSaveStatus('dirty');

    // Debounced automatic save (1500ms after user pauses editing)
    if (this._templateAutoSaveTimer) {
      clearTimeout(this._templateAutoSaveTimer);
    }
    this._templateAutoSaveTimer = setTimeout(() => {
      if (this.isTemplateDirty && this.activeTemplateId) {
        this.saveActiveTemplate(true);
      }
    }, 1500);
  }

  setTemplateSaveStatus(status) {
    const badge = document.getElementById('tpl-save-status-badge');
    const btn = document.getElementById('btn-save-template');
    if (!badge) return;

    if (status === 'dirty') {
      badge.className = 'badge badge-warning';
      badge.textContent = 'Unsaved changes';
      badge.style.display = 'inline-block';
      if (btn) btn.disabled = false;
    } else if (status === 'saving') {
      badge.className = 'badge badge-info';
      badge.textContent = 'Saving...';
      badge.style.display = 'inline-block';
      if (btn) btn.disabled = true;
    } else if (status === 'saved') {
      badge.className = 'badge badge-success';
      const timeStr = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      badge.textContent = `Saved (${timeStr})`;
      badge.style.display = 'inline-block';
      if (btn) btn.disabled = false;
    } else if (status === 'error') {
      badge.className = 'badge badge-danger';
      badge.textContent = 'Save failed — Retry';
      badge.style.display = 'inline-block';
      if (btn) btn.disabled = false;
    }
  }

  async saveActiveTemplate(isAutoSave = false) {
    if (!this.activeTemplateId) return false;
    if (this._templateAutoSaveTimer) {
      clearTimeout(this._templateAutoSaveTimer);
      this._templateAutoSaveTimer = null;
    }

    this.templateSaveGeneration = (this.templateSaveGeneration || 0) + 1;
    const currentGen = this.templateSaveGeneration;
    this.setTemplateSaveStatus('saving');

    try {
      const nameInput = document.getElementById('tpl-edit-name-input');
      const formatSelect = document.getElementById('tpl-message-format-select');
      const groupSelect = document.getElementById('tpl-contact-group-select');

      const name = nameInput ? nameInput.value.trim() : (this.activeTemplate ? this.activeTemplate.name : 'Untitled Template');
      const message_format = formatSelect ? formatSelect.value : 'image_with_caption';
      const target_group = groupSelect ? groupSelect.value : (this.activeTemplate ? this.activeTemplate.target_group : 'All');
      const mode = (this.activeTemplate && this.activeTemplate.content_selection_mode) || 'mix_variations';

      // Harvest text variations directly from DOM to avoid stale blur data
      const texts = [];
      if (this.activeTemplate && this.activeTemplate.text_variations) {
        for (const tv of this.activeTemplate.text_variations) {
          const textarea = document.getElementById(`tpl-var-text-${tv.id}`);
          const content = textarea ? textarea.value : tv.content;
          texts.push({
            id: tv.id,
            content: content,
            is_active: tv.is_active !== undefined ? tv.is_active : 1
          });
        }
      }

      // Harvest media assets
      const media = (this.activeTemplate && this.activeTemplate.media_assets) || [];

      // Harvest excluded contacts
      const excludedIds = [];
      if (this.allTemplateContacts && this.templateSelectedContactIds) {
        for (const c of this.allTemplateContacts) {
          if (!this.templateSelectedContactIds.has(c.id)) {
            excludedIds.push(c.id);
          }
        }
      }

      const payload = {
        name: name,
        description: (this.activeTemplate && this.activeTemplate.description) || '',
        content_selection_mode: mode,
        message_format: message_format,
        target_group: target_group,
        pacing_delay_min: (this.activeTemplate && this.activeTemplate.pacing_delay_min) || 8,
        pacing_delay_max: (this.activeTemplate && this.activeTemplate.pacing_delay_max) || 16,
        text_variations: texts,
        media_assets: media.map(m => ({ id: m.id, is_active: m.is_active !== 0 ? 1 : 0 })),
        excluded_contact_ids: excludedIds
      };

      const res = await this.api(`/api/templates/${this.activeTemplateId}/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });

      if (currentGen !== this.templateSaveGeneration) {
        // Discard stale response if newer edits occurred while saving
        return true;
      }

      if (res && res.template) {
        this.activeTemplate = res.template;
      }
      this.isTemplateDirty = false;
      this.setTemplateSaveStatus('saved');
      if (!isAutoSave) {
        this.showToast('Template saved', 'success');
      }
      return true;
    } catch (e) {
      if (currentGen === this.templateSaveGeneration) {
        console.error('Failed to save template:', e);
        this.setTemplateSaveStatus('error');
        const detailMsg = e.detail || e.message || 'Server returned an error';
        this.showToast(`Failed to save template: ${detailMsg}`, 'error');
      }
      return false;
    }
  }

  async saveActiveTemplateMeta() {
    return this.saveActiveTemplate();
  }

  async setActiveTemplateMode(mode) {
    if (!this.activeTemplateId) return;
    try {
      await this.api(`/api/templates/${this.activeTemplateId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content_selection_mode: mode })
      });
      if (this.activeTemplate) this.activeTemplate.content_selection_mode = mode;

      const btnMix = document.getElementById('btn-mode-mix');
      const btnSame = document.getElementById('btn-mode-same');
      if (btnMix) btnMix.classList.toggle('active', mode === 'mix_variations');
      if (btnSame) btnSame.classList.toggle('active', mode === 'same_for_everyone');

      const label = mode === 'mix_variations' ? 'Mix Variations (1 media + 1 text assigned per recipient)' : 'Same for Everyone (1 media + 1 text to all)';
      this.showToast(`Content selection set to: ${label}`, 'info');
    } catch (e) {
      console.error('Failed to set template mode:', e);
    }
  }

  async duplicateActiveTemplate() {
    if (this.activeTemplateId) {
      await this.duplicateTemplate(this.activeTemplateId);
    }
  }

  async deleteActiveTemplate() {
    if (this.activeTemplateId && this.activeTemplate) {
      await this.deleteTemplate(this.activeTemplateId, this.activeTemplate.name);
    }
  }

  // ==========================================================================
  // SECTION A: CONTACTS IN TEMPLATE EDITOR
  // ==========================================================================
  async onTemplateAudienceChange(groupName) {
    if (!this.activeTemplateId) return;
    try {
      await this.api(`/api/templates/${this.activeTemplateId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_group: groupName })
      });
      if (this.activeTemplate) this.activeTemplate.target_group = groupName;
      await this.renderTemplateContacts(this.activeTemplate);
    } catch (e) {
      console.error('Failed to update audience group:', e);
    }
  }

  async renderTemplateContacts(template) {
    const groupSelect = document.getElementById('tpl-contact-group-select');
    if (groupSelect) {
      const groups = await this.api('/api/contacts/groups', { silent: true }).catch(() => []);
      this.availableGroups = groups || [];
      groupSelect.innerHTML = '<option value="All">All Contacts</option>' +
        groups.map(g => `<option value="${this.escapeHtml(g.name)}" ${template.target_group === g.name ? 'selected' : ''}>${this.escapeHtml(g.name)} (${g.contact_count || 0})</option>`).join('');
    }

    const targetGrp = template.target_group || 'All';
    const resp = await this.api(`/api/contacts?limit=5000${targetGrp !== 'All' ? '&group_name=' + encodeURIComponent(targetGrp) : ''}`, { silent: true }).catch(() => []);
    const contacts = Array.isArray(resp) ? resp : (resp && resp.items ? resp.items : []);
    this.allTemplateContacts = contacts || [];

    const total = contacts.length;
    const eligible = contacts.filter(c => c.consent_status !== 'opted_out');
    const excluded = total - eligible.length;

    // Default select all eligible
    this.templateSelectedContactIds = new Set(eligible.map(c => c.id));

    const cntTotal = document.getElementById('tpl-cnt-total');
    const cntEligible = document.getElementById('tpl-cnt-eligible');
    const cntExcluded = document.getElementById('tpl-cnt-excluded');
    const cntIncluded = document.getElementById('tpl-cnt-included');

    if (cntTotal) cntTotal.textContent = total;
    if (cntEligible) cntEligible.textContent = eligible.length;
    if (cntExcluded) cntExcluded.textContent = excluded;
    if (cntIncluded) cntIncluded.textContent = this.templateSelectedContactIds.size;

    this.renderTemplateContactsTable(contacts);
  }

  filterTemplateContacts(search = '') {
    const q = (search || (document.getElementById('tpl-contacts-search') ? document.getElementById('tpl-contacts-search').value : '')).toLowerCase().trim();
    let filtered = this.allTemplateContacts || [];
    if (q) {
      filtered = filtered.filter(c => (c.name || '').toLowerCase().includes(q) || (c.phone || '').includes(q));
    }
    this.renderTemplateContactsTable(filtered);
  }

  renderTemplateContactsTable(contacts) {
    const tbody = document.getElementById('tpl-contacts-tbody');
    const masterChk = document.getElementById('chk-master-tpl-contacts');
    if (!tbody) return;

    if (!contacts || contacts.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No contacts found in selected audience. Click 'Import CSV/Excel' or 'Paste Numbers' to add contacts.</td></tr>`;
      if (masterChk) { masterChk.checked = false; masterChk.indeterminate = false; }
      return;
    }

    let allChecked = true;
    let someChecked = false;

    tbody.innerHTML = contacts.map(c => {
      const isChecked = this.templateSelectedContactIds.has(c.id);
      const isOptedOut = c.consent_status === 'opted_out';
      if (isChecked) someChecked = true;
      else allChecked = false;

      const consentBadge = isOptedOut
        ? `<span class="badge badge-warning" style="font-size: 0.7rem;">Opted Out</span>`
        : `<span class="badge badge-success" style="font-size: 0.7rem;">Opted In</span>`;

      return `
        <tr style="${isOptedOut ? 'opacity: 0.6;' : ''}">
          <td style="text-align: center;">
            <input type="checkbox" style="cursor: pointer; accent-color: var(--primary);" ${isChecked ? 'checked' : ''} onchange="app.toggleTemplateContact(${c.id}, this.checked)">
          </td>
          <td><strong>${this.escapeHtml(c.name || 'Unnamed')}</strong></td>
          <td style="font-family: var(--font-mono); font-size: 0.75rem;">+${this.escapeHtml(c.phone || '')}</td>
          <td><span class="badge badge-neutral" style="font-size: 0.7rem;">${this.escapeHtml(c.group_name || 'Default')}</span></td>
          <td>${consentBadge}</td>
        </tr>
      `;
    }).join('');

    if (masterChk) {
      masterChk.checked = allChecked && contacts.length > 0;
      masterChk.indeterminate = someChecked && !allChecked;
    }
  }

  toggleTemplateContact(contactId, checked) {
    if (checked) {
      this.templateSelectedContactIds.add(contactId);
    } else {
      this.templateSelectedContactIds.delete(contactId);
    }
    const cntIncluded = document.getElementById('tpl-cnt-included');
    if (cntIncluded) cntIncluded.textContent = this.templateSelectedContactIds.size;

    const masterChk = document.getElementById('chk-master-tpl-contacts');
    if (masterChk) {
      const total = (this.allTemplateContacts || []).length;
      const sel = this.templateSelectedContactIds.size;
      masterChk.checked = sel > 0 && sel === total;
      masterChk.indeterminate = sel > 0 && sel < total;
    }
  }

  toggleMasterTemplateContacts(checked) {
    this.selectAllTemplateContacts(checked);
  }

  selectAllTemplateContacts(selectAll) {
    if (selectAll) {
      (this.allTemplateContacts || []).forEach(c => {
        if (c.consent_status !== 'opted_out') this.templateSelectedContactIds.add(c.id);
      });
    } else {
      this.templateSelectedContactIds.clear();
    }
    const cntIncluded = document.getElementById('tpl-cnt-included');
    if (cntIncluded) cntIncluded.textContent = this.templateSelectedContactIds.size;
    this.renderTemplateContactsTable(this.allTemplateContacts || []);
  }

  // ==========================================================================
  // SECTION B: MEDIA ASSETS IN TEMPLATE EDITOR
  // ==========================================================================
  renderTemplateMedia(template) {
    const grid = document.getElementById('tpl-media-grid');
    const badge = document.getElementById('tpl-media-count-badge');
    const emptyNotice = document.getElementById('tpl-media-empty-notice');
    const bulkBar = document.getElementById('tpl-media-bulk-bar');

    const assets = template.media_assets || [];
    if (badge) badge.textContent = `${assets.length} assets`;

    this.templateSelectedMediaIds.clear();
    if (bulkBar) bulkBar.style.display = 'none';

    if (assets.length === 0) {
      if (grid) grid.innerHTML = '';
      if (emptyNotice) emptyNotice.style.display = 'block';
      return;
    }

    if (emptyNotice) emptyNotice.style.display = 'none';
    if (!grid) return;

    grid.innerHTML = assets.map(m => {
      const isExcluded = m.is_active === 0;
      const isSelected = this.templateSelectedMediaIds.has(m.id);
      const isImg = (m.mime_type || '').startsWith('image/');
      const isVid = (m.mime_type || '').startsWith('video/');
      const isPdf = (m.mime_type || '') === 'application/pdf';

      let thumbMarkup = '';
      if (isImg && m.id) {
        thumbMarkup = `<img src="/api/media/${m.id}/file" alt="${this.escapeHtml(m.filename)}" style="cursor: pointer;" onclick="app.openMediaPreviewModal(${m.id})">`;
      } else {
        const icon = isPdf ? '📄 PDF' : (isVid ? '🎬 Video' : '📎 File');
        thumbMarkup = `<div style="font-weight: 700; color: var(--text-muted); cursor: pointer;" onclick="app.openMediaPreviewModal(${m.id})">${icon}</div>`;
      }

      return `
        <div class="media-set-card-item ${isExcluded ? 'excluded' : ''} ${isSelected ? 'selected' : ''}" id="tpl-media-card-${m.id}">
          <div class="media-set-card-header">
            <input type="checkbox" title="Select for bulk actions" style="cursor: pointer; accent-color: var(--primary);" ${isSelected ? 'checked' : ''} onchange="app.toggleSelectTemplateMedia(${m.id}, this.checked)">
            <button type="button" class="media-active-pill ${!isExcluded ? 'active' : 'excluded'}" onclick="app.toggleTemplateMediaActive(${m.id}, ${isExcluded ? 'true' : 'false'})" title="${!isExcluded ? 'Click to exclude from rotation' : 'Click to include in rotation'}">
              <span>${!isExcluded ? '● Active' : '○ Excluded'}</span>
            </button>
          </div>

          <div class="media-set-thumb-box">
            ${thumbMarkup}
          </div>

          <div class="media-set-card-title" title="${this.escapeHtml(m.filename)}">
            ${this.escapeHtml(m.filename)}
          </div>

          <div class="media-set-card-meta">
            <span>${this.formatBytes(m.file_size)}</span>
            <span>${(m.mime_type || '').split('/')[1]?.toUpperCase() || 'FILE'}</span>
          </div>

          <div class="media-set-card-actions">
            <button type="button" class="btn btn-subtle btn-xs" onclick="app.openMediaPreviewModal(${m.id})">Preview</button>
            <button type="button" class="btn btn-subtle btn-xs" onclick="app.removeMediaFromTemplate(${m.id})" title="Remove from this template">Remove</button>
          </div>
        </div>
      `;
    }).join('');
  }

  async onTemplateMediaFilesSelected(e) {
    const files = e.target.files;
    if (!files || files.length === 0 || !this.activeTemplateId) return;

    const assetIds = [];
    for (let i = 0; i < files.length; i++) {
      const file = files[i];
      const formData = new FormData();
      formData.append('file', file);
      formData.append('title', file.name || 'Image');
      try {
        const res = await fetch('/api/media/upload', { method: 'POST', body: formData });
        if (res.ok) {
          const data = await res.json();
          if (data.id) assetIds.push(data.id);
        }
      } catch (err) {
        console.error('File upload failed:', err);
      }
    }

    if (assetIds.length > 0) {
      await this.api(`/api/templates/${this.activeTemplateId}/media`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_ids: assetIds, media_asset_ids: assetIds })
      });
      this.showToast(`Attached ${assetIds.length} media file(s) to template`, 'success');
      const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
      this.activeTemplate = updated;
      this.renderTemplateMedia(updated);
    }
    e.target.value = '';
  }

  async openTemplateMediaPickerModal() {
    try {
      const assets = await this.api('/api/media', { silent: true }).catch(() => []);
      const pickerList = document.getElementById('tpl-media-picker-list');
      if (!pickerList) return;

      this.pickerSelectedAssetIds = new Set();
      const existingIds = new Set((this.activeTemplate && this.activeTemplate.media_assets || []).map(m => m.id));

      if (!assets || assets.length === 0) {
        pickerList.innerHTML = `<div style="text-align: center; padding: 2rem; color: var(--text-muted);">No uploaded media found in library. Use '+ Upload Media' to add files.</div>`;
      } else {
        pickerList.innerHTML = `
          <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 0.75rem;">
            ${assets.map(a => {
              const alreadyAttached = existingIds.has(a.id);
              const isImg = (a.mime_type || '').startsWith('image/');
              return `
                <div style="border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 0.5rem; background: var(--bg-surface); opacity: ${alreadyAttached ? '0.5' : '1'};">
                  <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.35rem;">
                    <input type="checkbox" style="cursor: pointer; accent-color: var(--primary);" ${alreadyAttached ? 'disabled checked' : ''} onchange="app.togglePickerAsset(${a.id}, this.checked)">
                    <span style="font-size: 0.65rem; color: var(--text-muted);">${alreadyAttached ? 'Attached' : ''}</span>
                  </div>
                  <div style="width: 100%; height: 75px; background: var(--surface-subtle); display: flex; align-items: center; justify-content: center; overflow: hidden; border-radius: var(--radius-xs);">
                    ${isImg ? `<img src="/api/media/${a.id}/file" style="width: 100%; height: 100%; object-fit: cover;">` : `<span>📎</span>`}
                  </div>
                  <div style="font-size: 0.72rem; font-weight: 600; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; margin-top: 0.25rem;">
                    ${this.escapeHtml(a.filename)}
                  </div>
                </div>
              `;
            }).join('')}
          </div>
        `;
      }

      this.openModal('modal-template-media-picker');
    } catch (e) {
      console.error('Failed to open media picker:', e);
    }
  }

  togglePickerAsset(assetId, checked) {
    this.pickerSelectedAssetIds = this.pickerSelectedAssetIds || new Set();
    if (checked) this.pickerSelectedAssetIds.add(assetId);
    else this.pickerSelectedAssetIds.delete(assetId);

    const countLabel = document.getElementById('tpl-media-picker-selected-count');
    if (countLabel) countLabel.textContent = `${this.pickerSelectedAssetIds.size} selected`;
  }

  async confirmAddMediaToTemplate() {
    if (!this.pickerSelectedAssetIds || this.pickerSelectedAssetIds.size === 0 || !this.activeTemplateId) {
      this.closeModal('modal-template-media-picker');
      return;
    }

    try {
      const arr = Array.from(this.pickerSelectedAssetIds);
      await this.api(`/api/templates/${this.activeTemplateId}/media`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_ids: arr, media_asset_ids: arr })
      });
      this.closeModal('modal-template-media-picker');
      this.showToast(`Attached ${this.pickerSelectedAssetIds.size} media files`, 'success');
      const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
      this.activeTemplate = updated;
      this.renderTemplateMedia(updated);
    } catch (e) {
      console.error('Failed to add media to template:', e);
    }
  }

  async toggleTemplateMediaActive(assetId, isActive) {
    if (!this.activeTemplateId) return;
    try {
      await this.api(`/api/templates/${this.activeTemplateId}/media/${assetId}/toggle`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: isActive ? 1 : 0 })
      });
      const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
      this.activeTemplate = updated;
      this.renderTemplateMedia(updated);
      this.showToast(isActive ? 'Media included in rotation' : 'Media temporarily excluded', 'info');
    } catch (e) {
      console.error('Failed to toggle media active state:', e);
    }
  }

  async removeMediaFromTemplate(assetId) {
    if (!this.activeTemplateId) return;
    try {
      const currentTplId = this.activeTemplateId;
      await this.api(`/api/templates/${currentTplId}/media/${assetId}`, { method: 'DELETE' });
      this.showToastWithAction('Removed from template', 'Undo', async () => {
        try {
          await this.api(`/api/templates/${currentTplId}/media`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ asset_ids: [assetId], media_asset_ids: [assetId] })
          });
          const reloaded = await this.api(`/api/templates/${currentTplId}`);
          this.activeTemplate = reloaded;
          this.renderTemplateMedia(reloaded);
          this.showToast('Restored media to template', 'success');
        } catch (err) {
          console.error('Failed to undo media removal:', err);
        }
      }, 'info');
      const updated = await this.api(`/api/templates/${currentTplId}`);
      this.activeTemplate = updated;
      this.renderTemplateMedia(updated);
    } catch (e) {
      console.error('Failed to remove media:', e);
    }
  }

  async deleteMediaPermanently(assetId, filename) {
    const ok = await this.confirmDialog({
      title: 'Delete Media Permanently',
      message: `Are you sure you want to permanently delete "${filename}"?`,
      details: 'This will remove the file from your disk and delete it from all templates and library.',
      confirmText: 'Delete Permanently',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    try {
      await this.api(`/api/media/${assetId}?force=true`, { method: 'DELETE' });
      this.showToast(`Deleted "${filename}" permanently`, 'info');
      if (this.activeTemplateId) {
        const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
        this.activeTemplate = updated;
        this.renderTemplateMedia(updated);
      }
      if (this.currentTab === 'media') {
        this.loadMediaLibrary(this.mediaLibraryFilter || 'all');
      }
    } catch (e) {
      console.error('Failed to delete media asset:', e);
    }
  }

  toggleSelectTemplateMedia(assetId, checked) {
    if (checked) this.templateSelectedMediaIds.add(assetId);
    else this.templateSelectedMediaIds.delete(assetId);

    const bulkBar = document.getElementById('tpl-media-bulk-bar');
    const countLabel = document.getElementById('tpl-media-bulk-count');
    if (bulkBar && countLabel) {
      const size = this.templateSelectedMediaIds.size;
      bulkBar.style.display = size > 0 ? 'flex' : 'none';
      countLabel.textContent = `${size} selected`;
    }
  }

  clearTemplateMediaSelection() {
    this.templateSelectedMediaIds.clear();
    const bulkBar = document.getElementById('tpl-media-bulk-bar');
    if (bulkBar) bulkBar.style.display = 'none';
    if (this.activeTemplate) this.renderTemplateMedia(this.activeTemplate);
  }

  async bulkToggleTemplateMedia(include) {
    if (!this.activeTemplateId || this.templateSelectedMediaIds.size === 0) return;
    for (const aid of Array.from(this.templateSelectedMediaIds)) {
      await this.api(`/api/templates/${this.activeTemplateId}/media/${aid}/toggle`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: include ? 1 : 0 })
      });
    }
    this.showToast(`Updated ${this.templateSelectedMediaIds.size} media items`, 'info');
    const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
    this.activeTemplate = updated;
    this.renderTemplateMedia(updated);
  }

  async bulkRemoveTemplateMedia() {
    if (!this.activeTemplateId || this.templateSelectedMediaIds.size === 0) return;
    for (const aid of Array.from(this.templateSelectedMediaIds)) {
      await this.api(`/api/templates/${this.activeTemplateId}/media/${aid}`, { method: 'DELETE' });
    }
    this.showToast(`Removed ${this.templateSelectedMediaIds.size} items from template`, 'info');
    const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
    this.activeTemplate = updated;
    this.renderTemplateMedia(updated);
  }

  async bulkDeleteTemplateMediaPermanently() {
    if (this.templateSelectedMediaIds.size === 0) return;
    const ok = await this.confirmDialog({
      title: 'Delete Media Files Permanently',
      message: `Are you sure you want to permanently delete ${this.templateSelectedMediaIds.size} media file(s)?`,
      details: 'This will remove the files from your disk and database permanently. This action cannot be undone.',
      confirmText: `Delete ${this.templateSelectedMediaIds.size} Files`,
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    const ids = Array.from(this.templateSelectedMediaIds);
    await this.api('/api/media/bulk-delete', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset_ids: ids, force: true })
    });
    this.showToast(`Deleted ${ids.length} files permanently`, 'info');
    const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
    this.activeTemplate = updated;
    this.renderTemplateMedia(updated);
  }

  // --- Open Media Preview Modal ---
  async openMediaPreviewModal(assetId) {
    try {
      const asset = await this.api(`/api/media/${assetId}`);
      const titleEl = document.getElementById('media-preview-title');
      const metaEl = document.getElementById('media-preview-meta');
      const contentEl = document.getElementById('media-preview-content');

      if (titleEl) titleEl.textContent = asset.filename || 'Media Preview';
      if (metaEl) metaEl.textContent = `${this.formatBytes(asset.file_size)} · ${asset.mime_type || 'Unknown'}`;

      if (contentEl) {
        const isImg = (asset.mime_type || '').startsWith('image/');
        const isVid = (asset.mime_type || '').startsWith('video/');
        const isPdf = (asset.mime_type || '') === 'application/pdf';

        if (isImg) {
          contentEl.innerHTML = `<img src="/api/media/${asset.id}/file" style="max-width: 100%; max-height: 480px; border-radius: var(--radius-sm); object-fit: contain;">`;
        } else if (isVid) {
          contentEl.innerHTML = `<video controls src="/api/media/${asset.id}/file" style="max-width: 100%; max-height: 480px; border-radius: var(--radius-sm);"></video>`;
        } else if (isPdf) {
          contentEl.innerHTML = `
            <div style="padding: 2rem; background: var(--surface-subtle); border-radius: var(--radius-sm);">
              <div style="font-size: 2.5rem; margin-bottom: 0.5rem;">📄</div>
              <strong>${this.escapeHtml(asset.filename)}</strong>
              <div style="margin-top: 1rem;">
                <a href="/api/media/${asset.id}/file" target="_blank" class="btn btn-primary btn-sm">Open Document in Browser</a>
              </div>
            </div>
          `;
        } else {
          contentEl.innerHTML = `<div>Attachment: ${this.escapeHtml(asset.filename)}</div>`;
        }
      }

      this.openModal('modal-media-preview');
    } catch (e) {
      console.error('Failed to preview media:', e);
    }
  }

  // ==========================================================================
  // SECTION C: TEXT VARIATIONS IN TEMPLATE EDITOR
  // ==========================================================================
  renderTemplateTexts(template) {
    const list = document.getElementById('tpl-texts-list');
    const badge = document.getElementById('tpl-texts-count-badge');
    const emptyNotice = document.getElementById('tpl-texts-empty-notice');

    const texts = template.text_variations || [];
    if (badge) badge.textContent = `${texts.length} messages`;

    if (texts.length === 0) {
      if (list) list.innerHTML = '';
      if (emptyNotice) emptyNotice.style.display = 'block';
      return;
    }

    if (emptyNotice) emptyNotice.style.display = 'none';
    if (!list) return;

    list.innerHTML = texts.map((t, idx) => {
      const isExcluded = t.is_active === 0;
      const charCount = (t.content || '').length;

      return `
        <div class="variation-card ${isExcluded ? 'excluded' : ''}" id="tpl-var-card-${t.id}">
          <div class="variation-card-header">
            <div style="display: flex; align-items: center; gap: 0.5rem; flex: 1; flex-wrap: wrap;">
              <label style="display: inline-flex; align-items: center; gap: 0.35rem; font-size: 0.78rem; cursor: pointer; user-select: none;">
                <input type="checkbox" ${!isExcluded ? 'checked' : ''} style="cursor: pointer; accent-color: var(--primary);" onchange="app.toggleTextVariationActive(${t.id}, this.checked)">
                <strong style="color: ${!isExcluded ? 'var(--primary)' : 'var(--text-muted)'};">${!isExcluded ? 'Active' : 'Excluded'}</strong>
              </label>
              <input type="text" class="form-input" value="${this.escapeHtml(t.label || `Variation ${idx + 1}`)}" placeholder="Variation Label" style="max-width: 170px; font-size: 0.78rem; padding: 0.2rem 0.5rem;" onblur="app.updateTextVariation(${t.id}, 'label', this.value)">
              <span class="badge badge-neutral" style="font-size: 0.7rem;" id="tpl-char-cnt-${t.id}">${charCount} chars</span>
            </div>

            <div style="display: flex; align-items: center; gap: 0.35rem; flex-wrap: wrap;">
              <button type="button" class="btn btn-secondary btn-xs" onclick="app.insertVarIntoActiveVariation(${t.id}, '{name}')">{name}</button>
              <button type="button" class="btn btn-secondary btn-xs" onclick="app.insertVarIntoActiveVariation(${t.id}, '{first_name}')">{first_name}</button>
              <button type="button" class="btn btn-secondary btn-xs" onclick="app.insertVarIntoActiveVariation(${t.id}, '{phone}')">{phone}</button>
              <button type="button" class="btn btn-subtle btn-xs" onclick="app.duplicateTextVariation(${t.id})" title="Duplicate variation">Copy</button>
              <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.deleteTextVariation(${t.id})" title="Delete variation">Delete</button>
            </div>
          </div>

          <textarea class="form-textarea" id="tpl-var-text-${t.id}" rows="3" placeholder="Compose message copy with variables..." style="font-size: 0.85rem;" oninput="app.markTemplateDirty(); document.getElementById('tpl-char-cnt-${t.id}').textContent = this.value.length + ' chars'" onblur="app.updateTextVariation(${t.id}, 'text_content', this.value)">${this.escapeHtml(t.content || '')}</textarea>
        </div>
      `;
    }).join('');
  }

  async addTextVariationToActiveTemplate() {
    if (!this.activeTemplateId) return;
    try {
      const texts = (this.activeTemplate && this.activeTemplate.text_variations) || [];
      const newLabel = `Variation ${texts.length + 1}`;
      const newText = 'Hello {first_name}, ';

      await this.api(`/api/templates/${this.activeTemplateId}/texts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ content: newText, text_content: newText, label: newLabel })
      });

      this.showToast('Added message variation', 'info');
      const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
      this.activeTemplate = updated;
      this.renderTemplateTexts(updated);
    } catch (e) {
      console.error('Failed to add text variation:', e);
    }
  }

  async updateTextVariation(variantId, field, value) {
    if (!this.activeTemplateId) return;
    try {
      const payload = {};
      if (field === 'text_content') {
        payload.content = value;
        payload.text_content = value;
      } else {
        payload[field] = value;
      }
      await this.api(`/api/templates/${this.activeTemplateId}/texts/${variantId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      // Update local object
      if (this.activeTemplate && this.activeTemplate.text_variations) {
        const item = this.activeTemplate.text_variations.find(v => v.id === variantId);
        if (item) {
          if (field === 'text_content') item.content = value;
          if (field === 'label') item.label = value;
        }
      }
    } catch (e) {
      console.error('Failed to update text variation:', e);
    }
  }

  async toggleTextVariationActive(variantId, isActive) {
    if (!this.activeTemplateId) return;
    try {
      await this.api(`/api/templates/${this.activeTemplateId}/texts/${variantId}/toggle`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ is_active: isActive ? 1 : 0 })
      });
      const card = document.getElementById(`tpl-var-card-${variantId}`);
      if (card) card.classList.toggle('excluded', !isActive);
      this.showToast(isActive ? 'Variation included' : 'Variation temporarily excluded', 'info');
    } catch (e) {
      console.error('Failed to toggle variation:', e);
    }
  }

  async duplicateTextVariation(variantId) {
    if (!this.activeTemplateId || !this.activeTemplate) return;
    const texts = this.activeTemplate.text_variations || [];
    const source = texts.find(t => t.id === variantId);
    if (!source) return;

    try {
      await this.api(`/api/templates/${this.activeTemplateId}/texts`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          text_content: source.content,
          label: `${source.label || 'Variation'} (Copy)`
        })
      });
      this.showToast('Variation duplicated', 'info');
      const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
      this.activeTemplate = updated;
      this.renderTemplateTexts(updated);
    } catch (e) {
      console.error('Failed to duplicate variation:', e);
    }
  }

  async deleteTextVariation(variantId) {
    if (!this.activeTemplateId) return;
    try {
      await this.api(`/api/templates/${this.activeTemplateId}/texts/${variantId}`, { method: 'DELETE' });
      this.showToast('Variation removed', 'info');
      const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
      this.activeTemplate = updated;
      this.renderTemplateTexts(updated);
    } catch (e) {
      console.error('Failed to delete variation:', e);
    }
  }

  insertVarIntoActiveVariation(variantId, tag) {
    const textarea = document.getElementById(`tpl-var-text-${variantId}`);
    if (!textarea) return;
    const start = textarea.selectionStart || 0;
    const end = textarea.selectionEnd || 0;
    const text = textarea.value;
    textarea.value = text.substring(0, start) + tag + text.substring(end);
    textarea.focus();
    textarea.selectionStart = textarea.selectionEnd = start + tag.length;
    this.updateTextVariation(variantId, 'text_content', textarea.value);
  }

  openPasteMultipleTextsModal() {
    const textarea = document.getElementById('paste-multiple-raw-text');
    if (textarea) textarea.value = '';
    this.openModal('modal-paste-multiple-texts');
  }

  async submitPasteMultipleTexts() {
    if (!this.activeTemplateId) return;
    const textarea = document.getElementById('paste-multiple-raw-text');
    const delimSelect = document.getElementById('paste-multiple-delimiter');
    const raw = textarea ? textarea.value.trim() : '';

    if (!raw) {
      this.showToast('Please enter text variations', 'warning');
      return;
    }

    let sep = '\n';
    if (delimSelect && delimSelect.value === 'empty_line') sep = '\n\n';
    if (delimSelect && delimSelect.value === 'separator') sep = '---';

    try {
      const res = await this.api(`/api/templates/${this.activeTemplateId}/texts/paste-multiple`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ raw_text: raw, separator: sep })
      });

      this.closeModal('modal-paste-multiple-texts');
      this.showToast(`Added ${res.added_count || 'several'} variations`, 'success');
      const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
      this.activeTemplate = updated;
      this.renderTemplateTexts(updated);
    } catch (e) {
      console.error('Failed to paste multiple texts:', e);
    }
  }

  openImportTextsModal() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.txt,.csv';
    input.onchange = async (e) => {
      const file = e.target.files && e.target.files[0];
      if (!file || !this.activeTemplateId) return;
      const reader = new FileReader();
      reader.onload = async (evt) => {
        const text = evt.target.result;
        try {
          const res = await this.api(`/api/templates/${this.activeTemplateId}/texts/paste-multiple`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ raw_text: text, separator: '\n' })
          });
          this.showToast(`Imported ${res.added_count || 0} variations from file`, 'success');
          const updated = await this.api(`/api/templates/${this.activeTemplateId}`);
          this.activeTemplate = updated;
          this.renderTemplateTexts(updated);
        } catch (err) {
          this.showToast(`Import failed: ${err.message}`, 'error');
        }
      };
      reader.readAsText(file);
    };
    input.click();
  }

  // ==========================================================================
  // TRANSPARENT ASSIGNMENT PREVIEW MODAL
  // ==========================================================================
  async openAssignmentsPreviewModal() {
    if (!this.activeTemplateId) return;
    try {
      const data = await this.api(`/api/templates/${this.activeTemplateId}/preview-assignments`, { method: 'POST' });
      this.activeAssignments = data.all_assignments || data.sample_assignments || [];

      const modeLabel = data.mode === 'mix_variations' ? 'Mix Variations (1 media + 1 text assigned per recipient)' : 'Same for Everyone';
      const modeEl = document.getElementById('assign-prev-mode');
      const countEl = document.getElementById('assign-prev-count');
      if (modeEl) modeEl.textContent = modeLabel;
      if (countEl) countEl.textContent = `${data.total_recipients || this.activeAssignments.length} eligible contacts`;

      this.renderAssignmentsPreviewTable(this.activeAssignments);
      this.openModal('modal-preview-assignments');
    } catch (e) {
      console.error('Failed to generate preview assignments:', e);
      this.showToast('Could not compute assignments preview', 'error');
    }
  }

  filterAssignmentsPreview(query = '') {
    const q = (query || (document.getElementById('assign-prev-search') ? document.getElementById('assign-prev-search').value : '')).toLowerCase().trim();
    let filtered = this.activeAssignments || [];
    if (q) {
      filtered = filtered.filter(a => (a.name || '').toLowerCase().includes(q) || (a.phone || '').includes(q) || (a.assigned_message || '').toLowerCase().includes(q));
    }
    this.renderAssignmentsPreviewTable(filtered);
  }

  renderAssignmentsPreviewTable(assignments) {
    const tbody = document.getElementById('assign-prev-tbody');
    if (!tbody) return;

    if (!assignments || assignments.length === 0) {
      tbody.innerHTML = `<tr><td colspan="3" style="text-align: center; color: var(--text-muted); padding: 1.5rem;">No assignments found for eligible contacts.</td></tr>`;
      return;
    }

    tbody.innerHTML = assignments.map(a => {
      let mediaMarkup = '<span style="color: var(--text-muted);">None (Text-only)</span>';
      if (a.media_asset_id && a.media_filename) {
        mediaMarkup = `
          <div style="display: flex; align-items: center; gap: 0.5rem;">
            <div style="width: 32px; height: 32px; border-radius: var(--radius-xs); overflow: hidden; background: var(--surface-subtle); display: flex; align-items: center; justify-content: center; flex-shrink: 0;">
              <img src="/api/media/${a.media_asset_id}/file" style="width: 100%; height: 100%; object-fit: cover;" onerror="this.style.display='none'; this.nextElementSibling.style.display='inline';">
              <span style="display: none; font-size: 0.8rem;">📎</span>
            </div>
            <span style="font-size: 0.78rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(a.media_filename)}</span>
          </div>
        `;
      }

      return `
        <tr>
          <td>
            <strong>${this.escapeHtml(a.name || 'Customer')}</strong>
            <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">+${this.escapeHtml(a.phone || '')}</div>
          </td>
          <td>${mediaMarkup}</td>
          <td style="font-size: 0.8125rem; line-height: 1.4; color: var(--text-secondary);">${this.escapeHtml(a.assigned_message || '')}</td>
        </tr>
      `;
    }).join('');
  }

  // ==========================================================================
  // REVIEW & SEND BROADCAST MODAL
  // ==========================================================================
  async openReviewSendModal(templateId = null) {
    const tid = templateId || this.activeTemplateId;
    if (!tid) return;
    this.activeTemplateId = tid;

    if (this.isTemplateDirty) {
      const saved = await this.saveActiveTemplate();
      if (!saved) {
        this.showToast('Could not open Review & Send: template changes could not be saved', 'error');
        return;
      }
    }

    try {
      const t = await this.api(`/api/templates/${tid}`);
      this.activeTemplate = t;

      // Summary Fields
      const nameEl = document.getElementById('rev-tpl-name');
      const modeEl = document.getElementById('rev-tpl-mode');
      const cntEligible = document.getElementById('rev-cnt-eligible');
      const cntExcluded = document.getElementById('rev-cnt-excluded');
      const cntMedia = document.getElementById('rev-cnt-media');
      const cntTexts = document.getElementById('rev-cnt-texts');
      const campNameInput = document.getElementById('rev-campaign-name');
      const pacingMinInput = document.getElementById('rev-pacing-min');
      const pacingMaxInput = document.getElementById('rev-pacing-max');
      const warningBox = document.getElementById('rev-warning-box');
      const launchBtn = document.getElementById('btn-confirm-launch');

      const activeTexts = (t.text_variations || []).filter(x => x.is_active);
      const activeMedia = (t.media_assets || []).filter(x => x.is_active);

      // Summary counts from template
      const summary = t.contacts_summary || { total_selected: 0, eligible: 0, excluded: 0 };
      const eligibleCount = summary.eligible;
      const excludedCount = summary.excluded;

      if (nameEl) nameEl.textContent = t.name;
      if (modeEl) modeEl.textContent = t.content_selection_mode === 'mix_variations' ? 'Mix Variations' : 'Same for Everyone';
      if (cntEligible) cntEligible.textContent = eligibleCount;
      if (cntExcluded) cntExcluded.textContent = excludedCount;
      if (cntMedia) cntMedia.textContent = activeMedia.length;
      if (cntTexts) cntTexts.textContent = activeTexts.length;

      const dateStr = new Date().toLocaleDateString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
      if (campNameInput) campNameInput.value = `${t.name} — ${dateStr}`;
      if (pacingMinInput) pacingMinInput.value = t.pacing_delay_min || 8;
      if (pacingMaxInput) pacingMaxInput.value = t.pacing_delay_max || 16;

      // Connection Status Check
      const isConnected = this.currentSessionState === 'connected' || this.isWhatsAppConnected;
      const connDot = document.getElementById('rev-conn-dot');
      const connText = document.getElementById('rev-conn-text');
      const btnReconnect = document.getElementById('btn-rev-reconnect');
      if (connDot && connText) {
        if (isConnected) {
          connDot.className = 'status-indicator online';
          connText.textContent = 'Connection: Ready to dispatch';
          if (btnReconnect) btnReconnect.style.display = 'none';
        } else {
          connDot.className = 'status-indicator offline';
          connText.textContent = 'Connection: Action required (Browser not connected)';
          if (btnReconnect) btnReconnect.style.display = 'inline-block';
        }
      }

      // Smart Warnings & Validations
      let warning = '';
      let canSend = true;

      if (eligibleCount === 0) {
        warning = '❌ Cannot send broadcast: No eligible contacts found in selected audience.';
        canSend = false;
      } else if (activeTexts.length === 0 && !t.content) {
        warning = '❌ Cannot send broadcast: Please write at least one active message variation.';
        canSend = false;
      } else if (eligibleCount > 20 && activeTexts.length === 1) {
        warning = `⚠️ Spam Risk Warning: You are sending to ${eligibleCount} contacts with only 1 message variation. Adding 2–3 phrasing variations is strongly recommended to protect your WhatsApp account.`;
      }

      if (warningBox) {
        if (warning) {
          warningBox.style.display = 'block';
          warningBox.textContent = warning;
        } else {
          warningBox.style.display = 'none';
        }
      }

      if (launchBtn) launchBtn.disabled = !canSend;

      this.openModal('modal-review-send');
    } catch (e) {
      console.error('Failed to prepare review send modal:', e);
    }
  }

  async submitLaunchTemplateCampaign() {
    if (!this.activeTemplateId) return;
    const nameInput = document.getElementById('rev-campaign-name');
    const pacingMinInput = document.getElementById('rev-pacing-min');
    const pacingMaxInput = document.getElementById('rev-pacing-max');

    const campaignName = nameInput ? nameInput.value.trim() : '';
    const minDelay = pacingMinInput ? parseFloat(pacingMinInput.value) : 8;
    const maxDelay = pacingMaxInput ? parseFloat(pacingMaxInput.value) : 16;
    const formatSelect = document.getElementById('tpl-message-format-select');
    const msgFormat = (this.activeTemplate && this.activeTemplate.message_format) || (formatSelect ? formatSelect.value : 'image_with_caption');

    try {
      const res = await this.api(`/api/templates/${this.activeTemplateId}/launch`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          campaign_name: campaignName,
          pacing_delay_min: minDelay,
          pacing_delay_max: maxDelay,
          message_format: msgFormat
        })
      });

      this.closeModal('modal-review-send');
      this.showToast(`Broadcast '${res.campaign_name}' launched!`, 'success');
      this.navigate('campaigns');
    } catch (e) {
      console.error('Failed to launch campaign:', e);
    }
  }

  // ==========================================================================
  // SECTION: MEDIA LIBRARY (DEDICATED TAB)
  // ==========================================================================
  async loadMediaLibrary(filter = 'all') {
    this.mediaLibraryFilter = filter;
    ['all', 'image', 'video', 'doc'].forEach(f => {
      const btn = document.getElementById(`medialib-flt-${f}`);
      if (btn) btn.classList.toggle('active', f === filter);
    });

    try {
      const assets = await this.api('/api/media', { silent: true }).catch(() => []);
      const countLabel = document.getElementById('medialib-count-label');
      const grid = document.getElementById('medialib-grid');
      const emptyState = document.getElementById('medialib-empty-state');
      const bulkBar = document.getElementById('medialib-bulk-bar');
      const masterChk = document.getElementById('chk-master-medialib');

      this.selectedMediaLibraryIds.clear();
      if (bulkBar) bulkBar.style.display = 'none';
      if (masterChk) {
        masterChk.checked = false;
        masterChk.indeterminate = false;
      }

      let filtered = assets || [];
      if (filter === 'image') filtered = filtered.filter(a => (a.mime_type || '').startsWith('image/'));
      if (filter === 'video') filtered = filtered.filter(a => (a.mime_type || '').startsWith('video/'));
      if (filter === 'document') filtered = filtered.filter(a => (a.mime_type || '') === 'application/pdf');

      this.currentMediaAssets = filtered;

      if (countLabel) countLabel.textContent = `${filtered.length} durable assets in storage`;

      if (filtered.length === 0) {
        if (grid) grid.innerHTML = '';
        if (emptyState) emptyState.style.display = 'flex';
        return;
      }

      if (emptyState) emptyState.style.display = 'none';
      if (!grid) return;

      grid.innerHTML = filtered.map(a => {
        const isImg = (a.mime_type || '').startsWith('image/');
        const isVid = (a.mime_type || '').startsWith('video/');
        const isPdf = (a.mime_type || '') === 'application/pdf';

        let badgeType = 'FILE';
        if (isImg) badgeType = (a.mime_type || 'image/jpeg').split('/')[1].toUpperCase();
        else if (isVid) badgeType = 'VIDEO';
        else if (isPdf) badgeType = 'PDF';

        let thumbMarkup = '';
        if (isImg) {
          thumbMarkup = `<img src="/api/media/${a.id}/file" alt="${this.escapeHtml(a.title || a.filename)}" style="cursor: pointer; width: 100%; height: 100%; object-fit: cover;" onclick="app.openMediaPreviewModal(${a.id})">`;
        } else {
          const icon = isPdf ? '📄 PDF' : (isVid ? '🎬 Video' : '📎 File');
          thumbMarkup = `<div style="font-weight: 700; color: var(--text-muted); cursor: pointer;" onclick="app.openMediaPreviewModal(${a.id})">${icon}</div>`;
        }

        const displayTitle = a.title || a.filename || `Asset #${a.id}`;

        return `
          <div class="media-set-card-item" id="medialib-card-${a.id}">
            <div class="media-set-card-header">
              <input type="checkbox" id="chk-medialib-${a.id}" style="cursor: pointer; accent-color: var(--primary);" onchange="app.toggleSelectMediaLibrary(${a.id}, this.checked)">
              <span class="badge badge-neutral" style="font-size: 0.68rem;">${badgeType}</span>
            </div>

            <div class="media-set-thumb-box" style="height: 120px; overflow: hidden; display: flex; align-items: center; justify-content: center; background: var(--surface-subtle);">
              ${thumbMarkup}
            </div>

            <div class="media-set-card-title" title="${this.escapeHtml(displayTitle)}" style="font-weight: 600; font-size: 0.82rem; margin-top: 0.4rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;">
              ${this.escapeHtml(displayTitle)}
            </div>

            <div class="media-set-card-meta" style="font-size: 0.72rem; color: var(--text-muted); display: flex; justify-content: space-between; margin-top: 0.25rem;">
              <span>${this.formatBytes(a.file_size)}</span>
              <span>${(a.created_at || '').substring(0, 10)}</span>
            </div>

            <div class="media-set-card-actions" style="display: flex; gap: 0.35rem; margin-top: 0.5rem; justify-content: flex-end;">
              <button type="button" class="btn btn-subtle btn-xs" onclick="app.openMediaPreviewModal(${a.id})">Preview</button>
              <button type="button" class="btn btn-subtle btn-xs" onclick="app.openRenameMediaModal(${a.id}, '${this.escapeHtml(displayTitle)}')">Rename</button>
              <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.deleteMediaPermanently(${a.id}, '${this.escapeHtml(displayTitle)}')">Delete</button>
            </div>
          </div>
        `;
      }).join('');
    } catch (e) {
      console.error('Failed to load media library:', e);
    }
  }

  filterMediaLibrary(filter) {
    this.loadMediaLibrary(filter);
  }

  async onMediaLibraryFilesUploaded(e) {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    let uploaded = 0;
    for (let i = 0; i < files.length; i++) {
      const formData = new FormData();
      formData.append('file', files[i]);
      formData.append('title', files[i].name || 'Media Asset');
      try {
        const res = await fetch('/api/media/upload', { method: 'POST', body: formData });
        if (res.ok) uploaded++;
      } catch (err) {}
    }

    this.showToast(`Uploaded ${uploaded} file(s) to library`, 'success');
    e.target.value = '';
    this.loadMediaLibrary(this.mediaLibraryFilter || 'all');
  }

  toggleSelectMediaLibrary(assetId, checked) {
    if (checked) this.selectedMediaLibraryIds.add(assetId);
    else this.selectedMediaLibraryIds.delete(assetId);

    const bulkBar = document.getElementById('medialib-bulk-bar');
    const countLabel = document.getElementById('medialib-bulk-count');
    const masterChk = document.getElementById('chk-master-medialib');

    const totalCount = (this.currentMediaAssets || []).length;
    const selectedCount = this.selectedMediaLibraryIds.size;

    if (bulkBar && countLabel) {
      bulkBar.style.display = selectedCount > 0 ? 'flex' : 'none';
      countLabel.textContent = `${selectedCount} selected`;
    }

    if (masterChk) {
      if (selectedCount === 0) {
        masterChk.checked = false;
        masterChk.indeterminate = false;
      } else if (selectedCount === totalCount && totalCount > 0) {
        masterChk.checked = true;
        masterChk.indeterminate = false;
      } else {
        masterChk.checked = false;
        masterChk.indeterminate = true;
      }
    }
  }

  toggleSelectAllMediaLibrary(checked) {
    const assets = this.currentMediaAssets || [];
    this.selectedMediaLibraryIds.clear();

    if (checked) {
      assets.forEach(a => this.selectedMediaLibraryIds.add(a.id));
    }

    assets.forEach(a => {
      const chk = document.getElementById(`chk-medialib-${a.id}`);
      if (chk) chk.checked = checked;
    });

    const bulkBar = document.getElementById('medialib-bulk-bar');
    const countLabel = document.getElementById('medialib-bulk-count');
    const masterChk = document.getElementById('chk-master-medialib');

    if (bulkBar && countLabel) {
      const size = this.selectedMediaLibraryIds.size;
      bulkBar.style.display = size > 0 ? 'flex' : 'none';
      countLabel.textContent = `${size} selected`;
    }

    if (masterChk) {
      masterChk.checked = checked;
      masterChk.indeterminate = false;
    }
  }

  clearMediaLibrarySelection() {
    this.selectedMediaLibraryIds.clear();
    const bulkBar = document.getElementById('medialib-bulk-bar');
    if (bulkBar) bulkBar.style.display = 'none';
    const masterChk = document.getElementById('chk-master-medialib');
    if (masterChk) {
      masterChk.checked = false;
      masterChk.indeterminate = false;
    }
    (this.currentMediaAssets || []).forEach(a => {
      const chk = document.getElementById(`chk-medialib-${a.id}`);
      if (chk) chk.checked = false;
    });
  }

  openRenameMediaModal(assetId, currentTitle) {
    this.renamingMediaId = assetId;
    const input = document.getElementById('rename-media-input');
    if (input) input.value = currentTitle || '';
    this.openModal('modal-rename-media');
    setTimeout(() => {
      if (input) {
        input.focus();
        input.select();
      }
    }, 100);
  }

  async submitRenameMedia() {
    if (!this.renamingMediaId) return;
    const input = document.getElementById('rename-media-input');
    const title = input ? input.value.trim() : '';
    if (!title) {
      this.showToast('Please enter an asset title', 'warning');
      return;
    }

    try {
      await this.api(`/api/media/${this.renamingMediaId}/rename`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title })
      });
      this.closeModal('modal-rename-media');
      this.showToast('Media asset renamed', 'success');
      this.loadMediaLibrary(this.mediaLibraryFilter || 'all');
    } catch (e) {
      console.error('Failed to rename media asset:', e);
      this.showToast('Failed to rename media asset', 'danger');
    }
  }

  async executeBulkDeleteMediaLibrary() {
    if (this.selectedMediaLibraryIds.size === 0) return;
    const ok = await this.confirmDialog({
      title: 'Bulk Delete Media Files',
      message: `Are you sure you want to permanently delete ${this.selectedMediaLibraryIds.size} file(s) from disk and database?`,
      details: 'This will remove the selected files from storage and all templates.',
      confirmText: `Delete ${this.selectedMediaLibraryIds.size} Files`,
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;

    const ids = Array.from(this.selectedMediaLibraryIds);
    try {
      await this.api('/api/media/bulk-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ asset_ids: ids, force: true })
      });
      this.showToast(`Deleted ${ids.length} files permanently`, 'info');
      this.loadMediaLibrary(this.mediaLibraryFilter || 'all');
    } catch (e) {
      console.error('Failed to bulk delete media:', e);
    }
  }

  // ==========================================================================
  // SECTION: UNIFIED CAMPAIGNS PROGRESS & HISTORY (CAMPAIGNS TAB)
  // ==========================================================================
  async loadCampaignsData() {
    try {
      // 1. Check for active running job
      const activeRes = await this.api('/api/jobs/active', { silent: true }).catch(() => null);
      const activeJob = (activeRes && activeRes.active_job) ? activeRes.active_job : activeRes;
      if (activeJob && activeJob.status && activeJob.status !== 'COMPLETED' && activeJob.status !== 'CANCELLED' && activeJob.status !== 'FAILED') {
        this.updateCampaignProgressUI(activeJob);
      } else {
        const progCard = document.getElementById('campaign-progress-card');
        if (progCard) progCard.style.display = 'none';
      }

      // 2. Load past campaigns table
      const campaigns = await this.api('/api/campaigns', { silent: true }).catch(() => []);
      this.renderCampaignHistory(campaigns || []);

      // 3. Load recipient activity
      await this.loadRecipientActivity();
    } catch (e) {
      console.error('Failed to load campaigns data:', e);
    }
  }

  updateCampaignProgressUI(job) {
    const card = document.getElementById('campaign-progress-card');
    if (!card || !job) return;

    card.style.display = 'block';

    const nameEl = document.getElementById('prog-campaign-name');
    const badgeEl = document.getElementById('prog-badge-status');
    const timeEl = document.getElementById('prog-started-time');
    const labelEl = document.getElementById('prog-progress-text');
    const barEl = document.getElementById('prog-progress-bar');
    const sentEl = document.getElementById('prog-cnt-sent');
    const pendingEl = document.getElementById('prog-cnt-pending');
    const failedEl = document.getElementById('prog-cnt-failed');
    const uncertainEl = document.getElementById('prog-cnt-uncertain');
    const activityEl = document.getElementById('prog-current-activity');
    const pauseBtn = document.getElementById('btn-prog-pause');

    if (nameEl) nameEl.textContent = job.campaign_name || 'Active Campaign';
    if (badgeEl) badgeEl.textContent = job.status || 'SENDING';
    if (timeEl) timeEl.textContent = `Started: ${new Date(job.created_at || Date.now()).toLocaleTimeString()}`;

    const total = job.total_count || job.total || 0;
    const sent = job.sent_count || job.sent || 0;
    const failed = job.failed_count || job.failed || 0;
    const uncertain = job.uncertain_count || job.uncertain || 0;
    const pending = (job.pending_count !== undefined) ? job.pending_count : Math.max(0, total - (sent + failed + uncertain));
    const processed = sent + failed + uncertain;
    const pct = total > 0 ? Math.min(100, Math.round((processed / total) * 100)) : 0;

    if (sentEl) sentEl.textContent = sent;
    if (pendingEl) pendingEl.textContent = pending;
    if (failedEl) failedEl.textContent = failed;
    if (uncertainEl) uncertainEl.textContent = uncertain;

    if (labelEl) labelEl.textContent = `${processed} / ${total} processed (${pct}%)`;
    if (barEl) barEl.style.transform = `scaleX(${pct / 100})`;

    if (activityEl) {
      if (job.status === 'PAUSED') activityEl.textContent = 'Campaign paused. Click Resume to continue dispatching.';
      else if (job.current_recipient) activityEl.textContent = `Currently processing: ${job.current_recipient}`;
      else activityEl.textContent = `Active dispatch in progress (${processed}/${total})`;
    }

    if (pauseBtn) {
      pauseBtn.textContent = job.status === 'PAUSED' ? 'Resume' : 'Pause';
    }

    // Populate live dispatch feed rows
    const tbody = document.getElementById('prog-dispatch-tbody');
    if (tbody && job.queue_items) {
      tbody.innerHTML = job.queue_items.slice(-15).reverse().map(item => {
        let statusBadge = '<span class="badge badge-neutral">Pending</span>';
        if (item.status === 'SENT' || item.status === 'COMPLETED') statusBadge = '<span class="badge badge-success">Sent</span>';
        if (item.status === 'FAILED') statusBadge = '<span class="badge badge-danger">Failed</span>';
        if (item.status === 'UNCERTAIN') statusBadge = '<span class="badge badge-warning">Uncertain</span>';

        return `
          <tr>
            <td><strong>${this.escapeHtml(item.contact_name || 'Customer')}</strong></td>
            <td style="font-family: var(--font-mono); font-size: 0.72rem;">+${this.escapeHtml(item.phone || '')}</td>
            <td style="font-size: 0.75rem;">${item.media_filename ? '📎 ' + this.escapeHtml(item.media_filename) : 'Text only'}</td>
            <td style="font-size: 0.75rem; max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${this.escapeHtml(item.message || '')}</td>
            <td>${statusBadge}</td>
            <td style="font-size: 0.72rem; color: var(--text-muted);">${new Date(item.created_at || Date.now()).toLocaleTimeString()}</td>
            <td style="font-size: 0.72rem; color: var(--danger);">${this.escapeHtml(item.error_message || '—')}</td>
          </tr>
        `;
      }).join('');
    }
  }

  renderCampaignHistory(campaigns) {
    const tbody = document.getElementById('campaign-history-tbody');
    const emptyNotice = document.getElementById('campaign-history-empty');
    if (!tbody) return;

    if (!campaigns || campaigns.length === 0) {
      tbody.innerHTML = '';
      if (emptyNotice) emptyNotice.style.display = 'block';
      return;
    }

    if (emptyNotice) emptyNotice.style.display = 'none';

    tbody.innerHTML = campaigns.map(c => {
      let statusBadge = `<span class="badge badge-neutral">${this.escapeHtml(c.status || 'draft')}</span>`;
      if (c.status === 'COMPLETED') statusBadge = '<span class="badge badge-success">Completed</span>';
      if (c.status === 'RUNNING' || c.status === 'SENDING') statusBadge = '<span class="badge badge-primary">Running</span>';
      if (c.status === 'PAUSED') statusBadge = '<span class="badge badge-warning">Paused</span>';
      if (c.status === 'FAILED') statusBadge = '<span class="badge badge-danger">Failed</span>';

      const sentCount = c.sent_count || 0;
      const totalCount = c.total_count || 0;

      return `
        <tr>
          <td><strong>${this.escapeHtml(c.name || 'Unnamed Broadcast')}</strong></td>
          <td>${statusBadge}</td>
          <td><strong>${sentCount}</strong> / ${totalCount} delivered</td>
          <td style="font-size: 0.75rem; color: var(--text-muted);">${(c.created_at || '').substring(0, 16).replace('T', ' ')}</td>
          <td style="text-align: right;">
            <button type="button" class="btn btn-subtle btn-xs text-danger" onclick="app.deleteCampaignRecord(${c.id}, '${this.escapeHtml(c.name)}')">
              Delete
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  async deleteCampaignRecord(campaignId, name) {
    const ok = await this.confirmDialog({
      title: 'Delete Campaign Record',
      message: `Are you sure you want to delete campaign '${name}'?`,
      details: 'This will remove the campaign summary from your history.',
      confirmText: 'Delete Campaign',
      cancelText: 'Cancel',
      isDestructive: true
    });
    if (!ok) return;
    try {
      await this.api(`/api/campaigns/${campaignId}`, { method: 'DELETE' });
      this.showToast(`Deleted campaign '${name}'`, 'info');
      this.loadCampaignsData();
    } catch (e) {
      console.error('Failed to delete campaign:', e);
    }
  }

  // ==========================================================================
  // SECTION: RECIPIENT-LEVEL MESSAGING ACTIVITY & TECHNICAL AUDIT LOGS
  // ==========================================================================
  async loadRecipientActivity() {
    try {
      const status = this.recipientActivityFilter || 'ALL';
      const search = this.recipientActivitySearch || '';
      const params = new URLSearchParams();
      if (status && status !== 'ALL') params.append('status', status);
      if (search && search.trim()) params.append('search', search.trim());
      params.append('limit', '100');

      const res = await this.api(`/api/jobs/activity/items?${params.toString()}`, { silent: true }).catch(() => null);
      const items = (res && res.items) ? res.items : (Array.isArray(res) ? res : []);
      this.renderRecipientActivity(items);
    } catch (e) {
      console.error('Failed to load recipient activity:', e);
    }
  }

  filterRecipientActivity(status) {
    this.recipientActivityFilter = status || 'ALL';
    ['ALL', 'SENT', 'FAILED', 'UNCERTAIN', 'PENDING'].forEach(s => {
      const btn = document.getElementById(`act-flt-${s.toLowerCase()}`);
      if (btn) btn.classList.toggle('active', s === this.recipientActivityFilter);
    });
    this.loadRecipientActivity();
  }

  searchRecipientActivity(query) {
    this.recipientActivitySearch = query || '';
    if (this._recSearchTimeout) clearTimeout(this._recSearchTimeout);
    this._recSearchTimeout = setTimeout(() => {
      this.loadRecipientActivity();
    }, 250);
  }

  renderRecipientActivity(items) {
    const tbody = document.getElementById('recipient-activity-tbody');
    const emptyNotice = document.getElementById('recipient-activity-empty');
    if (!tbody) return;

    if (!items || items.length === 0) {
      tbody.innerHTML = '';
      if (emptyNotice) emptyNotice.style.display = 'block';
      return;
    }

    if (emptyNotice) emptyNotice.style.display = 'none';

    tbody.innerHTML = items.map(item => {
      let statusBadge = '<span class="badge badge-neutral">Pending</span>';
      if (item.status === 'SENT' || item.status === 'COMPLETED') {
        statusBadge = '<span class="badge badge-success" title="Handed off to WhatsApp Web">Sent</span>';
      } else if (item.status === 'PARTIALLY_SENT' || item.display_status === 'PARTIALLY_SENT') {
        statusBadge = '<span class="badge badge-warning" title="Image sent, follow-up text failed" style="background: rgba(245,158,11,0.15); color: #f59e0b; border: 1px solid rgba(245,158,11,0.3);">Partially Sent</span>';
      } else if (item.status === 'FAILED') {
        statusBadge = '<span class="badge badge-danger">Failed</span>';
      } else if (item.status === 'UNCERTAIN') {
        statusBadge = '<span class="badge badge-warning">Uncertain</span>';
      }

      let componentBadges = '';
      if (item.media_status && item.media_status !== 'SKIPPED') {
        const medIcon = item.media_status === 'SENT' ? '✓' : '✕';
        const medClass = item.media_status === 'SENT' ? 'badge-success' : 'badge-danger';
        componentBadges += `<span class="badge ${medClass}" style="font-size: 0.65rem; padding: 1px 4px; margin-right: 3px;">Image: ${medIcon}</span>`;
      }
      if (item.text_status && item.text_status !== 'SKIPPED') {
        const txtIcon = item.text_status === 'SENT' ? '✓' : '✕';
        const txtClass = item.text_status === 'SENT' ? 'badge-success' : 'badge-danger';
        componentBadges += `<span class="badge ${txtClass}" style="font-size: 0.65rem; padding: 1px 4px;">Text: ${txtIcon}</span>`;
      }

      let mediaDisplay = '<span style="color: var(--text-muted); font-size: 0.75rem;">Text only</span>';
      if (item.media_filename || item.media_path) {
        const fname = item.media_filename || (item.media_path ? item.media_path.split(/[\\/]/).pop() : 'Attachment');
        let thumb = '';
        if (item.media_asset_id) {
          thumb = `<img src="/api/media/${item.media_asset_id}/file" style="width: 22px; height: 22px; object-fit: cover; border-radius: 3px; vertical-align: middle; margin-right: 5px;">`;
        }
        mediaDisplay = `<div style="display: flex; align-items: center; font-size: 0.78rem;">${thumb}<span title="${this.escapeHtml(fname)}" style="max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">📎 ${this.escapeHtml(fname)}</span></div>`;
      }

      const rawMsg = item.message || '';
      const timeStr = item.sent_at || item.created_at || '';
      const formattedTime = timeStr ? timeStr.substring(0, 16).replace('T', ' ') : '—';

      return `
        <tr style="cursor: pointer;" onclick="app.openRecipientDetailDrawer(${item.id})">
          <td>
            <strong>${this.escapeHtml(item.contact_name || 'Recipient')}</strong>
            <div style="font-family: var(--font-mono); font-size: 0.72rem; color: var(--text-muted);">+${this.escapeHtml(item.phone || '')}</div>
            ${componentBadges ? `<div style="margin-top: 3px;">${componentBadges}</div>` : ''}
          </td>
          <td style="max-width: 280px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 0.8rem;" title="${this.escapeHtml(rawMsg)}">
            ${this.escapeHtml(rawMsg || '—')}
          </td>
          <td>${mediaDisplay}</td>
          <td>${statusBadge}</td>
          <td style="font-size: 0.72rem; color: var(--text-muted);">${formattedTime}</td>
          <td style="text-align: right;" onclick="event.stopPropagation()">
            <button type="button" class="btn btn-subtle btn-xs" onclick="app.openRecipientDetailDrawer(${item.id})">
              Details →
            </button>
          </td>
        </tr>
      `;
    }).join('');
  }

  async openRecipientDetailDrawer(itemId) {
    this.activeDrawerItemId = itemId;
    try {
      const data = await this.api(`/api/jobs/activity/items/${itemId}`, { silent: true });
      if (!data) return;

      const titleEl = document.getElementById('rec-drawer-title');
      const subEl = document.getElementById('rec-drawer-subtitle');
      const nameEl = document.getElementById('rec-drawer-name');
      const phoneEl = document.getElementById('rec-drawer-phone');
      const badgeEl = document.getElementById('rec-drawer-status-badge');
      const groupEl = document.getElementById('rec-drawer-group');
      const formatEl = document.getElementById('rec-drawer-format');
      const timeEl = document.getElementById('rec-drawer-dispatched');
      const campEl = document.getElementById('rec-drawer-campaign');
      const delivEl = document.getElementById('rec-drawer-delivery-explanation');
      const readEl = document.getElementById('rec-drawer-read-explanation');
      const errBox = document.getElementById('rec-drawer-error-box');
      const errText = document.getElementById('rec-drawer-error-text');
      const msgText = document.getElementById('rec-drawer-message-text');
      const mediaSec = document.getElementById('rec-drawer-media-section');
      const mediaThumb = document.getElementById('rec-drawer-media-thumb');
      const mediaTitle = document.getElementById('rec-drawer-media-title');
      const mediaMeta = document.getElementById('rec-drawer-media-meta');
      const retryBtn = document.getElementById('btn-rec-retry');

      if (titleEl) titleEl.textContent = `Recipient Activity #${data.id}`;
      if (subEl) subEl.textContent = `Campaign: ${data.campaign_name || 'Broadcast'}`;
      if (nameEl) nameEl.textContent = data.contact_name || 'Recipient';
      if (phoneEl) phoneEl.textContent = data.phone ? `+${data.phone}` : 'No phone';

      if (badgeEl) {
        badgeEl.className = 'badge';
        if (data.status === 'SENT' || data.status === 'COMPLETED') {
          badgeEl.classList.add('badge-success');
          badgeEl.textContent = 'Sent (Dispatched)';
        } else if (data.status === 'PARTIALLY_SENT' || data.display_status === 'PARTIALLY_SENT') {
          badgeEl.classList.add('badge-warning');
          badgeEl.style.background = 'rgba(245,158,11,0.15)';
          badgeEl.style.color = '#f59e0b';
          badgeEl.style.border = '1px solid rgba(245,158,11,0.3)';
          badgeEl.textContent = 'Partially Sent';
        } else if (data.status === 'FAILED') {
          badgeEl.classList.add('badge-danger');
          badgeEl.textContent = 'Failed';
        } else if (data.status === 'UNCERTAIN') {
          badgeEl.classList.add('badge-warning');
          badgeEl.textContent = 'Uncertain';
        } else {
          badgeEl.classList.add('badge-neutral');
          badgeEl.textContent = data.status || 'Pending';
        }
      }

      if (groupEl) groupEl.textContent = data.group_name || 'General';
      if (formatEl) {
        formatEl.textContent = data.message_format === 'image_then_text' ? 'Image then separate text' : 'Image with text caption';
      }
      if (timeEl) {
        const t = data.sent_at || data.created_at || '';
        timeEl.textContent = t ? t.substring(0, 19).replace('T', ' ') : '—';
      }
      if (campEl) campEl.textContent = data.campaign_name || 'Ad-hoc dispatch';

      if (delivEl) {
        if (data.status === 'SENT' || data.status === 'COMPLETED') {
          delivEl.innerHTML = '<strong>Handoff Confirmed:</strong> Message was successfully handed off to the WhatsApp Web chat input and accepted by the WhatsApp network interface.';
        } else if (data.status === 'PARTIALLY_SENT' || data.display_status === 'PARTIALLY_SENT') {
          delivEl.innerHTML = '<strong>Partially Delivered:</strong> The media asset was successfully delivered to the recipient, but the follow-up text failed to send. Retrying will safely send only the text without resending the media.';
        } else if (data.status === 'FAILED') {
          delivEl.innerHTML = '<strong>Handoff Failed:</strong> The dispatch attempt failed before message transmission could complete.';
        } else if (data.status === 'UNCERTAIN') {
          delivEl.innerHTML = '<strong>Inconclusive Confirmation:</strong> The browser action dispatched the message payload, but the post-send confirmation check timed out. Message may or may not have reached recipient.';
        } else {
          delivEl.innerHTML = '<strong>Pending:</strong> Recipient is scheduled in queue waiting for pacing interval.';
        }
      }

      if (readEl) {
        readEl.textContent = 'Delivery status reflects browser interface handoff. Read receipts ("Blue Ticks") are unexposed in browser DOM telemetry and are never fabricated.';
      }

      if (errBox && errText) {
        if (data.error_message) {
          errBox.style.display = 'block';
          errText.textContent = data.error_message;
        } else {
          errBox.style.display = 'none';
        }
      }

      if (msgText) msgText.textContent = data.message || '(No text content assigned)';

      const hasMedia = data.media_filename || data.media_path || data.media_asset_id;
      if (mediaSec) {
        if (hasMedia) {
          mediaSec.style.display = 'block';
          const fname = data.media_filename || (data.media_path ? data.media_path.split(/[\\/]/).pop() : 'Attachment');
          if (mediaTitle) mediaTitle.textContent = fname;
          if (mediaMeta) {
            mediaMeta.textContent = data.media_asset_id ? `Library Asset ID #${data.media_asset_id}` : 'Local attachment';
          }
          if (mediaThumb) {
            if (data.media_asset_id) {
              mediaThumb.innerHTML = `<img src="/api/media/${data.media_asset_id}/file" style="width: 100%; height: 100%; object-fit: cover; cursor: pointer;" onclick="app.openMediaPreviewModal(${data.media_asset_id})">`;
            } else {
              mediaThumb.innerHTML = `<span style="font-size: 1.25rem;">📎</span>`;
            }
          }
        } else {
          mediaSec.style.display = 'none';
        }
      }

      if (retryBtn) {
        const canRetry = data.status === 'FAILED' || data.status === 'UNCERTAIN' || data.status === 'PARTIALLY_SENT' || data.display_status === 'PARTIALLY_SENT';
        retryBtn.style.display = canRetry ? 'inline-flex' : 'none';
        if (data.recovery_action === 'retry_text_only' || data.media_status === 'SENT') {
          retryBtn.textContent = 'Retry Text Only';
          retryBtn.title = 'Image was already delivered. Retrying will only send the follow-up text.';
        } else {
          retryBtn.textContent = 'Retry Recipient';
          retryBtn.title = 'Re-queue message dispatch for this recipient';
        }
      }

      this.openModal('modal-recipient-drawer');
    } catch (e) {
      console.error('Failed to open recipient detail drawer:', e);
      this.showToast('Could not load recipient details', 'danger');
    }
  }

  async retryActiveDrawerRecipient() {
    if (!this.activeDrawerItemId) return;
    try {
      await this.api(`/api/jobs/activity/items/${this.activeDrawerItemId}/retry`, {
        method: 'POST'
      });
      this.showToast('Queued recipient for retry', 'success');
      await this.openRecipientDetailDrawer(this.activeDrawerItemId);
      this.loadRecipientActivity();
    } catch (e) {
      console.error('Failed to retry recipient:', e);
      this.showToast('Failed to retry recipient', 'danger');
    }
  }

  async loadTechnicalAuditLogs() {
    const filterEl = document.getElementById('audit-level-filter');
    const level = filterEl ? filterEl.value : 'ALL';
    const tbody = document.getElementById('technical-audit-tbody');
    if (!tbody) return;

    try {
      const res = await this.api(`/api/logs?level=${encodeURIComponent(level)}&limit=100`, { silent: true }).catch(() => null);
      const logs = (res && res.logs) ? res.logs : [];

      if (logs.length === 0) {
        tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: var(--text-muted); padding: 1rem;">No technical audit logs recorded yet.</td></tr>';
        return;
      }

      tbody.innerHTML = logs.map(l => {
        let levelBadge = '<span class="badge badge-neutral" style="font-size: 0.65rem;">INFO</span>';
        if (l.level === 'WARNING') levelBadge = '<span class="badge badge-warning" style="font-size: 0.65rem;">WARN</span>';
        if (l.level === 'ERROR') levelBadge = '<span class="badge badge-danger" style="font-size: 0.65rem;">ERROR</span>';

        return `
          <tr>
            <td style="color: var(--text-muted); white-space: nowrap;">${(l.timestamp || '').substring(0, 19).replace('T', ' ')}</td>
            <td>${levelBadge}</td>
            <td style="font-weight: 600; color: var(--text-secondary);">${this.escapeHtml(l.module || 'engine')}</td>
            <td style="white-space: pre-wrap; word-break: break-word;">${this.escapeHtml(l.message || '')}</td>
          </tr>
        `;
      }).join('');
    } catch (e) {
      console.error('Failed to load technical audit logs:', e);
    }
  }

}


// Instantiate singleton dashboard application
const app = new WhatsAppDashboardApp();
window.app = app;
