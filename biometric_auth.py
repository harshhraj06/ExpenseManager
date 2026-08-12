import os
import time
import base64
import secrets
import hmac
import json

from urllib.parse import urlparse

import db_compat as sqlite3

from flask import (
    Blueprint,
    request,
    session,
    redirect,
    render_template,
    jsonify,
)

from webauthn import (
    generate_registration_options,
    verify_registration_response,
    generate_authentication_options,
    verify_authentication_response,
    options_to_json,
    base64url_to_bytes,
)

from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    AuthenticatorAttachment,
    UserVerificationRequirement,
    ResidentKeyRequirement,
    AttestationConveyancePreference,
    PublicKeyCredentialDescriptor,
)


biometric_bp = Blueprint(
    "biometric_auth",
    __name__
)

DATABASE_URL = os.environ.get(
    "DATABASE_URL"
)


# ============================================================
# DATABASE
# ============================================================

def _connect():
    if DATABASE_URL:
        return sqlite3.connect(
            DATABASE_URL
        )

    return sqlite3.connect()


def _ensure_tables():

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS webauthn_credentials (
            credential_id TEXT PRIMARY KEY,

            user_id INTEGER NOT NULL,

            public_key TEXT NOT NULL,

            sign_count INTEGER NOT NULL DEFAULT 0,

            device_name TEXT,

            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

            FOREIGN KEY(user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )

    cursor.execute(
        """
        CREATE INDEX IF NOT EXISTS
        idx_webauthn_credentials_user

        ON webauthn_credentials(user_id)
        """
    )

    conn.commit()
    conn.close()


_ensure_tables()


# ============================================================
# HELPERS
# ============================================================

def _b64url(data):

    return (
        base64.urlsafe_b64encode(
            data
        )
        .rstrip(b"=")
        .decode("ascii")
    )


def _row_value(
    row,
    index,
    key
):

    if row is None:
        return None

    try:
        return row[key]
    except Exception:
        return row[index]


def _rp_config():

    configured_origin = (
        os.environ.get(
            "WEBAUTHN_ORIGIN"
        )
        or
        os.environ.get(
            "APP_BASE_URL"
        )
    )

    origin = (
        configured_origin.rstrip("/")
        if configured_origin
        else request.host_url.rstrip("/")
    )

    parsed = urlparse(
        origin
    )

    rp_id = (
        os.environ.get(
            "WEBAUTHN_RP_ID"
        )
        or parsed.hostname
        or request.host.split(":")[0]
    )

    return (
        rp_id,
        origin
    )


def _store_challenge(
    prefix,
    challenge
):

    session[
        f"{prefix}_challenge"
    ] = _b64url(
        challenge
    )

    session[
        f"{prefix}_started"
    ] = int(
        time.time()
    )


def _consume_challenge(
    prefix
):

    encoded = session.pop(
        f"{prefix}_challenge",
        None
    )

    started = session.pop(
        f"{prefix}_started",
        None
    )

    if (
        not encoded
        or not started
    ):
        return None

    if (
        time.time()
        - float(started)
        > 300
    ):
        return None

    return base64url_to_bytes(
        encoded
    )


def _csrf_token():

    token = session.get(
        "security_csrf"
    )

    if not token:

        token = secrets.token_urlsafe(
            32
        )

        session[
            "security_csrf"
        ] = token

    return token


def _valid_csrf(
    supplied
):

    stored = session.get(
        "security_csrf"
    )

    if (
        not stored
        or not supplied
    ):
        return False

    return hmac.compare_digest(
        stored,
        supplied
    )


# ============================================================
# SECURITY PAGE
# ============================================================

@biometric_bp.route(
    "/security"
)
def security_page():

    if "user_id" not in session:
        return redirect(
            "/login"
        )

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            credential_id,
            device_name,
            created_at

        FROM webauthn_credentials

        WHERE user_id=?

        ORDER BY created_at DESC
        """,
        (
            session["user_id"],
        )
    )

    credentials = cursor.fetchall()

    conn.close()

    return render_template(
        "security.html",
        credentials=credentials,
        csrf_token=_csrf_token(),
    )


# ============================================================
# REGISTRATION OPTIONS
# ============================================================

@biometric_bp.route(
    "/webauthn/register/options",
    methods=["POST"]
)
def webauthn_register_options():

    if "user_id" not in session:

        return jsonify({
            "error":
                "Authentication required."
        }), 401


    if not _valid_csrf(
        request.headers.get(
            "X-CSRF-Token"
        )
    ):

        return jsonify({
            "error":
                "Invalid security request."
        }), 403


    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT
            id,
            username,
            email

        FROM users

        WHERE id=?
        """,
        (
            session["user_id"],
        )
    )

    user = cursor.fetchone()


    if not user:

        conn.close()

        return jsonify({
            "error":
                "Account not found."
        }), 404


    user_id = _row_value(
        user,
        0,
        "id"
    )

    username = _row_value(
        user,
        1,
        "username"
    )

    email = _row_value(
        user,
        2,
        "email"
    )


    cursor.execute(
        """
        SELECT credential_id

        FROM webauthn_credentials

        WHERE user_id=?
        """,
        (
            user_id,
        )
    )

    existing = cursor.fetchall()

    conn.close()


    excluded = []

    for row in existing:

        credential_id = _row_value(
            row,
            0,
            "credential_id"
        )

        excluded.append(
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(
                    credential_id
                )
            )
        )


    rp_id, _ = _rp_config()


    options = generate_registration_options(

        rp_id=rp_id,

        rp_name="ExpenseX",

        user_id=str(
            user_id
        ).encode("utf-8"),

        user_name=email,

        user_display_name=username,

        authenticator_selection=
            AuthenticatorSelectionCriteria(

                authenticator_attachment=
                    AuthenticatorAttachment.PLATFORM,

                resident_key=
                    ResidentKeyRequirement.PREFERRED,

                user_verification=
                    UserVerificationRequirement.REQUIRED,
            ),

        attestation=
            AttestationConveyancePreference.NONE,

        exclude_credentials=excluded,
    )


    _store_challenge(
        "webauthn_reg",
        options.challenge
    )


    return jsonify(
        json.loads(
            options_to_json(
                options
            )
        )
    )


# ============================================================
# COMPLETE REGISTRATION
# ============================================================

@biometric_bp.route(
    "/webauthn/register/verify",
    methods=["POST"]
)
def webauthn_register_verify():

    if "user_id" not in session:

        return jsonify({
            "ok": False,
            "error":
                "Authentication required."
        }), 401


    if not _valid_csrf(
        request.headers.get(
            "X-CSRF-Token"
        )
    ):

        return jsonify({
            "ok": False,
            "error":
                "Invalid security request."
        }), 403


    challenge = _consume_challenge(
        "webauthn_reg"
    )


    if not challenge:

        return jsonify({
            "ok": False,
            "error":
                "Security request expired. Try again."
        }), 400


    data = (
        request.get_json(
            silent=True
        )
        or {}
    )


    rp_id, origin = _rp_config()


    try:

        verification = (
            verify_registration_response(

                credential=data,

                expected_challenge=
                    challenge,

                expected_rp_id=
                    rp_id,

                expected_origin=
                    origin,

                require_user_verification=
                    True,
            )
        )

    except Exception as exc:

        print(
            "[webauthn registration]",
            exc
        )

        return jsonify({
            "ok": False,
            "error":
                "Device verification failed."
        }), 400


    credential_id = _b64url(
        verification.credential_id
    )

    public_key = _b64url(
        verification.credential_public_key
    )

    sign_count = int(
        verification.sign_count
        or 0
    )


    device_name = str(
        data.get(
            "deviceName"
        )
        or "This device"
    )[:150]


    conn = _connect()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT credential_id

        FROM webauthn_credentials

        WHERE credential_id=?
        """,
        (
            credential_id,
        )
    )

    existing = cursor.fetchone()


    if existing:

        cursor.execute(
            """
            UPDATE webauthn_credentials

            SET
                user_id=?,
                public_key=?,
                sign_count=?,
                device_name=?

            WHERE credential_id=?
            """,
            (
                session["user_id"],
                public_key,
                sign_count,
                device_name,
                credential_id,
            )
        )

    else:

        cursor.execute(
            """
            INSERT INTO webauthn_credentials
            (
                credential_id,
                user_id,
                public_key,
                sign_count,
                device_name
            )

            VALUES (?, ?, ?, ?, ?)
            """,
            (
                credential_id,
                session["user_id"],
                public_key,
                sign_count,
                device_name,
            )
        )


    conn.commit()
    conn.close()


    return jsonify({
        "ok": True
    })


# ============================================================
# LOGIN OPTIONS
# ============================================================

@biometric_bp.route(
    "/webauthn/login/options",
    methods=["POST"]
)
def webauthn_login_options():

    payload = (
        request.get_json(
            silent=True
        )
        or {}
    )


    email = str(
        payload.get(
            "email"
        )
        or ""
    ).strip().lower()


    conn = _connect()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT
            id,
            username,
            email

        FROM users

        WHERE email=?
        """,
        (
            email,
        )
    )

    user = cursor.fetchone()


    if not user:

        conn.close()

        return jsonify({
            "error":
                "Device login is unavailable for this account."
        }), 400


    user_id = _row_value(
        user,
        0,
        "id"
    )


    cursor.execute(
        """
        SELECT credential_id

        FROM webauthn_credentials

        WHERE user_id=?
        """,
        (
            user_id,
        )
    )

    rows = cursor.fetchall()

    conn.close()


    if not rows:

        return jsonify({
            "error":
                "Device login is unavailable for this account."
        }), 400


    descriptors = []

    for row in rows:

        credential_id = _row_value(
            row,
            0,
            "credential_id"
        )

        descriptors.append(
            PublicKeyCredentialDescriptor(
                id=base64url_to_bytes(
                    credential_id
                )
            )
        )


    rp_id, _ = _rp_config()


    options = generate_authentication_options(

        rp_id=rp_id,

        allow_credentials=
            descriptors,

        user_verification=
            UserVerificationRequirement.REQUIRED,
    )


    _store_challenge(
        "webauthn_login",
        options.challenge
    )

    session[
        "webauthn_login_user_id"
    ] = user_id


    return jsonify(
        json.loads(
            options_to_json(
                options
            )
        )
    )


# ============================================================
# LOGIN VERIFY
# ============================================================

@biometric_bp.route(
    "/webauthn/login/verify",
    methods=["POST"]
)
def webauthn_login_verify():

    challenge = _consume_challenge(
        "webauthn_login"
    )

    login_user_id = session.pop(
        "webauthn_login_user_id",
        None
    )


    if (
        not challenge
        or not login_user_id
    ):

        return jsonify({
            "ok": False,
            "error":
                "Device login expired. Try again."
        }), 400


    data = (
        request.get_json(
            silent=True
        )
        or {}
    )


    credential_id = str(
        data.get(
            "id"
        )
        or ""
    )


    conn = _connect()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT
            credential_id,
            public_key,
            sign_count

        FROM webauthn_credentials

        WHERE
            credential_id=?
            AND user_id=?
        """,
        (
            credential_id,
            login_user_id,
        )
    )

    credential = cursor.fetchone()


    if not credential:

        conn.close()

        return jsonify({
            "ok": False,
            "error":
                "Device credential not recognised."
        }), 400


    stored_public_key = _row_value(
        credential,
        1,
        "public_key"
    )

    stored_sign_count = int(
        _row_value(
            credential,
            2,
            "sign_count"
        )
        or 0
    )


    rp_id, origin = _rp_config()


    try:

        verification = (
            verify_authentication_response(

                credential=data,

                expected_challenge=
                    challenge,

                expected_rp_id=
                    rp_id,

                expected_origin=
                    origin,

                credential_public_key=
                    base64url_to_bytes(
                        stored_public_key
                    ),

                credential_current_sign_count=
                    stored_sign_count,

                require_user_verification=
                    True,
            )
        )

    except Exception as exc:

        conn.close()

        print(
            "[webauthn login]",
            exc
        )

        return jsonify({
            "ok": False,
            "error":
                "Device verification failed."
        }), 400


    cursor.execute(
        """
        UPDATE webauthn_credentials

        SET sign_count=?

        WHERE credential_id=?
        """,
        (
            int(
                verification.new_sign_count
                or 0
            ),
            credential_id,
        )
    )


    cursor.execute(
        """
        SELECT
            id,
            username,
            email

        FROM users

        WHERE id=?
        """,
        (
            login_user_id,
        )
    )

    user = cursor.fetchone()


    if not user:

        conn.close()

        return jsonify({
            "ok": False,
            "error":
                "Account not found."
        }), 404


    conn.commit()
    conn.close()


    session.permanent = True

    session[
        "user_id"
    ] = _row_value(
        user,
        0,
        "id"
    )

    session[
        "username"
    ] = _row_value(
        user,
        1,
        "username"
    )

    session[
        "email"
    ] = _row_value(
        user,
        2,
        "email"
    )


    return jsonify({
        "ok": True
    })


# ============================================================
# REMOVE DEVICE
# ============================================================

@biometric_bp.route(
    "/security/remove-device",
    methods=["POST"]
)
def remove_webauthn_device():

    if "user_id" not in session:
        return redirect(
            "/login"
        )


    supplied = request.form.get(
        "csrf_token",
        ""
    )


    if not _valid_csrf(
        supplied
    ):
        return (
            "Invalid security request.",
            403
        )


    credential_id = request.form.get(
        "credential_id",
        ""
    )


    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM webauthn_credentials

        WHERE
            credential_id=?
            AND user_id=?
        """,
        (
            credential_id,
            session["user_id"],
        )
    )

    conn.commit()
    conn.close()


    return redirect(
        "/security"
    )
