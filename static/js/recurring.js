(() => {
    function updateFields() {
        const type =
            document.getElementById("recurring-type");

        const category =
            document.getElementById(
                "recurring-category-wrap"
            );

        const source =
            document.getElementById(
                "recurring-source-wrap"
            );

        const description =
            document.getElementById(
                "recurring-description-wrap"
            );

        if (!type) {
            return;
        }

        const isIncome =
            type.value === "income";

        category?.classList.toggle(
            "hidden",
            isIncome
        );

        source?.classList.toggle(
            "hidden",
            !isIncome
        );

        description?.classList.toggle(
            "hidden",
            isIncome
        );
    }

    document.addEventListener(
        "DOMContentLoaded",
        () => {
            const type =
                document.getElementById(
                    "recurring-type"
                );

            type?.addEventListener(
                "change",
                updateFields
            );

            updateFields();
        }
    );
})();
