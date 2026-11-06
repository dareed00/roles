from itertools import combinations
from collections import defaultdict

def find_same_attribute_unions_for_entitlement(ent_uids, attr_to_uids, min_jaccard=0.75):
    """
    Finds pairs of values of the SAME attribute whose UNION matches an entitlement.
    Example: location IN ('Detroit', 'Flint') -> Entitlement Population
    """
    ent_pop = len(ent_uids)
    if ent_pop == 0:
        return []

    # Group attribute values by attribute name (e.g., group all locations together)
    attrs_by_name = defaultdict(dict)
    for attr_key, uids in attr_to_uids.items():
        attr_name, attr_val = attr_key.split("=", 1)
        intersection = len(uids & ent_uids)
        if intersection > 0:  # Only consider values present in this entitlement
            attrs_by_name[attr_name][attr_val] = {
                "uids": uids,
                "intersection": intersection,
                "pop": len(uids)
            }

    winning_unions = []

    # Evaluate pairwise unions within each attribute family
    for attr_name, val_dict in attrs_by_name.items():
        candidate_values = list(val_dict.keys())
        if len(candidate_values) < 2:
            continue

        for v1, v2 in combinations(candidate_values, 2):
            # Fast Pruning: Skip if individual overlaps don't sum to at least 70% of entitlement
            inter1 = val_dict[v1]["intersection"]
            inter2 = val_dict[v2]["intersection"]
            if (inter1 + inter2) < (ent_pop * 0.70):
                continue

            # Compute actual union
            uids_v1 = val_dict[v1]["uids"]
            uids_v2 = val_dict[v2]["uids"]
            union_uids = uids_v1 | uids_v2

            # Calculate union metrics
            intersection = len(union_uids & ent_uids)
            union_total = len(union_uids | ent_uids)
            jaccard = intersection / union_total if union_total > 0 else 0

            if jaccard >= min_jaccard:
                coverage = intersection / len(union_uids)
                purity = intersection / ent_pop

                winning_unions.append({
                    "attribute_name": attr_name,
                    "values": [v1, v2],
                    "assignment_rule": f"{attr_name} IN ('{v1}', '{v2}')",
                    "role_name": f"All {v1} & {v2} {attr_name.capitalize()}s",
                    "union_population": len(union_uids),
                    "entitlement_population": ent_pop,
                    "coverage": coverage,
                    "purity": purity,
                    "jaccard": jaccard
                })

    winning_unions.sort(key=lambda x: x["jaccard"], reverse=True)
    return winning_unions
