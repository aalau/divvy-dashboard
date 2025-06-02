import streamlit as st
st.set_page_config(layout="wide", page_title="Divvy Demand Map")
import pandas as pd
import pydeck as pdk
import snowflake.connector
import requests
import logging

# Configure logging
logger = logging.getLogger(__name__)

# Snowflake connection parameters - will be loaded from Streamlit secrets
def get_snowflake_connection():
    """Get Snowflake connection using Streamlit secrets"""
    try:
        conn = snowflake.connector.connect(
            account=st.secrets["snowflake"]["account"],
            user=st.secrets["snowflake"]["user"],
            password=st.secrets["snowflake"]["password"],
            database=st.secrets["snowflake"]["database"],
            schema=st.secrets["snowflake"]["schema"],
            warehouse=st.secrets["snowflake"]["warehouse"]
        )
        return conn
    except Exception as e:
        logger.error(f"Error connecting to Snowflake: {str(e)}")
        return None

st.title("🚲 Divvy Station Demand Map – Chicago")

def load_from_api():
    """Load station data directly from the GBFS API"""
    try:
        info_url = "https://gbfs.divvybikes.com/gbfs/en/station_information.json"
        status_url = "https://gbfs.divvybikes.com/gbfs/en/station_status.json"

        info = pd.DataFrame(requests.get(info_url).json()['data']['stations'])
        status = pd.DataFrame(requests.get(status_url).json()['data']['stations'])

        df = pd.merge(info, status, on='station_id')
        
        # Calculate demand metrics
        df['bike_utilization'] = df['num_bikes_available'] / df['capacity']
        df['dock_utilization'] = df['num_docks_available'] / df['capacity']
        df['out_of_service_bikes'] = df['capacity'] - (df['num_bikes_available'] + df['num_docks_available'])
        df['out_of_service_ratio'] = df['out_of_service_bikes'] / df['capacity']
        
        # Add last_reported timestamp
        df['last_reported'] = pd.Timestamp.now(tz='UTC')
        
        logger.info("Successfully loaded data from GBFS API")
        return df
    except Exception as e:
        logger.error(f"Error loading data from API: {str(e)}")
        return pd.DataFrame()

def load_from_snowflake():
    """Load station data from Snowflake gold table"""
    try:
        # Connect to Snowflake using secrets
        conn = get_snowflake_connection()
        if conn is None:
            return pd.DataFrame()
        
        # Query the gold table
        query = """
        SELECT 
            station_id,
            station_name as name,
            latitude as lat,
            longitude as lon,
            station_capacity as capacity,
            num_bikes_available,
            num_docks_available,
            out_of_service_bikes,
            bike_utilization,
            dock_utilization,
            out_of_service_ratio,
            last_reported_utc as last_reported
        FROM divvy_station_status_gold
        WHERE ds = CURRENT_DATE()::VARCHAR
        """
        
        # Execute query and load into DataFrame
        df = pd.read_sql(query, conn)
        conn.close()
        
        logger.info("Successfully loaded data from Snowflake gold table")
        return df
        
    except Exception as e:
        logger.error(f"Error loading data from Snowflake: {str(e)}")
        return pd.DataFrame()

@st.cache_data(ttl=300)  # Cache for 5 minutes
def load_station_data():
    """Load station data with fallback to API if Snowflake fails"""
    # Try loading from Snowflake first
    df = load_from_snowflake()
    
    # If Snowflake load fails or returns empty, try API
    if df.empty:
        logger.warning("Snowflake load failed, falling back to API")
        df = load_from_api()
        
        # If API also fails, show error
        if df.empty:
            st.error("Unable to load station data from both Snowflake and API. Please try again later.")
            st.stop()
        else:
            st.warning("⚠️ Using backup data from GBFS API (Snowflake data unavailable)")
    
    return df

# Rest of the visualization code remains the same
df = load_station_data()

if df.empty:
    st.error("Unable to load station data. Please try again later.")
    st.stop()

# Sidebar filters
st.sidebar.header("Filter Stations")
min_capacity = st.sidebar.slider("Minimum station capacity", 0, 60, 10)
filtered_df = df[df['capacity'] >= min_capacity]

st.markdown(f"Showing **{len(filtered_df)}** stations with capacity ≥ {min_capacity}")

# Function to calculate color based on station status
def get_station_color(row):
    # Calculate base utilization (black to white)
    total_bikes = row['num_bikes_available'] + row['out_of_service_bikes']
    if total_bikes == 0:
        # If no bikes at all, use light gray
        return [200, 200, 200, 200]
    
    # Base color is black to white based on bike utilization
    utilization = row['bike_utilization']  # Use pre-calculated utilization
    base_intensity = int(255 * utilization)
    
    # Calculate red component based on broken bike ratio
    broken_ratio = row['out_of_service_ratio']  # Use pre-calculated ratio
    red_intensity = int(255 * broken_ratio)
    
    # Blend the colors: base (black/white) with red
    return [
        min(255, base_intensity + red_intensity),  # Red channel
        base_intensity,  # Green channel (same as base)
        base_intensity,  # Blue channel (same as base)
        200  # Alpha channel
    ]

# Apply color function to create color column
filtered_df['color'] = filtered_df.apply(get_station_color, axis=1)

# Function to calculate radius based on capacity groups
def get_station_radius(capacity):
    # Define capacity ranges and their corresponding radii
    size_groups = [
        (0, 10, 3),       # 1-10 docks: 3px
        (10, 20, 8),      # 10-20 docks: 8px
        (20, 30, 15),     # 20-30 docks: 13px
        (30, 50, 20),     # 30-50 docks: 18px
        (50, 75, 30),     # 50-75 docks: 25px
        (75, 100, 40),    # 75-115 docks: 35px
        (100, float('inf'), 50)  # 115+ docks: 50px
    ]
    
    # Find the appropriate size group
    for min_cap, max_cap, radius in size_groups:
        if min_cap <= capacity < max_cap:
            return radius
    
    # Fallback to smallest size if somehow no group matches
    return 3

# Apply radius function to create radius column
filtered_df['radius'] = filtered_df['capacity'].apply(get_station_radius)

# Create the map layer
layer = pdk.Layer(
    "ScatterplotLayer",
    data=filtered_df,
    get_position='[lon, lat]',
    get_fill_color='color',
    get_radius='radius',
    radius_min_pixels=3,
    radius_max_pixels=8,
    pickable=True,
    auto_highlight=True
)

# Enhanced tooltip
tooltip = {
    "html": """
    <b style="font-size: 16px;">{name}</b><br/>
    <span>Capacity: {capacity}</span><br/>
    <span>Bikes Available: {num_bikes_available}</span><br/>
    <span>Docks Available: {num_docks_available}</span><br/>
    <span>Out of Service: {out_of_service_bikes}</span><br/>
    <span>Utilization: {bike_utilization:.0%}</span>
    """,
    "style": {
        "backgroundColor": "rgba(0, 0, 0, 0.8)",
        "color": "white",
        "borderRadius": "5px",
        "padding": "10px"
    }
}

# Map view state
view_state = pdk.ViewState(
    latitude=41.8781,
    longitude=-87.6298,
    zoom=12,
    pitch=0
)

# Create the map
st.pydeck_chart(pdk.Deck(
    layers=[layer],
    initial_view_state=view_state,
    tooltip=tooltip,
    map_style="light"
))

# Legend
st.markdown("""
### 🎨 Map Legend
- **Black to White Gradient**: Base color shows bike utilization (darker = more bikes available)
- **Red Tint**: Indicates broken/out-of-service bikes (more red = more broken bikes)
- **Dot Size**: Indicates station capacity in groups:
  - 3px: 1-10 docks
  - 8px: 10-20 docks
  - 13px: 20-30 docks
  - 18px: 30-50 docks
  - 25px: 50-75 docks
  - 35px: 75-100 docks
  - 50px: 100+ docks
- **Example**: A station with 10 bikes (out of 15 docks) would be:
  - Gray if all bikes are working
  - Gray with slight red tint if some bikes are broken
  - Dark red if all bikes are broken
""")

# Station statistics
col1, col2, col3 = st.columns(3)

with col1:
    empty_stations = filtered_df[filtered_df['num_bikes_available'] == 0]
    st.metric("Empty Stations", len(empty_stations))

with col2:
    full_stations = filtered_df[filtered_df['num_docks_available'] == 0]
    st.metric("Full Stations", len(full_stations))

with col3:
    out_of_service = filtered_df[filtered_df['out_of_service_bikes'] > 0]
    st.metric("Stations with Out-of-Service Bikes", len(out_of_service))

# Data freshness indicator
if not df.empty:
    last_updated = df['last_reported'].max()
    st.sidebar.markdown(f"**Last Updated**: {last_updated.strftime('%Y-%m-%d %H:%M:%S UTC')}")

# Optional: Show raw data
if st.checkbox("Show raw data table"):
    st.dataframe(filtered_df[[
        'name', 'capacity', 'num_bikes_available', 
        'num_docks_available', 'out_of_service_bikes', 
        'bike_utilization'
    ]])