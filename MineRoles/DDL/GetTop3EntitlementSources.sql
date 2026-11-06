SELECT * FROM (
    SELECT 
        *,
        ROW_NUMBER() OVER(PARTITION BY entitlement_id ORDER BY jaccard_score DESC) as rn
    FROM Entitlement_to_Attribute_Correlations
) AS ranked_correlations
WHERE rn <= 3;