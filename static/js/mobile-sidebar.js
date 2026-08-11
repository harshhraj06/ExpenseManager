document.addEventListener(
    "DOMContentLoaded",
    function () {

        const sidebar =
            document.getElementById(
                "mobile-app-sidebar"
            );

        const overlay =
            document.getElementById(
                "mobile-sidebar-overlay"
            );

        const openButton =
            document.getElementById(
                "mobile-sidebar-toggle"
            );

        const closeButton =
            document.getElementById(
                "mobile-sidebar-close"
            );


        if (
            !sidebar
            || !overlay
            || !openButton
        ) {
            console.warn(
                "Mobile sidebar elements missing."
            );

            return;
        }


        function openSidebar() {

            sidebar.classList.add(
                "open"
            );

            overlay.classList.add(
                "open"
            );

            document.body.classList.add(
                "mobile-sidebar-open"
            );

            sidebar.setAttribute(
                "aria-hidden",
                "false"
            );

            openButton.setAttribute(
                "aria-expanded",
                "true"
            );
        }


        function closeSidebar() {

            sidebar.classList.remove(
                "open"
            );

            overlay.classList.remove(
                "open"
            );

            document.body.classList.remove(
                "mobile-sidebar-open"
            );

            sidebar.setAttribute(
                "aria-hidden",
                "true"
            );

            openButton.setAttribute(
                "aria-expanded",
                "false"
            );
        }


        openButton.addEventListener(
            "click",
            openSidebar
        );


        closeButton?.addEventListener(
            "click",
            closeSidebar
        );


        overlay.addEventListener(
            "click",
            closeSidebar
        );


        document.addEventListener(
            "keydown",
            function (event) {

                if (event.key === "Escape") {
                    closeSidebar();
                }

            }
        );


        sidebar
            .querySelectorAll(
                'a[href^="#"]'
            )
            .forEach(
                function (link) {

                    link.addEventListener(
                        "click",
                        function (event) {

                            const selector =
                                link.getAttribute(
                                    "href"
                                );

                            const target =
                                document.querySelector(
                                    selector
                                );

                            if (!target) {
                                return;
                            }

                            event.preventDefault();

                            closeSidebar();

                            setTimeout(
                                function () {

                                    target.scrollIntoView({
                                        behavior:
                                            "smooth",

                                        block:
                                            "start"
                                    });

                                },
                                180
                            );

                        }
                    );

                }
            );



        // =================================================
        // MOBILE MENU AUTO HIDE
        // =================================================

        let lastScrollY =
            window.scrollY;

        let ticking =
            false;


        function updateMobileMenuVisibility() {

            if (
                window.innerWidth > 768
            ) {
                openButton.classList.remove(
                    "scroll-hidden",
                    "near-top"
                );

                return;
            }


            const currentScrollY =
                Math.max(
                    window.scrollY,
                    0
                );


            // Always show menu near top
            if (
                currentScrollY < 80
            ) {
                openButton.classList.remove(
                    "scroll-hidden"
                );

                openButton.classList.add(
                    "near-top"
                );

                lastScrollY =
                    currentScrollY;

                ticking =
                    false;

                return;
            }


            openButton.classList.remove(
                "near-top"
            );


            const difference =
                currentScrollY
                - lastScrollY;


            // Ignore tiny movements
            if (
                Math.abs(
                    difference
                ) < 6
            ) {
                ticking =
                    false;

                return;
            }


            // Swiping upward on phone /
            // scrolling DOWN the page:
            // hide hamburger button.
            if (
                currentScrollY
                > lastScrollY
            ) {
                openButton.classList.add(
                    "scroll-hidden"
                );
            }

            // Scrolling back UP the page:
            // show hamburger button again.
            else {
                openButton.classList.remove(
                    "scroll-hidden"
                );
            }


            lastScrollY =
                currentScrollY;

            ticking =
                false;
        }


        window.addEventListener(
            "scroll",
            function () {

                if (
                    document.body.classList.contains(
                        "mobile-sidebar-open"
                    )
                ) {
                    return;
                }


                if (!ticking) {

                    window.requestAnimationFrame(
                        updateMobileMenuVisibility
                    );

                    ticking =
                        true;
                }

            },
            {
                passive: true
            }
        );


        // Show button whenever sidebar closes
        const originalCloseSidebar =
            closeSidebar;



        console.log(
            "Mobile sidebar ready.",
            window.innerWidth
        );

    }
);
