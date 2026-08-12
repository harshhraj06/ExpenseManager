(() => {
    "use strict";

    const originalButton =
        document.getElementById(
            "notifBellBtn"
        );

    const dropdown =
        document.getElementById(
            "notifDropdown"
        );

    if (
        !originalButton
        || !dropdown
    ) {
        return;
    }


    /*
     * Clone the bell button.
     *
     * This removes any duplicate click listeners that
     * previous notification scripts attached to it.
     */
    const button =
        originalButton.cloneNode(true);

    originalButton.replaceWith(
        button
    );


    button.addEventListener(
        "click",
        (event) => {

            /*
             * Prevent older document handlers from
             * immediately closing the popup.
             */
            event.preventDefault();

            event.stopPropagation();

            event.stopImmediatePropagation();

            dropdown.classList.toggle(
                "open"
            );

        }
    );


    /*
     * Clicking inside notification panel
     * should never close it unexpectedly.
     */
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

                dropdown.classList.remove(
                    "open"
                );

            }

        }
    );


    /*
     * Escape closes notifications.
     */
    document.addEventListener(
        "keydown",
        (event) => {

            if (
                event.key === "Escape"
            ) {

                dropdown.classList.remove(
                    "open"
                );

            }

        }
    );

})();
