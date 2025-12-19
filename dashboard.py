import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime
import json

# ==============================================================================
# 1. Dashboard Configuration
# ==============================================================================
st.set_page_config(layout="wide", page_title="Tobacco Curing System")

# Sidebar for Connection Settings
st.sidebar.header("🔌 Connection Settings")
# You can change the default value to your actual RPi IP
RPI_IP = st.sidebar.text_input("Raspberry Pi IP Address", value="192.168.1.100") 
PORT = "5050"
API_URL = f"http://{RPI_IP}:{PORT}"

REFRESH_RATE_SECONDS = 3

# ==============================================================================
# 2. API Interaction Functions
# ==============================================================================

@st.cache_data(ttl=REFRESH_RATE_SECONDS)
def get_status():
    """Fetches the current status from the Flask API."""
    try:
        response = requests.get(f"{API_URL}/api/status", timeout=2)
        response.raise_for_status()
        data = response.json()
        
        # Calculate uptime string
        uptime_seconds = data.get('uptime', 0)
        td = datetime.fromtimestamp(uptime_seconds) - datetime.fromtimestamp(0)
        data['uptime_str'] = str(td).split('.')[0]
        
        return data
    except requests.exceptions.RequestException as e:
        st.error(f"Cannot connect to RPi API at {API_URL}. Check IP and Port.")
        return None

def post_control(endpoint, payload=None):
    """Sends control commands to the Flask API."""
    try:
        response = requests.post(f"{API_URL}/api/{endpoint}", json=payload, timeout=2)
        response.raise_for_status()
        st.toast(f"Command '{endpoint}' successful!", icon='✅')
        time.sleep(0.5) # Short buffer for hardware to react
        st.rerun() 
    except requests.exceptions.RequestException as e:
        st.toast(f"Control command failed: {e}", icon='❌')

def get_trend_data():
    """Fetches historical data for charting."""
    try:
        response = requests.get(f"{API_URL}/api/trend_data", timeout=2)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException:
        return None

# ==============================================================================
# 3. Streamlit Dashboard Layout
# ==============================================================================

def display_dashboard():
    st.title("🍂 Remote Tobacco Curing Control")
    st.info(f"Connected to: `{API_URL}`")

    # Fetch all data
    data = get_status()
    trend_data = get_trend_data()
    
    if data is None:
        st.warning("Waiting for connection... ensure '16.py' is running on the Raspberry Pi.")
        if st.button("Retry Connection"):
            st.rerun()
        st.stop() 
        
    # --- 1. System Overview ---
    st.header("1. System Overview")
    col1, col2, col3, col4 = st.columns(4)
    
    next_increase_sec = data.get('next_temp_increase', 0)
    next_increase_str = f"{int(next_increase_sec // 60):02d}:{int(next_increase_sec % 60):02d}" if next_increase_sec > 0 else "N/A"

    col1.metric("Mode", data.get('mode', 'N/A'))
    col2.metric("Stage", data.get('stage', 'N/A').replace('_', ' '))
    col3.metric("Uptime", data.get('uptime_str', 'N/A'))
    col4.metric("Next Temp Increase", next_increase_str)

    st.divider()
    
    # --- 2. Current Readings ---
    st.header("2. Current Readings")
    temp_col, hum_col, target_col, fan_col = st.columns(4)
    
    target_temp = data.get('target_temp', 0)
    current_temp = data.get('temperature', 0)
    
    temp_col.metric("Temperature", f"{current_temp:.1f} °C", 
                    delta=f"Target: {target_temp:.1f} °C" if data.get('mode') == 'AUTO' else None)
    hum_col.metric("Humidity", f"{data.get('humidity', 0):.1f} %")
    
    fan_state = "ON" if data.get('fan_on') or data.get('fan_on_2') else "OFF"
    heater_state = "ON" if data.get('dehumidifier_on') or data.get('dehumidifier_on_2') else "OFF"
    
    target_col.metric("Heaters State", heater_state)
    fan_col.metric("Fans State", fan_state)

    if data.get('buzzer_on'):
        st.warning("🚨 OVER-TEMP ALARM IS ACTIVE!", icon="⚠️")
        
    st.divider()
    
    # --- 3. Data Trend ---
    st.header("3. Data Trend")
    if trend_data and trend_data.get('timestamps'):
        df = pd.DataFrame({
            'Time': [datetime.fromtimestamp(ts).strftime('%H:%M:%S') for ts in trend_data['timestamps']],
            'Temperature (°C)': trend_data['temperature'],
            'Humidity (%)': trend_data['humidity'],
            'Target Temp (°C)': trend_data['target_temp']
        }).set_index('Time')
        st.line_chart(df)
    else:
        st.info("No trend data available yet.")
        
    st.divider()
    
    # --- 4. System Controls ---
    st.header("4. System Controls")
    control_col, stage_col, servo_col = st.columns([1, 1, 1])

    with control_col:
        st.subheader("Mode & Reset")
        if st.button(f"🔄 Toggle Mode ({data.get('mode')})", type="primary", use_container_width=True):
            post_control('mode')
            
        if st.button("🔴 Reset System", use_container_width=True):
            post_control('reset')

    with stage_col:
        st.subheader("Change Stage")
        STAGES = ["YELLOWING", "LEAF_DRYING", "MIDRIB_DRYING"]
        for stage in STAGES:
            if st.button(stage.replace('_', ' ').title(), 
                         disabled=(data.get('stage') == stage), 
                         use_container_width=True):
                post_control('stage', {'stage': stage})

    with servo_col:
        st.subheader("Vent Control")
        current_angle = data.get('servo_angle', 0)
        new_angle = st.select_slider('Set Vent Angle (°)', options=[0, 45, 90, 180], value=current_angle)
        if new_angle != current_angle:
            post_control('servo', {'angle': new_angle})
            
    # Manual Overrides
    if data.get('mode') == 'MANUAL':
        st.subheader("Manual Actuator Overrides")
        m_col1, m_col2, m_col3, m_col4 = st.columns(4)
        if m_col1.button("Toggle Fan 1"): post_control('fan1_toggle')
        if m_col2.button("Toggle Heater 1"): post_control('heater1_toggle')
        if m_col3.button("Toggle Fan 2"): post_control('fan2_toggle')
        if m_col4.button("Toggle Heater 2"): post_control('heater2_toggle')

    # --- Auto-Refresh ---
    st.caption(f"Last updated: {datetime.now().strftime('%H:%M:%S')}")
    time.sleep(REFRESH_RATE_SECONDS)
    st.rerun()

if __name__ == '__main__':
    display_dashboard()
