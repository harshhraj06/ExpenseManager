(() => {
    "use strict";

    const dropdown =
        document.getElementById(
            "profileDropdown"
        );

    if (!dropdown) {
        return;
    }

    if (
        dropdown.querySelector(
            ".profile-settings-link"
        )
    ) {
        return;
    }


    const link =
        document.createElement(
            "a"
        );

    link.href =
        "/profile";

    link.className =
        "profile-settings-link";

    link.innerHTML = `
        <span class="profile-settings-icon">
            <svg viewBox="0 0 24 24">
                <circle
                    cx="12"
                    cy="8"
                    r="3">
                </circle>

                <path
                    d="M5 20
                       c0-4 2.5-6 7-6
                       s7 2 7 6">
                </path>
            </svg>
        </span>

        <span>
            <strong>Account settings</strong>
            <small>Edit profile & security</small>
        </span>
    `;

    dropdown.appendChild(
        link
    );

})();
