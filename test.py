import streamlit as st
import pandas as pd
from datetime import datetime
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

      /* Some Streamlit versions wrap inputs inside extra divs */
      .stTextInput div[data-baseweb="input"] > div,
      .stNumberInput div[data-baseweb="input"] > div,
      .stDateInput div[data-baseweb="input"] > div {
        background: var(--white) !important;
      }

      /* Selectbox */
      .stSelectbox [data-baseweb="select"] > div{
        background: var(--white) !important;
        color: var(--black) !important;
        border: 1px solid var(--border) !important;
        border-radius: 12px !important;
      }

      /* Select dropdown menu */
      ul[role="listbox"]{
        background: var(--white) !important;
        color: var(--black) !important;
        border: 1px solid var(--border) !important;
      }
      li[role="option"]{
        background: var(--white) !important;
        color: var(--black) !important;
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

      /* ---------------------------
         TABLES / DATAFRAMES: force WHITE
         --------------------------- */
      [data-testid="stDataFrame"]{
        background: var(--white) !important;
        border: 1px solid var(--border) !important;
        border-radius: 14px !important;
        overflow: hidden !important;
      }

      /* Some dataframe internal containers */
      [data-testid="stDataFrame"] *{
        color: var(--black) !important;
      }

      /* Expander */
      [data-testid="stExpander"]{
        border: 1px solid var(--border) !important;
        border-radius: 14px !important;
        background: var(--white) !important;
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
# Config (Streamlit Secrets)
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
        df["date"] = df["created_at"].dt.date
    return df

def stock_totals(stock_df: pd.DataFrame) -> pd.DataFrame:
    if stock_df.empty:
        return pd.DataFrame(columns=["organization", "kids_total", "adults_total", "grand_total"])
    pivot = (
        stock_df.groupby(["organization", "category"], as_index=False)["quantity"]
        .sum()
        .pivot(index="organization", columns="category", values="quantity")
        .fillna(0)
        .reset_index()
    )
    if "kids" not in pivot.columns:
        pivot["kids"] = 0
    if "adults" not in pivot.columns:
        pivot["adults"] = 0
    pivot["grand_total"] = pivot["kids"] + pivot["adults"]
    pivot = pivot.rename(columns={"kids": "kids_total", "adults": "adults_total"})
    return pivot[["organization", "kids_total", "adults_total", "grand_total"]]

def current_stock_kpis(stock_df: pd.DataFrame) -> dict:
    totals = stock_totals(stock_df)
    out = {}
    for org in ORGS:
        row = totals[totals["organization"] == org]
        out[org] = int(row["grand_total"].iloc[0]) if not row.empty else 0
    return out

def tx_kpis(tx_df: pd.DataFrame, start_date=None, end_date=None) -> pd.DataFrame:
    if tx_df.empty:
        return pd.DataFrame(columns=["organization", "in_qty", "out_qty", "net_in_minus_out"])
    df = tx_df.copy()
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    grp = df.groupby(["organization", "type"], as_index=False)["quantity"].sum()
    pivot = grp.pivot(index="organization", columns="type", values="quantity").fillna(0).reset_index()
    if "in" not in pivot.columns:
        pivot["in"] = 0
    if "out" not in pivot.columns:
        pivot["out"] = 0
    pivot["net_in_minus_out"] = pivot["in"] - pivot["out"]
    pivot = pivot.rename(columns={"in": "in_qty", "out": "out_qty"})
    return pivot.sort_values("organization")

def tx_daily_series(tx_df: pd.DataFrame, start_date=None, end_date=None) -> pd.DataFrame:
    if tx_df.empty:
        return pd.DataFrame(columns=["date", "in_qty", "out_qty"])
    df = tx_df.copy()
    if start_date:
        df = df[df["date"] >= start_date]
    if end_date:
        df = df[df["date"] <= end_date]
    daily = df.groupby(["date", "type"], as_index=False)["quantity"].sum()
    pivot = daily.pivot(index="date", columns="type", values="quantity").fillna(0).reset_index()
    if "in" not in pivot.columns:
        pivot["in"] = 0
    if "out" not in pivot.columns:
        pivot["out"] = 0
    pivot = pivot.rename(columns={"in": "in_qty", "out": "out_qty"})
    pivot["date"] = pd.to_datetime(pivot["date"])
    return pivot.sort_values("date")

# ---------------------------
# Header
# ---------------------------
st.markdown('<span class="brand-badge">Inventory Analytics</span>', unsafe_allow_html=True)
st.title("T‑Shirt Inventory Dashboard")

# Load data
stock_df = get_stock_df()
tx_df = get_transactions_df(limit=5000)

# Date filter
min_date = tx_df["date"].min() if not tx_df.empty else None
max_date = tx_df["date"].max() if not tx_df.empty else None

# ---------------------------
# Sidebar - Filters only
# ---------------------------
with st.sidebar:
    st.header("Filters")
    if min_date and max_date:
        start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
        end_date = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date)
    else:
        start_date, end_date = None, None
        st.info("No transactions yet, so date filter is disabled.")
    
    st.divider()
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

tabs = st.tabs(["Overview (Analytics)", "Transactions (Table)"])

# ---------------------------
# Overview
# ---------------------------
with tabs[0]:
    st.subheader("KPIs (Remaining + Movements)")

    kpis = current_stock_kpis(stock_df)
    a, b, c, d = st.columns(4)
    a.metric("Warehouse remaining", kpis.get("Warehouse", 0))
    b.metric("Bosch remaining", kpis.get("Bosch", 0))
    c.metric("TDK remaining", kpis.get("TDK", 0))
    d.metric("Mathma Nagar remaining", kpis.get("Mathma Nagar", 0))

    tx_summary = tx_kpis(tx_df, start_date=start_date, end_date=end_date)

    wh_row = tx_summary[tx_summary["organization"] == "Warehouse"]
    wh_in = int(wh_row["in_qty"].iloc[0]) if not wh_row.empty else 0

    b_row = tx_summary[tx_summary["organization"] == "Bosch"]
    t_row = tx_summary[tx_summary["organization"] == "TDK"]
    m_row = tx_summary[tx_summary["organization"] == "Mathma Nagar"]

    bosch_out = int(b_row["out_qty"].iloc[0]) if not b_row.empty else 0
    tdk_out = int(t_row["out_qty"].iloc[0]) if not t_row.empty else 0
    mathma_out = int(m_row["out_qty"].iloc[0]) if not m_row.empty else 0

    st.divider()
    st.subheader("Period totals (from transactions)")
    r1, r2, r3, r4 = st.columns(4)
    r1.metric("Warehouse total IN", wh_in)
    r2.metric("Bosch total OUT", bosch_out)
    r3.metric("TDK total OUT", tdk_out)
    r4.metric("Mathma Nagar total OUT", mathma_out)

    st.divider()
    st.subheader("Tables")

    st.markdown("**Stock totals by organization**")
    st.dataframe(stock_totals(stock_df), use_container_width=True, hide_index=True)

    st.markdown("**IN/OUT totals by organization (transactions)**")
    st.dataframe(tx_summary, use_container_width=True, hide_index=True)

    st.divider()
    st.subheader("Graphs")

    totals_df = stock_totals(stock_df).set_index("organization")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Current stock by organization (Grand Total)**")
        st.bar_chart(totals_df[["grand_total"]])

    with g2:
        st.markdown("**Current stock split (Kids vs Adults)**")
        st.bar_chart(totals_df[["kids_total", "adults_total"]])

    st.markdown("**Daily IN vs OUT trend**")
    daily = tx_daily_series(tx_df, start_date=start_date, end_date=end_date)
    if daily.empty:
        st.info("No transactions in selected date range.")
    else:
        st.line_chart(daily.set_index("date")[["in_qty", "out_qty"]])

    st.markdown("**Top dispatch reasons (OUT)**")
    if tx_df.empty:
        st.info("No transactions.")
    else:
        df_f = tx_df.copy()
        if start_date:
            df_f = df_f[df_f["date"] >= start_date]
        if end_date:
            df_f = df_f[df_f["date"] <= end_date]

        out_df = df_f[df_f["type"] == "out"].copy()
        if out_df.empty:
            st.info("No OUT transactions in selected range.")
        else:
            top_reasons = (
                out_df.assign(reason=out_df["reason"].fillna("No reason"))
                .groupby("reason", as_index=False)["quantity"]
                .sum()
                .sort_values("quantity", ascending=False)
                .head(12)
                .set_index("reason")
            )
            st.bar_chart(top_reasons)

# ---------------------------
# Transactions tab
# ---------------------------
with tabs[1]:
    st.subheader("Transactions table")

    if tx_df.empty:
        st.write("No transactions.")
    else:
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            org_f = st.selectbox("Org", ["all"] + ORGS, index=0)
        with c2:
            typ_f = st.selectbox("Type", ["all", "in", "out"], index=0)
        with c3:
            cat_f = st.selectbox("Category", ["all"] + CATEGORIES, index=0)
        with c4:
            size_f = st.text_input("Size", value="")

        df = tx_df.copy()
        if start_date:
            df = df[df["date"] >= start_date]
        if end_date:
            df = df[df["date"] <= end_date]
        if org_f != "all":
            df = df[df["organization"] == org_f]
        if typ_f != "all":
            df = df[df["type"] == typ_f]
        if cat_f != "all":
            df = df[df["category"] == cat_f]
        if size_f.strip():
            df = df[df["size"] == size_f.strip()]

        df = df.sort_values("created_at", ascending=False).copy()
        df["created_at"] = df["created_at"].dt.strftime("%Y-%m-%d %H:%M")
        st.dataframe(
            df[["id", "created_at", "organization", "type", "category", "size", "quantity", "reason", "user_name"]],
            use_container_width=True,
            hide_index=True,
        )
