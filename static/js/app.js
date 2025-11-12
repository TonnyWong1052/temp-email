// ===== Temporary Email Service Frontend - Multi-Email Support =====

// i18n Helper: Safe translation function with fallback
function safeT(key, params = {}) {
    // Check if i18n is loaded
    if (typeof window.t === 'function') {
        const translated = window.t(key, params);
        // If translation returns the key unchanged, try to get it directly
        if (translated === key && window.i18n && window.i18n.translations) {
            // Try direct lookup as fallback
            return window.i18n.translations[key] || key;
        }
        return translated;
    }
    // Fallback to key if i18n not loaded yet
    return key;
}

// State Management
const emailsState = {
    emails: [], // Array of email objects with {token, email, expiresAt, mails: [], mailCount: 0, isExpanded: true}
    autoRefreshInterval: null,
    expiresIntervals: {}, // Map of token to interval ID
    apiNotificationsEnabled: false, // Control API popup notifications (default: off)
    mailDetailsCache: {} // Cache for mail details and codes: {mailId: {subject, from, content, receivedAt, codes}}
};

// API Base URL
const API_BASE = window.location.origin;

// Built-in domains (same as backend config). Only non-builtin (custom/Cloudflare) domains get a star in UI.
const BUILTIN_EMAIL_DOMAINS = [
    "chatgptuk.pp.ua",
    "freemails.pp.ua",
    "email.gravityengine.cc",
    "gravityengine.cc",
    "3littlemiracles.com",
    "almiswelfare.org",
    "gyan-netra.com",
    "iraniandsa.org",
    "14club.org.uk",
    "aard.org.uk",
    "allumhall.co.uk",
    "cade.org.uk",
    "caye.org.uk",
    "cketrust.org",
    "club106.org.uk",
    "cok.org.uk",
    "cwetg.co.uk",
    "goleudy.org.uk",
    "hhe.org.uk",
    "hottchurch.org.uk",
];

// API Notification Stack Management
const apiNotifications = [];
const NOTIFICATION_HEIGHT = 110; // Approximate height of each notification
const NOTIFICATION_SPACING = 40; // Space between notifications (increased for better separation)

// Terminal API Log Management
const terminalLogs = [];
const MAX_TERMINAL_LOGS = 100; // Keep last 100 API calls

// Wrap fetch to show API notifications and capture request/response
const originalFetch = window.fetch;
window.fetch = async function(...args) {
    const [url, options = {}] = args;
    const method = options.method || 'GET';
    const startTime = Date.now();

    // Capture request details
    const requestHeaders = options.headers || {};
    let requestBody = null;
    if (options.body) {
        try {
            requestBody = typeof options.body === 'string' ? JSON.parse(options.body) : options.body;
        } catch {
            requestBody = options.body;
        }
    }

    // Show API notification
    showApiNotification(method, url);

    try {
        // Call original fetch
        const response = await originalFetch(...args);
        const endTime = Date.now();
        const duration = endTime - startTime;

        // Clone response to read body without consuming it
        const clonedResponse = response.clone();
        let responseBody = null;
        const contentType = response.headers.get('content-type');

        try {
            if (contentType && contentType.includes('application/json')) {
                responseBody = await clonedResponse.json();
            } else {
                responseBody = await clonedResponse.text();
            }
        } catch (err) {
            responseBody = '[无法解析响应体]';
        }

        // Capture response headers
        const responseHeaders = {};
        response.headers.forEach((value, key) => {
            responseHeaders[key] = value;
        });

        // Log to terminal with request/response details
        logApiToTerminal(method, url, {
            request: {
                headers: requestHeaders,
                body: requestBody
            },
            response: {
                status: response.status,
                statusText: response.statusText,
                headers: responseHeaders,
                body: responseBody
            },
            duration
        });

        return response;
    } catch (error) {
        const endTime = Date.now();
        const duration = endTime - startTime;

        // Log error to terminal
        logApiToTerminal(method, url, {
            request: {
                headers: requestHeaders,
                body: requestBody
            },
            response: {
                status: 0,
                statusText: 'Network Error',
                headers: {},
                body: error.message
            },
            duration,
            error: true
        });

        throw error;
    }
};

// DOM Elements
const generateBtn = document.getElementById('generateBtn');
const generateBtnText = document.getElementById('generateBtnText');
const domainSelect = document.getElementById('domainSelect');
const emailPrefixInput = document.getElementById('emailPrefix');
const emailList = document.getElementById('emailList');
const emailCount = document.getElementById('emailCount');
const autoRefreshBtn = document.getElementById('autoRefreshBtn');
const mailModal = document.getElementById('mailModal');
const closeModal = document.getElementById('closeModal');

// Stats Elements
const statEmailCount = document.getElementById('statEmailCount');
const statTotalMails = document.getElementById('statTotalMails');

// Terminal Elements
const terminalOutput = document.getElementById('terminalOutput');
const terminalCount = document.getElementById('terminalCount');
const clearTerminalBtn = document.getElementById('clearTerminalBtn');
const apiNotifyToggleBtn = document.getElementById('apiNotifyToggleBtn');

// Event Listeners
generateBtn.addEventListener('click', generateEmail);
if (autoRefreshBtn) autoRefreshBtn.addEventListener('click', toggleAutoRefresh);
if (clearTerminalBtn) clearTerminalBtn.addEventListener('click', clearTerminalLog);
if (apiNotifyToggleBtn) apiNotifyToggleBtn.addEventListener('click', toggleApiNotifications);

// Custom Prefix Mode Select Handler
const prefixModeSelect = document.getElementById('prefixModeSelect');
const customPrefixInputWrapper = document.getElementById('customPrefixInputWrapper');

if (prefixModeSelect && customPrefixInputWrapper) {
    prefixModeSelect.addEventListener('change', function() {
        if (this.value === 'custom') {
            customPrefixInputWrapper.style.display = 'block';
            // Focus on input when custom mode is selected
            if (emailPrefixInput) {
                setTimeout(() => emailPrefixInput.focus(), 100);
            }
        } else {
            customPrefixInputWrapper.style.display = 'none';
            // Clear input when switching back to random mode
            if (emailPrefixInput) {
                emailPrefixInput.value = '';
            }
        }
    });
}
closeModal.addEventListener('click', () => mailModal.style.display = 'none');

// Email Prefix Input Validation - Only allow alphanumeric characters
if (emailPrefixInput) {
    emailPrefixInput.addEventListener('input', (e) => {
        // Remove any non-alphanumeric characters (只保留字母和數字)
        e.target.value = e.target.value.replace(/[^a-zA-Z0-9]/g, '');
    });
}
mailModal.addEventListener('click', (e) => {
    if (e.target === mailModal || e.target.classList.contains('modal-backdrop')) {
        mailModal.style.display = 'none';
    }
});

// Get API description based on URL
function getApiDescription(url, method) {
    // Extract path from full URL
    const urlObj = new URL(url, window.location.origin);
    const path = urlObj.pathname;

    // Match different API endpoints
    if (method === 'POST' && path.includes('/api/email/generate')) {
        return safeT('api.descriptions.generate_email');
    }

    if (method === 'GET' && path.match(/\/api\/email\/[^/]+\/mails\/[^/]+$/)) {
        return safeT('api.descriptions.view_mail_detail');
    }

    if (method === 'GET' && path.match(/\/api\/email\/[^/]+\/mails/)) {
        return safeT('api.descriptions.get_mail_list');
    }

    if (method === 'GET' && path.match(/\/api\/email\/[^/]+\/codes/)) {
        return safeT('api.descriptions.extract_codes');
    }

    // GET /api/domains → Get domain list
    if (method === 'GET' && path === '/api/domains') {
        return safeT('api.descriptions.get_domains');
    }

    // Default fallback
    return safeT('api.descriptions.api_call');
}

// Update positions of all notifications
function updateNotificationPositions() {
    apiNotifications.forEach((notification, index) => {
        const bottomPosition = 20 + (index * (NOTIFICATION_HEIGHT + NOTIFICATION_SPACING));
        notification.style.bottom = bottomPosition + 'px';
    });
}

// Show API Notification in bottom-left corner
function showApiNotification(method, url) {
    // Check if API notifications are enabled
    if (!emailsState.apiNotificationsEnabled) {
        return; // Skip showing notification
    }

    // Create notification element
    const notification = document.createElement('div');
    notification.className = 'api-notification';

    // Get method class for styling
    const methodClass = method.toLowerCase();

    // Get API description (will be updated after insertion if needed)
    const apiDescription = getApiDescription(url, method);

    notification.innerHTML = `
        <div class="api-notification-content">
            <div class="api-notification-header">
                <div class="api-notification-left">
                    <span class="api-notification-method ${methodClass}">${method}</span>
                    <span class="api-notification-title" data-api-description="${url}">${escapeHtml(apiDescription)}</span>
                </div>
                <div class="api-notification-actions">
                    <button class="api-action-btn api-copy-btn" title="${escapeHtml(safeT('api.copy_url_tooltip'))}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                    <button class="api-action-btn api-close-btn" title="${escapeHtml(safeT('api.close_tooltip'))}">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="api-notification-url" title="${escapeHtml(url)}">${escapeHtml(url)}</div>
        </div>
    `;

    // Add to body
    document.body.appendChild(notification);

    // Add to notification stack
    apiNotifications.unshift(notification);

    // Update all notification positions
    updateNotificationPositions();

    // Add copy button click handler
    const copyBtn = notification.querySelector('.api-copy-btn');
    if (copyBtn) {
        copyBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            copyApiUrl(url, copyBtn);
        });
    }

    // Add close button click handler
    const closeBtn = notification.querySelector('.api-close-btn');
    if (closeBtn) {
        closeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            closeApiNotification(notification);
        });
    }

    // Update the description text if it's still showing a translation key
    setTimeout(() => {
        const titleElement = notification.querySelector('.api-notification-title');
        if (titleElement && titleElement.textContent.startsWith('api.')) {
            // Translation key is showing, update it
            const newDescription = getApiDescription(url, method);
            if (newDescription !== titleElement.textContent) {
                titleElement.textContent = newDescription;
            }
        }
    }, 100);

    // Trigger animation
    setTimeout(() => notification.classList.add('show'), 10);

    // Auto-remove after 5 seconds
    const autoRemoveTimeout = setTimeout(() => {
        closeApiNotification(notification);
    }, 5000);

    // Store timeout ID for manual close
    notification.dataset.timeoutId = autoRemoveTimeout;
}

// Close API notification
function closeApiNotification(notification) {
    // Clear auto-remove timeout
    if (notification.dataset.timeoutId) {
        clearTimeout(parseInt(notification.dataset.timeoutId));
    }

    notification.classList.remove('show');
    setTimeout(() => {
        notification.remove();

        // Remove from stack
        const index = apiNotifications.indexOf(notification);
        if (index > -1) {
            apiNotifications.splice(index, 1);
        }

        // Update positions of remaining notifications
        updateNotificationPositions();
    }, 300);
}

// Copy API URL to clipboard
function copyApiUrl(url, button) {
    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(() => {
            showCopySuccess(button);
        }).catch(err => {
            console.error('Clipboard API failed:', err);
            // Fallback to execCommand
            fallbackCopyToClipboard(url, button);
        });
    } else {
        // Use fallback method
        fallbackCopyToClipboard(url, button);
    }
}

// Fallback copy method using execCommand
function fallbackCopyToClipboard(text, button) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '-9999px';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showCopySuccess(button);
        } else {
            showToast(safeT('errors.copy_failed'), 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast(safeT('errors.copy_failed'), 'error');
    } finally {
        document.body.removeChild(textArea);
    }
}

// Show copy success feedback
function showCopySuccess(button) {
    // Change button icon to checkmark
    button.innerHTML = `
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
            <path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
        </svg>
    `;
    button.classList.add('copied');

    // Show small toast
    const miniToast = document.createElement('div');
    miniToast.className = 'api-copy-toast';
    miniToast.textContent = safeT('api.copied');
    document.body.appendChild(miniToast);

    setTimeout(() => miniToast.classList.add('show'), 10);
    setTimeout(() => {
        miniToast.classList.remove('show');
        setTimeout(() => miniToast.remove(), 300);
    }, 1500);

    // Reset button icon after 2 seconds
    setTimeout(() => {
        button.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
            </svg>
        `;
        button.classList.remove('copied');
    }, 2000);
}

// Load Available Domains
async function loadAvailableDomains() {
    try {
        const response = await fetch(`${API_BASE}/api/domains`);
        const data = await response.json();

        if (data.success && data.data.domains) {
            const domains = data.data.domains;

            // Clear existing options (except the first "random" option)
            domainSelect.innerHTML = `<option value="">${safeT('common_labels.random_domain')}</option>`;

            // Add each domain as an option
            domains.forEach(domain => {
                const option = document.createElement('option');
                option.value = domain;
                option.textContent = domain;

                // Star only Cloudflare-provided (custom) domains
                const isCloudflareDomain = !BUILTIN_EMAIL_DOMAINS.includes(domain);
                if (isCloudflareDomain) {
                    option.textContent += ' ⭐';
                }

                domainSelect.appendChild(option);
            });
        }
    } catch (error) {
        console.error('Failed to load domains:', error);
        // Keep the random option as fallback
    }
}

// Generate Email
async function generateEmail() {
    setLoading(generateBtn, true);
    generateBtnText.textContent = safeT('common.status.loading');

    try {
        // Get custom prefix (trim whitespace)
        const customPrefix = emailPrefixInput ? emailPrefixInput.value.trim() : '';

        // Get selected domain (empty string means random)
        const selectedDomain = domainSelect.value;

        // Build URL with optional prefix and domain parameters
        let url = `${API_BASE}/api/email/generate`;
        const params = [];

        if (customPrefix) {
            params.push(`prefix=${encodeURIComponent(customPrefix)}`);
        }

        if (selectedDomain) {
            params.push(`domain=${encodeURIComponent(selectedDomain)}`);
        }

        if (params.length > 0) {
            url += '?' + params.join('&');
        }

        const response = await fetch(url, {
            method: 'POST'
        });

        const data = await response.json();

        if (data.success) {
            const expiresMs = typeof data.data.expiresAtMs === 'number'
                ? data.data.expiresAtMs
                : Date.parse(String(data.data.expiresAt).replace(/Z?$/, 'Z'));
            const emailData = {
                token: data.data.token,
                email: data.data.email,
                expiresAt: new Date(expiresMs),
                webUrl: data.data.webUrl,
                useCloudflareKV: data.data.useCloudflareKV || false,
                mails: [],
                mailCount: 0,
                isExpanded: true
            };

            emailsState.emails.push(emailData);

            renderEmailList();
            updateStats();
            startExpiresCountdown(emailData.token, emailData.expiresAt);

            // Skip initial mail fetch - new emails have no mails yet
            // Auto-refresh (10s) or manual refresh will fetch mails later
            // setTimeout(() => fetchMailsForEmail(emailData.token), 500);

            // Clear the custom prefix input after successful generation
            if (emailPrefixInput) {
                emailPrefixInput.value = '';
            }

            // Show success message
            showToast(`✓ ${emailData.email}`, 'success');

            // API call is already shown in notification box
        } else {
            showToast(safeT('errors.generation_failed') + ': ' + data.error, 'error');
        }
    } catch (error) {
        showToast(safeT('errors.network_error') + ': ' + error.message, 'error');
    } finally {
        setLoading(generateBtn, false);
        // Restore button text using i18n
        if (typeof window.updateDOM === 'function') {
            window.updateDOM(); // Re-translate all elements including button
        }
    }
}

// Render Email List
function renderEmailList() {
    if (emailsState.emails.length === 0) {
        emailList.innerHTML = `
            <div class="empty-state">
                <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                </svg>
                <h3>${safeT('email.list.empty_state_title')}</h3>
                <p>${safeT('email.list.empty_state_message')}</p>
            </div>
        `;
        return;
    }

    emailList.innerHTML = emailsState.emails.map((emailData, index) =>
        renderEmailCard(emailData, index)
    ).join('');

    // Update email count badge
    emailCount.textContent = emailsState.emails.length;
}

// Render Single Email Card
function renderEmailCard(emailData, index) {
    const collapsedClass = emailData.isExpanded ? '' : 'collapsed';
    const expiresStr = formatExpires(emailData.expiresAt);

    // Determine status badge
    let statusBadge = '';
    if (emailData.status === 'not_found') {
        statusBadge = '<span class="email-status-badge email-status-not-found">未找到</span>';
    } else if (emailData.status === 'error') {
        statusBadge = '<span class="email-status-badge email-status-error">錯誤</span>';
    } else if (formatExpires(emailData.expiresAt) === '已过期') {
        statusBadge = '<span class="email-status-badge email-status-expired">已過期</span>';
    }

    return `
        <div class="email-card ${collapsedClass}" data-token="${emailData.token}">
            <div class="email-card-header" onclick="toggleEmailCard('${emailData.token}')">
                <div class="email-card-info">
                    <div class="email-card-address">
                        <div class="email-card-address-text" title="${escapeHtml(emailData.email)}">
                            ${escapeHtml(emailData.email)}
                            ${statusBadge}
                        </div>
                    </div>
                    <div class="email-card-meta">
                        <div class="email-card-meta-item">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                            <span id="expires-${emailData.token}">${expiresStr}</span>
                        </div>
                        <div class="email-card-meta-item">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                            <span>${emailData.mailCount} 封邮件</span>
                        </div>
                    </div>
                </div>
                <div class="email-card-actions" onclick="event.stopPropagation()">
                    <button class="btn-icon-sm" onclick="copyEmailAddress('${escapeHtml(emailData.email)}')" title="复制邮箱">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                    ${emailData.webUrl && !emailData.useCloudflareKV ? `
                    <a href="${emailData.webUrl}" target="_blank" class="btn-icon-sm" title="在外部查看">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </a>
                    ` : ''}
                    <button class="btn-icon-sm btn-delete" onclick="deleteEmail('${emailData.token}')" title="删除邮箱">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                    <button class="btn-toggle" title="展开/收起">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                </div>
            </div>
            <div class="email-card-body">
                <div class="email-card-divider"></div>
                <div class="email-card-mailbox">
                    <div class="email-card-mailbox-header">
                        <div class="mailbox-title">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                            收件箱
                            <span class="mailbox-count" id="mailbox-count-${emailData.token}">${emailData.mailCount}</span>
                        </div>
                        <button class="mailbox-refresh" onclick="fetchMailsForEmail('${emailData.token}')" title="刷新">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                        </button>
                    </div>
                    <div class="mail-list-in-card" id="mail-list-${emailData.token}">
                        ${renderMailList(emailData)}
                    </div>
                </div>
            </div>
        </div>
    `;
}

// Render Mail List for an Email
function renderMailList(emailData) {
    if (emailData.mails.length === 0) {
        return `
            <div class="empty-state">
                <svg class="empty-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                </svg>
                <h3>${safeT('email.mail.no_mails_title')}</h3>
                <p>${safeT('email.mail.no_mails_message')}</p>
            </div>
        `;
    }

    return emailData.mails.map(mail => {
        // Check if codes were previously extracted and displayed
        const cached = emailsState.mailDetailsCache[mail.id];
        const shouldShowCodes = cached?.codesExpanded === true;
        let codesHTML = '';

        if (shouldShowCodes && cached.codes) {
            // Render cached codes directly
            if (cached.codes.length > 0) {
                codesHTML = `
                    <div class="codes-result" style="display: block;">
                        <div class="codes-header">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                            <span>已找到 ${cached.codes.length} 个验证码：</span>
                            <button class="codes-close-btn" onclick="closeCodesInline('${mail.id}')" title="关闭">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                    <path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                                </svg>
                            </button>
                        </div>
                        <div class="codes-list">
                            ${cached.codes.map(code => `
                                <span class="code-chip" onclick="copyCodeFromChip(this, '${code.code}')" title="点击复制">
                                    ${code.code}
                                </span>
                            `).join('')}
                        </div>
                    </div>
                `;
            } else {
                codesHTML = `
                    <div class="codes-result" style="display: block;">
                        <div class="codes-empty">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                            <span>未找到验证码</span>
                            <button class="codes-close-btn" onclick="closeCodesInline('${mail.id}')" title="关闭">
                                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                    <path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                                </svg>
                            </button>
                        </div>
                    </div>
                `;
            }
        } else {
            codesHTML = `<div class="codes-result" style="display: none;"></div>`;
        }

        return `
            <div class="mail-item" data-mail-id="${mail.id}">
                <div class="mail-header">
                    <div class="mail-subject" onclick="showMailDetail('${emailData.token}', '${mail.id}')">${escapeHtml(mail.subject)}</div>
                    <button class="btn-extract-code" onclick="event.stopPropagation(); extractAndShowCodes('${emailData.token}', '${mail.id}')" title="提取验证码">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M15 7a2 2 0 012 2m4 0a6 6 0 01-7.743 5.743L11 17H9v2H7v2H4a1 1 0 01-1-1v-2.586a1 1 0 01.293-.707l5.964-5.964A6 6 0 1121 9z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                        <span>提取验证码</span>
                    </button>
                </div>
                <div class="mail-info">
                    <span>从: ${escapeHtml(mail.from)}</span>
                    <span>${formatTime(mail.receivedAt)}</span>
                </div>
                <div class="mail-preview" onclick="showMailDetail('${emailData.token}', '${mail.id}')">${escapeHtml(mail.content)}</div>
                <div class="mail-codes-inline" id="codes-${mail.id}" style="display: ${shouldShowCodes ? 'block' : 'none'};">
                    <div class="codes-loading" style="display: none;">
                        <svg class="spinner" viewBox="0 0 24 24">
                            <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none" stroke-dasharray="32" stroke-dashoffset="32">
                                <animate attributeName="stroke-dashoffset" dur="1s" repeatCount="indefinite" from="32" to="0"/>
                            </circle>
                        </svg>
                        <span>提取中...</span>
                    </div>
                    ${codesHTML}
                </div>
            </div>
        `;
    }).join('');
}

// Fetch Mails for Specific Email
async function fetchMailsForEmail(token) {
    const emailData = emailsState.emails.find(e => e.token === token);
    if (!emailData) return;

    // Get mail list container
    const mailListContainer = document.getElementById(`mail-list-${token}`);

    // Add loading indicator at the top (don't replace existing content)
    let loadingIndicator = mailListContainer.querySelector('.mail-list-loading');

    // Only show loading if there's no existing mails or if loading indicator doesn't exist
    if (mailListContainer && !loadingIndicator) {
        loadingIndicator = document.createElement('div');
        loadingIndicator.className = 'mail-list-loading';
        loadingIndicator.innerHTML = `
            <div class="mail-list-loading-spinner"></div>
            <div class="mail-list-loading-text">加載郵件中...</div>
        `;
        // Insert at the beginning of the container
        mailListContainer.insertBefore(loadingIndicator, mailListContainer.firstChild);
    }

    // Record start time to ensure minimum loading display duration
    const startTime = Date.now();
    const MIN_LOADING_TIME = 800; // Minimum 800ms

    try {
        const response = await fetch(`${API_BASE}/api/email/${token}/mails?limit=50`);
        const data = await response.json();

        // Ensure loading is shown for at least MIN_LOADING_TIME
        const elapsedTime = Date.now() - startTime;
        const remainingTime = Math.max(0, MIN_LOADING_TIME - elapsedTime);

        if (remainingTime > 0) {
            await new Promise(resolve => setTimeout(resolve, remainingTime));
        }

        // Remove loading indicator
        if (loadingIndicator && loadingIndicator.parentNode) {
            loadingIndicator.remove();
        }

        if (response.ok && data.success) {
            // Clear error status if previously set
            emailData.status = 'active';

            // Deduplicate mails
            const existingIds = new Set(emailData.mails.map(m => m.id));
            const newMails = data.data.mails.filter(m => !existingIds.has(m.id));

            emailData.mails = [...emailData.mails, ...newMails];
            emailData.mailCount = data.data.total;

            // 🆕 將完整郵件內容存入緩存（避免後續查看詳情時重複調用 API）
            data.data.mails.forEach(mail => {
                emailsState.mailDetailsCache[mail.id] = {
                    subject: mail.subject,
                    from: mail.from,
                    to: mail.to,  // 新 API 現在包含 to 字段
                    content: mail.content,  // 完整純文字內容
                    htmlContent: mail.htmlContent,  // 完整 HTML 內容
                    receivedAt: mail.receivedAt,
                    codes: null,  // 驗證碼需要手動提取
                    links: mail.links || []  // 自動提取的鏈接
                };
            });

            // Update the specific email card's mail list with actual data
            const mailboxCount = document.getElementById(`mailbox-count-${token}`);

            if (mailListContainer) {
                mailListContainer.innerHTML = renderMailList(emailData);
            }
            if (mailboxCount) {
                mailboxCount.textContent = emailData.mailCount;
            }

            // Update the email card meta to reflect new mail count
            const emailCard = document.querySelector(`.email-card[data-token="${token}"]`);
            if (emailCard) {
                const metaItem = emailCard.querySelector('.email-card-meta-item:last-child span');
                if (metaItem) {
                    metaItem.textContent = `${emailData.mailCount} 封邮件`;
                }
            }

            updateStats();

            // Re-render the card to update status badge
            renderEmailList();
        } else if (response.status === 404 && data.detail === "邮箱未找到") {
            // Remove loading indicator
            if (loadingIndicator && loadingIndicator.parentNode) {
                loadingIndicator.remove();
            }

            // Handle "邮箱未找到" (Email not found) error
            emailData.status = 'not_found';

            // Clear loading and show error state
            if (mailListContainer) {
                mailListContainer.innerHTML = renderMailList(emailData);
            }

            // Show alert to user
            alert(`错误：${data.detail}\n\n邮箱 ${emailData.email} 在服务器上未找到。\n可能原因：\n- 邮箱已过期\n- Token 已失效\n- 后端存储已清空`);

            // Re-render the card to show error status
            renderEmailList();
        }
    } catch (error) {
        console.error('Failed to fetch mails:', error);

        // Remove loading indicator
        if (loadingIndicator && loadingIndicator.parentNode) {
            loadingIndicator.remove();
        }

        // Mark email as error state and clear loading
        emailData.status = 'error';
        if (mailListContainer) {
            mailListContainer.innerHTML = renderMailList(emailData);
        }
        renderEmailList();
    }
}

// Refresh All Emails
async function refreshAllEmails() {
    const promises = emailsState.emails.map(emailData =>
        fetchMailsForEmail(emailData.token)
    );

    await Promise.all(promises);
    // API calls are already shown in notification box
}

// Toggle Email Card Expand/Collapse
function toggleEmailCard(token) {
    const emailData = emailsState.emails.find(e => e.token === token);
    if (emailData) {
        emailData.isExpanded = !emailData.isExpanded;

        const card = document.querySelector(`.email-card[data-token="${token}"]`);
        if (card) {
            card.classList.toggle('collapsed');
        }
    }
}

// Copy Email Address
function copyEmailAddress(email) {
    // Decode HTML entities that might have been escaped
    const textarea = document.createElement('textarea');
    textarea.innerHTML = email;
    const decodedEmail = textarea.value;

    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(decodedEmail).then(() => {
            showToast(safeT('messages.email_copied'), 'success');
        }).catch(err => {
            console.error('Clipboard API failed:', err);
            // Fallback to execCommand
            fallbackCopyEmail(decodedEmail);
        });
    } else {
        // Use fallback method
        fallbackCopyEmail(decodedEmail);
    }
}

// Fallback copy method for email addresses
function fallbackCopyEmail(email) {
    const textArea = document.createElement('textarea');
    textArea.value = email;
    textArea.style.position = 'fixed';
    textArea.style.top = '-9999px';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showToast(safeT('messages.email_copied'), 'success');
        } else {
            showToast(safeT('errors.copy_failed'), 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast(safeT('errors.copy_failed'), 'error');
    } finally {
        document.body.removeChild(textArea);
    }
}

// Delete Email
function deleteEmail(token) {
    if (!confirm(safeT('messages.confirm_delete'))) return;

    // Clear expires interval
    if (emailsState.expiresIntervals[token]) {
        clearInterval(emailsState.expiresIntervals[token]);
        delete emailsState.expiresIntervals[token];
    }

    // Remove from state
    emailsState.emails = emailsState.emails.filter(e => e.token !== token);

    // Re-render
    renderEmailList();
    updateStats();

    showToast(safeT('messages.email_deleted'), 'success');
}

// View Mode State (HTML or Text)
let currentViewMode = 'html'; // 'html' or 'text'

// Toggle View Mode (HTML/Text)
function toggleViewMode() {
    const viewModeText = document.getElementById('viewModeText');
    const htmlContent = document.getElementById('modalContentHtml');
    const textContent = document.getElementById('modalContent');

    if (currentViewMode === 'html') {
        // Switch to text mode
        currentViewMode = 'text';
        htmlContent.style.display = 'none';
        textContent.style.display = 'block';
        if (viewModeText) {
            viewModeText.textContent = '文本';
        }
    } else {
        // Switch to HTML mode
        currentViewMode = 'html';
        htmlContent.style.display = 'block';
        textContent.style.display = 'none';
        if (viewModeText) {
            viewModeText.textContent = 'HTML';
        }
    }
}

// Show Mail Detail - WITH HTML SUPPORT
async function showMailDetail(token, mailId) {
    const emailData = emailsState.emails.find(e => e.token === token);
    if (!emailData) {
        console.error('[showMailDetail] Email data not found for token:', token);
        return;
    }

    console.log('[showMailDetail] Showing detail for mailId:', mailId);

    // Store current mail context for manual code extraction
    window.currentMailContext = { token, mailId };

    // 显示加载状态的模态框
    document.getElementById('modalSubject').textContent = '载入中...';
    document.getElementById('modalFrom').textContent = '载入中...';
    document.getElementById('modalDate').textContent = '载入中...';
    document.getElementById('modalContent').textContent = '正在载入邮件内容...';
    document.getElementById('modalContentHtml').innerHTML = '<p style="color: #999;">正在载入邮件内容...</p>';

    // Reset codes section
    const codesSection = document.getElementById('modalCodes');
    const extractBtn = document.getElementById('extractCodesModalBtn');
    const codesContent = document.getElementById('modalCodesContent');

    codesSection.style.display = 'none';
    if (extractBtn) extractBtn.style.display = 'block';
    if (codesContent) codesContent.innerHTML = '';

    mailModal.style.display = 'flex';

    // Add toggle button event listener (only once)
    const viewModeToggle = document.getElementById('viewModeToggle');
    if (viewModeToggle && !viewModeToggle.hasAttribute('data-listener-attached')) {
        viewModeToggle.addEventListener('click', toggleViewMode);
        viewModeToggle.setAttribute('data-listener-attached', 'true');
    }

    // 🆕 優化：完全依賴緩存，不再調用 API
    // 因為 fetchMailsForEmail() 已經將完整內容存入緩存
    if (!emailsState.mailDetailsCache[mailId]) {
        // 緩存不存在，顯示錯誤提示
        console.warn('[showMailDetail] Mail details not in cache, mailId:', mailId);

        document.getElementById('modalSubject').textContent = '郵件數據未載入';
        document.getElementById('modalFrom').textContent = '請刷新郵件列表';
        document.getElementById('modalDate').textContent = '';
        document.getElementById('modalContent').textContent = '郵件詳情尚未載入到本地緩存。\n\n請點擊收件箱旁邊的"刷新"按鈕重新獲取郵件列表，然後再次嘗試查看此郵件。';
        document.getElementById('modalContentHtml').innerHTML = '<p style="color: #999; text-align: center; padding: 40px;">郵件詳情尚未載入，請刷新郵件列表後重試。</p>';

        showToast('郵件詳情不在緩存中，請刷新郵件列表', 'warning');
        return;
    }

    // 使用緩存的完整數據
    const cached = emailsState.mailDetailsCache[mailId];
    console.log('[showMailDetail] Using cached data (no API call):', cached);

    // 更新顯示
    document.getElementById('modalSubject').textContent = cached.subject || '（無主題）';
    document.getElementById('modalFrom').textContent = cached.from || '未知發件人';
    document.getElementById('modalDate').textContent = formatFullTime(cached.receivedAt) || '時間未知';

    // 渲染文本內容 (純文本)
    document.getElementById('modalContent').textContent = cached.content || '（郵件內容為空）';

    // 渲染 HTML 內容
    const htmlContentDiv = document.getElementById('modalContentHtml');
    if (cached.htmlContent) {
        htmlContentDiv.innerHTML = cached.htmlContent; // 後端已清理過，安全渲染
    } else {
        // 如果沒有 HTML 內容，顯示純文本
        htmlContentDiv.innerHTML = `<pre style="white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(cached.content || '（郵件內容為空）')}</pre>`;
    }

    // 默認顯示 HTML 模式
    currentViewMode = 'html';
    htmlContentDiv.style.display = 'block';
    document.getElementById('modalContent').style.display = 'none';
    const viewModeText = document.getElementById('viewModeText');
    if (viewModeText) viewModeText.textContent = 'HTML';

    // 顯示鏈接（如果有）
    if (cached.links && cached.links.length > 0) {
        displayLinksInModal(cached.links);
    } else {
        // 隱藏鏈接區域
        const linksSection = document.getElementById('modalLinks');
        if (linksSection) linksSection.style.display = 'none';
    }

    // 檢查是否已經提取驗證碼
    if (cached.codes !== null && cached.codes !== undefined) {
        // 隱藏提取按鈕，顯示已有的驗證碼
        if (extractBtn) extractBtn.style.display = 'none';
        displayCodesInModal(cached.codes);
    } else {
        // 顯示提取按鈕
        codesSection.style.display = 'block';
    }
}

// Manual Extract Codes in Modal
async function manualExtractCodesInModal() {
    if (!window.currentMailContext) {
        showToast('无法提取验证码，请重新打开邮件', 'error');
        return;
    }

    const { token, mailId } = window.currentMailContext;

    const extractBtn = document.getElementById('extractCodesModalBtn');
    const codesContent = document.getElementById('modalCodesContent');

    // Show loading state
    if (extractBtn) {
        setLoading(extractBtn, true);
        extractBtn.querySelector('span').textContent = '提取中...';
    }

    try {
        const response = await fetch(`${API_BASE}/api/email/${token}/codes?mail_id=${mailId}`);
        const data = await response.json();

        // Store in cache
        if (emailsState.mailDetailsCache[mailId]) {
            emailsState.mailDetailsCache[mailId].codes = data.success ? data.data.codes : [];
        } else {
            emailsState.mailDetailsCache[mailId] = {
                codes: data.success ? data.data.codes : []
            };
        }

        // Hide button and show results
        if (extractBtn) {
            extractBtn.style.display = 'none';
            setLoading(extractBtn, false);
        }

        // Display codes
        displayCodesInModal(data.success ? data.data.codes : []);

    } catch (error) {
        console.error('Failed to extract codes:', error);
        showToast(safeT('errors.extract_codes_failed'), 'error');

        // Reset button state
        if (extractBtn) {
            setLoading(extractBtn, false);
            extractBtn.querySelector('span').textContent = '提取验证码';
        }

        // Store empty codes in cache
        if (emailsState.mailDetailsCache[mailId]) {
            emailsState.mailDetailsCache[mailId].codes = [];
        }
    }
}

// Display Codes in Modal
function displayCodesInModal(codes) {
    const codesContent = document.getElementById('modalCodesContent');
    const codesSection = document.getElementById('modalCodes');

    if (!codesContent || !codesSection) return;

    if (codes.length > 0) {
        codesContent.innerHTML = codes.map(code => `
            <span class="code-item" onclick="copyCode('${code.code}')" title="点击复制">
                ${code.code}
            </span>
        `).join('');
        codesContent.style.display = 'block';

        // Show the codes header
        const codesHeader = codesSection.querySelector('.codes-header');
        if (codesHeader) codesHeader.style.display = 'flex';

        codesSection.style.display = 'block';
    } else {
        codesContent.innerHTML = '<p style="color: #999; text-align: center; padding: 20px;">未找到验证码</p>';
        codesContent.style.display = 'block';

        // Hide codes header if no codes found
        const codesHeader = codesSection.querySelector('.codes-header');
        if (codesHeader) codesHeader.style.display = 'none';

        codesSection.style.display = 'block';
    }
}

// Display Links in Modal
function displayLinksInModal(links) {
    const linksContent = document.getElementById('modalLinksContent');
    const linksSection = document.getElementById('modalLinks');

    if (!linksContent || !linksSection) return;

    if (links && links.length > 0) {
        linksContent.innerHTML = links.map(link => {
            const escapedUrl = escapeHtml(link.url);
            const escapedText = escapeHtml(link.text || link.url);
            const shortUrl = link.url.length > 60 ? link.url.substring(0, 57) + '...' : link.url;
            
            return `
                <div class="link-item">
                    <svg class="link-item-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                    </svg>
                    <div class="link-item-content">
                        <div class="link-item-text">${escapedText}</div>
                        <div class="link-item-url" title="${escapedUrl}">${escapeHtml(shortUrl)}</div>
                    </div>
                    <div class="link-item-actions">
                        <button class="link-btn link-btn-open" onclick="openLink('${escapedUrl}')" title="Open link in new tab">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                            Open
                        </button>
                        <button class="link-btn link-btn-copy" onclick="copyLink('${escapedUrl}')" title="Copy link">
                            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                                <path d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                            </svg>
                            Copy
                        </button>
                    </div>
                </div>
            `;
        }).join('');
        
        linksSection.style.display = 'block';
    } else {
        linksSection.style.display = 'none';
    }
}

// Open link in new tab
function openLink(url) {
    // Decode HTML entities
    const textarea = document.createElement('textarea');
    textarea.innerHTML = url;
    const decodedUrl = textarea.value;
    
    window.open(decodedUrl, '_blank', 'noopener,noreferrer');
    showToast('Opening link in new tab...', 'success');
}

// Copy link to clipboard
function copyLink(url) {
    // Decode HTML entities
    const textarea = document.createElement('textarea');
    textarea.innerHTML = url;
    const decodedUrl = textarea.value;
    
    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(decodedUrl).then(() => {
            showToast('Link copied to clipboard!', 'success');
        }).catch(err => {
            console.error('Clipboard API failed:', err);
            fallbackCopyText(decodedUrl);
        });
    } else {
        fallbackCopyText(decodedUrl);
    }
}

// Fallback copy method
function fallbackCopyText(text) {
    const textArea = document.createElement('textarea');
    textArea.value = text;
    textArea.style.position = 'fixed';
    textArea.style.top = '-9999px';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();
    
    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showToast('Link copied to clipboard!', 'success');
        } else {
            showToast('Failed to copy link', 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast('Failed to copy link', 'error');
    } finally {
        document.body.removeChild(textArea);
    }
}

// Fetch Mail Codes (kept for backward compatibility but no longer auto-called)
async function fetchMailCodes(token, mailId) {
    const codesElement = document.getElementById('modalCodes');
    const codesContent = document.getElementById('modalCodesContent');

    // 获取或创建 loading 元素
    let loadingElement = codesElement.querySelector('.codes-loading');
    if (!loadingElement) {
        loadingElement = document.createElement('div');
        loadingElement.className = 'codes-loading';
        loadingElement.innerHTML = `
            <svg class="spinner" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4" fill="none"
                        stroke-dasharray="32" stroke-dashoffset="32">
                    <animate attributeName="stroke-dashoffset" dur="1s" repeatCount="indefinite"
                             from="32" to="0"/>
                </circle>
            </svg>
            <span>提取验证码中...</span>
        `;
        codesElement.insertBefore(loadingElement, codesContent);
    }

    // 显示 loading 状态
    codesElement.style.display = 'block';
    loadingElement.style.display = 'flex';
    codesContent.style.display = 'none';

    // Check cache first
    if (emailsState.mailDetailsCache[mailId] && emailsState.mailDetailsCache[mailId].codes !== null) {
        const cachedCodes = emailsState.mailDetailsCache[mailId].codes;

        // 隐藏 loading
        loadingElement.style.display = 'none';

        // Use cached codes
        if (cachedCodes.length > 0) {
            codesContent.innerHTML = cachedCodes.map(code => `
                <span class="code-item" onclick="copyCode('${code.code}')" title="点击复制">
                    ${code.code}
                </span>
            `).join('');
            codesContent.style.display = 'block';
        } else {
            codesElement.style.display = 'none';
        }
        return;
    }

    // No cache, fetch from server
    try {
        const response = await fetch(`${API_BASE}/api/email/${token}/codes?mail_id=${mailId}`);
        const data = await response.json();

        // 隐藏 loading
        loadingElement.style.display = 'none';

        // Store in cache
        if (emailsState.mailDetailsCache[mailId]) {
            emailsState.mailDetailsCache[mailId].codes = data.success ? data.data.codes : [];
        } else {
            // Initialize cache entry if not exists
            emailsState.mailDetailsCache[mailId] = {
                codes: data.success ? data.data.codes : []
            };
        }

        if (data.success && data.data.codes.length > 0) {
            codesContent.innerHTML = data.data.codes.map(code => `
                <span class="code-item" onclick="copyCode('${code.code}')" title="点击复制">
                    ${code.code}
                </span>
            `).join('');
            codesContent.style.display = 'block';
        } else {
            codesElement.style.display = 'none';
        }
    } catch (error) {
        console.error('Failed to fetch codes:', error);

        // 隐藏 loading
        loadingElement.style.display = 'none';
        codesElement.style.display = 'none';

        // Store empty codes in cache on error to avoid repeated failed requests
        if (emailsState.mailDetailsCache[mailId]) {
            emailsState.mailDetailsCache[mailId].codes = [];
        } else {
            emailsState.mailDetailsCache[mailId] = { codes: [] };
        }
    }
}

// Extract and Show Codes Inline
async function extractAndShowCodes(token, mailId) {
    const codesContainer = document.getElementById(`codes-${mailId}`);
    const loadingElement = codesContainer.querySelector('.codes-loading');
    const resultElement = codesContainer.querySelector('.codes-result');

    // Check cache first
    if (emailsState.mailDetailsCache[mailId] && emailsState.mailDetailsCache[mailId].codes !== null) {
        const cachedCodes = emailsState.mailDetailsCache[mailId].codes;

        // Show container
        codesContainer.style.display = 'block';
        loadingElement.style.display = 'none';

        // Use cached codes
        if (cachedCodes.length > 0) {
            resultElement.innerHTML = `
                <div class="codes-header">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                    </svg>
                    <span>已找到 ${cachedCodes.length} 个验证码：</span>
                </div>
                <div class="codes-list">
                    ${cachedCodes.map(code => `
                        <span class="code-chip" onclick="copyCodeFromChip(this, '${code.code}')" title="点击复制">
                            ${code.code}
                        </span>
                    `).join('')}
                </div>
            `;
            resultElement.style.display = 'block';
        } else {
            resultElement.innerHTML = `
                <div class="codes-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                    </svg>
                    <span>未找到验证码</span>
                </div>
            `;
            resultElement.style.display = 'block';
        }
        return;
    }

    // No cache, show loading and fetch from server
    codesContainer.style.display = 'block';
    loadingElement.style.display = 'flex';
    resultElement.style.display = 'none';

    try {
        const response = await fetch(`${API_BASE}/api/email/${token}/codes?mail_id=${mailId}`);
        const data = await response.json();

        // Hide loading
        loadingElement.style.display = 'none';

        // Store in cache
        if (emailsState.mailDetailsCache[mailId]) {
            emailsState.mailDetailsCache[mailId].codes = data.success ? data.data.codes : [];
            emailsState.mailDetailsCache[mailId].codesExpanded = data.success && data.data.codes.length > 0;
        } else {
            emailsState.mailDetailsCache[mailId] = {
                codes: data.success ? data.data.codes : [],
                codesExpanded: data.success && data.data.codes.length > 0
            };
        }

        if (data.success && data.data.codes.length > 0) {
            // Show codes
            resultElement.innerHTML = `
                <div class="codes-header">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                    </svg>
                    <span>已找到 ${data.data.codes.length} 个验证码：</span>
                    <button class="codes-close-btn" onclick="closeCodesInline('${mailId}')" title="关闭">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                </div>
                <div class="codes-list">
                    ${data.data.codes.map(code => `
                        <span class="code-chip" onclick="copyCodeFromChip(this, '${code.code}')" title="点击复制">
                            ${code.code}
                        </span>
                    `).join('')}
                </div>
            `;
            resultElement.style.display = 'block';
        } else {
            resultElement.innerHTML = `
                <div class="codes-empty">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                    </svg>
                    <span>未找到验证码</span>
                    <button class="codes-close-btn" onclick="closeCodesInline('${mailId}')" title="关闭">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                </div>
            `;
            resultElement.style.display = 'block';
        }
    } catch (error) {
        loadingElement.style.display = 'none';
        resultElement.innerHTML = `
            <div class="codes-error">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                    <path d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                </svg>
                <span>提取失败，请重试</span>
                <button class="codes-close-btn" onclick="closeCodesInline('${mailId}')" title="关闭">
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                        <path d="M6 18L18 6M6 6l12 12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                    </svg>
                </button>
            </div>
        `;
        resultElement.style.display = 'block';

        // Store empty codes in cache on error
        if (emailsState.mailDetailsCache[mailId]) {
            emailsState.mailDetailsCache[mailId].codes = [];
            emailsState.mailDetailsCache[mailId].codesExpanded = false;
        } else {
            emailsState.mailDetailsCache[mailId] = { codes: [], codesExpanded: false };
        }
    }
}

// Copy Code from Chip with Visual Feedback
function copyCodeFromChip(chipElement, code) {
    // Helper function to show success feedback
    const showSuccessFeedback = () => {
        // Visual feedback
        const originalBg = chipElement.style.backgroundColor;
        chipElement.style.backgroundColor = '#10b981';
        chipElement.innerHTML = `
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" style="width: 16px; height: 16px; display: inline-block; margin-right: 4px;">
                <path d="M5 13l4 4L19 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
            </svg>
            已复制
        `;

        // Show toast
        showToast('验证码已复制: ' + code, 'success');

        // Reset after 2 seconds
        setTimeout(() => {
            chipElement.style.backgroundColor = originalBg;
            chipElement.textContent = code;
        }, 2000);
    };

    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(() => {
            showSuccessFeedback();
        }).catch(err => {
            console.error('Clipboard API failed:', err);
            // Fallback to execCommand
            fallbackCopyCode(code, showSuccessFeedback);
        });
    } else {
        // Use fallback method
        fallbackCopyCode(code, showSuccessFeedback);
    }
}

// Fallback copy method for verification codes
function fallbackCopyCode(code, onSuccess) {
    const textArea = document.createElement('textarea');
    textArea.value = code;
    textArea.style.position = 'fixed';
    textArea.style.top = '-9999px';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            if (onSuccess) onSuccess();
        } else {
            showToast(safeT('errors.copy_failed'), 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast(safeT('errors.copy_failed'), 'error');
    } finally {
        document.body.removeChild(textArea);
    }
}

// Copy Code (for modal)
function copyCode(code) {
    // Try modern clipboard API first
    if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(code).then(() => {
            showToast('验证码已复制: ' + code, 'success');
        }).catch(err => {
            console.error('Clipboard API failed:', err);
            // Fallback to execCommand
            fallbackCopyCodeSimple(code);
        });
    } else {
        // Use fallback method
        fallbackCopyCodeSimple(code);
    }
}

// Simple fallback copy for modal
function fallbackCopyCodeSimple(code) {
    const textArea = document.createElement('textarea');
    textArea.value = code;
    textArea.style.position = 'fixed';
    textArea.style.top = '-9999px';
    textArea.style.left = '-9999px';
    document.body.appendChild(textArea);
    textArea.focus();
    textArea.select();

    try {
        const successful = document.execCommand('copy');
        if (successful) {
            showToast('验证码已复制: ' + code, 'success');
        } else {
            showToast(safeT('errors.copy_failed'), 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast(safeT('errors.copy_failed'), 'error');
    } finally {
        document.body.removeChild(textArea);
    }
}

// Toggle Auto Refresh
function toggleAutoRefresh() {
    const autoRefreshText = document.getElementById('autoRefreshText');

    if (emailsState.autoRefreshInterval) {
        clearInterval(emailsState.autoRefreshInterval);
        emailsState.autoRefreshInterval = null;
        autoRefreshBtn.classList.remove('active');
        if (autoRefreshText) {
            autoRefreshText.textContent = safeT('api.auto_refresh.toggle', {status: safeT('api.auto_refresh.off')});
        }
        // Save preference to cookie
        setCookie('autoRefreshEnabled', 'false', 365);
    } else {
        emailsState.autoRefreshInterval = setInterval(refreshAllEmails, 10000); // 每10秒
        autoRefreshBtn.classList.add('active');
        if (autoRefreshText) {
            autoRefreshText.textContent = safeT('api.auto_refresh.toggle', {status: safeT('api.auto_refresh.on')});
        }
        showToast(safeT('messages.auto_refresh_enabled'), 'success');
        // Save preference to cookie
        setCookie('autoRefreshEnabled', 'true', 365);
    }
}

// Start Expires Countdown
function startExpiresCountdown(token, expiresDate) {
    if (emailsState.expiresIntervals[token]) {
        clearInterval(emailsState.expiresIntervals[token]);
    }

    emailsState.expiresIntervals[token] = setInterval(() => {
        const now = new Date();
        const diff = expiresDate - now;

        const expiresElement = document.getElementById(`expires-${token}`);
        if (!expiresElement) {
            clearInterval(emailsState.expiresIntervals[token]);
            delete emailsState.expiresIntervals[token];
            return;
        }

        if (diff <= 0) {
            expiresElement.textContent = '已过期';
            expiresElement.style.color = 'var(--danger)';
            clearInterval(emailsState.expiresIntervals[token]);
            delete emailsState.expiresIntervals[token];
            return;
        }

        expiresElement.textContent = formatExpires(expiresDate);
    }, 1000);
}

// Update Stats
function updateStats() {
    const totalMails = emailsState.emails.reduce((sum, e) => sum + e.mailCount, 0);

    statEmailCount.textContent = emailsState.emails.length;
    statTotalMails.textContent = totalMails;
}

// Format Expires Time
function formatExpires(expiresDate) {
    const now = new Date();
    const diff = expiresDate - now;

    if (diff <= 0) return '已过期';

    const minutes = Math.floor(diff / 1000 / 60);
    const seconds = Math.floor((diff / 1000) % 60);
    return `${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
}

// Cookie Utility Functions
function setCookie(name, value, days) {
    const expires = new Date();
    expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000);
    document.cookie = `${name}=${value};expires=${expires.toUTCString()};path=/`;
}

function getCookie(name) {
    const nameEQ = name + "=";
    const ca = document.cookie.split(';');
    for (let i = 0; i < ca.length; i++) {
        let c = ca[i];
        while (c.charAt(0) === ' ') c = c.substring(1, c.length);
        if (c.indexOf(nameEQ) === 0) return c.substring(nameEQ.length, c.length);
    }
    return null;
}

// Utility Functions
function setLoading(button, loading) {
    if (loading) {
        button.classList.add('loading');
        button.disabled = true;
    } else {
        button.classList.remove('loading');
        button.disabled = false;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function formatTime(isoString) {
    const date = new Date(isoString);
    const now = new Date();
    const diff = (now - date) / 1000; // seconds

    if (diff < 60) return safeT('common.time.just_now', {}, 'Just now');
    if (diff < 3600) {
        const minutes = Math.floor(diff / 60);
        return `${minutes} ${safeT('common.time.minutes', {}, 'minutes')} ${safeT('common.time.ago', {}, 'ago')}`;
    }
    if (diff < 86400) {
        const hours = Math.floor(diff / 3600);
        return `${hours} ${safeT('common.time.hours', {}, 'hours')} ${safeT('common.time.ago', {}, 'ago')}`;
    }

    // Get current language for locale formatting
    const currentLang = (typeof window.getCurrentLanguage === 'function' ? window.getCurrentLanguage() : 'en-US');
    const locale = currentLang === 'zh-CN' ? 'zh-CN' : 'en-US';

    return date.toLocaleDateString(locale, {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatFullTime(isoString) {
    // Validate input
    if (!isoString) {
        console.warn('[formatFullTime] Invalid input:', isoString);
        return safeT('errors.time_unknown', {}, 'Unknown time');
    }

    const date = new Date(isoString);

    // Check if date is valid
    if (isNaN(date.getTime())) {
        console.warn('[formatFullTime] Invalid date:', isoString);
        return safeT('errors.time_format_error', {}, 'Invalid time format');
    }

    // Get current language for locale formatting
    const currentLang = (typeof window.getCurrentLanguage === 'function' ? window.getCurrentLanguage() : 'en-US');
    const locale = currentLang === 'zh-CN' ? 'zh-CN' : 'en-US';

    return date.toLocaleString(locale, {
        year: 'numeric',
        month: 'long',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function showToast(message, type = 'info') {
    // Create toast element
    const toast = document.createElement('div');
    toast.className = 'toast toast-' + type;
    toast.textContent = message;
    toast.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        background: ${type === 'success' ? '#10b981' : type === 'error' ? '#ef4444' : '#3b82f6'};
        color: white;
        padding: 15px 20px;
        border-radius: 12px;
        box-shadow: 0 10px 25px rgba(0,0,0,0.15);
        z-index: 10000;
        font-weight: 600;
        animation: slideIn 0.3s ease;
    `;

    document.body.appendChild(toast);

    setTimeout(() => {
        toast.style.animation = 'slideOut 0.3s ease';
        setTimeout(() => toast.remove(), 300);
    }, 3000);
}

// Add animations
const style = document.createElement('style');
style.textContent = `
    @keyframes slideIn {
        from {
            transform: translateX(400px);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    @keyframes slideOut {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(400px);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Terminal API Log Functions
function logApiToTerminal(method, url, details = null) {
    const timestamp = new Date();
    const logEntry = {
        method,
        url,
        timestamp,
        description: getApiDescription(url, method),
        details,
        id: `log-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
    };

    terminalLogs.push(logEntry);

    // Keep only last MAX_TERMINAL_LOGS entries
    if (terminalLogs.length > MAX_TERMINAL_LOGS) {
        terminalLogs.shift();
    }

    renderTerminalLog(logEntry);
    updateTerminalCount();
}

function renderTerminalLog(logEntry) {
    if (!terminalOutput) return;

    const timestamp = logEntry.timestamp.toLocaleTimeString('zh-CN', {
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const methodClass = logEntry.method.toLowerCase();
    const hasDetails = logEntry.details !== null;
    const isError = logEntry.details?.error === true;
    const statusClass = isError ? 'error' : (logEntry.details?.response?.status >= 200 && logEntry.details?.response?.status < 300) ? 'success' : 'warning';

    const logContainer = document.createElement('div');
    logContainer.className = `terminal-log-entry ${hasDetails ? 'expandable' : ''}`;
    logContainer.id = logEntry.id;

    // Main log line
    const logLine = document.createElement('div');
    logLine.className = 'terminal-line terminal-line-main';

    let statusInfo = '';
    if (hasDetails && logEntry.details.response) {
        const status = logEntry.details.response.status;
        const duration = logEntry.details.duration;
        statusInfo = `<span class="terminal-status terminal-status-${statusClass}">${status}</span>
                      <span class="terminal-duration">${duration}ms</span>`;
    }

    logLine.innerHTML = `
        ${hasDetails ? `<button class="terminal-expand-btn" onclick="toggleTerminalLog('${logEntry.id}')">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                <path d="M9 5l7 7-7 7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
            </svg>
        </button>` : ''}
        <span class="terminal-timestamp">[${timestamp}]</span>
        <span class="terminal-method terminal-method-${methodClass}">${logEntry.method.padEnd(6)}</span>
        ${statusInfo}
        <span class="terminal-description" data-terminal-url="${escapeHtml(logEntry.url)}" data-terminal-method="${logEntry.method}">${escapeHtml(logEntry.description)}</span>
        <span class="terminal-url">${escapeHtml(logEntry.url)}</span>
    `;

    logContainer.appendChild(logLine);

    // Details section (collapsible)
    if (hasDetails) {
        const detailsSection = document.createElement('div');
        detailsSection.className = 'terminal-details';

        let requestSection = '';
        if (logEntry.details.request) {
            const reqHeaders = logEntry.details.request.headers;
            const reqBody = logEntry.details.request.body;

            requestSection = `
                <div class="terminal-section">
                    <div class="terminal-section-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M7 11l5-5m0 0l5 5m-5-5v12" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                        请求 (Request)
                    </div>
                    ${Object.keys(reqHeaders).length > 0 ? `
                        <div class="terminal-subsection">
                            <div class="terminal-subsection-title">Headers:</div>
                            <pre class="terminal-json">${escapeHtml(JSON.stringify(reqHeaders, null, 2))}</pre>
                        </div>
                    ` : ''}
                    ${reqBody ? `
                        <div class="terminal-subsection">
                            <div class="terminal-subsection-title">Body:</div>
                            <pre class="terminal-json">${escapeHtml(JSON.stringify(reqBody, null, 2))}</pre>
                        </div>
                    ` : '<div class="terminal-no-body">无请求体</div>'}
                </div>
            `;
        }

        let responseSection = '';
        if (logEntry.details.response) {
            const resStatus = logEntry.details.response.status;
            const resStatusText = logEntry.details.response.statusText;
            const resHeaders = logEntry.details.response.headers;
            const resBody = logEntry.details.response.body;

            responseSection = `
                <div class="terminal-section">
                    <div class="terminal-section-title">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M17 13l-5 5m0 0l-5-5m5 5V6" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                        响应 (Response) - ${resStatus} ${resStatusText}
                    </div>
                    ${Object.keys(resHeaders).length > 0 ? `
                        <div class="terminal-subsection">
                            <div class="terminal-subsection-title">Headers:</div>
                            <pre class="terminal-json">${escapeHtml(JSON.stringify(resHeaders, null, 2))}</pre>
                        </div>
                    ` : ''}
                    ${resBody ? `
                        <div class="terminal-subsection">
                            <div class="terminal-subsection-title">Body:</div>
                            <pre class="terminal-json">${escapeHtml(typeof resBody === 'object' ? JSON.stringify(resBody, null, 2) : resBody)}</pre>
                        </div>
                    ` : '<div class="terminal-no-body">无响应体</div>'}
                </div>
            `;
        }

        detailsSection.innerHTML = requestSection + responseSection;
        logContainer.appendChild(detailsSection);
    }

    terminalOutput.appendChild(logContainer);

    // Auto-scroll to bottom
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// Toggle terminal log expansion
function toggleTerminalLog(logId) {
    const logEntry = document.getElementById(logId);
    if (logEntry) {
        logEntry.classList.toggle('expanded');
    }
}

function updateTerminalCount() {
    if (terminalCount) {
        terminalCount.textContent = terminalLogs.length;
    }
}

function clearTerminalLog() {
    if (!confirm(safeT('api.terminal.confirm_clear'))) return;

    terminalLogs.length = 0;

    if (terminalOutput) {
        terminalOutput.innerHTML = `
            <div class="terminal-line terminal-welcome">
                <span class="terminal-prompt">$</span>
                <span class="terminal-text">${safeT('api.terminal.welcome')}</span>
            </div>
        `;
    }

    updateTerminalCount();
    showToast(safeT('api.terminal.logs_cleared'), 'success');
}

// Toggle API Notifications
function toggleApiNotifications() {
    emailsState.apiNotificationsEnabled = !emailsState.apiNotificationsEnabled;

    const toggleText = document.getElementById('apiNotifyToggleText');

    if (emailsState.apiNotificationsEnabled) {
        apiNotifyToggleBtn.classList.add('active');
        if (toggleText) {
            toggleText.textContent = safeT('api.notifications.popup_toggle', {status: safeT('api.notifications.on')});
        }
        showToast(safeT('messages.api_notifications_enabled'), 'success');
        // Save preference to cookie
        setCookie('apiNotificationsEnabled', 'true', 365);
    } else {
        apiNotifyToggleBtn.classList.remove('active');
        if (toggleText) {
            toggleText.textContent = safeT('api.notifications.popup_toggle', {status: safeT('api.notifications.off')});
        }
        // Close all existing notifications
        apiNotifications.forEach(notification => {
            closeApiNotification(notification);
        });
        showToast(safeT('messages.api_notifications_disabled'), 'info');
        // Save preference to cookie
        setCookie('apiNotificationsEnabled', 'false', 365);
    }
}

// Initialize Auto Refresh on Page Load
function initAutoRefresh() {
    const autoRefreshText = document.getElementById('autoRefreshText');

    // Read preference from cookie (default: true)
    const savedPref = getCookie('autoRefreshEnabled');
    const shouldEnable = savedPref !== 'false'; // Enable if not explicitly disabled

    if (shouldEnable) {
        // Start auto-refresh (every 10 seconds)
        emailsState.autoRefreshInterval = setInterval(refreshAllEmails, 10000);

        // Set button to active state
        if (autoRefreshBtn) {
            autoRefreshBtn.classList.add('active');
        }

        // Update text
        if (autoRefreshText) {
            autoRefreshText.textContent = safeT('api.auto_refresh.toggle', {status: safeT('api.auto_refresh.on')});
        }
    } else {
        // Keep auto-refresh disabled
        emailsState.autoRefreshInterval = null;

        // Set button to inactive state
        if (autoRefreshBtn) {
            autoRefreshBtn.classList.remove('active');
        }

        // Update text
        if (autoRefreshText) {
            autoRefreshText.textContent = safeT('api.auto_refresh.toggle', {status: safeT('api.auto_refresh.off')});
        }
    }
}

// Initialize API Notifications State on Page Load
function initApiNotifications() {
    const toggleText = document.getElementById('apiNotifyToggleText');

    // Read preference from cookie (default: false)
    const savedPref = getCookie('apiNotificationsEnabled');
    const shouldEnable = savedPref === 'true'; // Enable only if explicitly enabled

    emailsState.apiNotificationsEnabled = shouldEnable;

    if (shouldEnable) {
        // Set button to active state
        if (apiNotifyToggleBtn) {
            apiNotifyToggleBtn.classList.add('active');
        }

        // Update text
        if (toggleText) {
            toggleText.textContent = safeT('api.notifications.popup_toggle', {status: safeT('api.notifications.on')});
        }
    } else {
        // Set button to inactive state
        if (apiNotifyToggleBtn) {
            apiNotifyToggleBtn.classList.remove('active');
        }

        // Update text
        if (toggleText) {
            toggleText.textContent = safeT('api.notifications.popup_toggle', {status: safeT('api.notifications.off')});
        }
    }
}

// Initialize
console.log('Temporary Email Service - Multi-Email Support Ready!');
console.log('API Documentation: ' + API_BASE + '/docs');

// Close Codes Inline (for manual hide)
function closeCodesInline(mailId) {
    const codesContainer = document.getElementById(`codes-${mailId}`);
    if (codesContainer) {
        codesContainer.style.display = 'none';
    }

    // Update cache to remember the closed state
    if (emailsState.mailDetailsCache[mailId]) {
        emailsState.mailDetailsCache[mailId].codesExpanded = false;
    }
}

// Initialize app after i18n is loaded
function initializeApp() {
    console.log('[App] Initializing after i18n loaded');

    // Update any existing API notifications that were created before i18n loaded
    updateExistingApiNotifications();

    // Load available domains
    loadAvailableDomains();

    // Initialize UI
    renderEmailList();
    updateStats();
    updateTerminalCount();

    // Enable auto-refresh by default
    initAutoRefresh();

    // Initialize API notifications
    initApiNotifications();

    // Initialize custom prefix toggle
    initCustomPrefixToggle();
}

// Update existing API notifications with proper translations
function updateExistingApiNotifications() {
    // Update API notification popups
    document.querySelectorAll('.api-notification-title').forEach(titleElement => {
        const currentText = titleElement.textContent;
        // If showing a translation key, update it
        if (currentText && currentText.startsWith('api.')) {
            const url = titleElement.getAttribute('data-api-description');
            if (url) {
                // Extract method from parent notification
                const notification = titleElement.closest('.api-notification');
                if (notification) {
                    const methodElement = notification.querySelector('.api-notification-method');
                    if (methodElement) {
                        const method = methodElement.textContent.trim();
                        const newDescription = getApiDescription(url, method);
                        if (newDescription !== currentText) {
                            titleElement.textContent = newDescription;
                        }
                    }
                }
            }
        }
    });

    // Update terminal log descriptions
    document.querySelectorAll('.terminal-description').forEach(descElement => {
        const currentText = descElement.textContent;
        // If showing a translation key, update it
        if (currentText && currentText.startsWith('api.')) {
            const url = descElement.getAttribute('data-terminal-url');
            const method = descElement.getAttribute('data-terminal-method');
            if (url && method) {
                const newDescription = getApiDescription(url, method);
                if (newDescription !== currentText) {
                    descElement.textContent = newDescription;
                }
            }
        }
    });
}

// Wait for i18n to load before initializing
if (window.isI18nLoaded && window.isI18nLoaded()) {
    // i18n already loaded
    initializeApp();
} else {
    // Wait for i18n to load
    window.addEventListener('i18n:loaded', initializeApp, { once: true });

    // Fallback: initialize after 2 seconds if i18n event doesn't fire
    setTimeout(() => {
        if (!window.isI18nLoaded || !window.isI18nLoaded()) {
            console.warn('[App] i18n not loaded after 2s, initializing anyway');
            initializeApp();
        }
    }, 2000);
}

// ===== Welcome Message =====
// Check and display welcome message for first-time visitors (global, server-side controlled)

async function checkWelcomeMessage() {
    try {
        const response = await fetch('/api/welcome-message/status');
        const data = await response.json();

        if (data.success && !data.data.dismissed) {
            // Wait for i18n to be loaded before showing
            if (window.isI18nLoaded && window.isI18nLoaded()) {
                showWelcomeMessage();
            } else {
                window.addEventListener('i18n:loaded', showWelcomeMessage, { once: true });
            }
        }
    } catch (error) {
        console.error('[Welcome] Failed to check welcome message status:', error);
    }
}

function showWelcomeMessage() {
    const modal = document.getElementById('welcomeModal');
    if (!modal) return;

    // Update i18n content (in case it wasn't updated during page load)
    if (window.updateDOM) {
        window.updateDOM();
    }

    // Show modal
    modal.style.display = 'flex';

    // Add dismiss handler
    const dismissBtn = document.getElementById('welcomeDismissBtn');
    if (dismissBtn) {
        dismissBtn.addEventListener('click', dismissWelcomeMessage, { once: true });
    }
}

async function dismissWelcomeMessage() {
    try {
        const response = await fetch('/api/welcome-message/dismiss', { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            // Hide modal
            const modal = document.getElementById('welcomeModal');
            if (modal) {
                modal.style.display = 'none';
            }
            console.log('[Welcome] Message dismissed successfully');
        }
    } catch (error) {
        console.error('[Welcome] Failed to dismiss welcome message:', error);
        // Still hide the modal even if API call fails
        const modal = document.getElementById('welcomeModal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
}

// Check welcome message on page load
checkWelcomeMessage();

// ===== Custom Prefix Mode Select =====
// Initialize custom prefix mode select functionality

function initCustomPrefixToggle() {
    const modeSelect = document.getElementById('prefixModeSelect');
    const inputWrapper = document.getElementById('customPrefixInputWrapper');
    const prefixInput = document.getElementById('emailPrefix');

    if (!modeSelect || !inputWrapper || !prefixInput) {
        console.warn('[Custom Prefix] Mode select elements not found');
        return;
    }

    // Note: Event listener is already added above in the main initialization
    // This function just ensures the initial state is correct

    // Initialize as hidden (random mode is selected by default)
    inputWrapper.style.display = 'none';

    console.log('[Custom Prefix] Mode select initialized');
}
