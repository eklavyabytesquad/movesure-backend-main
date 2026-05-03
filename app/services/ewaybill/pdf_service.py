"""
E-Way Bill PDF Generator
------------------------
Generates a print-ready black & white PDF for a validated EWB.
Matches the official NIC EWB print layout:
  - Header with QR code (top-right)
  - Section 1: E-Way Bill Details
  - Section 2: Address Details (From / To)
  - Section 3: Goods Details (item table)
  - Section 4: Transportation Details
  - Section 5: Vehicle Details (if present)
  - Barcode (bottom, Code128 on the EWB number)

Usage:
    from app.services.ewaybill.pdf_service import generate_ewb_pdf
    pdf_bytes = generate_ewb_pdf(ewb_data)
    # ewb_data is the `message` dict from the NIC GetEwayBill response
"""

import io
import json
import logging
import qrcode
import barcode as pybarcode
from barcode.writer import ImageWriter

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Table, TableStyle, Paragraph,
    Spacer, Image, HRFlowable,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

logger = logging.getLogger("movesure.ewaybill.pdf")

# ── Page setup ────────────────────────────────────────────────────────────────
PAGE_W, PAGE_H = A4          # 595.27 x 841.89 pts
L_MARGIN = R_MARGIN = 10 * mm
T_MARGIN = B_MARGIN = 10 * mm

# ── Colours ───────────────────────────────────────────────────────────────────
BLACK  = colors.black
WHITE  = colors.white
LIGHT  = colors.Color(0.92, 0.92, 0.92)   # section header fill
BORDER = colors.Color(0.5, 0.5, 0.5)


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("title", parent=base["Normal"],
                                fontSize=13, fontName="Helvetica-Bold",
                                alignment=TA_CENTER),
        "section": ParagraphStyle("section", parent=base["Normal"],
                                  fontSize=7.5, fontName="Helvetica-Bold",
                                  leading=10),
        "cell_bold": ParagraphStyle("cell_bold", parent=base["Normal"],
                                    fontSize=7, fontName="Helvetica-Bold",
                                    leading=9),
        "cell": ParagraphStyle("cell", parent=base["Normal"],
                               fontSize=7, fontName="Helvetica",
                               leading=9),
        "small": ParagraphStyle("small", parent=base["Normal"],
                                fontSize=6, fontName="Helvetica",
                                leading=8),
    }


def _kv_table(rows: list[tuple], col_widths=None, usable_w=None) -> Table:
    """Generic key-value two-column table."""
    usable_w = usable_w or (PAGE_W - L_MARGIN - R_MARGIN)
    col_widths = col_widths or [usable_w * 0.35, usable_w * 0.65]
    S = _styles()
    data = []
    for k, v in rows:
        data.append([
            Paragraph(str(k), S["cell_bold"]),
            Paragraph(str(v) if v is not None else "—", S["cell"]),
        ])
    t = Table(data, colWidths=col_widths)
    t.setStyle(TableStyle([
        ("GRID",       (0, 0), (-1, -1), 0.4, BORDER),
        ("VALIGN",     (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING",(0, 0), (-1, -1), 3),
        ("RIGHTPADDING",(0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    return t


def _section_header(title: str, usable_w: float) -> Table:
    S = _styles()
    t = Table([[Paragraph(title, S["section"])]], colWidths=[usable_w])
    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, -1), LIGHT),
        ("GRID",         (0, 0), (-1, -1), 0.4, BORDER),
        ("LEFTPADDING",  (0, 0), (-1, -1), 4),
        ("TOPPADDING",   (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    return t


def _qr_image(data: str, size_mm: float = 28) -> Image:
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=4, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    size_pt = size_mm * mm
    return Image(buf, width=size_pt, height=size_pt)


def _barcode_image(text: str, width_mm: float = 80, height_mm: float = 14) -> Image:
    """Render a Code128 barcode as PNG via python-barcode and return a ReportLab Image."""
    CODE128 = pybarcode.get_barcode_class("code128")
    buf = io.BytesIO()
    writer_opts = {
        "module_height": 8.0,
        "module_width": 0.22,
        "font_size": 6,
        "text_distance": 2.5,
        "quiet_zone": 2.0,
        "write_text": True,
        "background": "white",
        "foreground": "black",
    }
    CODE128(text, writer=ImageWriter()).write(buf, options=writer_opts)
    buf.seek(0)
    return Image(buf, width=width_mm * mm, height=height_mm * mm)


def _fmt(val, default="—"):
    return str(val) if val not in (None, "", 0, 0.0) else default


def _addr(name, addr1, addr2, place, state, pin) -> str:
    parts = [p for p in [name, addr1, addr2, place, state, str(pin) if pin else ""] if p]
    return ", ".join(parts)


# ─────────────────────────────────────────────────────────────────────────────
# Main public function
# ─────────────────────────────────────────────────────────────────────────────

def generate_ewb_pdf(ewb_message: dict) -> bytes:
    """
    Build PDF bytes from the NIC EWB `message` dict.

    Args:
        ewb_message: The `message` object from NIC GetEwayBill results,
                     which is also stored as raw_response in ewb_records.

    Returns:
        PDF file as bytes — stream directly or save to disk.
    """
    buf = io.BytesIO()
    usable_w = PAGE_W - L_MARGIN - R_MARGIN
    S = _styles()

    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=L_MARGIN, rightMargin=R_MARGIN,
        topMargin=T_MARGIN, bottomMargin=B_MARGIN,
    )

    ewb_number = str(ewb_message.get("eway_bill_number", ""))
    story = []

    # ── Title row (text left, QR right) ──────────────────────────────────────
    qr_data = json.dumps({
        "ewb": ewb_number,
        "date": ewb_message.get("eway_bill_date", ""),
        "valid": ewb_message.get("eway_bill_valid_date", ""),
        "status": ewb_message.get("eway_bill_status", ""),
    })
    qr_img = _qr_image(qr_data, size_mm=26)

    title_data = [[
        Paragraph("e-Way Bill", S["title"]),
        qr_img,
    ]]
    title_table = Table(title_data, colWidths=[usable_w - 28 * mm, 28 * mm])
    title_table.setStyle(TableStyle([
        ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN",   (0, 0), (0, 0),   "CENTER"),
        ("ALIGN",   (1, 0), (1, 0),   "RIGHT"),
        ("TOPPADDING",  (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    story.append(title_table)
    story.append(HRFlowable(width="100%", thickness=1, color=BLACK, spaceAfter=2))

    # ── Section 1: EWB Details ────────────────────────────────────────────────
    story.append(_section_header("1. E-WAY BILL Details", usable_w))

    half = usable_w / 2
    left_rows = [
        ("eWay Bill No",     _fmt(ewb_number)),
        ("Mode",             _fmt(ewb_message.get("VehiclListDetails", [{}])[0].get("transportation_mode") if ewb_message.get("VehiclListDetails") else ewb_message.get("transportation_mode"))),
        ("Type",             f"{_fmt(ewb_message.get('supply_type'))} - {_fmt(ewb_message.get('sub_supply_type'))}"),
    ]
    right_rows = [
        ("Generated Date",   _fmt(ewb_message.get("eway_bill_date"))),
        ("Approx Distance",  f"{_fmt(ewb_message.get('transportation_distance'))} Kms"),
        ("Document Details", f"{_fmt(ewb_message.get('document_type'))} {_fmt(ewb_message.get('document_number'))} {_fmt(ewb_message.get('document_date'))}"),
    ]
    more_left = [
        ("Generated By",     _fmt(ewb_message.get("userGstin"))),
        ("Transaction type", _fmt(ewb_message.get("transaction_type"))),
    ]
    more_right = [
        ("Valid Upto",       _fmt(ewb_message.get("eway_bill_valid_date"))),
        ("EWB Status",       _fmt(ewb_message.get("eway_bill_status"))),
    ]

    def _side_table(rows, w):
        data = [[Paragraph(k, S["cell_bold"]), Paragraph(v, S["cell"])] for k, v in rows]
        t = Table(data, colWidths=[w * 0.38, w * 0.62])
        t.setStyle(TableStyle([
            ("GRID",        (0, 0), (-1, -1), 0.4, BORDER),
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING",(0, 0), (-1, -1), 3),
            ("TOPPADDING",  (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ]))
        return t

    sec1_top = Table(
        [[_side_table(left_rows, half), _side_table(right_rows, half)]],
        colWidths=[half, half],
    )
    sec1_top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(sec1_top)

    sec1_bot = Table(
        [[_side_table(more_left, half), _side_table(more_right, half)]],
        colWidths=[half, half],
    )
    sec1_bot.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    story.append(sec1_bot)

    # ── Section 2: Address Details ────────────────────────────────────────────
    story.append(Spacer(1, 2))
    story.append(_section_header("2. Address Details", usable_w))

    from_gstin = _fmt(ewb_message.get("gstin_of_consignor"))
    from_name  = _fmt(ewb_message.get("legal_name_of_consignor"))
    from_addr  = _addr(
        ewb_message.get("legal_name_of_consignor"),
        ewb_message.get("address1_of_consignor"),
        ewb_message.get("address2_of_consignor"),
        ewb_message.get("place_of_consignor"),
        ewb_message.get("state_of_consignor"),
        ewb_message.get("pincode_of_consignor"),
    )
    to_gstin = _fmt(ewb_message.get("gstin_of_consignee"))
    to_addr  = _addr(
        ewb_message.get("legal_name_of_consignee"),
        ewb_message.get("address1_of_consignee"),
        ewb_message.get("address2_of_consignee"),
        ewb_message.get("place_of_consignee"),
        ewb_message.get("state_of_supply"),
        ewb_message.get("pincode_of_consignee"),
    )

    addr_data = [
        [Paragraph("From", S["cell_bold"]), Paragraph("To", S["cell_bold"])],
        [
            Paragraph(f"GSTIN {from_gstin}<br/>{from_name}<br/><br/><i>Dispatch From:</i><br/>{from_addr}", S["cell"]),
            Paragraph(f"GSTIN {to_gstin}<br/><br/><i>Ship To:</i><br/>{to_addr}", S["cell"]),
        ],
    ]
    addr_table = Table(addr_data, colWidths=[half, half])
    addr_table.setStyle(TableStyle([
        ("GRID",        (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND",  (0, 0), (-1, 0),  LIGHT),
        ("ALIGN",       (0, 0), (-1, 0),  "CENTER"),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING",(0, 0), (-1, -1), 4),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
    ]))
    story.append(addr_table)

    # ── Section 3: Goods Details ──────────────────────────────────────────────
    story.append(Spacer(1, 2))
    story.append(_section_header("3. Goods Details", usable_w))

    item_list = ewb_message.get("itemList", [])
    goods_header = [
        Paragraph("HSN Code", S["cell_bold"]),
        Paragraph("Product Description", S["cell_bold"]),
        Paragraph("Quantity UOM", S["cell_bold"]),
        Paragraph("Taxable Amount Rs.", S["cell_bold"]),
        Paragraph("Tax rate (C+S+I+Cess+Cess Non.Advol)", S["cell_bold"]),
    ]
    goods_rows = [goods_header]
    for item in item_list:
        desc = item.get("product_description") or item.get("product_name") or "—"
        tax  = f"{item.get('cgst_rate',0)}+{item.get('sgst_rate',0)}+{item.get('igst_rate',0)}+{item.get('cess_rate',0)}+{item.get('cessNonAdvol',0)}"
        goods_rows.append([
            Paragraph(_fmt(item.get("hsn_code")), S["cell"]),
            Paragraph(desc, S["cell"]),
            Paragraph(f"{_fmt(item.get('quantity'))} {_fmt(item.get('unit_of_product'))}", S["cell"]),
            Paragraph(_fmt(item.get("taxable_amount")), S["cell"]),
            Paragraph(tax, S["cell"]),
        ])

    # Totals row
    goods_rows.append([
        Paragraph("", S["cell"]),
        Paragraph("", S["cell"]),
        Paragraph("", S["cell"]),
        Paragraph("", S["cell"]),
        Paragraph("", S["cell"]),
    ])

    cw = usable_w
    goods_col_w = [cw*0.12, cw*0.36, cw*0.14, cw*0.19, cw*0.19]
    goods_table = Table(goods_rows, colWidths=goods_col_w, repeatRows=1)
    goods_table.setStyle(TableStyle([
        ("GRID",        (0, 0), (-1, -1), 0.4, BORDER),
        ("BACKGROUND",  (0, 0), (-1, 0),  LIGHT),
        ("VALIGN",      (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING",(0, 0), (-1, -1), 3),
        ("TOPPADDING",  (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
    ]))
    story.append(goods_table)

    # Totals summary line
    total_taxable = _fmt(ewb_message.get("taxable_amount"))
    cgst  = _fmt(ewb_message.get("cgst_amount"))
    sgst  = _fmt(ewb_message.get("sgst_amount"))
    igst  = _fmt(ewb_message.get("igst_amount"))
    cess  = _fmt(ewb_message.get("cess_amount"))
    other = _fmt(ewb_message.get("other_value"))
    total_inv = _fmt(ewb_message.get("total_invoice_value"))
    summary_text = (
        f"Total Taxable Amount : {total_taxable}    "
        f"CGST Amount : {cgst}    SGST Amount : {sgst}    "
        f"IGST Amount : {igst}    CESS Amount : {cess}    "
        f"Cess Non.Advol Amt : 0    Other Amt : {other}    "
        f"Total Inv. Amt : {total_inv}"
    )
    story.append(Paragraph(summary_text, S["small"]))

    # ── Section 4: Transportation Details ────────────────────────────────────
    story.append(Spacer(1, 2))
    story.append(_section_header("4. Transportation Details", usable_w))

    trans_id   = _fmt(ewb_message.get("transporter_id"))
    trans_name = _fmt(ewb_message.get("transporter_name"))
    trans_rows = [
        ("Transporter Id & Name", f"{trans_id} & {trans_name}"),
        ("Transporter Doc. No & Date", "—"),
    ]
    # If vehicle list has doc info
    vlist = ewb_message.get("VehiclListDetails", [])
    if vlist:
        v0 = vlist[0]
        doc_no   = v0.get("transporter_document_number") or "—"
        doc_date = v0.get("transporter_document_date") or "—"
        trans_rows[1] = ("Transporter Doc. No & Date", f"{doc_no} & {doc_date}")

    trans_table = _kv_table(trans_rows, usable_w=usable_w)
    story.append(trans_table)

    # ── Section 5: Vehicle Details ────────────────────────────────────────────
    if vlist:
        story.append(Spacer(1, 2))
        story.append(_section_header("5. Vehicle Details", usable_w))

        veh_header = [
            Paragraph("Mode", S["cell_bold"]),
            Paragraph("Vehicle/Trans Doc No & Dt", S["cell_bold"]),
            Paragraph("From", S["cell_bold"]),
            Paragraph("Entered Date", S["cell_bold"]),
            Paragraph("Entered By", S["cell_bold"]),
            Paragraph("CEWB No\n(If any)", S["cell_bold"]),
            Paragraph("Multi Veh.Info\n(If any)", S["cell_bold"]),
        ]
        veh_rows = [veh_header]
        for v in vlist:
            veh_rows.append([
                Paragraph(_fmt(v.get("transportation_mode")), S["cell"]),
                Paragraph(_fmt(v.get("vehicle_number")), S["cell"]),
                Paragraph(_fmt(v.get("place_of_consignor")), S["cell"]),
                Paragraph(_fmt(v.get("vehicle_number_update_date")), S["cell"]),
                Paragraph(_fmt(v.get("userGstin")), S["cell"]),
                Paragraph("—", S["cell"]),
                Paragraph("—", S["cell"]),
            ])
        vcw = usable_w
        veh_col_w = [vcw*0.09, vcw*0.18, vcw*0.13, vcw*0.20, vcw*0.20, vcw*0.10, vcw*0.10]
        veh_table = Table(veh_rows, colWidths=veh_col_w, repeatRows=1)
        veh_table.setStyle(TableStyle([
            ("GRID",        (0, 0), (-1, -1), 0.4, BORDER),
            ("BACKGROUND",  (0, 0), (-1, 0),  LIGHT),
            ("VALIGN",      (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING",(0, 0), (-1, -1), 3),
            ("TOPPADDING",  (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 2),
        ]))
        story.append(veh_table)

    # ── Barcode (bottom) ──────────────────────────────────────────────────────
    story.append(Spacer(1, 6))
    story.append(HRFlowable(width="100%", thickness=0.5, color=BORDER, spaceAfter=4))
    if ewb_number:
        bc_img = _barcode_image(ewb_number, width_mm=100, height_mm=14)
        bc_table = Table([[bc_img]], colWidths=[usable_w])
        bc_table.setStyle(TableStyle([
            ("ALIGN",  (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ]))
        story.append(bc_table)

    doc.build(story)
    return buf.getvalue()


def generate_ewb_pdf_from_record(raw_response: dict) -> bytes:
    """
    Convenience wrapper when the input is the full API response
    (with results.message nesting) as stored in ewb_records.raw_response.
    """
    # Handle both flat message and nested results.message structure
    if "results" in raw_response:
        msg = raw_response["results"].get("message", raw_response)
    elif "message" in raw_response and isinstance(raw_response["message"], dict):
        msg = raw_response["message"]
    else:
        msg = raw_response
    return generate_ewb_pdf(msg)
