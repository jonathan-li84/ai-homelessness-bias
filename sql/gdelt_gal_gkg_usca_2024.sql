-- Full-year 2024 English homelessness-headline articles joined to GKG's
-- point-level California (USCA) location annotations.
--
-- The GAL predicate selects English headlines containing homelessness terms.
-- ADM1-only records (location_type = 2) are excluded because a state centroid
-- cannot be assigned meaningfully to a Continuum of Care.

WITH articles AS (
  SELECT
    date,
    url,
    domain,
    outletName AS publisher,
    title,
    `desc` AS description,
    lang AS language,
    author
  FROM `gdelt-bq.gdeltv2.gal`
  WHERE date >= TIMESTAMP("2024-01-01")
    AND date < TIMESTAMP("2025-01-01")
    AND LOWER(lang) IN ("en", "eng", "english")
    AND REGEXP_CONTAINS(
      LOWER(title),
      r"\b(?:homeless(?:ness)?|unhoused|people\s+experiencing\s+homelessness|homeless\s+population|homeless\s+residents)\b"
    )
)
SELECT DISTINCT
  a.date,
  a.url,
  a.domain,
  a.publisher,
  a.title,
  a.description,
  a.language,
  a.author,
  g.GKGRECORDID AS gkg_record_id,
  SAFE_CAST(SPLIT(location, "#")[SAFE_OFFSET(0)] AS INT64) AS location_type,
  SPLIT(location, "#")[SAFE_OFFSET(1)] AS location_name,
  SPLIT(location, "#")[SAFE_OFFSET(2)] AS country_code,
  SPLIT(location, "#")[SAFE_OFFSET(3)] AS adm1_code,
  SPLIT(location, "#")[SAFE_OFFSET(4)] AS adm2_code,
  SAFE_CAST(SPLIT(location, "#")[SAFE_OFFSET(5)] AS FLOAT64) AS latitude,
  SAFE_CAST(SPLIT(location, "#")[SAFE_OFFSET(6)] AS FLOAT64) AS longitude,
  SPLIT(location, "#")[SAFE_OFFSET(7)] AS feature_id,
  SAFE_CAST(SPLIT(location, "#")[SAFE_OFFSET(8)] AS INT64) AS character_offset
FROM articles AS a
JOIN `gdelt-bq.gdeltv2.gkg_partitioned` AS g
  ON g.DocumentIdentifier = a.url
 AND g._PARTITIONTIME >= TIMESTAMP("2024-01-01")
 AND g._PARTITIONTIME < TIMESTAMP("2025-01-02")
CROSS JOIN UNNEST(SPLIT(IFNULL(g.V2Locations, ""), ";")) AS location
WHERE SPLIT(location, "#")[SAFE_OFFSET(2)] = "US"
  AND SPLIT(location, "#")[SAFE_OFFSET(3)] = "USCA"
  AND SAFE_CAST(SPLIT(location, "#")[SAFE_OFFSET(0)] AS INT64) >= 3
  AND SAFE_CAST(SPLIT(location, "#")[SAFE_OFFSET(5)] AS FLOAT64) IS NOT NULL
  AND SAFE_CAST(SPLIT(location, "#")[SAFE_OFFSET(6)] AS FLOAT64) IS NOT NULL;
