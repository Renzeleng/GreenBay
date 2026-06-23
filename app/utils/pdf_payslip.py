"""
PDF payslip generator using ReportLab.
Thesis reference: Chapter III – Payslip generation, Table 3.3.
Produces itemized payslips accessible to individual staff through the portal.
"""

import io
import os
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Table, TableStyle,
                                  Paragraph, Spacer, HRFlowable, Image)
from reportlab.lib.enums import TA_CENTER, TA_RIGHT, TA_LEFT
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ReportLab's built-in "Helvetica" is one of the 14 standard PDF fonts and
# does NOT include the Peso sign (₱, U+20B1) glyph — it renders as a solid
# black box (the universal "missing glyph" placeholder) instead.
# Liberation Sans is a metric-compatible open-source equivalent of Arial
# (same look, same spacing) that DOES include the Peso sign, so payslips
# keep a familiar, professional default-font appearance while actually
# rendering currency correctly.
_LIBERATION_DIR = '/usr/share/fonts/truetype/liberation'
_FONT_REGULAR = 'LiberationSans'
_FONT_BOLD = 'LiberationSans-Bold'

try:
    pdfmetrics.registerFont(TTFont(_FONT_REGULAR, os.path.join(_LIBERATION_DIR, 'LiberationSans-Regular.ttf')))
    pdfmetrics.registerFont(TTFont(_FONT_BOLD, os.path.join(_LIBERATION_DIR, 'LiberationSans-Bold.ttf')))
    _BASE_FONT = _FONT_REGULAR
    _BOLD_FONT = _FONT_BOLD
except Exception:
    # Fall back to standard fonts if Liberation isn't available in this
    # environment — the peso sign will show as a box, but the PDF will
    # still generate rather than crash.
    _BASE_FONT = 'Helvetica'
    _BOLD_FONT = 'Helvetica-Bold'

# Clinic branding
CLINIC_NAME    = "Green Bay Pediatric Therapy Center"
CLINIC_ADDRESS = "2F Regency House, Chinatown Highway, Purok Poticar, Brgy. 9506, General Santos City"
CLINIC_CONTACT = "greenbay.ptc@email.com"
LOGO_PATH = os.path.join(os.path.dirname(__file__), '..', 'static', 'branding', 'logo_cropped.png')

# Palette sampled directly from the actual Green Bay logo artwork
TEAL    = colors.HexColor('#3F6B63')   # dark tree shape / wordmark
SAGE    = colors.HexColor('#B0CA8B')   # canopy shape / wordmark
ACCENT  = colors.HexColor('#D36F34')   # hand outline — their real recurring accent
LTEAL   = colors.HexColor('#E7EFEA')
GRAY    = colors.HexColor('#F7F4ED')
DKGRAY  = colors.HexColor('#3A352E')


def _peso(value: float) -> str:
    return f"₱{value:,.2f}"


def generate_payslip_pdf(payroll: dict, staff: dict) -> bytes:
    """
    Generate a PDF payslip and return bytes.

    :param payroll: dict from payroll table row
    :param staff:   dict from staff table row (joined with user)
    :returns: PDF bytes
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
    )

    styles = getSampleStyleSheet()
    # Every style below inherits from styles['Normal'] / styles['Heading1'],
    # so overriding the base stylesheet's fonts here means the Peso sign
    # renders correctly everywhere, not just in spots we remembered to set
    # fontName explicitly.
    styles['Normal'].fontName = _BASE_FONT
    styles['Heading1'].fontName = _BOLD_FONT
    styles['Heading2'].fontName = _BOLD_FONT

    title_style = ParagraphStyle(
        'Title', parent=styles['Heading1'],
        fontSize=16, textColor=TEAL, alignment=TA_CENTER, spaceAfter=2
    )
    subtitle_style = ParagraphStyle(
        'Sub', parent=styles['Normal'],
        fontSize=9, textColor=DKGRAY, alignment=TA_CENTER, spaceAfter=4
    )
    section_style = ParagraphStyle(
        'Section', parent=styles['Normal'],
        fontSize=9, textColor=colors.white, backColor=TEAL,
        leftIndent=4, rightIndent=4, spaceAfter=2, spaceBefore=6,
        leading=14, fontName=_BOLD_FONT
    )
    label_style = ParagraphStyle(
        'Label', parent=styles['Normal'],
        fontSize=9, textColor=DKGRAY
    )
    value_style = ParagraphStyle(
        'Value', parent=styles['Normal'],
        fontSize=9, textColor=DKGRAY, alignment=TA_RIGHT
    )
    bold_style = ParagraphStyle(
        'Bold', parent=styles['Normal'],
        fontSize=9, fontName=_BOLD_FONT
    )
    total_style = ParagraphStyle(
        'Total', parent=styles['Normal'],
        fontSize=11, fontName=_BOLD_FONT, textColor=TEAL, alignment=TA_RIGHT
    )

    elements = []

    # ------- Header -------
    try:
        logo_w = 1.6 * cm
        logo_h = logo_w * (971 / 812)  # preserve the cropped logo's aspect ratio
        logo_img = Image(LOGO_PATH, width=logo_w, height=logo_h)
        logo_img.hAlign = 'CENTER'
        elements.append(logo_img)
        elements.append(Spacer(1, 0.15 * cm))
    except Exception:
        pass  # if the logo file is ever missing, the text header alone still works
    elements.append(Paragraph(CLINIC_NAME, title_style))
    elements.append(Paragraph(CLINIC_ADDRESS, subtitle_style))
    elements.append(Paragraph(CLINIC_CONTACT, subtitle_style))
    elements.append(HRFlowable(width="100%", thickness=2, color=TEAL))
    elements.append(Spacer(1, 0.3 * cm))
    elements.append(Paragraph("PAYSLIP", ParagraphStyle(
        'PS', parent=styles['Heading2'], fontSize=13, alignment=TA_CENTER,
        textColor=TEAL, spaceAfter=4
    )))

    # ------- Employee Info -------
    period_start = payroll.get('pay_period_start', '')
    period_end   = payroll.get('pay_period_end', '')
    issued_at    = payroll.get('issued_at') or datetime.utcnow().strftime('%Y-%m-%d')

    emp_data = [
        [Paragraph('<b>Employee Name</b>', label_style),
         Paragraph(f"{staff.get('first_name','')} {staff.get('last_name','')}", label_style),
         Paragraph('<b>Pay Period</b>', label_style),
         Paragraph(f"{period_start} – {period_end}", label_style)],
        [Paragraph('<b>Position</b>', label_style),
         Paragraph(staff.get('position', '—'), label_style),
         Paragraph('<b>Date Issued</b>', label_style),
         Paragraph(str(issued_at)[:10], label_style)],
        [Paragraph('<b>Date Hired</b>', label_style),
         Paragraph(str(staff.get('date_hired') or '—'), label_style),
         Paragraph('<b>Employment Type</b>', label_style),
         Paragraph(staff.get('employment_type', '—').replace('_', ' ').title(), label_style)],
    ]

    emp_table = Table(emp_data, colWidths=[3.5 * cm, 6 * cm, 3.5 * cm, 5 * cm])
    emp_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), GRAY),
        ('GRID',       (0, 0), (-1, -1), 0.5, colors.white),
        ('ROWBACKGROUNDS', (0, 0), (-1, -1), [GRAY, colors.white]),
        ('TOPPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',  (0, 0), (-1, -1), 6),
    ]))
    elements.append(emp_table)
    elements.append(Spacer(1, 0.4 * cm))

    # ------- Earnings -------
    elements.append(Paragraph("  EARNINGS", section_style))
    earnings_data = [
        ['Description', 'Days Worked', 'Rate', 'Amount'],
        ['Basic Salary',
         f"{payroll.get('total_days_worked', 0):.1f} days",
         f"₱{staff.get('monthly_rate', 0):,.2f}/mo" if float(staff.get('monthly_rate', 0)) > 0
            else f"₱{staff.get('daily_rate', 0):,.2f}/day",
         _peso(payroll.get('gross_pay', 0) - payroll.get('allowances', 0))],
    ]
    if float(payroll.get('allowances', 0)) > 0:
        earnings_data.append([
            f"Allowances ({payroll.get('allowances_note', '') or 'Other'})",
            '—', '—', _peso(payroll['allowances'])
        ])
    earnings_data.append(['', '', Paragraph('<b>GROSS PAY</b>', bold_style),
                           Paragraph(_peso(payroll.get('gross_pay', 0)), total_style)])

    earn_table = Table(earnings_data,
                       colWidths=[7 * cm, 4.5 * cm, 3.5 * cm, 3.5 * cm])
    earn_table.setStyle(TableStyle([
        ('FONTNAME',    (0, 0), (-1, -1), _BASE_FONT),
        ('BACKGROUND',  (0, 0), (-1, 0), LTEAL),
        ('FONTNAME',    (0, 0), (-1, 0), _BOLD_FONT),
        ('FONTSIZE',    (0, 0), (-1, -1), 9),
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRAY]),
        ('ALIGN',       (2, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (0, -1), 8),
        ('LINEABOVE',   (0, -1), (-1, -1), 1, TEAL),
    ]))
    elements.append(earn_table)
    elements.append(Spacer(1, 0.3 * cm))

    # ------- Deductions -------
    # Statutory contributions are fixed monthly TOTAL amounts; the
    # employee's share is taken in full only on the second/last
    # bi-weekly cutoff of the month (zero on the first cutoff). The
    # "Basis" column shows that share so it's clear why a cut might
    # show ₱0 for these lines.
    elements.append(Paragraph("  DEDUCTIONS", section_style))
    is_last_cutoff = payroll.get('_is_last_cutoff')
    if is_last_cutoff is None:
        # Derive from the period end date if not explicitly provided
        try:
            from app.utils.payroll import is_second_cutoff
            is_last_cutoff = is_second_cutoff(payroll.get('pay_period_end', ''))
        except Exception:
            is_last_cutoff = float(payroll.get('sss_deduction', 0)) > 0

    cutoff_note = "this cutoff" if is_last_cutoff else "next cutoff (none this cut)"
    deductions_data = [
        ['Description', 'Employee Share', 'Amount'],
        ['SSS Contribution', f"40% — {cutoff_note}", _peso(payroll.get('sss_deduction', 0))],
        ['PhilHealth Contribution', f"50% — {cutoff_note}", _peso(payroll.get('philhealth_deduction', 0))],
        ['Pag-IBIG Contribution', f"50% — {cutoff_note}", _peso(payroll.get('pagibig_deduction', 0))],
    ]
    if float(payroll.get('other_deductions', 0)) > 0:
        deductions_data.append([
            f"Other ({payroll.get('other_deductions_note', '') or '—'})",
            '—',
            _peso(payroll['other_deductions'])
        ])
    deductions_data.append(['', Paragraph('<b>TOTAL DEDUCTIONS</b>', bold_style),
                             Paragraph(_peso(payroll.get('total_deductions', 0)), total_style)])

    ded_table = Table(deductions_data, colWidths=[7 * cm, 6 * cm, 5.5 * cm])
    ded_table.setStyle(TableStyle([
        ('FONTNAME',    (0, 0), (-1, -1), _BASE_FONT),
        ('BACKGROUND',  (0, 0), (-1, 0), LTEAL),
        ('FONTNAME',    (0, 0), (-1, 0), _BOLD_FONT),
        ('FONTSIZE',    (0, 0), (-1, -1), 9),
        ('GRID',        (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -2), [colors.white, GRAY]),
        ('ALIGN',       (1, 0), (-1, -1), 'RIGHT'),
        ('TOPPADDING',  (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LEFTPADDING',   (0, 0), (0, -1), 8),
        ('LINEABOVE',   (0, -1), (-1, -1), 1, TEAL),
    ]))
    elements.append(ded_table)
    elements.append(Spacer(1, 0.5 * cm))

    # ------- Net Pay -------
    net_data = [[
        Paragraph('<b>NET PAY</b>', ParagraphStyle(
            'NP', parent=styles['Normal'], fontSize=13, fontName=_BOLD_FONT, textColor=TEAL
        )),
        Paragraph(_peso(payroll.get('net_pay', 0)), ParagraphStyle(
            'NPV', parent=styles['Normal'], fontSize=14, fontName=_BOLD_FONT,
            textColor=TEAL, alignment=TA_RIGHT
        ))
    ]]
    net_table = Table(net_data, colWidths=[10 * cm, 8.5 * cm])
    net_table.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LTEAL),
        ('BOX',           (0, 0), (-1, -1), 1.5, TEAL),
        ('TOPPADDING',    (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('LEFTPADDING',   (0, 0), (-1, -1), 10),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 10),
    ]))
    elements.append(net_table)
    elements.append(Spacer(1, 0.8 * cm))

    # ------- Footer -------
    elements.append(HRFlowable(width="100%", thickness=1, color=TEAL))
    elements.append(Spacer(1, 0.2 * cm))
    elements.append(Paragraph(
        "This payslip is system-generated and is valid without a signature. "
        "For payroll inquiries, contact the clinic administrator.",
        ParagraphStyle('Footer', parent=styles['Normal'], fontSize=7,
                       textColor=colors.gray, alignment=TA_CENTER)
    ))

    doc.build(elements)
    pdf_bytes = buffer.getvalue()
    buffer.close()
    return pdf_bytes
