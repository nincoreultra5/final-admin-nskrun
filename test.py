import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client

# ---------------------------
# Page + Theme (white + red/orange)
# ---------------------------
st.set_page_config(page_title="Inventory Analytics Dashboard", layout="wide")

st.markdown(
    """
    <style>
      /* App background */
      .stApp { background: #ffffff; }

      /* Remove gray blocks feel */
      [data-testid="stHeader"] { background: rgba(255,255,255,0.9); }
      [data-testid="stSidebar"] { background: #ffffff; border-right: 1px solid #f1f1f1; }

      /* Accent colors */
      :root{
        --brand-red: #ef4444;
        --brand-orange: #f97316;
        --soft-red: rgba(239, 68, 68, 0.10);
        --soft-orange: rgba(249, 115, 22, 0.10);
      }

      /* Titles */
      h1, h2, h3 { color: #111827; }
      .brand-badge{
        display:inline-block;
        padding:6px 10px;
        border-radius:999px;
        font-weight:800;
        font-size:12px;
        color:#991b1b;
        background: var(--soft-red);
        border: 1px solid rgba(239,68,68,0.25);
      }

      /* Sidebar buttons */
      div.stButton > button{
        border-radius: 12px;
        font-weight: 800;
        border: 1px solid rgba(249,115,22,0.35);
        background: linear-gradient(135deg, rgba(239,68,68,0.14), rgba(249,115,22,0.14));
      }
      div.stButton > button:hover{
        border-color: rgba(239,68,68,0.55);
      }

      /* Tabs */
      button[data-baseweb="tab"]{
        font-weight:800;
      }

      /* Metrics card-ish feel */
      [data-testid="stMetric"]{
        background: #fff;
        border: 1px solid #f1f1f1;
        padding: 14px 14px;
        border-radius: 16px;
      }

      /* Dataframes padding */
      [data-testid="stDataFrame"]{
        border: 1px solid #f1f1f1;
        border-radius: 14px;
        overflow: hidden;
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

def require_login():
    if "user" not in st.session_state or not st.session_state["user"]:
        st.warning("Please login.")
        st.stop()

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
# UI - Header
# ---------------------------
st.markdown('<span class="brand-badge">RED / ORANGE • Inventory Analytics</span>', unsafe_allow_html=True)
st.title("T‑Shirt Inventory Dashboard")

# ---------------------------
# Sidebar - Login + Filters
# ---------------------------
with st.sidebar:
    st.header("Login")

    if "user" not in st.session_state:
        st.session_state["user"] = None

    if st.session_state["user"]:
        u = st.session_state["user"]
        st.success(f"Logged in: {u['name']} ({u['organization']})")
        if st.button("Logout"):
            st.session_state["user"] = None
            st.rerun()
    else:
        username = st.text_input("Username", value="", key="login_username")
        password = st.text_input("Password", value="", type="password", key="login_password")
        if st.button("Login"):
            resp = (
                client.table("users")
                .select("id,username,name,organization")
                .eq("username", username.strip())
                .eq("password", password.strip())
                .maybe_single()
                .execute()
            )
            data = getattr(resp, "data", None)
            if not data:
                st.error("Invalid credentials")
            else:
                st.session_state["user"] = data
                st.rerun()

    st.divider()
    if st.button("Refresh data"):
        st.cache_data.clear()
        st.rerun()

require_login()

# Load data
stock_df = get_stock_df()
tx_df = get_transactions_df(limit=5000)

# Date filters
min_date = tx_df["date"].min() if not tx_df.empty else None
max_date = tx_df["date"].max() if not tx_df.empty else None

with st.sidebar:
    st.header("Filters")
    if min_date and max_date:
        start_date = st.date_input("Start date", value=min_date, min_value=min_date, max_value=max_date)
        end_date = st.date_input("End date", value=max_date, min_value=min_date, max_value=max_date)
    else:
        start_date, end_date = None, None
        st.info("No transactions yet, so date filter is disabled.")

tabs = st.tabs(["Overview (Analytics)", "Transactions (Table)"])


# ---------------------------
# Overview
# ---------------------------
with tabs[0]:
    st.subheader("KPIs (Remaining + Movements)")

    # Remaining quantities (current stock)
    kpis = current_stock_kpis(stock_df)
    a, b, c, d = st.columns(4)
    a.metric("Warehouse remaining", kpis.get("Warehouse", 0))
    b.metric("Bosch remaining", kpis.get("Bosch", 0))
    c.metric("TDK remaining", kpis.get("TDK", 0))
    d.metric("Mathma Nagar remaining", kpis.get("Mathma Nagar", 0))

    # Movement totals from transactions (requested)
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
    st.subheader("Tables (before graphs)")

    st.markdown("**Stock totals by organization**")
    st.dataframe(stock_totals(stock_df), use_container_width=True, hide_index=True)

    st.markdown("**IN/OUT totals by organization (transactions)**")
    st.dataframe(tx_summary, use_container_width=True, hide_index=True)

    # ---------------------------
    # GRAPHS (ALL at bottom as requested)
    # ---------------------------
    st.divider()
    st.subheader("Graphs")

    totals_df = stock_totals(stock_df).set_index("organization")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Current stock by organization (Grand Total)**")
        st.bar_chart(totals_df[["grand_total"]])  # built-in chart [web:261]

    with g2:
        st.markdown("**Current stock split (Kids vs Adults)**")
        st.bar_chart(totals_df[["kids_total", "adults_total"]])  # built-in chart [web:261]

    st.markdown("**Daily IN vs OUT trend**")
    daily = tx_daily_series(tx_df, start_date=start_date, end_date=end_date)
    if daily.empty:
        st.info("No transactions in selected date range.")
    else:
        st.line_chart(daily.set_index("date")[["in_qty", "out_qty"]])  # chart element [web:260]

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
            st.bar_chart(top_reasons)  # built-in chart [web:261]


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
