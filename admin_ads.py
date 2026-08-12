import os
import uuid
from datetime import datetime
from urllib.parse import urlparse

import db_compat as sqlite3

from flask import (
    Blueprint,
    render_template,
    request,
    session,
    redirect,
    abort,
)


admin_ads_bp = Blueprint(
    "admin_ads",
    __name__
)


DATABASE_URL = os.environ.get(
    "DATABASE_URL"
)


def _connect():

    if DATABASE_URL:
        return sqlite3.connect(
            DATABASE_URL
        )

    return sqlite3.connect()


# ============================================================
# DATABASE
# ============================================================

def _ensure_ad_tables():

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS sponsored_campaigns (
            id TEXT PRIMARY KEY,

            campaign_type TEXT NOT NULL
                DEFAULT 'advertisement',

            campaign_name TEXT NOT NULL,

            sponsor_name TEXT NOT NULL,

            headline TEXT NOT NULL,

            description TEXT,

            badge_text TEXT
                DEFAULT 'Sponsored',

            cta_text TEXT
                DEFAULT 'Learn more',

            logo_url TEXT,

            image_url TEXT,

            destination_url TEXT,

            placement TEXT NOT NULL
                DEFAULT 'dashboard_hero',

            status TEXT NOT NULL
                DEFAULT 'draft',

            start_at TEXT,

            end_at TEXT,

            priority INTEGER
                DEFAULT 0,

            impressions INTEGER
                DEFAULT 0,

            clicks INTEGER
                DEFAULT 0,

            created_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP,

            updated_at TIMESTAMP
                DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()


_ensure_ad_tables()


# ============================================================
# SECURITY
# ============================================================

def _configured_admin_emails():

    value = (
        os.environ.get(
            "ADMIN_EMAILS"
        )
        or
        os.environ.get(
            "ADMIN_EMAIL"
        )
        or
        ""
    )

    return {
        email.strip().lower()
        for email in value.split(",")
        if email.strip()
    }


def _current_user_email():

    if not session.get(
        "user_id"
    ):
        return None


    session_email = session.get(
        "email"
    )

    if session_email:
        return str(
            session_email
        ).strip().lower()


    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT email
        FROM users
        WHERE id=?
        """,
        (
            session["user_id"],
        )
    )

    row = cursor.fetchone()

    conn.close()


    if not row:
        return None


    return str(
        row[0]
    ).strip().lower()


def _is_admin():

    email = _current_user_email()

    return bool(
        email
        and
        email
        in _configured_admin_emails()
    )


def _admin_required():

    if not session.get(
        "user_id"
    ):
        return redirect(
            "/login"
        )

    if not _is_admin():
        abort(403)

    return None


# ============================================================
# HELPERS
# ============================================================

def _safe_http_url(
    value
):

    value = (
        value
        or ""
    ).strip()

    if not value:
        return ""

    try:

        parsed = urlparse(
            value
        )

        if parsed.scheme not in (
            "http",
            "https",
        ):
            return ""

        if not parsed.netloc:
            return ""

        return value

    except Exception:
        return ""


def _clean(
    value,
    limit
):

    return (
        value
        or ""
    ).strip()[:limit]


def _campaign_row_to_dict(
    row
):

    if not row:
        return None

    return {
        "id": row[0],
        "campaign_type": row[1],
        "campaign_name": row[2],
        "sponsor_name": row[3],
        "headline": row[4],
        "description": row[5] or "",
        "badge_text": row[6] or "Sponsored",
        "cta_text": row[7] or "Learn more",
        "logo_url": row[8] or "",
        "image_url": row[9] or "",
        "destination_url": row[10] or "",
        "placement": row[11],
        "status": row[12],
        "start_at": row[13] or "",
        "end_at": row[14] or "",
        "priority": row[15] or 0,
        "impressions": row[16] or 0,
        "clicks": row[17] or 0,
        "created_at": row[18],
        "updated_at": row[19],
    }


CAMPAIGN_SELECT = """
SELECT
    id,
    campaign_type,
    campaign_name,
    sponsor_name,
    headline,
    description,
    badge_text,
    cta_text,
    logo_url,
    image_url,
    destination_url,
    placement,
    status,
    start_at,
    end_at,
    priority,
    impressions,
    clicks,
    created_at,
    updated_at

FROM sponsored_campaigns
"""


# ============================================================
# ADMIN ACCESS API
# ============================================================

@admin_ads_bp.route(
    "/api/admin/access"
)
def admin_access():

    return {
        "admin": _is_admin()
    }


# ============================================================
# ADMIN PANEL
# ============================================================

@admin_ads_bp.route(
    "/admin/ads"
)
def admin_ads():

    denied = _admin_required()

    if denied:
        return denied


    conn = _connect()
    cursor = conn.cursor()


    cursor.execute(
        CAMPAIGN_SELECT
        +
        """
        ORDER BY
            priority DESC,
            created_at DESC
        """
    )

    campaigns = [
        _campaign_row_to_dict(
            row
        )
        for row
        in cursor.fetchall()
    ]


    cursor.execute(
        """
        SELECT
            COUNT(*),
            SUM(
                CASE
                    WHEN status='active'
                    THEN 1
                    ELSE 0
                END
            ),
            COALESCE(
                SUM(impressions),
                0
            ),
            COALESCE(
                SUM(clicks),
                0
            )

        FROM sponsored_campaigns
        """
    )

    stats_row = cursor.fetchone()


    stats = {
        "total": stats_row[0] or 0,
        "active": stats_row[1] or 0,
        "impressions": stats_row[2] or 0,
        "clicks": stats_row[3] or 0,
    }


    edit_campaign = None

    edit_id = request.args.get(
        "edit",
        ""
    ).strip()


    if edit_id:

        cursor.execute(
            CAMPAIGN_SELECT
            +
            """
            WHERE id=?
            """,
            (
                edit_id,
            )
        )

        edit_campaign = (
            _campaign_row_to_dict(
                cursor.fetchone()
            )
        )


    conn.close()


    return render_template(
        "admin_ads.html",
        campaigns=campaigns,
        stats=stats,
        edit_campaign=edit_campaign,
    )


# ============================================================
# CREATE / UPDATE CAMPAIGN
# ============================================================

@admin_ads_bp.route(
    "/admin/ads/save",
    methods=["POST"]
)
def admin_ads_save():

    denied = _admin_required()

    if denied:
        return denied


    campaign_id = (
        request.form.get(
            "campaign_id"
        )
        or
        (
            "cmp_"
            + uuid.uuid4().hex[:18]
        )
    )


    campaign_type = request.form.get(
        "campaign_type",
        "advertisement"
    )

    if campaign_type not in (
        "advertisement",
        "sponsorship",
    ):
        campaign_type = (
            "advertisement"
        )


    status = request.form.get(
        "status",
        "draft"
    )

    if status not in (
        "draft",
        "active",
        "paused",
    ):
        status = "draft"


    try:
        priority = int(
            request.form.get(
                "priority",
                0
            )
        )
    except ValueError:
        priority = 0


    campaign_name = _clean(
        request.form.get(
            "campaign_name"
        ),
        120
    )

    sponsor_name = _clean(
        request.form.get(
            "sponsor_name"
        ),
        120
    )

    headline = _clean(
        request.form.get(
            "headline"
        ),
        160
    )


    if not campaign_name:
        campaign_name = headline

    if not sponsor_name:
        sponsor_name = "Sponsor"

    if not headline:
        headline = campaign_name


    description = _clean(
        request.form.get(
            "description"
        ),
        600
    )

    badge_text = _clean(
        request.form.get(
            "badge_text"
        )
        or "Sponsored",
        50
    )

    cta_text = _clean(
        request.form.get(
            "cta_text"
        )
        or "Learn more",
        50
    )


    logo_url = _safe_http_url(
        request.form.get(
            "logo_url"
        )
    )

    image_url = _safe_http_url(
        request.form.get(
            "image_url"
        )
    )

    destination_url = (
        _safe_http_url(
            request.form.get(
                "destination_url"
            )
        )
    )


    start_at = _clean(
        request.form.get(
            "start_at"
        ),
        40
    )

    end_at = _clean(
        request.form.get(
            "end_at"
        ),
        40
    )


    conn = _connect()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT id
        FROM sponsored_campaigns
        WHERE id=?
        """,
        (
            campaign_id,
        )
    )

    exists = cursor.fetchone()


    if exists:

        cursor.execute(
            """
            UPDATE sponsored_campaigns

            SET
                campaign_type=?,
                campaign_name=?,
                sponsor_name=?,
                headline=?,
                description=?,
                badge_text=?,
                cta_text=?,
                logo_url=?,
                image_url=?,
                destination_url=?,
                placement='dashboard_hero',
                status=?,
                start_at=?,
                end_at=?,
                priority=?,
                updated_at=CURRENT_TIMESTAMP

            WHERE id=?
            """,
            (
                campaign_type,
                campaign_name,
                sponsor_name,
                headline,
                description,
                badge_text,
                cta_text,
                logo_url,
                image_url,
                destination_url,
                status,
                start_at,
                end_at,
                priority,
                campaign_id,
            )
        )


    else:

        cursor.execute(
            """
            INSERT INTO sponsored_campaigns
            (
                id,
                campaign_type,
                campaign_name,
                sponsor_name,
                headline,
                description,
                badge_text,
                cta_text,
                logo_url,
                image_url,
                destination_url,
                placement,
                status,
                start_at,
                end_at,
                priority
            )

            VALUES
            (
                ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                'dashboard_hero',
                ?, ?, ?, ?
            )
            """,
            (
                campaign_id,
                campaign_type,
                campaign_name,
                sponsor_name,
                headline,
                description,
                badge_text,
                cta_text,
                logo_url,
                image_url,
                destination_url,
                status,
                start_at,
                end_at,
                priority,
            )
        )


    conn.commit()
    conn.close()


    return redirect(
        "/admin/ads?saved=1"
    )


# ============================================================
# STATUS
# ============================================================

@admin_ads_bp.route(
    "/admin/ads/status/<campaign_id>",
    methods=["POST"]
)
def admin_ads_status(
    campaign_id
):

    denied = _admin_required()

    if denied:
        return denied


    status = request.form.get(
        "status",
        "paused"
    )


    if status not in (
        "active",
        "paused",
        "draft",
    ):
        status = "paused"


    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE sponsored_campaigns

        SET
            status=?,
            updated_at=CURRENT_TIMESTAMP

        WHERE id=?
        """,
        (
            status,
            campaign_id,
        )
    )

    conn.commit()
    conn.close()


    return redirect(
        "/admin/ads"
    )


# ============================================================
# DELETE
# ============================================================

@admin_ads_bp.route(
    "/admin/ads/delete/<campaign_id>",
    methods=["POST"]
)
def admin_ads_delete(
    campaign_id
):

    denied = _admin_required()

    if denied:
        return denied


    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        DELETE FROM sponsored_campaigns
        WHERE id=?
        """,
        (
            campaign_id,
        )
    )

    conn.commit()
    conn.close()


    return redirect(
        "/admin/ads"
    )


# ============================================================
# PUBLIC DASHBOARD AD API
# ============================================================

@admin_ads_bp.route(
    "/api/dashboard-ad"
)
def dashboard_ad_api():

    if not session.get(
        "user_id"
    ):
        return {
            "ads": []
        }


    now = datetime.utcnow().strftime(
        "%Y-%m-%dT%H:%M"
    )


    conn = _connect()
    cursor = conn.cursor()


    cursor.execute(
        """
        SELECT
            id,
            campaign_type,
            sponsor_name,
            headline,
            description,
            badge_text,
            cta_text,
            logo_url,
            image_url,
            destination_url

        FROM sponsored_campaigns

        WHERE
            placement='dashboard_hero'

            AND status='active'

            AND (
                start_at IS NULL
                OR start_at=''
                OR start_at<=?
            )

            AND (
                end_at IS NULL
                OR end_at=''
                OR end_at>=?
            )

        ORDER BY
            priority DESC,
            created_at DESC

        LIMIT 5
        """,
        (
            now,
            now,
        )
    )


    ads = []

    for row in cursor.fetchall():

        ads.append({
            "id": row[0],
            "campaign_type": row[1],
            "sponsor_name": row[2],
            "headline": row[3],
            "description": row[4] or "",
            "badge_text": row[5] or "Sponsored",
            "cta_text": row[6] or "Learn more",
            "logo_url": row[7] or "",
            "image_url": row[8] or "",
            "destination_url": row[9] or "",
        })


    conn.close()


    return {
        "ads": ads
    }


# ============================================================
# IMPRESSION TRACKING
# ============================================================

@admin_ads_bp.route(
    "/api/sponsored/impression/<campaign_id>",
    methods=["POST"]
)
def sponsored_impression(
    campaign_id
):

    if not session.get(
        "user_id"
    ):
        return {
            "ok": False
        }, 401


    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        UPDATE sponsored_campaigns

        SET impressions =
            COALESCE(
                impressions,
                0
            ) + 1

        WHERE
            id=?
            AND status='active'
        """,
        (
            campaign_id,
        )
    )

    conn.commit()
    conn.close()


    return {
        "ok": True
    }


# ============================================================
# CLICK TRACKING
# ============================================================

@admin_ads_bp.route(
    "/sponsored/click/<campaign_id>"
)
def sponsored_click(
    campaign_id
):

    conn = _connect()
    cursor = conn.cursor()

    cursor.execute(
        """
        SELECT destination_url
        FROM sponsored_campaigns
        WHERE id=?
        """,
        (
            campaign_id,
        )
    )

    row = cursor.fetchone()


    if not row:
        conn.close()

        return redirect(
            "/"
        )


    destination = _safe_http_url(
        row[0]
    )


    cursor.execute(
        """
        UPDATE sponsored_campaigns

        SET clicks =
            COALESCE(
                clicks,
                0
            ) + 1

        WHERE id=?
        """,
        (
            campaign_id,
        )
    )

    conn.commit()
    conn.close()


    if not destination:
        return redirect(
            "/"
        )


    return redirect(
        destination
    )
