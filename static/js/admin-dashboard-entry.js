(() => {
    "use strict";

    document.addEventListener(
        "DOMContentLoaded",
        async () => {

            const dropdown =
                document.getElementById(
                    "profileDropdown"
                );

            if (!dropdown) {
                return;
            }

            try {

                const response =
                    await fetch(
                        "/api/admin/access",
                        {
                            credentials:
                                "same-origin",
                            cache:
                                "no-store"
                        }
                    );

                if (!response.ok) {
                    return;
                }

                const data =
                    await response.json();

                if (!data.admin) {
                    return;
                }

                if (
                    dropdown.querySelector(
                        ".profile-admin-entry"
                    )
                ) {
                    return;
                }


                const divider =
                    document.createElement(
                        "div"
                    );

                divider.className =
                    "profile-admin-divider";


                const link =
                    document.createElement(
                        "a"
                    );

                link.href =
                    "/admin/ads";

                link.className =
                    "profile-admin-entry";

                link.innerHTML = `
                    <span class="profile-admin-icon">
                        AD
                    </span>

                    <span class="profile-admin-copy">
                        <strong>
                            Advertising Studio
                        </strong>

                        <small>
                            Manage ads & sponsorships
                        </small>
                    </span>

                    <span class="profile-admin-arrow">
                        →
                    </span>
                `;


                dropdown.appendChild(
                    divider
                );

                dropdown.appendChild(
                    link
                );

            } catch (error) {

                console.warn(
                    "Admin access check failed",
                    error
                );

            }

        }
    );

})();
