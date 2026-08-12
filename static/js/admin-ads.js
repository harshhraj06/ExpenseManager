(() => {
    "use strict";


    const form =
        document.getElementById(
            "campaignEditor"
        );

    if (!form) {
        return;
    }


    const sponsor =
        document.getElementById(
            "sponsorName"
        );

    const headline =
        document.getElementById(
            "adHeadline"
        );

    const description =
        document.getElementById(
            "adDescription"
        );

    const cta =
        document.getElementById(
            "adCta"
        );

    const imageUrl =
        document.getElementById(
            "adImageUrl"
        );

    const logoUrl =
        document.getElementById(
            "adLogoUrl"
        );


    const previewSponsor =
        document.getElementById(
            "previewSponsor"
        );

    const previewHeadline =
        document.getElementById(
            "previewHeadline"
        );

    const previewDescription =
        document.getElementById(
            "previewDescription"
        );

    const previewCta =
        document.getElementById(
            "previewCta"
        );

    const previewImage =
        document.getElementById(
            "previewAdImage"
        );

    const previewLogo =
        document.getElementById(
            "previewSponsorLogo"
        );


    function updatePreview() {

        previewSponsor.textContent =
            sponsor.value.trim()
            || "Sponsor";


        previewHeadline.textContent =
            headline.value.trim()
            || "Campaign headline";


        previewDescription.textContent =
            description.value.trim()
            ||
            "Your sponsored message will appear here.";


        previewCta.textContent =
            cta.value.trim()
            || "Learn more";


        const image =
            imageUrl.value.trim();


        if (image) {

            previewImage.src =
                image;

            previewImage.hidden =
                false;

        } else {

            previewImage.removeAttribute(
                "src"
            );

            previewImage.hidden =
                true;

        }


        const logo =
            logoUrl.value.trim();


        if (logo) {

            previewLogo.src =
                logo;

            previewLogo.hidden =
                false;

        } else {

            previewLogo.removeAttribute(
                "src"
            );

            previewLogo.hidden =
                true;

        }

    }


    [
        sponsor,
        headline,
        description,
        cta,
        imageUrl,
        logoUrl
    ]
    .forEach(
        element => {

            element?.addEventListener(
                "input",
                updatePreview
            );

        }
    );


    previewImage.addEventListener(
        "error",
        () => {
            previewImage.hidden =
                true;
        }
    );


    previewLogo.addEventListener(
        "error",
        () => {
            previewLogo.hidden =
                true;
        }
    );


    /* ======================================================
       UTC SCHEDULING
       Admin enters local time.
       Server stores UTC.
       ====================================================== */

    const startLocal =
        document.getElementById(
            "adStartLocal"
        );

    const endLocal =
        document.getElementById(
            "adEndLocal"
        );

    const startUtc =
        document.getElementById(
            "adStartUtc"
        );

    const endUtc =
        document.getElementById(
            "adEndUtc"
        );


    function utcToLocalInput(
        value
    ) {

        if (!value) {
            return "";
        }

        try {

            const date =
                new Date(
                    value + "Z"
                );

            if (
                Number.isNaN(
                    date.getTime()
                )
            ) {
                return "";
            }


            const offset =
                date.getTimezoneOffset()
                * 60000;


            return new Date(
                date.getTime()
                - offset
            )
            .toISOString()
            .slice(
                0,
                16
            );

        } catch {
            return "";
        }

    }


    function localToUtcInput(
        value
    ) {

        if (!value) {
            return "";
        }

        const date =
            new Date(
                value
            );

        if (
            Number.isNaN(
                date.getTime()
            )
        ) {
            return "";
        }


        return date
            .toISOString()
            .slice(
                0,
                16
            );

    }


    if (
        startUtc.value
    ) {
        startLocal.value =
            utcToLocalInput(
                startUtc.value
            );
    }


    if (
        endUtc.value
    ) {
        endLocal.value =
            utcToLocalInput(
                endUtc.value
            );
    }


    form.addEventListener(
        "submit",
        () => {

            startUtc.value =
                localToUtcInput(
                    startLocal.value
                );

            endUtc.value =
                localToUtcInput(
                    endLocal.value
                );

        }
    );


    updatePreview();

})();
