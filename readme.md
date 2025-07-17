# Divvy Station Demand Map

A real-time visualization of Divvy bike station status across Chicago, showing station capacity, bike availability, and out-of-service bikes.

## Features

- Interactive map showing all Divvy stations in Chicago
- Color-coded stations based on bike utilization and out-of-service bikes
- Station size indicates capacity
- Real-time data with 5-minute caching
- Fallback to GBFS API if database is unavailable
- Station statistics and filtering options

## Deployment Instructions

### Local Development

1. Clone this repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Create a `.streamlit/secrets.toml` file with your Snowflake credentials:
   ```toml
   [snowflake]
   account = "your-account"
   user = "your-username"
   password = "your-password"
   database = "BOOTCAMP"
   schema = "your-schema"
   warehouse = "BOOTCAMP_WH"
   ```
4. Run the app:
   ```bash
   streamlit run divvy_demand_map_public.py
   ```

### Streamlit Cloud Deployment

1. Fork this repository
2. Go to [Streamlit Cloud](https://streamlit.io/cloud)
3. Create a new app and connect it to your forked repository
4. Add your Snowflake credentials in the Streamlit Cloud secrets management:
   - Go to your app settings
   - Click on "Secrets"
   - Add the same secrets as shown in the local development section
5. Deploy the app

## Data Sources

- Primary: Snowflake database (gold table)
- Fallback: Divvy GBFS API (real-time data)

## Note

This app will work without Snowflake credentials by falling back to the GBFS API, but for the best experience (including historical data and analytics), Snowflake credentials are recommended.
