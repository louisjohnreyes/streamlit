import streamlit as st
import requests
import time
import pandas as pd
from datetime import datetime
import json

# ==============================================================================
# 1. Configuration - YOU MUST CHANGE THIS
# ==============================================================================

# IMPORTANT: Replace '127.0.0.1' with the actual IP address of your Raspberry Pi 
# on your local network (e.g., '192.168.1.100').
RPI_IP = '192.168.1.77' 
API_URL = f"http://{RPI_IP}:5050"

# Set the dashboard refresh rate in seconds
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
        st.error(f"Cannot connect to RPi API at {API_URL}. Is '16.py' running?")
        st.error(f"Error details: {e}")
        return None

def post_control(endpoint, payload=None):
    """Sends control commands to the Flask API."""
    try:
        response = requests.post(f"{API_URL}/api/{endpoint}", json=payload, timeout=2)
        response.raise_for_status()
        st.toast(f"Command '{endpoint}' successful!", icon='✅')
    except requests.exceptions.RequestException as e:
        st.toast(f"Control command failed: {e}", icon='❌')
    
    # Force Streamlit to re-run and refresh the status immediately
    st.session_state['rerun_trigger'] = time.time()
    st.experimental_rerun()

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
    """Main function to draw the Streamlit UI."""
    st.set_page_config(layout="wide", page_title="Tobacco Curing System")
    st.title("🍂 Remote Tobacco Curing Control")
    st.markdown(f"**API Endpoint:** `{API_URL}`")

    # Fetch all data
    data = get_status()
    trend_data = get_trend_data()
    
    if data is None:
        st.stop() # Stop if connection failed
        
    # --- Mode and Stage Display ---
    st.header("1. System Overview")
    
    col1, col2, col3, col4 = st.columns(4)
    
    # Calculate time until next temperature increase
    next_increase_sec = data.get('next_temp_increase', 0)
    next_increase_str = "N/A"
    if next_increase_sec > 0:
        minutes = int(next_increase_sec // 60)
        seconds = int(next_increase_sec % 60)
        next_increase_str = f"{minutes:02d}:{seconds:02d}"

    col1.metric("Mode", data.get('mode', 'N/A'))
    col2.metric("Stage", data.get('stage', 'N/A').replace('_', ' '))
    col3.metric("Uptime", data.get('uptime_str', 'N/A'))
    col4.metric("Next Temp Increase", next_increase_str)

    st.markdown("---")
    
    # --- Temperature and Humidity Gauges ---
    st.header("2. Current Readings")
    temp_col, hum_col, target_col, fan_col = st.columns(4)
    
    target_temp = data.get('target_temp', 0)
    current_temp = data.get('temperature', 0)
    
    temp_col.metric(
        "Temperature",
        f"{current_temp:.1f} °C",
        delta=f"Target: {target_temp:.1f} °C" if data.get('mode') == 'AUTO' else "Target: N/A"
    )
    hum_col.metric(
        "Humidity",
        f"{data.get('humidity', 0):.1f} %"
    )
    
    # Actuator Indicator
    fan_state = "ON" if data.get('fan_on') or data.get('fan_on_2') else "OFF"
    heater_state = "ON" if data.get('dehumidifier_on') or data.get('dehumidifier_on_2') else "OFF"
    
    target_col.metric("Heaters State", heater_state)
    fan_col.metric("Fans State", fan_state)

    if data.get('buzzer_on'):
        st.warning("🚨 OVER-TEMP ALARM IS ACTIVE!", icon="⚠️")
        
    st.markdown("---")
    
    # --- Trend Chart ---
    st.header("3. Data Trend")
    if trend_data and trend_data.get('timestamps'):
        try:
            df = pd.DataFrame({
                'Time': [datetime.fromtimestamp(ts).strftime('%H:%M:%S') for ts in trend_data['timestamps']],
                'Temperature (°C)': trend_data['temperature'],
                'Humidity (%)': trend_data['humidity'],
                'Target Temp (°C)': trend_data['target_temp']
            })
            
            df = df.set_index('Time')
            st.line_chart(df[['Temperature (°C)', 'Target Temp (°C)', 'Humidity (%)']])
            st.caption(f"Showing {len(df)} data points from the log.")
        except Exception as e:
            st.error(f"Error processing trend data: {e}")
            st.code(json.dumps(trend_data, indent=2))
    else:
        st.info("Trend data is not available or log file is empty.")
        
    st.markdown("---")
    
    # --- Control Panel ---
    st.header("4. System Controls")
    
    # Mode Toggle and Stage Selection
    control_col, stage_col, servo_col = st.columns([1, 1, 1])

    with control_col:
        st.subheader("Mode & Reset")
        current_mode = data.get('mode', 'N/A')
        
        mode_btn = st.button(f"🔄 Toggle Mode (Current: {current_mode})", type="primary")
        if mode_btn:
            post_control('mode')
            
        reset_btn = st.button("🔴 Reset System State")
        if reset_btn:
            # Confirm with the user before resetting
            if st.popover("Confirm Reset", help="This will stop the curing process and reset all parameters."):
                if st.button("I CONFIRM, Reset Now", type="danger"):
                    post_control('reset')

    with stage_col:
        st.subheader("Change Curing Stage")
        current_stage = data.get('stage', 'N/A')
        STAGES = ["YELLOWING", "LEAF_DRYING", "MIDRIB_DRYING"]
        
        st.markdown(f"**Current Stage:** `{current_stage.replace('_', ' ').title()}`")

        stage_cols = st.columns(3)
        for i, stage in enumerate(STAGES):
            display_name = stage.replace('_', ' ').title()
            
            # Disable buttons if already in that stage
            disabled = (current_stage == stage)
            
            if stage_cols[i].button(display_name, disabled=disabled):
                post_control('stage', {'stage': stage})

    with servo_col:
        st.subheader("Flue Gas Vent Control")
        # Ensure your SERVO_DUTY_CYCLES in 16.py supports these angles
        servo_options = [0, 45, 90, 180] 
        current_angle = data.get('servo_angle', 0)
        
        new_angle = st.select_slider(
            'Set Vent Angle (°)',
            options=servo_options,
            value=current_angle,
            help="Controls the flue gas vent opening."
        )
        
        if new_angle != current_angle:
            post_control('servo', {'angle': new_angle})
            
    # Manual Actuator Overrides (Conditional)
    st.markdown("### Manual Actuator Overrides")
    
    if data.get('mode') == 'MANUAL':
        act_col1, act_col2, act_col3, act_col4 = st.columns(4)
        
        fan_state_1 = "ON" if data.get('fan_on') else "OFF"
        if act_col1.button(f"🌬️ Fan 1 Toggle ({fan_state_1})"):
            post_control('fan1_toggle') # Assuming you add this new endpoint
            
        heater_state_1 = "ON" if data.get('dehumidifier_on') else "OFF"
        if act_col2.button(f"🔥 Heater 1 Toggle ({heater_state_1})"):
            post_control('heater1_toggle') # Assuming you add this new endpoint

        fan_state_2 = "ON" if data.get('fan_on_2') else "OFF"
        if act_col3.button(f"🌬️ Fan 2 Toggle ({fan_state_2})"):
            post_control('fan2_toggle') # Assuming you add this new endpoint

        heater_state_2 = "ON" if data.get('dehumidifier_on_2') else "OFF"
        if act_col4.button(f"🔥 Heater 2 Toggle ({heater_state_2})"):
            post_control('heater2_toggle') # Assuming you add this new endpoint
    else:
        st.warning("Manual actuator controls are only available when **Mode** is set to `MANUAL`.")
    
    st.markdown("---")
    
    # --- Auto-Refresh Logic ---
    st.caption(f"Last API call: {datetime.now().strftime('%H:%M:%S')} | Dashboard refreshes every {REFRESH_RATE_SECONDS} seconds.")
    
    # This sleep combined with st.experimental_rerun() forces the dashboard 
    # to refresh periodically, creating a real-time effect.
    time.sleep(REFRESH_RATE_SECONDS)
    st.experimental_rerun()


if __name__ == '__main__':
    display_dashboard()
