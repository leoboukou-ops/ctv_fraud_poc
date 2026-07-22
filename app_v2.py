import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
import time
import gdown
from datetime import datetime

# ============================================
# PEER39 BRANDING - MUST BE FIRST
# ============================================
from peer39_style import apply_peer39_theme, peer39_header, sidebar_logo, style_plotly

# ============================================
# PAGE CONFIG - MUST BE THE FIRST STREAMLIT COMMAND
# ============================================
st.set_page_config(
    page_title="CTV Fraud Detector",
    page_icon="📺",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================
# APPLY PEER39 THEME
# ============================================
apply_peer39_theme()  # Inject the CSS
sidebar_logo()        # Add logo to sidebar (white version)

# ============================================
# GOOGLE DRIVE FILE IDs
# ============================================
google_drive_full_db = "14wLgFa80bMl9PKfPYrVSiSHLvjISJgle"
google_drive_demo_db = "1HtoEBV_AHoVGKpEq7uROKuaa53VJqYaU"

# ============================================
# DATABASE SELECTION
# ============================================
st.sidebar.markdown("---")
st.sidebar.header("Database")

db_choice = st.sidebar.radio(
    "Select database:",
    ["Demo (Fast)", "Full (Complete)"],
    help="Demo: Proportional sample, instant load\nFull: 131M events, 10GB download"
)

if "Full" in db_choice:
    db_path = 'fraud_detection_full.db'
    if not os.path.exists(db_path):
        st.sidebar.warning("Full database not downloaded yet")
        if st.sidebar.button("Download Full Database (10GB)"):
            with st.spinner("Downloading 10GB database... 15-30 minutes."):
                progress_bar = st.progress(0)
                status_text = st.empty()
                try:
                    status_text.text("Connecting to Google Drive...")
                    gdown.download(f"https://drive.google.com/uc?id={google_drive_full_db}", db_path, quiet=False)
                    progress_bar.progress(100)
                    status_text.text("Download complete!")
                    st.success("Full database ready! Refreshing...")
                    time.sleep(2)
                    st.rerun()
                except Exception as e:
                    progress_bar.progress(0)
                    status_text.text("Download failed")
                    st.error(f"Download failed: {e}")
        st.sidebar.info("Using demo database until download completes")
        db_path = 'fraud_detection.db'
    elif os.path.getsize(db_path) < 500000000:
        st.sidebar.warning("Full database appears incomplete, using demo")
        db_path = 'fraud_detection.db'
else:
    db_path = 'fraud_detection.db'
    if not os.path.exists(db_path):
        st.sidebar.warning("Downloading demo database...")
        with st.spinner("Downloading demo database... 1-2 minutes."):
            progress_bar = st.progress(0)
            try:
                gdown.download(f"https://drive.google.com/uc?id={google_drive_demo_db}", db_path, quiet=False)
                progress_bar.progress(100)
                st.sidebar.success("Demo database ready!")
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
    st.sidebar.success(f"{db_size_gb:.1f}GB | {event_count:,} events")
except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

# Peer39 color palette
P39_COLORS = {
    'Valid': '#8cba51',
    'GIVT': '#d92d20',
    'SIVT': '#E6AF2E',
    'Unknown': '#757575',
}
P39_CHART_PALETTE = ['#8cba51', '#d92d20', '#E6AF2E', '#757575', '#3d85c6', '#9fc5e8', '#073763']

# ============================================
# SIDEBAR - NAVIGATION & FILTERS
# ============================================
st.sidebar.title("Navigation")
page = st.sidebar.radio("Go to:", ["Dashboard", "Methodology & MRC", "Findings & Recommendations", "Trace a Case"])

st.sidebar.header("Date Filter")
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
        devices = conn.execute("SELECT DISTINCT p39_device_type FROM normalized_devices WHERE p39_device_type IS NOT NULL AND p39_device_type != '' ORDER BY p39_device_type").df()
        return {
            'dsps': ['All'] + dsps['dsp_id'].tolist() if not dsps.empty else ['All'],
            'exchanges': ['All'] + exchanges['exchange_id'].tolist() if not exchanges.empty else ['All'],
            'apps': ['All'] + apps['app_name'].tolist() if not apps.empty else ['All'],
            'devices': ['All'] + devices['p39_device_type'].tolist() if not devices.empty else ['All']
        }
    except:
        return {'dsps': ['All'], 'exchanges': ['All'], 'apps': ['All'], 'devices': ['All']}

if 'selected_dsp' not in st.session_state: st.session_state.selected_dsp = 'All'
if 'selected_exchange' not in st.session_state: st.session_state.selected_exchange = 'All'
if 'selected_app' not in st.session_state: st.session_state.selected_app = 'All'
if 'selected_device' not in st.session_state: st.session_state.selected_device = 'All'

filter_options = get_filter_options()

st.sidebar.header("Filters")
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
if st.sidebar.button("Reset All Filters"):
    st.session_state.selected_dsp = 'All'
    st.session_state.selected_exchange = 'All'
    st.session_state.selected_app = 'All'
    st.session_state.selected_device = 'All'
    st.rerun()

def build_filter_conditions(dsp, exchange, app, device):
    conditions = []
    if dsp != 'All': conditions.append(f"dsp_id = '{dsp}'")
    if exchange != 'All': conditions.append(f"exchange_id = '{exchange}'")
    if app != 'All': conditions.append(f"appstore_app_name = '{app}'")
    if device != 'All': conditions.append(f"p39_device_type = '{device}'")
    return " AND ".join(conditions) if conditions else "1=1"

def show_active_filters():
    filters = []
    if selected_dsp != 'All': filters.append(f"DSP: {selected_dsp}")
    if selected_exchange != 'All': filters.append(f"Exchange: {selected_exchange}")
    if selected_app != 'All': filters.append(f"App: {selected_app}")
    if selected_device != 'All': filters.append(f"Device: {selected_device}")
    if filters: st.info(f"**Active Filters:** " + " | ".join(filters))

# Helper function to abbreviate numbers
def fmt(n):
    if abs(n) >= 1_000_000:
        return f"{n/1_000_000:.1f}M"
    elif abs(n) >= 1_000:
        return f"{n/1_000:.1f}K"
    else:
        return str(n)

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
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    """
    try: return conn.execute(query).df()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_daily(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT prt_dt as date, COUNT(*) as total_events,
        SUM(CASE WHEN is_missing_auction = 1 THEN 1 ELSE 0 END) as unknown_events,
        SUM(CASE WHEN is_missing_auction = 0 AND (is_datacenter = 1 OR is_invalid_event = 1) THEN 1 ELSE 0 END) as givt_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0 AND is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as sivt_events
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
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
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_dsp(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    dsp_filter = f"AND dsp_id = '{dsp}'" if dsp != 'All' else ""
    query = f"""
    SELECT dsp_id, COUNT(*) as total_events,
        SUM(CASE WHEN is_missing_auction = 1 THEN 1 ELSE 0 END) as unknown_events,
        SUM(CASE WHEN is_missing_auction = 0 AND (is_datacenter = 1 OR is_invalid_event = 1) THEN 1 ELSE 0 END) as givt_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0 AND is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as sivt_events
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND dsp_id IS NOT NULL AND {where_clause} {dsp_filter}
    GROUP BY dsp_id HAVING COUNT(*) > 1000 ORDER BY givt_events DESC
    """
    try:
        df = conn.execute(query).df()
        if df.empty: return df
        df['invalid_events'] = df['givt_events'] + df['sivt_events']
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['unknown_events']
        for col in ['givt', 'sivt', 'invalid', 'unknown', 'valid']:
            df[f'{col}_pct'] = (df[f'{col}_events'] / df['total_events'] * 100).round(2)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_exchange(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    exchange_filter = f"AND exchange_id = '{exchange}'" if exchange != 'All' else ""
    query = f"""
    SELECT exchange_id, COUNT(*) as total_events,
        SUM(CASE WHEN is_missing_auction = 1 THEN 1 ELSE 0 END) as unknown_events,
        SUM(CASE WHEN is_missing_auction = 0 AND (is_datacenter = 1 OR is_invalid_event = 1) THEN 1 ELSE 0 END) as givt_events,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0 AND is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as sivt_events
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND exchange_id IS NOT NULL AND {where_clause} {exchange_filter}
    GROUP BY exchange_id HAVING COUNT(*) > 1000 ORDER BY givt_events DESC LIMIT 20
    """
    try:
        df = conn.execute(query).df()
        if df.empty: return df
        df['invalid_events'] = df['givt_events'] + df['sivt_events']
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['unknown_events']
        for col in ['givt', 'sivt', 'invalid', 'unknown', 'valid']:
            df[f'{col}_pct'] = (df[f'{col}_events'] / df['total_events'] * 100).round(2)
        return df
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_sivt_breakdown(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT detected_category || ' → ' || reported_category as mismatch_type,
        detected_category, reported_category, COUNT(*) as event_count,
        COUNT(DISTINCT geo_ip_0) as unique_ips, COUNT(DISTINCT dsp_id) as unique_dsps
    FROM normalized_devices
    WHERE is_device_mismatch_sivt = 1 AND is_missing_auction = 0 AND is_datacenter = 0 AND is_invalid_event = 0
    AND prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    GROUP BY detected_category, reported_category ORDER BY event_count DESC
    """
    try: return conn.execute(query).df()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_givt_breakdown(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT 'Datacenter Traffic' as givt_type,
        SUM(CASE WHEN is_missing_auction = 0 AND is_datacenter = 1 THEN 1 ELSE 0 END) as event_count
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    UNION ALL
    SELECT 'Invalid Event (None/Null)' as givt_type,
        SUM(CASE WHEN is_missing_auction = 0 AND is_invalid_event = 1 THEN 1 ELSE 0 END) as event_count
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    """
    try:
        df = conn.execute(query).df()
        return df if not df.empty else pd.DataFrame(columns=['givt_type', 'event_count'])
    except: return pd.DataFrame(columns=['givt_type', 'event_count'])

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
    except: total_records, total_events = 0, 0
    try:
        df = conn.execute(f"""
            SELECT ip, dsp_id, detected_category, reported_category, mismatch_count, days_active, severity, severity_score
            FROM device_category_mismatch
            WHERE ip IN (SELECT DISTINCT geo_ip_0 FROM normalized_devices WHERE {where_clause})
            ORDER BY mismatch_count DESC LIMIT 50
        """).df()
        return df, total_records, total_events
    except: return pd.DataFrame(), total_records, total_events

@st.cache_data(ttl=3600)
def get_device_distribution(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT detected_category as device_type, COUNT(*) as event_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    AND detected_category IS NOT NULL AND detected_category != 'Other'
    GROUP BY detected_category ORDER BY event_count DESC
    """
    try: return conn.execute(query).df()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_raw_device_types(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT p39_device_type as raw_device_type, COUNT(*) as event_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM normalized_devices WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}' AND {where_clause}
    AND p39_device_type IS NOT NULL AND p39_device_type != ''
    GROUP BY p39_device_type ORDER BY event_count DESC
    """
    try: return conn.execute(query).df()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_traceable_ips(limit=100):
    try:
        return conn.execute(f"SELECT DISTINCT ip, classification, COUNT(*) as event_count FROM traceability_samples GROUP BY ip, classification ORDER BY event_count DESC LIMIT {limit}").df()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def trace_ip_details(ip, classification_filter='All'):
    class_filter = f"AND classification = '{classification_filter}'" if classification_filter != 'All' else ""
    try:
        return conn.execute(f"SELECT ip, dsp_id, exchange_id, publisher_id, app_name, date, detected_device, reported_device, detected_category, reported_category, p39_device_type, classification FROM traceability_samples WHERE ip = '{ip}' {class_filter} ORDER BY date, classification LIMIT 100").df()
    except: return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_fraud_reasoning(ip):
    reasons = []
    try:
        dm = conn.execute(f"SELECT * FROM device_category_mismatch WHERE ip = '{ip}'").df()
        if not dm.empty:
            for _, row in dm.iterrows():
                reasons.append({'method': 'Device Mismatch (SIVT)', 'severity': row['severity'], 'score': row['severity_score'],
                    'details': f"{row['detected_category']} detected but reported as {row['reported_category']} — {row['mismatch_count']:,} events"})
    except: pass
    return pd.DataFrame(reasons)

# ============================================
# PAGE 1: DASHBOARD
# ============================================
if page == "Dashboard":
    peer39_header("CTV Fraud Detector")  # Top bar with logo
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
        
        # 1. METRICS ROW (abbreviated numbers)
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1: st.metric("Total Events", fmt(total_events))
        with col2: st.metric("Valid Traffic", f"{valid_rate:.1f}%", delta=fmt(valid), delta_color="normal")
        with col3: st.metric("Invalid", f"{invalid_rate:.1f}%", delta=fmt(invalid), delta_color="inverse")
        with col4: st.metric("GIVT", f"{givt_rate:.1f}%", delta=fmt(givt), delta_color="inverse")
        with col5: st.metric("SIVT", f"{sivt_rate:.1f}%", delta=fmt(sivt_total), delta_color="inverse")
        with col6: st.metric("Unknown", f"{unknown_rate:.1f}%", delta=fmt(unknown), delta_color="off")
        
        # 2. CRITICAL ALERTS
        st.subheader("Critical Alerts")
        alert_col1, alert_col2 = st.columns(2)
        with alert_col1:
            if givt > 0:
                alerts = [f"**GIVT:** {givt:,} events ({givt_rate:.1f}%)"]
                if datacenter > 0: alerts.append(f"  - Datacenter: {datacenter:,}")
                if invalid_event_count > 0: alerts.append(f"  - Invalid Events: {invalid_event_count:,}")
                if not dsp.empty:
                    for _, row in dsp[dsp['givt_pct'] == 100].iterrows():
                        alerts.append(f"  - DSP {row['dsp_id']}: 100% GIVT")
                st.error("\n".join(alerts))
            else: st.success("No GIVT alerts")
        with alert_col2:
            if unknown > 0 or sivt_total > 0:
                alerts = []
                if sivt_total > 0: alerts.append(f"**SIVT:** {sivt_total:,} events ({sivt_rate:.1f}%)")
                if unknown > 0: alerts.append(f"**Unknown:** {unknown:,} events ({unknown_rate:.1f}%)")
                st.warning("\n".join(alerts))
            else: st.info("No SIVT alerts")
        
        # 3. DEVICE TYPE DISTRIBUTION (CATEGORIZED)
        st.subheader("Device Type Distribution (Categorized)")
        if not device_distribution.empty and device_distribution['event_count'].sum() > 0:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_device = px.pie(device_distribution, values='event_count', names='device_type',
                                    title='Device Type Distribution', color_discrete_sequence=P39_CHART_PALETTE)
                fig_device = style_plotly(fig_device)  # Apply Peer39 styling
                fig_device.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_device, use_container_width=True)
            with col2:
                st.write("**Categorized Device Types**")
                device_display = device_distribution.copy()
                device_display['event_count'] = device_display['event_count'].apply(lambda x: f"{x:,}")
                device_display['percentage'] = device_display['percentage'].apply(lambda x: f"{x:.2f}%")
                st.dataframe(device_display, use_container_width=True, hide_index=True)
        else: st.info("No device type data available")
        
        # 4. RAW PEER39 DEVICE TYPES
        st.subheader("Raw Peer39 Device Type Distribution")
        if not raw_device_types.empty and raw_device_types['event_count'].sum() > 0:
            st.markdown("""
            <div style="background-color: #f3f8fd; border-left: 4px solid #3d85c6; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
            <strong>About Raw Device Types:</strong> Original Peer39 values before categorization.
            </div>""", unsafe_allow_html=True)
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_raw = px.bar(raw_device_types.head(20), x='raw_device_type', y='event_count',
                                title='Top 20 Raw Peer39 Device Types', color_discrete_sequence=P39_CHART_PALETTE)
                fig_raw = style_plotly(fig_raw)  # Apply Peer39 styling
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
        else: st.info("No raw Peer39 device types available")
        
        # 5. TRAFFIC CLASSIFICATION PIE
        st.subheader("Traffic Classification")
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
                            color='Category', color_discrete_map=P39_COLORS)
                fig = style_plotly(fig)  # Apply Peer39 styling
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                st.write("**Classification Details**")
                display_df = pie_data.copy()
                display_df['Events'] = display_df['Events'].apply(lambda x: f"{x:,}")
                display_df['Pct'] = display_df['Pct'].apply(lambda x: f"{x:.1f}%")
                display_df.columns = ['Category', 'Events', 'Percentage']
                st.dataframe(display_df, use_container_width=True, hide_index=True)
        
        # 6. DAILY TRENDS
        st.subheader("Daily Trends")
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
                        color_discrete_map=P39_COLORS)
            fig = style_plotly(fig)  # Apply Peer39 styling
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
        else: st.info("No daily data available")
        
        # 7. GIVT BREAKDOWN
        st.subheader("GIVT Breakdown")
        if not givt_breakdown.empty and givt_breakdown['event_count'].sum() > 0 and givt > 0:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_givt = px.pie(givt_breakdown, values='event_count', names='givt_type',
                                  title='GIVT by Type', color_discrete_sequence=['#d92d20', '#B54F6F'])
                fig_givt = style_plotly(fig_givt)  # Apply Peer39 styling
                fig_givt.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_givt, use_container_width=True)
            with col2:
                st.write("**GIVT Details**")
                givt_display = givt_breakdown.copy()
                givt_display['event_count'] = givt_display['event_count'].apply(lambda x: f"{x:,}")
                givt_display['percentage'] = givt_breakdown['event_count'].apply(
                    lambda x: f"{x/givt*100:.1f}%" if givt > 0 else "0%")
                st.dataframe(givt_display, use_container_width=True, hide_index=True)
        else: st.info("No GIVT data available")
        
        # 8. SIVT BREAKDOWN
        st.subheader("SIVT Breakdown (Device Mismatch)")
        if not sivt_breakdown.empty and sivt_breakdown['event_count'].sum() > 0 and sivt_total > 0:
            st.markdown("""
            <div style="background-color: #fbf1d6; border-left: 4px solid #E6AF2E; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
            <strong>Methodology Note:</strong> SIVT = <strong>Device Mismatch only</strong>. Multi-Device, Volume, Overnight moved to roadmap.
            </div>""", unsafe_allow_html=True)
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_sivt = px.pie(sivt_breakdown, values='event_count', names='mismatch_type',
                                  title='SIVT by Mismatch Type', color_discrete_sequence=P39_CHART_PALETTE)
                fig_sivt = style_plotly(fig_sivt)  # Apply Peer39 styling
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
        else: st.success("No device category mismatches detected.")
        
        # 9. SIVT DETECTION DETAIL
        st.subheader("SIVT Detection — Top 50 Mismatches")
        if not sivt_breakdown.empty and sivt_breakdown['event_count'].sum() > 0:
            device_mismatch, dm_records, dm_events = get_device_mismatch_data(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
            if device_mismatch is not None and not device_mismatch.empty:
                display_cols = ['ip', 'dsp_id', 'detected_category', 'reported_category', 'mismatch_count', 'severity']
                dm_display = device_mismatch[display_cols].copy()
                dm_display.columns = ['IP', 'DSP', 'Detected', 'Reported', 'Events', 'Severity']
                st.dataframe(dm_display, use_container_width=True, hide_index=True)
            else: st.info("No detailed mismatch records")
        
        # 10. DSP RANKINGS
        st.subheader("DSP Rankings")
        if not dsp.empty:
            dsp_display = dsp[['dsp_id', 'total_events', 'valid_events', 'givt_events', 'sivt_events', 'unknown_events',
                               'valid_pct', 'givt_pct', 'sivt_pct', 'unknown_pct']].copy()
            dsp_display.columns = ['DSP ID', 'Total', 'Valid', 'GIVT', 'SIVT', 'Unknown', 'Valid %', 'GIVT %', 'SIVT %', 'Unknown %']
            st.dataframe(dsp_display, use_container_width=True, hide_index=True)
        else: st.info("No DSP data available")
        
        # 11. EXCHANGE RANKINGS
        st.subheader("Exchange Rankings")
        if not exchanges.empty:
            ex_display = exchanges[['exchange_id', 'total_events', 'valid_events', 'givt_events', 'sivt_events', 'unknown_events',
                                    'valid_pct', 'givt_pct', 'sivt_pct', 'unknown_pct']].copy()
            ex_display.columns = ['Exchange ID', 'Total', 'Valid', 'GIVT', 'SIVT', 'Unknown', 'Valid %', 'GIVT %', 'SIVT %', 'Unknown %']
            st.dataframe(ex_display, use_container_width=True, hide_index=True)
        else: st.info("No exchange data available")
        
        st.info("**Categories are mutually exclusive:** Unknown > GIVT > SIVT > Valid. All percentages sum to 100%.")
        
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
        
        # Display current data summary
        st.markdown(f"""
        ## 🎯 Fraud Definition (MRC-Compliant)
        
        Following **MRC Invalid Traffic Detection and Filtration Standards** (v3.0), Invalid Traffic (IVT) is defined as traffic that cannot be validated as coming from a real user watching real content on a real TV device. This includes:
        
        - **GIVT (General Invalid Traffic)**: Non-human traffic from datacenters, bots, or invalid events
        - **SIVT (Sophisticated Invalid Traffic)**: Traffic that mimics human behavior but fails device/context validation
        - **Unknown**: Traffic missing critical identifiers for proper classification
        
        ## 📊 Mutually Exclusive Classification Hierarchy
        
        Categories applied in **priority order** (highest to lowest). Once classified, events are excluded from lower-priority categories:
        
        | Priority | Category | Criteria | Detection Method |
        |----------|----------|----------|------------------|
        | 🔴 1 | **Unknown** | Missing auction ID (`is_missing_auction = 1`) | Database flag |
        | 🟠 2 | **GIVT** | Datacenter IP OR invalid event type (with auction ID) | IP range + event validation |
        | 🟡 3 | **SIVT** | Device category mismatch (not GIVT, with auction ID) | Device fingerprint analysis |
        | 🟢 4 | **Valid** | None of the above | Passes all checks |
        
        ### 🔍 GIVT Detection Details
        
        GIVT is detected through two complementary methods:
        
        **1. Datacenter Traffic**
        - IP addresses from known cloud provider ranges (AWS, GCP, Azure, etc.)
        - Flag: `is_datacenter = 1`
        - These IPs cannot represent real TV viewers
        
        **2. Invalid Events**
        - Events with null or 'None' event types
        - Flag: `is_invalid_event = 1`
        - Suggests malformed or bot-generated bid requests
        
        ### 🔍 SIVT Detection Details
        
        SIVT is detected through **device category mismatch analysis**:
        
        - **Detected Category**: The device type identified by Peer39's device detection
        - **Reported Category**: The device type claimed in the bid request
        - **Mismatch**: When detected ≠ reported, suggests fraud
        - Flag: `is_device_mismatch_sivt = 1`
        - **Requires**: Valid auction ID, not GIVT
        
        ## 📊 Current Data Summary
        
        | Category | Events | Percentage | Status |
        |----------|--------|------------|--------|
        | ✅ Valid | {valid:,} | {valid/total*100:.1f}% | ✅ Clean Traffic |
        | ❌ GIVT | {givt:,} | {givt/total*100:.1f}% | ⚠️ General Invalid |
        | ├─ Datacenter | {datacenter:,} | {datacenter/total*100:.2f}% | 🏢 Cloud IPs |
        | └─ Invalid Events | {invalid_event:,} | {invalid_event/total*100:.2f}% | 🔄 Malformed Events |
        | ❌ SIVT | {sivt:,} | {sivt/total*100:.1f}% | 🎯 Sophisticated Invalid |
        | ❓ Unknown | {unknown:,} | {unknown/total*100:.1f}% | 🔍 Missing Auction ID |
        | **Total** | **{total:,}** | **100%** | - |
        
        ## 📋 MRC Compliance Checklist
        
        | MRC Requirement | Implementation Status | Notes |
        |-----------------|----------------------|-------|
        | **GIVT Detection** | ✅ Implemented | Datacenter IPs + Invalid Events |
        | **SIVT Detection** | ✅ Implemented | Device Category Mismatch |
        | **Traffic Filtration** | ✅ Implemented | Mutually Exclusive Classification |
        | **Auction ID Validation** | ✅ Implemented | Unknown classification |
        | **Multi-Device Detection** | ⏳ Roadmap | Planned for Phase 4 |
        | **Volume Anomaly Detection** | ⏳ Roadmap | Planned for Phase 4 |
        | **Overnight Traffic Detection** | ⏳ Roadmap | Planned for Phase 4 |
        
        ## 🛡️ Data Quality Metrics
        
        | Metric | Value | Interpretation |
        |--------|-------|----------------|
        | **Data Completeness** | {total:,} events | Full dataset analyzed |
        | **Auction ID Coverage** | {(total-unknown)/total*100:.1f}% | { "✅ Good" if (total-unknown)/total > 0.8 else "⚠️ Needs Improvement" } |
        | **Invalid Rate** | {(givt+sivt)/total*100:.1f}% | { "✅ Acceptable" if (givt+sivt)/total < 0.2 else "⚠️ High Invalid Rate" } |
        | **GIVT Rate** | {givt/total*100:.1f}% | { "✅ Normal" if givt/total < 0.1 else "⚠️ Elevated GIVT" } |
        | **SIVT Rate** | {sivt/total*100:.1f}% | { "✅ Normal" if sivt/total < 0.1 else "⚠️ Elevated SIVT" } |
        """)
        
        # Show GIVT vs SIVT comparison chart
        st.subheader("📊 GIVT vs SIVT Composition")
        givt_sivt_data = pd.DataFrame([
            {'Category': 'GIVT', 'Events': givt, 'Percentage': f"{givt/total*100:.1f}%"},
            {'Category': 'SIVT', 'Events': sivt, 'Percentage': f"{sivt/total*100:.1f}%"},
            {'Category': 'Unknown', 'Events': unknown, 'Percentage': f"{unknown/total*100:.1f}%"},
            {'Category': 'Valid', 'Events': valid, 'Percentage': f"{valid/total*100:.1f}%"}
        ])
        
        col1, col2 = st.columns([3, 2])
        with col1:
            fig_composition = px.pie(givt_sivt_data[givt_sivt_data['Events'] > 0], 
                                     values='Events', names='Category',
                                     title='Traffic Composition',
                                     color='Category',
                                     color_discrete_map=P39_COLORS)
            fig_composition = style_plotly(fig_composition)
            fig_composition.update_traces(textposition='inside', textinfo='percent+label')
            st.plotly_chart(fig_composition, use_container_width=True)
        
        with col2:
            st.write("**Composition Details**")
            st.dataframe(givt_sivt_data[givt_sivt_data['Events'] > 0], 
                        use_container_width=True, hide_index=True)
        
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
        
        invalid_total = givt + sivt
        total_invalid_rate = invalid_total / total * 100
        
        # Determine overall risk level
        if total_invalid_rate > 20:
            risk_level = "🔴 CRITICAL"
            risk_color = "red"
        elif total_invalid_rate > 10:
            risk_level = "🟠 HIGH"
            risk_color = "orange"
        elif total_invalid_rate > 5:
            risk_level = "🟡 MEDIUM"
            risk_color = "gold"
        else:
            risk_level = "🟢 LOW"
            risk_color = "green"
        
        st.markdown(f"""
        ## 📊 Executive Summary
        
        | Metric | Value | Status |
        |--------|-------|--------|
        | **Data Analyzed** | {total:,} events | - |
        | **Valid Traffic** | {valid:,} ({valid/total*100:.1f}%) | ✅ Clean |
        | **Invalid Traffic** | {invalid_total:,} ({total_invalid_rate:.1f}%) | {risk_level} |
        | ├─ GIVT | {givt:,} ({givt/total*100:.1f}%) | ⚠️ General Invalid |
        | └─ SIVT | {sivt:,} ({sivt/total*100:.1f}%) | 🎯 Sophisticated Invalid |
        | **Unknown** | {unknown:,} ({unknown/total*100:.1f}%) | ❓ Missing Auction ID |
        | **Overall Risk Level** | {risk_level} | <span style='color:{risk_color}'>{total_invalid_rate:.1f}% Invalid</span> |
        """, unsafe_allow_html=True)
        
        # Risk Assessment Dashboard
        st.subheader("🚨 Risk Assessment Dashboard")
        
        risk_col1, risk_col2, risk_col3, risk_col4 = st.columns(4)
        with risk_col1:
            st.metric("⚠️ Invalid Rate", f"{total_invalid_rate:.1f}%", 
                     delta=f"{total_invalid_rate - 5:.1f}% above baseline", 
                     delta_color="inverse" if total_invalid_rate > 5 else "normal")
        with risk_col2:
            st.metric("🏢 Datacenter Traffic", f"{datacenter/total*100:.2f}%", 
                     delta=f"{datacenter:,} events")
        with risk_col3:
            st.metric("🔄 Malformed Events", f"{invalid_event/total*100:.2f}%", 
                     delta=f"{invalid_event:,} events")
        with risk_col4:
            st.metric("📱 Device Mismatches", f"{sivt/total*100:.1f}%", 
                     delta=f"{sivt:,} events", delta_color="inverse" if sivt > 0 else "normal")
        
        # 🚨 Critical Alerts Section
        st.subheader("🚨 Critical Alerts")
        
        alert_col1, alert_col2 = st.columns(2)
        
        with alert_col1:
            # GIVT Alerts
            givt_alerts = []
            if givt > 0:
                givt_alerts.append(f"**GIVT Detected:** {givt:,} events ({givt/total*100:.1f}%)")
                if datacenter > 0:
                    givt_alerts.append(f"  - 🏢 Datacenter Traffic: {datacenter:,} events")
                if invalid_event > 0:
                    givt_alerts.append(f"  - 🔄 Invalid Events: {invalid_event:,} events")
                if not dsp_data.empty:
                    # DSPs with 100% GIVT
                    full_givt = dsp_data[dsp_data['givt_pct'] == 100]
                    if not full_givt.empty:
                        for _, row in full_givt.head(5).iterrows():
                            givt_alerts.append(f"  - ⛔ DSP {row['dsp_id']}: 100% GIVT")
                st.error("\n".join(givt_alerts))
            else:
                st.success("✅ No GIVT detected in the current filter")
        
        with alert_col2:
            # SIVT Alerts
            sivt_alerts = []
            if sivt > 0:
                sivt_alerts.append(f"**SIVT Detected:** {sivt:,} events ({sivt/total*100:.1f}%)")
                if not sivt_breakdown.empty:
                    top_mismatches = sivt_breakdown.head(3)
                    for _, row in top_mismatches.iterrows():
                        sivt_alerts.append(f"  - 🔄 {row['mismatch_type']}: {row['event_count']:,} events")
                st.warning("\n".join(sivt_alerts))
            else:
                st.success("✅ No SIVT detected in the current filter")
        
        if unknown > 0:
            st.info(f"🔍 **Unknown Traffic:** {unknown:,} events ({unknown/total*100:.1f}%) - Missing auction IDs")
        
        # 📊 DSP Analysis
        st.subheader("📊 DSP Performance Analysis")
        
        if not dsp_data.empty:
            # Filter DSPs by performance
            dsp_data_copy = dsp_data.copy()
            dsp_data_copy['risk_category'] = dsp_data_copy['givt_pct'].apply(
                lambda x: '🔴 Critical' if x >= 50 else ('🟠 High' if x >= 20 else ('🟡 Medium' if x >= 10 else '🟢 Low'))
            )
            
            # Show top offenders
            st.write("**🔴 DSPs with Highest Invalid Rates (Top 10)**")
            top_offenders = dsp_data_copy.sort_values('givt_pct', ascending=False).head(10)
            
            # Create a bar chart for DSP performance
            fig_dsp = px.bar(top_offenders, x='dsp_id', y=['valid_pct', 'givt_pct', 'sivt_pct', 'unknown_pct'],
                            title='DSP Traffic Composition (Top 10 by Invalid Rate)',
                            labels={'value': 'Percentage', 'variable': 'Category', 'dsp_id': 'DSP ID'},
                            color_discrete_map={
                                'valid_pct': '#8cba51',
                                'givt_pct': '#d92d20',
                                'sivt_pct': '#E6AF2E',
                                'unknown_pct': '#757575'
                            })
            fig_dsp = style_plotly(fig_dsp)
            fig_dsp.update_layout(barmode='stack', xaxis_tickangle=-45)
            st.plotly_chart(fig_dsp, use_container_width=True)
            
            # Display table
            st.write("**📋 DSP Performance Data**")
            dsp_display = top_offenders[['dsp_id', 'total_events', 'valid_pct', 'givt_pct', 'sivt_pct', 'unknown_pct']].copy()
            dsp_display.columns = ['DSP ID', 'Total Events', 'Valid %', 'GIVT %', 'SIVT %', 'Unknown %']
            st.dataframe(dsp_display, use_container_width=True, hide_index=True)
            
            # Immediate action recommendations for DSPs
            critical_dsps = dsp_data[dsp_data['givt_pct'] >= 50]
            if not critical_dsps.empty:
                st.error(f"**🚨 IMMEDIATE ACTION REQUIRED:** {len(critical_dsps)} DSP(s) have ≥50% GIVT rate")
                for _, row in critical_dsps.iterrows():
                    st.error(f"  - **DSP {row['dsp_id']}**: {row['givt_pct']:.0f}% GIVT — RECOMMEND: Block immediately")
        
        # 🔄 SIVT Analysis
        st.subheader("🔄 SIVT Device Mismatch Analysis")
        
        if not sivt_breakdown.empty:
            # Show top mismatch patterns
            st.write("**Top Device Mismatch Patterns**")
            
            fig_sivt_pattern = px.bar(sivt_breakdown.head(10), x='mismatch_type', y='event_count',
                                     title='Top 10 Device Mismatch Patterns',
                                     color='event_count',
                                     color_continuous_scale='YlOrRd')
            fig_sivt_pattern = style_plotly(fig_sivt_pattern)
            fig_sivt_pattern.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig_sivt_pattern, use_container_width=True)
            
            # Detailed table
            st.write("**📋 SIVT Mismatch Details**")
            sivt_display = sivt_breakdown[['mismatch_type', 'event_count', 'unique_ips', 'unique_dsps']].copy()
            sivt_display.columns = ['Mismatch Pattern', 'Events', 'Unique IPs', 'Unique DSPs']
            st.dataframe(sivt_display, use_container_width=True, hide_index=True)
            
            # Recommendations based on SIVT patterns
            st.subheader("💡 SIVT Recommendations")
            top_mismatch = sivt_breakdown.iloc[0] if not sivt_breakdown.empty else None
            
            if top_mismatch is not None:
                st.markdown(f"""
                **Primary Issue:** `{top_mismatch['mismatch_type']}` with {top_mismatch['event_count']:,} events
                
                **Recommended Actions:**
                1. 🎯 **Device Verification**: Implement pre-bid device validation
                2. 📊 **DSP Review**: Check DSPs with high SIVT rates
                3. 🔍 **Pattern Analysis**: Investigate detected → reported mismatch patterns
                4. 🛡️ **Blocking Rules**: Create rules for frequent mismatch patterns
                """)
        else:
            st.success("✅ No device category mismatches detected - SIVT is clean!")
        
        # 📋 Production Roadmap
        st.subheader("🚀 Production Roadmap")
        
        col1, col2 = st.columns([3, 2])
        
        with col1:
            st.markdown("""
            | Phase | Timeline | Actions |
            |-------|----------|---------|
            | **Phase 1** | Week 1 | ✅ Block 100% GIVT DSPs, ✅ Block datacenter IPs, ✅ Alert on high GIVT rates |
            | **Phase 2** | Month 1 | 🔄 Fix auction ID pass-through, 🔄 SIVT monitoring dashboard, 🔄 Automated alerts |
            | **Phase 3** | Month 2 | 🎯 Device verification pre-bid, 🎯 SSAI validation, 🎯 Publisher quality scoring |
            | **Phase 4** | Month 3 | 📊 Multi-Device detection, 📊 Volume anomaly detection, 📊 Overnight traffic detection |
            """)
        
        with col2:
            # Current status
            st.write("**✅ Implementation Status**")
            if givt > 0:
                st.warning(f"⚠️ {givt/total*100:.1f}% GIVT — Immediate action needed")
            if sivt > 0:
                st.warning(f"⚠️ {sivt/total*100:.1f}% SIVT — Monitoring recommended")
            if unknown > 0:
                st.info(f"🔍 {unknown/total*100:.1f}% Unknown — Investigation needed")
            
            if givt == 0 and sivt == 0:
                st.success("✅ All traffic validated — Great quality!")
        
        # Final Summary
        st.subheader("📋 Summary & Next Steps")
        
        st.markdown(f"""
        **Current Status:** {risk_level} Risk Level ({total_invalid_rate:.1f}% Invalid)
        
        **Top Priority Actions:**
        """)
        
        priority_actions = []
        if givt/total > 0.1:
            priority_actions.append("🔴 **Immediate:** Block DSPs with >50% GIVT rate")
        if datacenter > 0:
            priority_actions.append("🏢 **Immediate:** Block datacenter IP ranges")
        if sivt > 0:
            priority_actions.append("🔄 **High Priority:** Investigate SIVT mismatch patterns")
        if unknown > 0:
            priority_actions.append("🔍 **Medium Priority:** Fix auction ID pass-through")
        
        if priority_actions:
            for action in priority_actions:
                st.markdown(f"- {action}")
        else:
            st.success("✅ No critical issues detected — Maintain current monitoring")
        
        if unknown > 0:
            st.info(f"**Note:** {unknown:,} events ({unknown/total*100:.1f}%) classified as Unknown due to missing auction IDs. Fixing this will improve classification accuracy.")
        
    else:
        st.info("No data available for the selected filters")

# ============================================
# PAGE 4: TRACE A CASE
# ============================================
else:
    peer39_header("CTV Fraud Detector")
    st.title("Trace a Case — End-to-End Audit")
    st.markdown("Select a flagged IP to trace the fraud reasoning end-to-end.")
    
    traceable_ips = get_traceable_ips(200)
    
    if not traceable_ips.empty:
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.subheader("Select an IP to Trace")
            classifications = ['All'] + traceable_ips['classification'].unique().tolist()
            selected_class = st.selectbox("Filter by Classification", classifications)
            
            if selected_class != 'All':
                filtered = traceable_ips[traceable_ips['classification'] == selected_class]
            else:
                filtered = traceable_ips
            
            st.write(f"**{len(filtered)} IPs available**")
            
            ip_list = filtered.head(50).copy()
            ip_options = []
            for _, row in ip_list.iterrows():
                ip_options.append(f"{row['ip']} | {row['classification']} | {row['event_count']:,} events")
            
            selected_option = st.selectbox("Select IP", ip_options)
            selected_ip = selected_option.split(" | ")[0]
            
            manual_ip = st.text_input("Or enter IP manually:", placeholder="e.g., 192.168.1.1")
            if manual_ip:
                selected_ip = manual_ip
        
        with col2:
            if selected_ip:
                st.subheader(f"Audit: {selected_ip}")
                
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
                    st.write(f"Showing {len(details)} sample events:")
                    
                    class_breakdown = details['classification'].value_counts().reset_index()
                    class_breakdown.columns = ['Classification', 'Count']
                    st.write("**Classification Breakdown:**")
                    st.dataframe(class_breakdown, use_container_width=True, hide_index=True)
                    
                    st.write("**Raw Event Details:**")
                    display_cols = ['date', 'dsp_id', 'exchange_id', 'p39_device_type', 'detected_category', 'reported_category', 'classification']
                    if all(c in details.columns for c in display_cols):
                        trace_display = details[display_cols].copy()
                        trace_display.columns = ['Date', 'DSP', 'Exchange', 'Raw Device', 'Detected Cat.', 'Reported Cat.', 'Classification']
                        st.dataframe(trace_display, use_container_width=True, hide_index=True)
                    
                    givt_events = len(details[details['classification'].str.contains('GIVT', na=False)])
                    sivt_events = len(details[details['classification'].str.contains('SIVT', na=False)])
                    unknown_events = len(details[details['classification'].str.contains('Unknown', na=False)])
                    
                    vc1, vc2, vc3 = st.columns(3)
                    with vc1: st.metric("GIVT Events", givt_events)
                    with vc2: st.metric("SIVT Events", sivt_events)
                    with vc3: st.metric("Unknown Events", unknown_events)
                    
                    if sivt_events > 0:
                        sivt_samples = details[details['classification'].str.contains('SIVT', na=False)]
                        if not sivt_samples.empty:
                            sample = sivt_samples.iloc[0]
                            st.success(f"**SIVT Verified:** Detected `{sample['detected_category']}` but reported as `{sample['reported_category']}` — Device mismatch confirmed.")
                else:
                    st.warning(f"No traceable events found for IP `{selected_ip}`")
    else:
        st.warning("No traceability data available.")

conn.close()