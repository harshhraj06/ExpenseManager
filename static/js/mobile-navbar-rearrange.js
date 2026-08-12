(() => {
    "use strict";

    const media =
        window.matchMedia(
            "(max-width: 768px)"
        );


    document.querySelectorAll(
        ".nav"
    )
    .forEach((nav) => {

        const links =
            nav.querySelector(
                ".nav-links"
            );

        if (!links) {
            return;
        }


        const notification =
            links.querySelector(
                ".notif-bell-wrap"
            );

        if (!notification) {
            return;
        }


        const placeholder =
            document.createComment(
                "mobile-notification-position"
            );

        notification.before(
            placeholder
        );


        function sync() {

            if (media.matches) {

                notification.classList.add(
                    "mobile-rearranged-notif"
                );

                nav.appendChild(
                    notification
                );

            } else {

                notification.classList.remove(
                    "mobile-rearranged-notif"
                );

                if (
                    placeholder.parentNode
                ) {
                    placeholder.after(
                        notification
                    );
                }

            }

        }


        media.addEventListener(
            "change",
            sync
        );


        sync();

    });

})();
