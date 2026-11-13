#!/usr/bin/env python3
"""
bundleBuilder - Interactive Role Approval & Staging Excel Generator
File: Scripts/Report/generate_role_approval_workbook.py

Main orchestrator and sheet builders for the multi-sheet .xlsx workbook.
"""

import os
import sys
from datetime import datetime
import openpyxl
from openpyxl.worksheet.datavalidation import DataValidation

# Ensure Scripts root is on sys.path
scripts_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if scripts_dir not in sys.path:
    sys.path.append(scripts_dir)

from Utils.config import PROJECT_ROOT
from Report.workbook_helpers import (
    format_found_date,
    format_decision_date,
    is_splittable_rule,
    build_user_roster_string,
)
from Report.workbook_styles import (
    GREY_OUT_FILL, MUTED_FONT,
    FONT_GREEN_DARK, FONT_OLIVE_DARK, FONT_AMBER_DARK, FONT_PURPLE_DARK, FONT_GRAY_MUTED,
    FONT_TITLE, FONT_HEADER, FONT_DATA, FONT_FORMULA, FONT_CODE, FONT_CODE_FADED,
    FONT_KPI_NUM, FONT_KPI_LBL, FONT_ACTION_BLUE,
    FILL_WHITE, FILL_LIGHT_BLUE, FILL_DYNAMIC_PARENT, FILL_DYNAMIC_SUBTIER,
    FILL_HEADER_NAVY, FILL_HEADER_BLUE, FILL_HEADER_INDIGO, FILL_HEADER_PURPLE,
    FILL_HEADER_EMERALD, FILL_KPI_BG,
    THIN_BORDER, ALIGN_CENTER, ALIGN_LEFT, ALIGN_LEFT_WRAP,
    style_confidence_cell, style_coverage_cell, style_missing_cell,
    style_extra_cell, style_decision_cell, auto_fit_workbook_columns,
)
from Report.workbook_data_loader import load_staging_data

OUTPUT_EXCEL = os.path.join(PROJECT_ROOT, "Report", "Role_Mining_Admin_Approval_Workbook.xlsx")
DEFAULT_OWNER_FULLNAME = "IAM Security Team"


def build_validations(max_lookup_row):
    """Creates reusable OpenPyXL DataValidation dropdown objects."""
    return {
        "role_decision": DataValidation(
            type="list",
            formula1='"ACCEPT,DENY,IGNORE,SPLIT,MAKE_DYNAMIC,CERTIFY,APPROVED,REJECTED,PENDING_REVIEW,ALREADY_IN_PROD"',
            allow_blank=False,
        ),
        "ent_action": DataValidation(
            type="list",
            formula1='"ACCEPT,DENY,IGNORE,SPLIT"',
            allow_blank=False,
        ),
        "target": DataValidation(
            type="list",
            formula1='"BOTH,ISC_CLOUD,IIQ_ONPREM,SKIP"',
            allow_blank=False,
        ),
        "yesno": DataValidation(
            type="list",
            formula1='"ACCEPT,DENY,IGNORE"',
            allow_blank=False,
        ),
        "action": DataValidation(
            type="list",
            formula1='"ACCEPT,DENY,IGNORE,SPLIT,KEEP_AS_SUGGESTED,SEPARATE,MAKE_DYNAMIC,CERTIFY"',
            allow_blank=True,
        ),
        "owner_fullname": DataValidation(
            type="list",
            formula1=f"='_Lookups_Reference'!$B$2:$B${max_lookup_row}",
            allow_blank=True,
        ),
    }


def build_lookups_sheet(wb, lookup_owners):
    """Builds Sheet 7: _Lookups_Reference."""
    ws = wb.create_sheet(title="_Lookups_Reference")
    ws.views.sheetView[0].showGridLines = True
    headers = [
        "Owner UID (Col A)", "Full Name (Lookup Key - Col B)", "Job Title (Col C)",
        "Department (Col D)", "Email (Col E)", "Owner Type (Col F)"
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_NAVY
        cell.alignment = ALIGN_CENTER

    for row_idx, o in enumerate(lookup_owners, 2):
        ws.cell(row=row_idx, column=1, value=o["uid"]).alignment = ALIGN_LEFT
        ws.cell(row=row_idx, column=2, value=o["name"]).alignment = ALIGN_LEFT
        ws.cell(row=row_idx, column=3, value=o["title"]).alignment = ALIGN_LEFT
        ws.cell(row=row_idx, column=4, value=o["dept"]).alignment = ALIGN_LEFT
        ws.cell(row=row_idx, column=5, value=o["email"]).alignment = ALIGN_LEFT
        ws.cell(row=row_idx, column=6, value=o["type"]).alignment = ALIGN_CENTER

        fill = FILL_LIGHT_BLUE if row_idx % 2 == 0 else FILL_WHITE
        for c in range(1, 7):
            ws.cell(row=row_idx, column=c).font = FONT_DATA
            ws.cell(row=row_idx, column=c).fill = fill
            ws.cell(row=row_idx, column=c).border = THIN_BORDER


def build_executive_summary_sheet(wb):
    """Builds Sheet 1: Executive_Summary."""
    ws = wb.create_sheet(title="Executive_Summary")
    ws.views.sheetView[0].showGridLines = True
    ws.cell(row=2, column=2, value="Role Mining Staging & Delta Approval Dashboard").font = FONT_TITLE
    ws.cell(
        row=3, column=2,
        value=f"Generated on {datetime.now().strftime('%B %d, %Y')} | Supports ACCEPT, DENY, IGNORE, and SPLIT across Roles & Entitlements."
    ).font = FONT_DATA

    kpis = [
        ("Total Business Roles", "=COUNTA(Business_Roles_Review!C5:C500)", "B5"),
        ("Accepted Business Roles", '=COUNTIF(Business_Roles_Review!A5:A500, "ACCEPT")+COUNTIF(Business_Roles_Review!A5:A500, "APPROVED")', "C5"),
        ("Accepted Biz Permissions", '=COUNTIF(Business_Role_Entitlements!A5:A2000, "ACCEPT")+COUNTIF(Business_Role_Entitlements!A5:A2000, "YES")', "D5"),
        ("Total IT Roles", "=COUNTA(IT_Roles_Review!C5:C500)", "E5"),
        ("Accepted IT Roles", '=COUNTIF(IT_Roles_Review!A5:A500, "ACCEPT")+COUNTIF(IT_Roles_Review!A5:A500, "APPROVED")', "F5"),
        ("Modular Overlap Pairs", "=COUNTA(Role_Hierarchy_Overlap!A5:A500)", "G5"),
    ]
    for label, formula, col_ref in kpis:
        col_letter = col_ref[0]
        c_num = ws[f"{col_letter}5"]
        c_num.value = formula
        c_num.font = FONT_KPI_NUM
        c_num.alignment = ALIGN_CENTER
        c_num.fill = FILL_KPI_BG
        c_num.border = THIN_BORDER

        c_lbl = ws[f"{col_letter}6"]
        c_lbl.value = label
        c_lbl.font = FONT_KPI_LBL
        c_lbl.alignment = ALIGN_CENTER
        c_lbl.fill = FILL_KPI_BG
        c_lbl.border = THIN_BORDER


def build_business_roles_sheet(wb, biz_roles, biz_to_it_overlaps, it_role_meta, dvs):
    """Builds Sheet 2: Business_Roles_Review."""
    ws = wb.create_sheet(title="Business_Roles_Review")
    ws.views.sheetView[0].showGridLines = True
    ws.add_data_validation(dvs["role_decision"])
    ws.add_data_validation(dvs["target"])
    ws.add_data_validation(dvs["owner_fullname"])
    ws.add_data_validation(dvs["action"])

    ws.cell(row=2, column=1, value="Business Roles Review & Ownership Staging (Select ACCEPT, DENY, IGNORE, or SPLIT in Col A or Col Q)").font = FONT_TITLE
    headers = [
        "Decision (ACCEPT/DENY/IGNORE/SPLIT)", "Deploy Target", "Role ID", "Role Definition Delta", "Suggested Role Name", "Final Role Name (Override)",
        "Assigned Owner (Fullname)", "Owner UUID (Auto)", "Owner Title (Auto)", "Owner Email (Auto)",
        "Membership Rule", "Contained IT Roles (Modularization)", "Total Ents", "Target Users", "Confidence", "Admin Review Notes",
        "Resolution Action", "Hierarchy Type", "Parent Role ID", "Found Date", "Decision Date"
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_NAVY
        cell.alignment = ALIGN_CENTER

    for idx, r in enumerate(biz_roles, 5):
        b_id = r["id"]
        role_id_str = f"BR-{b_id:04d}"
        suggested_name = r["role_name"]
        is_already_defined = bool(r.get("already_defined", False))
        h_type = r.get("hierarchy_type") or "STANDARD"
        parent_id = r.get("parent_role_id")
        dim_attr = r.get("dimension_attribute")
        dim_val = r.get("dimension_value")
        found_dt_str = format_found_date(r.get("found_date"))
        decision_dt_str = format_decision_date(r.get("decision_date"), r.get("found_date"), r.get("approval_status"))

        if h_type == "DYNAMIC_SUB_TIER":
            display_role_name = f"    ↳ [SUB-TIER: {dim_attr}={dim_val}] {suggested_name}"
            stripe_fill = FILL_DYNAMIC_SUBTIER
        elif h_type == "DYNAMIC_PARENT":
            display_role_name = f"🌐 [DYNAMIC PARENT] {suggested_name}"
            stripe_fill = FILL_DYNAMIC_PARENT
        else:
            display_role_name = suggested_name
            stripe_fill = FILL_WHITE if idx % 2 != 0 else FILL_LIGHT_BLUE

        row_fill = GREY_OUT_FILL if is_already_defined else stripe_fill
        parent_label = f"BR-{int(parent_id):04d}" if parent_id else "—"

        b_overlaps = biz_to_it_overlaps.get(b_id, {})
        contained_it_list = []
        for it_id, ov in b_overlaps.items():
            it_name_short = it_role_meta.get(it_id, {}).get("name", f"ITR-{it_id}")
            if ov["containment_pct"] >= 99.9:
                contained_it_list.append(f"🟢 [ITR-{it_id:04d}] {it_name_short} (100%)")
            elif ov["containment_pct"] >= 75.0:
                contained_it_list.append(f"🟡 [ITR-{it_id:04d}] {it_name_short} ({ov['containment_pct']:.0f}%)")
        contained_it_str = " | ".join(contained_it_list) if contained_it_list else "None (Loose Entitlements)"

        raw_status = str(r.get("approval_status") or "").upper()
        if is_already_defined:
            default_decision = "ALREADY_IN_PROD"
        elif raw_status in ("APPROVED", "ACCEPT", "PENDING_REVIEW", ""):
            default_decision = "ACCEPT"
        elif raw_status in ("REJECTED", "DENY"):
            default_decision = "DENY"
        else:
            default_decision = raw_status

        default_target = r.get("deploy_target") or ("SKIP" if is_already_defined else "BOTH")
        res_action = r.get("resolution_action") or "ACCEPT"
        delta_label = "⚪ Already in Prod" if is_already_defined else ("✂️ Splittable Multi-Attr Role" if is_splittable_rule(r["assignment_rule"]) else "✨ Net-New Role")

        c_dec = ws.cell(row=idx, column=1)
        style_decision_cell(c_dec, default_decision, is_faded=is_already_defined)
        c_dec.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=2, value=default_target).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=3, value=role_id_str).alignment = ALIGN_CENTER

        c_delta = ws.cell(row=idx, column=4, value=delta_label)
        c_delta.font = FONT_GRAY_MUTED if is_already_defined else (FONT_PURPLE_DARK if "Splittable" in delta_label else FONT_GREEN_DARK)
        c_delta.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=5, value=display_role_name).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=6, value=r.get("approved_role_name") or suggested_name).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=7, value=r.get("owner_name") or DEFAULT_OWNER_FULLNAME).alignment = ALIGN_LEFT

        ws.cell(row=idx, column=8, value=f'=IF(G{idx}="","",XLOOKUP(G{idx},_Lookups_Reference!$B:$B,_Lookups_Reference!$A:$A,"⚠️ Invalid Full Name"))').font = FONT_FORMULA
        ws.cell(row=idx, column=9, value=f'=IF(G{idx}="","",XLOOKUP(G{idx},_Lookups_Reference!$B:$B,_Lookups_Reference!$C:$C,"⚠️ Invalid Full Name"))').font = FONT_FORMULA
        ws.cell(row=idx, column=10, value=f'=IF(G{idx}="","",XLOOKUP(G{idx},_Lookups_Reference!$B:$B,_Lookups_Reference!$E:$E,"⚠️ Invalid Full Name"))').font = FONT_FORMULA

        c_rule = ws.cell(row=idx, column=11, value=r["assignment_rule"])
        c_rule.alignment = ALIGN_LEFT
        c_rule.font = FONT_CODE_FADED if is_already_defined else FONT_CODE

        c_it_cont = ws.cell(row=idx, column=12, value=contained_it_str)
        c_it_cont.alignment = ALIGN_LEFT
        c_it_cont.font = FONT_GRAY_MUTED if is_already_defined else (FONT_PURPLE_DARK if "ITR-" in contained_it_str else FONT_GRAY_MUTED)

        ws.cell(row=idx, column=13, value=r["total_entitlements_count"]).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=14, value=r["target_population"]).alignment = ALIGN_CENTER

        c_conf = ws.cell(row=idx, column=15)
        style_confidence_cell(c_conf, float(r["avg_jaccard_score"]), is_faded=is_already_defined)
        c_conf.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=16, value=r.get("admin_notes") or "").alignment = ALIGN_LEFT

        c_act = ws.cell(row=idx, column=17, value=res_action)
        c_act.alignment = ALIGN_CENTER
        c_act.font = FONT_ACTION_BLUE
        dvs["action"].add(c_act)

        ws.cell(row=idx, column=18, value=h_type).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=19, value=parent_label).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=20, value=found_dt_str).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=21, value=decision_dt_str).alignment = ALIGN_CENTER

        dvs["role_decision"].add(ws.cell(row=idx, column=1))
        dvs["target"].add(ws.cell(row=idx, column=2))
        dvs["owner_fullname"].add(ws.cell(row=idx, column=7))

        for c in range(1, 22):
            cell = ws.cell(row=idx, column=c)
            cell.border = THIN_BORDER
            cell.fill = row_fill
            if is_already_defined:
                cell.font = MUTED_FONT
            elif c not in (1, 4, 11, 12, 15, 17):
                cell.font = FONT_DATA if c not in (8, 9, 10) else FONT_FORMULA


def build_business_role_entitlements_sheet(wb, biz_roles, biz_ents, ent_to_it_roles_list, biz_to_it_overlaps, biz_missing_users, biz_extra_users, dvs):
    """Builds Sheet 3: Business_Role_Entitlements."""
    ws = wb.create_sheet(title="Business_Role_Entitlements")
    ws.views.sheetView[0].showGridLines = True
    ws.add_data_validation(dvs["ent_action"])

    ws.cell(row=2, column=1, value="Fine-Grained Business Role Entitlement Actions (Select ACCEPT, DENY, IGNORE, or SPLIT in Col A)").font = FONT_TITLE
    headers = [
        "Action (ACCEPT/DENY/IGNORE/SPLIT)", "Role ID", "Suggested Role Name", "Approved Model Delta", "Match Tier", "Cohort Coverage",
        "Entitlement Name", "Target Application", "Associated IT Role ID", "Associated IT Role Name",
        "Modularization Opportunity", "Jaccard %",
        "Missing (Grant)", "Missing Users Details (Grant Roster)",
        "Extra (Revoke)", "Extra Users Details (Revocation Roster)",
        "Deployment Impact / Split Info", "Admin Notes", "Found Date", "Decision Date"
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_BLUE
        cell.alignment = ALIGN_CENTER

    role_meta_map = {r["id"]: (f"BR-{r['id']:04d}", r["role_name"], r["target_population"], r["assignment_rule"]) for r in biz_roles}
    current_biz_role_id = None
    biz_role_toggle = 0

    for idx, e in enumerate(biz_ents, 5):
        r_id = e["role_id"]
        if r_id != current_biz_role_id:
            current_biz_role_id = r_id
            biz_role_toggle = 1 - biz_role_toggle

        is_already = bool(e.get("already_in_role", False))
        stripe_fill = FILL_WHITE if biz_role_toggle == 1 else FILL_LIGHT_BLUE
        row_fill = GREY_OUT_FILL if is_already else stripe_fill

        rid_tuple = role_meta_map.get(r_id, (f"BR-{r_id:04d}", "Unknown Role", 0, ""))
        role_id_str, r_name, target_pop, parent_rule = rid_tuple
        jaccard_val = float(e["jaccard_score"])
        missing_cnt = e["missing_users_count"]
        extra_cnt = e["extra_users_count"]
        e_name = e["entitlement_name"].strip()
        e_norm = e_name.lower()
        found_dt_str = format_found_date(e.get("found_date"))
        decision_dt_str = format_decision_date(e.get("decision_date"), e.get("found_date"))

        cohort_holders = max(0, target_pop - missing_cnt)
        cov_pct = (cohort_holders / target_pop * 100.0) if target_pop > 0 else 100.0

        delta_str = "⚪ In Approved Role" if is_already else ("✂️ Splittable Rule" if is_splittable_rule(parent_rule) else "✨ Net-New Proposal")
        delta_font = FONT_GRAY_MUTED if is_already else (FONT_PURPLE_DARK if "Splittable" in delta_str else FONT_GREEN_DARK)

        if missing_cnt == 0 and extra_cnt == 0:
            tier = "🟢 EXACT (100%)"
            tier_font = FONT_GRAY_MUTED if is_already else FONT_GREEN_DARK
        elif missing_cnt == 0:
            tier = "⭐ 100% ADOPTED"
            tier_font = FONT_GRAY_MUTED if is_already else FONT_OLIVE_DARK
        else:
            tier = f"🟡 FUZZY ({jaccard_val*100:.1f}%)"
            tier_font = FONT_GRAY_MUTED if is_already else FONT_AMBER_DARK

        it_matches = ent_to_it_roles_list.get(e_norm, [])
        if it_matches:
            best_match = it_matches[0]
            it_id_str = best_match["it_role_id_str"]
            it_name_str = best_match["it_role_name"]
            cov_info = biz_to_it_overlaps.get(r_id, {}).get(best_match["it_role_id"], {})
            b_cnt = cov_info.get("containment_pct", 0)
            if b_cnt >= 99.9:
                mod_opp = f"🟢 FULL IT BUNDLE ({best_match['total_ents']}/{best_match['total_ents']} Perms)"
                mod_font = FONT_GRAY_MUTED if is_already else FONT_GREEN_DARK
            else:
                mod_opp = f"🟡 PARTIAL IT BUNDLE ({cov_info.get('shared_count', 1)}/{best_match['total_ents']} Perms)"
                mod_font = FONT_GRAY_MUTED if is_already else FONT_AMBER_DARK
        else:
            it_id_str = "Standalone"
            it_name_str = "Direct / Standalone Permission"
            mod_opp = "⚪ Standalone Entitlement"
            mod_font = FONT_GRAY_MUTED

        missing_user_list = biz_missing_users.get((r_id, e_norm), [])
        extra_user_list = biz_extra_users.get((r_id, e_norm), [])
        missing_details_str = build_user_roster_string(missing_user_list, "None (All cohort members already hold access)")
        extra_details_str = build_user_roster_string(extra_user_list, "None (Zero rogue / extra access)")

        base_impact = "🟢 ZERO IMPACT (0 Grants)" if missing_cnt == 0 else f"🟡 GRANTS ({missing_cnt} users)"
        deploy_impact = f"{base_impact} | ✂️ SPLIT reallocates to individual rules: {parent_rule}" if is_splittable_rule(parent_rule) else base_impact
        impact_font = FONT_GRAY_MUTED if is_already else (FONT_GREEN_DARK if missing_cnt == 0 else FONT_AMBER_DARK)

        inc_val = "ACCEPT" if is_already else ("DENY" if e.get("is_included") == 0 else "ACCEPT")
        c_inc = ws.cell(row=idx, column=1)
        style_decision_cell(c_inc, inc_val, is_faded=is_already)
        c_inc.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=2, value=role_id_str).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=3, value=r_name).alignment = ALIGN_LEFT

        c_delta = ws.cell(row=idx, column=4, value=delta_str)
        c_delta.font = delta_font
        c_delta.alignment = ALIGN_CENTER

        c_tier = ws.cell(row=idx, column=5, value=tier)
        c_tier.font = tier_font
        c_tier.alignment = ALIGN_LEFT

        c_cov = ws.cell(row=idx, column=6)
        style_coverage_cell(c_cov, cov_pct, cohort_holders, target_pop, is_faded=is_already)
        c_cov.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=7, value=e["entitlement_name"]).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=8, value=e["source_name"]).alignment = ALIGN_LEFT

        c_it_id = ws.cell(row=idx, column=9, value=it_id_str)
        c_it_id.alignment = ALIGN_CENTER
        c_it_id.font = FONT_GRAY_MUTED if is_already else (FONT_PURPLE_DARK if it_id_str != "Standalone" else FONT_GRAY_MUTED)

        c_it_name = ws.cell(row=idx, column=10, value=it_name_str)
        c_it_name.alignment = ALIGN_LEFT
        c_it_name.font = FONT_GRAY_MUTED if is_already else (FONT_PURPLE_DARK if it_id_str != "Standalone" else FONT_GRAY_MUTED)

        c_mod = ws.cell(row=idx, column=11, value=mod_opp)
        c_mod.alignment = ALIGN_LEFT
        c_mod.font = mod_font

        c_jacc = ws.cell(row=idx, column=12)
        style_confidence_cell(c_jacc, jaccard_val, is_faded=is_already)
        c_jacc.alignment = ALIGN_CENTER

        c_miss = ws.cell(row=idx, column=13)
        style_missing_cell(c_miss, missing_cnt, is_faded=is_already)
        c_miss.alignment = ALIGN_CENTER

        c_miss_details = ws.cell(row=idx, column=14, value=missing_details_str)
        c_miss_details.alignment = ALIGN_LEFT_WRAP
        c_miss_details.font = FONT_GRAY_MUTED if (is_already or missing_cnt == 0) else FONT_DATA

        c_extra = ws.cell(row=idx, column=15)
        style_extra_cell(c_extra, extra_cnt, is_faded=is_already)
        c_extra.alignment = ALIGN_CENTER

        c_extra_details = ws.cell(row=idx, column=16, value=extra_details_str)
        c_extra_details.alignment = ALIGN_LEFT_WRAP
        c_extra_details.font = FONT_GRAY_MUTED if (is_already or extra_cnt == 0) else FONT_DATA

        c_impact = ws.cell(row=idx, column=17, value=deploy_impact)
        c_impact.alignment = ALIGN_LEFT
        c_impact.font = impact_font

        ws.cell(row=idx, column=18, value="").alignment = ALIGN_LEFT
        ws.cell(row=idx, column=19, value=found_dt_str).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=20, value=decision_dt_str).alignment = ALIGN_CENTER

        dvs["ent_action"].add(ws.cell(row=idx, column=1))

        for col_idx in range(1, 21):
            cell = ws.cell(row=idx, column=col_idx)
            cell.border = THIN_BORDER
            cell.fill = row_fill
            if is_already:
                cell.font = MUTED_FONT
            elif col_idx not in (1, 4, 5, 6, 9, 10, 11, 12, 13, 14, 15, 16, 17):
                cell.font = FONT_DATA

    return role_meta_map


def build_overlap_matrix_sheet(wb, overlap_matrix_records):
    """Builds Sheet 4: Role_Hierarchy_Overlap."""
    ws = wb.create_sheet(title="Role_Hierarchy_Overlap")
    ws.views.sheetView[0].showGridLines = True
    ws.cell(row=2, column=1, value="Role Hierarchy Decomposition & Containment Matrix (Business <-> IT Roles)").font = FONT_TITLE
    headers = [
        "Business Role ID", "Business Role Name", "Contained IT Role ID", "Contained IT Role Name",
        "Target Application", "Containment %", "Shared Permissions", "IT Role Total Perms",
        "Business Role Total Perms", "Architectural Recommendation", "Missing Perms from Business Role"
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_EMERALD
        cell.alignment = ALIGN_CENTER

    for idx, r in enumerate(overlap_matrix_records, 5):
        row_fill = FILL_WHITE if idx % 2 != 0 else FILL_LIGHT_BLUE
        pct = r["containment_pct"]
        ws.cell(row=idx, column=1, value=r["biz_id_str"]).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=2, value=r["biz_name"]).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=3, value=r["it_id_str"]).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=4, value=r["it_name"]).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=5, value=r["it_source"]).alignment = ALIGN_LEFT

        c_pct = ws.cell(row=idx, column=6)
        style_confidence_cell(c_pct, pct)
        c_pct.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=7, value=r["shared_count"]).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=8, value=r["it_total"]).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=9, value=r["biz_total"]).alignment = ALIGN_CENTER

        c_rec = ws.cell(row=idx, column=10, value=r["recommendation"])
        c_rec.alignment = ALIGN_LEFT
        c_rec.font = FONT_GREEN_DARK if pct >= 99.9 else FONT_AMBER_DARK

        c_miss = ws.cell(row=idx, column=11, value=r["missing_str"])
        c_miss.alignment = ALIGN_LEFT
        c_miss.font = FONT_GRAY_MUTED if "None" in r["missing_str"] else FONT_AMBER_DARK

        for c in range(1, 12):
            cell = ws.cell(row=idx, column=c)
            cell.border = THIN_BORDER
            cell.fill = row_fill
            if c not in (6, 10, 11):
                cell.font = FONT_DATA


def build_it_roles_sheet(wb, it_roles, it_to_biz_overlaps, role_meta_map, dvs):
    """Builds Sheet 5: IT_Roles_Review with full already_defined support."""
    ws = wb.create_sheet(title="IT_Roles_Review")
    ws.views.sheetView[0].showGridLines = True
    ws.add_data_validation(dvs["role_decision"])
    ws.add_data_validation(dvs["target"])
    ws.add_data_validation(dvs["owner_fullname"])

    ws.cell(row=2, column=1, value="IT Roles & Functional Access Profiles Review").font = FONT_TITLE
    headers = [
        "Decision (ACCEPT/DENY/IGNORE)", "Deploy Target", "IT Role ID", "Role Definition Delta",
        "Suggested IT Role Name", "Final Role Name (Override)",
        "Assigned Owner (Fullname)", "Owner UUID (Auto)", "Contained In Business Roles",
        "Primary Application", "Permissions Count",
        "Full Holders (100%)", "Partial Candidates", "Cluster Cohesion",
        "Admin Review Notes", "Found Date", "Decision Date"
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_INDIGO
        cell.alignment = ALIGN_CENTER

    it_role_row_map = {}
    for idx, r in enumerate(it_roles, 5):
        it_id = r["id"]
        role_id_str = f"ITR-{it_id:04d}"
        suggested_name = r["it_role_name"]
        it_role_row_map[it_id] = (role_id_str, suggested_name, r["full_holders_count"])

        raw_status = str(r.get("approval_status") or "").upper()
        is_already_defined = bool(r.get("already_defined", False)) or raw_status in ("ALREADY_IN_PROD", "DEPLOYED")

        stripe_fill = FILL_WHITE if idx % 2 != 0 else FILL_LIGHT_BLUE
        row_fill = GREY_OUT_FILL if is_already_defined else stripe_fill

        found_dt_str = format_found_date(r.get("found_date"))
        decision_dt_str = format_decision_date(r.get("decision_date"), r.get("found_date"), r.get("approval_status"))

        it_overlaps = it_to_biz_overlaps.get(it_id, {})
        parent_biz_list = []
        for b_id, ov in it_overlaps.items():
            b_name_short = role_meta_map.get(b_id, (f"BR-{b_id}", "BR", 0, ""))
            if ov["containment_pct"] >= 99.9:
                parent_biz_list.append(f"🟢 [BR-{b_id:04d}] {b_name_short} (100%)")
            elif ov["containment_pct"] >= 75.0:
                parent_biz_list.append(f"🟡 [BR-{b_id:04d}] {b_name_short} ({ov['containment_pct']:.0f}%)")
        parent_biz_str = " | ".join(parent_biz_list) if parent_biz_list else "None (Independent)"

        if is_already_defined:
            default_decision = "ALREADY_IN_PROD"
        elif raw_status in ("APPROVED", "ACCEPT", "PENDING_REVIEW", ""):
            default_decision = "ACCEPT"
        elif raw_status in ("REJECTED", "DENY"):
            default_decision = "DENY"
        else:
            default_decision = raw_status

        default_target = r.get("deploy_target") or ("SKIP" if is_already_defined else "BOTH")
        delta_label = "⚪ Already in Prod" if is_already_defined else "✨ Net-New IT Role"

        # Col 1: Decision
        c_dec = ws.cell(row=idx, column=1)
        style_decision_cell(c_dec, default_decision, is_faded=is_already_defined)
        c_dec.alignment = ALIGN_CENTER

        # Col 2: Deploy Target
        ws.cell(row=idx, column=2, value=default_target).alignment = ALIGN_CENTER

        # Col 3: IT Role ID
        ws.cell(row=idx, column=3, value=role_id_str).alignment = ALIGN_CENTER

        # Col 4: Role Definition Delta
        c_delta = ws.cell(row=idx, column=4, value=delta_label)
        c_delta.font = FONT_GRAY_MUTED if is_already_defined else FONT_GREEN_DARK
        c_delta.alignment = ALIGN_CENTER

        # Col 5 & 6: Suggested Name & Override Name
        ws.cell(row=idx, column=5, value=suggested_name).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=6, value=r.get("approved_role_name") or suggested_name).alignment = ALIGN_LEFT

        # Col 7 & 8: Owner Name & Auto XLOOKUP UUID
        ws.cell(row=idx, column=7, value=r.get("owner_name") or DEFAULT_OWNER_FULLNAME).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=8, value=f'=IF(G{idx}="","",XLOOKUP(G{idx},_Lookups_Reference!$B:$B,_Lookups_Reference!$A:$A,"⚠️ Invalid Full Name"))').font = FONT_FORMULA

        # Col 9: Contained In Business Roles
        c_biz_parent = ws.cell(row=idx, column=9, value=parent_biz_str)
        c_biz_parent.alignment = ALIGN_LEFT
        c_biz_parent.font = FONT_GRAY_MUTED if is_already_defined else (FONT_PURPLE_DARK if "BR-" in parent_biz_str else FONT_GRAY_MUTED)

        # Col 10-13: Source, Counts, Cohesion
        ws.cell(row=idx, column=10, value=r["primary_source"]).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=11, value=r["entitlements_count"]).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=12, value=r["full_holders_count"]).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=13, value=r["partial_holders_count"]).alignment = ALIGN_CENTER

        c_coh = ws.cell(row=idx, column=14)
        style_confidence_cell(c_coh, float(r["bundle_cohesion_score"]), is_faded=is_already_defined)
        c_coh.alignment = ALIGN_CENTER

        # Col 15-17: Notes, Found Date, Decision Date
        ws.cell(row=idx, column=15, value=r.get("admin_notes") or "").alignment = ALIGN_LEFT
        ws.cell(row=idx, column=16, value=found_dt_str).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=17, value=decision_dt_str).alignment = ALIGN_CENTER

        dvs["role_decision"].add(ws.cell(row=idx, column=1))
        dvs["target"].add(ws.cell(row=idx, column=2))
        dvs["owner_fullname"].add(ws.cell(row=idx, column=7))

        for col_idx in range(1, 18):
            cell = ws.cell(row=idx, column=col_idx)
            cell.border = THIN_BORDER
            cell.fill = row_fill
            if is_already_defined:
                cell.font = MUTED_FONT
            elif col_idx not in (1, 4, 9, 14):
                cell.font = FONT_DATA if col_idx != 8 else FONT_FORMULA

    return it_role_row_map


def build_it_role_entitlements_sheet(wb, it_ents, it_role_row_map, it_ent_missing_users, it_ent_extra_users, dvs):
    """Builds Sheet 6: IT_Role_Entitlements."""
    ws = wb.create_sheet(title="IT_Role_Entitlements")
    ws.views.sheetView[0].showGridLines = True
    ws.add_data_validation(dvs["yesno"])

    ws.cell(row=2, column=1, value="Fine-Grained IT Role Entitlement Selection & Cluster Exception Rosters").font = FONT_TITLE
    headers = [
        "Action (ACCEPT/DENY/IGNORE)", "IT Role ID", "Suggested IT Role Name", "Approved Model Delta", "Entitlement Name",
        "Target Application", "Enterprise Assignments",
        "Missing in Cluster (Count)", "Missing Users Details (Partial Candidates lacking permission)",
        "Extra / Standalone Holders (Count)", "Extra Users Details (Standalone Holders outside cluster)",
        "Bundle Penetration %", "Admin Notes", "Found Date", "Decision Date"
    ]
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=4, column=col_idx, value=h)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER_PURPLE
        cell.alignment = ALIGN_CENTER

    current_it_role_id = None
    it_role_toggle = 0

    for idx, e in enumerate(it_ents, 5):
        r_id = e["it_role_id"]
        if r_id != current_it_role_id:
            current_it_role_id = r_id
            it_role_toggle = 1 - it_role_toggle

        is_already = bool(e.get("already_in_role", False))
        stripe_fill = FILL_WHITE if it_role_toggle == 1 else FILL_LIGHT_BLUE
        row_fill = GREY_OUT_FILL if is_already else stripe_fill

        rid_tuple = it_role_row_map.get(r_id, (f"ITR-{r_id:04d}", "Unknown IT Role", 0))
        role_id_str, r_name, full_holders = rid_tuple
        assignments = e["assignment_count"]
        e_norm = e["entitlement_name"].strip().lower()
        penetration = (full_holders / assignments * 100.0) if assignments > 0 else 100.0
        found_dt_str = format_found_date(e.get("found_date"))
        decision_dt_str = format_decision_date(e.get("decision_date"), e.get("found_date"))

        it_miss_list = it_ent_missing_users.get((r_id, e_norm), [])
        it_extra_list = it_ent_extra_users.get((r_id, e_norm), [])
        it_miss_str = build_user_roster_string(it_miss_list, "None (All cluster members hold this permission)")
        it_extra_str = build_user_roster_string(it_extra_list, "None (Zero standalone holders outside cluster)")

        delta_str = "⚪ In Approved Role" if is_already else "✨ Net-New Proposal"
        delta_font = FONT_GRAY_MUTED if is_already else FONT_GREEN_DARK

        inc_val = "ACCEPT" if is_already else ("DENY" if e.get("is_included") == 0 else "ACCEPT")
        c_inc = ws.cell(row=idx, column=1)
        style_decision_cell(c_inc, inc_val, is_faded=is_already)
        c_inc.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=2, value=role_id_str).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=3, value=r_name).alignment = ALIGN_LEFT

        c_delta = ws.cell(row=idx, column=4, value=delta_str)
        c_delta.font = delta_font
        c_delta.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=5, value=e["entitlement_name"]).alignment = ALIGN_LEFT
        ws.cell(row=idx, column=6, value=e["source_name"] or "Unknown").alignment = ALIGN_LEFT
        ws.cell(row=idx, column=7, value=assignments).alignment = ALIGN_CENTER

        c_it_miss = ws.cell(row=idx, column=8)
        style_missing_cell(c_it_miss, len(it_miss_list), is_faded=is_already)
        c_it_miss.alignment = ALIGN_CENTER

        c_it_miss_dt = ws.cell(row=idx, column=9, value=it_miss_str)
        c_it_miss_dt.alignment = ALIGN_LEFT_WRAP
        c_it_miss_dt.font = FONT_GRAY_MUTED if (is_already or len(it_miss_list) == 0) else FONT_DATA

        c_it_extra = ws.cell(row=idx, column=10)
        style_extra_cell(c_it_extra, len(it_extra_list), is_faded=is_already)
        c_it_extra.alignment = ALIGN_CENTER

        c_it_extra_dt = ws.cell(row=idx, column=11, value=it_extra_str)
        c_it_extra_dt.alignment = ALIGN_LEFT_WRAP
        c_it_extra_dt.font = FONT_GRAY_MUTED if (is_already or len(it_extra_list) == 0) else FONT_DATA

        c_pen = ws.cell(row=idx, column=12)
        style_confidence_cell(c_pen, penetration / 100.0, is_faded=is_already)
        c_pen.alignment = ALIGN_CENTER

        ws.cell(row=idx, column=13, value="").alignment = ALIGN_LEFT
        ws.cell(row=idx, column=14, value=found_dt_str).alignment = ALIGN_CENTER
        ws.cell(row=idx, column=15, value=decision_dt_str).alignment = ALIGN_CENTER

        dvs["yesno"].add(ws.cell(row=idx, column=1))

        for col_idx in range(1, 16):
            cell = ws.cell(row=idx, column=col_idx)
            cell.border = THIN_BORDER
            cell.fill = row_fill
            if is_already:
                cell.font = MUTED_FONT
            elif col_idx not in (1, 4, 8, 9, 10, 11, 12):
                cell.font = FONT_DATA


def create_styled_workbook(
    biz_roles, biz_ents, it_roles, it_ents, lookup_owners,
    ent_to_it_roles_list, biz_to_it_overlaps, it_to_biz_overlaps,
    it_role_meta, overlap_matrix_records,
    biz_missing_users, biz_extra_users,
    it_ent_missing_users, it_ent_extra_users,
    filename=OUTPUT_EXCEL
):
    print("🎨 Generating Excel workbook with ACCEPT/DENY/IGNORE/SPLIT actions on Roles & Entitlements...")
    wb = openpyxl.Workbook()
    wb.remove(wb.active)

    max_lookup_row = len(lookup_owners) + 1
    dvs = build_validations(max_lookup_row)

    build_lookups_sheet(wb, lookup_owners)
    build_executive_summary_sheet(wb)
    build_business_roles_sheet(wb, biz_roles, biz_to_it_overlaps, it_role_meta, dvs)
    role_meta_map = build_business_role_entitlements_sheet(
        wb, biz_roles, biz_ents, ent_to_it_roles_list,
        biz_to_it_overlaps, biz_missing_users, biz_extra_users, dvs
    )
    build_overlap_matrix_sheet(wb, overlap_matrix_records)
    it_role_row_map = build_it_roles_sheet(wb, it_roles, it_to_biz_overlaps, role_meta_map, dvs)
    build_it_role_entitlements_sheet(
        wb, it_ents, it_role_row_map,
        it_ent_missing_users, it_ent_extra_users, dvs
    )

    auto_fit_workbook_columns(wb)

    os.makedirs(os.path.dirname(filename) or ".", exist_ok=True)
    wb.save(filename)
    print(f"✅ Successfully generated Excel Workbook with ACCEPT/DENY/IGNORE/SPLIT at: '{filename}'")


if __name__ == "__main__":
    staging_data = load_staging_data()
    create_styled_workbook(*staging_data, filename=OUTPUT_EXCEL)
