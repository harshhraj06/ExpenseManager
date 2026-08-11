(() => {
    const STORAGE_KEY =
        "expense-manager-theme";

    function getTheme() {
        const saved =
            localStorage.getItem(
                STORAGE_KEY
            );

        if (
            saved === "dark"
            || saved === "light"
        ) {
            return saved;
        }

        return window.matchMedia(
            "(prefers-color-scheme: light)"
        ).matches
            ? "light"
            : "dark";
    }


    function updateThemeColor(theme) {
        let meta =
            document.querySelector(
                'meta[name="theme-color"]'
            );

        if (!meta) {
            meta =
                document.createElement(
                    "meta"
                );

            meta.name =
                "theme-color";

            document.head.appendChild(
                meta
            );
        }

        meta.content =
            theme === "light"
                ? "#f4f6f8"
                : "#080808";
    }


    function applyTheme(theme) {
        document.documentElement.setAttribute(
            "data-theme",
            theme
        );

        updateThemeColor(
            theme
        );

        const button =
            document.getElementById(
                "global-theme-toggle"
            );

        if (!button) {
            return;
        }

        const icon =
            button.querySelector(
                ".theme-toggle-icon"
            );

        const label =
            button.querySelector(
                ".theme-toggle-label"
            );

        const isDark =
            theme === "dark";

        if (icon) {
            icon.textContent =
                isDark
                    ? "☀"
                    : "☾";
        }

        if (label) {
            label.textContent =
                isDark
                    ? "Light mode"
                    : "Dark mode";
        }

        button.setAttribute(
            "aria-label",
            isDark
                ? "Switch to light mode"
                : "Switch to dark mode"
        );

        button.setAttribute(
            "title",
            isDark
                ? "Light mode"
                : "Dark mode"
        );
    }


    function createToggle() {
        if (
            document.getElementById(
                "global-theme-toggle"
            )
        ) {
            return;
        }

        const button =
            document.createElement(
                "button"
            );

        button.type =
            "button";

        button.id =
            "global-theme-toggle";

        button.className =
            "theme-toggle";

        button.innerHTML = `
            <span
                class="theme-toggle-icon"
                aria-hidden="true">
            </span>

            <span
                class="theme-toggle-label">
            </span>
        `;

        button.addEventListener(
            "click",
            () => {
                const current =
                    document.documentElement
                        .getAttribute(
                            "data-theme"
                        )
                    || "dark";

                const next =
                    current === "dark"
                        ? "light"
                        : "dark";

                localStorage.setItem(
                    STORAGE_KEY,
                    next
                );

                applyTheme(
                    next
                );
            }
        );

        document.body.appendChild(
            button
        );
    }




    function positionThemeToggleAboveStatus() {
        const themeButton =
            document.getElementById(
                "global-theme-toggle"
            );

        if (!themeButton) {
            return;
        }

        const selectors = [
            "#offline-indicator",
            ".offline-indicator",
            "#connection-status",
            ".connection-status",
            ".online-status",
            ".offline-status"
        ];

        let statusElement = null;

        for (const selector of selectors) {
            const element =
                document.querySelector(
                    selector
                );

            if (
                element
                && element !== themeButton
            ) {
                statusElement = element;
                break;
            }
        }

        if (!statusElement) {
            themeButton.style.bottom =
                window.innerWidth <= 600
                    ? "72px"
                    : "82px";

            return;
        }

        const rect =
            statusElement.getBoundingClientRect();

        if (
            rect.width === 0
            && rect.height === 0
        ) {
            return;
        }

        const distanceFromBottom =
            window.innerHeight
            - rect.top;

        themeButton.style.bottom =
            `${distanceFromBottom + 10}px`;
    }


    document.addEventListener(
        "DOMContentLoaded",
        () => {
            createToggle();

            applyTheme(
                getTheme()
            );

            positionThemeToggleAboveStatus();

            setTimeout(
                positionThemeToggleAboveStatus,
                300
            );
        }
    );

    window.addEventListener(
        "resize",
        positionThemeToggleAboveStatus
    );

    window.addEventListener(
        "online",
        () => {
            setTimeout(
                positionThemeToggleAboveStatus,
                100
            );
        }
    );

    window.addEventListener(
        "offline",
        () => {
            setTimeout(
                positionThemeToggleAboveStatus,
                100
            );
        }
    );


    const media =
        window.matchMedia(
            "(prefers-color-scheme: light)"
        );

    media.addEventListener?.(
        "change",
        event => {
            if (
                localStorage.getItem(
                    STORAGE_KEY
                )
            ) {
                return;
            }

            applyTheme(
                event.matches
                    ? "light"
                    : "dark"
            );
        }
    );
})();
