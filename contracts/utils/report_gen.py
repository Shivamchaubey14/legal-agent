import io
import os
import logging
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import (
    HexColor, white, black
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table,
    TableStyle, HRFlowable, KeepTogether
)
from reportlab.platypus import PageBreak

logger = logging.getLogger(__name__)

# ── Brand colors ──────────────────────────────────────────────
GOLD        = HexColor('#C9A84C')
GOLD_LIGHT  = HexColor('#F0D98C')
DARK_BG     = HexColor('#0F0F0F')
SURFACE     = HexColor('#1A1A1A')
SURFACE2    = HexColor('#222222')
TXT         = HexColor('#F0F0F0')
TXT2        = HexColor('#CCCCCC')
TXT3        = HexColor('#999999')
HIGH        = HexColor('#FF6B6B')
MED         = HexColor('#FFC107')
LOW         = HexColor('#3DD68C')
CRITICAL    = HexColor('#FF3B30')
BORDER      = HexColor('#2A2A2A')
WHITE       = white

RISK_COLORS = {
    'low':      LOW,
    'medium':   MED,
    'high':     HIGH,
    'critical': CRITICAL,
}

RISK_BG = {
    'low':      HexColor('#0D2B1A'),
    'medium':   HexColor('#2B1F00'),
    'high':     HexColor('#2B0A0A'),
    'critical': HexColor('#2B0505'),
}

PAGE_W, PAGE_H = A4
MARGIN = 20 * mm


def get_styles():
    styles = getSampleStyleSheet()

    base = dict(
        fontName    = 'Helvetica',
        textColor   = TXT,
        leading     = 14,
    )

    return {
        'cover_title': ParagraphStyle('cover_title',
            fontName='Helvetica-Bold', fontSize=32,
            textColor=GOLD, leading=38, spaceAfter=6,
            alignment=TA_CENTER),

        'cover_sub': ParagraphStyle('cover_sub',
            fontName='Helvetica', fontSize=13,
            textColor=TXT2, leading=18,
            alignment=TA_CENTER),

        'cover_meta': ParagraphStyle('cover_meta',
            fontName='Helvetica', fontSize=10,
            textColor=TXT3, leading=14,
            alignment=TA_CENTER),

        'section_heading': ParagraphStyle('section_heading',
            fontName='Helvetica-Bold', fontSize=14,
            textColor=GOLD, leading=20,
            spaceBefore=14, spaceAfter=8),

        'body': ParagraphStyle('body',
            fontName='Helvetica', fontSize=10,
            textColor=TXT2, leading=15,
            spaceAfter=6),

        'body_small': ParagraphStyle('body_small',
            fontName='Helvetica', fontSize=9,
            textColor=TXT3, leading=13),

        'flag_type': ParagraphStyle('flag_type',
            fontName='Helvetica-Bold', fontSize=11,
            textColor=TXT, leading=15),

        'flag_text': ParagraphStyle('flag_text',
            fontName='Helvetica-Oblique', fontSize=9,
            textColor=TXT3, leading=13,
            leftIndent=8),

        'flag_label': ParagraphStyle('flag_label',
            fontName='Helvetica-Bold', fontSize=8,
            textColor=TXT3, leading=12,
            spaceBefore=6),

        'flag_body': ParagraphStyle('flag_body',
            fontName='Helvetica', fontSize=9,
            textColor=TXT2, leading=13,
            leftIndent=8),

        'redline': ParagraphStyle('redline',
            fontName='Helvetica', fontSize=9,
            textColor=GOLD_LIGHT, leading=13,
            leftIndent=8, backColor=HexColor('#1A1500')),

        'toc_item': ParagraphStyle('toc_item',
            fontName='Helvetica', fontSize=10,
            textColor=TXT2, leading=16),

        'mono': ParagraphStyle('mono',
            fontName='Courier', fontSize=9,
            textColor=TXT2, leading=13),
    }


# ── Page template with header/footer ─────────────────────────
class ReportTemplate(SimpleDocTemplate):
    def __init__(self, buffer, contract_title, **kwargs):
        super().__init__(buffer, **kwargs)
        self.contract_title = contract_title
        self.page_num       = 0

    def handle_pageBegin(self):
        super().handle_pageBegin()
        self.page_num += 1

    def afterPage(self):
        canvas = self.canv
        w, h   = A4

        # Skip header/footer on cover page
        if self.page_num <= 1:
            return

        # Header bar
        canvas.saveState()
        canvas.setFillColor(SURFACE)
        canvas.rect(0, h - 14*mm, w, 14*mm, fill=1, stroke=0)

        canvas.setFillColor(GOLD)
        canvas.rect(0, h - 14*mm, 3, 14*mm, fill=1, stroke=0)

        canvas.setFont('Helvetica', 8)
        canvas.setFillColor(TXT3)
        canvas.drawString(MARGIN, h - 9*mm, 'LEGAL CONTRACT INTELLIGENCE AGENT')
        title = self.contract_title[:60] + ('…' if len(self.contract_title) > 60 else '')
        canvas.drawRightString(w - MARGIN, h - 9*mm, title)

        # Footer bar
        canvas.setFillColor(SURFACE)
        canvas.rect(0, 0, w, 10*mm, fill=1, stroke=0)
        canvas.setFillColor(TXT3)
        canvas.setFont('Helvetica', 8)
        canvas.drawString(MARGIN, 4*mm, f'Confidential — Generated {datetime.now().strftime("%B %d, %Y")}')
        canvas.drawRightString(w - MARGIN, 4*mm, f'Page {self.page_num}')

        canvas.restoreState()


def build_cover(contract, score_result, styles, story):
    """Cover page."""
    w, h = A4

    # Full-page dark background drawn via a table
    cover_table = Table(
        [['']],
        colWidths=[w - 2*MARGIN],
        rowHeights=[h - 4*MARGIN],
    )
    cover_table.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), DARK_BG),
        ('BOX',        (0,0), (-1,-1), 1, BORDER),
        ('ROUNDEDCORNERS', [8]),
    ]))

    # We draw on top with paragraphs
    story.append(Spacer(1, 40*mm))

    # Logo / badge line
    story.append(Paragraph('⚖ LEGAL INTELLIGENCE REPORT', styles['cover_meta']))
    story.append(Spacer(1, 6*mm))

    # Contract title
    safe_title = contract.title.replace('&', '&amp;')
    story.append(Paragraph(safe_title, styles['cover_title']))
    story.append(Spacer(1, 4*mm))

    # Risk pill
    risk   = (contract.risk_score or 'low').upper()
    rcolor = RISK_COLORS.get(contract.risk_score or 'low', GOLD)
    story.append(Paragraph(
        f'<font color="#{rcolor.hexval()[2:]}"><b>● {risk} RISK</b></font>',
        styles['cover_sub']))
    story.append(Spacer(1, 8*mm))

    # Score bar line
    score = score_result.get('score', contract.risk_score_value or 0)
    story.append(Paragraph(f'Risk Score: {score}/100', styles['cover_meta']))
    story.append(Spacer(1, 2*mm))

    # Horizontal rule
    story.append(HRFlowable(width='60%', color=GOLD, thickness=1, hAlign='CENTER'))
    story.append(Spacer(1, 6*mm))

    # Meta block
    meta_lines = [
        f'Contract ID: #{contract.id}',
        f'Pages: {contract.page_count or "—"}',
        f'Analyzed: {datetime.now().strftime("%B %d, %Y at %H:%M")}',
        f'Prepared for: {contract.user.get_full_name() or contract.user.username}',
    ]
    for line in meta_lines:
        story.append(Paragraph(line, styles['cover_meta']))
        story.append(Spacer(1, 1*mm))

    story.append(PageBreak())


def build_summary(contract, flags, score_result, styles, story):
    """Executive summary page."""
    story.append(Paragraph('Executive Summary', styles['section_heading']))
    story.append(HRFlowable(width='100%', color=BORDER, thickness=0.5))
    story.append(Spacer(1, 4*mm))

    score     = score_result.get('score', contract.risk_score_value or 0)
    breakdown = score_result.get('breakdown', {})
    risk      = contract.risk_score or 'low'
    rcolor    = RISK_COLORS.get(risk, GOLD)

    # Score summary table
    summary_data = [
        ['Overall Risk Score', 'Risk Level', 'Total Flags', 'High', 'Medium', 'Low'],
        [
            str(score) + '/100',
            risk.upper(),
            str(len(flags)),
            str(breakdown.get('high', 0)),
            str(breakdown.get('medium', 0)),
            str(breakdown.get('low', 0)),
        ]
    ]

    col_w = (PAGE_W - 2*MARGIN) / 6
    t = Table(summary_data, colWidths=[col_w]*6, rowHeights=[8*mm, 12*mm])
    t.setStyle(TableStyle([
        # Header row
        ('BACKGROUND',  (0,0), (-1,0), SURFACE2),
        ('TEXTCOLOR',   (0,0), (-1,0), TXT3),
        ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,0), 8),
        ('ALIGN',       (0,0), (-1,-1), 'CENTER'),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        # Data row
        ('BACKGROUND',  (0,1), (-1,1), SURFACE),
        ('TEXTCOLOR',   (0,1), (0,1),  rcolor),
        ('FONTNAME',    (0,1), (-1,1), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,1), (-1,1), 14),
        ('TEXTCOLOR',   (1,1), (1,1),  rcolor),
        ('TEXTCOLOR',   (3,1), (3,1),  HIGH),
        ('TEXTCOLOR',   (4,1), (4,1),  MED),
        ('TEXTCOLOR',   (5,1), (5,1),  LOW),
        # Borders
        ('BOX',         (0,0), (-1,-1), 1, BORDER),
        ('INNERGRID',   (0,0), (-1,-1), 0.5, BORDER),
        ('ROUNDEDCORNERS', [4]),
    ]))
    story.append(t)
    story.append(Spacer(1, 6*mm))

    # Contract details
    story.append(Paragraph('Contract Details', styles['section_heading']))
    story.append(HRFlowable(width='100%', color=BORDER, thickness=0.5))
    story.append(Spacer(1, 2*mm))

    detail_data = [
        ['Field', 'Value'],
        ['Title',    contract.title],
        ['Status',   contract.status.upper()],
        ['Pages',    str(contract.page_count or '—')],
        ['Created',  contract.created_at.strftime('%B %d, %Y')],
        ['Owner',    contract.user.get_full_name() or contract.user.username],
    ]

    col_widths = [40*mm, PAGE_W - 2*MARGIN - 40*mm]
    dt = Table(detail_data, colWidths=col_widths, rowHeights=8*mm)
    dt.setStyle(TableStyle([
        ('BACKGROUND',  (0,0), (-1,0), SURFACE2),
        ('TEXTCOLOR',   (0,0), (-1,0), TXT3),
        ('FONTNAME',    (0,0), (-1,0), 'Helvetica-Bold'),
        ('FONTSIZE',    (0,0), (-1,-1), 9),
        ('BACKGROUND',  (0,1), (0,-1), SURFACE),
        ('BACKGROUND',  (1,1), (1,-1), DARK_BG),
        ('TEXTCOLOR',   (0,1), (0,-1), TXT3),
        ('TEXTCOLOR',   (1,1), (1,-1), TXT2),
        ('FONTNAME',    (0,1), (0,-1), 'Helvetica-Bold'),
        ('ALIGN',       (0,0), (-1,-1), 'LEFT'),
        ('VALIGN',      (0,0), (-1,-1), 'MIDDLE'),
        ('LEFTPADDING', (0,0), (-1,-1), 8),
        ('BOX',         (0,0), (-1,-1), 1, BORDER),
        ('INNERGRID',   (0,0), (-1,-1), 0.5, BORDER),
    ]))
    story.append(dt)
    story.append(Spacer(1, 4*mm))


def build_flags_section(flags, styles, story):
    """Clause flags section — one card per flag."""
    story.append(PageBreak())
    story.append(Paragraph('Clause Risk Analysis', styles['section_heading']))
    story.append(HRFlowable(width='100%', color=BORDER, thickness=0.5))
    story.append(Spacer(1, 4*mm))

    if not flags:
        story.append(Paragraph('No risky clauses were detected in this contract.', styles['body']))
        return

    for i, flag in enumerate(flags, 1):
        risk   = flag.risk_level
        rcolor = RISK_COLORS.get(risk, GOLD)
        rbg    = RISK_BG.get(risk, SURFACE)

        # Card content rows
        card_rows = []

        # Header row: number + type + risk badge
        header_content = [
            Paragraph(f'<b>#{i} — {flag.clause_type}</b>', styles['flag_type']),
            Paragraph(f'<font color="#{rcolor.hexval()[2:]}"><b>{risk.upper()}</b></font>', styles['flag_type']),
        ]
        card_rows.append(header_content)

        # Clause text
        if flag.clause_text:
            excerpt = flag.clause_text[:300].replace('&', '&amp;').replace('<', '&lt;')
            card_rows.append([
                Paragraph(f'<i>"{excerpt}…"</i>', styles['flag_text']),
                '',
            ])

        # Reason
        if flag.reason:
            reason = flag.reason.replace('&', '&amp;').replace('<', '&lt;')
            card_rows.append([Paragraph('WHY IT\'S RISKY', styles['flag_label']), ''])
            card_rows.append([Paragraph(reason, styles['flag_body']), ''])

        # Suggestion
        if flag.suggestion:
            suggestion = flag.suggestion.replace('&', '&amp;').replace('<', '&lt;')
            card_rows.append([Paragraph('SUGGESTION', styles['flag_label']), ''])
            card_rows.append([Paragraph(suggestion, styles['flag_body']), ''])

        # Redline
        if flag.redline:
            redline = flag.redline.replace('&', '&amp;').replace('<', '&lt;')
            card_rows.append([Paragraph('SUGGESTED REDLINE', styles['flag_label']), ''])
            card_rows.append([Paragraph(redline, styles['redline']), ''])

        # Build card table
        col_w = PAGE_W - 2*MARGIN
        row_heights = [10*mm] + [None] * (len(card_rows) - 1)

        card = Table(
            card_rows,
            colWidths=[col_w * 0.75, col_w * 0.25],
            rowHeights=row_heights,
        )
        card.setStyle(TableStyle([
            # Header row
            ('BACKGROUND',   (0,0), (-1,0), rbg),
            ('TEXTCOLOR',    (1,0), (1,0),  rcolor),
            ('ALIGN',        (1,0), (1,0),  'RIGHT'),
            ('RIGHTPADDING', (1,0), (1,0),  10),
            # All rows
            ('BACKGROUND',   (0,1), (-1,-1), SURFACE),
            ('LEFTPADDING',  (0,0), (-1,-1), 10),
            ('TOPPADDING',   (0,0), (-1,-1), 4),
            ('BOTTOMPADDING',(0,0), (-1,-1), 4),
            ('SPAN',         (0,1), (-1,1)),   # span clause text row
            ('BOX',          (0,0), (-1,-1), 1, rcolor),
            ('LINEBELOW',    (0,0), (-1,0),  1, rcolor),
        ]))

        story.append(KeepTogether(card))
        story.append(Spacer(1, 5*mm))


def generate_report(contract, flags, score_result) -> bytes:
    """
    Generate a PDF report and return raw bytes.

    Args:
        contract:     Contract model instance
        flags:        QuerySet of ClauseFlag
        score_result: dict from compute_risk_score()

    Returns:
        PDF bytes
    """
    buffer = io.BytesIO()

    doc = ReportTemplate(
        buffer,
        contract_title = contract.title,
        pagesize       = A4,
        leftMargin     = MARGIN,
        rightMargin    = MARGIN,
        topMargin      = MARGIN + 5*mm,
        bottomMargin   = MARGIN,
        title          = f'Risk Report — {contract.title}',
        author         = 'Legal Contract Intelligence Agent',
    )

    styles = get_styles()
    story  = []

    # 1. Cover
    build_cover(contract, score_result, styles, story)

    # 2. Executive summary
    build_summary(contract, list(flags), score_result, styles, story)

    # 3. Clause flags
    build_flags_section(list(flags), styles, story)

    # 4. Build
    try:
        doc.build(story)
    except Exception as e:
        logger.error(f'Report build error: {e}')
        raise

    buffer.seek(0)
    return buffer.read()