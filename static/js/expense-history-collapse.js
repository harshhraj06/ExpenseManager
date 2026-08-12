(() => {
    "use strict";

    const section =
        document.querySelector(
            ".expense-history-section"
        );

    if (!section) {
        return;
    }


    /* ------------------------------------------------------
       Find Expense History heading
       ------------------------------------------------------ */

    const heading =
        [...section.querySelectorAll(
            "h1, h2, h3"
        )].find((element) => {

            return (
                element.textContent || ""
            )
            .trim()
            .toLowerCase()
            === "expense history";

        });

    if (!heading) {
        return;
    }


    /* ------------------------------------------------------
       Locate table/history content
       ------------------------------------------------------ */

    const table =
        section.querySelector("table");

    if (table) {
        table.classList.add(
            "expense-history-toggle-target"
        );
    }


    /*
     * Support a mobile history list too,
     * if your mobile CSS/JS creates one.
     */
    section.querySelectorAll(
        ".expense-history-mobile-list, " +
        ".mobile-expense-history, " +
        "[data-expense-history-list]"
    ).forEach((element) => {

        element.classList.add(
            "expense-history-toggle-target"
        );

    });


    /* ------------------------------------------------------
       History starts closed every page load
       ------------------------------------------------------ */

    section.classList.remove(
        "expense-history-open"
    );


    /* ------------------------------------------------------
       Find/create section header
       ------------------------------------------------------ */

    let header =
        heading.closest(
            ".section-header"
        );

    if (!header) {

        header =
            document.createElement(
                "div"
            );

        header.className =
            "section-header";

        heading.parentNode.insertBefore(
            header,
            heading
        );

        header.appendChild(
            heading
        );
    }


    /* ------------------------------------------------------
       Actions wrapper
       ------------------------------------------------------ */

    let actions =
        header.querySelector(
            ".expense-history-header-actions"
        );

    if (!actions) {

        actions =
            document.createElement(
                "div"
            );

        actions.className =
            "expense-history-header-actions";


        /*
         * Keep Download Expense Bill beside
         * the Show History button.
         */
        const download =
            header.querySelector(
                ".download-btn"
            )
            ||
            [...section.querySelectorAll("a")]
            .find((link) =>
                (
                    link.textContent || ""
                )
                .toLowerCase()
                .includes(
                    "download expense bill"
                )
            );


        if (download) {
            actions.appendChild(
                download
            );
        }


        header.appendChild(
            actions
        );
    }


    /* ------------------------------------------------------
       Toggle button
       ------------------------------------------------------ */

    let button =
        actions.querySelector(
            ".expense-history-toggle-btn"
        );

    if (!button) {

        button =
            document.createElement(
                "button"
            );

        button.type =
            "button";

        button.className =
            "expense-history-toggle-btn";

        actions.appendChild(
            button
        );
    }


    const eyeIcon = `
        <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
                d="M2.5 12s3.5-6 9.5-6
                   9.5 6 9.5 6
                   -3.5 6-9.5 6
                   -9.5-6-9.5-6">
            </path>

            <circle
                cx="12"
                cy="12"
                r="2.7">
            </circle>
        </svg>
    `;


    function renderButton() {

        const open =
            section.classList.contains(
                "expense-history-open"
            );

        button.innerHTML =
            eyeIcon +
            (
                open
                    ? "<span>Hide History</span>"
                    : "<span>Show History</span>"
            );

        button.setAttribute(
            "aria-expanded",
            String(open)
        );
    }


    button.addEventListener(
        "click",
        () => {

            section.classList.toggle(
                "expense-history-open"
            );

            renderButton();

        }
    );


    renderButton();

})();
