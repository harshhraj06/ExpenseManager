(() => {
    "use strict";

    /*
     * Connected Apps professional branding.
     *
     * IMPORTANT:
     * Branding is scoped ONLY to [data-integration-card].
     * It never scans every h3/h4 on the page.
     */

    const brands = {

        gmail: {
            slug: "gmail",
            color: "#EA4335",
            soft: "rgba(234, 67, 53, 0.10)"
        },

        amazon: {
            slug: "amazon",
            color: "#FF9900",
            soft: "rgba(255, 153, 0, 0.11)"
        },

        flipkart: {
            slug: "flipkart",
            color: "#2874F0",
            soft: "rgba(40, 116, 240, 0.10)"
        },

        swiggy: {
            slug: "swiggy",
            color: "#FC8019",
            soft: "rgba(252, 128, 25, 0.10)"
        },

        zomato: {
            slug: "zomato",
            color: "#E23744",
            soft: "rgba(226, 55, 68, 0.10)"
        },

        blinkit: {
            slug: "blinkit",
            color: "#0C831F",
            soft: "rgba(12, 131, 31, 0.10)"
        },

        zepto: {
            slug: "zepto",
            color: "#8A2BE2",
            soft: "rgba(138, 43, 226, 0.10)"
        },

        myntra: {
            slug: "myntra",
            color: "#FF3F6C",
            soft: "rgba(255, 63, 108, 0.10)"
        }

    };


    function normalise(value) {

        return String(value || "")
            .trim()
            .toLowerCase();

    }


    function createFallback(
        name,
        brand
    ) {

        const fallback =
            document.createElement("span");

        fallback.className =
            "platform-logo-fallback";

        fallback.textContent =
            name.charAt(0).toUpperCase();

        fallback.style.color =
            brand.color;

        return fallback;

    }


    function applyBrand(card) {

        /*
         * Explicit provider id is preferred.
         * Name is only a safe fallback.
         */

        const heading =
            card.querySelector(
                ".integration-card-body h3"
            );

        const provider =
            normalise(
                card.dataset.provider
                ||
                heading?.textContent
            );

        const brand =
            brands[provider];

        /*
         * Unknown providers keep their original monogram.
         */
        if (!brand) {
            return;
        }


        card.classList.add(
            "platform-branded-card"
        );


        /*
         * CSS variables exist only on THIS card.
         */

        card.style.setProperty(
            "--platform-accent",
            brand.color
        );

        card.style.setProperty(
            "--platform-soft",
            brand.soft
        );


        /*
         * Reuse the existing top-left monogram container.
         * This prevents duplicate letter + logo combinations.
         */

        const logoContainer =
            card.querySelector(
                ".provider-monogram"
            );

        if (!logoContainer) {
            return;
        }


        logoContainer.classList.add(
            "platform-brand-logo"
        );


        /*
         * Clear the old initial letter for known brands.
         */

        logoContainer.replaceChildren();


        const image =
            document.createElement("img");

        image.className =
            "platform-logo-image";


        /*
         * Correct Simple Icons URL.
         *
         * Previous script contained a Markdown-formatted URL,
         * which caused broken/mixed logo behaviour.
         */

        const iconColor =
            brand.color.replace("#", "");

        image.src =
            `https://cdn.simpleicons.org/${brand.slug}/${iconColor}`;

        image.alt =
            `${heading?.textContent.trim() || provider} logo`;

        image.loading =
            "lazy";

        image.decoding =
            "async";

        image.referrerPolicy =
            "no-referrer";


        const fallback =
            createFallback(
                heading?.textContent.trim()
                || provider,
                brand
            );


        image.addEventListener(
            "error",
            () => {

                image.remove();

                fallback.style.display =
                    "grid";

            },
            {
                once: true
            }
        );


        logoContainer.append(
            image,
            fallback
        );

    }


    /*
     * CRITICAL:
     * Only integration cards are branded.
     */

    document
        .querySelectorAll(
            "[data-integration-card]"
        )
        .forEach(
            applyBrand
        );

})();
