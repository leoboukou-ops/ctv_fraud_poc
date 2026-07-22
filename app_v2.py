import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import os
from datetime import datetime

# ============================================
# DATABASE CONNECTION
# ============================================
db_path = 'fraud_detection.db'
if not os.path.exists(db_path):
    st.error("Database file not found!")
    st.info("Please run: python3 build_aggregates_v2.py")
    st.stop()

try:
    conn = duckdb.connect(db_path, read_only=True)
except Exception as e:
    st.error(f"Database connection error: {e}")
    st.stop()

st.set_page_config(page_title="CTV Fraud Detector", layout="wide")

# ============================================
# DEBUG MODE - Helps identify data issues
# ============================================
with st.sidebar.expander("🔧 Debug Info", expanded=True):
    try:
        # Test basic query
        total = conn.execute("SELECT COUNT(*) FROM normalized_devices").fetchone()[0]
        st.write(f"✅ Total events in DB: {total:,}")
        
        # Test date range
        dates = conn.execute("SELECT MIN(prt_dt), MAX(prt_dt) FROM normalized_devices").fetchone()
        st.write(f"📅 Date range: {dates[0]} to {dates[1]}")
        
        # Test filter options
        dsp_count = conn.execute("SELECT COUNT(DISTINCT dsp_id) FROM normalized_devices").fetchone()[0]
        st.write(f"🏢 Unique DSPs: {dsp_count:,}")
        
        exchange_count = conn.execute("SELECT COUNT(DISTINCT exchange_id) FROM normalized_devices").fetchone()[0]
        st.write(f"🔄 Unique Exchanges: {exchange_count:,}")
        
        device_count = conn.execute("SELECT COUNT(DISTINCT p39_device_type) FROM normalized_devices WHERE p39_device_type IS NOT NULL AND p39_device_type != ''").fetchone()[0]
        st.write(f"📱 Unique Device Types: {device_count:,}")
        
        app_count = conn.execute("SELECT COUNT(DISTINCT appstore_app_name) FROM normalized_devices WHERE appstore_app_name IS NOT NULL").fetchone()[0]
        st.write(f"📲 Unique Apps: {app_count:,}")
        
        # Test column existence
        columns = conn.execute("SELECT column_name FROM information_schema.columns WHERE table_name='normalized_devices'").df()
        st.write(f"📋 Columns in DB: {len(columns)}")
        
    except Exception as e:
        st.error(f"❌ Debug error: {e}")
        st.exception(e)

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

# Test with date filter in debug
with st.sidebar.expander("🔧 Debug Info", expanded=True):
    try:
        test_query = f"""
        SELECT COUNT(*) 
        FROM normalized_devices 
        WHERE prt_dt BETWEEN '{min_date_str}' AND '{max_date_str}'
        """
        filtered_total = conn.execute(test_query).fetchone()[0]
        st.write(f"📊 Events in selected date range: {filtered_total:,}")
    except Exception as e:
        st.error(f"❌ Date filter error: {e}")

# ============================================
# FILTER FUNCTIONS
# ============================================
@st.cache_data(ttl=3600)
def get_filter_options():
    """Get filter options from normalized_devices table."""
    try:
        dsps = conn.execute("SELECT DISTINCT dsp_id FROM normalized_devices WHERE dsp_id IS NOT NULL ORDER BY dsp_id").df()
        exchanges = conn.execute("SELECT DISTINCT exchange_id FROM normalized_devices WHERE exchange_id IS NOT NULL ORDER BY exchange_id").df()
        apps = conn.execute("SELECT DISTINCT appstore_app_name as app_name FROM normalized_devices WHERE appstore_app_name IS NOT NULL ORDER BY appstore_app_name LIMIT 100").df()
        
        devices = conn.execute("""
            SELECT DISTINCT p39_device_type 
            FROM normalized_devices 
            WHERE p39_device_type IS NOT NULL 
            AND p39_device_type != ''
            ORDER BY p39_device_type
        """).df()
        
        return {
            'dsps': ['All'] + dsps['dsp_id'].tolist() if not dsps.empty else ['All'],
            'exchanges': ['All'] + exchanges['exchange_id'].tolist() if not exchanges.empty else ['All'],
            'apps': ['All'] + apps['app_name'].tolist() if not apps.empty else ['All'],
            'devices': ['All'] + devices['p39_device_type'].tolist() if not devices.empty else ['All']
        }
    except Exception as e:
        st.sidebar.error(f"❌ Error loading filters: {e}")
        return {'dsps': ['All'], 'exchanges': ['All'], 'apps': ['All'], 'devices': ['All']}

# Initialize session state for filters
if 'selected_dsp' not in st.session_state:
    st.session_state.selected_dsp = 'All'
if 'selected_exchange' not in st.session_state:
    st.session_state.selected_exchange = 'All'
if 'selected_app' not in st.session_state:
    st.session_state.selected_app = 'All'
if 'selected_device' not in st.session_state:
    st.session_state.selected_device = 'All'

# Get filter options
filter_options = get_filter_options()

st.sidebar.header("🎯 Filters")

selected_dsp = st.sidebar.selectbox(
    "DSP", 
    filter_options['dsps'],
    index=filter_options['dsps'].index(st.session_state.selected_dsp) if st.session_state.selected_dsp in filter_options['dsps'] else 0
)
selected_exchange = st.sidebar.selectbox(
    "Exchange", 
    filter_options['exchanges'],
    index=filter_options['exchanges'].index(st.session_state.selected_exchange) if st.session_state.selected_exchange in filter_options['exchanges'] else 0
)
selected_app = st.sidebar.selectbox(
    "App Name", 
    filter_options['apps'],
    index=filter_options['apps'].index(st.session_state.selected_app) if st.session_state.selected_app in filter_options['apps'] else 0
)
selected_device = st.sidebar.selectbox(
    "Peer39 Device Type", 
    filter_options['devices'],
    index=filter_options['devices'].index(st.session_state.selected_device) if st.session_state.selected_device in filter_options['devices'] else 0
)

# Update session state
st.session_state.selected_dsp = selected_dsp
st.session_state.selected_exchange = selected_exchange
st.session_state.selected_app = selected_app
st.session_state.selected_device = selected_device

# Reset button
st.sidebar.markdown("---")
if st.sidebar.button("🔄 Reset All Filters"):
    st.session_state.selected_dsp = 'All'
    st.session_state.selected_exchange = 'All'
    st.session_state.selected_app = 'All'
    st.session_state.selected_device = 'All'
    st.rerun()

st.sidebar.success("✅ Using persistent database")

# ============================================
# BUILD FILTER CONDITIONS
# ============================================
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
    if selected_dsp != 'All':
        filters.append(f"DSP: {selected_dsp}")
    if selected_exchange != 'All':
        filters.append(f"Exchange: {selected_exchange}")
    if selected_app != 'All':
        filters.append(f"App: {selected_app}")
    if selected_device != 'All':
        filters.append(f"Peer39 Device: {selected_device}")
    if filters:
        st.info(f"🔍 **Active Filters:** " + " | ".join(filters))

# ============================================
# FILTERED DATA FUNCTIONS
# ============================================
@st.cache_data(ttl=3600)
def get_filtered_summary(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    query = f"""
    SELECT 
        COUNT(*) as total_events,
        SUM(is_datacenter) as datacenter_traffic,
        SUM(is_invalid_event) as invalid_event_count,
        SUM(is_missing_auction) as missing_auction_ids,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
        SUM(is_device_mismatch_sivt) as sivt_events,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
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
        st.error(f"❌ Summary query error: {e}")
        st.code(query)
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_daily(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    query = f"""
    SELECT 
        prt_dt as date,
        COUNT(*) as total_events,
        SUM(is_datacenter) as datacenter_traffic,
        SUM(is_invalid_event) as invalid_event_count,
        SUM(is_missing_auction) as missing_auction_ids,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
        SUM(is_device_mismatch_sivt) as sivt_events,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    GROUP BY prt_dt
    ORDER BY prt_dt
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return df
        
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['missing_auction_ids']
        df['givt_pct'] = (df['givt_events'] / df['total_events'] * 100).round(2)
        df['sivt_pct'] = (df['sivt_events'] / df['total_events'] * 100).round(2)
        df['invalid_pct'] = (df['invalid_events'] / df['total_events'] * 100).round(2)
        df['unknown_pct'] = (df['missing_auction_ids'] / df['total_events'] * 100).round(2)
        df['valid_pct'] = (df['valid_events'] / df['total_events'] * 100).round(2)
        
        return df
    except Exception as e:
        st.error(f"❌ Daily query error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_dsp(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    dsp_filter = f"AND dsp_id = '{dsp}'" if dsp != 'All' else ""
    
    query = f"""
    SELECT 
        dsp_id,
        COUNT(*) as total_events,
        SUM(is_datacenter) as datacenter_traffic,
        SUM(is_invalid_event) as invalid_event_count,
        SUM(is_missing_auction) as missing_auction_ids,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
        SUM(is_device_mismatch_sivt) as sivt_events,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
        COUNT(DISTINCT geo_ip_0) as unique_ips
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND dsp_id IS NOT NULL
    AND {where_clause}
    {dsp_filter}
    GROUP BY dsp_id
    HAVING COUNT(*) > 1000
    ORDER BY givt_events DESC
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return df
        
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['missing_auction_ids']
        df['givt_pct'] = (df['givt_events'] / df['total_events'] * 100).round(2)
        df['sivt_pct'] = (df['sivt_events'] / df['total_events'] * 100).round(2)
        df['invalid_pct'] = (df['invalid_events'] / df['total_events'] * 100).round(2)
        df['unknown_pct'] = (df['missing_auction_ids'] / df['total_events'] * 100).round(2)
        df['valid_pct'] = (df['valid_events'] / df['total_events'] * 100).round(2)
        
        return df
    except Exception as e:
        st.error(f"❌ DSP query error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_exchange(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    exchange_filter = f"AND exchange_id = '{exchange}'" if exchange != 'All' else ""
    
    query = f"""
    SELECT 
        exchange_id,
        COUNT(*) as total_events,
        SUM(is_datacenter) as datacenter_traffic,
        SUM(is_invalid_event) as invalid_event_count,
        SUM(is_missing_auction) as missing_auction_ids,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 THEN 1 ELSE 0 END) as givt_events,
        SUM(is_device_mismatch_sivt) as sivt_events,
        SUM(CASE WHEN is_datacenter = 1 OR is_invalid_event = 1 OR is_device_mismatch_sivt = 1 THEN 1 ELSE 0 END) as invalid_events,
        COUNT(DISTINCT geo_ip_0) as unique_ips
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND exchange_id IS NOT NULL
    AND {where_clause}
    {exchange_filter}
    GROUP BY exchange_id
    HAVING COUNT(*) > 1000
    ORDER BY givt_events DESC
    LIMIT 20
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return df
        
        df['valid_events'] = df['total_events'] - df['invalid_events'] - df['missing_auction_ids']
        df['givt_pct'] = (df['givt_events'] / df['total_events'] * 100).round(2)
        df['sivt_pct'] = (df['sivt_events'] / df['total_events'] * 100).round(2)
        df['invalid_pct'] = (df['invalid_events'] / df['total_events'] * 100).round(2)
        df['unknown_pct'] = (df['missing_auction_ids'] / df['total_events'] * 100).round(2)
        df['valid_pct'] = (df['valid_events'] / df['total_events'] * 100).round(2)
        
        return df
    except Exception as e:
        st.error(f"❌ Exchange query error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_sivt_breakdown(dsp, exchange, app, device, min_date, max_date):
    """Get SIVT breakdown from pre-aggregated table."""
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    query = f"""
    SELECT 
        detected_category || ' → ' || reported_category as mismatch_type,
        detected_category,
        reported_category,
        COUNT(*) as event_count,
        COUNT(DISTINCT geo_ip_0) as unique_ips,
        COUNT(DISTINCT dsp_id) as unique_dsps
    FROM normalized_devices
    WHERE is_device_mismatch_sivt = 1
    AND prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    GROUP BY detected_category, reported_category
    ORDER BY event_count DESC
    """
    try:
        return conn.execute(query).df()
    except Exception as e:
        st.error(f"❌ SIVT breakdown error: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_givt_breakdown(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    query = f"""
    SELECT 
        'Datacenter Traffic' as givt_type,
        SUM(is_datacenter) as event_count
    FROM normalized_devices
    WHERE is_datacenter = 1
    AND prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    UNION ALL
    SELECT 
        'Invalid Event (None/Null)' as givt_type,
        SUM(is_invalid_event) as event_count
    FROM normalized_devices
    WHERE is_invalid_event = 1
    AND prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return pd.DataFrame(columns=['givt_type', 'event_count'])
        return df
    except Exception as e:
        st.error(f"❌ GIVT breakdown error: {e}")
        return pd.DataFrame(columns=['givt_type', 'event_count'])

@st.cache_data(ttl=3600)
def get_device_mismatch_data(dsp, exchange, app, device, min_date, max_date):
    """Get device mismatch data - returns total records, total events, and top 50 records."""
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    # Get total counts
    count_query = f"""
    SELECT 
        COUNT(*) as total_records,
        COALESCE(SUM(mismatch_count), 0) as total_events
    FROM device_category_mismatch
    WHERE ip IN (SELECT DISTINCT geo_ip_0 FROM normalized_devices WHERE {where_clause})
    """
    try:
        result = conn.execute(count_query).fetchone()
        total_records = result[0] if result else 0
        total_events = result[1] if result else 0
    except:
        total_records = 0
        total_events = 0
    
    # Get top 50 records
    query = f"""
    SELECT 
        ip,
        dsp_id,
        detected_category,
        reported_category,
        mismatch_count,
        days_active,
        severity,
        severity_score
    FROM device_category_mismatch
    WHERE ip IN (SELECT DISTINCT geo_ip_0 FROM normalized_devices WHERE {where_clause})
    ORDER BY mismatch_count DESC
    LIMIT 50
    """
    try:
        df = conn.execute(query).df()
        return df, total_records, total_events
    except:
        return pd.DataFrame(), total_records, total_events

# ============================================
# DEVICE TYPE DISTRIBUTION
# ============================================
@st.cache_data(ttl=3600)
def get_device_distribution(dsp, exchange, app, device, min_date, max_date):
    """Get device type distribution using detected_category for reporting."""
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    query = f"""
    SELECT 
        detected_category as device_type,
        COUNT(*) as event_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    AND detected_category IS NOT NULL
    AND detected_category != 'Other'
    GROUP BY detected_category
    ORDER BY event_count DESC
    """
    try:
        return conn.execute(query).df()
    except Exception as e:
        st.error(f"❌ Device distribution error: {e}")
        return pd.DataFrame()

# ============================================
# RAW PEER39 DEVICE TYPE BREAKDOWN
# ============================================
@st.cache_data(ttl=3600)
def get_raw_device_types(dsp, exchange, app, device, min_date, max_date):
    """Get raw Peer39 device type distribution."""
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    
    query = f"""
    SELECT 
        p39_device_type as raw_device_type,
        COUNT(*) as event_count,
        ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER(), 2) as percentage
    FROM normalized_devices
    WHERE prt_dt BETWEEN '{min_date}' AND '{max_date}'
    AND {where_clause}
    AND p39_device_type IS NOT NULL
    AND p39_device_type != ''
    GROUP BY p39_device_type
    ORDER BY event_count DESC
    """
    try:
        return conn.execute(query).df()
    except Exception as e:
        st.error(f"❌ Raw device types error: {e}")
        return pd.DataFrame()

# ============================================
# TRACEABILITY FUNCTIONS
# ============================================
@st.cache_data(ttl=3600)
def get_traceable_ips(limit=100):
    try:
        return conn.execute(f"""
            SELECT DISTINCT ip, classification, COUNT(*) as event_count
            FROM traceability_samples
            GROUP BY ip, classification
            ORDER BY event_count DESC
            LIMIT {limit}
        """).df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def trace_ip_details(ip, classification_filter='All'):
    class_filter = f"AND classification = '{classification_filter}'" if classification_filter != 'All' else ""
    try:
        return conn.execute(f"""
            SELECT 
                ip, dsp_id, exchange_id, publisher_id, app_name, date,
                detected_device, reported_device, detected_category, reported_category,
                p39_device_type, classification
            FROM traceability_samples
            WHERE ip = '{ip}'
            {class_filter}
            ORDER BY date, classification
            LIMIT 100
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
            total_events = summary['total_events'].iloc[0]
            givt = summary['givt_events'].iloc[0]
            sivt_total = summary['sivt_events'].iloc[0]
            unknown = summary['missing_auction_ids'].iloc[0]
            datacenter = summary['datacenter_traffic'].iloc[0]
            invalid_event_count = summary['invalid_event_count'].iloc[0]
        else:
            st.warning("No data found for the selected filters")
            total_events = givt = sivt_total = unknown = datacenter = invalid_event_count = 0
        
        invalid = givt + sivt_total
        valid = total_events - invalid - unknown
        
        givt_rate = (givt / total_events * 100) if total_events > 0 else 0
        sivt_rate = (sivt_total / total_events * 100) if total_events > 0 else 0
        unknown_rate = (unknown / total_events * 100) if total_events > 0 else 0
        invalid_rate = (invalid / total_events * 100) if total_events > 0 else 0
        valid_rate = (valid / total_events * 100) if total_events > 0 else 0
        
        # ============================================
        # METRICS ROW
        # ============================================
        col1, col2, col3, col4, col5, col6 = st.columns(6)
        with col1:
            st.metric("Total Events", f"{total_events:,}" if total_events > 0 else "0")
        with col2:
            st.metric("Valid Traffic", f"{valid_rate:.2f}%", 
                     delta=f"{valid:,.0f} events" if valid > 0 else None, delta_color="normal")
        with col3:
            st.metric("Invalid (GIVT+SIVT)", f"{invalid_rate:.2f}%", 
                     delta=f"{invalid:,.0f} events" if invalid > 0 else None, delta_color="inverse")
        with col4:
            st.metric("GIVT", f"{givt_rate:.2f}%", 
                     delta=f"{givt:,.0f} events" if givt > 0 else None, delta_color="inverse")
        with col5:
            st.metric("SIVT", f"{sivt_rate:.2f}%", 
                     delta=f"{sivt_total:,.0f} events" if sivt_total > 0 else None, delta_color="inverse")
        with col6:
            st.metric("Unknown", f"{unknown_rate:.2f}%", 
                     delta=f"{unknown:,.0f} events" if unknown > 0 else None, delta_color="off")
        
        # ============================================
        # CRITICAL ALERTS
        # ============================================
        st.subheader("🚨 Critical Alerts")
        alert_col1, alert_col2 = st.columns(2)
        
        with alert_col1:
            givt_alerts = []
            if givt > 0:
                givt_alerts.append(f"**GIVT:** {givt:,.0f} events ({givt_rate:.2f}%)")
            if datacenter > 0:
                givt_alerts.append(f"  - Datacenter: {datacenter:,.0f} events")
            if invalid_event_count > 0:
                givt_alerts.append(f"  - Invalid Events: {invalid_event_count:,.0f} events")
            if not dsp.empty:
                fraudulent_dsps = dsp[dsp['givt_pct'] == 100]
                for _, row in fraudulent_dsps.iterrows():
                    givt_alerts.append(f"  - 🚨 DSP {row['dsp_id']}: 100% GIVT ({row['total_events']:,.0f} events)")
            if givt_alerts:
                st.error("\n".join(givt_alerts))
            else:
                st.success("✅ No GIVT alerts")
        
        with alert_col2:
            sivt_alerts = []
            if sivt_total > 0:
                sivt_alerts.append(f"**SIVT (Device Mismatch):** {sivt_total:,.0f} events ({sivt_rate:.2f}%)")
            if unknown > 0:
                sivt_alerts.append(f"**Unknown:** {unknown:,.0f} events ({unknown_rate:.2f}%)")
            if sivt_alerts:
                st.warning("\n".join(sivt_alerts))
            else:
                st.info("✅ No SIVT alerts")
        
        # ============================================
        # DEVICE TYPE DISTRIBUTION (detected_category)
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
            before any categorization or mapping. This filter controls which device types are included in the analysis.
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
        # TRAFFIC CLASSIFICATION
        # ============================================
        st.subheader("📊 Traffic Classification")
        
        classification_data = []
        if valid > 0:
            classification_data.append({'category': 'Valid Traffic', 'events': int(valid), 'percentage': valid_rate})
        if givt > 0:
            classification_data.append({'category': 'GIVT', 'events': int(givt), 'percentage': givt_rate})
        if sivt_total > 0:
            classification_data.append({'category': 'SIVT', 'events': int(sivt_total), 'percentage': sivt_rate})
        if unknown > 0:
            classification_data.append({'category': 'Unknown', 'events': int(unknown), 'percentage': unknown_rate})
        
        classification = pd.DataFrame(classification_data)
        
        col1, col2 = st.columns([2, 1])
        with col1:
            if not classification.empty and classification['events'].sum() > 0:
                fig = px.pie(classification, values='events', names='category', 
                             title='Traffic Classification',
                             color_discrete_sequence=['#2ecc71', '#e74c3c', '#f39c12', '#95a5a6'])
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No classification data available")
        with col2:
            st.write("**Classification Details**")
            if not classification.empty:
                display_df = classification.copy()
                display_df['events'] = display_df['events'].apply(lambda x: f"{x:,}")
                display_df['percentage'] = display_df['percentage'].apply(lambda x: f"{x:.2f}%")
                st.dataframe(display_df, use_container_width=True, hide_index=True)
            else:
                st.info("No classification data to display")
        
        # ============================================
        # GIVT BREAKDOWN
        # ============================================
        st.subheader("🛑 GIVT Breakdown")
        if not givt_breakdown.empty and givt_breakdown['event_count'].sum() > 0 and givt > 0:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_givt = px.pie(givt_breakdown, values='event_count', names='givt_type',
                                  title='GIVT by Type',
                                  color_discrete_sequence=['#e74c3c', '#c0392b'])
                fig_givt.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_givt, use_container_width=True)
            with col2:
                st.write("**GIVT Details**")
                givt_display = givt_breakdown.copy()
                givt_display['event_count'] = givt_display['event_count'].apply(lambda x: f"{x:,}")
                givt_display['percentage'] = givt_breakdown['event_count'].apply(
                    lambda x: f"{x/givt*100:.2f}%" if givt > 0 else "0.00%"
                )
                st.dataframe(givt_display, use_container_width=True, hide_index=True)
        else:
            st.info("No GIVT data available for the selected filters")
        
        # ============================================
        # SIVT BREAKDOWN
        # ============================================
        st.subheader("🔄 SIVT Breakdown (Device Mismatch)")
        if not sivt_breakdown.empty and sivt_breakdown['event_count'].sum() > 0 and sivt_total > 0:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_sivt = px.pie(sivt_breakdown, values='event_count', names='mismatch_type',
                                  title='SIVT by Mismatch Type',
                                  color_discrete_sequence=px.colors.qualitative.Set2)
                fig_sivt.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig_sivt, use_container_width=True)
            with col2:
                st.write("**SIVT Details**")
                sivt_display = sivt_breakdown.copy()
                sivt_display['event_count'] = sivt_display['event_count'].apply(lambda x: f"{x:,}")
                sivt_display['percentage'] = sivt_breakdown['event_count'].apply(
                    lambda x: f"{x/sivt_total*100:.2f}%" if sivt_total > 0 else "0.00%"
                )
                st.dataframe(sivt_display[['mismatch_type', 'event_count', 'percentage', 'unique_ips', 'unique_dsps']], 
                           use_container_width=True, hide_index=True)
        else:
            st.info("No SIVT data available for the selected filters")
        
        # ============================================
        # DAILY TRENDS
        # ============================================
        st.subheader("📈 Daily Trends: Valid, Invalid (GIVT+SIVT), Unknown")
        
        if not daily.empty:
            daily_melted = daily.melt(
                id_vars=['date'], 
                value_vars=['valid_events', 'invalid_events', 'missing_auction_ids'],
                var_name='category', 
                value_name='events'
            )
            
            category_map = {
                'valid_events': 'Valid',
                'invalid_events': 'Invalid (GIVT+SIVT)',
                'missing_auction_ids': 'Unknown'
            }
            daily_melted['category'] = daily_melted['category'].map(category_map)
            
            fig = px.bar(daily_melted, x='date', y='events', color='category',
                        title='Daily Events by Category',
                        barmode='stack',
                        labels={'events': 'Events', 'date': 'Date', 'category': 'Category'},
                        color_discrete_map={
                            'Valid': '#2ecc71',
                            'Invalid (GIVT+SIVT)': '#e74c3c',
                            'Unknown': '#95a5a6'
                        })
            st.plotly_chart(fig, use_container_width=True)
            
            daily_display = daily.copy()
            if 'date' in daily_display.columns:
                daily_display['date'] = pd.to_datetime(daily_display['date']).dt.strftime('%Y-%m-%d')
            
            display_cols = ['date', 'total_events', 'valid_events', 'invalid_events', 'missing_auction_ids', 
                           'givt_events', 'sivt_events', 'valid_pct', 'invalid_pct', 'unknown_pct', 'givt_pct', 'sivt_pct']
            display_cols = [c for c in display_cols if c in daily_display.columns]
            if display_cols:
                daily_display = daily_display[display_cols]
                daily_display.columns = ['Date', 'Total', 'Valid', 'Invalid (GIVT+SIVT)', 'Unknown', 
                                        'GIVT', 'SIVT', 'Valid %', 'Invalid %', 'Unknown %', 'GIVT %', 'SIVT %']
                st.dataframe(daily_display, use_container_width=True, hide_index=True)
        else:
            st.info("No daily data available for the selected filters")
        
        # ============================================
        # SIVT DETECTION
        # ============================================
        st.subheader("🔍 SIVT Detection — Device Mismatch")
        st.markdown("""
        <div style="background-color: #fff3cd; border-left: 4px solid #f39c12; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
        <strong>📋 Methodology Note:</strong> SIVT = <strong>Device Mismatch only</strong> (directly verifiable from raw data). 
        Multi-Device, Volume, and Overnight detections were evaluated and moved to the production roadmap as future enhancements.
        </div>
        """, unsafe_allow_html=True)
        
        if not sivt_breakdown.empty and sivt_breakdown['event_count'].sum() > 0:
            total_sivt = sivt_breakdown['event_count'].sum()
            st.warning(f"⚠️ Found {total_sivt:,.0f} SIVT events (Device Mismatches)")
            st.metric("Total SIVT Events", f"{total_sivt:,.0f}")
            
            st.write("**Breakdown by Mismatch Type:**")
            breakdown_display = sivt_breakdown.copy()
            breakdown_display['percentage'] = breakdown_display['event_count'].apply(
                lambda x: f"{x/total_sivt*100:.2f}%"
            )
            st.dataframe(breakdown_display[['mismatch_type', 'event_count', 'percentage', 'unique_ips', 'unique_dsps']], 
                        use_container_width=True, hide_index=True)
            
            with st.expander("📋 Top 50 Detailed Mismatches (Sample)"):
                device_mismatch, dm_records, dm_events = get_device_mismatch_data(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
                if device_mismatch is not None and not device_mismatch.empty:
                    display_cols = ['ip', 'dsp_id', 'detected_category', 'reported_category', 'mismatch_count', 'severity']
                    dm_display = device_mismatch[display_cols].copy()
                    dm_display.columns = ['IP', 'DSP', 'Detected', 'Reported', 'Events', 'Severity']
                    st.dataframe(dm_display, use_container_width=True, hide_index=True)
                else:
                    st.info("No detailed mismatch records available for the selected filters")
        else:
            st.success("✅ No device category mismatches detected for the selected filters.")
        
        # ============================================
        # DSP RANKINGS
        # ============================================
        st.subheader("🏢 DSP Rankings")
        if not dsp.empty:
            dsp_display = dsp.copy()
            dsp_display = dsp_display[['dsp_id', 'total_events', 'valid_events', 'invalid_events', 'missing_auction_ids',
                                      'givt_events', 'sivt_events', 'valid_pct', 'invalid_pct', 'unknown_pct', 'givt_pct', 'sivt_pct']]
            dsp_display.columns = ['DSP ID', 'Total', 'Valid', 'Invalid (GIVT+SIVT)', 'Unknown', 
                                   'GIVT', 'SIVT', 'Valid %', 'Invalid %', 'Unknown %', 'GIVT %', 'SIVT %']
            st.dataframe(dsp_display, use_container_width=True, hide_index=True)
        else:
            st.info("No DSP data available for the selected filters")
        
        # ============================================
        # EXCHANGE RANKINGS
        # ============================================
        st.subheader("🔄 Exchange Rankings")
        if not exchanges.empty:
            exchange_display = exchanges.copy()
            exchange_display = exchange_display[['exchange_id', 'total_events', 'valid_events', 'invalid_events', 'missing_auction_ids',
                                                 'givt_events', 'sivt_events', 'valid_pct', 'invalid_pct', 'unknown_pct', 'givt_pct', 'sivt_pct']]
            exchange_display.columns = ['Exchange ID', 'Total', 'Valid', 'Invalid (GIVT+SIVT)', 'Unknown',
                                        'GIVT', 'SIVT', 'Valid %', 'Invalid %', 'Unknown %', 'GIVT %', 'SIVT %']
            st.dataframe(exchange_display, use_container_width=True, hide_index=True)
        else:
            st.info("No exchange data available for the selected filters")
        
        # ============================================
        # FOOTER
        # ============================================
        st.info("""
        **📊 Data Architecture:**
        - All metrics calculated from `normalized_devices` view with filters applied
        - Device filter now uses raw Peer39 device types (`p39_device_type`) for filtering
        - All reporting uses `detected_category` for categorized device type analysis
        - SIVT = Device Mismatch only (directly verifiable per event)
        - Categories are mutually exclusive: Valid + Invalid + Unknown = Total
        - Multi-Device, Volume, and Overnight moved to production roadmap (see Findings page)
        """)
        
    except Exception as e:
        st.error(f"Error loading dashboard data: {e}")
        st.exception(e)

# ============================================
# PAGE 2: METHODOLOGY & MRC
# ============================================
elif page == "📋 Methodology & MRC":
    st.title("📋 Methodology & MRC Reference Points")

    summary = get_filtered_summary(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    sivt_breakdown = get_sivt_breakdown(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)

    if not summary.empty:
        total_events = summary['total_events'].iloc[0]
        givt = summary['givt_events'].iloc[0]
        sivt_total = summary['sivt_events'].iloc[0]
        unknown = summary['missing_auction_ids'].iloc[0]
        datacenter = summary['datacenter_traffic'].iloc[0]
        invalid_event_count = summary['invalid_event_count'].iloc[0]

        invalid = givt + sivt_total
        valid = total_events - invalid - unknown

        valid_pct = (valid / total_events * 100) if total_events > 0 else 0
        invalid_pct = (invalid / total_events * 100) if total_events > 0 else 0
        unknown_pct = (unknown / total_events * 100) if total_events > 0 else 0
        givt_pct = (givt / total_events * 100) if total_events > 0 else 0
        sivt_pct = (sivt_total / total_events * 100) if total_events > 0 else 0

        st.markdown(f"""
        ## 🎯 1. Fraud Definition (MRC-Compliant)

        Following the **MRC Invalid Traffic Detection and Filtration Standards (2020)** and the **MRC CTV/Advanced TV Reference Document**, we define **Invalid Traffic (IVT)** as traffic that cannot be validated as coming from a real user watching real content on a real TV.

        ---

        ## 📊 2. Traffic Classification Framework

        | Classification | Definition | Treatment |
        |----------------|------------|-----------|
        | **Valid Traffic** | Events confirmed to come from real users on real devices | Counted as valid impressions |
        | **Invalid Traffic (IVT)** | Events confirmed to be invalid through GIVT or SIVT detection | Removed from reporting |
        | **Unknown** | Events that cannot be validated (measurement limitations) | Excluded, separately disclosed |

        ---

        ## 📊 3. Current Data Summary
        """)

        st.markdown(f"""
        | Category | Events | Percentage | Treatment |
        |----------|--------|------------|-----------|
        | ✅ **Valid Traffic** | {valid:,.0f} | {valid_pct:.2f}% | Counted as valid impressions |
        | ❌ **Invalid (GIVT+SIVT)** | {invalid:,.0f} | {invalid_pct:.2f}% | Removed from reporting |
        | ├─ GIVT | {givt:,.0f} | {givt_pct:.2f}% | Routine filtration |
        | │  ├─ Datacenter | {datacenter:,.0f} | {datacenter/total_events*100:.2f}% | |
        | │  └─ Invalid Events | {invalid_event_count:,.0f} | {invalid_event_count/total_events*100:.2f}% | |
        | └─ SIVT (Device Mismatch) | {sivt_total:,.0f} | {sivt_pct:.2f}% | Advanced analytics |
        | ❓ **Unknown** | {unknown:,.0f} | {unknown_pct:.2f}% | Excluded, separately disclosed |
        """)
    else:
        st.info("No data available for the selected filters")

# ============================================
# PAGE 3: FINDINGS & RECOMMENDATIONS
# ============================================
elif page == "🔍 Findings & Recommendations":
    st.title("🔍 Findings & Recommendations")

    summary = get_filtered_summary(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    dsp = get_filtered_dsp(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    sivt_breakdown = get_sivt_breakdown(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)

    if not summary.empty:
        total_events = summary['total_events'].iloc[0]
        givt = summary['givt_events'].iloc[0]
        sivt_total = summary['sivt_events'].iloc[0]
        unknown = summary['missing_auction_ids'].iloc[0]
        datacenter = summary['datacenter_traffic'].iloc[0]
        invalid_event_count = summary['invalid_event_count'].iloc[0]

        invalid = givt + sivt_total
        valid = total_events - invalid - unknown

        givt_rate = (givt / total_events * 100) if total_events > 0 else 0
        sivt_rate = (sivt_total / total_events * 100) if total_events > 0 else 0
        unknown_rate = (unknown / total_events * 100) if total_events > 0 else 0
        invalid_rate = (invalid / total_events * 100) if total_events > 0 else 0

        st.markdown(f"""
        ## 📊 Executive Summary

        | Metric | Value |
        |--------|-------|
        | Data Analyzed | {total_events:,} events |
        | **Valid Traffic** | {valid:,.0f} events ({valid/total_events*100:.2f}%) |
        | **Invalid (GIVT+SIVT)** | {invalid:,.0f} events ({invalid_rate:.2f}%) |
        | ├─ GIVT | {givt:,.0f} events ({givt_rate:.2f}%) |
        | └─ SIVT (Device Mismatch) | {sivt_total:,.0f} events ({sivt_rate:.2f}%) |
        | **Unknown** | {unknown:,.0f} events ({unknown_rate:.2f}%) |
        """)

        if not dsp.empty:
            fraudulent_dsps = dsp[dsp['givt_pct'] == 100]
            if not fraudulent_dsps.empty:
                st.subheader("🚨 DSPs with 100% GIVT")
                for _, row in fraudulent_dsps.iterrows():
                    st.error(f"**DSP {row['dsp_id']}** — {row['total_events']:,.0f} events — {row['givt_pct']:.0f}% GIVT — **BLOCK IMMEDIATELY**")
    else:
        st.info("No data available for the selected filters")

# ============================================
# PAGE 4: TRACE A CASE
# ============================================
else:
    st.title("🔎 Trace a Case — End-to-End Audit")
    st.markdown("""
    ### How to use this page:
    1. Select a flagged IP from the list below (or enter one manually)
    2. Review the **fraud reasoning** — why was this IP flagged?
    3. Review the **sample events** — see the raw data that led to the flag
    4. Verify the classification matches the reasoning
    """)

    traceable_ips = get_traceable_ips(200)

    if not traceable_ips.empty:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("📋 Select an IP to Trace")
            classifications = ['All'] + traceable_ips['classification'].unique().tolist()
            selected_class = st.selectbox("Filter by Classification", classifications)

            if selected_class != 'All':
                filtered_ips = traceable_ips[traceable_ips['classification'] == selected_class]
            else:
                filtered_ips = traceable_ips

            st.write(f"**{len(filtered_ips)} IPs available**")

            ip_df = filtered_ips.head(50).copy()
            ip_df['label'] = ip_df.apply(lambda x: f"{x['ip']} ({x['classification']}, {x['event_count']:,} events)", axis=1)

            selected_ip = st.selectbox("Select IP", ip_df['ip'].tolist(), 
                                      format_func=lambda x: ip_df[ip_df['ip']==x]['label'].iloc[0] if not ip_df[ip_df['ip']==x].empty else x)

            manual_ip = st.text_input("Or enter IP manually:", placeholder="e.g., 192.168.1.1")
            if manual_ip:
                selected_ip = manual_ip

        with col2:
            if selected_ip:
                st.subheader(f"🔍 Audit: {selected_ip}")
                st.write("**Step 1: Why was this IP flagged?**")

                reasoning = get_fraud_reasoning(selected_ip)

                if not reasoning.empty:
                    for _, reason in reasoning.iterrows():
                        severity_class = "alert-critical" if reason['score'] >= 3 else "alert-high" if reason['score'] >= 2 else "alert-medium" if reason['score'] >= 1 else "alert-low"
                        st.markdown(f"""
                        <div class="metric-card {severity_class}">
                        <strong>{reason['method']}</strong><br>
                        <span style="color: #666;">{reason['severity']}</span><br>
                        <small>{reason['details']}</small>
                        </div>
                        """, unsafe_allow_html=True)
                else:
                    st.info("This IP was not flagged by any SIVT detection method.")

                st.write("**Step 2: Sample Events for this IP**")
                trace_details = trace_ip_details(selected_ip, selected_class if selected_class != 'All' else 'All')

                if not trace_details.empty:
                    st.write(f"Showing {len(trace_details)} sample events:")

                    class_breakdown = trace_details['classification'].value_counts().reset_index()
                    class_breakdown.columns = ['Classification', 'Count']
                    st.write("**Classification Breakdown:**")
                    st.dataframe(class_breakdown, use_container_width=True, hide_index=True)

                    display_cols = ['date', 'dsp_id', 'exchange_id', 'p39_device_type', 'detected_device', 'reported_device', 'detected_category', 'reported_category', 'classification']
                    trace_display = trace_details[display_cols].copy()
                    trace_display.columns = ['Date', 'DSP', 'Exchange', 'Raw Device Type', 'Detected Device', 'Reported Device', 'Detected Cat.', 'Reported Cat.', 'Classification']

                    st.write("**Raw Event Details (including Peer39 device type):**")
                    st.dataframe(trace_display, use_container_width=True, hide_index=True)

                    givt_events = len(trace_details[trace_details['classification'].str.contains('GIVT', na=False)])
                    sivt_events = len(trace_details[trace_details['classification'].str.contains('SIVT', na=False)])
                    unknown_events = len(trace_details[trace_details['classification'].str.contains('Unknown', na=False)])

                    verify_col1, verify_col2, verify_col3 = st.columns(3)
                    with verify_col1:
                        st.metric("GIVT Events", givt_events)
                    with verify_col2:
                        st.metric("SIVT Events", sivt_events)
                    with verify_col3:
                        st.metric("Unknown Events", unknown_events)

                    if sivt_events > 0:
                        sivt_samples = trace_details[trace_details['classification'].str.contains('SIVT', na=False)]
                        if not sivt_samples.empty:
                            sample = sivt_samples.iloc[0]
                            st.success(f"✅ **SIVT Verified:** Detected `{sample['detected_category']}` but reported as `{sample['reported_category']}` — Device mismatch confirmed.")
                else:
                    st.warning(f"No traceable events found for IP `{selected_ip}`.")
    else:
        st.warning("No traceability data available. Please run `build_aggregates_v2.py` to generate traceability samples.")

# Close the database connection
conn.close()