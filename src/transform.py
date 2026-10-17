import sqlite3
import pandas as pd
import os
from datetime import datetime

def build_database():
    os.makedirs('data/processed', exist_ok=True)
    os.makedirs('data/raw', exist_ok=True)
    db_path = 'data/processed/providence_health_equity.db'
    conn = sqlite3.connect(db_path)
    c = conn.cursor()

    # 1. Census ACS Baseline
    df_census = pd.DataFrame([
        {'geo_id': '02903', 'total_population': 15400, 'group_quarters_population': 2100},
        {'geo_id': '02905', 'total_population': 26200, 'group_quarters_population': 450},
        {'geo_id': '02906', 'total_population': 28500, 'group_quarters_population': 10200},
        {'geo_id': '02907', 'total_population': 29800, 'group_quarters_population': 610},
        {'geo_id': '02908', 'total_population': 36100, 'group_quarters_population': 3200},
        {'geo_id': '02909', 'total_population': 38400, 'group_quarters_population': 520}
    ])
    geo_names = {
        "02903": "Downtown / Capital Hill",
        "02905": "South Washington Park",
        "02906": "College Hill / East Side",
        "02907": "South Providence / Elmwood",
        "02908": "Mount Pleasant / Elmhurst",
        "02909": "Olneyville / Silver Lake"
    }
    df_census["geo_name"] = df_census["geo_id"].map(geo_names)
    df_census["geo_id"] = df_census["geo_id"].astype(str).str.zfill(5)

    # 2. CDC PLACES Baseline
    cdc_rows = []
    zcta_values = {
        '02903': {'CASTHMA': 10.5, 'DENTAL': 62.1, 'DIABETES': 9.2},
        '02905': {'CASTHMA': 12.8, 'DENTAL': 54.2, 'DIABETES': 13.1},
        '02906': {'CASTHMA': 8.1, 'DENTAL': 78.4, 'DIABETES': 5.4},
        '02907': {'CASTHMA': 13.5, 'DENTAL': 50.8, 'DIABETES': 14.5},
        '02908': {'CASTHMA': 11.2, 'DENTAL': 58.6, 'DIABETES': 10.8},
        '02909': {'CASTHMA': 13.2, 'DENTAL': 51.3, 'DIABETES': 14.1}
    }
    for z, vals in zcta_values.items():
        for code, desc in [('CASTHMA', 'Current asthma among adults'), ('DENTAL', 'Dental visit among adults'), ('DIABETES', 'Diagnosed diabetes among adults')]:
            cdc_rows.append({'zcta5': str(z).zfill(5), 'measureid': code, 'measure': desc, 'data_value': str(vals[code])})
    df_cdc = pd.DataFrame(cdc_rows)

    # 3. CMS Primary Care Clinics
    df_clinics = pd.DataFrame([
        {"facility_name": "Providence Community Health Centers (Olneyville)", "address": "100 Curtis St", "lat": 41.8175, "lon": -71.4431, "type": "FQHC Safety-Net"},
        {"facility_name": "PCHC Central Health Center", "address": "377 Broad St", "lat": 41.8112, "lon": -71.4185, "type": "FQHC Safety-Net"},
        {"facility_name": "Rhode Island Hospital Primary Care", "address": "593 Eddy St", "lat": 41.8135, "lon": -71.4112, "type": "Hospital Ambulatory Clinic"},
        {"facility_name": "East Side Primary Care Center", "address": "468 Waterman St", "lat": 41.8321, "lon": -71.3892, "type": "Community Practice"}
    ])

    # Stage to SQLite
    df_census.to_sql('raw_census', conn, if_exists='replace', index=False)
    df_cdc.to_sql('raw_cdc_places', conn, if_exists='replace', index=False)
    df_clinics.to_sql('providence_clinics', conn, if_exists='replace', index=False)

    c.execute('DROP TABLE IF EXISTS normalized_health_equity;')
    c.execute('''
    CREATE TABLE normalized_health_equity AS
    SELECT 
        PRINTF('%05d', CAST(c.geo_id AS INT)) AS geo_id,
        c.geo_name,
        'ZCTA' AS geo_type,
        p.measureid AS icd10_category,
        p.measure AS indicator_description,
        CAST(p.data_value AS FLOAT) AS prevalence_pct,
        c.total_population,
        c.group_quarters_population,
        (c.total_population - c.group_quarters_population) AS community_population,
        ROUND((CAST(p.data_value AS FLOAT) / 100.0) * c.total_population, 0) AS estimated_cases_raw,
        ROUND((CAST(p.data_value AS FLOAT) / 100.0) * (c.total_population - c.group_quarters_population), 0) AS estimated_cases_community_adjusted,
        ROUND(CAST(p.data_value AS FLOAT) * 10, 2) AS raw_rate_per_1k,
        ROUND((CAST(p.data_value AS FLOAT) * (c.total_population - c.group_quarters_population) / NULLIF(c.total_population, 0)) * 10, 2) AS adjusted_rate_per_1k
    FROM raw_census c
    JOIN raw_cdc_places p ON PRINTF('%05d', CAST(c.geo_id AS INT)) = PRINTF('%05d', CAST(p.zcta5 AS INT));
    ''')

    c.execute('DROP TABLE IF EXISTS metadata_refresh;')
    c.execute('CREATE TABLE metadata_refresh (last_updated TEXT);')
    c.execute('INSERT INTO metadata_refresh VALUES (?);', (datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC'),))

    conn.commit()
    conn.close()
    print("✓ Successfully generated data/processed/providence_health_equity.db")

if __name__ == "__main__":
    build_database()
