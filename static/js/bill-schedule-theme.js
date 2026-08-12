(() => {
    "use strict";

    /*
     * Locate the current New Bill panel without depending
     * on one exact HTML class name.
     */
    const possiblePanels = [
        ...document.querySelectorAll(
            "#bill-form, "
            + "section, "
            + "aside, "
            + "article, "
            + ".card, "
            + "[class*='panel']"
        )
    ];


    const panel = possiblePanels.find(
        (element) => {

            const text = (
                element.textContent || ""
            ).toLowerCase();

            return (
                text.includes("new bill")
                && text.includes(
                    "add to schedule"
                )
            );
        }
    ) || document.querySelector(
        "#bill-form"
    );


    if (panel) {

        panel.classList.add(
            "bill-schedule-professional"
        );


        /*
         * Find the smaller recurring-bill explanation box.
         */
        const elements = [
            ...panel.querySelectorAll(
                "strong, h4, h5, h6, span, p"
            )
        ];

        const recurringTitle =
            elements.find((element) => {

                return (
                    element.textContent
                    || ""
                )
                .trim()
                .toLowerCase()
                === "recurring bill logic";
            });


        if (recurringTitle) {

            const note =
                recurringTitle.closest(
                    ".recurring-note, "
                    + ".form-note, "
                    + ".logic-note, "
                    + "div, "
                    + "aside"
                );

            if (note) {
                note.classList.add(
                    "recurring-logic-professional"
                );
            }
        }
    }

})();
