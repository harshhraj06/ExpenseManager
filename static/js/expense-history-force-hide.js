(() => {
    "use strict";

    const section =
        document.querySelector(
            ".expense-history-section"
        );

    if (!section) {
        return;
    }


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


    const tables =
        [...section.querySelectorAll(
            "table"
        )];


    if (!tables.length) {
        return;
    }


    function hideHistory() {

        section.classList.remove(
            "expense-history-open"
        );

        tables.forEach((table) => {

            table.hidden = true;

            table.style.setProperty(
                "display",
                "none",
                "important"
            );
        });
    }


    function showHistory() {

        section.classList.add(
            "expense-history-open"
        );

        tables.forEach((table) => {

            table.hidden = false;

            table.style.setProperty(
                "display",
                "table",
                "important"
            );
        });
    }


    /*
     * ALWAYS CLOSED ON INITIAL PAGE LOAD.
     */
    hideHistory();


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


    /*
     * Remove any previous toggle buttons so
     * only one control exists.
     */
    section.querySelectorAll(
        ".expense-history-toggle-btn, " +
        ".history-toggle-btn"
    ).forEach((button) => {
        button.remove();
    });


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

        const download =
            [...section.querySelectorAll("a")]
            .find((link) => {

                return (
                    link.textContent || ""
                )
                .toLowerCase()
                .includes(
                    "download expense bill"
                );
            });


        if (download) {
            actions.appendChild(
                download
            );
        }

        header.appendChild(
            actions
        );
    }


    const button =
        document.createElement(
            "button"
        );

    button.type =
        "button";

    button.className =
        "expense-history-toggle-btn";


    const eye = `
        <svg viewBox="0 0 24 24">
            <path
                d="M2.5 12s3.5-6 9.5-6
                   9.5 6 9.5 6
                   -3.5 6-9.5 6
                   -9.5-6-9.5-6">
            </path>
            <circle cx="12" cy="12" r="2.7"></circle>
        </svg>
    `;


    function updateButton() {

        const open =
            section.classList.contains(
                "expense-history-open"
            );

        button.innerHTML =
            eye +
            (
                open
                ? "<span>Hide History</span>"
                : "<span>Show History</span>"
            );
    }


    button.addEventListener(
        "click",
        () => {

            if (
                section.classList.contains(
                    "expense-history-open"
                )
            ) {
                hideHistory();
            } else {
                showHistory();
            }

            updateButton();
        }
    );


    actions.appendChild(
        button
    );

    updateButton();

})();
