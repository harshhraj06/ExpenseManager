(() => {
    "use strict";


    function base64urlToBuffer(
        value
    ) {

        const padding =
            "=".repeat(
                (
                    4
                    - value.length % 4
                ) % 4
            );

        const base64 =
            (
                value
                + padding
            )
            .replace(/-/g, "+")
            .replace(/_/g, "/");


        const binary =
            atob(base64);


        const bytes =
            new Uint8Array(
                binary.length
            );


        for (
            let i = 0;
            i < binary.length;
            i++
        ) {
            bytes[i] =
                binary.charCodeAt(i);
        }


        return bytes.buffer;
    }


    function bufferToBase64url(
        buffer
    ) {

        const bytes =
            new Uint8Array(
                buffer
            );

        let binary = "";


        for (
            let i = 0;
            i < bytes.length;
            i++
        ) {

            binary +=
                String.fromCharCode(
                    bytes[i]
                );

        }


        return btoa(binary)
            .replace(/\+/g, "-")
            .replace(/\//g, "_")
            .replace(/=+$/g, "");
    }


    function decodeCreationOptions(
        options
    ) {

        options.challenge =
            base64urlToBuffer(
                options.challenge
            );


        options.user.id =
            base64urlToBuffer(
                options.user.id
            );


        options.excludeCredentials =
            (
                options.excludeCredentials
                || []
            )
            .map(
                credential => ({
                    ...credential,

                    id:
                        base64urlToBuffer(
                            credential.id
                        )
                })
            );


        return options;
    }


    function decodeRequestOptions(
        options
    ) {

        options.challenge =
            base64urlToBuffer(
                options.challenge
            );


        options.allowCredentials =
            (
                options.allowCredentials
                || []
            )
            .map(
                credential => ({
                    ...credential,

                    id:
                        base64urlToBuffer(
                            credential.id
                        )
                })
            );


        return options;
    }


    function registrationJSON(
        credential
    ) {

        return {
            id:
                credential.id,

            rawId:
                bufferToBase64url(
                    credential.rawId
                ),

            type:
                credential.type,

            authenticatorAttachment:
                credential.authenticatorAttachment,

            clientExtensionResults:
                credential.getClientExtensionResults(),

            deviceName:
                (
                    navigator.userAgentData
                    ?.platform
                    ||
                    navigator.platform
                    ||
                    "This device"
                ),

            response: {

                clientDataJSON:
                    bufferToBase64url(
                        credential
                            .response
                            .clientDataJSON
                    ),

                attestationObject:
                    bufferToBase64url(
                        credential
                            .response
                            .attestationObject
                    ),

                transports:
                    credential
                        .response
                        .getTransports
                        ? credential
                            .response
                            .getTransports()
                        : []
            }
        };
    }


    function authenticationJSON(
        credential
    ) {

        return {
            id:
                credential.id,

            rawId:
                bufferToBase64url(
                    credential.rawId
                ),

            type:
                credential.type,

            authenticatorAttachment:
                credential.authenticatorAttachment,

            clientExtensionResults:
                credential.getClientExtensionResults(),

            response: {

                clientDataJSON:
                    bufferToBase64url(
                        credential
                            .response
                            .clientDataJSON
                    ),

                authenticatorData:
                    bufferToBase64url(
                        credential
                            .response
                            .authenticatorData
                    ),

                signature:
                    bufferToBase64url(
                        credential
                            .response
                            .signature
                    ),

                userHandle:
                    credential
                        .response
                        .userHandle
                        ? bufferToBase64url(
                            credential
                                .response
                                .userHandle
                        )
                        : null
            }
        };
    }


    async function platformAvailable() {

        if (
            !window.PublicKeyCredential
            ||
            !navigator.credentials
        ) {
            return false;
        }


        if (
            PublicKeyCredential
                .isUserVerifyingPlatformAuthenticatorAvailable
        ) {

            try {

                return await (
                    PublicKeyCredential
                        .isUserVerifyingPlatformAuthenticatorAvailable()
                );

            } catch {
                return false;
            }

        }


        return true;
    }


    // ======================================================
    // SECURITY PAGE — REGISTER
    // ======================================================

    async function setupSecurityPage() {

        const button =
            document.getElementById(
                "enableBiometricBtn"
            );

        if (!button) {
            return;
        }


        const status =
            document.getElementById(
                "biometricStatus"
            );

        const message =
            document.getElementById(
                "biometricMessage"
            );


        const available =
            await platformAvailable();


        if (!available) {

            status.textContent =
                "Device authentication unavailable";

            button.disabled =
                true;

            button.textContent =
                "Not available on this device";

            return;
        }


        status.textContent =
            "Device authentication available";


        button.addEventListener(
            "click",
            async () => {

                button.disabled = true;

                message.textContent =
                    "Waiting for device verification…";


                const csrf =
                    document.body.dataset
                        .securityCsrf;


                try {

                    const optionsResponse =
                        await fetch(
                            "/webauthn/register/options",
                            {
                                method: "POST",

                                credentials:
                                    "same-origin",

                                headers: {
                                    "X-CSRF-Token":
                                        csrf
                                }
                            }
                        );


                    const options =
                        await optionsResponse.json();


                    if (
                        !optionsResponse.ok
                    ) {
                        throw new Error(
                            options.error
                            ||
                            "Could not start device registration."
                        );
                    }


                    const credential =
                        await navigator.credentials
                            .create({
                                publicKey:
                                    decodeCreationOptions(
                                        options
                                    )
                            });


                    const verifyResponse =
                        await fetch(
                            "/webauthn/register/verify",
                            {
                                method: "POST",

                                credentials:
                                    "same-origin",

                                headers: {
                                    "Content-Type":
                                        "application/json",

                                    "X-CSRF-Token":
                                        csrf
                                },

                                body:
                                    JSON.stringify(
                                        registrationJSON(
                                            credential
                                        )
                                    )
                            }
                        );


                    const result =
                        await verifyResponse.json();


                    if (
                        !verifyResponse.ok
                        ||
                        !result.ok
                    ) {

                        throw new Error(
                            result.error
                            ||
                            "Device registration failed."
                        );
                    }


                    message.textContent =
                        "Device authentication enabled successfully.";


                    window.setTimeout(
                        () => {
                            window.location.reload();
                        },
                        700
                    );

                } catch (error) {

                    if (
                        error.name
                        === "NotAllowedError"
                    ) {

                        message.textContent =
                            "Device verification was cancelled.";

                    } else {

                        message.textContent =
                            error.message
                            ||
                            "Could not enable device authentication.";

                    }


                    button.disabled =
                        false;

                }

            }
        );

    }


    // ======================================================
    // LOGIN PAGE
    // ======================================================

    async function setupLoginPage() {

        const emailInput =
            document.querySelector(
                'input[name="email"]'
            );

        const passwordInput =
            document.querySelector(
                'input[name="password"]'
            );


        if (
            !emailInput
            ||
            !passwordInput
        ) {
            return;
        }


        const form =
            emailInput.closest(
                "form"
            );


        if (
            !form
            ||
            document.getElementById(
                "biometricLoginBtn"
            )
        ) {
            return;
        }


        const available =
            await platformAvailable();


        if (!available) {
            return;
        }


        const container =
            document.createElement(
                "div"
            );

        container.className =
            "biometric-login-block";


        container.innerHTML = `

            <div class="biometric-divider">
                <span>or</span>
            </div>

            <button
                type="button"
                id="biometricLoginBtn"
                class="biometric-login-btn">

                <span class="biometric-login-icon">
                    ◎
                </span>

                <span>
                    Use fingerprint / device unlock
                </span>

            </button>

            <div
                class="biometric-login-message"
                id="biometricLoginMessage">
            </div>
        `;


        form.appendChild(
            container
        );


        const button =
            container.querySelector(
                "#biometricLoginBtn"
            );

        const message =
            container.querySelector(
                "#biometricLoginMessage"
            );


        button.addEventListener(
            "click",
            async () => {

                const email =
                    emailInput.value
                        .trim();


                if (!email) {

                    message.textContent =
                        "Enter your email first.";

                    emailInput.focus();

                    return;
                }


                button.disabled =
                    true;

                message.textContent =
                    "Waiting for device verification…";


                try {

                    const optionsResponse =
                        await fetch(
                            "/webauthn/login/options",
                            {
                                method: "POST",

                                credentials:
                                    "same-origin",

                                headers: {
                                    "Content-Type":
                                        "application/json"
                                },

                                body:
                                    JSON.stringify({
                                        email
                                    })
                            }
                        );


                    const options =
                        await optionsResponse.json();


                    if (
                        !optionsResponse.ok
                    ) {
                        throw new Error(
                            options.error
                            ||
                            "Device login unavailable."
                        );
                    }


                    const credential =
                        await navigator.credentials
                            .get({
                                publicKey:
                                    decodeRequestOptions(
                                        options
                                    )
                            });


                    const verifyResponse =
                        await fetch(
                            "/webauthn/login/verify",
                            {
                                method: "POST",

                                credentials:
                                    "same-origin",

                                headers: {
                                    "Content-Type":
                                        "application/json"
                                },

                                body:
                                    JSON.stringify(
                                        authenticationJSON(
                                            credential
                                        )
                                    )
                            }
                        );


                    const result =
                        await verifyResponse.json();


                    if (
                        !verifyResponse.ok
                        ||
                        !result.ok
                    ) {

                        throw new Error(
                            result.error
                            ||
                            "Device authentication failed."
                        );
                    }


                    message.textContent =
                        "Verified. Signing in…";


                    window.location.href =
                        "/";

                } catch (error) {

                    if (
                        error.name
                        === "NotAllowedError"
                    ) {

                        message.textContent =
                            "Device verification was cancelled.";

                    } else {

                        message.textContent =
                            error.message
                            ||
                            "Device authentication failed.";

                    }


                    button.disabled =
                        false;

                }

            }
        );

    }


    document.addEventListener(
        "DOMContentLoaded",
        () => {

            setupSecurityPage();

            setupLoginPage();

        }
    );

})();
