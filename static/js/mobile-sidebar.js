document.addEventListener(
    "DOMContentLoaded",
    function () {
        "use strict";


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
            !sidebar ||
            !overlay ||
            !openButton
        ) {
            console.warn(
                "Mobile sidebar elements missing."
            );

            return;
        }


        /*
         * Closed sidebar should not contain
         * keyboard-focusable content.
         */
        sidebar.setAttribute(
            "aria-hidden",
            "true"
        );

        sidebar.setAttribute(
            "inert",
            ""
        );

        openButton.setAttribute(
            "aria-expanded",
            "false"
        );


        function openSidebar() {

            /*
             * Remove inert BEFORE opening,
             * otherwise controls cannot receive focus.
             */
            sidebar.removeAttribute(
                "inert"
            );

            sidebar.setAttribute(
                "aria-hidden",
                "false"
            );


            sidebar.classList.add(
                "open"
            );

            overlay.classList.add(
                "open"
            );

            document.body.classList.add(
                "mobile-sidebar-open"
            );


            openButton.setAttribute(
                "aria-expanded",
                "true"
            );


            /*
             * Move keyboard focus into drawer.
             */
            window.requestAnimationFrame(
                function () {
                    if (closeButton) {
                        try {
                            closeButton.focus({
                                preventScroll: true
                            });
                        } catch (_) {
                            closeButton.focus();
                        }
                    }
                }
            );
        }


        function closeSidebar() {

            /*
             * IMPORTANT:
             * Move focus OUT of the sidebar BEFORE
             * aria-hidden/inert is applied.
             *
             * This fixes:
             * "Blocked aria-hidden because descendant
             * retained focus."
             */

            document.body.classList.remove(
                "mobile-sidebar-open"
            );


            if (
                sidebar.contains(
                    document.activeElement
                )
            ) {
                try {
                    openButton.focus({
                        preventScroll: true
                    });
                } catch (_) {
                    openButton.focus();
                }
            }


            sidebar.classList.remove(
                "open"
            );

            overlay.classList.remove(
                "open"
            );


            sidebar.setAttribute(
                "aria-hidden",
                "true"
            );

            sidebar.setAttribute(
                "inert",
                ""
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


        if (closeButton) {
            closeButton.addEventListener(
                "click",
                closeSidebar
            );
        }


        overlay.addEventListener(
            "click",
            closeSidebar
        );


        document.addEventListener(
            "keydown",
            function (event) {

                if (
                    event.key === "Escape" &&
                    sidebar.classList.contains(
                        "open"
                    )
                ) {
                    closeSidebar();
                }

            }
        );


        /*
         * Hash links inside drawer:
         * close first, then scroll smoothly.
         */
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

                            if (
                                !selector ||
                                selector === "#"
                            ) {
                                return;
                            }


                            let target = null;

                            try {
                                target =
                                    document.querySelector(
                                        selector
                                    );
                            } catch (_) {
                                return;
                            }


                            if (!target) {
                                return;
                            }


                            event.preventDefault();

                            closeSidebar();


                            window.setTimeout(
                                function () {
                                    target.scrollIntoView({
                                        behavior:
                                            "smooth",

                                        block:
                                            "start"
                                    });
                                },
                                120
                            );
                        }
                    );

                }
            );


        /*
         * No scroll auto-hide.
         * Hamburger is now permanently part
         * of the mobile header.
         */
        openButton.classList.remove(
            "scroll-hidden",
            "near-top"
        );


        console.log(
            "Mobile sidebar ready.",
            window.innerWidth
        );
    }
);
