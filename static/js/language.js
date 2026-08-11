(() => {
    const STORAGE_KEY = "expense-manager-language";

    const languages = {
        en: {
            label: "English",
            short: "EN",
            locale: "en-IN"
        },

        hi: {
            label: "हिन्दी",
            short: "हि",
            locale: "hi-IN"
        },

        kn: {
            label: "ಕನ್ನಡ",
            short: "ಕ",
            locale: "kn-IN"
        }
    };


    const translations = {

        hi: {
            "Dashboard": "डैशबोर्ड",
            "Groups": "समूह",
            "Bills": "बिल",
            "Logout": "लॉग आउट",

            "Welcome": "स्वागत है",
            "Personal Finance": "व्यक्तिगत वित्त",
            "Financial Control Center": "वित्तीय नियंत्रण केंद्र",
            "Quick Actions": "त्वरित कार्य",
            "Manage your money": "अपने पैसे प्रबंधित करें",

            "+ Expense": "+ खर्च",
            "+ Income": "+ आय",
            "Split": "विभाजित करें",
            "Budgets": "बजट",
            "Goals": "लक्ष्य",
            "Subscriptions": "सब्सक्रिप्शन",
            "Reports": "रिपोर्ट",
            "Recurring": "आवर्ती",

            "Search": "खोजें",
            "Search transactions, category, source...":
                "लेन-देन, श्रेणी या स्रोत खोजें...",

            "Financial Health": "वित्तीय स्वास्थ्य",
            "Excellent": "उत्कृष्ट",
            "Good": "अच्छा",
            "Fair": "ठीक",
            "Needs attention": "ध्यान देने की आवश्यकता",

            "Savings": "बचत",
            "Budget": "बजट",
            "Subs": "सब्सक्रिप्शन",
            "Clear": "कोई बकाया नहीं",
            "Bills": "बिल",

            "Total Income": "कुल आय",
            "Total Expense": "कुल खर्च",
            "Balance": "शेष राशि",

            "Add Expense": "खर्च जोड़ें",
            "Add Income": "आय जोड़ें",

            "Amount": "राशि",
            "Category": "श्रेणी",
            "Description": "विवरण",
            "Date": "तारीख",
            "Action": "कार्रवाई",
            "Source": "स्रोत",

            "Expense History": "खर्च का इतिहास",
            "Income History": "आय का इतिहास",
            "Hide Expense History": "खर्च इतिहास छिपाएँ",
            "Show Expense History": "खर्च इतिहास दिखाएँ",
            "Download Expense Bill": "खर्च बिल डाउनलोड करें",

            "Food": "भोजन",
            "Travel": "यात्रा",
            "Shopping": "खरीदारी",
            "Entertainment": "मनोरंजन",
            "Education": "शिक्षा",
            "Rent": "किराया",
            "EMI": "ईएमआई",
            "Other": "अन्य",

            "Delete": "हटाएँ",
            "Edit": "संपादित करें",
            "Save": "सहेजें",
            "Cancel": "रद्द करें",

            "Monthly Budgets": "मासिक बजट",
            "Savings Goals": "बचत लक्ष्य",
            "Subscription Tracker": "सब्सक्रिप्शन ट्रैकर",
            "Financial Reports": "वित्तीय रिपोर्ट",
            "Recurring Transactions": "आवर्ती लेन-देन",

            "Create Schedule": "शेड्यूल बनाएँ",
            "Frequency": "आवृत्ति",
            "Monthly": "मासिक",
            "Yearly": "वार्षिक",
            "Active": "सक्रिय",
            "Paused": "रुका हुआ",
            "Pause": "रोकें",
            "Resume": "फिर शुरू करें",

            "Run Due Transactions": "देय लेन-देन चलाएँ",
            "Next Run": "अगली तारीख",

            "Dark mode": "डार्क मोड",
            "Light mode": "लाइट मोड",

            "Online": "ऑनलाइन",
            "Offline": "ऑफलाइन",
            "All synced": "सभी सिंक हो गए",
            "Checking sync": "सिंक जाँच रहा है"
        },


        kn: {
            "Dashboard": "ಡ್ಯಾಶ್‌ಬೋರ್ಡ್",
            "Groups": "ಗುಂಪುಗಳು",
            "Bills": "ಬಿಲ್‌ಗಳು",
            "Logout": "ಲಾಗ್ ಔಟ್",

            "Welcome": "ಸ್ವಾಗತ",
            "Personal Finance": "ವೈಯಕ್ತಿಕ ಹಣಕಾಸು",
            "Financial Control Center": "ಹಣಕಾಸು ನಿಯಂತ್ರಣ ಕೇಂದ್ರ",
            "Quick Actions": "ತ್ವರಿತ ಕಾರ್ಯಗಳು",
            "Manage your money": "ನಿಮ್ಮ ಹಣವನ್ನು ನಿರ್ವಹಿಸಿ",

            "+ Expense": "+ ಖರ್ಚು",
            "+ Income": "+ ಆದಾಯ",
            "Split": "ವಿಭಜಿಸಿ",
            "Budgets": "ಬಜೆಟ್‌ಗಳು",
            "Goals": "ಗುರಿಗಳು",
            "Subscriptions": "ಚಂದಾದಾರಿಕೆಗಳು",
            "Reports": "ವರದಿಗಳು",
            "Recurring": "ಮರುಕಳಿಸುವ",

            "Search": "ಹುಡುಕಿ",
            "Search transactions, category, source...":
                "ವಹಿವಾಟು, ವರ್ಗ ಅಥವಾ ಮೂಲ ಹುಡುಕಿ...",

            "Financial Health": "ಹಣಕಾಸಿನ ಆರೋಗ್ಯ",
            "Excellent": "ಅತ್ಯುತ್ತಮ",
            "Good": "ಉತ್ತಮ",
            "Fair": "ಸರಾಸರಿ",
            "Needs attention": "ಗಮನ ಅಗತ್ಯ",

            "Savings": "ಉಳಿತಾಯ",
            "Budget": "ಬಜೆಟ್",
            "Subs": "ಚಂದಾದಾರಿಕೆ",
            "Clear": "ಬಾಕಿ ಇಲ್ಲ",
            "Bills": "ಬಿಲ್‌ಗಳು",

            "Total Income": "ಒಟ್ಟು ಆದಾಯ",
            "Total Expense": "ಒಟ್ಟು ಖರ್ಚು",
            "Balance": "ಉಳಿಕೆ",

            "Add Expense": "ಖರ್ಚು ಸೇರಿಸಿ",
            "Add Income": "ಆದಾಯ ಸೇರಿಸಿ",

            "Amount": "ಮೊತ್ತ",
            "Category": "ವರ್ಗ",
            "Description": "ವಿವರಣೆ",
            "Date": "ದಿನಾಂಕ",
            "Action": "ಕ್ರಿಯೆ",
            "Source": "ಮೂಲ",

            "Expense History": "ಖರ್ಚಿನ ಇತಿಹಾಸ",
            "Income History": "ಆದಾಯ ಇತಿಹಾಸ",
            "Hide Expense History": "ಖರ್ಚಿನ ಇತಿಹಾಸ ಮರೆಮಾಡಿ",
            "Show Expense History": "ಖರ್ಚಿನ ಇತಿಹಾಸ ತೋರಿಸಿ",
            "Download Expense Bill": "ಖರ್ಚಿನ ಬಿಲ್ ಡೌನ್‌ಲೋಡ್ ಮಾಡಿ",

            "Food": "ಆಹಾರ",
            "Travel": "ಪ್ರಯಾಣ",
            "Shopping": "ಖರೀದಿ",
            "Entertainment": "ಮನರಂಜನೆ",
            "Education": "ಶಿಕ್ಷಣ",
            "Rent": "ಬಾಡಿಗೆ",
            "EMI": "ಇಎಂಐ",
            "Other": "ಇತರೆ",

            "Delete": "ಅಳಿಸಿ",
            "Edit": "ತಿದ್ದು",
            "Save": "ಉಳಿಸಿ",
            "Cancel": "ರದ್ದುಮಾಡಿ",

            "Monthly Budgets": "ಮಾಸಿಕ ಬಜೆಟ್‌ಗಳು",
            "Savings Goals": "ಉಳಿತಾಯ ಗುರಿಗಳು",
            "Subscription Tracker": "ಚಂದಾದಾರಿಕೆ ಟ್ರ್ಯಾಕರ್",
            "Financial Reports": "ಹಣಕಾಸು ವರದಿಗಳು",
            "Recurring Transactions": "ಮರುಕಳಿಸುವ ವಹಿವಾಟುಗಳು",

            "Create Schedule": "ವೇಳಾಪಟ್ಟಿ ರಚಿಸಿ",
            "Frequency": "ಆವರ್ತನೆ",
            "Monthly": "ಮಾಸಿಕ",
            "Yearly": "ವಾರ್ಷಿಕ",
            "Active": "ಸಕ್ರಿಯ",
            "Paused": "ವಿರಾಮ",
            "Pause": "ವಿರಾಮ",
            "Resume": "ಮುಂದುವರಿಸಿ",

            "Run Due Transactions": "ಬಾಕಿ ವಹಿವಾಟುಗಳನ್ನು ಚಲಾಯಿಸಿ",
            "Next Run": "ಮುಂದಿನ ದಿನಾಂಕ",

            "Dark mode": "ಡಾರ್ಕ್ ಮೋಡ್",
            "Light mode": "ಲೈಟ್ ಮೋಡ್",

            "Online": "ಆನ್‌ಲೈನ್",
            "Offline": "ಆಫ್‌ಲೈನ್",
            "All synced": "ಎಲ್ಲವೂ ಸಿಂಕ್ ಆಗಿದೆ",
            "Checking sync": "ಸಿಂಕ್ ಪರಿಶೀಲಿಸಲಾಗುತ್ತಿದೆ"
        }
    };


    const originals = new WeakMap();


    function currentLanguage() {
        const saved =
            localStorage.getItem(STORAGE_KEY);

        return languages[saved]
            ? saved
            : "en";
    }


    function translateText(text, language) {
        if (
            !text
            || language === "en"
        ) {
            return text;
        }

        const clean =
            text.trim();

        if (!clean) {
            return text;
        }

        const translated =
            translations[language]?.[clean];

        if (!translated) {
            return text;
        }

        const leading =
            text.match(/^\s*/)?.[0] || "";

        const trailing =
            text.match(/\s*$/)?.[0] || "";

        return (
            leading
            + translated
            + trailing
        );
    }


    function translateTextNode(
        node,
        language
    ) {
        if (
            !node
            || node.nodeType !== Node.TEXT_NODE
        ) {
            return;
        }

        const parent =
            node.parentElement;

        if (!parent) {
            return;
        }

        if (
            parent.closest(
                "script, style, code, pre, [data-no-i18n]"
            )
        ) {
            return;
        }

        if (!originals.has(node)) {
            originals.set(
                node,
                node.nodeValue
            );
        }

        const original =
            originals.get(node);

        node.nodeValue =
            language === "en"
                ? original
                : translateText(
                    original,
                    language
                );
    }


    function translateAttributes(
        element,
        language
    ) {
        const attributes = [
            "placeholder",
            "title",
            "aria-label"
        ];

        for (const attribute of attributes) {
            if (
                !element.hasAttribute(
                    attribute
                )
            ) {
                continue;
            }

            const originalKey =
                `i18nOriginal${attribute
                    .replace(
                        /-([a-z])/g,
                        (_, letter) =>
                            letter.toUpperCase()
                    )
                    .replace(
                        /^./,
                        char =>
                            char.toUpperCase()
                    )}`;

            if (!element.dataset[originalKey]) {
                element.dataset[originalKey] =
                    element.getAttribute(
                        attribute
                    );
            }

            const original =
                element.dataset[originalKey];

            element.setAttribute(
                attribute,
                language === "en"
                    ? original
                    : (
                        translations[
                            language
                        ]?.[original]
                        || original
                    )
            );
        }
    }


    function translatePage(language) {
        document.documentElement.lang =
            language;

        const walker =
            document.createTreeWalker(
                document.body,
                NodeFilter.SHOW_TEXT
            );

        const nodes = [];

        while (walker.nextNode()) {
            nodes.push(
                walker.currentNode
            );
        }

        nodes.forEach(
            node =>
                translateTextNode(
                    node,
                    language
                )
        );

        document
            .querySelectorAll(
                "input, textarea, button, a, select"
            )
            .forEach(
                element =>
                    translateAttributes(
                        element,
                        language
                    )
            );

        updateToday(language);
        updateSelector(language);
    }


    function updateToday(language) {
        const today =
            document.getElementById(
                "pro-today"
            );

        if (!today) {
            return;
        }

        const locale =
            languages[language]?.locale
            || "en-IN";

        today.textContent =
            new Intl.DateTimeFormat(
                locale,
                {
                    weekday: "long",
                    day: "numeric",
                    month: "long",
                    year: "numeric"
                }
            ).format(
                new Date()
            );
    }


    function updateSelector(language) {
        const current =
            document.getElementById(
                "language-current"
            );

        if (current) {
            current.textContent =
                languages[language].short;
        }

        document
            .querySelectorAll(
                ".language-option"
            )
            .forEach(
                option => {
                    option.classList.toggle(
                        "active",
                        option.dataset.language
                            === language
                    );
                }
            );
    }


    function setLanguage(language) {
        if (!languages[language]) {
            return;
        }

        localStorage.setItem(
            STORAGE_KEY,
            language
        );

        translatePage(
            language
        );

        const menu =
            document.getElementById(
                "language-menu"
            );

        menu?.classList.remove(
            "open"
        );
    }


    function createLanguageSelector() {
        if (
            document.getElementById(
                "language-switcher"
            )
        ) {
            return;
        }

        const wrapper =
            document.createElement(
                "div"
            );

        wrapper.id =
            "language-switcher";

        wrapper.className =
            "language-switcher";

        wrapper.setAttribute(
            "data-no-i18n",
            "true"
        );

        wrapper.innerHTML = `
            <div
                class="language-menu"
                id="language-menu">

                <button
                    type="button"
                    class="language-option"
                    data-language="en">
                    <span>EN</span>
                    English
                </button>

                <button
                    type="button"
                    class="language-option"
                    data-language="hi">
                    <span>हि</span>
                    हिन्दी
                </button>

                <button
                    type="button"
                    class="language-option"
                    data-language="kn">
                    <span>ಕ</span>
                    ಕನ್ನಡ
                </button>

            </div>

            <button
                type="button"
                class="language-toggle"
                id="language-toggle"
                aria-label="Change language"
                title="Change language">

                <span
                    id="language-current">
                    EN
                </span>

            </button>
        `;

        document.body.appendChild(
            wrapper
        );

        const toggle =
            document.getElementById(
                "language-toggle"
            );

        const menu =
            document.getElementById(
                "language-menu"
            );

        toggle.addEventListener(
            "click",
            event => {
                event.stopPropagation();

                menu.classList.toggle(
                    "open"
                );
            }
        );

        document
            .querySelectorAll(
                ".language-option"
            )
            .forEach(
                option => {
                    option.addEventListener(
                        "click",
                        () => {
                            setLanguage(
                                option.dataset.language
                            );
                        }
                    );
                }
            );

        document.addEventListener(
            "click",
            event => {
                if (
                    !wrapper.contains(
                        event.target
                    )
                ) {
                    menu.classList.remove(
                        "open"
                    );
                }
            }
        );
    }


    document.addEventListener(
        "DOMContentLoaded",
        () => {
            createLanguageSelector();

            translatePage(
                currentLanguage()
            );

            setTimeout(
                () =>
                    translatePage(
                        currentLanguage()
                    ),
                350
            );
        }
    );


    const observer =
        new MutationObserver(
            mutations => {
                const language =
                    currentLanguage();

                if (language === "en") {
                    return;
                }

                for (
                    const mutation
                    of mutations
                ) {
                    for (
                        const node
                        of mutation.addedNodes
                    ) {
                        if (
                            node.nodeType
                            === Node.TEXT_NODE
                        ) {
                            translateTextNode(
                                node,
                                language
                            );
                        }

                        if (
                            node.nodeType
                            === Node.ELEMENT_NODE
                        ) {
                            node
                                .querySelectorAll?.(
                                    "input, textarea, button, a, select"
                                )
                                .forEach(
                                    element =>
                                        translateAttributes(
                                            element,
                                            language
                                        )
                                );
                        }
                    }
                }
            }
        );


    document.addEventListener(
        "DOMContentLoaded",
        () => {
            observer.observe(
                document.body,
                {
                    childList: true,
                    subtree: true
                }
            );
        }
    );

})();
