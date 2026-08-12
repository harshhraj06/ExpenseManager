(() => {
    "use strict";

    document.addEventListener(
        "DOMContentLoaded",
        () => {

            const menu =
                document.getElementById(
                    "profileDropdown"
                );

            if (
                !menu
                ||
                menu.querySelector(
                    ".profile-security-entry"
                )
            ) {
                return;
            }


            const link =
                document.createElement(
                    "a"
                );

            link.href =
                "/security";

            link.className =
                "profile-security-entry";

            link.innerHTML = `
                <span>◎</span>
                Security & device unlock
            `;


            menu.appendChild(
                link
            );

        }
    );

})();
