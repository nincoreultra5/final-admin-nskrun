import streamlit as st
import pandas as pd
from datetime import datetime
from supabase import create_client

# ---------------------------
# Config - Read from Streamlit secrets
# ---------------------------
try:
    SUPABASE_URL = st.secrets["https://eqvhzxljdcoeigbyqrlg.supabase.co"]
    SUPABASE_ANON_KEY = st.secrets["eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImVxdmh6eGxqZGNvZWlnYnlxcmxnIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjU4MDg1OTcsImV4cCI6MjA4MTM4NDU5N30.q71CAFw3UsjiNwW8oM66HiHbWxGQZQzKRcISoPOO8QE"]
except KeyError:
    st.error("❌ Missing secrets! Add SUPABASE_URL and SUPABASE_ANON_KEY in Streamlit Cloud secrets.")
    st.stop()

ORGS = ["Warehouse", "Bosch", "TDK", "Mathma Nagar"]
CATEGORIES = ["kids", "adults"]
KIDS_SIZES = ["26", "28", "30", "32", "34"]
ADULT_SIZES = ["36", "38", "40", "42", "44", "46"]

st.set_page_config(page_title="T‑Shirt Inventory Dashboard", layout="wide")


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


def fmt_ts(ts):
    if not ts:
        return ""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return str(ts)


def require_login():
    if "user" not in st.session_state or not st.session_state["user"]:
        st.warning("Please login.")
        st.stop()


def get_stock_df():
    resp = client.table("stock").select("organization,category,size,quantity,updated_at").execute()
    return sb_to_df(resp)


def get_transactions_df(limit=500):
    resp = (
        client.table("transactions")
        .select("id,organization,category,size,quantity,type,reason,user_name,created_at")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
    )
    return sb_to_df(resp)


def get_pending_transfers_for_org(org: str):
    t = (
        client.table("stock_transfers")
        .select("id,from_org,to_org,status,reason,created_by_name,created_by_username,created_at")
        .eq("to_org", org)
        .eq("status", "pending")
        .order("created_at")
        .execute()
    )
    tdf = sb_to_df(t)
    if tdf.empty:
        return tdf, pd.DataFrame()

    ids = tdf["id"].tolist()
    items = (
        client.table("stock_transfer_items")
        .select("transfer_id,category,size,quantity")
        .in_("transfer_id", ids)
        .order("category")
        .order("size")
        .execute()
    )
    idf = sb_to_df(items)
    return tdf, idf


def get_pending_transfers_created_by_warehouse():
    t = (
        client.table("stock_transfers")
        .select("id,from_org,to_org,status,reason,created_by_name,created_by_username,created_at,decided_at,decided_by_name,reject_note")
        .eq("from_org", "Warehouse")
        .order("created_at", desc=True)
        .limit(200)
        .execute()
    )
    tdf = sb_to_df(t)
    items = (
        client.table("stock_transfer_items")
        .select("transfer_id,category,size,quantity")
        .order("transfer_id", desc=True)
        .execute()
    )
    idf = sb_to_df(items)
    return tdf, idf


def make_transfer_items_from_inputs(kids_map, adults_map):
    items = []
    for size, qty in kids_map.items():
        if qty and qty > 0:
            items.append({"category": "kids", "size": str(size), "quantity": int(qty)})
    for size, qty in adults_map.items():
        if qty and qty > 0:
            items.append({"category": "adults", "size": str(size), "quantity": int(qty)})
    return items


def stock_totals_by_org(stock_df: pd.DataFrame) -> pd.DataFrame:
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


# ---------------------------
# Auth UI
# ---------------------------
st.title("Inventory Dashboard (Warehouse + Bosch + TDK + Mathma Nagar)")

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
    st.caption("Note: anon + RLS open is not secure for production.")


# ---------------------------
# Tabs
# ---------------------------
tabs = st.tabs(["Overview", "Warehouse: Create Queue", "Org: Confirm Queue", "Transactions"])

# ---------------------------
# Overview
# ---------------------------
with tabs[0]:
    require_login()

    colA, colB = st.columns([1, 1])
    with colA:
        st.subheader("Stock totals by organization")
    with colB:
        if st.button("Refresh data"):
            st.cache_data.clear()
            st.rerun()

    stock_df = get_stock_df()
    totals_df = stock_totals_by_org(stock_df)
    st.dataframe(totals_df, use_container_width=True, hide_index=True)

    st.subheader("Per-size stock (filtered)")
    c1, c2, c3 = st.columns(3)
    with c1:
        org_filter = st.selectbox("Organization", ORGS, index=ORGS.index(st.session_state["user"]["organization"]))
    with c2:
        cat_filter = st.selectbox("Category", ["all"] + CATEGORIES, index=0)
    with c3:
        size_filter = st.text_input("Size (optional)", value="")

    df = stock_df.copy()
    df = df[df["organization"] == org_filter]
    if cat_filter != "all":
        df = df[df["category"] == cat_filter]
    if size_filter.strip():
        df = df[df["size"] == size_filter.strip()]
    df = df.sort_values(["category", "size"])
    st.dataframe(df[["organization", "category", "size", "quantity", "updated_at"]], use_container_width=True, hide_index=True)


# ---------------------------
# Warehouse: create transfer queue
# ---------------------------
with tabs[1]:
    require_login()
    user = st.session_state["user"]

    if user["organization"] != "Warehouse":
        st.info("Only Warehouse can create queue transfer requests.")
        st.stop()

    st.subheader("Create pending transfer (Warehouse → Organization)")

    to_org = st.selectbox("To organization", ["Bosch", "TDK", "Mathma Nagar"])
    reason = st.text_input("Reason (optional)", value="")

    st.markdown("### Select quantities")
    kids_cols = st.columns(len(KIDS_SIZES))
    kids_map = {}
    for i, size in enumerate(KIDS_SIZES):
        with kids_cols[i]:
            kids_map[size] = st.number_input(f"Kids {size}", min_value=0, step=1, value=0, key=f"k_{size}")

    adult_cols = st.columns(len(ADULT_SIZES))
    adults_map = {}
    for i, size in enumerate(ADULT_SIZES):
        with adult_cols[i]:
            adults_map[size] = st.number_input(f"Adults {size}", min_value=0, step=1, value=0, key=f"a_{size}")

    items = make_transfer_items_from_inputs(kids_map, adults_map)
    total_qty = sum(x["quantity"] for x in items)

    st.write(f"Total qty: {total_qty}")

    col1, col2 = st.columns([1, 2])
    with col1:
        if st.button("Create transfer request", disabled=(total_qty == 0)):
            try:
                resp = (
                    client.rpc(
                        "create_stock_transfer",
                        {
                            "p_from_org": "Warehouse",
                            "p_to_org": to_org,
                            "p_items": items,
                            "p_reason": reason or None,
                            "p_created_by_name": user["name"],
                            "p_created_by_username": user["username"],
                        },
                    ).execute()
                )
                st.success(f"Created transfer request. Response: {resp.data}")
            except Exception as e:
                st.error(f"Failed: {e}")

    st.divider()
    st.subheader("Recent transfer requests (Warehouse)")
    tdf, idf = get_pending_transfers_created_by_warehouse()
    if tdf.empty:
        st.write("No transfers found.")
    else:
        if not idf.empty:
            grouped = idf.groupby("transfer_id").apply(
                lambda x: ", ".join([f"{r['category']}-{r['size']}:{r['quantity']}" for _, r in x.iterrows()])
            ).reset_index(name="items")
            out = tdf.merge(grouped, left_on="id", right_on="transfer_id", how="left").drop(columns=["transfer_id"])
        else:
            out = tdf.copy()
            out["items"] = ""

        out["created_at"] = out["created_at"].apply(fmt_ts)
        out["decided_at"] = out["decided_at"].apply(fmt_ts)
        st.dataframe(
            out[["id", "to_org", "status", "reason", "items", "created_by_name", "created_at", "decided_by_name", "decided_at", "reject_note"]],
            use_container_width=True,
            hide_index=True,
        )


# ---------------------------
# Org: confirm queue
# ---------------------------
with tabs[2]:
    require_login()
    user = st.session_state["user"]
    org = user["organization"]

    if org == "Warehouse":
        st.info("Warehouse does not accept queue requests here. Use the Warehouse tab to create them.")
        st.stop()

    st.subheader(f"Pending requests for {org}")

    tdf, idf = get_pending_transfers_for_org(org)

    if tdf.empty:
        st.write("No pending requests.")
    else:
        for _, tr in tdf.sort_values("created_at").iterrows():
            transfer_id = int(tr["id"])
            tr_items = idf[idf["transfer_id"] == transfer_id] if not idf.empty else pd.DataFrame()
            total = int(tr_items["quantity"].sum()) if not tr_items.empty else 0

            with st.expander(f"Request #{transfer_id} from {tr['from_org']} • Total {total}", expanded=False):
                st.write(f"Created by: {tr.get('created_by_name') or 'Warehouse'} ({tr.get('created_by_username') or ''})")
                st.write(f"Reason: {tr.get('reason') or ''}")
                st.write(f"Created at: {fmt_ts(tr.get('created_at'))}")

                if not tr_items.empty:
                    st.dataframe(tr_items[["category", "size", "quantity"]], use_container_width=True, hide_index=True)

                c1, c2 = st.columns(2)
                with c1:
                    if st.button(f"Accept #{transfer_id}", key=f"acc_{transfer_id}"):
                        try:
                            resp = (
                                client.rpc(
                                    "accept_stock_transfer",
                                    {
                                        "p_transfer_id": transfer_id,
                                        "p_decided_by_name": user["name"],
                                        "p_decided_by_username": user["username"],
                                    },
                                ).execute()
                            )
                            st.success(f"Accepted #{transfer_id}.")
                            st.rerun()
                        except Exception as e:
                            st.error(f"Accept failed: {e}")

                with c2:
                    note = st.text_input("Reject note", value="", key=f"rej_note_{transfer_id}")
                    if st.button(f"Reject #{transfer_id}", key=f"rej_{transfer_id}"):
                        if not note.strip():
                            st.warning("Reject note required.")
                        else:
                            try:
                                resp = (
                                    client.rpc(
                                        "reject_stock_transfer",
                                        {
                                            "p_transfer_id": transfer_id,
                                            "p_reject_note": note.strip(),
                                            "p_decided_by_name": user["name"],
                                        },
                                    ).execute()
                                )
                                st.success(f"Rejected #{transfer_id}.")
                                st.rerun()
                            except Exception as e:
                                st.error(f"Reject failed: {e}")


# ---------------------------
# Transactions
# ---------------------------
with tabs[3]:
    require_login()

    st.subheader("Transactions")
    tdf = get_transactions_df(limit=500)
    if tdf.empty:
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

        df = tdf.copy()
        if org_f != "all":
            df = df[df["organization"] == org_f]
        if typ_f != "all":
            df = df[df["type"] == typ_f]
        if cat_f != "all":
            df = df[df["category"] == cat_f]
        if size_f.strip():
            df = df[df["size"] == size_f.strip()]

        df["created_at"] = df["created_at"].apply(fmt_ts)
        st.dataframe(
            df[["id", "created_at", "organization", "type", "category", "size", "quantity", "reason", "user_name"]],
            use_container_width=True,
            hide_index=True,
        )
