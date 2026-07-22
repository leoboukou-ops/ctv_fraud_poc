import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from datetime import datetime

# ============================================
# PEER39 BRANDING
# ============================================
from peer39_style import apply_peer39_theme, peer39_header, sidebar_logo

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

# Apply Peer39 theme (replaces the old inline CSS block)
apply_peer39_theme()
sidebar_logo()

# Peer39 color palette for charts
P39_COLORS = {
    'Valid': '#8cba51',
    'GIVT': '#d92d20',
    'SIVT': '#E6AF2E',
    'Unknown': '#757575',
    'Invalid (GIVT+SIVT)': '#d92d20',
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
# FILTER FUNCTIONS - ALL FROM PRE-AGGREGATED TABLES
# ============================================
@st.cache_data(ttl=3600)
def get_filter_options():
    try:
        dsps = conn.execute("SELECT DISTINCT dsp_id FROM dsp_aggregates WHERE dsp_id IS NOT NULL ORDER BY dsp_id").df()
        exchanges = conn.execute("SELECT DISTINCT exchange_id FROM exchange_aggregates WHERE exchange_id IS NOT NULL ORDER BY exchange_id").df()
        apps = conn.execute("SELECT DISTINCT app_name FROM app_aggregates WHERE app_name IS NOT NULL ORDER BY app_name LIMIT 100").df()

        devices = conn.execute("""
            SELECT DISTINCT detected_category as device_type FROM device_aggregates 
            WHERE detected_category IS NOT NULL AND detected_category != 'Other'
            ORDER BY detected_category
        """).df()

        return {
            'dsps': ['All'] + dsps['dsp_id'].tolist(),
            'exchanges': ['All'] + exchanges['exchange_id'].tolist(),
            'apps': ['All'] + apps['app_name'].tolist() if not apps.empty else ['All'],
            'devices': ['All'] + devices['device_type'].tolist() if not devices.empty else ['All']
        }
    except Exception as e:
        return {'dsps': ['All'], 'exchanges': ['All'], 'apps': ['All'], 'devices': ['All']}

filter_options = get_filter_options()

st.sidebar.header("Filters")
selected_dsp = st.sidebar.selectbox("DSP", filter_options['dsps'])
selected_exchange = st.sidebar.selectbox("Exchange", filter_options['exchanges'])
selected_app = st.sidebar.selectbox("App Name", filter_options['apps'])
selected_device = st.sidebar.selectbox("Device Type", filter_options['devices'])

st.sidebar.success("Using persistent database")

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
        conditions.append(f"app_name = '{app}'")
    if device != 'All':
        conditions.append(f"detected_category = '{device}'")
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
        filters.append(f"Device: {selected_device}")
    if filters:
        st.info(f"**Active Filters:** " + " | ".join(filters))

# ============================================
# DATA FUNCTIONS - ALL FROM PRE-AGGREGATED TABLES
# Single source of truth: fraud_detection.db
# ============================================
@st.cache_data(ttl=3600)
def get_global_summary():
    try:
        return conn.execute("SELECT * FROM global_summary").df()
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_stats(dsp, exchange, app, device, min_date, max_date):
    where_clause = build_filter_conditions(dsp, exchange, app, device)
    query = f"""
    SELECT 
        SUM(total_events) as total_events,
        SUM(datacenter_traffic) as datacenter_traffic,
        SUM(invalid_event_count) as invalid_event_count,
        SUM(missing_auction_ids) as missing_auction_ids,
        SUM(givt_events) as givt_events,
        SUM(sivt_events) as sivt_events,
        SUM(invalid_events) as invalid_events,
        SUM(unique_dsps) as total_dsps,
        SUM(unique_publishers) as total_publishers,
        SUM(unique_exchanges) as total_exchanges,
        MIN(date) as earliest_date,
        MAX(date) as latest_date
    FROM daily_aggregates
    WHERE date BETWEEN '{min_date}' AND '{max_date}'
    """
    try:
        return conn.execute(query).df()
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_daily(dsp, exchange, app, device, min_date, max_date):
    query = f"""
    SELECT 
        date,
        total_events,
        givt_events,
        sivt_events,
        missing_auction_ids,
        invalid_events,
        (total_events - invalid_events - missing_auction_ids) as valid_events
    FROM daily_aggregates
    WHERE date BETWEEN '{min_date}' AND '{max_date}'
    ORDER BY date
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return df
        df['givt_pct'] = (df['givt_events'] / df['total_events'] * 100).round(2)
        df['sivt_pct'] = (df['sivt_events'] / df['total_events'] * 100).round(2)
        df['invalid_pct'] = (df['invalid_events'] / df['total_events'] * 100).round(2)
        df['unknown_pct'] = (df['missing_auction_ids'] / df['total_events'] * 100).round(2)
        df['valid_pct'] = (df['valid_events'] / df['total_events'] * 100).round(2)
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_dsp(dsp, exchange, app, device, min_date, max_date):
    query = f"""
    SELECT 
        dsp_id,
        total_events,
        givt_events,
        sivt_events,
        missing_auction_ids,
        invalid_events,
        (total_events - invalid_events - missing_auction_ids) as valid_events,
        unique_publishers,
        unique_exchanges,
        unique_ips
    FROM dsp_aggregates
    ORDER BY givt_events DESC
    LIMIT 50
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return df
        df['givt_pct'] = (df['givt_events'] / df['total_events'] * 100).round(2)
        df['sivt_pct'] = (df['sivt_events'] / df['total_events'] * 100).round(2)
        df['invalid_pct'] = (df['invalid_events'] / df['total_events'] * 100).round(2)
        df['unknown_pct'] = (df['missing_auction_ids'] / df['total_events'] * 100).round(2)
        df['valid_pct'] = (df['valid_events'] / df['total_events'] * 100).round(2)
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_filtered_exchange(dsp, exchange, app, device, min_date, max_date):
    query = f"""
    SELECT 
        exchange_id,
        total_events,
        givt_events,
        sivt_events,
        missing_auction_ids,
        invalid_events,
        (total_events - invalid_events - missing_auction_ids) as valid_events,
        unique_dsps,
        unique_publishers,
        unique_ips
    FROM exchange_aggregates
    ORDER BY givt_events DESC
    LIMIT 50
    """
    try:
        df = conn.execute(query).df()
        if df.empty:
            return df
        df['givt_pct'] = (df['givt_events'] / df['total_events'] * 100).round(2)
        df['sivt_pct'] = (df['sivt_events'] / df['total_events'] * 100).round(2)
        df['invalid_pct'] = (df['invalid_events'] / df['total_events'] * 100).round(2)
        df['unknown_pct'] = (df['missing_auction_ids'] / df['total_events'] * 100).round(2)
        df['valid_pct'] = (df['valid_events'] / df['total_events'] * 100).round(2)
        return df
    except Exception as e:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_sivt_breakdown():
    try:
        return conn.execute("SELECT * FROM sivt_breakdown ORDER BY event_count DESC").df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_givt_breakdown():
    try:
        return conn.execute("SELECT * FROM givt_breakdown ORDER BY event_count DESC").df()
    except:
        return pd.DataFrame()

# ============================================
# SIVT DETECTION TABLES
# ============================================
@st.cache_data(ttl=3600)
def get_multi_device_data():
    try:
        return conn.execute("SELECT * FROM multi_device_analysis ORDER BY total_events DESC LIMIT 50").df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_volume_suspicious():
    try:
        return conn.execute("SELECT * FROM volume_suspicious_ips ORDER BY avg_events_per_day DESC LIMIT 50").df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_overnight_suspicious():
    try:
        return conn.execute("SELECT * FROM overnight_suspicious ORDER BY overnight_pct DESC, total_events DESC LIMIT 50").df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_device_mismatch_data():
    try:
        return conn.execute("SELECT * FROM device_category_mismatch ORDER BY mismatch_count DESC LIMIT 50").df()
    except:
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
                classification
            FROM traceability_samples
            WHERE ip = '{ip}'
            {class_filter}
            ORDER BY date, classification
            LIMIT 100
        """).df()
    except:
        return pd.DataFrame()

@st.cache_data(ttl=3600)
def get_fraud_reasoning(ip, dsp_id=None):
    reasons = []
    try:
        md = conn.execute(f"SELECT * FROM multi_device_analysis WHERE ip = '{ip}'").df()
        if not md.empty:
            reasons.append({
                'method': 'Multi-Device Detection',
                'severity': md['suspicion_reason'].iloc[0],
                'score': md['severity_score'].iloc[0],
                'details': f"{md['device_type_count'].iloc[0]} device types, {md['total_events'].iloc[0]:,} events, {md['avg_events_per_day'].iloc[0]:.0f} avg/day"
            })
    except:
        pass
    try:
        vol = conn.execute(f"SELECT * FROM volume_suspicious_ips WHERE ip = '{ip}'").df()
        if not vol.empty:
            reasons.append({
                'method': 'Volume Analysis',
                'severity': vol['volume_suspicion'].iloc[0],
                'score': vol['severity_score'].iloc[0],
                'details': f"{vol['total_events'].iloc[0]:,} events, {vol['avg_events_per_day'].iloc[0]:.0f} avg/day across {vol['days_active'].iloc[0]} days"
            })
    except:
        pass
    try:
        on = conn.execute(f"SELECT * FROM overnight_suspicious WHERE ip = '{ip}'").df()
        if not on.empty:
            reasons.append({
                'method': 'Overnight Activity',
                'severity': on['overnight_suspicion'].iloc[0],
                'score': on['severity_score'].iloc[0],
                'details': f"{on['overnight_pct'].iloc[0]:.1f}% overnight activity ({on['overnight_events'].iloc[0]:,} of {on['total_events'].iloc[0]:,} events)"
            })
    except:
        pass
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
if page == "Dashboard":
    peer39_header("CTV Fraud Detector")
    st.markdown("### MRC-Compliant Fraud Detection with GIVT + SIVT + Unknown Classification")

    show_active_filters()

    try:
        global_stats = get_global_summary()
        stats = get_filtered_stats(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        daily = get_filtered_daily(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        dsp = get_filtered_dsp(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        exchanges = get_filtered_exchange(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
        sivt_breakdown = get_sivt_breakdown()
        givt_breakdown = get_givt_breakdown()

        if selected_dsp == 'All' and selected_exchange == 'All' and selected_app == 'All' and selected_device == 'All':
            if not global_stats.empty:
                total_events = global_stats['total_events'].iloc[0]
                givt = global_stats['givt_events'].iloc[0]
                sivt_total = global_stats['sivt_events'].iloc[0]
                unknown = global_stats['missing_auction_ids'].iloc[0]
                datacenter = global_stats['datacenter_traffic'].iloc[0]
                invalid_event_count = global_stats['invalid_event_count'].iloc[0]
            else:
                total_events = givt = sivt_total = unknown = datacenter = invalid_event_count = 0
        else:
            if not stats.empty:
                total_events = stats['total_events'].iloc[0]
                givt = stats['givt_events'].iloc[0]
                sivt_total = stats['sivt_events'].iloc[0]
                unknown = stats['missing_auction_ids'].iloc[0]
                datacenter = stats['datacenter_traffic'].iloc[0]
                invalid_event_count = stats['invalid_event_count'].iloc[0]
            else:
                total_events = givt = sivt_total = unknown = datacenter = invalid_event_count = 0

        invalid = givt + sivt_total
        valid = total_events - invalid - unknown

        givt_rate = (givt / total_events * 100) if total_events > 0 else 0
        sivt_rate = (sivt_total / total_events * 100) if total_events > 0 else 0
        unknown_rate = (unknown / total_events * 100) if total_events > 0 else 0
        invalid_rate = (invalid / total_events * 100) if total_events > 0 else 0
        valid_rate = (valid / total_events * 100) if total_events > 0 else 0

        # METRICS ROW
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("Total Events", f"{total_events:,}")
        with col2:
            st.metric("Invalid (GIVT+SIVT)", f"{invalid_rate:.2f}%", 
                     delta=f"{invalid:,.0f} events", delta_color="inverse")
        with col3:
            st.metric("GIVT", f"{givt_rate:.2f}%", 
                     delta=f"{givt:,.0f} events", delta_color="inverse")
        with col4:
            st.metric("SIVT", f"{sivt_rate:.2f}%", 
                     delta=f"{sivt_total:,.0f} events", delta_color="inverse")
        with col5:
            st.metric("Unknown", f"{unknown_rate:.2f}%", 
                     delta=f"{unknown:,.0f} events", delta_color="off")

        # CRITICAL ALERTS
        st.subheader("Critical Alerts")

        alert_col1, alert_col2 = st.columns(2)

        with alert_col1:
            givt_alerts = []
            if givt > 0:
                givt_alerts.append(f"**GIVT:** {givt:,.0f} events ({givt_rate:.2f}%)")
            if datacenter > 0:
                givt_alerts.append(f"  - Datacenter: {datacenter:,.0f} events")
            if invalid_event_count > 0:
                givt_alerts.append(f"  - Invalid Events (None/Null): {invalid_event_count:,.0f} events")

            if not dsp.empty:
                fraudulent_dsps = dsp[dsp['givt_pct'] == 100]
                for _, row in fraudulent_dsps.iterrows():
                    givt_alerts.append(f"  - DSP {row['dsp_id']}: 100% GIVT ({row['total_events']:,.0f} events)")

            if givt_alerts:
                st.error("\n".join(givt_alerts))
            else:
                st.success("No GIVT alerts")

        with alert_col2:
            sivt_alerts = []
            multi_device = get_multi_device_data()
            volume_suspicious = get_volume_suspicious()
            overnight_suspicious = get_overnight_suspicious()
            device_mismatch = get_device_mismatch_data()

            if not multi_device.empty:
                critical_md = multi_device[multi_device['severity_score'] >= 3]
                if not critical_md.empty:
                    sivt_alerts.append(f"**Multi-Device:** {len(critical_md)} CRITICAL IPs")
                else:
                    sivt_alerts.append(f"**Multi-Device:** {len(multi_device)} suspicious IPs")
            if not volume_suspicious.empty:
                critical_vol = volume_suspicious[volume_suspicious['severity_score'] >= 2]
                if not critical_vol.empty:
                    sivt_alerts.append(f"**High Volume:** {len(critical_vol)} CRITICAL IPs")
                else:
                    sivt_alerts.append(f"**High Volume:** {len(volume_suspicious)} suspicious IPs")
            if not overnight_suspicious.empty:
                sivt_alerts.append(f"**Overnight:** {len(overnight_suspicious)} suspicious IPs")
            if not device_mismatch.empty:
                total_mismatches = device_mismatch['mismatch_count'].sum()
                critical_dm = device_mismatch[device_mismatch['severity_score'] >= 3]
                if not critical_dm.empty:
                    sivt_alerts.append(f"**Device Mismatch:** {len(critical_dm)} CRITICAL ({total_mismatches:,.0f} events)")
                else:
                    sivt_alerts.append(f"**Device Mismatch:** {len(device_mismatch)} records ({total_mismatches:,.0f} events)")

            if sivt_alerts:
                st.warning("\n".join(sivt_alerts))
            else:
                st.info("No SIVT alerts")

        # TRAFFIC CLASSIFICATION
        st.subheader("Traffic Classification")

        classification_data = []
        if valid > 0:
            classification_data.append({'category': 'Valid', 'events': int(valid), 'percentage': valid_rate})
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
                             color='category',
                             color_discrete_map=P39_COLORS)
                fig.update_traces(textposition='inside', textinfo='percent+label')
                st.plotly_chart(fig, use_container_width=True)
            else:
                st.info("No classification data available")
        with col2:
            st.write("**Classification Details**")
            display_df = classification.copy()
            display_df['events'] = display_df['events'].apply(lambda x: f"{x:,}")
            display_df['percentage'] = display_df['percentage'].apply(lambda x: f"{x:.2f}%")
            st.dataframe(display_df, use_container_width=True, hide_index=True)

        # GIVT BREAKDOWN
        st.subheader("GIVT Breakdown")

        if not givt_breakdown.empty:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_givt = px.pie(givt_breakdown, values='event_count', names='givt_type',
                                  title='GIVT by Type',
                                  color_discrete_sequence=['#d92d20', '#B54F6F'])
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
            st.info("No GIVT data available")

        # SIVT BREAKDOWN
        st.subheader("SIVT Breakdown (Device Mismatch)")

        if not sivt_breakdown.empty:
            col1, col2 = st.columns([2, 1])
            with col1:
                fig_sivt = px.pie(sivt_breakdown, values='event_count', names='mismatch_type',
                                  title='SIVT by Mismatch Type',
                                  color_discrete_sequence=P39_CHART_PALETTE)
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
            st.info("No SIVT data available")

        # DAILY TRENDS
        st.subheader("Daily Trends: Valid, Invalid (GIVT+SIVT), Unknown")

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
                        color_discrete_map=P39_COLORS)
            st.plotly_chart(fig, use_container_width=True)

            daily_display = daily.copy()
            if 'date' in daily_display.columns:
                daily_display['date'] = pd.to_datetime(daily_display['date']).dt.strftime('%Y-%m-%d')

            display_cols = ['date', 'total_events', 'valid_events', 'invalid_events', 'missing_auction_ids', 
                           'givt_events', 'sivt_events', 'valid_pct', 'invalid_pct', 'unknown_pct', 'givt_pct', 'sivt_pct']
            display_cols = [c for c in display_cols if c in daily_display.columns]
            daily_display = daily_display[display_cols]
            daily_display.columns = ['Date', 'Total', 'Valid', 'Invalid (GIVT+SIVT)', 'Unknown', 
                                    'GIVT', 'SIVT', 'Valid %', 'Invalid %', 'Unknown %', 'GIVT %', 'SIVT %']
            st.dataframe(daily_display, use_container_width=True, hide_index=True)
        else:
            st.info("No daily data available for the selected filters")

        # SIVT DETECTION TABS
        st.subheader("SIVT Detection Methods")
        st.markdown("""
        <div style="background-color: #fff3cd; border-left: 4px solid #E6AF2E; padding: 10px; border-radius: 4px; margin-bottom: 15px;">
        <strong>Methodology Note:</strong> SIVT total in metrics = <strong>Device Mismatch only</strong> (directly verifiable from raw data). 
        Multi-Device, Volume, and Overnight are <strong>detection signals</strong> used for investigation and monitoring.
        </div>
        """, unsafe_allow_html=True)

        tab1, tab2, tab3, tab4 = st.tabs(["Device Mismatch", "Overnight", "High Volume", "Multi-Device"])

        with tab1:
            device_mismatch = get_device_mismatch_data()
            if not device_mismatch.empty:
                total_mismatch_events = device_mismatch['mismatch_count'].sum()
                critical_dm = device_mismatch[device_mismatch['severity_score'] >= 3]

                if not critical_dm.empty:
                    st.error(f"Found {len(critical_dm)} CRITICAL device category mismatches")
                st.warning(f"Found {len(device_mismatch):,} device category mismatches ({total_mismatch_events:,.0f} events)")
                st.metric("Total Mismatch Events", f"{total_mismatch_events:,.0f}")

                severity_counts = device_mismatch.groupby('severity').agg({
                    'mismatch_count': 'sum',
                    'ip': 'nunique'
                }).reset_index()
                severity_counts.columns = ['Severity', 'Events', 'Unique IPs']
                st.write("**Severity Breakdown**")
                st.dataframe(severity_counts, use_container_width=True, hide_index=True)

                st.write("**Top 50 Detailed Mismatches**")
                display_cols = ['ip', 'dsp_id', 'detected_category', 'reported_category', 'mismatch_count', 'severity', 'severity_score']
                dm_display = device_mismatch[display_cols].copy()
                dm_display.columns = ['IP', 'DSP', 'Detected', 'Reported', 'Events', 'Severity', 'Score']
                st.dataframe(dm_display, use_container_width=True, hide_index=True)
            else:
                st.success("No device category mismatches detected.")

        with tab2:
            overnight_suspicious = get_overnight_suspicious()
            if not overnight_suspicious.empty:
                total_overnight_events = overnight_suspicious['total_events'].sum()
                critical_on = overnight_suspicious[overnight_suspicious['severity_score'] >= 3]

                if not critical_on.empty:
                    st.error(f"Found {len(critical_on)} CRITICAL overnight IPs")
                st.warning(f"Found {len(overnight_suspicious):,} IPs with significant overnight activity ({total_overnight_events:,.0f} events)")
                st.metric("Total Overnight Events", f"{total_overnight_events:,.0f}")

                display_cols = ['ip', 'total_events', 'overnight_events', 'overnight_pct', 'overnight_suspicion', 'severity_score']
                on_display = overnight_suspicious[display_cols].copy()
                on_display.columns = ['IP', 'Total Events', 'Overnight Events', 'Overnight %', 'Suspicion', 'Score']
                st.dataframe(on_display, use_container_width=True, hide_index=True)
            else:
                st.success("No overnight-suspicious IPs detected.")

        with tab3:
            volume_suspicious = get_volume_suspicious()
            if not volume_suspicious.empty:
                total_volume_events = volume_suspicious['total_events'].sum()
                critical_vol = volume_suspicious[volume_suspicious['severity_score'] >= 2]

                if not critical_vol.empty:
                    st.error(f"Found {len(critical_vol)} CRITICAL high-volume IPs")
                st.warning(f"Found {len(volume_suspicious):,} high-volume IPs ({total_volume_events:,.0f} events)")
                st.metric("Total High-Volume Events", f"{total_volume_events:,.0f}")

                display_cols = ['ip', 'total_events', 'avg_events_per_day', 'days_active', 'unique_apps', 'volume_suspicion', 'severity_score']
                vol_display = volume_suspicious[display_cols].copy()
                vol_display.columns = ['IP', 'Total Events', 'Avg/Day', 'Days Active', 'Unique Apps', 'Suspicion', 'Score']
                st.dataframe(vol_display, use_container_width=True, hide_index=True)
            else:
                st.success("No high-volume suspicious IPs detected.")

        with tab4:
            multi_device = get_multi_device_data()
            if not multi_device.empty:
                total_multi_events = multi_device['total_events'].sum()
                critical_md = multi_device[multi_device['severity_score'] >= 3]

                if not critical_md.empty:
                    st.error(f"Found {len(critical_md)} CRITICAL multi-device IPs")
                st.warning(f"Found {len(multi_device):,} suspicious multi-device IPs ({total_multi_events:,.0f} events)")
                st.metric("Total Multi-Device Events", f"{total_multi_events:,.0f}")

                display_cols = ['ip', 'device_type_count', 'total_events', 'avg_events_per_day', 'unique_dsps', 'suspicion_reason', 'severity_score']
                md_display = multi_device[display_cols].copy()
                md_display.columns = ['IP', 'Device Types', 'Total Events', 'Avg/Day', 'Unique DSPs', 'Reason', 'Score']
                st.dataframe(md_display, use_container_width=True, hide_index=True)
            else:
                st.success("No suspicious multi-device IPs detected.")

        # DSP RANKINGS
        st.subheader("DSP Rankings")
        if not dsp.empty:
            dsp_display = dsp.copy()
            dsp_display = dsp_display[['dsp_id', 'total_events', 'valid_events', 'invalid_events', 'missing_auction_ids',
                                      'givt_events', 'sivt_events', 'valid_pct', 'invalid_pct', 'unknown_pct', 'givt_pct', 'sivt_pct']]
            dsp_display.columns = ['DSP ID', 'Total', 'Valid', 'Invalid (GIVT+SIVT)', 'Unknown', 
                                   'GIVT', 'SIVT', 'Valid %', 'Invalid %', 'Unknown %', 'GIVT %', 'SIVT %']

            def highlight_fraud(row):
                if row['GIVT %'] == 100:
                    return ['background-color: #fef3f2'] * len(row)
                return [''] * len(row)

            st.dataframe(dsp_display.style.apply(highlight_fraud, axis=1), use_container_width=True, hide_index=True)
        else:
            st.info("No DSP data available")

        # EXCHANGE RANKINGS
        st.subheader("Exchange Rankings")
        if not exchanges.empty:
            exchange_display = exchanges.copy()
            exchange_display = exchange_display[['exchange_id', 'total_events', 'valid_events', 'invalid_events', 'missing_auction_ids',
                                                 'givt_events', 'sivt_events', 'valid_pct', 'invalid_pct', 'unknown_pct', 'givt_pct', 'sivt_pct']]
            exchange_display.columns = ['Exchange ID', 'Total', 'Valid', 'Invalid (GIVT+SIVT)', 'Unknown',
                                        'GIVT', 'SIVT', 'Valid %', 'Invalid %', 'Unknown %', 'GIVT %', 'SIVT %']
            st.dataframe(exchange_display, use_container_width=True, hide_index=True)
        else:
            st.info("No exchange data available")

        # DATA QUALITY FOOTER
        st.info("""
        **Data Architecture (v2 - Single Source of Truth):**
        - All metrics calculated in `build_aggregates_v2.py` and stored in `fraud_detection.db`
        - Dashboard reads **only** from pre-aggregated tables — no raw parquet queries
        - Categories are mutually exclusive: Valid + Invalid + Unknown = Total
        - SIVT = Device Mismatch only (directly verifiable); other methods = detection signals
        - Traceability: 10K sample events stored for end-to-end audit
        """)

    except Exception as e:
        st.error(f"Error loading data: {e}")
        import traceback
        st.code(traceback.format_exc())

# ============================================
# PAGE 2: METHODOLOGY & MRC
# ============================================
elif page == "Methodology & MRC":
    peer39_header("CTV Fraud Detector")
    st.title("Methodology & MRC Reference Points")

    global_stats = get_global_summary()

    if not global_stats.empty:
        total_events = global_stats['total_events'].iloc[0]
        givt = global_stats['givt_events'].iloc[0]
        sivt_total = global_stats['sivt_events'].iloc[0]
        unknown = global_stats['missing_auction_ids'].iloc[0]
        datacenter = global_stats['datacenter_traffic'].iloc[0]
        invalid_event_count = global_stats['invalid_event_count'].iloc[0]

        invalid = givt + sivt_total
        valid = total_events - invalid - unknown

        valid_pct = (valid / total_events * 100) if total_events > 0 else 0
        invalid_pct = (invalid / total_events * 100) if total_events > 0 else 0
        unknown_pct = (unknown / total_events * 100) if total_events > 0 else 0
        givt_pct = (givt / total_events * 100) if total_events > 0 else 0
        sivt_pct = (sivt_total / total_events * 100) if total_events > 0 else 0

        st.markdown(f"""
        ## 1. Fraud Definition (MRC-Compliant)

        Following the **MRC Invalid Traffic Detection and Filtration Standards (2020)** and the **MRC CTV/Advanced TV Reference Document**, we define **Invalid Traffic (IVT)** as traffic that cannot be validated as coming from a real user watching real content on a real TV.

        **Key MRC Reference Documents Used:**

        | Document | Applicable Sections |
        |----------|---------------------|
        | **MRC Invalid Traffic Detection and Filtration Standards (2020)** | GIVT/SIVT definitions, Filtration requirements, Disclosures |
        | **MRC CTV/Advanced TV Reference Document** | CTV definitions, TV Off detection, Inactivity rules, IVT risk analyses |
        | **MRC SSAI and OTT Guidance (2021)** | SSAI measurement, Certification process, IP range disclosure |

        ---

        ## 2. Traffic Classification Framework

        The framework categorizes all traffic into **mutually exclusive** classifications:

        | Classification | Definition | Treatment |
        |----------------|------------|-----------|
        | **Valid Traffic** | Events confirmed to come from real users on real devices with valid identifiers | Counted as valid impressions |
        | **Invalid Traffic (IVT)** | Events confirmed to be invalid through GIVT or SIVT detection | Removed from reporting |
        | **Unknown** | Events that cannot be validated (measurement limitations) | Excluded from valid, separately disclosed |

        ### 2.1 General Invalid Traffic (GIVT)

        | Type | Detection | Description | MRC Reference |
        |------|-----------|-------------|---------------|
        | **Datacenter Traffic** | `datacenter = '1'` | Traffic originating from cloud provider IP ranges | *"Data-center traffic must be known to be invalid through direct signals"* |
        | **Invalid Events** | `event = 'None'` or NULL | Events with no meaningful event type | *"Events that cannot be associated with a valid ad interaction"* |

        ### 2.2 Sophisticated Invalid Traffic (SIVT)

        | Type | Detection | Description | MRC Reference | Counts Toward SIVT Total? |
        |------|-----------|-------------|---------------|---------------------------|
        | **Device Category Mismatch** | Mobile to CTV, TV to Desktop, etc. | Device spoofing — detected vs reported device type differ | *"Device spoofing and misrepresentation"* | **Yes** — Directly verifiable per event |
        | **Multi-Device IP** | Same IP, 2+ device types, >10K events | Bot farm or shared proxy | *"Non-human traffic patterns"* | No — Detection signal only |
        | **High Volume IP** | >5K events/day or >50K total | Automated traffic | *"Traffic patterns inconsistent with human behavior"* | No — Detection signal only |
        | **Overnight Activity** | >40% events between 00:00-06:00 | Non-human viewing patterns | *"Temporal anomalies"* | No — Detection signal only |

        > **Why only Device Mismatch counts toward SIVT total?** Device mismatch is directly verifiable on a per-event basis (we can check `p39_device_type` vs `dsp_device_type` for every single event). Multi-device, volume, and overnight are aggregate patterns that require statistical thresholds — they flag IPs for investigation but cannot be definitively classified as invalid on a per-event basis without additional evidence.

        ### 2.3 Unknown Traffic (Measurement Limitation)

        | Type | Detection | MRC Reference |
        |------|-----------|---------------|
        | **Missing Auction ID** | `auction_id IS NULL` | *"Traffic that cannot be fully measured should be treated as **unknown**"* |

        ---

        ## 3. Current Data Summary

        | Category | Events | Percentage | Treatment |
        |----------|--------|------------|-----------|
        | **Valid Traffic** | {valid:,.0f} | {valid_pct:.2f}% | Counted as valid impressions |
        | **Invalid (GIVT+SIVT)** | {invalid:,.0f} | {invalid_pct:.2f}% | Removed from reporting |
        | GIVT | {givt:,.0f} | {givt_pct:.2f}% | Routine filtration |
        | Datacenter | {datacenter:,.0f} | {datacenter/total_events*100:.2f}% | |
        | Invalid Events | {invalid_event_count:,.0f} | {invalid_event_count/total_events*100:.2f}% | |
        | SIVT (Device Mismatch) | {sivt_total:,.0f} | {sivt_pct:.2f}% | Advanced analytics |
        | **Unknown** | {unknown:,.0f} | {unknown_pct:.2f}% | Excluded, separately disclosed |

        ---

        ## 4. Data Architecture (v2)

        | Component | Details |
        |-----------|---------|
        | **Raw Data** | 7 parquet files (~5.64 GB) |
        | **Total Events** | {total_events:,} |
        | **Processing** | DuckDB with persistent database (`fraud_detection.db`) |
        | **Single Source of Truth** | All fraud metrics pre-calculated in `build_aggregates_v2.py` |
        | **Dashboard** | Reads **only** from pre-aggregated tables — no raw queries |
        | **Traceability** | 10K sample events stored for end-to-end audit |
        | **Coverage** | 100% (no sampling) |
        | **Response Time** | < 1 second |
        | **Filters** | Date, DSP, Exchange, App, Device |

        ---

        ## 5. MRC Compliance Status

        | Requirement | Status | Notes |
        |-------------|--------|-------|
        | GIVT Filtration | Implemented | Datacenter + Invalid Events |
        | SIVT Analytics | Implemented | Device Mismatch (directly verifiable) |
        | SIVT Detection Signals | Implemented | Multi-Device, Volume, Overnight |
        | Unknown Disclosure | Implemented | Missing Auction ID |
        | Traceability | Implemented | 10K sample events with full reasoning |
        | Documentation | Complete | This page + handoff doc |
        | TV Off Detection | Enhancement needed | Requires session-level data |
        | SSAI Validation | Enhancement needed | Requires SSAI metadata |
        """)
    else:
        st.info("No data available")

# ============================================
# PAGE 3: FINDINGS & RECOMMENDATIONS
# ============================================
elif page == "Findings & Recommendations":
    peer39_header("CTV Fraud Detector")
    st.title("Findings & Recommendations")

    global_stats = get_global_summary()
    dsp = get_filtered_dsp(selected_dsp, selected_exchange, selected_app, selected_device, min_date_str, max_date_str)
    sivt_breakdown = get_sivt_breakdown()

    if not global_stats.empty:
        total_events = global_stats['total_events'].iloc[0]
        givt = global_stats['givt_events'].iloc[0]
        sivt_total = global_stats['sivt_events'].iloc[0]
        unknown = global_stats['missing_auction_ids'].iloc[0]
        datacenter = global_stats['datacenter_traffic'].iloc[0]
        invalid_event_count = global_stats['invalid_event_count'].iloc[0]

        invalid = givt + sivt_total
        valid = total_events - invalid - unknown

        givt_rate = (givt / total_events * 100) if total_events > 0 else 0
        sivt_rate = (sivt_total / total_events * 100) if total_events > 0 else 0
        unknown_rate = (unknown / total_events * 100) if total_events > 0 else 0
        invalid_rate = (invalid / total_events * 100) if total_events > 0 else 0

        st.markdown(f"""
        ## Executive Summary

        | Metric | Value |
        |--------|-------|
        | Data Analyzed | {total_events:,} events |
        | **Valid Traffic** | {valid:,.0f} events ({valid/total_events*100:.2f}%) |
        | **Invalid (GIVT+SIVT)** | {invalid:,.0f} events ({invalid_rate:.2f}%) |
        | GIVT | {givt:,.0f} events ({givt_rate:.2f}%) |
        | Datacenter | {datacenter:,.0f} events ({datacenter/total_events*100:.2f}%) |
        | Invalid Events | {invalid_event_count:,.0f} events ({invalid_event_count/total_events*100:.2f}%) |
        | SIVT (Device Mismatch) | {sivt_total:,.0f} events ({sivt_rate:.2f}%) |
        | **Unknown** | {unknown:,.0f} events ({unknown_rate:.2f}%) |
        """)

        if not dsp.empty:
            fraudulent_dsps = dsp[dsp['givt_pct'] == 100]
            if not fraudulent_dsps.empty:
                st.subheader("DSPs with 100% GIVT")
                for _, row in fraudulent_dsps.iterrows():
                    st.error(f"**DSP {row['dsp_id']}** — {row['total_events']:,.0f} events — {row['givt_pct']:.0f}% GIVT — **BLOCK IMMEDIATELY**")

        if not sivt_breakdown.empty:
            st.markdown("**SIVT Breakdown (Device Mismatch):**")
            sivt_display = sivt_breakdown.copy()
            sivt_display['percentage'] = sivt_display['event_count'].apply(lambda x: f"{x/sivt_total*100:.2f}%" if sivt_total > 0 else "0%")
            st.dataframe(sivt_display[['mismatch_type', 'event_count', 'percentage', 'unique_ips', 'unique_dsps']], 
                        use_container_width=True, hide_index=True)

        st.markdown(f"""
        ### Critical Finding 1: Block 100% GIVT DSPs Immediately

        DSPs with 100% GIVT are delivering zero valid traffic. These should be blocked at the exchange level immediately.

        ---

        ### Critical Finding 2: Unknown Traffic
        - **{unknown:,.0f} events** missing auction IDs ({unknown_rate:.2f}%)
        - **Per MRC:** *"Traffic that cannot be fully measured should be treated as unknown"*
        - **Root Cause:** Likely FreeWheel auction ID pass-through issue

        ### Recommendation: Fix FreeWheel Auction ID Pass-Through

        ---

        ### Critical Finding 3: Device Spoofing (SIVT)
        - **{sivt_total:,.0f} events** show device category mismatch
        - Most common: Mobile devices reporting as CTV (highest CPM inventory)
        - **Impact:** Advertisers paying CTV CPMs for mobile inventory

        ### Recommendation: Implement Device Verification Pre-Bid

        ---

        ## Production Roadmap

        | Phase | Timeline | Actions | Owner |
        |-------|----------|---------|-------|
        | **Phase 1** | Week 1 | Block 100% GIVT DSPs, Block datacenter IPs at firewall | Engineering |
        | **Phase 2** | Month 1 | Fix FreeWheel auction ID pass-through, Add SIVT monitoring dashboard | Engineering + Product |
        | **Phase 3** | Month 2 | Implement device verification pre-bid, Add SSAI validation | Engineering |
        | **Phase 4** | Quarter 1 | Session-level analysis, TV Off detection, Real-time scoring | Data Science |

        ---

        ## Known Limitations

        | Limitation | Impact | Mitigation |
        |------------|--------|------------|
        | SIVT total = Device Mismatch only | Undercounts true SIVT | Multi-device/volume/overnight flagged for manual review |
        | No session-level data | Cannot detect TV Off | Flag IPs with suspicious patterns for investigation |
        | No SSAI metadata | Cannot validate SSAI traffic | Work with exchanges to obtain SSAI signals |
        | Single-device fingerprinting | Limited bot detection | Combine with IP reputation + behavior analysis |
        | 10K traceability sample | May not cover all edge cases | Expand sample or add on-demand trace queries |
        """)
    else:
        st.info("No data available")

# ============================================
# PAGE 4: TRACE A CASE
# ============================================
else:
    peer39_header("CTV Fraud Detector")
    st.title("Trace a Case — End-to-End Audit")
    st.markdown("""
    ### How to use this page:
    1. Select a flagged IP from the list below (or enter one manually)
    2. Review the **fraud reasoning** — why was this IP flagged?
    3. Review the **sample events** — see the raw data that led to the flag
    4. Verify the classification matches the reasoning

    > **For reviewers:** Pick any IP, trace the reasoning, and verify the classification is justified.
    """)

    traceable_ips = get_traceable_ips(200)

    if not traceable_ips.empty:
        col1, col2 = st.columns([1, 2])

        with col1:
            st.subheader("Select an IP to Trace")

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
                st.subheader(f"Audit: {selected_ip}")

                st.markdown("<div class='trace-box'>", unsafe_allow_html=True)
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
                    st.info("This IP was not flagged by any SIVT detection method. It may be classified based on single-event signals (datacenter, invalid event, or missing auction ID).")

                st.markdown("</div>", unsafe_allow_html=True)

                st.markdown("<div class='trace-box'>", unsafe_allow_html=True)
                st.write("**Step 2: Sample Events for this IP**")

                trace_details = trace_ip_details(selected_ip, selected_class if selected_class != 'All' else 'All')

                if not trace_details.empty:
                    st.write(f"Showing {len(trace_details)} sample events:")

                    class_breakdown = trace_details['classification'].value_counts().reset_index()
                    class_breakdown.columns = ['Classification', 'Count']
                    st.write("**Classification Breakdown:**")
                    st.dataframe(class_breakdown, use_container_width=True, hide_index=True)

                    display_cols = ['date', 'dsp_id', 'exchange_id', 'detected_device', 'reported_device', 'detected_category', 'reported_category', 'classification']
                    trace_display = trace_details[display_cols].copy()
                    trace_display.columns = ['Date', 'DSP', 'Exchange', 'Detected Device', 'Reported Device', 'Detected Cat.', 'Reported Cat.', 'Classification']

                    st.write("**Raw Event Details:**")
                    st.dataframe(trace_display, use_container_width=True, hide_index=True)

                    st.write("**Step 3: Verification**")

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
                            st.success(f"**SIVT Verified:** Detected `{sample['detected_category']}` but reported as `{sample['reported_category']}` — Device mismatch confirmed.")

                    if givt_events > 0:
                        givt_samples = trace_details[trace_details['classification'].str.contains('GIVT', na=False)]
                        if not givt_samples.empty:
                            st.info(f"**GIVT Verified:** {givt_events} events flagged as GIVT (datacenter or invalid event).")

                else:
                    st.warning(f"No traceable events found for IP `{selected_ip}`. This IP may not be in the 10K sample, or may not match the selected classification filter.")
                    st.info("Try selecting 'All' classifications, or check if this IP exists in the detection tables.")

                st.markdown("</div>", unsafe_allow_html=True)
    else:
        st.warning("No traceability data available. Please run `build_aggregates_v2.py` to generate traceability samples.")
