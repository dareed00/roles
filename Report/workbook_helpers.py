#!/usr/bin/env python3
"""
RoleMiner - Workbook Date, Rule, and Roster Formatting Helpers
File: Scripts/Report/workbook_helpers.py
"""

import re
from datetime import datetime, date
from collections import defaultdict


def parse_hire_date(date_str):
    if not date_str:
        return None, "Unknown"
    clean_str = str(date_str).strip()
    formats = [
        "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y/%m/%d", "%m/%d/%Y",
        "%d-%m-%Y", "%Y%m%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"
    ]
    parsed_date = None
    for fmt in formats:
        try:
            parsed_date = datetime.strptime(clean_str.split(".")[0], fmt).date()
            break
        except (ValueError, TypeError):
            continue
    if not parsed_date:
        return None, clean_str
    days_ago = (date.today() - parsed_date).days
    return days_ago, parsed_date.strftime("%Y-%m-%d")


def format_found_date(dt_val):
    if not dt_val:
        return datetime.now().strftime("%Y-%m-%d %H:%M")
    if isinstance(dt_val, datetime):
        return dt_val.strftime("%Y-%m-%d %H:%M")
    if isinstance(dt_val, date):
        return dt_val.strftime("%Y-%m-%d")
    clean = str(dt_val).strip().replace("T", " ").rstrip("Z")
    if "." in clean:
        clean = clean.split(".")[0]
    return clean[:16] if len(clean) >= 16 else clean


def format_decision_date(decision_dt, found_dt=None, status=None):
    if not decision_dt:
        return "Pending"
    if status and str(status).upper() == "PENDING_REVIEW" and found_dt and str(decision_dt) == str(found_dt):
        return "Pending"
    if isinstance(decision_dt, datetime):
        return decision_dt.strftime("%Y-%m-%d %H:%M")
    if isinstance(decision_dt, date):
        return decision_dt.strftime("%Y-%m-%d")
    clean = str(decision_dt).strip().replace("T", " ").rstrip("Z")
    if "." in clean:
        clean = clean.split(".")[0]
    return clean[:16] if len(clean) >= 16 else clean


def is_splittable_rule(assignment_rule_str):
    """Returns True if the assignment rule contains multiple attribute clauses (IN, OR, AND)."""
    if not assignment_rule_str:
        return False
    rule = str(assignment_rule_str)
    if re.search(r"\bIN\s*\(", rule, flags=re.IGNORECASE):
        return True
    if re.search(r"\b(OR|AND)\b", rule, flags=re.IGNORECASE):
        return True
    return False


def format_user_summary(prof):
    name = prof.get("name", "Unknown")
    uid = prof.get("uid", "Unknown")
    state = prof.get("state_clean", "ACTIVE")
    title = prof.get("title", "Unknown Title")
    dept = prof.get("department", "Unknown Dept")
    days_ago = prof.get("days_ago")
    state_badge = (
        "[🟢 ACTIVE]" if state == "ACTIVE"
        else ("[🔴 INACTIVE]" if state in ("INACTIVE", "TERMINATED") else f"[{state}]")
    )

    if days_ago is not None and 0 <= days_ago <= 30:
        tenure_badge = f"[🐣 New Hire: {days_ago}d ago]"
    elif days_ago is not None:
        tenure_badge = f"[{days_ago:,}d ago]"
    else:
        tenure_badge = "[Tenure: Unknown]"
    return f"{name} ({uid}) {state_badge} - {title}, {dept} {tenure_badge}"


def build_user_roster_string(user_list, zero_label):
    if not user_list:
        return zero_label
    lines = []
    for idx, prof in enumerate(user_list[:6], start=1):
        lines.append(f"{idx}. {format_user_summary(prof)}")
    if len(user_list) > 6:
        lines.append(f"... and {len(user_list) - 6} more users.")
    return "\n".join(lines)


def order_roles_with_dynamic_subtiers(roles_rows):
    parents = []
    subtiers_by_parent = defaultdict(list)
    for r in roles_rows:
        p_id = r.get("parent_role_id")
        if p_id:
            subtiers_by_parent[p_id].append(r)
        else:
            parents.append(r)
    ordered = []
    for p in parents:
        ordered.append(p)
        children = subtiers_by_parent.get(p["id"], [])
        for c in children:
            ordered.append(c)
    return ordered
