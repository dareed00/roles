#!/usr/bin/env python3
"""
bundleBuilder - Executive Dashboard PDF Report Generator
Generates publication-quality PDF documents containing high-level analytics,
population metrics, and role-mining coverage summary for executives.
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

PDF_OUTPUT_PATH = os.path.join("Report", "Executive_Role_Mining_Dashboard.pdf")


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
            self.drawString(54, 750, "bundleBuilder - Executive Role Mining Dashboard")
            self.setStrokeColor(colors.HexColor("#CCCCCC"))
            self.setLineWidth(0.5)
            self.line(54, 742, 558, 742)

            # Draw Footer
            page_text = f"Page {self._pageNumber} of {page_count}"
            self.drawRightString(558, 40, page_text)
            self.drawString(54, 40, "CONFIDENTIAL - Executive Identity Governance & Administration Dashboard")
            self.line(54, 52, 558, 52)

        self.restoreState()


# ==============================================================================
# 3. DATA EXTRACTION ENGINE
# ==============================================================================
def load_dashboard_metrics():
    print("💾 Extracting executive dashboard metrics from MySQL...")
    db_connection = None
    cursor = None

    try:
        db_connection = open_connection()
        if not db_connection:
            print("❌ Failed to connect to the database.")
            sys.exit(1)

        cursor = db_connection.cursor(dictionary=True)

        metrics = {}

        # 1. Total Identities
        cursor.execute("SELECT COUNT(*) as count FROM Identities")
        metrics["total_identities"] = (cursor.fetchone() or {"count": 0})["count"]

        # 2. Filtered Identities
        cursor.execute("SELECT COUNT(*) as count FROM Identities_Filtered")
        metrics["filtered_identities"] = (cursor.fetchone() or {"count": 0})["count"]

        # 3. Total Entitlements
        cursor.execute("SELECT COUNT(*) as count FROM entitlements")
        metrics["total_entitlements"] = (cursor.fetchone() or {"count": 0})["count"]

        # 4. Correlated Entitlements (is_correlated = 1)
        cursor.execute("SELECT COUNT(*) as count FROM entitlements WHERE is_correlated = 1")
        metrics["correlated_entitlements"] = (cursor.fetchone() or {"count": 0})["count"]

        # 5. Total Suggested Business Roles
        cursor.execute("SELECT COUNT(*) as count FROM Suggested_Roles WHERE approval_status != 'IGNORED'")
        metrics["suggested_business_roles"] = (cursor.fetchone() or {"count": 0})["count"]

        # 6. Total Suggested APs (IT Roles)
        cursor.execute("SELECT COUNT(*) as count FROM Suggested_IT_Roles")
        metrics["suggested_it_roles"] = (cursor.fetchone() or {"count": 0})["count"]

        # 7. Total Exclusions tracked
        cursor.execute("SELECT COUNT(*) as count FROM Role_Entitlement_Exclusions")
        metrics["total_exclusions"] = (cursor.fetchone() or {"count": 0})["count"]

        return metrics

    except Error as e:
        print(f"❌ Database error loading dashboard metrics: {e}")
        sys.exit(1)
    finally:
        if db_connection:
            close_db_connection(db_connection, cursor)


# ==============================================================================
# 4. PDF BUILDER
# ==============================================================================
def generate_executive_dashboard_pdf(output_path=PDF_OUTPUT_PATH):
    metrics = load_dashboard_metrics()
    if not metrics:
        return

    os.makedirs(os.path.dirname(output_path) if os.path.dirname(output_path) else ".", exist_ok=True)

    print(f"✍️ Compiling Executive PDF document structure at: '{output_path}'...")
    
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
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#333333")
    )
    style_table_cell_bold = ParagraphStyle(
        'TableCellBold',
        parent=styles['Normal'],
        fontName='Helvetica-Bold',
        fontSize=10,
        leading=13,
        textColor=colors.HexColor("#1F4E78")
    )

    story = []

    # ==========================================================================
    # COVER PAGE
    # ==========================================================================
    story.append(Spacer(1, 100))
    story.append(Paragraph("bundleBuilder", ParagraphStyle('CoverSub', fontName='Helvetica-Bold', fontSize=14, leading=16, textColor=colors.HexColor("#555555"), spaceAfter=10)))
    story.append(Paragraph("EXECUTIVE ROLE MINING DASHBOARD", style_cover_title))
    story.append(Paragraph("A high-level governance dashboard reporting critical database metrics, active assignment coverage, and correlation pipeline results for identity access management alignment.", style_body_text))
    story.append(Spacer(1, 40))

    # Executive Summary Metrics Block
    coverage_ratio = (metrics["correlated_entitlements"] / metrics["total_entitlements"] * 100.0) if metrics["total_entitlements"] > 0 else 0
    
    dashboard_data = [
        [Paragraph("<b>Metric Dimension</b>", style_table_cell_bold), Paragraph("<b>Calculated Value / Result</b>", style_table_cell_bold)],
        [Paragraph("Total Identities Loaded:", style_table_cell), Paragraph(f"{metrics['total_identities']:,} employees", style_table_cell)],
        [Paragraph("Target Filtered Mining Population:", style_table_cell), Paragraph(f"{metrics['filtered_identities']:,} active employees", style_table_cell)],
        [Paragraph("Total Entitlements in Catalog:", style_table_cell), Paragraph(f"{metrics['total_entitlements']:,} permissions", style_table_cell)],
        [Paragraph("Statistically Correlated Access Items:", style_table_cell), Paragraph(f"{metrics['correlated_entitlements']:,} entitlements", style_table_cell)],
        [Paragraph("<b>Role Coverage Success Ratio:</b>", style_table_cell), Paragraph(f"<b>{coverage_ratio:.1f}% of catalog mapped</b>", style_table_cell_bold)],
        [Paragraph("Suggested Business Role Objects:", style_table_cell), Paragraph(f"{metrics['suggested_business_roles']:,} roles", style_table_cell)],
        [Paragraph("Suggested APs (IT Functional Roles):", style_table_cell), Paragraph(f"{metrics['suggested_it_roles']:,} profiles", style_table_cell)],
        [Paragraph("Persistent Reviewer Exclusions:", style_table_cell), Paragraph(f"{metrics['total_exclusions']:,} suppressed relationships", style_table_cell)],
    ]
    
    t_dashboard = Table(dashboard_data, colWidths=[250, 254])
    t_dashboard.setStyle(TableStyle([
        ('BACKGROUND', (0,0), (-1,0), colors.HexColor("#D9E1F2")),
        ('BOX', (0,0), (-1,-1), 1, colors.HexColor("#1F4E78")),
        ('INNERGRID', (0,0), (-1,-1), 0.5, colors.HexColor("#CCCCCC")),
        ('TOPPADDING', (0,0), (-1,-1), 8),
        ('BOTTOMPADDING', (0,0), (-1,-1), 8),
        ('LEFTPADDING', (0,0), (-1,-1), 12),
        ('RIGHTPADDING', (0,0), (-1,-1), 12),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor("#F9FAFC")]),
    ]))
    
    story.append(t_dashboard)
    story.append(Spacer(1, 25))
    
    # Add brief narrative details
    story.append(Paragraph("<b>📈 Key Takeaways & Recommendations</b>", style_section_heading))
    story.append(Paragraph(f"The exact and fuzzy correlation passes successfully analyzed <b>{metrics['filtered_identities']:,}</b> active identities. The current model correlates <b>{metrics['correlated_entitlements']:,}</b> unique permissions, resulting in a healthy <b>{coverage_ratio:.1f}%</b> analytical coverage ratio. It is highly recommended to prioritize reviewing the suggested <b>{metrics['suggested_business_roles']:,}</b> business roles using the interactive admin approval workbook prior to staging your next access certification campaign.", style_body_text))

    # Build PDF
    doc.build(story, canvasmaker=NumberedCanvas)
    print(f"   ✓ Executive Dashboard PDF successfully generated at: '{output_path}'")


if __name__ == "__main__":
    generate_executive_dashboard_pdf()
