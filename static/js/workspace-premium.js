(() => {
    "use strict";

    const path = window.location.pathname;

    document.body.classList.add(
        "workspace-premium"
    );


    if (path === "/groups") {
        document.body.classList.add(
            "pw-groups"
        );
    }


    if (path === "/bills") {
        document.body.classList.add(
            "pw-bills"
        );
    }


    if (
        path === "/connected_apps"
        || path.startsWith(
            "/connected_apps/"
        )
    ) {
        document.body.classList.add(
            "pw-connected-apps"
        );
    }


    // -------------------------------------------------------
    // Cards
    // -------------------------------------------------------

    const cards = [
        ...document.querySelectorAll(
            ".card, "
            + ".integration-card, "
            + ".provider-card, "
            + ".app-card, "
            + ".group-card, "
            + ".bill-card, "
            + "article"
        )
    ];


    cards.forEach((card) => {
        card.classList.add(
            "pw-card"
        );
    });


    // -------------------------------------------------------
    // Masthead
    // -------------------------------------------------------

    const pageTitle =
        document.querySelector(
            ".container h1, main h1"
        );

    if (pageTitle) {

        const parent =
            pageTitle.closest(
                ".card, "
                + "section, "
                + "article, "
                + ".hero"
            )
            || pageTitle.parentElement;

        if (parent) {
            parent.classList.add(
                "pw-masthead"
            );
        }
    }


    // -------------------------------------------------------
    // Stat cards
    // -------------------------------------------------------

    document.querySelectorAll(
        ".stat-card, "
        + "[class*='stat-card'], "
        + "[class*='metric-card'], "
        + "[class*='summary-card']"
    ).forEach((element) => {

        element.classList.add(
            "pw-stat"
        );

    });


    // -------------------------------------------------------
    // Helper
    // -------------------------------------------------------

    function text(element) {
        return (
            element.textContent || ""
        )
        .replace(/\s+/g, " ")
        .trim()
        .toLowerCase();
    }


    // -------------------------------------------------------
    // Groups
    // -------------------------------------------------------

    if (
        document.body.classList.contains(
            "pw-groups"
        )
    ) {

        cards.forEach((card) => {

            const value = text(card);

            if (
                value.includes("create group")
                || value.includes("new group")
            ) {
                card.classList.add(
                    "pw-create-panel"
                );
            }

        });
    }


    // -------------------------------------------------------
    // Bills
    // -------------------------------------------------------

    if (
        document.body.classList.contains(
            "pw-bills"
        )
    ) {

        const billForm =
            document.querySelector(
                "#bill-form"
            );

        if (billForm) {
            billForm.classList.add(
                "pw-new-bill"
            );
        }


        cards.forEach((card) => {

            const value = text(card);

            if (
                value.includes(
                    "pending bill"
                )
                || value.includes(
                    "due now"
                )
            ) {
                card.classList.add(
                    "pw-pending"
                );
            }


            if (
                value.includes(
                    "paid bill"
                )
                || value.includes(
                    "payment history"
                )
            ) {
                card.classList.add(
                    "pw-paid"
                );
            }


            if (
                value.includes(
                    "recurring bill logic"
                )
            ) {
                card.classList.add(
                    "pw-recurring-note"
                );
            }

        });

    }


    // -------------------------------------------------------
    // Connected Apps
    // -------------------------------------------------------

    const brands = {

        gmail: "#EA4335",

        amazon: "#FF9900",

        flipkart: "#2874F0",

        swiggy: "#FC8019",

        zomato: "#E23744",

        blinkit: "#0C831F",

        zepto: "#8B3FFD",

        myntra: "#FF3F6C"

    };


    if (
        document.body.classList.contains(
            "pw-connected-apps"
        )
    ) {

        const providerHeadings =
            document.querySelectorAll(
                "h2, h3, h4, "
                + ".provider-name, "
                + ".integration-name"
            );


        providerHeadings.forEach(
            (heading) => {

                const name =
                    text(heading);

                const brandName =
                    Object.keys(
                        brands
                    ).find(
                        (key) =>
                            name === key
                            || name.startsWith(
                                key + " "
                            )
                    );

                if (!brandName) {
                    return;
                }


                const card =
                    heading.closest(
                        ".integration-card, "
                        + ".provider-card, "
                        + ".app-card, "
                        + ".card, "
                        + "article"
                    );


                if (!card) {
                    return;
                }


                card.classList.add(
                    "pw-provider"
                );


                card.style.setProperty(
                    "--provider-accent",
                    brands[brandName]
                );

            }
        );


        // Connected = green
        document.querySelectorAll(
            "span, strong, button, div"
        ).forEach((element) => {

            const value =
                text(element);

            if (
                value === "connected"
                || value === "connected ✓"
            ) {
                element.classList.add(
                    "pw-connected-state"
                );
            }

        });


        cards.forEach((card) => {

            const value = text(card);

            if (
                value.includes(
                    "sync activity"
                )
                || value.includes(
                    "recent activity"
                )
                || value.includes(
                    "imported activity"
                )
            ) {
                card.classList.add(
                    "pw-activity"
                );
            }

        });

    }


    // -------------------------------------------------------
    // Better table scrolling on mobile
    // -------------------------------------------------------

    document.querySelectorAll(
        "table"
    ).forEach((table) => {

        const parent =
            table.parentElement;

        if (parent) {
            parent.classList.add(
                "pw-table-container"
            );
        }

    });

})();
