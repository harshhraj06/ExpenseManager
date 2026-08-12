(() => {
    "use strict";

    const button =
        document.getElementById(
            "profileBtn"
        );

    if (!button) {
        return;
    }


    fetch(
        "/api/profile",
        {
            credentials:
                "same-origin"
        }
    )
    .then(response => {

        if (!response.ok) {
            throw new Error(
                "Profile unavailable"
            );
        }

        return response.json();

    })
    .then(profile => {

        if (!profile.profile_image) {
            return;
        }


        button.classList.add(
            "profile-btn-has-photo"
        );


        const image =
            document.createElement(
                "img"
            );

        image.src =
            profile.profile_image;

        image.alt =
            "Profile";

        image.className =
            "nav-profile-photo";


        button.prepend(
            image
        );

    })
    .catch(() => {});

})();
