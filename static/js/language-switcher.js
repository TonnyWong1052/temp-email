// ===== Language Switcher Component =====
// Creates a language switcher UI component in the navigation bar

// Language switcher state
const languageSwitcher = {
    isInitialized: false,
    currentLanguage: 'en-US',
    availableLanguages: {
        'en-US': {
            name: 'English',
            flag: '🇺🇸',
            nativeName: 'English'
        },
        'zh-CN': {
            name: '简体中文',
            flag: '🇨🇳',
            nativeName: '简体中文'
        }
    }
};

/**
 * Initialize language switcher
 * Creates and inserts the language switcher UI into the navigation bar
 */
function initLanguageSwitcher() {
    if (languageSwitcher.isInitialized) {
        return;
    }

    // Wait for i18n to load first
    if (!window.isI18nLoaded || !window.isI18nLoaded()) {
        // Retry after i18n is loaded
        window.addEventListener('i18n:loaded', () => {
            initLanguageSwitcher();
        }, { once: true });
        return;
    }

    // Get current language from i18n system
    languageSwitcher.currentLanguage = window.getCurrentLanguage ? window.getCurrentLanguage() : 'en-US';

    // Create language switcher UI
    createLanguageSwitcherUI();

    // Mark as initialized
    languageSwitcher.isInitialized = true;

    console.log('[Language Switcher] Initialized');
}

/**
 * Create language switcher UI component
 */
function createLanguageSwitcherUI() {
    // Find nav-links container
    const navLinks = document.querySelector('.nav-links');
    if (!navLinks) {
        console.warn('[Language Switcher] Nav links container not found');
        return;
    }

    // Create language switcher HTML
    const currentLang = languageSwitcher.availableLanguages[languageSwitcher.currentLanguage];
    const otherLangs = Object.keys(languageSwitcher.availableLanguages)
        .filter(code => code !== languageSwitcher.currentLanguage);

    const switcherHTML = `
        <div class="language-switcher">
            <button class="lang-btn" id="langSwitcherBtn" aria-label="Switch language" aria-haspopup="true" aria-expanded="false">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="lang-icon">
                    <path d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                </svg>
                <span class="lang-name">${currentLang.flag} ${currentLang.nativeName}</span>
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" class="lang-chevron">
                    <path d="M19 9l-7 7-7-7" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/>
                </svg>
            </button>
            <div class="lang-dropdown" id="langDropdown" role="menu" aria-hidden="true">
                ${otherLangs.map(code => {
                    const lang = languageSwitcher.availableLanguages[code];
                    return `
                        <a href="#" class="lang-option" data-lang="${code}" role="menuitem">
                            <span class="lang-flag">${lang.flag}</span>
                            <span class="lang-text">${lang.nativeName}</span>
                        </a>
                    `;
                }).join('')}
            </div>
        </div>
    `;

    // Insert language switcher before the first nav-link
    navLinks.insertAdjacentHTML('afterbegin', switcherHTML);

    // Set up event listeners
    setupEventListeners();
}

/**
 * Set up event listeners for language switcher
 */
function setupEventListeners() {
    const langBtn = document.getElementById('langSwitcherBtn');
    const langDropdown = document.getElementById('langDropdown');

    if (!langBtn || !langDropdown) {
        return;
    }

    // Toggle dropdown on button click
    langBtn.addEventListener('click', (e) => {
        e.preventDefault();
        e.stopPropagation();
        toggleDropdown();
    });

    // Close dropdown when clicking outside
    document.addEventListener('click', (e) => {
        if (!e.target.closest('.language-switcher')) {
            closeDropdown();
        }
    });

    // Handle language option clicks
    document.querySelectorAll('.lang-option').forEach(option => {
        option.addEventListener('click', (e) => {
            e.preventDefault();
            const targetLang = option.getAttribute('data-lang');
            switchToLanguage(targetLang);
        });
    });

    // Keyboard navigation
    langBtn.addEventListener('keydown', (e) => {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            toggleDropdown();
        } else if (e.key === 'Escape') {
            closeDropdown();
        }
    });
}

/**
 * Toggle dropdown visibility
 */
function toggleDropdown() {
    const langBtn = document.getElementById('langSwitcherBtn');
    const langDropdown = document.getElementById('langDropdown');

    if (!langBtn || !langDropdown) {
        return;
    }

    const isOpen = langDropdown.classList.contains('show');

    if (isOpen) {
        closeDropdown();
    } else {
        openDropdown();
    }
}

/**
 * Open dropdown
 */
function openDropdown() {
    const langBtn = document.getElementById('langSwitcherBtn');
    const langDropdown = document.getElementById('langDropdown');

    if (!langBtn || !langDropdown) {
        return;
    }

    langDropdown.classList.add('show');
    langBtn.setAttribute('aria-expanded', 'true');
    langDropdown.setAttribute('aria-hidden', 'false');
}

/**
 * Close dropdown
 */
function closeDropdown() {
    const langBtn = document.getElementById('langSwitcherBtn');
    const langDropdown = document.getElementById('langDropdown');

    if (!langBtn || !langDropdown) {
        return;
    }

    langDropdown.classList.remove('show');
    langBtn.setAttribute('aria-expanded', 'false');
    langDropdown.setAttribute('aria-hidden', 'true');
}

/**
 * Switch to a different language
 * @param {string} languageCode - Target language code
 */
function switchToLanguage(languageCode) {
    if (!languageSwitcher.availableLanguages[languageCode]) {
        console.error(`[Language Switcher] Invalid language: ${languageCode}`);
        return;
    }

    // Close dropdown
    closeDropdown();

    // Use global switchLanguage function from i18n.js
    if (window.switchLanguage) {
        window.switchLanguage(languageCode);
    } else {
        console.error('[Language Switcher] switchLanguage function not found');
    }
}

/**
 * Update current language display
 * @param {string} languageCode - Current language code
 */
function updateCurrentLanguageDisplay(languageCode) {
    const langBtn = document.getElementById('langSwitcherBtn');
    if (!langBtn) {
        return;
    }

    const langNameEl = langBtn.querySelector('.lang-name');
    if (!langNameEl) {
        return;
    }

    const lang = languageSwitcher.availableLanguages[languageCode];
    if (lang) {
        langNameEl.textContent = `${lang.flag} ${lang.nativeName}`;
    }
}

// Auto-initialize when DOM is ready
if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initLanguageSwitcher);
} else {
    // DOM already loaded
    initLanguageSwitcher();
}

// Export functions to global scope
window.initLanguageSwitcher = initLanguageSwitcher;
window.switchToLanguage = switchToLanguage;
