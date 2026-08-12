(() => {
    "use strict";

    document.addEventListener(
        "DOMContentLoaded",
        initSponsoredPlacement
    );

    async function initSponsoredPlacement() {

        const heroRight =
            document.querySelector(".hero-right");

        if (!heroRight) {
            return;
        }

        const financeMap =
            heroRight.querySelector(
                ".hero-finance-map"
            );

        let slot =
            heroRight.querySelector(
                ".hero-sponsored-slot"
            );

        if (!slot) {
            slot = document.createElement("div");
            slot.className = "hero-sponsored-slot";
            slot.hidden = true;

            heroRight.prepend(slot);
        }


        function showFinanceMap() {

            slot.hidden = true;
            slot.innerHTML = "";

            if (financeMap) {
                financeMap.hidden = false;
                financeMap.style.display = "";
            }
        }


        let response;

        try {

            response = await fetch(
                "/api/dashboard-ad",
                {
                    credentials: "same-origin",
                    cache: "no-store"
                }
            );

        } catch (error) {

            console.warn(
                "Sponsored campaign request failed:",
                error
            );

            showFinanceMap();

            return;
        }


        if (!response.ok) {

            showFinanceMap();

            return;
        }


        let payload;

        try {

            payload = await response.json();

        } catch {

            showFinanceMap();

            return;
        }


        const ads =
            Array.isArray(payload.ads)
                ? payload.ads
                : [];


        if (!ads.length) {

            showFinanceMap();

            return;
        }


        /* ==============================================
           Active ad exists:
           hide finance diagram
           ============================================== */

        if (financeMap) {

            financeMap.hidden = true;
            financeMap.style.display = "none";
        }

        slot.hidden = false;


        let currentIndex = 0;

        const recordedImpressions =
            new Set();


        function createElement(
            tag,
            className,
            text
        ) {

            const element =
                document.createElement(tag);

            if (className) {
                element.className = className;
            }

            if (text !== undefined) {
                element.textContent = text;
            }

            return element;
        }


        function recordImpression(ad) {

            if (
                !ad.id ||
                recordedImpressions.has(ad.id)
            ) {
                return;
            }

            recordedImpressions.add(ad.id);

            fetch(
                "/api/sponsored/impression/"
                + encodeURIComponent(ad.id),
                {
                    method: "POST",
                    credentials: "same-origin",
                    keepalive: true
                }
            ).catch(() => {});
        }


        function renderAd(index) {

            const ad = ads[index];

            if (!ad) {
                return;
            }

            slot.innerHTML = "";


            const card =
                createElement(
                    "article",
                    "hero-sponsored-card"
                );


            /* ==========================================
               AD IMAGE
               ========================================== */

            if (ad.image_url) {

                const media =
                    createElement(
                        "div",
                        "hero-sponsored-media"
                    );

                const image =
                    document.createElement("img");

                image.src = ad.image_url;
                image.alt = "";

                image.loading = "lazy";

                image.addEventListener(
                    "error",
                    () => {
                        media.remove();
                    }
                );

                media.appendChild(image);

                card.appendChild(media);
            }


            /* ==========================================
               CONTENT
               ========================================== */

            const content =
                createElement(
                    "div",
                    "hero-sponsored-content"
                );


            const top =
                createElement(
                    "div",
                    "hero-sponsored-top"
                );


            const brand =
                createElement(
                    "div",
                    "hero-sponsored-brand"
                );


            if (ad.logo_url) {

                const logo =
                    document.createElement("img");

                logo.src = ad.logo_url;
                logo.alt = "";

                logo.loading = "lazy";

                logo.addEventListener(
                    "error",
                    () => {
                        logo.remove();
                    }
                );

                brand.appendChild(logo);
            }


            const brandCopy =
                document.createElement("div");


            brandCopy.appendChild(
                createElement(
                    "span",
                    "hero-sponsored-label",
                    ad.badge_text || "Sponsored"
                )
            );


            brandCopy.appendChild(
                createElement(
                    "strong",
                    "hero-sponsored-name",
                    ad.sponsor_name || "Partner"
                )
            );


            brand.appendChild(brandCopy);

            top.appendChild(brand);


            if (
                ad.campaign_type ===
                "sponsorship"
            ) {

                top.appendChild(
                    createElement(
                        "span",
                        "hero-sponsored-type",
                        "Partner"
                    )
                );
            }


            content.appendChild(top);


            content.appendChild(
                createElement(
                    "h3",
                    "hero-sponsored-headline",
                    ad.headline || ""
                )
            );


            if (ad.description) {

                content.appendChild(
                    createElement(
                        "p",
                        "hero-sponsored-description",
                        ad.description
                    )
                );
            }


            /* ==========================================
               FOOTER / CTA
               ========================================== */

            const footer =
                createElement(
                    "div",
                    "hero-sponsored-footer"
                );


            if (ad.destination_url) {

                const cta =
                    createElement(
                        "a",
                        "hero-sponsored-cta",
                        ad.cta_text || "Learn more"
                    );

                cta.href =
                    "/sponsored/click/"
                    + encodeURIComponent(ad.id);

                cta.target = "_blank";

                cta.rel =
                    "nofollow sponsored noopener";

                footer.appendChild(cta);

            } else {

                footer.appendChild(
                    createElement(
                        "span",
                        "hero-sponsored-cta",
                        ad.cta_text || "Sponsored"
                    )
                );
            }


            /* ==========================================
               ROTATION DOTS
               ========================================== */

            if (ads.length > 1) {

                const dots =
                    createElement(
                        "div",
                        "hero-sponsored-dots"
                    );


                ads.forEach(
                    (_, dotIndex) => {

                        const dot =
                            document.createElement(
                                "button"
                            );

                        dot.type = "button";

                        if (dotIndex === index) {
                            dot.classList.add("active");
                        }

                        dot.setAttribute(
                            "aria-label",
                            "Show sponsored campaign "
                            + (dotIndex + 1)
                        );


                        dot.addEventListener(
                            "click",
                            () => {

                                currentIndex =
                                    dotIndex;

                                renderAd(
                                    currentIndex
                                );
                            }
                        );


                        dots.appendChild(dot);
                    }
                );


                footer.appendChild(dots);
            }


            content.appendChild(footer);

            card.appendChild(content);

            slot.appendChild(card);


            recordImpression(ad);
        }


        renderAd(currentIndex);


        /* ==============================================
           Rotate multiple campaigns every 8 seconds
           ============================================== */

        if (ads.length > 1) {

            window.setInterval(
                () => {

                    if (
                        document.hidden
                    ) {
                        return;
                    }

                    currentIndex =
                        (
                            currentIndex + 1
                        ) % ads.length;

                    renderAd(currentIndex);

                },
                8000
            );
        }
    }
})();
