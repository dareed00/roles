# report_utils.py

import mysql.connector
from mysql.connector import Error
from openpyxl.styles import Font, Alignment, PatternFill

# --- Shared Configuration ---
USER_CONTEXT_ATTRIBUTES = ['jobTitle', 'department', 'type']


def get_entitlement_population_ids(cursor, entitlement_db_id):
    sql = """
    SELECT T2.id FROM IdentityEffectiveEntitlements_Filtered AS T1 JOIN Identities_Filtered AS T2 ON T1.identity_id = T2.id WHERE T1.entitlement_id = (SELECT entitlement_id FROM entitlements WHERE id = %s)
    UNION
    SELECT T2.id FROM IdentityEntitlementAssignments_Filtered AS T1 JOIN Identities_Filtered AS T2 ON T1.identity_id = T2.id WHERE T1.entitlement_id = (SELECT entitlement_id FROM entitlements WHERE id = %s)
    """
    cursor.execute(sql, (entitlement_db_id, entitlement_db_id))
    return {row['id'] for row in cursor.fetchall()}

def get_attribute_population_ids(cursor, attr_name, attr_value):
    sql = "SELECT identity_id FROM Identity_Attributes_Filtered WHERE attribute_name = %s AND attribute_value = %s"
    cursor.execute(sql, (attr_name, attr_value))
    return {row['identity_id'] for row in cursor.fetchall()}

def get_user_context(cursor, identity_ids):
    if not identity_ids: return {}
    context = {id: {'id': id} for id in identity_ids}
    id_placeholder = ', '.join(['%s'] * len(identity_ids))
    name_sql = f"SELECT id, name FROM Identities_Filtered WHERE id IN ({id_placeholder})"
    cursor.execute(name_sql, list(identity_ids))
    for row in cursor.fetchall():
        context[row['id']]['name'] = row['name']
    attr_placeholder = ', '.join(['%s'] * len(USER_CONTEXT_ATTRIBUTES))
    attr_sql = f"SELECT identity_id, attribute_name, attribute_value FROM Identity_Attributes_Filtered WHERE identity_id IN ({id_placeholder}) AND attribute_name IN ({attr_placeholder})"
    params = list(identity_ids) + USER_CONTEXT_ATTRIBUTES
    cursor.execute(attr_sql, params)
    for row in cursor.fetchall():
        context[row['identity_id']][row['attribute_name']] = row['attribute_value']
    return context

def get_parent_bundles(cursor, entitlement_db_id):
    parents = {'roles': [], 'access_profiles': []}
    role_sql = "SELECT T2.role_name FROM entitlements AS T1 JOIN CurrentRoleModel_RoleEffectiveEntitlements AS T2 ON T1.entitlement_id = T2.entitlement_id WHERE T1.id = %s"
    cursor.execute(role_sql, (entitlement_db_id,))
    parents['roles'] = [row['role_name'] for row in cursor.fetchall()]
    ap_sql = "SELECT T2.access_profile_name FROM entitlements AS T1 JOIN CurrentRoleModel_AccessProfileEntitlements AS T2 ON T1.entitlement_id = T2.entitlement_id WHERE T1.id = %s"
    cursor.execute(ap_sql, (entitlement_db_id,))
    parents['access_profiles'] = [row['access_profile_name'] for row in cursor.fetchall()]
    return parents

def get_assignment_breakdown(cursor, entitlement_id, total_population):
    sql = "SELECT COUNT(DISTINCT identity_id) as direct_count FROM IdentityEntitlementAssignments_Filtered WHERE entitlement_id = (SELECT entitlement_id FROM entitlements WHERE id = %s)"
    cursor.execute(sql, (entitlement_id,))
    direct_count = cursor.fetchone()['direct_count']
    indirect_count = total_population - direct_count
    return {'direct': direct_count, 'indirect': indirect_count}

def get_correlation_analysis(score, population):
    score_pct = f"{score:.2%}"
    if score == 1.0:
        return {'title': f"ABSOLUTE CORRELATION ({score_pct})", 'details': "PERFECT Correlation score..."}
    if population > 100 and score >= 0.92:
        return {'title': f"NEAR PERFECT CORRELATION ({score_pct})", 'details': f"NEAR PERFECT Correlation score..."}
    # (rest of analysis logic is correct)
    return {'title': f"{score_pct}", 'details': "Standard correlation."}

# --- Excel Styling & Formatting Helpers ---
def style_header(cell, text):
    cell.value = text
    cell.font = Font(bold=True, color="FFFFFF")
    cell.fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

def style_description(cell, text):
    cell.value = text
    cell.font = Font(italic=True, color="595959")
    cell.fill = PatternFill(start_color="D9D9D9", end_color="D9D9D9", fill_type="solid")
    cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    
def style_summary_header(cell, text):
    cell.value = text
    cell.font = Font(bold=True, size=14, color="4F81BD")
    cell.alignment = Alignment(horizontal="center", vertical="center")

def style_summary_value(cell, value):
    cell.value = value
    cell.font = Font(bold=True, size=18)
    cell.alignment = Alignment(horizontal="center", vertical="center")

def auto_fit_columns(worksheet):
    for col in worksheet.columns:
        max_length = 0
        for cell in col:
            try:
                if cell.value and len(str(cell.value)) > max_length: max_length = len(str(cell.value))
            except: pass
        adjusted_width = (max_length + 2) if max_length < 60 else 60
        worksheet.column_dimensions[col[0].column_letter].width = adjusted_width

def format_delta_text(user_context, user_ids):
    lines = [f"- {user_context[user_id].get('name', user_id)} ({', '.join(f'{attr.capitalize()}: {user_context[user_id].get(attr, 'N/A')}' for attr in USER_CONTEXT_ATTRIBUTES)})" for user_id in sorted(list(user_ids))[:5]]
    if len(user_ids) > 5: lines.append(f"- [{len(user_ids) - 5} more users...]")
    return "\n".join(lines)



def get_correlation_analysis(score, population):
    """Translates a Jaccard score into a human-readable analysis."""
    score_pct = f"{score:.2%}"
    
    if score == 1.0:
        return {'title': f"ABSOLUTE CORRELATION ({score_pct})", 'details': "PERFECT Correlation score. The population of users in the attribute or attribute combination overlaps 100% the population of this entitlement. This is absolutely an Access Member of this role."}
    
    if population > 100 and score >= 0.92:
        return {'title': f"NEAR PERFECT CORRELATION ({score_pct})", 'details': f"NEAR PERFECT Correlation score. The population of users with this attribute or attribute combination is over 100 and overlaps the population of this entitlement at a level of {score_pct}. This is most likely an Access Member of this role. Please review the missing members to see if perhaps these are new users, or new users to the attribute. (I.e. they still need to request the access to align with their peers, but for whatever reason have not yet.)"}
    
    if 80 < population <= 100 and score >= 0.90:
        return {'title': f"NEAR PERFECT CORRELATION ({score_pct})", 'details': "NEAR PERFECT SCORE"}
    
    if 50 < population <= 80 and score >= 0.80:
        return {'title': f"NEAR PERFECT CORRELATION ({score_pct})", 'details': "NEAR PERFECT SCORE"}
    
    if 50 < population <= 80 and 0.60 <= score < 0.80:
        return {'title': f"POSSIBLE CORRELATION ({score_pct})", 'details': "SCORE WORTH INVESTIGATING"}
    
    # This is the new default "catch-all" return statement
    return {'title': f"{score_pct}", 'details': "Standard correlation. Review delta for opportunities."}


# --- NEW: Function for Cohesion Analysis ---
def get_cohesion_analysis(score):
    """Translates a cohesion score into a human-readable analysis string."""
    score_pct = f"{score:.2%}"
    
    if score > 0.90:
        return f"Exceptional ({score_pct}). This is almost certainly a Business Role or IT Role"
    elif score > 0.70:
        return f"Strong ({score_pct}). This is most likely a Business Role or IT Role"
    elif score > 0.60:
        return f"High Moderate ({score_pct}). If the population is small, This is likely a Business Role or IT Role"
    elif score > 0.50:
        return f"Moderate ({score_pct}). If the population is small, this is may be a Business Role or IT Role"
    elif score > 0.40:
        return f"Low Moderate ({score_pct}). Unless the population is very small, this is not likely to be a Business Role or IT Role"
    else:
        return f"Low ({score_pct}). Unlikely to be a functional role."


