import time
import numpy as np
import pandas as pd
from scipy.sparse import csr_matrix
import mysql.connector
from mysql.connector import Error

# ==========================================
# 1. DATABASE CONFIGURATION
# ==========================================
DB_CONFIG = {
    'host': 'localhost',
    'user': 'root',
    'password': 'your_password',
    'database': 'bundleBuilder',
    'raise_on_warnings': True,
    'autocommit': False
}

BATCH_SIZE = 10000

# ==========================================
# 2. DATA EXTRACTION & MATRIX BUILDER
# ==========================================
def load_data_and_build_matrix(conn, grouping_column='department'):
    """
    Loads raw identity access and demographics, constructing sparse binary matrices.
    """
    print(f"[*] Extracting raw data from excel_raw_data for grouping: '{grouping_column}'...")
    
    # Load core access mappings and demographic metadata
    query = f"""
        SELECT 
            UID,
            {grouping_column} AS primary_value,
            Attribute_Value_Name,
            Access_Source_Name,
            type,
            Is_Manager,
            country,
            department,
            jobTitle,
            location
        FROM excel_raw_data
        WHERE UID IS NOT NULL 
          AND Attribute_Value_Name IS NOT NULL 
          AND Access_Source_Name IS NOT NULL;
    """
    df = pd.read_sql(query, conn)
    
    if df.empty:
        raise ValueError("No records found in excel_raw_data.")

    # Unique demographic metadata per UID for outlier tracking
    user_meta = df[['UID', 'type', 'Is_Manager', 'country', 'department', 'jobTitle', 'location']].drop_duplicates(subset=['UID']).set_index('UID')
    
    # Index UIDs
    unique_uids = df['UID'].unique()
    uid_to_idx = {uid: idx for idx, uid in enumerate(unique_uids)}
    idx_to_uid = {idx: uid for idx, uid in enumerate(unique_uids)}
    n_users = len(unique_uids)

    # 1. Construct Primary Grouping Binary Matrix (e.g. Department -> Users)
    primary_df = df[['UID', 'primary_value']].dropna().drop_duplicates()
    unique_primaries = primary_df['primary_value'].unique()
    primary_to_idx = {val: idx for idx, val in enumerate(unique_primaries)}
    idx_to_primary = {idx: val for idx, val in enumerate(unique_primaries)}
    
    prim_row = [uid_to_idx[u] for u in primary_df['UID']]
    prim_col = [primary_to_idx[p] for p in primary_df['primary_value']]
    mat_primary = csr_matrix((np.ones(len(prim_row), dtype=np.int8), (prim_row, prim_col)), shape=(n_users, len(unique_primaries)))

    # 2. Construct Access Item Binary Matrix (e.g. Attribute+Source -> Users)
    df['access_key'] = df['Attribute_Value_Name'] + "|||" + df['Access_Source_Name']
    access_df = df[['UID', 'access_key', 'Attribute_Value_Name', 'Access_Source_Name']].drop_duplicates()
    
    # Filter birthright noise (>95% population) and singleton noise (<3 users)
    counts = access_df['access_key'].value_counts()
    valid_keys = counts[(counts >= 3) & (counts <= (0.95 * n_users))].index
    access_df = access_df[access_df['access_key'].isin(valid_keys)]

    unique_access = access_df[['access_key', 'Attribute_Value_Name', 'Access_Source_Name']].drop_duplicates()
    access_to_idx = {row['access_key']: idx for idx, row in unique_access.reset_index(drop=True).iterrows()}
    idx_to_access = {idx: row for idx, row in unique_access.reset_index(drop=True).iterrows()}
    
    acc_row = [uid_to_idx[u] for u in access_df['UID']]
    acc_col = [access_to_idx[k] for k in access_df['access_key']]
    mat_access = csr_matrix((np.ones(len(acc_row), dtype=np.int8), (acc_row, len(access_to_idx))), shape=(n_users, len(access_to_idx)))

    print(f"[*] Processed {n_users} Identities, {len(unique_primaries)} Primary Groups, {len(access_to_idx)} Access Items.")
    return (mat_primary, mat_access, idx_to_primary, idx_to_access, idx_to_uid, user_meta)

# ==========================================
# 3. VECTORIZED CORRELATION CALCULATION
# ==========================================
def compute_correlations(mat_primary, mat_access, idx_to_primary, idx_to_access, idx_to_uid, user_meta, grouping_col, min_jaccard=0.70):
    """
    Computes Exact (1.0) and Near-Identical Jaccard correlations using sparse matrix dot products.
    """
    print("[*] Computing intersections via Sparse Matrix Dot Product...")
    start_t = time.time()

    # Intersections: C[i, j] = |Primary_i ∩ Access_j|
    intersection_mat = (mat_primary.T @ mat_access).tocoo()

    # Set sizes
    size_primary = np.array(mat_primary.sum(axis=0)).flatten()
    size_access = np.array(mat_access.sum(axis=0)).flatten()

    exact_records = []
    near_records = []
    outlier_records = []

    print(f"[*] Evaluating {intersection_mat.nnz} non-zero intersection candidates...")

    for p_idx, a_idx, intersection in zip(intersection_mat.row, intersection_mat.col, intersection_mat.data):
        len_p = size_primary[p_idx]
        len_a = size_access[a_idx]

        # Length-bound filter
        if min(len_p, len_a) / max(len_p, len_a) < min_jaccard:
            continue

        union = len_p + len_a - intersection
        jaccard = intersection / union

        prim_val = idx_to_primary[p_idx]
        acc_info = idx_to_access[a_idx]
        attr_val = acc_info['Attribute_Value_Name']
        src_name = acc_info['Access_Source_Name']

        if jaccard == 1.0:
            exact_records.append((grouping_col, prim_val, attr_val, src_name, int(len_p)))
        elif jaccard >= min_jaccard:
            # Temporary ID placeholder for foreign key mapping
            corr_idx = len(near_records) + 1
            near_records.append((corr_idx, grouping_col, prim_val, attr_val, src_name, float(round(jaccard, 4)), int(len_p)))

            # Extract differing UIDs using bitwise boolean masks
            p_users = mat_primary[:, p_idx].toarray().flatten().astype(bool)
            a_users = mat_access[:, a_idx].toarray().flatten().astype(bool)

            in_p_only = np.where(p_users & (~a_users))[0]
            in_a_only = np.where(a_users & (~p_users))[0]

            for u_idx in in_p_only:
                uid = idx_to_uid[u_idx]
                meta = user_meta.loc[uid] if uid in user_meta.index else {}
                outlier_records.append((
                    corr_idx, uid, True, False,
                    meta.get('type', None), meta.get('Is_Manager', None), meta.get('country', None),
                    meta.get('department', None), meta.get('jobTitle', None), meta.get('location', None)
                ))

            for u_idx in in_a_only:
                uid = idx_to_uid[u_idx]
                meta = user_meta.loc[uid] if uid in user_meta.index else {}
                outlier_records.append((
                    corr_idx, uid, False, True,
                    meta.get('type', None), meta.get('Is_Manager', None), meta.get('country', None),
                    meta.get('department', None), meta.get('jobTitle', None), meta.get('location', None)
                ))

    print(f"[✓] Correlation compute finished in {time.time() - start_t:.2f}s.")
    print(f"    - Exact correlations found: {len(exact_records)}")
    print(f"    - Near-match correlations found: {len(near_records)}")
    print(f"    - Outlier identity rows generated: {len(outlier_records)}")

    return exact_records, near_records, outlier_records

# ==========================================
# 4. CHUNKED BULK INSERTION
# ==========================================
def bulk_insert_results(conn, exact_records, near_records, outlier_records):
    """
    Flushes calculation batches into MySQL using multi-row parameter arrays.
    """
    cursor = conn.cursor()
    print("[*] Writing results to database...")

    try:
        # 1. Insert Exact Correlations
        if exact_records:
            sql_exact = """
                INSERT INTO exact_correlations 
                (primary_grouping_column, primary_value, attribute_value, access_source_name, population_size)
                VALUES (%s, %s, %s, %s, %s)
            """
            for i in range(0, len(exact_records), BATCH_SIZE):
                cursor.executemany(sql_exact, exact_records[i:i + BATCH_SIZE])

        # 2. Insert Near Identical Correlations & Map Generated Auto IDs
        corr_id_map = {}
        if near_records:
            sql_near = """
                INSERT INTO near_identical_correlations 
                (primary_grouping_column, primary_value, attribute_value, access_source_name, jaccard_score, primary_population_size)
                VALUES (%s, %s, %s, %s, %s, %s)
            """
            for rec in near_records:
                temp_id, col, p_val, a_val, s_name, j_score, pop_size = rec
                cursor.execute(sql_near, (col, p_val, a_val, s_name, j_score, pop_size))
                corr_id_map[temp_id] = cursor.lastrowid

        # 3. Insert Outliers with true Foreign Key IDs
        if outlier_records:
            sql_outliers = """
                INSERT INTO near_match_differing_uids 
                (near_match_correlation_id, uid, is_in_primary_only, is_in_attribute_only, type, is_manager, country, department, jobTitle, location)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            remapped_outliers = [
                (corr_id_map[r[0]], r, r, r, r, r, r, r, r, r)
                for r in outlier_records if r[0] in corr_id_map
            ]

            for i in range(0, len(remapped_outliers), BATCH_SIZE):
                cursor.executemany(sql_outliers, remapped_outliers[i:i + BATCH_SIZE])

        conn.commit()
        print("[✓] All correlation records successfully persisted to MySQL.")

    except Error as e:
        conn.rollback()
        print(f"[!] Database write failure: {e}")
        raise
    finally:
        cursor.close()

# ==========================================
# 5. EXECUTION PIPELINE
# ==========================================
def run_pipeline():
    conn = mysql.connector.connect(**DB_CONFIG)
    try:
        # Run analysis across key organizational dimensions
        dimensions = ['department', 'jobTitle', 'location']
        
        for dim in dimensions:
            print(f"\n{'='*50}\nRUNNING CORRELATION PIPELINE FOR: {dim}\n{'='*50}")
            mat_p, mat_a, id_p, id_a, id_u, user_meta = load_data_and_build_matrix(conn, grouping_column=dim)
            
            exact_res, near_res, outlier_res = compute_correlations(
                mat_p, mat_a, id_p, id_a, id_u, user_meta,
                grouping_col=dim,
                min_jaccard=0.75
            )
            
            bulk_insert_results(conn, exact_res, near_res, outlier_res)

    finally:
        conn.close()

if __name__ == '__main__':
    run_pipeline()
