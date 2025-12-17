import streamlit as st
from supabase import create_client, Client
import pandas as pd

# -----------------------------------------------------------------------------
# 1. SETUP & CONNECTION
# -----------------------------------------------------------------------------
# Replace these with your actual Supabase credentials
SUPABASE_URL = "https://your-project-url.supabase.co"
SUPABASE_KEY = "your-anon-public-key"

@st.cache_resource
def init_connection():
    try:
        return create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        st.error(f"Failed to connect to Supabase: {e}")
        return None

supabase = init_connection()

# -----------------------------------------------------------------------------
# 2. DATA FETCHING FUNCTIONS
# -----------------------------------------------------------------------------
def get_dashboard_metrics():
    """
    Calculates the 3 key metrics for the top boxes:
    1. Total Purchased (Warehouse Inflow)
    2. Total Consumed (Distributed to Orgs)
    3. Total Remaining (Current Warehouse Stock)
    """
    if not supabase: return 0, 0, 0
    
    # BOX 1: Total Purchased (Transactions IN to Warehouse)
    # logic: Sum quantity from transactions where org='Warehouse' AND type='in'
    res_purchased = supabase.table('transactions')\
        .select('quantity')\
        .eq('organization', 'Warehouse')\
        .eq('type', 'in')\
        .execute()
    
    total_purchased = sum(item['quantity'] for item in res_purchased.data)

    # BOX 2: Total Consumed (Distributed to Locations)
    # logic: Sum quantity from transactions where org is NOT Warehouse AND type='in'
    # (This assumes stock moving TO Bosch/TDK counts as "consumed" from the warehouse perspective)
    res_consumed = supabase.table('transactions')\
        .select('quantity')\
        .neq('organization', 'Warehouse')\
        .eq('type', 'in')\
        .execute()
        
    total_consumed = sum(item['quantity'] for item in res_consumed.data)

    # BOX 3: Total Remaining (Current Warehouse Stock)
    # logic: Sum actual 'quantity' column in 'stock' table for Warehouse
    res_remaining = supabase.table('stock')\
        .select('quantity')\
        .eq('organization', 'Warehouse')\
        .execute()
        
    total_remaining = sum(item['quantity'] for item in res_remaining.data)
    
    return total_purchased, total_consumed, total_remaining

def get_detailed_stock():
    """Fetches stock broken down by Size for the table view"""
    if not supabase: return pd.DataFrame()
    
    response = supabase.table('stock').select('*').order('size').execute()
    return pd.DataFrame(response.data)

# -----------------------------------------------------------------------------
# 3. DASHBOARD UI
# -----------------------------------------------------------------------------
st.title("NR T-Shirt Distribution Analysis")

# Fetch live data
purchased, consumed, remaining = get_dashboard_metrics()

# --- TOP LAYER: 3 BOXES ---
st.markdown("### Overview")
col1, col2, col3 = st.columns(3)

with col1:
    st.container(border=True)
    st.metric(label="T-Shirts Purchased", value=purchased, delta="Supplier → Warehouse")
    st.caption("Total Inflow")

with col2:
    st.container(border=True)
    st.metric(label="T-Shirts Consumed", value=consumed, delta="Distributed Out", delta_color="inverse")
    st.caption("Bosch + TDK + MN")

with col3:
    st.container(border=True)
    # Validate math: Purchased - Consumed should roughly equal Remaining
    st.metric(label="T-Shirts Remaining", value=remaining)
    st.caption("Available in Warehouse")

# --- MIDDLE LAYER: STOCK TABLE ---
st.markdown("---")
st.subheader("Live Inventory by Size & Location")

df_stock = get_detailed_stock()

if not df_stock.empty:
    # Pivot table to match your diagram (Sizes as columns, Org as rows)
    # Filter for relevant columns
    pivot_df = df_stock.pivot_table(
        index='organization', 
        columns='size', 
        values='quantity', 
        aggfunc='sum',
        fill_value=0
    )
    
    # Reorder columns to sort sizes correctly (numeric sort)
    try:
        sorted_cols = sorted(pivot_df.columns, key=lambda x: int(x))
        pivot_df = pivot_df[sorted_cols]
    except:
        pass # fallback if sizes aren't purely numeric
        
    st.dataframe(pivot_df, use_container_width=True)
else:
    st.info("No stock data available.")

# --- BOTTOM LAYER: ACTION BUTTONS ---
st.markdown("### Actions")
b_col1, b_col2, b_col3, b_col4 = st.columns(4)
b_col1.button("Warehouse")
b_col2.button("Bosch")
b_col3.button("TDK")
b_col4.button("Mathma Nagar")
