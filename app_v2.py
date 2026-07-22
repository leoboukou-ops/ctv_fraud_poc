import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import os
import time
import gdown
from datetime import datetime

# ============================================
# GOOGLE DRIVE FILE IDs
# ============================================
google_drive_full_db = "14wLgFa80bMl9PKfPYrVSiSHLvjISJgle"  # Full 10GB database
google_drive_demo_db = "1HtoEBV_AHoVGKpEq7uROKuaa53VJqYaU"   # Demo database

st.set_page_config(page_title="CTV Fraud Detector", layout="wide")

# ============================================
# DATABASE SELECTION
# ============================================
st.sidebar.markdown("---")
st.sidebar.header("📊 Database")

db_choice = st.sidebar.radio(
    "Select database:",
    ["🚀 Demo (Fast)", "💪 Full (Complete)"],
    help="Demo: Proportional sample, instant load\nFull: 131M events, 10GB download"
)

if "Full" in db_choice:
    db_path = 'fraud_detection_full.db'
    
    if not os.path.exists(db_path):
        st.sidebar.warning("⏳ Full database not downloaded yet")
        if st.sidebar.button("📥 Download Full Database (10GB)"):
            with st.spinner("📥 Downloading 10GB database... 15-30 minutes."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                try:
                    status_text.text("Connecting to Google Drive...")
                    gdown.download(f"https://drive.google.com/uc?id={google_drive_full_db}", db_path, quiet=False)
                    progress_bar.progress(100)
                    status_text.text("✅ Download complete!")
                    st.success("✅ Full database ready! Refreshing...")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    progress_bar.progress(0)
                    status_text.text("❌ Download failed")
                    st.error(f"Download failed: {e}")
        st.sidebar.info("Using demo database until download completes")
        db_path = 'fraud_detection.db'
    elif os.path.getsize(db_path) < 500000000:
        st.sidebar.warning("Full database appears incomplete, using demo")
        db_path = 'fraud_detection.db'
else:
    db_path = 'fraud_detection.db'
    if not os.path.exists(db_path):
        st.sidebar.warning("⏳ Downloading demo database...")
        with st.spinner("📥 Downloading demo database... 1-2 minutes."):
            progress_bar = st.progress(0)
            try:
                gdown.download(f"https://drive.google.com/uc?id={google_drive_demo_db}", db_path, quiet=False)
                progress_bar.progress(100)
                st.sidebar.success("✅ Demo database ready!")
                time.sleep(1)
                st.rerun()
            except Exception as e:
                st.sidebar.error(f"Download failed: {e}")
                st.stop()

# ============================================
# DATABASE CONNECTION
# ============================================
if not os.path.exists(db_path):
    st.error(f"Database file not found: {db_path}")
    st.stop()

try:
    conn = duckdb.connect(db_path, read_only=True)
    db_size_gb = os.path.getsize(db_path) / 1024 / 1024 / 1024
    event_count = conn.execute("SELECT COUNT(*) FROM normalized_devices").fetchone()[0]
    st.sidebar.success(f"✅ {db_size_gb:.1f}GB | {event_count:,} events")
except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

# ============================================
# DEBUG MODE
# ============================================
with st.sidebar.expander("🔧 Debug Info", expanded=False):
    try:
        total = conn.execute("SELECT COUNT(*) FROM normalized_devices").fetchone()[0]
        st.write(f"✅ Total events: {total:,}")
        dates = conn.execute("SELECT MIN(prt_dt), MAX(prt_dt) FROM normalized_devices").fetchone()
        st.write(f"📅 Date range: {dates[0]} to {dates[1]}")
        dsp_count = conn.execute("SELECT COUNT(DISTINCT dsp_id) FROM normalized_devices").fetchone()[0]
        st.write(f"🏢 Unique DSPs: {dsp_count:,}")
    except Exception as e:
        st.error(f"Debug error: {e}")

# Custom CSS
st.markdown("""
<style>
    .stDateInput label .stMarkdown { display: none !important; }
    .stDateInput label small { display: none !important; }
    .stDateInput label .stText { display: inline-block !important; }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 15px;
        border-left: 4px solid #3498db;
    }
    .alert-critical { border-left-color: #e74c3c; background-color: #fdf2f2; }
    .alert-high { border-left-color: #e67e22; background-color: #fef5e7; }
    .alert-medium { border-left-color: #f39c12; background-color: #fef9e7; }
    .alert-low { border-left-color: #3498db; background-color: #ebf5fb; }
</style>
""", unsafe_allow_html=True)

# ============================================
# SIDEBAR - NAVIGATION & FILTERS
# ============================================
st.sidebar.title("📊 Navigation")
page = st.sidebar.radio("Go to:", ["📈 Dashboard", "📋 Methodology & MRC", "🔍 Findings & Recommendations", "🔎 Trace a Case"])

st.sidebar.header("📅 Date Filter")
min_date = st.sidebar.date_input("Start Date", datetime(2026, 6, 16))
max_date = st.sidebar.date_input("End Date", datetime(2026, 6, 22))
min_date_str = min_date.strftime("%Y-%m-%d")
max_date_str = max_date.strftime("%Y-%m-%d")

# ============================================
# FILTER FUNCTIONS
# ============================================
@st.cache_data(ttl=3600)
def get_filter_options():
    try:
        dsps = conn.execute("SELECT DISTINCT dsp_id FROM normalized_devices WHERE dsp_id IS NOT NULL ORDER BY dsp_id").df()
        exchanges = conn.execute("SELECT DISTINCT exchange_id FROM normalized_devices WHERE exchange_id IS NOT NULL ORDER BY exchange_id").df()
        apps = conn.execute("SELECT DISTINCT appstore_app_name as app_name FROM normalized_devices WHERE appstore_app_name IS NOT NULL ORDER BY appstore_app_name LIMIT 100").df()
        devices = conn.execute("""
            SELECT DISTINCT p39_device_type FROM normalized_devices 
            WHERE p39_device_type IS NOT NULL AND p39_device_type != ''
            ORDER BY p39_device_type
        """).df()
        return {
            'dsps': ['All'] + dsps['dsp_id'].tolist() if not dsps.empty else ['All'],
            'exchanges': ['All'] + exchanges['exchange_id'].tolist() if not exchanges.empty else ['All'],
            'apps': ['All'] + apps['app_name'].tolist() if not apps.empty else ['All'],
            'devices': ['All'] + devices['p39_device_type'].tolist() if not devices.empty else ['All']
        }
    except:
        return {'dsps': ['All'], 'exchanges': ['All'], 'apps': ['All'], 'devices': ['All']}

if 'selected_dsp' not in st.session_state:
    st.session_state.selected_dsp = 'All'
if 'selected_exchange' not in st.session_state:
    st.session_state.selected_exchange = 'All'
if 'selected_app' not in st.session_state:
    st.session_state.selected_app = 'All'
if 'selected_device' not in st.session_state:
    st.session_state.selected_device = 'All'

filter_options = get_filter_options()

st.sidebar.header("🎯 Filters")
selected_dsp = st.sidebar.selectbox("DSP", filter_options['dsps'],
    index=filter_options['dsps'].index(st.session_state.selected_dsp) if st.session_state.selected_dsp in filter_options['dsps'] else 0)
selected_exchange = st.sidebar.selectbox("Exchange", filter_options['exchanges'],
    index=filter_options['exchanges'].index(st.session_state.selected_exchange) if st.session_state.selected_exchange in filter_options['exchanges'] else 0)
selected_app = st.sidebar.selectbox("App Name", filter_options['apps'],
    index=filter_options['apps'].index(st.session_state.selected_app) if st.session_state.selected_app in filter_options['apps'] else 0)
selected_device = st.sidebar.selectbox("Peer39 Device Type", filter_options['devices'],
    index=filter_options['devices'].index(st.session_state.selected_device) if st.session_state.selected_device in filter_options['devices'] else 0)

st.session_state.selected_dsp = selected_dsp
st.session_state.selected_exchange = selected_exchange
st.session_state.selected_app = selected_app
st.session_state.selected_device = selected_device

st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reset All Filters"):
    st.session_state.selected_dsp = 'All'
    st.session_state.selected_exchange = 'All'
    st.session_state.selected_app = 'All'
    st.session_state.selected_device = 'All'
    st.rerun()

def build_filter_conditions(dsp, exchange, app, device):
    conditions = []
    if dsp != 'All':
        conditions.append(f"dsp_id = '{dsp}'")
    if exchange != 'All':
        conditions.append(f"exchange_id = '{exchange}'")
    if app != 'All':
        conditions.append(f"appstore_app_name = '{app}'")
    if device != 'All':
        conditions.append(f"p39_device_type = '{device}'")
    return " AND ".join(conditions) if conditions else "1=1"

def show_active_filters():
    filters = []
    if selected_dsp != 'All': filters.append(f"DSP: {selected_dsp}")
    if selected_exchange != 'All': filters.append(f"Exchange: {selected_exchange}")
    if selected_app != 'All': filters.append(f"App: {selected_app}")
    if selected_device != 'All': filters.append(f"Device: {selected_device}")
    if filters:
        st.info(f"🔍 **Active Filters:** " + " | ".join(filters))

# ============================================
# DATA FUNCTIONS (MUTUALLY EXCLUSIVE CATEGORIES)
# ============================================
@st.cache_data(ttl=3600)
def get_filtered_summary(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT 
        COUNT(*) as total_events,
        SUM(CASE WHEN is_missing_auction = 1 THEN 1 ELSE 0 END) as unknown_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 1 THEN 1 ELSE 0 END) as datacenter_traffic,
        SUM(CASE WHEN is_missing_auction = 0 AND is_invalid_event = 1 THEN 1 ELSE 0 END) as invalid_event_count,
        SUM(CASE WHEN is_missing_auction = 0 AND (is_datacenter = 1 OR is_invalid_event = 1) THEN 1 ELSE 0 END) as givt_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0 AND is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as sivt_events,
        COUNT(DISTINCT dsp_id) as total_dsps,
        COUNT(DISTINCT publisher_id) as total_publishers,
        COUNT(DISTINCT exchange_id) as total_exchanges
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    """
    try:
        return conn.execute(query).df()
    except Exception as e:
        st.error(f"Summary query error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_daily(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT 
        prt_dt as date,
        COUNT(*) as total_events,
        SUM(CASE WHEN is_missing_auction = 1 THEN 1 ELSE 0 END) as unknown_events,
        SUM(CASE WHEN is_missing_auction = 0 AND (is_datacenter = 1 OR is_invalid_event = 1) THEN 1 ELSE 0 END) as givt_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0 AND is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as sivt_events
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    GROUP BY prt_dt ORDER BY prt_dt
    """
    try:
        df = conn.execute(query).df()
        if df.empty: return df
        df['invalid_events'] = df['givt_events'] + df['sivt_events']
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['unknown_events']
        for col in ['givt', 'sivt', 'invalid', 'unknown', 'valid']:
            df[f'{col}_pct'] = (df[f'{col}_events'] / df['total_events'] * 100).round(2)
        return df
    except Exception as e:
        st.error(f"Daily query error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_dsp(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    dsp_filter = f"AND dsp_id = '{dsp}'" if dsp != 'All' else ""
    query = f"""
    SELECT 
        dsp_id, COUNT(*) as total_events,
        SUM(CASE WHEN is_missing_auction = 1 THEN 1 ELSE 0 END) as unknown_events,
        SUM(CASE WHEN is_missing_auction = 0 AND (is_datacenter = 1 OR is_invalid_event = 1) THEN 1 ELSE 0 END) as givt_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0 AND is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as sivt_events
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND dsp_id IS NOT NULL AND {where_clause} {dsp_filter}
    GROUP BY dsp_id HAVING COUNT(*) > 1000
    ORDER BY givt_events DESC
    """
    try:
        df = conn.execute(query).df()
        if df.empty: return df
        df['invalid_events'] = df['givt_events'] + df['sivt_events']
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['unknown_events']
        for col in ['givt', 'sivt', 'invalid', 'unknown', 'valid']:
            df[f'{col}_pct'] = (df[f'{col}_events'] / df['total_events'] * 100).round(2)
        return df
    except Exception as e:
        st.error(f"DSP query error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_exchange(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    exchange_filter = f"AND exchange_id = '{exchange}'" if exchange != 'All' else ""
    query = f"""
    SELECT 
        exchange_id, COUNT(*) as total_events,
        SUM(CASE WHEN is_missing_auction = 1 THEN 1 ELSE 0 END) as unknown_events,
        SUM(CASE WHEN is_missing_auction = 0 AND (is_datacenter = 1 OR is_invalid_event = 1) THEN 1 ELSE 0 END) as givt_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0 AND is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as sivt_events
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND exchange_id IS NOT NULL AND {where_clause} {exchange_filter}
    GROUP BY exchange_id HAVING COUNT(*) > 1000
    ORDER BY givt_events DESC LIMIT 20
    """
    try:
        df = conn.execute(query).df()
        if df.empty: return df
        df['invalid_events'] = df['givt_events'] + df['sivt_events']
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['unknown_events']
        for col in ['givt', 'sivt', 'invalid', 'unknown', 'valid']:
            df[f'{col}_pct'] = (df[f'{col}_events'] / df['total_events'] * 100).round(2)
        return df
    except Exception as e:
        st.error(f"Exchange query error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_sivt_breakdown(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT 
        detected_category || ' → ' || reported_category as mismatch_type,
        detected_category, reported_category,
        COUNT(*) as event_count,
        COUNT(DISTINCT geo_ip_0) as unique_ips,
        COUNT(DISTINCT dsp_id) as unique_dsps
    FROM normalized_devices
    WHERE is_device_mismatch_sivt = 1
    AND is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0
    AND prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    GROUP BY detected_category, reported_category
    ORDER BY event_count DESC
    """
    try:
        return conn.execute(query).df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_givt_breakdown(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT 'Datacenter Traffic' as givt_type,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 1 THEN 1 ELSE 0 END) as event_count
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    UNION ALL
    SELECT 'Invalid Event (None/Null)' as givt_type,
        SUM(CASE WHEN is_missing_auction = 0 AND is_invalid_event = 1 THEN 1 ELSE 0 END) as event_count
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    """
    try:
        df = conn.execute(query).df()
        return df if not df.empty else pd.DataFrame(columns=['givt_type', 'event_count'])
    except:
        return pd.DataFrame(columns=['givt_type', 'event_count'])

@st.cache_data(ttl=3600)
def get_device_mismatch_data(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    try:
        result = conn.execute(f"""
            SELECT COUNT(*) as total_records, COALESCE(SUM(mismatch_count), 0) as total_events
            FROM device_category_mismatch
            WHERE ip IN (SELECT DISTINCT geo_ip_0 FROM normalized_devices WHERE {where_clause})
        """).fetchone()
        total_records, total_events = result if result else (0, 0)
    except:
        total_records, total_events = 0, 0
    try:
        df = conn.execute(f"""
            SELECT ip, dsp_id, detected_category, reported_category, mismatch_count, days_active, severity, severity_score
            FROM device_category_mismatch
            WHERE ip IN (SELECT DISTINCT geo_ip_0 FROM normalized_devices WHERE {where_clause})
            ORDER BY mismatch_count DESC LIMIT 50
        """).df()
        return df, total_records, total_events
    except:
        return pd.DataFrame(), total_records, total_events

@st.cache_data(ttl=3600)
def get_device_distribution(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT detected_category as device_type, COUNT(*) as event_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    AND detected_category IS NOT NULL AND detected_category != 'Other'
    GROUP BY detected_category ORDER BY event_count DESC
    """
    try:
        return conn.execute(query).df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_raw_device_types(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT p39_device_type as raw_device_type, COUNT(*) as event_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    AND p39_device_type IS NOT NULL AND p39_device_type != ''
    GROUP BY p39_device_type ORDER BY event_count DESC
    """
    try:
        return conn.execute(query).df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_traceable_ips(limit=100):
    try:
        return conn.execute(f"""
            SELECT DISTINCT ip, classification, COUNT(*) as event_count
            FROM traceability_samples GROUP BY ip, classification
            ORDER BY event_count DESC LIMIT {limit}
        """).df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def trace_ip_details(ip, classification_filter='All'):
    class_filter = f"AND classification = '{classification_filter}'" if classification_filter != 'All' else ""
    try:
        return conn.execute(f"""
            SELECT ip, dsp_id, exchange_id, publisher_id, app_name, date,
                detected_device, reported_device, detected_category, reported_category,
                p39_device_type, classification
            FROM traceability_samples
            WHERE ip = '{ip}' {class_filter}
            ORDER BY date, classification LIMIT 100
        """).df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_fraud_reasoning(ip):
    reasons = []
    try:
        dm = conn.execute(f"SELECT * FROM device_category_mismatch WHERE ip = '{ip}'").df()
        if not dm.empty:
            for _, row in dm.iterrows():
                reasons.append({
                    'method': 'Device Mismatch (SIVT)',
                    'severity': row['severity'],
                    'score': row['severity_score'],
                    'details': f"{row['detected_category']} detected but reported as {row['reported_category']} — {row['mismatch_count']:,} events"
                })
    except:
        pass
    return pd.DataFrame(reasons)

# ============================================
# PAGE 1: DASHBOARD
# ============================================
if page == "📈 Dashboard":
    st.title("📺 CTV Traffic Quality - Fraud Detection Dashboard")
    st.markdown("### MRC-Compliant Fraud Detection with GIVT + SIVT + Unknown Classification")
    
    show_active_filters()
    
    try:
        summary = get_filtered_summary(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        daily = get_filtered_daily(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        dsp = get_filtered_dsp(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        exchanges = get_filtered_exchange(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        sivt_breakdown = get_sivt_breakdown(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        givt_breakdown = get_givt_breakdown(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        device_distribution = get_device_distribution(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        raw_device_types = get_raw_device_types(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        
        if not summary.empty:
            total_events = int(summary['total_events'].iloc[0])
            unknown = int(summary['unknown_events'].iloc[0])
            givt = int(summary['givt_events'].iloc[0])
            sivt_total = int(summary['sivt_events'].iloc[0])
            datacenter = int(summary['datacenter_traffic'].iloc[0])
            invalid_event_count = int(summary['invalid_event_count'].iloc[0])
        else:
            st.warning("No data found for the selected filters")
            total_events = unknown = givt = sivt_total = datacenter = invalid_event_count = 0
        
        invalid = givt + sivt_total
        valid = total_events - invalid - unknown
        
        valid_rate = (valid / total_events * 100) if total_events > 0 else 0
        givt_rate = (givt / total_events * 100) if total_events > 0 else 0
        sivt_rate = (sivt_total / total_events * 100) if total_events > 0 else 0
        unknown_rate = (unknown / total_events * 100) if total_events > 0 else 0
        invalid_rate = givt_rate + sivt_rate
        
        # ============================================
        # METRICS ROW
        # ============================================
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("Total Events", f"{total_events:,}")
        with col2:
            st.metric("Valid Traffic", f"{valid_rate:.1f}%", delta=f"{valid:,} events", delta_color="normal")
        with col3:
            st.metric("Invalid (GIVT+SIVT)", f"{invalid_rate:.1f}%", delta=f"{invalid:,} events", delta_color="inverse")
        with col4:
            st.metric("GIVT", f"{givt_rate:.1f}%", delta=f"{givt:,} events", delta_color="inverse")
        with col5:
            st.metric("SIVT", f"{sivt_rate:.1f}%", delta=f"{sivt_total:,} events", delta_color="inverse")
        with col6:
            st.metric("Unknown", f"{unknown_rate:.1f}%", delta=f"{unknown:,} events", delta_color="off")
        
        # Verify sum
        total_pct = valid_rate + givt_rate + sivt_rate + unknown_rate
        if abs(total_pct - 100) > 1:
            st.warning(f"⚠️ Percentages sum to {total_pct:.1f}% (should be 100%)")
        
        # ============================================
        # CRITICAL ALERTS
        # ============================================
        st.subheader("🚨 Critical Alerts")
        alert_col1, alert_col2 = st.columns(2)
        
        with alert_col1:
            if givt > 0:
                alerts = [f"**GIVT:** {givt:,} events ({givt_rate:.1f}%)"]
                if datacenter > 0: alerts.append(f"  - Datacenter: {datacenter:,}")
                if invalid_event_count > 0: alerts.append(f"  - Invalid Events: {invalid_event_count:,}")
                if not dsp.empty:
                    for _, row in dsp[dsp['givt_pct'] == 100].iterrows():
                        alerts.append(f"  - 🚨 DSP {row['dsp_id']}: 100% GIVT ({row['total_events']:,} events)")
                st.error("\n".join(alerts))
            else:
                st.success("✅ No GIVT alerts")
        
        with alert_col2:
            if unknown > 0 or sivt_total > 0:
                alerts = []
                if sivt_total > 0: alerts.append(f"**SIVT (Device Mismatch):** {sivt_total:,} events ({sivt_rate:.1f}%)")
                if unknown > 0: alerts.append(f"**Unknown:** {unknown:,} events ({unknown_rate:.1f}%)")
                st.warning("\n".join(alerts))
            else:
                st.info("✅ No SIVT alerts")
        
        # ============================================
        # TRAFFIC CLASSIFICATION PIE
        # ============================================
        st.subheader("📊 Traffic Classification")
        pie_data = pd.DataFrame([
            {'Category': 'Valid', 'Events': valid, 'Pct': valid_rate},
            {'Category': 'GIVT', 'Events': givt, 'Pct': givt_rate},
            {'Category': 'SIVT', 'Events': sivt_total, 'Pct': sivt_rate},
            {'Category': 'Unknown', 'Events': unknown, 'Pct': unknown_rate}
        ])
        pie_data = pie_data[pie_data['Events'] > 0]
        
        if not pie_data.empty:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig = px.pie(pie_data, values='Events', names='Category', title='Traffic Classification',
                            color_discrete_sequence=['#2ecc71', '#e74c3c', '#f39c12', '#95a5a6'])
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.write("**Classification Details**")
                display_df = pie_data.copy()
                display_df['Events'] = display_df['Events'].apply(lambda x: f"{x:,}")
                display_df['Pct'] = display_df['Pct'].apply(lambda x: f"{x:.1f}%")
                display_df.columns = ['Category', 'Events', 'Percentage']
                st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # ============================================
        # GIVT BREAKDOWN
        # ============================================
        st.subheader("🛑 GIVT Breakdown")
        if not givt_breakdown.empty and givt_breakdown['event_count'].sum() > 0 and givt > 0:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_givt = px.pie(givt_breakdown, values='event_count', names='givt_type',
                                  title='GIVT by Type', color_discrete_sequence=['#e74c3c', '#c0392b'])
                fig_givt.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_givt, use_container_width=True)
            with col2:
                st.write("**GIVT Details**")
                givt_display = givt_breakdown.copy()
                givt_display['event_count'] = givt_display['event_count'].apply(lambda x: f"{x:,}")
                givt_display['percentage'] = givt_breakdown['event_count'].apply(
                    lambda x: f"{x/givt*100:.1f}%" if givt > 0 else "0%")
                st.dataframe(givt_display, use_container_width=True, hide_index=True)
        else:
            st.info("No GIVT data available for the selected filters")
        
        # ============================================
        # SIVT BREAKDOWN
        # ============================================
        st.subheader("🔄 SIVT Breakdown (Device Mismatch)")
        if not sivt_breakdown.empty and sivt_breakdown['event_count'].sum() > 0 and sivt_total > 0:
            st.markdown("""
            <div style="background-color: #fff3cd; border-left: 4px solid #f39c12; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
            <strong>📋 Methodology Note:</strong> SIVT = <strong>Device Mismatch only</strong> (directly verifiable from raw data). 
            Multi-Device, Volume, and Overnight detections were evaluated and moved to the production roadmap.
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_sivt = px.pie(sivt_breakdown, values='event_count', names='mismatch_type',
                                  title='SIVT by Mismatch Type', color_discrete_sequence=px.colors.qualitative.Set2)
                fig_sivt.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_sivt, use_container_width=True)
            with col2:
                st.write("**SIVT Details**")
                sivt_display = sivt_breakdown.copy()
                sivt_display['event_count'] = sivt_display['event_count'].apply(lambda x: f"{x:,}")
                sivt_display['percentage'] = sivt_breakdown['event_count'].apply(
                    lambda x: f"{x/sivt_total*100:.1f}%" if sivt_total > 0 else "0%")
                st.dataframe(sivt_display[['mismatch_type', 'event_count', 'percentage', 'unique_ips', 'unique_dsps']], 
                           use_container_width=True, hide_index=True)
        else:
            st.success("✅ No device category mismatches detected for the selected filters.")
        
        # ============================================
        # DAILY TRENDS
        # ============================================
        st.subheader("📈 Daily Trends: Valid, Invalid (GIVT+SIVT), Unknown")
        if not daily.empty:
            daily_melted = daily.melt(id_vars=['date'], 
                value_vars=['valid_events', 'givt_events', 'sivt_events', 'unknown_events'],
                var_name='category', value_name='events')
            daily_melted['category'] = daily_melted['category'].map({
                'valid_events': 'Valid', 'givt_events': 'GIVT',
                'sivt_events': 'SIVT', 'unknown_events': 'Unknown'
            })
            
            fig = px.bar(daily_melted, x='date', y='events', color='category',
                        title='Daily Events by Category', barmode='stack',
                        labels={'events': 'Events', 'date': 'Date', 'category': 'Category'},
                        color_discrete_map={
                            'Valid': '#2ecc71', 'GIVT': '#e74c3c',
                            'SIVT': '#f39c12', 'Unknown': '#95a5a6'
                        })
            st.plotly_chart(fig, use_container_width=True)
            
            daily_display = daily.copy()
            if 'date' in daily_display.columns:
                daily_display['date'] = pd.to_datetime(daily_display['date']).dt.strftime('%Y-%m-%d')
            display_cols = ['date', 'total_events', 'valid_events', 'givt_events', 'sivt_events', 'unknown_events',
                           'valid_pct', 'givt_pct', 'sivt_pct', 'unknown_pct']
            display_cols = [c for c in display_cols if c in daily_display.columns]
            if display_cols:
                daily_display = daily_display[display_cols]
                daily_display.columns = ['Date', 'Total', 'Valid', 'GIVT', 'SIVT', 'Unknown',
                                        'Valid %', 'GIVT %', 'SIVT %', 'Unknown %']
                st.dataframe(daily_display, use_container_width=True, hide_index=True)
        else:
            st.info("No daily data available for the selected filters")
        
        # ============================================
        # DEVICE TYPE DISTRIBUTION
        # ============================================
        st.subheader("📊 Device Type Distribution (Categorized)")
        if not device_distribution.empty and device_distribution['event_count'].sum() > 0:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_device = px.pie(device_distribution, values='event_count', names='device_type',
                                    title='Device Type Distribution (detected_category)',
                                    color_discrete_sequence=px.colors.qualitative.Set2)
                fig_device.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_device, use_container_width=True)
            with col2:
                st.write("**Categorized Device Types**")
                device_display = device_distribution.copy()
                device_display['event_count'] = device_display['event_count'].apply(lambda x: f"{x:,}")
                device_display['percentage'] = device_display['percentage'].apply(lambda x: f"{x:.2f}%")
                st.dataframe(device_display, use_container_width=True, hide_index=True)
        else:
            st.info("No device type data available for the selected filters")
        
        # ============================================
        # RAW PEER39 DEVICE TYPE DISTRIBUTION
        # ============================================
        st.subheader("📊 Raw Peer39 Device Type Distribution")
        if not raw_device_types.empty and raw_device_types['event_count'].sum() > 0:
            st.markdown("""
            <div style="background-color: #e8f4fd; border-left: 4px solid #3498db; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
            <strong>💡 About Raw Device Types:</strong> These are the original Peer39 device type values from the raw data, 
            before any categorization or mapping. The filter controls which device types are included in the analysis.
            The "Categorized" chart above shows grouped categories derived from these raw types.
            </div>
            """, unsafe_allow_html=True)
            
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_raw = px.bar(raw_device_types.head(20), x='raw_device_type', y='event_count',
                                title='Top 20 Raw Peer39 Device Types',
                                labels={'raw_device_type': 'Raw Device Type', 'event_count': 'Events'},
                                color_discrete_sequence=px.colors.qualitative.Set3)
                fig_raw.update_xaxes(tickangle=45)
                st.plotly_chart(fig_raw, use_container_width=True)
            with col2:
                st.write("**Raw Device Types (Top 20)**")
                raw_display = raw_device_types.head(20).copy()
                raw_display['event_count'] = raw_display['event_count'].apply(lambda x: f"{x:,}")
                raw_display['percentage'] = raw_display['percentage'].apply(lambda x: f"{x:.2f}%")
                raw_display.columns = ['Raw Device Type', 'Events', 'Percentage']
                st.dataframe(raw_display, use_container_width=True, hide_index=True)
                st.metric("Total Unique Raw Device Types", len(raw_device_types))
        else:
            st.info("No raw Peer39 device types available for the selected filters")
        
        # ============================================
        # SIVT DETECTION DETAIL
        # ============================================
        st.subheader("🔍 SIVT Detection — Device Mismatch Detail")
        if not sivt_breakdown.empty and sivt_breakdown['event_count'].sum() > 0:
            total_sivt = sivt_breakdown['event_count'].sum()
            st.warning(f"⚠️ Found {total_sivt:,.0f} SIVT events (Device Mismatches)")
            
            with st.expander("📋 Top 50 Detailed Mismatches (Sample)"):
                device_mismatch, dm_records, dm_events = get_device_mismatch_data(
                    selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
                if device_mismatch is not None and not device_mismatch.empty:
                    display_cols = ['ip', 'dsp_id', 'detected_category', 'reported_category', 'mismatch_count', 'severity']
                    dm_display = device_mismatch[display_cols].copy()
                    dm_display.columns = ['IP', 'DSP', 'Detected', 'Reported', 'Events', 'Severity']
                    st.dataframe(dm_display, use_container_width=True, hide_index=True)
                else:
                    st.info("No detailed mismatch records available")
        else:
            st.success("✅ No device category mismatches detected.")
        
        # ============================================
        # DSP RANKINGS
        # ============================================
        st.subheader("🏢 DSP Rankings")
        if not dsp.empty:
            dsp_display = dsp[['dsp_id', 'total_events', 'valid_events', 'givt_events', 'sivt_events', 'unknown_events',
                               'valid_pct', 'givt_pct', 'sivt_pct', 'unknown_pct']].copy()
            dsp_display.columns = ['DSP ID', 'Total', 'Valid', 'GIVT', 'SIVT', 'Unknown',
                                   'Valid %', 'GIVT %', 'SIVT %', 'Unknown %']
            st.dataframe(dsp_display, use_container_width=True, hide_index=True)
        else:
            st.info("No DSP data available for the selected filters")
        
        # ============================================
        # EXCHANGE RANKINGS
        # ============================================
        st.subheader("🔄 Exchange Rankings")
        if not exchanges.empty:
            ex_display = exchanges[['exchange_id', 'total_events', 'valid_events', 'givt_events', 'sivt_events', 'unknown_events',
                                    'valid_pct', 'givt_pct', 'sivt_pct', 'unknown_pct']].copy()
            ex_display.columns = ['Exchange ID', 'Total', 'Valid', 'GIVT', 'SIVT', 'Unknown',
                                  'Valid %', 'GIVT %', 'SIVT %', 'Unknown %']
            st.dataframe(ex_display, use_container_width=True, hide_index=True)
        else:
            st.info("No exchange data available for the selected filters")
        
        # Footer
        st.info("""
        **📊 Categories are mutually exclusive:** Unknown > GIVT > SIVT > Valid. All percentages sum to 100%.
        **Device filter** uses raw Peer39 types. **Reporting** uses categorized device types.
        """)
        
    except Exception as e:
        st.error(f"Error loading dashboard: {e}")
        st.exception(e)

# ============================================
# PAGE 2: METHODOLOGY & MRC
# ============================================
elif page == "📋 Methodology & MRC":
    st.title("📋 Methodology & MRC Reference Points")
    
    summary = get_filtered_summary(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    
    if not summary.empty:
        total = int(summary['total_events'].iloc[0])
        unknown = int(summary['unknown_events'].iloc[0])
        givt = int(summary['givt_events'].iloc[0])
        sivt = int(summary['sivt_events'].iloc[0])
        datacenter = int(summary['datacenter_traffic'].iloc[0])
        invalid_event = int(summary['invalid_event_count'].iloc[0])
        valid = total - unknown - givt - sivt
        
        st.markdown(f"""
        ## 🎯 Fraud Definition (MRC-Compliant)
        
        Following MRC Invalid Traffic Detection and Filtration Standards, Invalid Traffic (IVT) is traffic that cannot be validated as coming from a real user watching real content on a real TV.
        
        ## 📊 Mutually Exclusive Classification
        
        Categories applied in priority order:
        
        | Priority | Category | Criteria |
        |----------|----------|----------|
        | 1 | **Unknown** | Missing auction ID |
        | 2 | **GIVT** | Datacenter IP or invalid event type (with auction ID) |
        | 3 | **SIVT** | Device category mismatch (not GIVT, with auction ID) |
        | 4 | **Valid** | None of the above |
        
        ### GIVT Detection
        - **Datacenter Traffic**: IP addresses from cloud provider ranges
        - **Invalid Events**: Events with null/'None' event types
        
        ### SIVT Detection
        - **Device Category Mismatch**: Detected vs reported device type differs after normalization
        
        ## 📊 Current Data Summary
        
        | Category | Events | Percentage |
        |----------|--------|------------|
        | ✅ Valid | {valid:,} | {valid/total*100:.1f}% |
        | ❌ GIVT | {givt:,} | {givt/total*100:.1f}% |
        | ├─ Datacenter | {datacenter:,} | {datacenter/total*100:.2f}% |
        | └─ Invalid Events | {invalid_event:,} | {invalid_event/total*100:.2f}% |
        | ❌ SIVT | {sivt:,} | {sivt/total*100:.1f}% |
        | ❓ Unknown | {unknown:,} | {unknown/total*100:.1f}% |
        | **Total** | **{total:,}** | **100%** |
        """)
    else:
        st.info("No data available for the selected filters")

# ============================================
# PAGE 3: FINDINGS & RECOMMENDATIONS
# ============================================
elif page == "🔍 Findings & Recommendations":
    st.title("🔍 Findings & Recommendations")
    
    summary = get_filtered_summary(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    dsp_data = get_filtered_dsp(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    sivt_breakdown = get_sivt_breakdown(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    
    if not summary.empty:
        total = int(summary['total_events'].iloc[0])
        unknown = int(summary['unknown_events'].iloc[0])
        givt = int(summary['givt_events'].iloc[0])
        sivt = int(summary['sivt_events'].iloc[0])
        datacenter = int(summary['datacenter_traffic'].iloc[0])
        invalid_event = int(summary['invalid_event_count'].iloc[0])
        valid = total - unknown - givt - sivt
        
        st.markdown(f"""
        ## 📊 Executive Summary
        
        | Metric | Value |
        |--------|-------|
        | Data Analyzed | {total:,} events |
        | Valid Traffic | {valid:,} ({valid/total*100:.1f}%) |
        | Invalid (GIVT+SIVT) | {givt+sivt:,} ({(givt+sivt)/total*100:.1f}%) |
        | ├─ GIVT | {givt:,} ({givt/total*100:.1f}%) |
        | └─ SIVT | {sivt:,} ({sivt/total*100:.1f}%) |
        | Unknown | {unknown:,} ({unknown/total*100:.1f}%) |
        """)
        
        if not dsp_data.empty:
            fraudulent = dsp_data[dsp_data['givt_pct'] >= 90]
            if not fraudulent.empty:
                st.subheader("🚨 DSPs with ≥90% GIVT")
                for _, row in fraudulent.iterrows():
                    st.error(f"**DSP {row['dsp_id']}** — {row['total_events']:,} events — {row['givt_pct']:.0f}% GIVT — **BLOCK IMMEDIATELY**")
        
        if not sivt_breakdown.empty:
            st.subheader("🔄 SIVT Breakdown")
            st.dataframe(sivt_breakdown[['mismatch_type', 'event_count', 'unique_ips', 'unique_dsps']], 
                        use_container_width=True, hide_index=True)
        
        st.markdown("""
        ## 🚀 Production Roadmap
        
        | Phase | Timeline | Actions |
        |-------|----------|---------|
        | Phase 1 | Week 1 | Block 100% GIVT DSPs, Block datacenter IPs |
        | Phase 2 | Month 1 | Fix auction ID pass-through, SIVT monitoring |
        | Phase 3 | Month 2 | Device verification pre-bid, SSAI validation |
        | Phase 4 | Month 3 | Multi-Device detection, Volume detection |
        """)
    else:
        st.info("No data available for the selected filters")

# ============================================
# PAGE 4: TRACE A CASE
# ============================================
else:
    st.title("🔎 Trace a Case — End-to-End Audit")
    st.markdown("Select a flagged IP to trace the fraud reasoning end-to-end.")
    
    traceable_ips = get_traceable_ips(200)
            
            manual_ip = st.text_input("Or enter IP manually:")
            if manual_ip:
                selected_ip = manual_ip
        
        with col2:
            if selected_ip:
                st.subheader(f"🔍 Audit: {selected_ip}")
                
                st.write("**Step 1: Fraud Reasoning**")
                reasoning = get_fraud_reasoning(selected_ip)
                if not reasoning.empty:
                    for _, r in reasoning.iterrows():
                        severity = "alert-critical" if r['score'] >= 3 else "alert-high" if r['score'] >= 2 else "alert-medium"
                        st.markdown(f"""
                        <div class="metric-card {severity}">
                        <strong>{r['method']}</strong><br>
                        {r['severity']}<br>
                        <small>{r['details']}</small>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("No SIVT flags for this IP")
                
                st.write("**Step 2: Sample Events**")
                details = trace_ip_details(selected_ip, selected_class if selected_class != 'All' else 'All')
                if not details.empty:
                    st.dataframe(details, use_container_width=True, hide_index=True)
                else:
                    st.warning(f"No traceable events found for IP {selected_ip}")
    else:
        st.warning("No traceability data available.")

conn.close()