from io import BytesIO
from html import escape
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    HRFlowable,
)


ACCENTS = {
    "slate": "#526779",
    "blue": "#55758F",
    "sage": "#607D6E",
    "copper": "#916E55",
    "plum": "#76647E",
}


def _safe(value):
    return escape(str(value or ""))


def _money(value):
    try:
        return f"Rs. {float(value):,.2f}"
    except (TypeError, ValueError):
        return "Rs. 0.00"


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_invoice(items, tax_percent, discount, extra):
    subtotal = 0.0

    normalized = []

    for item in items:
        description = str(
            item.get("description") or "Item"
        ).strip()

        quantity = max(
            _number(item.get("quantity"), 1),
            0
        )

        rate = max(
            _number(item.get("rate"), 0),
            0
        )

        line_total = quantity * rate

        subtotal += line_total

        normalized.append({
            "description": description,
            "quantity": quantity,
            "rate": rate,
            "total": line_total,
        })

    tax_percent = max(
        _number(tax_percent),
        0
    )

    discount = max(
        _number(discount),
        0
    )

    extra = max(
        _number(extra),
        0
    )

    tax_amount = (
        subtotal *
        tax_percent /
        100
    )

    total = (
        subtotal
        + tax_amount
        + extra
        - discount
    )

    total = max(total, 0)

    return {
        "items": normalized,
        "subtotal": subtotal,
        "tax_percent": tax_percent,
        "tax_amount": tax_amount,
        "discount": discount,
        "extra": extra,
        "total": total,
    }


def build_bill_invoice_pdf(
    bill,
    user,
    settings
):
    """
    bill:
      {
        id, name, amount, category,
        due_date, recurrence, status,
        paid_date
      }

    user:
      {
        username, email
      }
    """

    accent_hex = ACCENTS.get(
        settings.get("accent"),
        ACCENTS["slate"]
    )

    accent = colors.HexColor(
        accent_hex
    )

    dark = colors.HexColor(
        "#1B232B"
    )

    muted = colors.HexColor(
        "#6B7680"
    )

    border = colors.HexColor(
        "#DCE1E5"
    )

    soft = colors.HexColor(
        "#F5F7F8"
    )

    calculation = calculate_invoice(
        settings.get("items", []),
        settings.get("tax_percent", 0),
        settings.get("discount_amount", 0),
        settings.get("extra_charges", 0),
    )

    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=17 * mm,
        leftMargin=17 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=str(
            settings.get(
                "document_title",
                "Invoice"
            )
        ),
        author="Expense Manager",
    )

    title_style = ParagraphStyle(
        "InvoiceTitle",
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=28,
        textColor=dark,
        alignment=TA_RIGHT,
    )

    invoice_number_style = ParagraphStyle(
        "InvoiceNumber",
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=muted,
        alignment=TA_RIGHT,
    )

    company_style = ParagraphStyle(
        "Company",
        fontName="Helvetica-Bold",
        fontSize=15,
        leading=18,
        textColor=dark,
        alignment=TA_LEFT,
    )

    small_style = ParagraphStyle(
        "Small",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=muted,
        alignment=TA_LEFT,
    )

    label_style = ParagraphStyle(
        "Label",
        fontName="Helvetica-Bold",
        fontSize=7.5,
        leading=10,
        textColor=accent,
        spaceAfter=4,
    )

    normal_style = ParagraphStyle(
        "NormalInvoice",
        fontName="Helvetica",
        fontSize=9.5,
        leading=13,
        textColor=dark,
    )

    note_style = ParagraphStyle(
        "Notes",
        fontName="Helvetica",
        fontSize=8.5,
        leading=12,
        textColor=muted,
    )

    total_label_style = ParagraphStyle(
        "TotalLabel",
        fontName="Helvetica-Bold",
        fontSize=9,
        textColor=dark,
        alignment=TA_RIGHT,
    )

    total_value_style = ParagraphStyle(
        "TotalValue",
        fontName="Helvetica-Bold",
        fontSize=16,
        textColor=accent,
        alignment=TA_RIGHT,
    )

    story = []

    # ======================================================
    # HEADER
    # ======================================================

    company_lines = []

    if settings.get("business_email"):
        company_lines.append(
            _safe(
                settings["business_email"]
            )
        )

    if settings.get("business_phone"):
        company_lines.append(
            _safe(
                settings["business_phone"]
            )
        )

    if settings.get("business_address"):
        company_lines.append(
            _safe(
                settings["business_address"]
            ).replace("\n", "<br/>")
        )

    company_info = "<br/>".join(
        company_lines
    )

    header = Table(
        [
            [
                [
                    Paragraph(
                        _safe(
                            settings.get(
                                "business_name"
                            )
                            or "Expense Manager"
                        ),
                        company_style,
                    ),
                    Spacer(1, 2 * mm),
                    Paragraph(
                        company_info,
                        small_style,
                    ),
                ],
                [
                    Paragraph(
                        _safe(
                            settings.get(
                                "document_title"
                            )
                            or "INVOICE"
                        ).upper(),
                        title_style,
                    ),
                    Spacer(1, 2 * mm),
                    Paragraph(
                        "No. "
                        + _safe(
                            settings.get(
                                "invoice_number"
                            )
                            or (
                                f"INV-"
                                f"{bill['id']:05d}"
                            )
                        ),
                        invoice_number_style,
                    ),
                ],
            ]
        ],
        colWidths=[
            95 * mm,
            78 * mm,
        ],
    )

    header.setStyle(
        TableStyle([
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
        ])
    )

    story.append(header)

    story.append(
        Spacer(
            1,
            6 * mm
        )
    )

    story.append(
        HRFlowable(
            width="100%",
            thickness=2,
            color=accent,
        )
    )

    story.append(
        Spacer(
            1,
            6 * mm
        )
    )

    # ======================================================
    # BILL TO / META
    # ======================================================

    bill_to = [
        Paragraph(
            "BILL TO",
            label_style,
        ),
        Paragraph(
            "<b>"
            + _safe(
                settings.get(
                    "bill_to_name"
                )
                or user.get(
                    "username"
                )
                or "Customer"
            )
            + "</b>",
            normal_style,
        ),
    ]

    if settings.get("bill_to_email"):
        bill_to.append(
            Paragraph(
                _safe(
                    settings[
                        "bill_to_email"
                    ]
                ),
                small_style,
            )
        )

    if settings.get("bill_to_address"):
        bill_to.append(
            Paragraph(
                _safe(
                    settings[
                        "bill_to_address"
                    ]
                ).replace(
                    "\n",
                    "<br/>"
                ),
                small_style,
            )
        )

    meta = [
        [
            "Issue date",
            settings.get(
                "issue_date"
            )
            or bill.get(
                "paid_date"
            )
            or bill.get(
                "due_date"
            ),
        ],
        [
            "Due date",
            bill.get(
                "due_date"
            ),
        ],
        [
            "Category",
            bill.get(
                "category"
            ),
        ],
        [
            "Payment",
            settings.get(
                "payment_method"
            )
            or (
                "Completed"
                if bill.get(
                    "status"
                ) == "paid"
                else "Pending"
            ),
        ],
    ]

    meta_rows = []

    for key, value in meta:
        meta_rows.append([
            Paragraph(
                _safe(key),
                small_style,
            ),
            Paragraph(
                "<b>"
                + _safe(value)
                + "</b>",
                normal_style,
            ),
        ])

    meta_table = Table(
        meta_rows,
        colWidths=[
            26 * mm,
            48 * mm,
        ],
    )

    meta_table.setStyle(
        TableStyle([
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                3,
            ),
        ])
    )

    info = Table(
        [[bill_to, meta_table]],
        colWidths=[
            99 * mm,
            74 * mm,
        ],
    )

    info.setStyle(
        TableStyle([
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
        ])
    )

    story.append(info)

    story.append(
        Spacer(
            1,
            8 * mm
        )
    )

    # ======================================================
    # ITEMS
    # ======================================================

    item_rows = [
        [
            "DESCRIPTION",
            "QTY",
            "RATE",
            "AMOUNT",
        ]
    ]

    for item in calculation[
        "items"
    ]:
        item_rows.append([
            Paragraph(
                _safe(
                    item[
                        "description"
                    ]
                ),
                normal_style,
            ),
            f"{item['quantity']:g}",
            _money(
                item["rate"]
            ),
            _money(
                item["total"]
            ),
        ])

    item_table = Table(
        item_rows,
        colWidths=[
            89 * mm,
            18 * mm,
            31 * mm,
            35 * mm,
        ],
        repeatRows=1,
    )

    item_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, 0),
                dark,
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, 0),
                colors.white,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, 0),
                "Helvetica-Bold",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, 0),
                8,
            ),
            (
                "ALIGN",
                (1, 0),
                (-1, -1),
                "RIGHT",
            ),
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "MIDDLE",
            ),
            (
                "ROWBACKGROUNDS",
                (0, 1),
                (-1, -1),
                [
                    colors.white,
                    soft,
                ],
            ),
            (
                "TEXTCOLOR",
                (0, 1),
                (-1, -1),
                dark,
            ),
            (
                "FONTNAME",
                (0, 1),
                (-1, -1),
                "Helvetica",
            ),
            (
                "FONTSIZE",
                (0, 1),
                (-1, -1),
                9,
            ),
            (
                "LINEBELOW",
                (0, 1),
                (-1, -2),
                .35,
                border,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                9,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                9,
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                8,
            ),
        ])
    )

    story.append(
        item_table
    )

    story.append(
        Spacer(
            1,
            6 * mm
        )
    )

    # ======================================================
    # TOTALS
    # ======================================================

    totals = [
        [
            "Subtotal",
            _money(
                calculation[
                    "subtotal"
                ]
            ),
        ]
    ]

    if calculation[
        "tax_percent"
    ] > 0:
        totals.append([
            (
                "Tax "
                f"({calculation['tax_percent']:g}%)"
            ),
            _money(
                calculation[
                    "tax_amount"
                ]
            ),
        ])

    if calculation[
        "discount"
    ] > 0:
        totals.append([
            "Discount",
            "- "
            + _money(
                calculation[
                    "discount"
                ]
            ),
        ])

    if calculation[
        "extra"
    ] > 0:
        totals.append([
            "Additional charges",
            _money(
                calculation[
                    "extra"
                ]
            ),
        ])

    totals.append([
        Paragraph(
            "TOTAL",
            total_label_style,
        ),
        Paragraph(
            _money(
                calculation[
                    "total"
                ]
            ),
            total_value_style,
        ),
    ])

    totals_table = Table(
        totals,
        colWidths=[
            40 * mm,
            43 * mm,
        ],
    )

    totals_table.setStyle(
        TableStyle([
            (
                "ALIGN",
                (0, 0),
                (-1, -1),
                "RIGHT",
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -2),
                muted,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, -2),
                "Helvetica",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -2),
                9,
            ),
            (
                "LINEABOVE",
                (0, -1),
                (-1, -1),
                1.2,
                accent,
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                5,
            ),
        ])
    )

    totals_wrapper = Table(
        [["", totals_table]],
        colWidths=[
            90 * mm,
            83 * mm,
        ],
    )

    totals_wrapper.setStyle(
        TableStyle([
            (
                "VALIGN",
                (0, 0),
                (-1, -1),
                "TOP",
            ),
            (
                "LEFTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
            (
                "RIGHTPADDING",
                (0, 0),
                (-1, -1),
                0,
            ),
        ])
    )

    story.append(
        totals_wrapper
    )

    story.append(
        Spacer(
            1,
            7 * mm
        )
    )

    # ======================================================
    # STATUS
    # ======================================================

    is_paid = (
        bill.get(
            "status"
        )
        == "paid"
    )

    status_bg = (
        colors.HexColor(
            "#E7F1EB"
        )
        if is_paid
        else colors.HexColor(
            "#F3EEE7"
        )
    )

    status_text = (
        colors.HexColor(
            "#456855"
        )
        if is_paid
        else colors.HexColor(
            "#806A50"
        )
    )

    status_label = (
        "PAYMENT COMPLETED"
        if is_paid
        else "PAYMENT PENDING"
    )

    status_table = Table(
        [[status_label]],
        colWidths=[
            173 * mm
        ],
    )

    status_table.setStyle(
        TableStyle([
            (
                "BACKGROUND",
                (0, 0),
                (-1, -1),
                status_bg,
            ),
            (
                "TEXTCOLOR",
                (0, 0),
                (-1, -1),
                status_text,
            ),
            (
                "FONTNAME",
                (0, 0),
                (-1, -1),
                "Helvetica-Bold",
            ),
            (
                "FONTSIZE",
                (0, 0),
                (-1, -1),
                9,
            ),
            (
                "ALIGN",
                (0, 0),
                (-1, -1),
                "CENTER",
            ),
            (
                "TOPPADDING",
                (0, 0),
                (-1, -1),
                9,
            ),
            (
                "BOTTOMPADDING",
                (0, 0),
                (-1, -1),
                9,
            ),
        ])
    )

    story.append(
        status_table
    )

    # ======================================================
    # NOTES
    # ======================================================

    if settings.get("notes"):
        story.append(
            Spacer(
                1,
                7 * mm
            )
        )

        story.append(
            Paragraph(
                "NOTES",
                label_style,
            )
        )

        story.append(
            Paragraph(
                _safe(
                    settings[
                        "notes"
                    ]
                ).replace(
                    "\n",
                    "<br/>"
                ),
                note_style,
            )
        )

    story.append(
        Spacer(
            1,
            9 * mm
        )
    )

    story.append(
        HRFlowable(
            width="100%",
            thickness=.6,
            color=border,
        )
    )

    story.append(
        Spacer(
            1,
            4 * mm
        )
    )

    footer_text = (
        settings.get(
            "footer_text"
        )
        or
        (
            "Generated by Expense Manager. "
            "This document is computer generated."
        )
    )

    footer_style = ParagraphStyle(
        "InvoiceFooter",
        fontName="Helvetica",
        fontSize=7.5,
        leading=10,
        textColor=colors.HexColor(
            "#9099A1"
        ),
        alignment=TA_CENTER,
    )

    story.append(
        Paragraph(
            _safe(
                footer_text
            ),
            footer_style,
        )
    )

    doc.build(
        story
    )

    buffer.seek(0)

    raw_name = str(
        settings.get(
            "invoice_number"
        )
        or
        f"INV-{bill['id']:05d}"
    )

    safe_name = re.sub(
        r"[^A-Za-z0-9_-]+",
        "_",
        raw_name
    ).strip("_")

    filename = (
        f"{safe_name or 'invoice'}.pdf"
    )

    return (
        buffer,
        filename,
        calculation,
    )
