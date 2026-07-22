"""
CTV Fraud Detection - Pre-Aggregation Script v2 (Persistent Database)
Single Source of Truth: All fraud metrics calculated here, app.py only reads from DB.
"""

import duckdb
import pandas as pd
import os
from datetime import datetime

print("="*80)
print("CTV FRAUD DETECTION - BUILD AGGREGATES v2 (SINGLE SOURCE OF TRUTH)")
print("="*80)
print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

# Connect to a persistent database file
db_path = 'fraud_detection.db'
conn = duckdb.connect(db_path)

print(f"\n📁 Creating database: {db_path}")

# DuckDB optimization
conn.execute("SET memory_limit='4GB'")
conn.execute("SET max_temp_directory_size='30GB'")
conn.execute("SET preserve_insertion_order=false")
conn.execute("SET threads=2")

# Find parquet files
parquet_files = sorted([f for f in os.listdir('.') if f.endswith('.parquet')])
file_list = ', '.join([f"'{f}'" for f in parquet_files])

print(f"📁 Found {len(parquet_files)} files")
total_size_gb = sum(os.path.getsize(f) for f in parquet_files) / (1024**3)
print(f"📊 Total size: {total_size_gb:.2f} GB")

print("\n🔨 Building aggregate tables...")

# ============================================
# 0. NORMALIZED DEVICE CATEGORIES VIEW
# ============================================
print("\n📐 Creating normalized_device_categories view...")
conn.execute(f"""
CREATE OR REPLACE VIEW normalized_devices AS
SELECT 
    *,
    CASE 
        WHEN upper(TRIM(p39_device_type)) IN ('TV', 'CONNECTEDTV', 'CONNECTED_TV', 'SMART TV', 'STREAMING DEVICE', 'SET_TOP_BOX', 'CTV', 'SMART_TV', 'STREAMING_DEVICE') 
            THEN 'Connected TV'
        WHEN upper(TRIM(p39_device_type)) IN ('TABLET', 'MOBILE PHONE', 'PHONE', 'MOBILE', 'SMARTPHONE', 'CELL PHONE') 
            THEN 'Mobile'
        WHEN upper(TRIM(p39_device_type)) IN ('DESKTOP', 'COMPUTER', 'DESKTOP_APP', 'PC', 'LAPTOP') 
            THEN 'Desktop'
        ELSE NULL
    END as detected_category,
    CASE 
        WHEN upper(TRIM(dsp_device_type)) IN ('TV', 'CONNECTEDTV', 'CONNECTED_TV', 'SMART TV', 'STREAMING DEVICE', 'SET_TOP_BOX', 'CTV', 'SMART_TV', 'STREAMING_DEVICE') 
            THEN 'Connected TV'
        WHEN upper(TRIM(dsp_device_type)) IN ('TABLET', 'MOBILE PHONE', 'PHONE', 'MOBILE', 'SMARTPHONE', 'CELL PHONE') 
            THEN 'Mobile'
        WHEN upper(TRIM(dsp_device_type)) IN ('DESKTOP', 'COMPUTER', 'DESKTOP_APP', 'PC', 'LAPTOP') 
            THEN 'Desktop'
        ELSE NULL
    END as reported_category,
    CASE 
        WHEN datacenter = '1' THEN 1 ELSE 0 
    END as is_datacenter,
    CASE 
        WHEN event = 'None' OR event IS NULL THEN 1 ELSE 0 
    END as is_invalid_event,
    CASE 
        WHEN auction_id IS NULL THEN 1 ELSE 0 
    END as is_missing_auction,
    CASE 
        WHEN detected_category IS NOT NULL 
        AND reported_category IS NOT NULL
        AND detected_category != reported_category 
        AND (
            (detected_category = 'Mobile' AND reported_category = 'Connected TV')
            OR (detected_category = 'Connected TV' AND reported_category = 'Desktop')
            OR (detected_category = 'Desktop' AND reported_category = 'Connected TV')
            OR (detected_category = 'Mobile' AND reported_category = 'Desktop')
            OR (detected_category = 'Connected TV' AND reported_category = 'Mobile')
            OR (detected_category = 'Desktop' AND reported_category = 'Mobile')
        ) THEN 1 ELSE 0 
    END as is_device_mismatch_sivt
FROM read_parquet([{file_list}])
""")
print("   ✅ normalized_devices view created")

# ============================================
# 1. DAILY AGGREGATES
# ============================================
print("\n📅 Building daily_aggregates...")
conn.execute(f"""
CREATE OR REPLACE TABLE daily_aggregates AS
SELECT 
    prt_dt as date,
    COUNT(*) as total_events,
    SUM(is_datacenter) as datacenter_traffic,
    SUM(is_invalid_event) as invalid_event_count,
    SUM(is_missing_auction) as missing_auction_ids,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
    SUM(is_device_mismatch_sivt) as sivt_events,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
    COUNT(DISTINCT dsp_id) as unique_dsps,
    COUNT(DISTINCT publisher_id) as unique_publishers,
    COUNT(DISTINCT exchange_id) as unique_exchanges
FROM normalized_devices
GROUP BY prt_dt
ORDER BY prt_dt
""")
count = conn.execute("SELECT COUNT(*) FROM daily_aggregates").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 2. DSP AGGREGATES
# ============================================
print("\n🏢 Building dsp_aggregates...")
conn.execute(f"""
CREATE OR REPLACE TABLE dsp_aggregates AS
SELECT 
    dsp_id,
    COUNT(*) as total_events,
    SUM(is_datacenter) as datacenter_traffic,
    SUM(is_invalid_event) as invalid_event_count,
    SUM(is_missing_auction) as missing_auction_ids,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
    SUM(is_device_mismatch_sivt) as sivt_events,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
    COUNT(DISTINCT publisher_id) as unique_publishers,
    COUNT(DISTINCT exchange_id) as unique_exchanges,
    COUNT(DISTINCT geo_ip_0) as unique_ips,
    MIN(prt_dt) as first_seen,
    MAX(prt_dt) as last_seen
FROM normalized_devices
WHERE dsp_id IS NOT NULL
GROUP BY dsp_id
HAVING COUNT(*) > 1000
ORDER BY givt_events DESC
""")
count = conn.execute("SELECT COUNT(*) FROM dsp_aggregates").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 3. EXCHANGE AGGREGATES
# ============================================
print("\n🔄 Building exchange_aggregates...")
conn.execute(f"""
CREATE OR REPLACE TABLE exchange_aggregates AS
SELECT 
    exchange_id,
    COUNT(*) as total_events,
    SUM(is_datacenter) as datacenter_traffic,
    SUM(is_invalid_event) as invalid_event_count,
    SUM(is_missing_auction) as missing_auction_ids,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
    SUM(is_device_mismatch_sivt) as sivt_events,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
    COUNT(DISTINCT dsp_id) as unique_dsps,
    COUNT(DISTINCT publisher_id) as unique_publishers,
    COUNT(DISTINCT geo_ip_0) as unique_ips,
    MIN(prt_dt) as first_seen,
    MAX(prt_dt) as last_seen
FROM normalized_devices
WHERE exchange_id IS NOT NULL
GROUP BY exchange_id
HAVING COUNT(*) > 1000
ORDER BY givt_events DESC
""")
count = conn.execute("SELECT COUNT(*) FROM exchange_aggregates").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 4. PUBLISHER AGGREGATES
# ============================================
print("\n📰 Building publisher_aggregates...")
conn.execute(f"""
CREATE OR REPLACE TABLE publisher_aggregates AS
SELECT 
    publisher_id,
    COUNT(*) as total_events,
    SUM(is_datacenter) as datacenter_traffic,
    SUM(is_invalid_event) as invalid_event_count,
    SUM(is_missing_auction) as missing_auction_ids,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
    SUM(is_device_mismatch_sivt) as sivt_events,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
    COUNT(DISTINCT dsp_id) as unique_dsps,
    COUNT(DISTINCT exchange_id) as unique_exchanges,
    COUNT(DISTINCT geo_ip_0) as unique_ips,
    MIN(prt_dt) as first_seen,
    MAX(prt_dt) as last_seen
FROM normalized_devices
WHERE publisher_id IS NOT NULL
GROUP BY publisher_id
HAVING COUNT(*) > 1000
ORDER BY givt_events DESC
""")
count = conn.execute("SELECT COUNT(*) FROM publisher_aggregates").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 5. APP AGGREGATES
# ============================================
print("\n📱 Building app_aggregates...")
conn.execute(f"""
CREATE OR REPLACE TABLE app_aggregates AS
SELECT 
    appstore_app_name as app_name,
    COUNT(*) as total_events,
    SUM(is_datacenter) as datacenter_traffic,
    SUM(is_invalid_event) as invalid_event_count,
    SUM(is_missing_auction) as missing_auction_ids,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
    SUM(is_device_mismatch_sivt) as sivt_events,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
    COUNT(DISTINCT dsp_id) as unique_dsps,
    COUNT(DISTINCT exchange_id) as unique_exchanges,
    COUNT(DISTINCT geo_ip_0) as unique_ips,
    MIN(prt_dt) as first_seen,
    MAX(prt_dt) as last_seen
FROM normalized_devices
WHERE appstore_app_name IS NOT NULL
GROUP BY appstore_app_name
HAVING COUNT(*) > 1000
ORDER BY givt_events DESC
""")
count = conn.execute("SELECT COUNT(*) FROM app_aggregates").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 6. DEVICE TYPE AGGREGATES
# ============================================
print("\n📱 Building device_aggregates...")
conn.execute(f"""
CREATE OR REPLACE TABLE device_aggregates AS
SELECT 
    detected_category,
    reported_category,
    COUNT(*) as total_events,
    SUM(is_datacenter) as datacenter_traffic,
    SUM(is_invalid_event) as invalid_event_count,
    SUM(is_missing_auction) as missing_auction_ids,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
    SUM(is_device_mismatch_sivt) as sivt_events,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
    COUNT(DISTINCT dsp_id) as unique_dsps,
    COUNT(DISTINCT exchange_id) as unique_exchanges,
    COUNT(DISTINCT geo_ip_0) as unique_ips
FROM normalized_devices
WHERE detected_category IS NOT NULL
GROUP BY detected_category, reported_category
ORDER BY total_events DESC
""")
count = conn.execute("SELECT COUNT(*) FROM device_aggregates").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 7. SIVT BREAKDOWN
# ============================================
print("\n🔄 Building sivt_breakdown...")
conn.execute(f"""
CREATE OR REPLACE TABLE sivt_breakdown AS
SELECT 
    detected_category || ' → ' || reported_category as mismatch_type,
    detected_category,
    reported_category,
    COUNT(*) as event_count,
    COUNT(DISTINCT geo_ip_0) as unique_ips,
    COUNT(DISTINCT dsp_id) as unique_dsps
FROM normalized_devices
WHERE is_device_mismatch_sivt = 1
GROUP BY detected_category, reported_category
ORDER BY event_count DESC
""")
count = conn.execute("SELECT COUNT(*) FROM sivt_breakdown").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 8. GIVT BREAKDOWN
# ============================================
print("\n🛑 Building givt_breakdown...")
conn.execute(f"""
CREATE OR REPLACE TABLE givt_breakdown AS
SELECT 
    'Datacenter Traffic' as givt_type,
    SUM(is_datacenter) as event_count
FROM normalized_devices
WHERE is_datacenter = 1
UNION ALL
SELECT 
    'Invalid Event (None/Null)' as givt_type,
    SUM(is_invalid_event) as event_count
FROM normalized_devices
WHERE is_invalid_event = 1
""")
count = conn.execute("SELECT COUNT(*) FROM givt_breakdown").fetchone()[0]
print(f"   ✅ {count} rows created")

# ============================================
# 9. GLOBAL SUMMARY
# ============================================
print("\n📊 Building global_summary...")

# Get the SIVT total from sivt_breakdown
sivt_total = conn.execute("SELECT SUM(event_count) FROM sivt_breakdown").fetchone()[0]
print(f"   SIVT total from breakdown: {sivt_total:,}")

conn.execute(f"""
CREATE OR REPLACE TABLE global_summary AS
SELECT 
    COUNT(*) as total_events,
    SUM(is_datacenter) as datacenter_traffic,
    SUM(is_invalid_event) as invalid_event_count,
    SUM(is_missing_auction) as missing_auction_ids,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
    {sivt_total} as sivt_events,
    SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) + {sivt_total} as invalid_events,
    COUNT(DISTINCT dsp_id) as total_dsps,
    COUNT(DISTINCT publisher_id) as total_publishers,
    COUNT(DISTINCT exchange_id) as total_exchanges,
    COUNT(DISTINCT geo_ip_0) as total_ips,
    COUNT(DISTINCT appstore_app_name) as total_apps,
    MIN(prt_dt) as earliest_date,
    MAX(prt_dt) as latest_date
FROM normalized_devices
""")
print("   ✅ 1 summary row created")

# ============================================
# 10. DEVICE CATEGORY MISMATCH (TRACEABILITY)
# ============================================
print("\n📱 Device Category Mismatch Analysis (Traceability)...")
conn.execute(f"""
CREATE OR REPLACE TABLE device_category_mismatch AS
WITH normalized_devices_agg AS (
    SELECT 
        geo_ip_0 as ip,
        dsp_id,
        detected_category,
        reported_category,
        COUNT(*) as mismatch_count,
        COUNT(DISTINCT prt_dt) as days_active,
        MIN(prt_dt) as first_seen,
        MAX(prt_dt) as last_seen
    FROM normalized_devices
    WHERE detected_category IS NOT NULL
    AND reported_category IS NOT NULL
    AND detected_category != reported_category 
    AND (
        (detected_category = 'Mobile' AND reported_category = 'Connected TV')
        OR (detected_category = 'Connected TV' AND reported_category = 'Desktop')
        OR (detected_category = 'Desktop' AND reported_category = 'Connected TV')
        OR (detected_category = 'Mobile' AND reported_category = 'Desktop')
        OR (detected_category = 'Connected TV' AND reported_category = 'Mobile')
        OR (detected_category = 'Desktop' AND reported_category = 'Mobile')
    )
    GROUP BY geo_ip_0, dsp_id, detected_category, reported_category
)
SELECT 
    ip,
    dsp_id,
    detected_category,
    reported_category,
    mismatch_count,
    days_active,
    first_seen,
    last_seen,
    CASE 
        WHEN detected_category = 'Mobile' AND reported_category = 'Connected TV' 
            THEN 'CRITICAL: Mobile spoofing as CTV'
        WHEN detected_category = 'Connected TV' AND reported_category = 'Desktop' 
            THEN 'HIGH: CTV spoofing as Desktop'
        WHEN detected_category = 'Desktop' AND reported_category = 'Connected TV' 
            THEN 'HIGH: Desktop spoofing as CTV'
        WHEN detected_category = 'Mobile' AND reported_category = 'Desktop' 
            THEN 'MEDIUM: Mobile spoofing as Desktop'
        WHEN detected_category = 'Desktop' AND reported_category = 'Mobile' 
            THEN 'MEDIUM: Desktop spoofing as Mobile'
        WHEN detected_category = 'Connected TV' AND reported_category = 'Mobile' 
            THEN 'MEDIUM: CTV spoofing as Mobile'
        ELSE 'LOW: Unusual mismatch'
    END as severity,
    CASE 
        WHEN detected_category = 'Mobile' AND reported_category = 'Connected TV' THEN 3
        WHEN detected_category = 'Connected TV' AND reported_category = 'Desktop' THEN 2
        WHEN detected_category = 'Desktop' AND reported_category = 'Connected TV' THEN 2
        WHEN detected_category = 'Mobile' AND reported_category = 'Desktop' THEN 1
        WHEN detected_category = 'Desktop' AND reported_category = 'Mobile' THEN 1
        WHEN detected_category = 'Connected TV' AND reported_category = 'Mobile' THEN 1
        ELSE 0
    END as severity_score
FROM normalized_devices_agg
ORDER BY mismatch_count DESC
""")
mismatch_count = conn.execute("SELECT COUNT(*) FROM device_category_mismatch").fetchone()[0]
print(f"   ✅ {mismatch_count} device category mismatches found")

# ============================================
# 11. ASN ANALYSIS (GIVT Enhancement)
# ============================================
print("\n🌍 ASN Analysis...")
conn.execute(f"""
CREATE OR REPLACE TABLE asn_analysis AS
SELECT 
    geo_as_0 as asn,
    COUNT(*) as total_events,
    COUNT(DISTINCT geo_ip_0) as unique_ips,
    SUM(is_datacenter) as datacenter_events,
    SUM(is_device_mismatch_sivt) as sivt_events,
    ROUND(100.0 * SUM(is_datacenter) / NULLIF(COUNT(*), 0), 2) as datacenter_pct,
    MIN(prt_dt) as first_seen,
    MAX(prt_dt) as last_seen
FROM normalized_devices
WHERE geo_as_0 IS NOT NULL
AND geo_as_0 != ''
GROUP BY geo_as_0
HAVING COUNT(*) > 10000
ORDER BY total_events DESC
""")
asn_count = conn.execute("SELECT COUNT(*) FROM asn_analysis").fetchone()[0]
print(f"   ✅ {asn_count} ASN records found")

# ============================================
# 12. TRACEABILITY TABLE
# ============================================
print("\n🔍 Building traceability_samples...")
conn.execute(f"""
CREATE OR REPLACE TABLE traceability_samples AS
SELECT 
    geo_ip_0 as ip,
    dsp_id,
    exchange_id,
    publisher_id,
    appstore_app_name as app_name,
    prt_dt as date,
    time_stamp,
    p39_device_type as detected_device,
    dsp_device_type as reported_device,
    detected_category,
    reported_category,
    CASE 
        WHEN is_datacenter = 1 THEN 'GIVT: Datacenter'
        WHEN is_invalid_event = 1 THEN 'GIVT: Invalid Event'
        WHEN is_device_mismatch_sivt = 1 THEN 'SIVT: Device Mismatch'
        WHEN is_missing_auction = 1 THEN 'Unknown: Missing Auction ID'
        ELSE 'Valid'
    END as classification,
    CASE 
        WHEN is_datacenter = 1 THEN 1
        WHEN is_invalid_event = 1 THEN 2
        WHEN is_device_mismatch_sivt = 1 THEN 3
        WHEN is_missing_auction = 1 THEN 4
        ELSE 0
    END as classification_order
FROM normalized_devices
WHERE is_datacenter = 1 
   OR is_invalid_event = 1 
   OR is_device_mismatch_sivt = 1 
   OR is_missing_auction = 1
ORDER BY RANDOM()
LIMIT 10000
""")
trace_count = conn.execute("SELECT COUNT(*) FROM traceability_samples").fetchone()[0]
print(f"   ✅ {trace_count} traceable sample events stored")

# ============================================
# 13. SIVT SUMMARY
# ============================================
print("\n📊 SIVT Summary...")
conn.execute("""
CREATE OR REPLACE TABLE sivt_summary AS
SELECT 'Device Mismatch' as sivt_type, 
       COUNT(*) as ip_count, 
       SUM(mismatch_count) as total_events, 
       AVG(severity_score) as avg_severity 
FROM device_category_mismatch
""")
print("   ✅ sivt_summary created")

# ============================================
# VERIFICATION
# ============================================
print("\n" + "="*80)
print("📊 AGGREGATION COMPLETE - STATISTICS")
print("="*80)

tables = [
    "normalized_devices",
    "daily_aggregates", 
    "dsp_aggregates", 
    "publisher_aggregates", 
    "exchange_aggregates",
    "app_aggregates",
    "device_aggregates",
    "sivt_breakdown",
    "givt_breakdown",
    "global_summary", 
    "device_category_mismatch",
    "asn_analysis",
    "traceability_samples",
    "sivt_summary"
]

print("\n✅ Tables created in fraud_detection.db:")
for table in tables:
    try:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        status = "✅" if count > 0 else "⚠️ Empty"
        print(f"   - {table}: {count:,} rows {status}")
    except Exception as e:
        print(f"   - {table}: ❌ Not created ({e})")

print("\n🔍 FRAUD DETECTION SUMMARY:")
global_stats = conn.execute("SELECT * FROM global_summary").df()
print(f"   - Total Events: {global_stats['total_events'].iloc[0]:,}")
print(f"   - GIVT Events: {global_stats['givt_events'].iloc[0]:,} ({global_stats['givt_events'].iloc[0]/global_stats['total_events'].iloc[0]*100:.2f}%)")
print(f"   - SIVT Events: {global_stats['sivt_events'].iloc[0]:,} ({global_stats['sivt_events'].iloc[0]/global_stats['total_events'].iloc[0]*100:.2f}%)")
print(f"   - Unknown (Missing Auction): {global_stats['missing_auction_ids'].iloc[0]:,} ({global_stats['missing_auction_ids'].iloc[0]/global_stats['total_events'].iloc[0]*100:.2f}%)")
print(f"   - Valid Events: {global_stats['total_events'].iloc[0] - global_stats['invalid_events'].iloc[0] - global_stats['missing_auction_ids'].iloc[0]:,}")

mismatch_count = conn.execute("SELECT COUNT(*) FROM device_category_mismatch").fetchone()[0]
asn_count = conn.execute("SELECT COUNT(*) FROM asn_analysis").fetchone()[0]

print(f"\n🔍 SIVT DETECTION METHODS:")
print(f"   - Device Category Mismatches: {mismatch_count}")
print(f"   - ASN Records: {asn_count}")

# Export key tables to CSV as backup
print("\n💾 Exporting key tables to CSV as backup...")
export_tables = [
    "daily_aggregates", "dsp_aggregates", "exchange_aggregates",
    "global_summary", "sivt_summary", "sivt_breakdown", "givt_breakdown"
]
for table in export_tables:
    try:
        df = conn.execute(f"SELECT * FROM {table}").df()
        df.to_csv(f"{table}.csv", index=False)
        print(f"   ✅ {table}.csv exported ({len(df)} rows)")
    except Exception as e:
        print(f"   ⚠️ Could not export {table}: {e}")

# Close connection
conn.close()

print(f"\n⏱️ Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print("\n💾 Aggregation complete!")
print("   - Database file: fraud_detection.db")
print("   - CSV backups: *.csv")
print("\n   Run the dashboard: streamlit run app_v2.py")