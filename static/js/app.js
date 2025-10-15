// ===== Temporary Email Service Frontend - Multi-Email Support =====

// State Management
const emailsState = {
    emails: [], // Array of email objects with {token, email, expiresAt, mails: [], mailCount: 0, isExpanded: true}
    autoRefreshInterval: null,
    expiresIntervals: {}, // Map of token to interval ID
    apiNotificationsEnabled: true, // Control API popup notifications
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
const emailList = document.getElementById('emailList');
const emailCount = document.getElementById('emailCount');
const refreshAllBtn = document.getElementById('refreshAllBtn');
const autoRefreshBtn = document.getElementById('autoRefreshBtn');
const mailModal = document.getElementById('mailModal');
const closeModal = document.getElementById('closeModal');

// Stats Elements
const statEmailCount = document.getElementById('statEmailCount');
const statTotalMails = document.getElementById('statTotalMails');
const statReadMails = document.getElementById('statReadMails');

// Terminal Elements
const terminalOutput = document.getElementById('terminalOutput');
const terminalCount = document.getElementById('terminalCount');
const clearTerminalBtn = document.getElementById('clearTerminalBtn');
const apiNotifyToggleBtn = document.getElementById('apiNotifyToggleBtn');

// Event Listeners
generateBtn.addEventListener('click', generateEmail);
if (refreshAllBtn) refreshAllBtn.addEventListener('click', refreshAllEmails);
if (autoRefreshBtn) autoRefreshBtn.addEventListener('click', toggleAutoRefresh);
if (clearTerminalBtn) clearTerminalBtn.addEventListener('click', clearTerminalLog);
if (apiNotifyToggleBtn) apiNotifyToggleBtn.addEventListener('click', toggleApiNotifications);
closeModal.addEventListener('click', () => mailModal.style.display = 'none');
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
        return '生成临时邮箱';
    }

    if (method === 'GET' && path.match(/\/api\/email\/[^/]+\/mails\/[^/]+$/)) {
        return '查看邮件详情';
    }

    if (method === 'GET' && path.match(/\/api\/email\/[^/]+\/mails/)) {
        return '获取邮件列表';
    }

    if (method === 'GET' && path.match(/\/api\/email\/[^/]+\/codes/)) {
        return '提取验证码';
    }

    // Default fallback
    return 'API 调用';
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

    // Get API description
    const apiDescription = getApiDescription(url, method);

    notification.innerHTML = `
        <div class="api-notification-content">
            <div class="api-notification-header">
                <div class="api-notification-left">
                    <span class="api-notification-method ${methodClass}">${method}</span>
                    <span class="api-notification-title">${escapeHtml(apiDescription)}</span>
                </div>
                <div class="api-notification-actions">
                    <button class="api-action-btn api-copy-btn" title="复制 URL">
                        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor">
                            <path d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                        </svg>
                    </button>
                    <button class="api-action-btn api-close-btn" title="关闭">
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
            showToast('复制失败', 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast('复制失败', 'error');
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
    miniToast.textContent = '已复制!';
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
            domainSelect.innerHTML = '<option value="">🎲 随机域名（推荐）</option>';

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
    generateBtnText.textContent = '生成中';

    try {
        // Get selected domain (empty string means random)
        const selectedDomain = domainSelect.value;

        // Build URL with optional domain parameter
        let url = `${API_BASE}/api/email/generate`;
        if (selectedDomain) {
            url += `?domain=${encodeURIComponent(selectedDomain)}`;
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

            // Show success message with domain info
            if (selectedDomain) {
                showToast(`成功生成邮箱：${emailData.email.split('@')[0]}@${selectedDomain}`, 'success');
            }

            // API call is already shown in notification box
        } else {
            showToast('生成失败: ' + data.error, 'error');
        }
    } catch (error) {
        showToast('网络错误: ' + error.message, 'error');
    } finally {
        setLoading(generateBtn, false);
        generateBtnText.textContent = '立即生成新邮箱';
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
                <h3>尚未创建邮箱</h3>
                <p>点击上方按钮生成您的第一个临时邮箱地址</p>
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
                <h3>还没有邮件</h3>
                <p>等待新邮件到达...</p>
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

    try {
        const response = await fetch(`${API_BASE}/api/email/${token}/mails?limit=50`);
        const data = await response.json();

        if (response.ok && data.success) {
            // Clear error status if previously set
            emailData.status = 'active';

            // Deduplicate mails
            const existingIds = new Set(emailData.mails.map(m => m.id));
            const newMails = data.data.mails.filter(m => !existingIds.has(m.id));

            emailData.mails = [...emailData.mails, ...newMails];
            emailData.mailCount = data.data.total;

            // Update the specific email card's mail list
            const mailListContainer = document.getElementById(`mail-list-${token}`);
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
            // Handle "邮箱未找到" (Email not found) error
            emailData.status = 'not_found';

            // Show alert to user
            alert(`错误：${data.detail}\n\n邮箱 ${emailData.email} 在服务器上未找到。\n可能原因：\n- 邮箱已过期\n- Token 已失效\n- 后端存储已清空`);

            // Re-render the card to show error status
            renderEmailList();
        }
    } catch (error) {
        console.error('Failed to fetch mails:', error);

        // Mark email as error state
        emailData.status = 'error';
        renderEmailList();
    }
}

// Refresh All Emails
async function refreshAllEmails() {
    setLoading(refreshAllBtn, true);

    const promises = emailsState.emails.map(emailData =>
        fetchMailsForEmail(emailData.token)
    );

    await Promise.all(promises);

    setLoading(refreshAllBtn, false);
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
            showToast('邮箱已复制到剪贴板!', 'success');
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
            showToast('邮箱已复制到剪贴板!', 'success');
        } else {
            showToast('复制失败，请手动复制', 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast('复制失败，请手动复制', 'error');
    } finally {
        document.body.removeChild(textArea);
    }
}

// Delete Email
function deleteEmail(token) {
    if (!confirm('确定要删除这个邮箱吗？')) return;

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

    showToast('邮箱已删除', 'success');
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

    // 检查缓存
    if (emailsState.mailDetailsCache[mailId]) {
        const cached = emailsState.mailDetailsCache[mailId];
        console.log('[showMailDetail] Using cached data:', cached);

        // 使用缓存的完整数据
        document.getElementById('modalSubject').textContent = cached.subject || '（无主题）';
        document.getElementById('modalFrom').textContent = cached.from || '未知发件人';
        document.getElementById('modalDate').textContent = formatFullTime(cached.receivedAt) || '时间未知';

        // 渲染文本内容 (纯文本)
        document.getElementById('modalContent').textContent = cached.content || '（邮件内容为空）';

        // 渲染 HTML 内容
        const htmlContentDiv = document.getElementById('modalContentHtml');
        if (cached.htmlContent) {
            htmlContentDiv.innerHTML = cached.htmlContent; // 后端已清理过，安全渲染
        } else {
            // 如果没有 HTML 内容，显示纯文本
            htmlContentDiv.innerHTML = `<pre style="white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(cached.content || '（邮件内容为空）')}</pre>`;
        }

        // 默认显示 HTML 模式
        currentViewMode = 'html';
        htmlContentDiv.style.display = 'block';
        document.getElementById('modalContent').style.display = 'none';
        const viewModeText = document.getElementById('viewModeText');
        if (viewModeText) viewModeText.textContent = 'HTML';

        // Check if codes already extracted
        if (cached.codes !== null && cached.codes !== undefined) {
            // Hide button and show codes
            if (extractBtn) extractBtn.style.display = 'none';
            displayCodesInModal(cached.codes);
        } else {
            // Show extract button
            codesSection.style.display = 'block';
        }
        return;
    }

    // 从 API 获取完整邮件数据
    try {
        const response = await fetch(`${API_BASE}/api/email/${token}/mails/${mailId}`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        console.log('[showMailDetail] API response:', data);

        if (data.success && data.data) {
            const mail = data.data;
            console.log('[showMailDetail] Mail data fields:', {
                hasSubject: !!mail.subject,
                hasFrom: !!mail.from,
                hasContent: !!mail.content,
                hasReceivedAt: !!mail.receivedAt,
                subject: mail.subject,
                from: mail.from,
                contentLength: mail.content ? mail.content.length : 0,
                receivedAt: mail.receivedAt
            });

            // 存储到缓存
            emailsState.mailDetailsCache[mailId] = {
                subject: mail.subject,
                from: mail.from,
                content: mail.content,
                htmlContent: mail.htmlContent, // 新增：储存清理后的 HTML
                receivedAt: mail.receivedAt,
                codes: null // Will be populated by manual extraction
            };

            // 更新显示 - 使用更安全的默认值处理
            document.getElementById('modalSubject').textContent =
                (mail.subject !== undefined && mail.subject !== null && mail.subject !== '')
                ? mail.subject
                : '（无主题）';

            document.getElementById('modalFrom').textContent =
                (mail.from !== undefined && mail.from !== null && mail.from !== '')
                ? mail.from
                : '未知发件人';

            document.getElementById('modalDate').textContent =
                mail.receivedAt
                ? formatFullTime(mail.receivedAt)
                : '时间未知';

            // 渲染文本内容 (纯文本)
            document.getElementById('modalContent').textContent =
                (mail.content !== undefined && mail.content !== null && mail.content !== '')
                ? mail.content
                : '（邮件内容为空）';

            // 渲染 HTML 内容
            const htmlContentDiv = document.getElementById('modalContentHtml');
            if (mail.htmlContent) {
                htmlContentDiv.innerHTML = mail.htmlContent; // 后端已清理过，安全渲染
            } else {
                // 如果没有 HTML 内容，显示纯文本
                htmlContentDiv.innerHTML = `<pre style="white-space: pre-wrap; word-wrap: break-word;">${escapeHtml(mail.content || '（邮件内容为空）')}</pre>`;
            }

            // 默认显示 HTML 模式
            currentViewMode = 'html';
            htmlContentDiv.style.display = 'block';
            document.getElementById('modalContent').style.display = 'none';
            const viewModeText = document.getElementById('viewModeText');
            if (viewModeText) viewModeText.textContent = 'HTML';

            // Show extract button
            codesSection.style.display = 'block';
        } else {
            throw new Error('Invalid API response format');
        }
    } catch (error) {
        console.error('[showMailDetail] Failed to fetch mail details:', error);

        // 显示错误信息
        document.getElementById('modalSubject').textContent = '载入失败';
        document.getElementById('modalFrom').textContent = '无法载入发件人';
        document.getElementById('modalDate').textContent = '无法载入时间';
        document.getElementById('modalContent').textContent = `载入邮件内容时发生错误：${error.message}`;

        // 显示错误提示
        showToast('载入邮件详情失败，请重试', 'error');
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
        showToast('提取验证码失败，请重试', 'error');

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
            showToast('复制失败，请重试', 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast('复制失败，请重试', 'error');
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
            showToast('复制失败，请重试', 'error');
        }
    } catch (err) {
        console.error('Fallback copy failed:', err);
        showToast('复制失败，请重试', 'error');
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
            autoRefreshText.textContent = '自动刷新: 关闭';
        }
        // Save preference to cookie
        setCookie('autoRefreshEnabled', 'false', 365);
    } else {
        emailsState.autoRefreshInterval = setInterval(refreshAllEmails, 10000); // 每10秒
        autoRefreshBtn.classList.add('active');
        if (autoRefreshText) {
            autoRefreshText.textContent = '自动刷新: 开启';
        }
        showToast('已开启自动刷新 (每10秒)', 'success');
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
    statReadMails.textContent = 0; // Placeholder - would need read tracking
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

    if (diff < 60) return '刚刚';
    if (diff < 3600) return Math.floor(diff / 60) + '分钟前';
    if (diff < 86400) return Math.floor(diff / 3600) + '小时前';

    return date.toLocaleDateString('zh-CN', {
        month: 'short',
        day: 'numeric',
        hour: '2-digit',
        minute: '2-digit'
    });
}

function formatFullTime(isoString) {
    // 验证输入
    if (!isoString) {
        console.warn('[formatFullTime] Invalid input:', isoString);
        return '时间未知';
    }

    const date = new Date(isoString);

    // 检查日期是否有效
    if (isNaN(date.getTime())) {
        console.warn('[formatFullTime] Invalid date:', isoString);
        return '时间格式错误';
    }

    return date.toLocaleString('zh-CN', {
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
        <span class="terminal-description">${escapeHtml(logEntry.description)}</span>
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
    if (!confirm('确定要清空所有 API 日志吗？')) return;

    terminalLogs.length = 0;

    if (terminalOutput) {
        terminalOutput.innerHTML = `
            <div class="terminal-line terminal-welcome">
                <span class="terminal-prompt">$</span>
                <span class="terminal-text">API 调用监控已启动...</span>
            </div>
        `;
    }

    updateTerminalCount();
    showToast('API 日志已清空', 'success');
}

// Toggle API Notifications
function toggleApiNotifications() {
    emailsState.apiNotificationsEnabled = !emailsState.apiNotificationsEnabled;

    const toggleText = document.getElementById('apiNotifyToggleText');

    if (emailsState.apiNotificationsEnabled) {
        apiNotifyToggleBtn.classList.add('active');
        if (toggleText) {
            toggleText.textContent = '弹窗通知: 开启';
        }
        showToast('API 弹窗通知已开启', 'success');
        // Save preference to cookie
        setCookie('apiNotificationsEnabled', 'true', 365);
    } else {
        apiNotifyToggleBtn.classList.remove('active');
        if (toggleText) {
            toggleText.textContent = '弹窗通知: 关闭';
        }
        // Close all existing notifications
        apiNotifications.forEach(notification => {
            closeApiNotification(notification);
        });
        showToast('API 弹窗通知已关闭', 'info');
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
            autoRefreshText.textContent = '自动刷新: 开启';
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
            autoRefreshText.textContent = '自动刷新: 关闭';
        }
    }
}

// Initialize API Notifications State on Page Load
function initApiNotifications() {
    const toggleText = document.getElementById('apiNotifyToggleText');

    // Read preference from cookie (default: true)
    const savedPref = getCookie('apiNotificationsEnabled');
    const shouldEnable = savedPref !== 'false'; // Enable if not explicitly disabled

    emailsState.apiNotificationsEnabled = shouldEnable;

    if (shouldEnable) {
        // Set button to active state
        if (apiNotifyToggleBtn) {
            apiNotifyToggleBtn.classList.add('active');
        }

        // Update text
        if (toggleText) {
            toggleText.textContent = '弹窗通知: 开启';
        }
    } else {
        // Set button to inactive state
        if (apiNotifyToggleBtn) {
            apiNotifyToggleBtn.classList.remove('active');
        }

        // Update text
        if (toggleText) {
            toggleText.textContent = '弹窗通知: 关闭';
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
