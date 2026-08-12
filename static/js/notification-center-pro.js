(() => {
    "use strict";

    const bellIcon = `
        <svg viewBox="0 0 24 24">
            <path
                d="M18 8a6 6 0 0 0-12 0
                   c0 7-3 7-3 9h18
                   c0-2-3-2-3-9">
            </path>
            <path d="M10 21h4"></path>
        </svg>
    `;

    const updateIcon = `
        <svg viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="7"></circle>
            <path d="M12 8v4l3 2"></path>
        </svg>
    `;

    document.querySelectorAll(
        ".notif-bell-btn"
    ).forEach((button) => {

        if (
            button.querySelector(
                ".pro-notif-bell"
            )
        ) {
            return;
        }

        [...button.childNodes]
        .forEach((node) => {

            if (
                node.nodeType === Node.TEXT_NODE
                &&
                node.textContent.includes("🔔")
            ) {
                node.remove();
            }

        });

        const icon =
            document.createElement("span");

        icon.className =
            "pro-notif-bell";

        icon.innerHTML =
            bellIcon;

        button.prepend(icon);
    });


    document.querySelectorAll(
        ".notif-dropdown-header"
    ).forEach((header) => {

        if (
            header.querySelector(
                ".pro-notif-heading"
            )
        ) {
            return;
        }

        const oldTitle =
            header.querySelector(
                ":scope > span"
            );

        const heading =
            document.createElement("div");

        heading.className =
            "pro-notif-heading";

        heading.innerHTML = `
            <strong>Notification Center</strong>
            <small>Payments, reminders and account updates</small>
        `;

        if (oldTitle) {
            oldTitle.replaceWith(
                heading
            );
        } else {
            header.prepend(
                heading
            );
        }
    });


    document.querySelectorAll(
        ".notif-item"
    ).forEach((item) => {

        if (
            item.querySelector(
                ".pro-notif-item-icon"
            )
        ) {
            return;
        }

        const title =
            item.querySelector(
                ".notif-item-title"
            );

        if (title) {
            title.textContent =
                title.textContent
                .replace(/^🔔\s*/, "")
                .trim();
        }

        const icon =
            document.createElement("span");

        icon.className =
            "pro-notif-item-icon";

        icon.innerHTML =
            updateIcon;

        item.prepend(icon);
    });


    document.querySelectorAll(
        ".notif-empty"
    ).forEach((empty) => {

        empty.innerHTML = `
            <div class="pro-notif-empty-icon">
                ${bellIcon}
            </div>

            <span class="pro-notif-empty-title">
                You're all caught up
            </span>

            <span class="pro-notif-empty-copy">
                No new notifications right now.
            </span>
        `;
    });

})();
