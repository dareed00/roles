#!/usr/bin/env python3
"""
bundleBuilder - Suggested IT Roles PDF Scorecard Generator
Generates publication-quality PDF documents containing detailed structural profiles,
Jaccard cohesion rankings, and adoption metrics for discovered IT functional roles.
"""

import os
import sys
from collections import defaultdict
import mysql.connector
from mysql.connector import Error

# Import ReportLab elements
try:
    from reportlab.lib.pagesizes import letter
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
except ImportError:
    print("❌ Error: reportlab module not found. Please install it using: pip install reportlab")
    sys.exit(1)

# ==============================================================================
# 1. DYNAMIC SYSTEM PATH RESOLUTION & CENTRAL IMPORTS
# ==============================================================================
root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if root_dir not in sys.path:
    sys.path.append(root_dir)

from Utils.config import open_connection, close_db_connection, DB_CONFIG

PDF_OUTPUT_PATH = os.path.join("Report", "Suggested_IT_Roles_Scorecard.pdf")


# ==============================================================================
# 2. REPORTLAB CANVAS WITH PAGE NUMBERING
# ==============================================================================
class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_elements(num_pages)
            super().showPage()
        super().save()

    def draw_page_elements(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 8)
        self.setFillColor(colors.HexColor("#555555"))

        # Skip running header/footer on the cover page
        if self._pageNumber > 1:
            # Draw Header
            self.drawString(54, 750, "bundleBuilder - Discovered IT Functional Roles Profile")
            self.setStrokeColor(colors.HexColor("#CCCCCC"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)

            # Draw Footer
            page_text = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(558, 40, page_text)
            self.drawString(54, 40, "CONFIDENTIAL - Internal Identity Governance & Administration Review Only")
            self.line(54, 52, 558, 52)

        self.restoreState()


# ==============================================================================
# 3. DATA EXTRACTION ENGINE
# ==============================================================================
def load_staging_it_roles_data():
    print("💾 Extracting suggested IT Functional Roles metadata from MySQL...")
    db_connection = None
    cursor = None

    try:
        db_connection = open_connection()
        if not db_connection:
            print("❌ Failed to connect to the database.")
            sys.exit(1)

        cursor = db_connection.cursor(dictionary=True)

        # 1. Fetch IT Roles
        cursor.execute("""
            SELECT 
                id, it_role_name, approval_status, deploy_target, approved_role_name,
                primary_source, description, entitlements_count, full_holders_count,
                partial_holders_count, bundle_cohesion_score, admin_notes
            FROM Suggested_IT_Roles
            ORDER BY entitlements_count DESC, full_holders_count DESC
        """)
        it_roles = cursor.fetchall()

        if not it_roles:
            print("⚠️ No suggested IT Roles found in the database. PDF cannot be generated.")
            return None, None

        # 2. Fetch IT Role Entitlements
        cursor.execute("""
            SELECT it_role_id, entitlement_id, entitlement_name, source_name, assignment_count
            FROM Suggested_IT_Role_Entitlements
            WHERE is_included = 1
            ORDER BY it_role_id, assignment_count DESC
        """)
        entitlements_by_role = defaultdict(list)
        for row in cursor.fetchall():
            entitlements_by_role[row["it_role_id"]].append(row)

        return it_roles, entitlements_by_role

    except Error as e:
        print(f"❌ Database error loading IT roles: {e}")
        sys.exit(1)
    finally:
        if db_connection:
            close_db_connection(db_connection, cursor)


# ==============================================================================
# 4. PDF BUILDER
# ==============================================================================
def generate_suggested_it_roles_pdf(output_path=PDF_OUTPUT_PATH):
    it_roles, entitlements_by_role = load_staging_it_roles_data()
    if not it_roles:
        return

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    print(f"✍️ Compiling PDF document structure at: '{output_path}'...")
    
    # 54pt margins give exactly 504pt of printable width (Letter = 612x792)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()
    
    # Custom Palette Style Definitions
    style_cover_title = ParagraphStyle(
        'CoverTitle',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=24,
        leading=28,
        textColor=colors.HexColor("#1F4E78"),
        spaceAfter=15
    )
    style_section_heading = ParagraphStyle(
        'SectionHeading',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=14,
        leading=18,
        textColor=colors.HexColor("#1F4E78"),
        spaceBefore=15,
        spaceAfter=10,
        keepWithNext=True
    )
    style_body_text = ParagraphStyle(
        'BodyText',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=10,
        leading=14,
        textColor=colors.HexColor("#333333"),
        spaceAfter=10
    )
    style_table_cell = ParagraphStyle(
        'TableCell',
        parent=styles['Normal'],
        fontName='Helvetica',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#333333")
    )
    style_table_header = ParagraphStyle(
        'TableHeader',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#FFFFFF")
    )

    story = []

    # ==========================================================================
    # COVER PAGE
    # ==========================================================================
    story.append(Spacer(1, 100))
    story.append(Paragraph("bundleBuilder", ParagraphStyle('CoverSub', fontName='Helvetica-Bold', fontSize=14, leading=16, textColor=colors.HexColor("#555555"), spaceAfter=10)))
    story.append(Paragraph("DISCOVERED IT FUNCTIONAL ROLES PROFILE", style_cover_title))
    story.append(Paragraph("A publication-quality analysis of access profile clusters, entitlement correlations, and user adoption footprints for automated SailPoint Identity Security Cloud deployment.", style_body_text))
    story.append(Spacer(1, 40))

    # Executive Metadata Block
    meta_data = [
        [Paragraph("<b>Target System:</b>", style_table_cell), Paragraph("SailPoint Identity Security Cloud", style_table_cell)],
        [Paragraph("<b>Total Discovered IT Roles:</b>", style_table_cell), Paragraph(f"{len(it_roles):,}", style_table_cell)],
        [Paragraph("<b>Report Generated:</b>", style_table_cell), Paragraph("Automatic Deployment Pipeline", style_table_cell)],
        [Paragraph("<b>Classification:</b>", style_table_cell), Paragraph("<font color='red'><b>CONFIDENTIAL - RESTRICTED</b></font>", style_table_cell)]
    ]
    t_meta = Table(meta_data, colWidths=[150, 354])
    t_meta.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,-1), colors.HexColor("#F2F4F8")),
        ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E4E8")),
        ('TOPPADDING', (0,0), (-1,-1), 6),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('LEFTPADDING', (0,0), (-1,-1), 10),
        ('RIGHTPADDING', (0,0), (-1,-1), 10),
    ]))
    story.append(t_meta)
    story.append(PageBreak())

    # ==========================================================================
    # ROLE DETAILS SCORECARDS
    # ==============================================================================
    story.append(Paragraph("🏛️ DISCOVERED FUNCTIONAL ROLES CATALOG", style_section_heading))
    story.append(Paragraph("Below are individual profiles detailing each suggested IT Functional Role, including candidate entitlements, Jaccard cohesion, and adoption demographics.", style_body_text))
    story.append(Spacer(1, 10))

    for idx, r in enumerate(it_roles, start=1):
        role_story_block = []
        role_id_str = f"ITR-{int(r['id']):04d}"
        role_story_block.append(Paragraph(f"<b>{idx}. {r['it_role_name']} ({role_id_str})</b>", style_section_heading))

        # Core statistics table
        cohesion_pct = float(r.get("bundle_cohesion_score") or 1.0) * 100.0
        summary_data = [
            [Paragraph("<b>Primary Application Source:</b>", style_table_cell), Paragraph(r["primary_source"], style_table_cell)],
            [Paragraph("<b>Structural Description:</b>", style_table_cell), Paragraph(r["description"] or "None provided.", style_table_cell)],
            [Paragraph("<b>Deployment Target:</b>", style_table_cell), Paragraph(r["deploy_target"], style_table_cell)],
            [Paragraph("<b>Approval Status:</b>", style_table_cell), Paragraph(f"<b>{r['approval_status']}</b>", style_table_cell)],
            [Paragraph("<b>Role Cohesion (Pairwise Jaccard):</b>", style_table_cell), Paragraph(f"{cohesion_pct:.1f}%", style_table_cell)],
            [Paragraph("<b>Adoption Profile:</b>", style_table_cell), Paragraph(f"<b>{r['full_holders_count']:,} Full Holders (100%)</b> | {r['partial_holders_count']:,} Partial Candidates", style_table_cell)],
        ]
        t_summary = Table(summary_data, colWidths=[150, 354])
        t_summary.setStyle(TableStyle([
            ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#1F4E78")),
            ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#D9E1F2")),
            ('TOPPADDING', (0,0), (-1,-1), 5),
            ('BOTTOMPADDING', (0,0), (-1,-1), 5),
            ('LEFTPADDING', (0,0), (-1,-1), 8),
            ('BACKGROUND', (0,0), (0,-1), colors.HexColor("#F2F4F8")),
        ]))
        role_story_block.append(t_summary)
        role_story_block.append(Spacer(1, 8))

        # Entitlements list table
        ents = entitlements_by_role.get(r["id"], [])
        if ents:
            ent_data = [[
                Paragraph("Entitlement ID / Name", style_table_header),
                Paragraph("Source Application", style_table_header),
                Paragraph("Active Users", style_table_header)
            ]]
            for e in ents:
                ent_data.append([
                    Paragraph(e["entitlement_name"], style_table_cell),
                    Paragraph(e["source_name"], style_table_cell),
                    Paragraph(f"{e['assignment_count']:,} users", style_table_cell)
                ])
            t_ents = Table(ent_data, colWidths=[240, 150, 114])
            t_ents.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#1F4E78")),
                ('BOX', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
                ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#E2E4E8")),
                ('TOPPADDING', (0,0), (-1,-1), 4),
                ('BOTTOMPADDING', (0,0), (-1,-1), 4),
                ('LEFTPADDING', (0,0), (-1,-1), 6),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F9FAFC")]),
            ]))
            role_story_block.append(t_ents)
        else:
            role_story_block.append(Paragraph("<i>No entitlements linked to this Functional Role.</i>", style_body_text))

        role_story_block.append(Spacer(1, 15))
        story.append(KeepTogether(role_story_block))

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"✅ Success! PDF Scorecard generated successfully at: '{output_path}'")


if __name__ == "__main__":
    generate_suggested_it_roles_pdf()
