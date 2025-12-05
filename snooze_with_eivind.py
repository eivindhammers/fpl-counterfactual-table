import streamlit as st
import requests
import pandas as pd

# -----------------------------------
# CONFIG – your defaults
# -----------------------------------
DEFAULT_LEAGUE_ID = 219710
YOUR_ENTRY_ID = 7582343
YOUR_TEAM_NAME = "Wirtz a shot?"
YOUR_MANAGER_NAME = "Eivind Moe Hammersmark"

# -----------------------------------
# Helpers
# -----------------------------------

def get_gw_dates():
    boot = requests.get("https://fantasy.premierleague.com/api/bootstrap-static/").json()
    return pd.DataFrame([
        {"gw": ev["id"], "deadline": ev["deadline_time"][:10]}
        for ev in boot["events"]
    ])


def get_entry_history(entry_id, team_name, manager_name):
    url = f"https://fantasy.premierleague.com/api/entry/{entry_id}/history/"
    res = requests.get(url).json()
    if "current" not in res:
        return pd.DataFrame()

    rows = []
    for gw in res["current"]:
        rows.append({
            "entry_id": entry_id,
            "team_name": team_name,
            "manager": manager_name,
            "gw": gw["event"],
            "points_gw_net": gw["points"],
            "points_gw_raw": gw["points"] + gw["event_transfers_cost"],
            "transfer_cost": gw["event_transfers_cost"],
        })
    return pd.DataFrame(rows)


def get_league_entries(league_id):
    url = f"https://fantasy.premierleague.com/api/leagues-classic/{league_id}/standings/"
    data = requests.get(url).json()
    if "standings" not in data:
        return []

    return [
        (t["entry"], t["entry_name"], t["player_name"])
        for t in data["standings"]["results"]
    ]


# -----------------------------------
# Streamlit UI
# -----------------------------------

st.title("Kontrafaktisk Snooze-tabell")
st.caption("Snooze-data er lagt inn med Eivind som ekstra deltaker, men man kan i prinsippet sjekke hvilken som helst liga, dersom man har den 6-sifrede ID-en.")

# Pre-filled ID values
league_id = st.number_input("Liga-ID (default: Snooze)", min_value=1, step=1, value=DEFAULT_LEAGUE_ID)
start_date = st.date_input("Dato hvor poengtelling starter (default: 1. november, rett før GW10)", value=pd.to_datetime("2025-11-01"))

# -----------------------------------
# Manual entries (your team auto-added)
# -----------------------------------

if "manual_entries" not in st.session_state:
    st.session_state.manual_entries = [
        (YOUR_ENTRY_ID, YOUR_TEAM_NAME, YOUR_MANAGER_NAME)
    ]

st.subheader("➕ Legg til flere spillere")

with st.form("manual"):
    entry_id_manual = st.text_input("'Entry ID'")
    entry_team_manual = st.text_input("Lagnavn")
    entry_manager_manual = st.text_input("Managernavn")
    add_manual = st.form_submit_button("Legg til")

if add_manual and entry_id_manual:
    st.session_state.manual_entries.append(
        (int(entry_id_manual), entry_team_manual, entry_manager_manual)
    )

# Show manual entries
st.write("Manuelle spillere inkludert:")
st.table(pd.DataFrame(
    st.session_state.manual_entries,
    columns=["'Entry ID'", "Lag", "Manager"]
))

# -----------------------------------
# Compute league table
# -----------------------------------

if st.button("Beregn ligatabellen"):
    st.write("Henter liga-data…")
    gw_dates = get_gw_dates()

    # Fetch league entries
    entries = []
    if league_id > 0:
        entries = get_league_entries(league_id)

    # Add manual entries (including your team)
    entries.extend(st.session_state.manual_entries)

    # Deduplicate by entry ID
    seen = set()
    deduped = []
    for e in entries:
        if e[0] not in seen:
            deduped.append(e)
            seen.add(e[0])
    entries = deduped

    if len(entries) == 0:
        st.warning("Ingen spillere funnet eller lagt til manuelt. Prøv igjen.")
        st.stop()

    # Build history dataframe
    st.write("Henter gameweek historikk…")
    dfs = []
    for eid, name, manager in entries:
        dfs.append(get_entry_history(eid, name, manager))
    df = pd.concat(dfs, ignore_index=True)

    # Merge with deadlines
    df = df.merge(get_gw_dates(), on="gw", how="left")

    # Filter since start date
    df["deadline"] = pd.to_datetime(df["deadline"])
    cutoff = pd.to_datetime(start_date)
    df_since = df[df["deadline"] >= cutoff].copy()

    if df_since.empty:
        st.warning("Ingen gameweek data etter valgt dato.")
        st.stop()

    # Compute standings
    table = (
        df_since.groupby(["entry_id", "team_name", "manager"])["points_gw_net"]
        .sum()
        .reset_index()
        .rename(columns={"points_gw_net": "points_since"})
    )

    # Rank
    table["rank"] = table["points_since"].rank(method="min", ascending=False)
    table = table.sort_values("rank").reset_index(drop=True)

    # Drop entry_id in display
    display = table.drop(columns=["entry_id"])

    st.subheader(f"🏆 Ligatabell fom. valgt dato: {start_date}")
    st.dataframe(display)

    # Download
    st.download_button(
        "Last ned CSV",
        data=display.to_csv(index=False),
        file_name="league_table_since.csv",
        mime="text/csv"
    )