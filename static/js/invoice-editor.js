(() => {
    "use strict";

    const form =
        document.getElementById(
            "invoiceEditorForm"
        );

    if (!form) {
        return;
    }


    const itemContainer =
        document.getElementById(
            "invoiceItems"
        );

    const previewItems =
        document.getElementById(
            "previewItems"
        );


    function money(value) {
        return "₹" +
            Number(value || 0)
                .toLocaleString(
                    "en-IN",
                    {
                        minimumFractionDigits: 2,
                        maximumFractionDigits: 2
                    }
                );
    }


    function numeric(value) {
        const number =
            Number(value);

        return Number.isFinite(number)
            ? number
            : 0;
    }


    function updateSimpleFields() {

        const mappings = {
            documentTitle:
                "previewDocumentTitle",

            invoiceNumber:
                "previewInvoiceNumber",

            issueDate:
                "previewIssueDate",

            businessName:
                "previewBusinessName",

            billToName:
                "previewBillTo",

            billToEmail:
                "previewBillToEmail",

            invoiceNotes:
                "previewNotes",

            invoiceFooter:
                "previewFooter",
        };


        Object.entries(
            mappings
        )
        .forEach(
            ([source, target]) => {

                const input =
                    form.querySelector(
                        `[data-preview="${source}"]`
                    );

                const output =
                    document.getElementById(
                        target
                    );

                if (
                    input
                    &&
                    output
                ) {
                    output.textContent =
                        input.value;
                }

            }
        );


        const businessEmail =
            form.querySelector(
                '[data-preview="businessEmail"]'
            );

        const businessPhone =
            form.querySelector(
                '[data-preview="businessPhone"]'
            );

        const businessAddress =
            form.querySelector(
                '[data-preview="businessAddress"]'
            );

        const meta =
            document.getElementById(
                "previewBusinessMeta"
            );

        if (meta) {

            meta.textContent = [
                businessEmail?.value,
                businessPhone?.value,
                businessAddress?.value
            ]
            .filter(Boolean)
            .join("\n");

        }


        const notes =
            form.querySelector(
                '[data-preview="invoiceNotes"]'
            );

        const notesBlock =
            document.getElementById(
                "previewNotesBlock"
            );

        if (
            notes
            &&
            notesBlock
        ) {

            notesBlock.style.display =
                notes.value.trim()
                    ? ""
                    : "none";

        }

    }


    function updateAccent() {

        const select =
            document.getElementById(
                "accentSelect"
            );

        const paper =
            document.getElementById(
                "invoicePaper"
            );

        if (
            !select
            ||
            !paper
        ) {
            return;
        }

        paper.className =
            "invoice-paper accent-"
            + select.value;

    }


    function updateTotals() {

        const rows =
            [
                ...itemContainer.querySelectorAll(
                    ".invoice-item-editor"
                )
            ];

        previewItems.innerHTML =
            "";

        let subtotal =
            0;


        rows.forEach(
            row => {

                const description =
                    row.querySelector(
                        '[name="item_description"]'
                    )?.value.trim()
                    || "Item";

                const quantity =
                    numeric(
                        row.querySelector(
                            '[name="item_quantity"]'
                        )?.value
                    );

                const rate =
                    numeric(
                        row.querySelector(
                            '[name="item_rate"]'
                        )?.value
                    );

                const total =
                    quantity * rate;

                subtotal +=
                    total;


                const preview =
                    document.createElement(
                        "div"
                    );

                preview.className =
                    "invoice-preview-item-row";

                preview.innerHTML = `
                    <span>${escapeHTML(description)}</span>
                    <span>${quantity}</span>
                    <span>${money(rate)}</span>
                    <span>${money(total)}</span>
                `;

                previewItems.appendChild(
                    preview
                );

            }
        );


        const taxPercent =
            numeric(
                document.getElementById(
                    "invoiceTax"
                )?.value
            );

        const discount =
            Math.max(
                numeric(
                    document.getElementById(
                        "invoiceDiscount"
                    )?.value
                ),
                0
            );

        const charges =
            Math.max(
                numeric(
                    document.getElementById(
                        "invoiceCharges"
                    )?.value
                ),
                0
            );

        const tax =
            subtotal *
            Math.max(
                taxPercent,
                0
            ) /
            100;

        const total =
            Math.max(
                subtotal
                + tax
                + charges
                - discount,
                0
            );


        document.getElementById(
            "previewSubtotal"
        ).textContent =
            money(subtotal);


        document.getElementById(
            "previewTax"
        ).textContent =
            money(tax);


        document.getElementById(
            "previewDiscount"
        ).textContent =
            "- " + money(discount);


        document.getElementById(
            "previewCharges"
        ).textContent =
            money(charges);


        document.getElementById(
            "previewTotal"
        ).textContent =
            money(total);


        document.getElementById(
            "previewTaxRow"
        ).style.display =
            tax > 0
                ? ""
                : "none";


        document.getElementById(
            "previewDiscountRow"
        ).style.display =
            discount > 0
                ? ""
                : "none";


        document.getElementById(
            "previewChargesRow"
        ).style.display =
            charges > 0
                ? ""
                : "none";

    }


    function escapeHTML(value) {

        const div =
            document.createElement(
                "div"
            );

        div.textContent =
            value;

        return div.innerHTML;

    }


    function bindItemRow(
        row
    ) {

        row.querySelectorAll(
            "input"
        )
        .forEach(
            input => {

                input.addEventListener(
                    "input",
                    updateTotals
                );

            }
        );


        const remove =
            row.querySelector(
                ".invoice-remove-item"
            );

        if (remove) {

            remove.addEventListener(
                "click",
                () => {

                    const rows =
                        itemContainer.querySelectorAll(
                            ".invoice-item-editor"
                        );

                    if (
                        rows.length <= 1
                    ) {
                        return;
                    }

                    row.remove();

                    updateTotals();

                }
            );

        }

    }


    itemContainer.querySelectorAll(
        ".invoice-item-editor"
    )
    .forEach(
        bindItemRow
    );


    document.getElementById(
        "addInvoiceItem"
    )
    ?.addEventListener(
        "click",
        () => {

            if (
                itemContainer.querySelectorAll(
                    ".invoice-item-editor"
                ).length >= 20
            ) {
                return;
            }

            const row =
                document.createElement(
                    "div"
                );

            row.className =
                "invoice-item-editor";

            row.innerHTML = `

                <label class="invoice-item-description">

                    Description

                    <input
                        name="item_description"
                        type="text"
                        value=""
                        maxlength="180">

                </label>

                <label>

                    Qty

                    <input
                        name="item_quantity"
                        type="number"
                        step="0.01"
                        min="0"
                        value="1">

                </label>

                <label>

                    Rate

                    <input
                        name="item_rate"
                        type="number"
                        step="0.01"
                        min="0"
                        value="0">

                </label>

                <button
                    type="button"
                    class="invoice-remove-item"
                    aria-label="Remove item">

                    ×

                </button>
            `;

            itemContainer.appendChild(
                row
            );

            bindItemRow(
                row
            );

            row.querySelector(
                '[name="item_description"]'
            )?.focus();

            updateTotals();

        }
    );


    form.querySelectorAll(
        "input, select, textarea"
    )
    .forEach(
        element => {

            element.addEventListener(
                "input",
                () => {
                    updateSimpleFields();
                    updateAccent();
                    updateTotals();
                }
            );

            element.addEventListener(
                "change",
                () => {
                    updateSimpleFields();
                    updateAccent();
                    updateTotals();
                }
            );

        }
    );


    updateSimpleFields();
    updateAccent();
    updateTotals();

})();
