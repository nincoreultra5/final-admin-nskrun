import streamlit as st
import pandas as pd
from supabase import create_client

# ---------------------------
# Page config
# ---------------------------
st.set_page_config(page_title="Inventory Analytics Dashboard", layout="wide")

# ---------------------------
# HARD UI THEME: White + Black + Red ONLY
# ---------------------------
st.markdown(
    """
    <style>
      :root{
        --red:#ef4444;
        --black:#111827;
        --white:#ffffff;
        --border:#e5e7eb;
        --muted:#6b7280;
        --soft-red: rgba(239,68,68,0.08);
      }

      /* Main background */
      html, body, [data-testid="stAppViewContainer"], .stApp {
        background: var(--white) !important;
        color: var(--black) !important;
      }

      /* Sidebar background */
      [data-testid="stSidebar"]{
        background: var(--white) !important;
        border-right: 1px solid var(--border) !important;
      }
      [data-testid="stSidebar"] *{
        color: var(--black) !important;
      }

      /* Header background */
      [data-testid="stHeader"]{
        background: var(--white) !important;
      }

      /* Force all text black */
      h1,h2,h3,h4,h5,h6,p,span,div,label,small,li,strong,em,code {
        color: var(--black) !important;
      }

      /* Links red */
      a, a:visited { color: var(--red) !important; }

      /* Tabs */
      button[data-baseweb="tab"]{
        color: var(--black) !important;
        font-weight: 800 !important;
      }
      button[data-baseweb="tab"][aria-selected="true"]{
        border-bottom: 2px solid var(--red) !important;
      }

      /* Metric cards */
      [data-testid="stMetric"]{
        background: var(--white) !important;
        border: 1px solid var(--border) !important;
        border-radius: 16px !important;
        padding: 14px 14px !important;
      }

      /* ---------------------------
         INPUTS: force WHITE
         --------------------------- */

      /* Text + password + number + date inputs */
      .stTextInput input,
      .stNumberInput input,
      .stDateInput input,
      .stTextArea textarea {
        background: var(--white) !important;
        color: var(--black) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
      }

      /* Selectbox */
      .stSelectbox [data-baseweb="select"] > div{
        background: var(--white) !important;
        color: var(--black) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
      }

      /* Buttons: white with red border */
      div.stButton > button{
        background: var(--white) !important;
        color: var(--black) !important;
        border: 1px solid rgba(239,68,68,0.55) !important;
        border-radius: 12px !important;
        font-weight: 900 !important;
      }
      div.stButton > button:hover{
        background: #f9fafb !important;
        border-color: var(--red) !important;
      }

      /* Tables / DataFrames */
      [data-testid="stDataFrame"]{
        background: var(--white) !important;
        border: 1px solid var(--border) !important;
        border-radius: 14px !important;
        overflow: hidden !important;
      }
      [data-testid="stDataFrame"] *{
        color: var(--black) !important;
      }

      /* Badge */
      .brand-badge{
        display:inline-block;
        padding:6px 10px;
        border-radius:999px;
        font-weight:900;
        font-size:12px;
        color:#b91c1c !important;
        background: var(--soft-red) !important;
        border: 1px solid rgba(239,68,68,0.25) !important;
      }
    </style>
    """,
    unsafe_allow_html=True,
)

# ---------------------------
# Config
# ---------------------------
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_ANON_KEY = st.secrets["SUPABASE_ANON_KEY"]
except KeyError:
    st.error("Missing secrets. Add SUPABASE_URL and SUPABASE_ANON_KEY in Streamlit Cloud → Settings → Secrets.")
    st.stop()

ORGS = ["Warehouse", "Bosch", "TDK", "Mathma Nagar"]
CATEGORIES = ["kids", "adults"]

# ---------------------------
# Supabase client
# ---------------------------
@st.cache_resource
def get_client():
    return create_client(SUPABASE_URL, SUPABASE_ANON_KEY)

client = get_client()

# ---------------------------
# Helpers
# ---------------------------
def sb_to_df(resp) -> pd.DataFrame:
    data = getattr(resp, "data", None) or []
    return pd.DataFrame(data)

@st.cache_data(ttl=20)
def get_stock_df():
    resp = client.table("stock").select("organization,category,size,quantity,updated_at").execute()
    df = sb_to_df(resp)
    if not df.empty:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
    return df

@st.cache_data(ttl=20)
def get_transactions_df(limit=5000):
    resp = (
        client.table("transactions")
        .select("id,organization,category,size,quantity,type,reason,user_name,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    df = sb_to_df(resp)
    if not df.empty:
        df["quantity"] = pd.to_numeric(df["quantity"], errors="coerce").fillna(0).astype(int)
        df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce", utc=True)
    return df

def stock_totals_by_org_size(stock_df: pd.DataFrame) -> pd.DataFrame:
    """Stock totals per organization and size - ONLY available combinations"""
    if stock_df.empty:
        return pd.DataFrame()
    
    # Get unique organizations and sizes that actually have data
    available_orgs = stock_df["organization"].unique()
    available_sizes = stock_df["size"].dropna().unique()
    
    # Filter to only available data
    filtered_df = stock_df[stock_df["organization"].isin(available_orgs) & 
                          stock_df["size"].isin(available_sizes)]
    
    totals = filtered_df.groupby(["organization", "size"], as_index=False)["quantity"].sum()
    if totals.empty:
        return pd.DataFrame()
    
    pivot = totals.pivot(index="organization", columns="size", values="quantity").fillna(0)
    return pivot

def current_stock_kpis(stock_df: pd.DataFrame) -> dict:
    """Current stock per organization"""
    if stock_df.empty:
        return {org: 0 for org in ORGS}
    totals = stock_df.groupby("organization")["quantity"].sum().to_dict()
    return {org: int(totals.get(org, 0)) for org in ORGS}

def get_total_in_out(tx_df: pd.DataFrame) -> dict:
    """Total IN and OUT across all organizations"""
    if tx_df.empty:
        return {"total_in": 0, "total_out": 0}
    
    in_total = tx_df[tx_df["type"] == "in"]["quantity"].sum()
    out_total = tx_df[tx_df["type"] == "out"]["quantity"].sum()
    return {"total_in": int(in_total), "total_out": int(out_total)}

def get_out_by_org(tx_df: pd.DataFrame) -> dict:
    """OUT totals for Bosch, TDK, Warehouse"""
    if tx_df.empty:
        return {"Bosch": 0, "TDK": 0, "Warehouse": 0}
    
    out_df = tx_df[tx_df["type"] == "out"]
    results = {}
    for org in ["Bosch", "TDK", "Warehouse"]:
        org_out = out_df[out_df["organization"] == org]["quantity"].sum()
        results[org] = int(org_out)
    return results

def stock_pie_data(stock_df: pd.DataFrame) -> pd.DataFrame:
    """Data for pie chart display"""
    if stock_df.empty:
        return pd.DataFrame({"organization": ORGS, "quantity": 0})
    
    totals = stock_df.groupby("organization")["quantity"].sum().reset_index()
    all_orgs = pd.DataFrame({"organization": ORGS})
    return all_orgs.merge(totals, on="organization", how="left").fillna({"quantity": 0})

# ---------------------------
# Header
# ---------------------------
st.markdown('<span class="brand-badge">Inventory Analytics</span>', unsafe_allow_html=True)
st.title("T‑Shirt Inventory Dashboard")

# Load data
stock_df = get_stock_df()
tx_df = get_transactions_df(limit=5000)

# Calculate metrics
kpis = current_stock_kpis(stock_df)
total_metrics = get_total_in_out(tx_df)
out_by_org = get_out_by_org(tx_df)
pie_data = stock_pie_data(stock_df)

# ---------------------------
# Sidebar - Simple refresh only
# ---------------------------
with st.sidebar:
    st.header("Controls")
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

tabs = st.tabs(["Overview (Analytics)", "Transactions (Table)"])

# ---------------------------
# Overview Tab
# ---------------------------
with tabs[0]:
    # Total Metrics Row 1
    st.subheader("🏆 TOTAL INVENTORY METRICS (ALL TIME)")
    
    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Warehouse Stock", kpis["Warehouse"])
    col2.metric("Bosch Stock", kpis["Bosch"])
    col3.metric("TDK Stock", kpis["TDK"])
    col4.metric("Mathma Nagar Stock", kpis["Mathma Nagar"])
    
    # Total IN/OUT + OUT by endpoints
    col5, col6, col7, col8 = st.columns(4)
    col5.metric("💰 TOTAL IN", total_metrics["total_in"])
    col6.metric("📤 TOTAL OUT", total_metrics["total_out"])
    col7.metric("🔴 Bosch OUT", out_by_org["Bosch"])
    col8.metric("🔵 TDK OUT", out_by_org["TDK"])

    st.divider()
    
    # Per Company Stock by Size Table - ONLY AVAILABLE DATA
    st.subheader("📊 Stock by Company & Available Sizes")
    stock_size_table = stock_totals_by_org_size(stock_df)
    if not stock_size_table.empty:
        st.dataframe(stock_size_table, use_container_width=True, hide_index=True)
    else:
        st.info("No stock data available.")
    
    st.divider()
    
    # Simple Distribution Chart
    st.subheader("📈 Stock Distribution by Organization")
    if not pie_data.empty and pie_data["quantity"].sum() > 0:
        st.bar_chart(pie_data.set_index("organization")["quantity"], height=400)
        # Display percentages
        total_stock = pie_data["quantity"].sum()
        for idx, row in pie_data.iterrows():
            if row["quantity"] > 0:
                pct = (row["quantity"] / total_stock * 100)
                st.metric(f"{row['organization']}", f"{int(row['quantity'])}", f"{pct:.1f}%")
    else:
        st.info("No stock data available for distribution chart.")

# ---------------------------
# Transactions Tab
# ---------------------------
with tabs[1]:
    st.subheader("Transactions Table (All Time)")

    if tx_df.empty:
        st.write("No transactions.")
    else:
        c1, c2, c3 = st.columns(3)
        with c1:
            org_f = st.selectbox("Org", ["all"] + ORGS, index=0)
        with c2:
            typ_f = st.selectbox("Type", ["all", "in", "out"], index=0)
        with c3:
            cat_f = st.selectbox("Category", ["all"] + CATEGORIES, index=0)

        df = tx_df.copy()
        if org_f != "all":
            df = df[df["organization"] == org_f]
        if typ_f != "all":
            df = df[df["type"] == typ_f]
        if cat_f != "all":
            df = df[df["category"] == cat_f]

        df = df.sort_values("created_at", ascending=False).copy()
        df["created_at"] = df["created_at"].dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(
            df[["id", "created_at", "organization", "type", "category", "size", "quantity", "reason", "user_name"]],
            use_container_width=True,
            hide_index=True,
        )
