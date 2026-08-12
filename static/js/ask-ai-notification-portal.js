(() => {
    "use strict";

    const oldButton =
        document.getElementById(
            "notifBellBtn"
        );

    const dropdown =
        document.getElementById(
            "notifDropdown"
        );

    if (
        !oldButton
        || !dropdown
    ) {
        return;
    }


    /*
     * Clone button to remove any old duplicate
     * notification click listeners.
     */

    const button =
        oldButton.cloneNode(true);

    oldButton.replaceWith(
        button
    );


    /*
     * Move dropdown directly under body.
     * This escapes every hero/topbar stacking context.
     */

    dropdown.classList.add(
        "ai-notif-portal"
    );

    document.body.appendChild(
        dropdown
    );


    function positionDropdown() {

        const rect =
            button.getBoundingClientRect();

        const width =
            Math.min(
                390,
                window.innerWidth - 28
            );

        let left =
            rect.right - width;

        if (left < 14) {
            left = 14;
        }

        if (
            left + width >
            window.innerWidth - 14
        ) {
            left =
                window.innerWidth
                - width
                - 14;
        }


        const top =
            Math.min(
                rect.bottom + 12,
                window.innerHeight - 100
            );


        dropdown.style.left =
            left + "px";

        dropdown.style.right =
            "auto";

        dropdown.style.top =
            top + "px";
    }


    function openDropdown() {

        positionDropdown();

        dropdown.classList.add(
            "open"
        );

        button.setAttribute(
            "aria-expanded",
            "true"
        );
    }


    function closeDropdown() {

        dropdown.classList.remove(
            "open"
        );

        button.setAttribute(
            "aria-expanded",
            "false"
        );
    }


    button.setAttribute(
        "aria-expanded",
        "false"
    );


    button.addEventListener(
        "click",
        (event) => {

            event.preventDefault();
            event.stopPropagation();
            event.stopImmediatePropagation();


            if (
                dropdown.classList.contains(
                    "open"
                )
            ) {
                closeDropdown();
            } else {
                openDropdown();
            }

        },
        true
    );


    dropdown.addEventListener(
        "click",
        (event) => {

            event.stopPropagation();

        }
    );


    document.addEventListener(
        "click",
        (event) => {

            if (
                dropdown.classList.contains(
                    "open"
                )
                &&
                !dropdown.contains(
                    event.target
                )
                &&
                !button.contains(
                    event.target
                )
            ) {
                closeDropdown();
            }

        }
    );


    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Escape"
            ) {
                closeDropdown();
            }

        }
    );


    window.addEventListener(
        "resize",
        () => {

            if (
                dropdown.classList.contains(
                    "open"
                )
            ) {
                positionDropdown();
            }

        }
    );


    window.addEventListener(
        "scroll",
        () => {

            if (
                dropdown.classList.contains(
                    "open"
                )
            ) {
                positionDropdown();
            }

        },
        {
            passive: true
        }
    );

})();
