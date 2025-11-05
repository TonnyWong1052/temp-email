// ===== i18n (Internationalization) Module =====
// Handles translation loading, DOM updates, and language switching

// Global i18n state
window.i18n = {
    currentLanguage: 'en-US',
    translations: {},
    availableLanguages: {
        'en-US': 'English',
        'zh-CN': '简体中文'
    },
    isLoaded: false
};

/**
 * Initialize i18n system
 * Loads translations from API and updates DOM
 */
async function initI18n() {
    try {
        // Detect current language from HTML lang attribute or cookie
        const htmlLang = document.documentElement.lang || 'en-US';
        const cookieLang = getCookie('tempmail_lang');

        window.i18n.currentLanguage = cookieLang || htmlLang || 'en-US';

        // Load translations from API
        await loadTranslations();

        // Update all DOM elements with translations
        updateDOM();

        window.i18n.isLoaded = true;
        console.log(`[i18n] Initialized with language: ${window.i18n.currentLanguage}`);

        // Dispatch custom event for other scripts
        window.dispatchEvent(new CustomEvent('i18n:loaded', {
            detail: { language: window.i18n.currentLanguage }
        }));
    } catch (error) {
        console.error('[i18n] Initialization failed:', error);
        // Fallback: keep default language
        window.i18n.isLoaded = true;
    }
}

/**
 * Load translations from API
 */
async function loadTranslations() {
    try {
        // Send current language to API
        const url = `/api/i18n/translations?lang=${encodeURIComponent(window.i18n.currentLanguage)}`;
        const response = await fetch(url);
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();

        if (data.success && data.data) {
            window.i18n.currentLanguage = data.data.language;
            window.i18n.translations = data.data.translations;
            window.i18n.availableLanguages = data.data.availableLanguages;

            // Update HTML lang attribute
            document.documentElement.lang = window.i18n.currentLanguage;
        } else {
            throw new Error('Invalid API response');
        }
    } catch (error) {
        console.error('[i18n] Failed to load translations:', error);
        // Use empty translations as fallback
        window.i18n.translations = {};
    }
}

/**
 * Get translation for a key
 * @param {string} key - Translation key (e.g., 'common.buttons.generate')
 * @param {object} params - Optional parameters for string interpolation
 * @returns {string} Translated string
 */
function t(key, params = {}) {
    if (!key) return '';

    // Get translation from loaded translations
    let translation = window.i18n.translations[key];

    // Fallback to key if translation not found
    if (!translation) {
        console.warn(`[i18n] Translation not found for key: ${key}`);
        return key;
    }

    // Replace parameters in translation
    // Supports {param} syntax
    if (params && typeof params === 'object') {
        Object.keys(params).forEach(param => {
            const placeholder = `{${param}}`;
            translation = translation.replace(new RegExp(placeholder, 'g'), params[param]);
        });
    }

    return translation;
}

/**
 * Update all DOM elements with data-i18n attributes
 */
function updateDOM() {
    // Update text content elements
    document.querySelectorAll('[data-i18n]').forEach(element => {
        const key = element.getAttribute('data-i18n');

        // Get params from data-i18n-params attribute (JSON format)
        let params = {};
        const paramsAttr = element.getAttribute('data-i18n-params');
        if (paramsAttr) {
            try {
                params = JSON.parse(paramsAttr);
            } catch (e) {
                console.warn('[i18n] Invalid params JSON:', paramsAttr);
            }
        }

        // Get translated text
        const translatedText = t(key, params);

        // Check if translation contains HTML tags
        const containsHTML = /<[^>]+>/.test(translatedText);

        // Update element text content
        if (containsHTML) {
            // Translation contains HTML - use innerHTML
            element.innerHTML = translatedText;
        } else if (element.childNodes.length === 1 && element.childNodes[0].nodeType === 3) {
            // Simple text node - replace directly
            element.textContent = translatedText;
        } else {
            // Has child elements - replace only text nodes
            updateTextNodes(element, translatedText);
        }
    });

    // Update placeholder attributes
    document.querySelectorAll('[data-i18n-placeholder]').forEach(element => {
        const key = element.getAttribute('data-i18n-placeholder');
        const translatedText = t(key);
        element.setAttribute('placeholder', translatedText);
    });

    // Update title attributes (tooltips)
    document.querySelectorAll('[data-i18n-title]').forEach(element => {
        const key = element.getAttribute('data-i18n-title');
        const translatedText = t(key);
        element.setAttribute('title', translatedText);
    });

    // Update meta tags
    document.querySelectorAll('meta[data-i18n]').forEach(meta => {
        const key = meta.getAttribute('data-i18n');
        const translatedText = t(key);
        meta.setAttribute('content', translatedText);
    });

    // Update title tag
    const titleElement = document.querySelector('title[data-i18n]');
    if (titleElement) {
        const key = titleElement.getAttribute('data-i18n');
        titleElement.textContent = t(key);
    }
}

/**
 * Update text nodes within an element while preserving child elements
 * @param {HTMLElement} element - Element to update
 * @param {string} newText - New text content
 */
function updateTextNodes(element, newText) {
    // Find direct text nodes and replace the first one
    let textNodeFound = false;

    element.childNodes.forEach(node => {
        if (node.nodeType === 3 && !textNodeFound && node.textContent.trim()) {
            // First text node with content
            node.textContent = newText;
            textNodeFound = true;
        }
    });

    // If no text node found, append as text
    if (!textNodeFound) {
        const textNode = document.createTextNode(newText);
        element.insertBefore(textNode, element.firstChild);
    }
}

/**
 * Switch to a different language
 * @param {string} languageCode - Target language code
 */
async function switchLanguage(languageCode) {
    if (!window.i18n.availableLanguages[languageCode]) {
        console.error(`[i18n] Unsupported language: ${languageCode}`);
        return;
    }

    // Save to cookie
    setCookie('tempmail_lang', languageCode, 365);

    // Redirect to language-specific URL
    const currentPath = window.location.pathname;
    const currentQuery = window.location.search;

    // Special handling for admin paths - don't use language prefix
    if (currentPath.startsWith('/admin')) {
        // Just reload the page with new language cookie
        window.location.reload();
        return;
    }

    // Build new URL based on language
    let newPath = currentPath;

    // Remove existing language prefix
    newPath = newPath.replace(/^\/(en|zh-cn)\/?/, '/');

    // Add new language prefix (except for default language en-US)
    if (languageCode === 'zh-CN') {
        newPath = '/zh-cn' + newPath;
    }

    // Redirect
    window.location.href = newPath + currentQuery;
}

/**
 * Get cookie value
 * @param {string} name - Cookie name
 * @returns {string|null} Cookie value
 */
function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) {
        return parts.pop().split(';').shift();
    }
    return null;
}

/**
 * Set cookie
 * @param {string} name - Cookie name
 * @param {string} value - Cookie value
 * @param {number} days - Expiration in days
 */
function setCookie(name, value, days) {
    const date = new Date();
    date.setTime(date.getTime() + (days * 24 * 60 * 60 * 1000));
    const expires = `expires=${date.toUTCString()}`;
    document.cookie = `${name}=${value};${expires};path=/`;
}

/**
 * Get current language code
 * @returns {string} Current language code
 */
function getCurrentLanguage() {
    return window.i18n.currentLanguage;
}

/**
 * Check if i18n is loaded
 * @returns {boolean} True if loaded
 */
function isI18nLoaded() {
    return window.i18n.isLoaded;
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initI18n);
} else {
    // DOM already loaded
    initI18n();
}

// Export functions to global scope
window.t = t;
window.switchLanguage = switchLanguage;
window.getCurrentLanguage = getCurrentLanguage;
window.isI18nLoaded = isI18nLoaded;
window.updateDOM = updateDOM;
