(() => {
    "use strict";


    const select =
        document.getElementById(
            "billInvoiceSelect"
        );

    const open =
        document.getElementById(
            "openBillInvoiceEditor"
        );


    open?.addEventListener(
        "click",
        () => {

            const id =
                select?.value;

            if (!id) {
                return;
            }

            window.location.href =
                "/bill_invoice_editor/"
                + id;

        }
    );


    /*
     * Pending bills:
     * add Edit Invoice beside Pay Now.
     */

    document.querySelectorAll(
        'a[href^="/pay_bill_page/"]'
    )
    .forEach(
        paymentLink => {

            const id =
                paymentLink
                .getAttribute("href")
                .split("/")
                .filter(Boolean)
                .pop();

            if (!id) {
                return;
            }


            const edit =
                document.createElement(
                    "a"
                );

            edit.href =
                "/bill_invoice_editor/"
                + id;

            edit.className =
                "invoice-edit-inline";

            edit.textContent =
                "Edit Invoice";

            paymentLink.before(
                edit
            );

        }
    );


    /*
     * Paid bills:
     * change old Receipt link to professional invoice,
     * and add editor.
     */

    document.querySelectorAll(
        'a[href^="/bill_receipt/"]'
    )
    .forEach(
        receiptLink => {

            const id =
                receiptLink
                .getAttribute("href")
                .split("/")
                .filter(Boolean)
                .pop();

            if (!id) {
                return;
            }


            receiptLink.href =
                "/bill_invoice/"
                + id;

            receiptLink.textContent =
                "Download Invoice";

            receiptLink.classList.add(
                "invoice-download-inline"
            );


            const edit =
                document.createElement(
                    "a"
                );

            edit.href =
                "/bill_invoice_editor/"
                + id;

            edit.className =
                "invoice-edit-inline";

            edit.textContent =
                "Edit Invoice";

            receiptLink.before(
                edit
            );

        }
    );

})();
