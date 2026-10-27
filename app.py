from datetime import date, datetime, timedelta
from pathlib import Path
import base64
import html
import json
import os
import re
import sys
import subprocess
from pathlib import Path
import requests

import streamlit as st

from railway.data_loader import load_data, station_options
from railway.route_finder import find_journeys
from railway.pnr_search import get_pnr_status
from railway.train_available import (
    _call_live_availability,
    _inject_availability_styles,
    _first as _availability_first,
    _station_code as _availability_station_code,
    _status_class as _availability_status_class,
    _status_label as _availability_status_label,
)


# ============================================================
# RailConnect — Train Route Finder
# ============================================================

st.set_page_config(
    page_title="RailConnect | Train Route Finder",
    page_icon="R",
    layout="wide",
    initial_sidebar_state="collapsed",
)

PROJECT_DIR = Path(__file__).resolve().parent
IMAGE_NAME = "vande_bharat.png"
LOGO_NAME = "Logo.png"
LOGO_CANDIDATES = [
    PROJECT_DIR / "assets" / LOGO_NAME,
    PROJECT_DIR / LOGO_NAME,
    Path(r"C:\Users\par30\OneDrive\Desktop\Project_New\Rail_Connect\railway-route-finder\assets\Logo.png"),
]

# Resolve the hero image relative to this app, which works both locally and
# on Streamlit Community Cloud. Do not rely on a personal Windows-only path.
IMAGE_CANDIDATES = [
    PROJECT_DIR / "assets" / IMAGE_NAME,
    PROJECT_DIR / IMAGE_NAME,
    PROJECT_DIR / "assets" / "Modern Indian Railways EMU in Green Corridor.png",
    PROJECT_DIR / "Modern Indian Railways EMU in Green Corridor.png",
]

# If the filename's capitalization differs in the deployed Linux environment,
# also try a case-insensitive match inside the assets directory.
ASSETS_DIR = PROJECT_DIR / "assets"
if ASSETS_DIR.is_dir():
    try:
        for asset_path in ASSETS_DIR.iterdir():
            if asset_path.is_file() and asset_path.name.casefold() == IMAGE_NAME.casefold():
                IMAGE_CANDIDATES.insert(0, asset_path)
                break
        else:
            for asset_path in ASSETS_DIR.iterdir():
                if asset_path.is_file() and asset_path.suffix.casefold() in {".png", ".jpg", ".jpeg", ".webp"} and "vande" in asset_path.name.casefold():
                    IMAGE_CANDIDATES.insert(0, asset_path)
                    break
    except OSError:
        pass


# ----------------------------- Data -----------------------------

@st.cache_resource(show_spinner="Loading railway schedules...")
def get_data():
    return load_data()


try:
    data = get_data()
    stations = station_options(data)
except Exception as exc:
    st.error(f"Could not load railway data: {exc}")
    st.info(
        "Check that trains.csv, stops.csv and stations.csv are in the "
        "data folder configured by railway/data_loader.py."
    )
    st.stop()

if not stations:
    st.error("No stations were found in the railway data.")
    st.stop()

station_labels = list(stations.keys())


# ----------------------------- Styling -----------------------------

st.markdown(
    """
<style>
@import url("https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap");

:root {
    --rail-blue: #0754c8;
    --rail-blue-dark: #0646a8;
    --rail-orange: #f47b20;
    --rail-ink: #0a1b49;
    --rail-muted: #68748a;
    --rail-border: #d7e1f1;
}

html, body, [class*="css"] { font-family: Inter, sans-serif; }
.stApp { color: var(--rail-ink); background: #ffffff !important; }
#MainMenu, footer, header[data-testid="stHeader"] { visibility: hidden; }
[data-testid="stSidebar"] { display: none; }
.block-container { max-width: 1440px !important; width: calc(100% - 32px) !important; margin-left: auto !important; margin-right: auto !important; padding-top: 0 !important; padding-bottom: 2.5rem !important; padding-left: 0 !important; padding-right: 0 !important; }
.advisory { background: #ffb24c; color: #18243b; padding: 10px 22px; margin: 0; font-size: 12px; font-weight: 600; }
.navbar { background: linear-gradient(105deg, #0878b8, #0756a8); color: white; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 18px 28px; margin: 0; min-height: 90px; }
.brand { display: flex; align-items: center; gap: 12px; }
.brand-mark { display: grid; place-items: center; width: 44px; height: 44px; border-radius: 12px; background: white; color: var(--rail-blue); font-size: 25px; font-weight: 800; }
.brand-name { font-size: 23px; font-weight: 800; letter-spacing: -.7px; }
.brand-sub { margin-top: 3px; font-size: 10px; letter-spacing: 2px; }
.nav-right { display: flex; align-items: center; gap: 24px; color: white; font-size: 13px; font-weight: 700; }
.nav-right a { color: white !important; text-decoration: none !important; }
.hero { position: relative; isolation: isolate; min-height: 410px; overflow: hidden; margin: 0; padding: 72px clamp(24px, 6vw, 90px) 48px; border-radius: 0 0 28px 28px; background: linear-gradient(115deg, #e6f0ff 0%, #ffffff 45%, #fff0e2 100%); box-shadow: 0 14px 35px #183d6810; }
.hero-image { position: absolute; z-index: -1; right: 0; top: 0; width: 55%; height: 100%; object-fit: cover; object-position: center; opacity: .94; mask-image: linear-gradient(to right, transparent 0%, black 35%); }
.hero-copy { position: relative; z-index: 1; max-width: 690px; }
.hero-kicker { color: var(--rail-blue); font-size: 12px; font-weight: 800; letter-spacing: 2.5px; text-transform: uppercase; margin-bottom: 14px; }
.hero h1 { color: #071946; font-size: clamp(38px, 5vw, 64px); line-height: 1.08; letter-spacing: -2px; font-weight: 800; margin: 0 0 17px; }
.hero h1 span { color: var(--rail-orange); }
.hero p { max-width: 525px; color: #4c5a71; font-size: 15px; line-height: 1.8; }
.hero-note { display: inline-block; margin-top: 12px; padding: 9px 14px; border: 1px solid #d5e4fa; border-radius: 24px; background: #ffffffdf; color: #23436f; font-size: 12px; font-weight: 700; }
.section-heading { color: #0b1c48; font-size: 25px; font-weight: 800; margin: 20px 0 3px; }
.section-subtitle { color: #68748a; font-size: 13px; margin-bottom: 14px; }
div[data-testid="stSelectbox"] label, div[data-testid="stDateInput"] label { color: #47566d; font-size: 12px; font-weight: 700; }
div[data-testid="stSelectbox"] [data-baseweb="select"] > div { min-height: 50px; border-radius: 11px; border-color: #d7e1f1; background: white; }
div[data-testid="stDateInput"] input { min-height: 50px; border-radius: 11px; border-color: #d7e1f1; background: white; }
div[data-testid="stRadio"] > div { gap: 10px; }
div[data-testid="stRadio"] label { padding: 7px 16px; border: 1px solid #d7e1f1; border-radius: 22px; background: #fff; color: #0754c8; font-size: 13px; font-weight: 800; }
div[data-testid="stRadio"] label:has(input:checked) { background: #0754c8; border-color: #0754c8; color: #fff; }
div[data-testid="stRadio"] label p { color: inherit; }
div[data-testid="stButton"] button { min-height: 38px; border-radius: 10px; font-weight: 700; }
div[data-testid="stButton"] button[kind="primary"] { min-height: 36px !important; width: auto !important; padding: .35rem 1.15rem !important; border-radius: 22px !important; background: #477bc0 !important; color: white !important; border: 1px solid #477bc0 !important; font-size: 13px !important; font-weight: 700 !important; box-shadow: 0 3px 8px #0754c822; transition: background .2s ease, transform .2s ease; }
div[data-testid="stButton"] button[kind="primary"]:hover { background: #315f9e !important; border-color: #315f9e !important; transform: translateY(-1px); }
div[data-testid="stFormSubmitButton"] button { min-height: 38px; border-radius: 22px; background: var(--rail-blue); color: white; border: 0; font-weight: 800; }
.train-card { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); align-items: center; gap: 15px; padding: 20px; margin: 12px 0; border: 1px solid #d7e3f3; border-radius: 20px; background: linear-gradient(115deg, #fff 0%, #f7faff 62%, #edf6ff 100%); box-shadow: 0 9px 25px #173b6312; transition: transform .18s ease, box-shadow .18s ease; }
.train-card:hover { transform: translateY(-2px); box-shadow: 0 14px 30px #173b6318; }
.train-id { color: #5d6b80; font-size: 11px; font-weight: 800; margin-bottom: 7px; }
.train-name { color: #0c1b3d; font-size: 16px; font-weight: 800; line-height: 1.4; }
.train-names { display: flex; flex-direction: column; gap: 5px; }
.train-name-line { color: #0c1b3d; font-size: 14px; font-weight: 800; line-height: 1.5; overflow-wrap: anywhere; }
.route-tag { display: inline-block; border-radius: 20px; background: #eaf2ff; color: #1957ad; padding: 5px 9px; font-size: 10px; font-weight: 800; margin-top: 9px; }
.time { color: #101c36; font-size: 25px; line-height: 1.2; font-weight: 800; }
.date-small { color: #243958; font-size: 16px; font-weight: 800; margin-top: 7px; }
.station { color: #263954; font-size: 12px; line-height: 1.45; margin-top: 5px; font-weight: 700; overflow-wrap: anywhere; }
.route-middle { display: flex; flex-direction: column; align-items: center; text-align: center; min-width: 0; }
.duration { color: #101c36; text-align: center; font-size: 15px; font-weight: 800; white-space: nowrap; }
.timeline { position: relative; width: calc(100% - 10px); box-sizing: border-box; height: 3px; margin: 12px 0 10px; background: #2e49df; border-radius: 3px; }
.timeline:before, .timeline:after { content: ""; position: absolute; top: -3px; width: 9px; height: 9px; border-radius: 50%; background: #2e49df; }
.timeline:before { left: -3px; } .timeline:after { right: -3px; }
.distance-value { color: #17243d; text-align: center; font-size: 14px; font-weight: 800; margin-top: 0; }
.changes { color: #a4164a; font-size: 10px; font-weight: 800; text-align: center; margin-top: 6px; }
.train-action { border-left: 1px solid #cbd7e6; padding-left: 12px; }
.day-row { display: flex; gap: 4px; flex-wrap: wrap; margin: 0 0 10px; }
.day-circle { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; border-radius: 50%; font-size: 9px; font-weight: 800; border: 1px solid #34445d; color: #17243d; background: #fff; }
.day-circle.active { background: #0754c8; color: #fff; border-color: #0754c8; }
.leg-title { font-size: 14px; font-weight: 800; color: #10244a; margin-bottom: 13px; }
.leg-route { display: grid; grid-template-columns: minmax(0, 1fr) minmax(120px, .65fr) minmax(0, 1fr); align-items: center; gap: 18px; padding: 16px 18px; border-radius: 12px; background: linear-gradient(110deg, #fff 0%, #f4f8ff 100%); border: 1px solid #e0e8f5; }
.leg-end { min-width: 0; } .leg-end.arrival { text-align: right; }
.leg-caption { color: #7b8798; font-size: 10px; font-weight: 800; letter-spacing: .8px; }
.leg-time { color: #15254a; font-size: 23px; font-weight: 800; margin-top: 4px; }
.leg-station { color: #263954; font-size: 12px; font-weight: 700; line-height: 1.5; margin-top: 5px; overflow-wrap: anywhere; }
.leg-date { color: #243958; font-size: 16px; font-weight: 800; margin-top: 7px; }
.leg-track { min-width: 0; text-align: center; align-self: center; }
.leg-summary-duration { color: #15254a; font-size: 16px; font-weight: 800; white-space: nowrap; }
.leg-timeline { position: relative; height: 3px; margin: 15px 7px 12px; border-radius: 3px; background: #2e49df; }
.leg-timeline:before, .leg-timeline:after { content: ""; position: absolute; top: -4px; width: 11px; height: 11px; border-radius: 50%; background: #2e49df; }
.leg-timeline:before { left: -4px; } .leg-timeline:after { right: -4px; }
.leg-summary-distance { color: #17243d; font-size: 14px; font-weight: 800; }

/* Interchange details — soft purple / lavender aesthetic */
.transfer { position: relative; overflow: hidden; background: linear-gradient(135deg, #f7f2ff 0%, #efe7ff 52%, #e9e6ff 100%); border: 1px solid #d8c8f4; border-left: 5px solid #8052cf; color: #4a3566; border-radius: 18px; padding: 20px 22px; font-size: 12px; line-height: 1.8; margin: 12px 0 18px; box-shadow: 0 10px 26px rgba(75, 42, 130, .10); }
.transfer:after { content: ""; position: absolute; width: 150px; height: 150px; right: -68px; top: -82px; border: 22px solid rgba(126, 87, 194, .08); border-radius: 50%; pointer-events: none; }
.transfer-title { position: relative; z-index: 1; font-size: 18px; font-weight: 800; color: #56308e; margin-bottom: 10px; letter-spacing: -.25px; }
.transfer > div:not(.transfer-title) { position: relative; z-index: 1; }
.transfer b { color: #5b3a8c; }
.transfer-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; margin-top: 14px; }
.transfer-item { position: relative; z-index: 1; background: rgba(255,255,255,.78); border: 1px solid #dfd2f4; border-radius: 14px; padding: 14px 15px; min-height: 100px; box-shadow: 0 4px 12px rgba(74, 46, 122, .04); }
.transfer-label { color: #8264ad; font-size: 10px; font-weight: 800; letter-spacing: 1.1px; }
.transfer-value { color: #43266e; font-size: 17px; font-weight: 800; margin-top: 5px; }
.transfer-train { color: #5b4777; font-size: 12px; font-weight: 700; margin-top: 8px; overflow-wrap: anywhere; }
.transfer-wait { position: relative; z-index: 1; display: flex; align-items: center; justify-content: center; gap: 8px; margin-top: 15px; padding: 11px 15px; border: 1px solid #d1baf0; border-radius: 12px; background: linear-gradient(100deg, #e8dcfb, #e1e5ff); color: #542b8a; font-size: 13px; font-weight: 800; text-align: center; }
.transfer-wait-label { color: #7756a3; font-size: 10px; letter-spacing: 1px; text-transform: uppercase; }
.results-summary { margin: 12px 0; padding: 12px 16px; border: 1px solid #d7e3f1; border-radius: 12px; background: #ffffffc9; color: #34445d; font-size: 13px; }
.helper { background: #ffffffd9; border: 1px solid #d7e3f1; border-radius: 17px; padding: 22px 24px; margin-top: 32px; }
.helper h3 { font-size: 18px; color: #0b1c48; margin: 0 0 7px; }
.helper p { color: #6c788b; font-size: 12px; line-height: 1.8; overflow-wrap: anywhere; }
.footer { text-align: center; color: #8590a0; font-size: 11px; padding: 20px 0 5px; }
@media (max-width: 1000px) { .train-card { grid-template-columns: 1fr 1fr; } .train-action { border-left: 0; padding-left: 0; } .hero-image { width: 70%; opacity: .28; } .leg-route { grid-template-columns: minmax(0, 1fr) minmax(95px, .55fr) minmax(0, 1fr); gap: 12px; padding: 13px; } }
@media (max-width: 650px) {
    .block-container { width: calc(100% - 20px) !important; }
    .navbar { padding: 14px 20px; flex-wrap: wrap; }
    .brand-name { font-size: 19px; } .nav-right { gap: 12px; }
    .hero { padding: 40px 22px; min-height: 340px; } .hero-image { width: 100%; opacity: .17; mask-image: none; }
    .hero h1 { letter-spacing: -1px; } .train-card { grid-template-columns: 1fr 1fr; padding: 15px; gap: 13px; }
    .route-middle { grid-column: 1 / -1; grid-row: 3; padding: 0 8px; } .train-action { grid-column: 1 / -1; }
    .leg-route { grid-template-columns: 1fr; gap: 15px; } .leg-end.arrival { text-align: left; }
    .leg-track { grid-row: 2; padding: 0 12px; } .transfer-grid { grid-template-columns: 1fr; }
}
.section-heading { color: #111d43; font-size: clamp(22px, 2.5vw, 28px); font-weight: 800; letter-spacing: -.55px; margin: 24px 0 5px; }
.section-subtitle { color: #68748a; font-size: 13px; line-height: 1.7; margin-bottom: 16px; }
div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stDateInput"]) { border: 1px solid #ded6ff !important; border-radius: 20px !important; background: linear-gradient(115deg, #f7f4ff 0%, #fff 58%, #edf7ff 100%) !important; box-shadow: 0 10px 28px #3513a510 !important; padding: 22px 24px !important; }
div[data-testid="stSelectbox"] label, div[data-testid="stDateInput"] label { color: #34445d !important; font-size: 12px !important; font-weight: 800 !important; margin-bottom: 6px !important; }
div[data-testid="stSelectbox"] [data-baseweb="select"] > div, div[data-testid="stDateInput"] input { min-height: 48px !important; border-radius: 12px !important; border: 1px solid #d9dff0 !important; background: #fff !important; box-shadow: 0 2px 7px #172c4a08 !important; transition: border-color .18s ease, box-shadow .18s ease !important; }
div[data-testid="stSelectbox"] [data-baseweb="select"] > div:focus-within, div[data-testid="stDateInput"] input:focus { border-color: #7b61e8 !important; box-shadow: 0 0 0 3px #7b61e81c !important; }
div[data-testid="stButton"] button[kind="primary"] { background: linear-gradient(105deg, #4b19d1 0%, #0878b8 100%) !important; border: 0 !important; border-radius: 13px !important; min-height: 46px !important; padding: .65rem 1.3rem !important; box-shadow: 0 7px 16px #3513a52b !important; font-size: 13px !important; font-weight: 800 !important; }
div[data-testid="stButton"] button[kind="primary"]:hover { filter: brightness(1.05) !important; box-shadow: 0 10px 20px #3513a533 !important; transform: translateY(-1px); }
.train-card { border: 1px solid #dce3f2; border-radius: 20px; background: linear-gradient(115deg, #fff 0%, #faf9ff 52%, #eef8ff 100%); box-shadow: 0 9px 25px #1b31500c; padding: 22px; }
.train-card:hover { border-color: #c9bfff; box-shadow: 0 14px 30px #3513a51a; }
.route-tag { background: #eee9ff; color: #4b19d1; border: 1px solid #e0d8ff; }
.timeline { background: linear-gradient(90deg, #4b19d1, #0b83bf); }
.timeline:before, .timeline:after { background: #4b19d1; }
.timeline:after { background: #0b83bf; } .duration { color: #4b19d1; }
@media (max-width: 650px) { div[data-testid="stVerticalBlockBorderWrapper"]:has([data-testid="stDateInput"]) { padding: 16px !important; border-radius: 16px !important; } .train-card { padding: 16px; border-radius: 16px; } }
.pnr-hero { position: relative; overflow: hidden; padding: 25px 28px; margin: 14px 0 18px; border-radius: 22px; color: #fff; background: linear-gradient(120deg, #28106f 0%, #4b19d1 48%, #0878b8 100%); box-shadow: 0 14px 32px #3513a51f; }
.pnr-hero:after { content: ""; position: absolute; width: 190px; height: 190px; right: -42px; top: -72px; border: 28px solid #ffffff18; border-radius: 50%; }
.pnr-eyebrow { position: relative; z-index: 1; color: #d9ccff; font-size: 10px; font-weight: 800; letter-spacing: 2px; text-transform: uppercase; }
.pnr-title { position: relative; z-index: 1; margin-top: 7px; font-size: clamp(25px, 3vw, 34px); line-height: 1.2; font-weight: 800; letter-spacing: -.8px; }
.pnr-description { position: relative; z-index: 1; margin-top: 8px; color: #f0ebff; font-size: 13px; line-height: 1.7; max-width: 650px; }
.pnr-panel-title { color: #111d43; font-size: 18px; font-weight: 800; margin: 8px 0 12px; }
.pnr-train-banner { padding: 22px 24px; border: 1px solid #ded6ff; border-radius: 18px; background: linear-gradient(115deg, #f7f4ff 0%, #fff 58%, #edf7ff 100%); box-shadow: 0 8px 22px #1b31500a; margin: 12px 0 15px; }
.pnr-train-name { color: #111d43; font-size: clamp(20px, 2.5vw, 27px); font-weight: 800; line-height: 1.35; overflow-wrap: anywhere; }
.pnr-train-number { display: inline-block; margin-top: 9px; padding: 6px 11px; border-radius: 20px; background: #ebe5ff; color: #4b19d1; font-size: 11px; font-weight: 800; }
.pnr-meta-pill { display: inline-block; margin: 5px 5px 0 0; padding: 7px 10px; border-radius: 9px; border: 1px solid #e0e6f2; background: #fff; color: #47566d; font-size: 11px; font-weight: 700; }
.pnr-route-box { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); align-items: center; gap: 12px; padding: 20px; margin: 10px 0 20px; border: 1px solid #e0e7f2; border-radius: 17px; background: #fff; position: relative; min-height: 150px; box-sizing: border-box; }
.pnr-route-box > div { min-width: 0; } .pnr-route-box > div:first-child { grid-column: 1; grid-row: 1; padding-right: 12%; } .pnr-route-box > div:last-child { grid-column: 2; grid-row: 1; padding-left: 12%; text-align: right; }
.pnr-route-middle { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); width: 28%; min-width: 120px; max-width: 240px; text-align: center; margin: 0; z-index: 1; }
.pnr-route-line { display: block; width: 100%; box-sizing: border-box; }
.pnr-route-label { color: #7a8799; font-size: 10px; font-weight: 800; letter-spacing: 1px; }
.pnr-route-station { color: #13254a; font-size: 17px; line-height: 1.5; font-weight: 800; margin-top: 6px; overflow-wrap: anywhere; }
.pnr-route-time { color: #4b19d1; font-size: 13px; font-weight: 800; margin-top: 7px; }
.pnr-route-date { color: #718096; font-size: 11px; font-weight: 700; margin-top: 4px; }
.pnr-route-line { height: 3px; border-radius: 5px; margin: 12px 4px; background: linear-gradient(90deg, #4b19d1, #0b83bf); position: relative; }
.pnr-route-line:before, .pnr-route-line:after { content: ""; position: absolute; top: -4px; width: 11px; height: 11px; border-radius: 50%; background: #4b19d1; }
.pnr-route-line:before { left: -2px; } .pnr-route-line:after { right: -2px; background: #0b83bf; }
.pnr-route-duration { color: #34445d; font-size: 12px; font-weight: 800; } .pnr-route-distance { display: none; }
.pnr-passenger-card { padding: 17px 18px; margin: 10px 0; border: 1px solid #e0e7f2; border-radius: 16px; background: linear-gradient(110deg, #fff, #f8faff); }
.pnr-passenger-heading { color: #13254a; font-size: 15px; font-weight: 800; margin-bottom: 12px; }
.pnr-status-pill { display: inline-block; padding: 10px 16px; border-radius: 20px; background: #e8f8ef; border: 1px solid #c6efd6; color: #137744; font-size: 18px; line-height: 1.35; font-weight: 900; }
.pnr-help-note { margin-top: 15px; padding: 13px 15px; border: 1px solid #d8e5f6; border-radius: 12px; background: #f4f8ff; color: #4e5e77; font-size: 12px; line-height: 1.7; }
@media (max-width: 650px) { .pnr-hero { padding: 22px 19px; } .pnr-route-box { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; padding: 16px; min-height: 170px; } .pnr-route-box > div:first-child { padding-right: 8%; } .pnr-route-box > div:last-child { padding-left: 8%; } .pnr-route-middle { width: 26%; min-width: 86px; max-width: 140px; } .pnr-route-station { font-size: 15px; } .pnr-route-duration { font-size: 10px; } .pnr-route-label { font-size: 9px; } .pnr-train-banner { padding: 18px; } }
div[data-testid="stRadio"] { width: fit-content !important; max-width: calc(100% - 32px) !important; margin: 18px auto 24px !important; padding: 6px 8px !important; box-sizing: border-box !important; border: 1px solid #e1def5 !important; border-radius: 17px !important; background: #ffffff !important; box-shadow: 0 5px 18px rgba(25, 45, 80, .08) !important; }
div[data-testid="stRadio"] > label { display: none !important; }
div[data-testid="stRadio"] div[role="radiogroup"] { gap: 4px !important; align-items: center !important; justify-content: center !important; flex-wrap: wrap !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label { position: relative !important; display: flex !important; align-items: center !important; justify-content: center !important; min-width: 0 !important; flex: 1 1 auto !important; padding: 11px clamp(10px, 1.6vw, 23px) !important; margin: 0 !important; border: 1px solid transparent !important; border-radius: 12px !important; background: transparent !important; color: #59647d !important; font-size: 13px !important; font-weight: 800 !important; line-height: 1.25 !important; cursor: pointer !important; transition: background .2s ease, color .2s ease, box-shadow .2s ease, transform .2s ease !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label:hover { background: #fff !important; color: #4b2bc4 !important; transform: translateY(-1px) !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label > div:first-child { display: none !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label:has(input:checked) { background: linear-gradient(110deg, #552bd8 0%, #087ab8 100%) !important; color: #fff !important; border-color: transparent !important; box-shadow: 0 6px 15px rgba(66, 57, 180, .23) !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label p { color: inherit !important; font-weight: inherit !important; margin: 0 !important; }
.hero { border: 1px solid rgba(255,255,255,.8) !important; background: radial-gradient(circle at 85% 15%, rgba(255,255,255,.8), transparent 27%), linear-gradient(120deg, #eaf1ff 0%, #fbfaff 48%, #fff0e5 100%) !important; box-shadow: 0 20px 50px rgba(26, 47, 92, .11) !important; }
.hero-kicker { display: inline-flex !important; align-items: center !important; gap: 8px !important; padding: 8px 12px !important; border: 1px solid #dbe5ff !important; border-radius: 999px !important; background: rgba(255,255,255,.82) !important; box-shadow: 0 4px 14px rgba(33, 70, 140, .06) !important; letter-spacing: 1.5px !important; }
.hero h1 { letter-spacing: -2.4px !important; text-shadow: 0 3px 18px rgba(11, 28, 72, .05) !important; }
.hero h1 span { background: linear-gradient(100deg, #f47b20 0%, #ef4e78 55%, #7044dc 100%) !important; -webkit-background-clip: text !important; background-clip: text !important; color: transparent !important; }
.hero-note { border-color: rgba(199, 213, 244, .9) !important; box-shadow: 0 8px 22px rgba(28, 55, 105, .06) !important; }
.train-card { border-color: #e2e5f4 !important; box-shadow: 0 12px 30px rgba(29, 45, 86, .07) !important; transition: transform .2s ease, box-shadow .2s ease, border-color .2s ease !important; }
.train-card:hover { border-color: #c9c4f5 !important; box-shadow: 0 18px 36px rgba(48, 42, 118, .12) !important; transform: translateY(-2px) !important; }
@media (max-width: 640px) { div[data-testid="stRadio"] { width: 100% !important; margin: 14px auto 20px !important; } div[data-testid="stRadio"] div[role="radiogroup"] label { min-width: 0 !important; flex: 1 1 0 !important; padding: 11px 10px !important; font-size: 12px !important; } }
/* Final feature-selector spacing override, applied on every page. */
div[data-testid="stRadio"] { width: fit-content !important; max-width: calc(100% - 32px) !important; margin: 14px auto 20px !important; padding: 5px !important; box-sizing: border-box !important; }
div[data-testid="stRadio"] div[role="radiogroup"] { display: flex !important; flex-flow: row wrap !important; justify-content: center !important; gap: 4px !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label { min-width: 0 !important; flex: 0 1 auto !important; white-space: nowrap !important; padding: 10px clamp(10px, 1.35vw, 19px) !important; margin: 0 !important; font-size: 12px !important; }
@media (max-width: 720px) { div[data-testid="stRadio"] { width: calc(100% - 20px) !important; max-width: calc(100% - 20px) !important; margin: 12px auto 16px !important; } div[data-testid="stRadio"] div[role="radiogroup"] label { flex: 1 1 42% !important; white-space: normal !important; padding: 10px 7px !important; font-size: 11px !important; } }
.advisory { display: flex !important; align-items: center !important; gap: 6px !important; min-height: 34px !important; padding: 8px 22px !important; background: linear-gradient(90deg, #fff1d6 0%, #ffe5bd 100%) !important; border: 1px solid rgba(232, 157, 54, .22) !important; border-bottom: 0 !important; color: #664116 !important; font-size: 11px !important; line-height: 1.45 !important; letter-spacing: .08px !important; }
.advisory b { color: #8a4b08 !important; font-weight: 800 !important; }
.navbar { position: relative !important; overflow: hidden !important; min-height: 86px !important; padding: 18px 28px !important; border: 1px solid rgba(255,255,255,.22) !important; border-top: 0 !important; border-radius: 0 0 18px 18px !important; background: linear-gradient(112deg, #0756a8 0%, #087ab8 58%, #0b69ad 100%) !important; box-shadow: 0 14px 32px rgba(9, 76, 145, .16) !important; }
.navbar::after { content: "" !important; position: absolute !important; width: 260px !important; height: 260px !important; right: 12% !important; top: -190px !important; border: 1px solid rgba(255,255,255,.13) !important; border-radius: 50% !important; box-shadow: 0 0 0 28px rgba(255,255,255,.035), 0 0 0 58px rgba(255,255,255,.025) !important; pointer-events: none !important; }
.brand { position: relative !important; z-index: 1 !important; gap: 13px !important; }
.brand-mark { width: 46px !important; height: 46px !important; border-radius: 14px !important; box-shadow: 0 5px 14px rgba(0, 27, 84, .15) !important; font-size: 24px !important; overflow: hidden !important; flex: 0 0 46px !important; }
.brand-mark img { display: block !important; width: 100% !important; height: 100% !important; object-fit: contain !important; border-radius: inherit !important; background: #fff !important; }
.brand-name { font-size: 24px !important; letter-spacing: -.8px !important; }
.brand-sub { opacity: .84 !important; font-size: 9px !important; letter-spacing: 2.1px !important; }
.nav-right { position: relative !important; z-index: 1 !important; gap: 10px !important; }
.nav-right span, .nav-right a { padding: 9px 13px !important; border: 1px solid rgba(255,255,255,.19) !important; border-radius: 999px !important; background: rgba(255,255,255,.08) !important; text-decoration: none !important; transition: background .18s ease, transform .18s ease !important; }
.nav-right a:hover, .nav-right span:hover { background: rgba(255,255,255,.17) !important; transform: translateY(-1px) !important; }
div[data-testid="stRadio"] { width: fit-content !important; max-width: calc(100% - 24px) !important; margin: 22px auto 26px !important; padding: 6px !important; border: 1px solid rgba(205, 216, 239, .9) !important; border-radius: 16px !important; background: rgba(255,255,255,.78) !important; box-shadow: 0 12px 30px rgba(35, 57, 102, .08) !important; backdrop-filter: blur(12px) !important; }
div[data-testid="stRadio"] div[role="radiogroup"] { display: flex !important; flex-flow: row nowrap !important; gap: 5px !important; }
div[data-testid="stRadio"] div[role="radiogroup"] label { min-width: 150px !important; white-space: nowrap !important; padding: 11px 20px !important; border-radius: 11px !important; font-size: 12px !important; }
@media (max-width: 720px) { .advisory { align-items: flex-start !important; padding: 8px 12px !important; font-size: 10px !important; } .navbar { padding: 15px 16px !important; min-height: 76px !important; } .brand-name { font-size: 20px !important; } .brand-sub { font-size: 8px !important; letter-spacing: 1.4px !important; } .nav-right { gap: 5px !important; font-size: 10px !important; } .nav-right span, .nav-right a { padding: 7px 9px !important; } div[data-testid="stRadio"] { width: calc(100% - 8px) !important; margin: 16px auto 20px !important; } div[data-testid="stRadio"] div[role="radiogroup"] { flex-wrap: wrap !important; justify-content: center !important; } div[data-testid="stRadio"] div[role="radiogroup"] label { min-width: 0 !important; flex: 1 1 auto !important; padding: 10px 12px !important; font-size: 11px !important; } }
.availability-placeholder-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 10px; margin: -8px 0 22px; }
.availability-placeholder { display: flex; flex-direction: column; gap: 5px; padding: 12px 14px; border: 1px solid #d6e5da; border-radius: 12px; background: #f2f8f3; color: #245b36; }
.availability-placeholder strong { font-size: 15px; } .availability-placeholder span { font-size: 12px; color: #68748a; }
@media (max-width: 640px) { .availability-placeholder-grid { grid-template-columns: 1fr; } }
/* Page selector: full-width single row directly under the hero. */
div[data-testid="stRadio"] { width: 100% !important; box-sizing: border-box !important; margin: 14px 0 24px !important; padding: 8px 14px !important; border: 1px solid #d7e1f1 !important; border-radius: 18px !important; background: #fff !important; box-shadow: 0 8px 24px rgba(25, 54, 100, .07) !important; }
div[data-testid="stRadio"] > div { display: flex !important; flex-flow: row nowrap !important; align-items: center !important; justify-content: space-around !important; gap: 8px !important; width: 100% !important; overflow-x: auto !important; }
div[data-testid="stRadio"] label { flex: 0 0 auto !important; white-space: nowrap !important; margin: 0 !important; }
@media (max-width: 650px) { div[data-testid="stRadio"] { padding: 6px 8px !important; } div[data-testid="stRadio"] > div { justify-content: flex-start !important; gap: 6px !important; } div[data-testid="stRadio"] label { padding: 6px 9px !important; font-size: 11px !important; } }
</style>
""",
    unsafe_allow_html=True,
)


# ----------------------------- Image and header -----------------------------

logo_data = None
for candidate in LOGO_CANDIDATES:
    try:
        if candidate.is_file():
            logo_data = base64.b64encode(candidate.read_bytes()).decode("ascii")
            break
    except OSError:
        pass

logo_html = (
    f'<img src="data:image/png;base64,{logo_data}" alt="RailConnect logo">'
    if logo_data else "R"
)

image_data = None
for candidate in IMAGE_CANDIDATES:
    try:
        if candidate.is_file():
            image_data = base64.b64encode(candidate.read_bytes()).decode("ascii")
            break
    except OSError:
        pass

if image_data:
    hero_image_html = (
        '<img class="hero-image" alt="Vande Bharat train" '
        f'src="data:image/png;base64,{image_data}">'
    )
else:
    hero_image_html = ""

st.html(
    f"""
<div class="advisory">
    <b>Travel Advisory:</b>
    Verify train timings and operations before travelling.
    Always check NTES and the Official Railway Website.
</div>
<div class="navbar">
    <div class="brand">
        <div class="brand-mark">{logo_html}</div>
        <div>
            <div class="brand-name">RailConnect</div>
            <div class="brand-sub">EVERY JOURNEY, CONNECTED</div>
        </div>
    </div>
    <div class="nav-right">
        <span>WELCOME</span>
        <a href="mailto:par305065@gmail.com?subject=RailConnect%20Help%20or%20Suggestion">Help / Suggestions</a>
    </div>
</div>
"""
)

if "railconnect_page" not in st.session_state:
    st.session_state.railconnect_page = "Train Search"

# Keep the branded hero on every page; place the page selector directly beneath it.
st.html(
    f"""
<div class="hero">
    {hero_image_html}
    <div class="hero-copy">
        <div class="hero-kicker">A smarter way to travel</div>
        <h1>Every Journey,<br><span>Connected.</span></h1>
        <p>Find direct trains and connecting routes across India. Compare journey durations, transfers and distances in one clear place.</p>
        <div class="hero-note">Plan your route · Compare journey options</div>
    </div>
</div>
"""
)
if not image_data:
    st.warning(
        "Vande Bharat image could not be loaded. Confirm that "
        f"assets/{IMAGE_NAME} exists in the GitHub repository on the deployed branch. "
        "Image paths are case-sensitive on Streamlit Cloud."
    )

st.radio(
    "Choose a page",
    options=["Train Search", "Train Availability", "Live Train Status", "PNR Search"],
    key="railconnect_page", horizontal=True, label_visibility="collapsed",
)


# ----------------------------- Session state -----------------------------

defaults = {
    "source_station_label": None, "destination_station_label": None,
    "rail_search_results": None, "rail_search_query": None, "rail_search_status": "idle",
}
for key, value in defaults.items():
    if key not in st.session_state:
        st.session_state[key] = value


def swap_stations():
    source = st.session_state.get("source_station_label")
    destination = st.session_state.get("destination_station_label")
    st.session_state.source_station_label = destination
    st.session_state.destination_station_label = source


# ----------------------------- Formatting helpers -----------------------------

def safe(value):
    return html.escape(str(value if value is not None else ""))


def format_duration(minutes):
    try:
        minutes = max(0, int(minutes))
    except (TypeError, ValueError):
        return "Not available"
    hours, remaining = divmod(minutes, 60)
    return f"{hours:02d} h {remaining:02d} m"


def format_pnr_duration(value):
    if value is None or str(value).strip() == "":
        return "Not available"
    import re
    text_value = str(value).strip()
    match = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", text_value)
    if match:
        total_hours, minutes = int(match.group(1)), int(match.group(2))
        return f"{total_hours + minutes // 60}h {minutes % 60}m"
    unit_match = re.fullmatch(
        r"\s*(?:(\d+)\s*d(?:ays?)?\s*)?(?:(\d+)\s*h(?:ours?)?\s*)?"
        r"(?:(\d+)\s*m(?:in(?:utes?)?)?\s*)?(?:(\d+)\s*s(?:ec(?:onds?)?)?\s*)?",
        text_value, re.IGNORECASE,
    )
    if unit_match and any(part is not None for part in unit_match.groups()):
        days, hours, minutes, _seconds = (int(part or 0) for part in unit_match.groups())
        total_hours, remaining_minutes = divmod(days * 24 * 60 + hours * 60 + minutes, 60)
        return f"{total_hours}h {remaining_minutes}m"
    try:
        total_hours, remaining_minutes = divmod(max(0, int(float(text_value))), 60)
        return f"{total_hours}h {remaining_minutes}m"
    except (TypeError, ValueError):
        return text_value


def pnr_arrival_date(journey_date, departure_time, arrival_time, duration_value=None):
    import re
    if not journey_date or str(journey_date).strip().upper() in {"N/A", "NA", "NONE"}:
        return "N/A"
    date_text = str(journey_date).strip()
    parsed_date = None
    for fmt in ("%d-%m-%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d %b %Y"):
        try:
            parsed_date = datetime.strptime(date_text, fmt).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        return date_text

    def clock_minutes(value):
        match = re.search(r"(\d{1,2}):(\d{2})", str(value or ""))
        if not match:
            return None
        hour, minute = int(match.group(1)), int(match.group(2))
        return None if hour > 23 or minute > 59 else hour * 60 + minute

    departure, arrival = clock_minutes(departure_time), clock_minutes(arrival_time)
    duration_match = re.fullmatch(r"(\d+):(\d{1,2})(?::(\d{1,2}))?", str(duration_value or "").strip())
    if duration_match:
        total_minutes = int(duration_match.group(1)) * 60 + int(duration_match.group(2))
        if departure is not None:
            return (parsed_date + timedelta(days=(departure + total_minutes) // 1440)).strftime("%d-%m-%Y")
    if departure is not None and arrival is not None:
        return (parsed_date + timedelta(days=1 if arrival < departure else 0)).strftime("%d-%m-%Y")
    return parsed_date.strftime("%d-%m-%Y")


def format_distance(distance):
    if distance is None or distance == "":
        return "Not available"
    try:
        return f"{float(distance):,.0f} km"
    except (TypeError, ValueError):
        return "Not available"


def format_clock(minutes):
    hour, minute = divmod(int(minutes) % 1440, 60)
    return f"{hour:02d}:{minute:02d}"


def format_date_time(minutes, start_date):
    actual_date = start_date + timedelta(days=int(minutes) // 1440)
    return f"{actual_date:%d-%m-%Y}"


def station_display(name, code):
    station_name, station_code = str(name or "").strip(), str(code or "").strip()
    if station_name and station_code:
        if station_name.upper().endswith(f"({station_code.upper()})"):
            return station_name
        return f"{station_name} ({station_code})"
    return station_name or station_code or "Station not available"


def train_display_name(leg):
    name, number = str(leg.get("name") or "Train").strip(), str(leg.get("number") or "").strip()
    if not number or name.endswith(f"({number})"):
        return name
    return f"{name} ({number})"


def _render_journey_seat_availability(journey, number, selected_date):
    legs = journey.get("legs", [])
    changes = int(journey.get("changes", len(legs) - 1))
    if not st.button("Show seat availability", key=f"journey_seats_{changes}_{number}", use_container_width=False):
        return
    if not legs:
        st.info("No train legs were found for this journey.")
        return
    _inject_availability_styles()
    with st.spinner("Fetching live seat availability for this journey..."):
        for leg_index, leg in enumerate(legs, start=1):
            train_name = train_display_name(leg)
            train_number = str(leg.get("number") or "").strip()
            source_value, destination_value = leg.get("source", ""), leg.get("destination", "")
            source_label = str(leg.get("source_name") or source_value or "")
            destination_label = str(leg.get("destination_name") or destination_value or "")
            source_code = _availability_station_code(source_label, source_value)
            destination_code = _availability_station_code(destination_label, destination_value)
            departure_minutes = int(leg.get("departure", 0))
            leg_date = selected_date + timedelta(days=max(0, departure_minutes // 1440))
            st.markdown(f"**Train {leg_index}: {safe(train_name)}**")
            st.caption(f"{safe(source_label)} ({safe(source_code or 'code unavailable')}) to {safe(destination_label)} ({safe(destination_code or 'code unavailable')})")
            try:
                result = _call_live_availability(source_code, destination_code, leg_date, "All classes", "GN")
                trains = result.get("trains") or []
                matching_train = None
                if train_number:
                    normalized_number = "".join(ch for ch in train_number if ch.isdigit())
                    for candidate in trains:
                        candidate_number = str(_availability_first(candidate, "trainNumber", "trainNo", "number", "train_number", default=""))
                        candidate_number = "".join(ch for ch in candidate_number if ch.isdigit())
                        if normalized_number and candidate_number == normalized_number:
                            matching_train = candidate
                            break
                if matching_train is None:
                    st.info("Live availability was fetched, but the selected train could not be matched to a result for this exact station pair and date.")
                    continue
                availability = matching_train.get("availabilityCache") or matching_train.get("availability") or matching_train.get("classes")
                if not isinstance(availability, dict) or not availability:
                    st.info("The provider did not include class-wise seat availability for this train.")
                    continue
                with st.container(border=True):
                    st.markdown("**Seat availability by class (General quota)**")
                    columns = st.columns(min(len(availability), 5))
                    for index, (class_code, details) in enumerate(availability.items()):
                        if isinstance(details, dict):
                            status = _availability_first(details, "availability", "status", "availablityStatus", "state", "text", default="Status not supplied")
                            fare = _availability_first(details, "fare", "totalFare", "amount", default=None)
                        else:
                            status, fare = details, None
                        with columns[index % len(columns)]:
                            status_class = _availability_status_class(status)
                            status_label = _availability_status_label(status)
                            fare_html = f'<div class="availability-fare">₹{safe(str(fare))}</div>' if fare is not None else ""
                            st.markdown(f'<div class="availability-class-card"><div class="availability-class-code">{safe(str(class_code))}</div><span class="availability-status {safe(status_class)}">{safe(str(status_label))}</span>{fare_html}</div>', unsafe_allow_html=True)
                st.caption(f"Availability fetched for {leg_date:%d-%m-%Y}.")
            except Exception as exc:
                st.warning(f"Could not fetch availability for {train_name}: {exc}")


def category_name(changes):
    if changes == 0:
        return "DIRECT TRAIN"
    if changes == 1:
        return "1 INTERCHANGE"
    return f"{changes} INTERCHANGES"


def journey_signature(journey):
    return tuple((str(leg.get("number", "")).strip(), str(leg.get("source", "")).strip().upper(),
                  str(leg.get("destination", "")).strip().upper(), int(leg.get("departure", 0)),
                  int(leg.get("arrival", 0))) for leg in journey.get("legs", []))


def deduplicate_journeys(journeys):
    unique, seen = [], set()
    for journey in journeys or []:
        signature = journey_signature(journey)
        if not signature or signature in seen:
            continue
        seen.add(signature)
        unique.append(journey)
    return unique


def running_day_markup(leg):
    raw = leg.get("runningDays", leg.get("runs_days", leg.get("running_days", leg.get("running_days_text", ""))))
    value = str(raw or "").strip().lower()
    day_names = ["M", "T", "W", "T", "F", "S", "S"]
    full_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    aliases = [("mon", "monday"), ("tue", "tuesday"), ("wed", "wednesday"), ("thu", "thursday"),
               ("fri", "friday"), ("sat", "saturday"), ("sun", "sunday")]
    active = [False] * 7
    if value in ("daily", "everyday", "every day", "all days"):
        active = [True] * 7
    elif len(value) == 7 and set(value) <= {"0", "1"}:
        active = [character == "1" for character in value]
    else:
        for index, alias_group in enumerate(aliases):
            active[index] = any(alias in value for alias in alias_group)
    circles = []
    for index, day in enumerate(day_names):
        active_class = " active" if active[index] else ""
        circles.append(f'<span class="day-circle{active_class}" title="{full_names[index]}">{day}</span>')
    return '<div class="day-row">' + "".join(circles) + "</div>"


# ----------------------------- Route cards -----------------------------

def render_journey(journey, number, selected_date):
    legs = journey.get("legs", [])
    if not legs:
        return
    departure = int(journey.get("departure", legs[0]["departure"]))
    arrival = int(journey.get("arrival", legs[-1]["arrival"]))
    duration = max(0, arrival - departure)
    changes = int(journey.get("changes", len(legs) - 1))
    distance = journey.get("distance_km")
    first_leg, last_leg = legs[0], legs[-1]
    source_station = station_display(first_leg.get("source_name", first_leg.get("source", "")), first_leg.get("source", ""))
    destination_station = station_display(last_leg.get("destination_name", last_leg.get("destination", "")), last_leg.get("destination", ""))
    train_names_html = "".join(f'<div class="train-name-line">Train {index + 1} - {safe(train_display_name(leg))}</div>' for index, leg in enumerate(legs))
    st.html(f"""
<div class="train-card">
    <div><div class="train-names">{train_names_html}</div><div class="route-tag">{category_name(changes)}</div></div>
    <div><div class="time">{format_clock(departure)}</div><div class="station">{safe(source_station)}</div><div class="date-small">{format_date_time(departure, selected_date)}</div></div>
    <div class="route-middle"><div class="duration">{format_duration(duration)}</div><div class="timeline"></div><div class="distance-value">{format_distance(distance)}</div><div class="changes">{"NON-STOP" if changes == 0 else f"{changes} CHANGE(S)"}</div></div>
    <div><div class="time">{format_clock(arrival)}</div><div class="station">{safe(destination_station)}</div><div class="date-small">{format_date_time(arrival, selected_date)}</div></div>
    <div class="train-action">{running_day_markup(first_leg)}<div class="route-tag">Journey option {number}</div></div>
</div>
""")
    _render_journey_seat_availability(journey, number, selected_date)
    with st.expander("View train schedule and connection details", expanded=(number == 1)):
        for index, leg in enumerate(legs):
            leg_departure, leg_arrival = int(leg["departure"]), int(leg["arrival"])
            leg_duration = leg_arrival - leg_departure
            leg_source = station_display(leg.get("source_name", leg.get("source", "")), leg.get("source", ""))
            leg_destination = station_display(leg.get("destination_name", leg.get("destination", "")), leg.get("destination", ""))
            leg_train_name = train_display_name(leg)
            with st.container(border=True):
                st.html(f'<div class="leg-title">Train {index + 1} - {safe(leg_train_name)}</div>')
                st.html(f"""
<div class="leg-route">
    <div class="leg-end"><div class="leg-caption">DEPARTURE</div><div class="leg-time">{format_clock(leg_departure)}</div><div class="leg-station">{safe(leg_source)}</div><div class="leg-date">{format_date_time(leg_departure, selected_date)}</div></div>
    <div class="leg-track"><div class="leg-summary-duration">{format_duration(leg_duration)}</div><div class="leg-timeline"></div><div class="leg-summary-distance">{format_distance(leg.get("distance_km"))}</div></div>
    <div class="leg-end arrival"><div class="leg-caption">ARRIVAL</div><div class="leg-time">{format_clock(leg_arrival)}</div><div class="leg-station">{safe(leg_destination)}</div><div class="leg-date">{format_date_time(leg_arrival, selected_date)}</div></div>
</div>
""")
            if index < len(legs) - 1:
                next_leg = legs[index + 1]
                next_departure = int(next_leg["departure"])
                wait = next_departure - leg_arrival
                change_station = station_display(leg.get("destination_name", leg.get("destination", "")), leg.get("destination", ""))
                incoming_train_label = f"Train {index + 1} - {train_display_name(leg)}"
                connecting_train_label = f"Train {index + 2} - {train_display_name(next_leg)}"
                if wait < 0:
                    st.error("The next train appears to depart before the previous train arrives. Please verify the timetable data.")
                else:
                    st.html(f"""
<div class="transfer">
    <div class="transfer-title">Interchange at {safe(change_station)}</div>
    <div><b>Incoming train:</b> {safe(incoming_train_label)}</div><div><b>Connecting train:</b> {safe(connecting_train_label)}</div>
    <div class="transfer-grid">
        <div class="transfer-item"><div class="transfer-label">ARRIVAL</div><div class="transfer-value">{format_clock(leg_arrival)}</div><div class="transfer-value">{format_date_time(leg_arrival, selected_date)}</div><div class="transfer-train">{safe(incoming_train_label)}</div></div>
        <div class="transfer-item"><div class="transfer-label">NEXT DEPARTURE</div><div class="transfer-value">{format_clock(next_departure)}</div><div class="transfer-value">{format_date_time(next_departure, selected_date)}</div><div class="transfer-train">{safe(connecting_train_label)}</div></div>
    </div>
    <div class="transfer-wait"><span class="transfer-wait-label">Waiting time</span><span>{format_duration(wait)}</span></div>
</div>
""")
        if journey.get("short_transfer_warning"):
            st.warning("This route contains a transfer shorter than the requested minimum. Verify the connection carefully.")
        threshold = journey.get("transfer_threshold_used")
        if threshold is not None and threshold < 30:
            st.caption(f"The route was found after relaxing the minimum transfer time to {threshold} minutes.")


if st.session_state.railconnect_page == "Train Search":
    if st.session_state.rail_search_status != "complete" or st.session_state.rail_search_results is None:
        st.html('<div class="section-heading">Find your train route</div>')
        st.html('<div class="section-subtitle">Select your stations and travel date to explore direct and connecting journeys.</div>')
        with st.container(border=True):
            source_col, swap_col, destination_col = st.columns([5, 0.8, 5], vertical_alignment="bottom")
            with source_col:
                source_label = st.selectbox("From", options=station_labels, index=None, placeholder="Select departure station", key="source_station_label")
            with swap_col:
                st.button("⇄", key="swap_stations_button", help="Swap departure and destination", on_click=swap_stations, use_container_width=True)
            with destination_col:
                destination_label = st.selectbox("To", options=station_labels, index=None, placeholder="Select destination station", key="destination_station_label")
            date_col, period_col = st.columns(2)
            with date_col:
                journey_date = st.date_input("Journey date", value=date.today(), min_value=date.today(), format="DD/MM/YYYY", key="journey_date")
            with period_col:
                departure_period = st.selectbox("Departure period", options=["All times", "Morning", "Afternoon", "Evening", "Night"], index=0, key="departure_period")
            search_clicked = st.button("Search Trains  →", type="primary", use_container_width=False)
        if search_clicked:
            if not source_label or not destination_label:
                st.warning("Please select both departure and destination stations.")
            else:
                source, destination = stations[source_label], stations[destination_label]
                if source == destination:
                    st.warning("Choose two different stations.")
                else:
                    actual_period = "All" if departure_period == "All times" else departure_period
                    st.session_state.rail_search_query = {"source_label": source_label, "destination_label": destination_label, "journey_date": journey_date, "departure_period": departure_period}
                    st.session_state.rail_search_results = None
                    st.session_state.rail_search_status = "idle"
                    try:
                        with st.spinner("Finding direct and connecting journeys..."):
                            results = find_journeys(data=data, source=source, destination=destination, journey_date=journey_date, max_changes=2, min_transfer=30, departure_period=actual_period)
                        st.session_state.rail_search_results = deduplicate_journeys(results)
                        st.session_state.rail_search_status = "complete"
                        st.rerun()
                    except Exception as exc:
                        st.session_state.rail_search_results = None
                        st.session_state.rail_search_query = None
                        st.session_state.rail_search_status = "idle"
                        st.error(f"Route search failed: {exc}")
                        st.exception(exc)

    if st.session_state.rail_search_status == "complete" and st.session_state.rail_search_results is not None and st.session_state.rail_search_query is not None:
        query, results = st.session_state.rail_search_query, st.session_state.rail_search_results
        selected_date, selected_period = query["journey_date"], query["departure_period"]
        if st.button("← Back to Search", key="back_to_search"):
            st.session_state.rail_search_results = None
            st.session_state.rail_search_query = None
            st.session_state.rail_search_status = "idle"
            st.rerun()
        st.html('<div class="section-heading">Available journey options</div>')
        st.html(f'<div class="section-subtitle">{safe(query["source_label"])} to {safe(query["destination_label"])} · {selected_date:%d-%m-%Y} · Departure: {safe(selected_period)}</div>')
        if not results:
            st.warning("No routes were found for the selected stations and departure period. Try another date or departure period.")
        else:
            direct = [j for j in results if j.get("changes", len(j.get("legs", [])) - 1) == 0]
            one_change = [j for j in results if j.get("changes", len(j.get("legs", [])) - 1) == 1]
            two_changes = [j for j in results if j.get("changes", len(j.get("legs", [])) - 1) == 2]
            st.html(f'<div class="results-summary"><b>{len(results)} routes found</b> · {len(direct)} direct · {len(one_change)} with one interchange · {len(two_changes)} with two interchanges</div>')
            for title, journeys, description in [("Direct trains", direct, "Travel without changing trains."), ("One interchange", one_change, "Routes with one train change."), ("Two interchanges", two_changes, "Routes with two train changes.")]:
                if not journeys:
                    continue
                st.html(f'<div class="section-heading" style="font-size:20px">{safe(title)}</div><div class="section-subtitle">{safe(description)}</div>')
                for number, journey in enumerate(journeys, start=1):
                    render_journey(journey, number, selected_date)


if st.session_state.railconnect_page == "PNR Search":
    st.html("""
<div class="pnr-hero"><div class="pnr-eyebrow">RailConnect · Reservation enquiry</div><div class="pnr-title">Check your PNR status</div><div class="pnr-description">Get your reservation details, journey information and passenger status in one clear view. Enter the 10-digit PNR printed on your ticket.</div></div>
""")
    with st.container(border=True):
        st.html('<div class="pnr-panel-title">Find your reservation</div>')
        pnr_number = st.text_input("10-digit PNR number", max_chars=10, placeholder="e.g. 1234567890", help="Enter the PNR printed on your railway ticket.", key="railconnect_pnr_input").strip()
        pnr_valid = len(pnr_number) == 10 and pnr_number.isdigit()
        search_col, hint_col = st.columns([1, 3])
        with search_col:
            pnr_search_clicked = st.button("Search PNR  →", type="primary", use_container_width=True, key="railconnect_pnr_search_button")
        with hint_col:
            if pnr_number and not pnr_valid:
                st.caption("Enter all 10 digits to search your PNR.")
        if pnr_search_clicked:
            if not pnr_valid:
                st.error("Please enter a valid 10-digit PNR number.")
            else:
                st.session_state.pnr_last_queried = pnr_number
                st.session_state.pnr_cached_result = None
                st.session_state.pnr_cached_error = None
                try:
                    with st.spinner("Fetching your reservation details..."):
                        st.session_state.pnr_cached_result = get_pnr_status(pnr_number)
                except Exception as exc:
                    st.session_state.pnr_cached_error = str(exc)
        if pnr_valid and st.session_state.get("pnr_last_queried") == pnr_number:
            if st.session_state.get("pnr_cached_error"):
                st.error(f"Could not retrieve PNR status: {st.session_state.pnr_cached_error}")
                st.info("The PNR layout is ready, but live status depends on a successful response from the configured data provider.")
            else:
                try:
                    pnr_result = st.session_state.get("pnr_cached_result")
                    if isinstance(pnr_result, str):
                        pnr_result = json.loads(pnr_result)
                    pnr_data = pnr_result.get("data", {}).get("pnrResponse") if isinstance(pnr_result, dict) and isinstance(pnr_result.get("data", {}), dict) else None
                    if pnr_data is None and isinstance(pnr_result, dict):
                        pnr_data = pnr_result.get("pnrResponse")
                    if not isinstance(pnr_data, dict):
                        st.error("PNR data was not found in the provider response.")
                        st.caption("The provider response did not contain the expected data.pnrResponse information.")
                    else:
                        st.success("Reservation information retrieved successfully.")
                        train_name, train_no = pnr_data.get("trainName") or "Train details", pnr_data.get("trainNo") or "N/A"
                        shown_pnr = pnr_data.get("pnr") or pnr_number
                        st.html(f'<div class="pnr-train-banner"><div class="pnr-route-label">TRAIN DETAILS</div><div class="pnr-train-name">{safe(train_name)}</div><div class="pnr-train-number">TRAIN NO. {safe(train_no)}</div><div class="pnr-meta-pill">PNR: {safe(shown_pnr)}</div><div class="pnr-meta-pill">Journey: {safe(pnr_data.get("doj") or "N/A")}</div><div class="pnr-meta-pill">Class: {safe(pnr_data.get("class") or "N/A")}</div><div class="pnr-meta-pill">Quota: {safe(pnr_data.get("quota") or "N/A")}</div></div>')
                        st.html('<div class="pnr-panel-title">Journey overview</div>')
                        source_name = pnr_data.get("sourceName") or pnr_data.get("from") or "N/A"
                        destination_name = pnr_data.get("destinationName") or pnr_data.get("to") or "N/A"
                        departure_time, arrival_time = pnr_data.get("departureTime") or "N/A", pnr_data.get("arrivalTime") or "N/A"
                        duration = format_pnr_duration(pnr_data.get("duration"))
                        journey_date = pnr_data.get("doj") or pnr_data.get("journeyDate") or "N/A"
                        departure_date = pnr_data.get("departureDate") or journey_date
                        arrival_date = pnr_arrival_date(departure_date, departure_time, arrival_time, pnr_data.get("duration"))
                        boarding = pnr_data.get("boardingStationName") or "N/A"
                        st.html(f'<div class="pnr-route-box"><div><div class="pnr-route-label">FROM</div><div class="pnr-route-station">{safe(source_name)}</div><div class="pnr-route-time">Departure · {safe(departure_time)}</div><div class="pnr-route-date">{safe(departure_date)}</div></div><div class="pnr-route-middle"><div class="pnr-route-duration">{safe(duration)}</div><div class="pnr-route-line"></div><div class="pnr-route-label">YOUR JOURNEY</div></div><div><div class="pnr-route-label">TO</div><div class="pnr-route-station">{safe(destination_name)}</div><div class="pnr-route-time">Arrival · {safe(arrival_time)}</div><div class="pnr-route-date">{safe(arrival_date)}</div></div></div>')
                        st.caption(f"Boarding station: {boarding}")
                        st.html('<div class="pnr-panel-title">Passenger status</div>')
                        passengers = pnr_data.get("passengerStatus") or []
                        if passengers:
                            for index, passenger in enumerate(passengers, start=1):
                                passenger_number = passenger.get("number") or index
                                current_status = passenger.get("currentStatus") or passenger.get("bookingStatus") or "Not available"
                                coach = passenger.get("currentCoachId") or passenger.get("bookingCoachId") or passenger.get("coach") or ""
                                berth = passenger.get("currentBerthNo") or passenger.get("bookingBerthNo") or passenger.get("berth") or ""
                                prediction = passenger.get("prediction") or "N/A"
                                with st.container(border=True):
                                    st.html(f'<div class="pnr-passenger-heading">Passenger {safe(passenger_number)}</div>')
                                    passenger_col1, passenger_col2, passenger_col3 = st.columns(3)
                                    with passenger_col1:
                                        st.caption("CURRENT STATUS")
                                        st.html(f'<span class="pnr-status-pill">{safe(current_status)}</span>')
                                    with passenger_col2:
                                        st.caption("COACH / BERTH")
                                        st.markdown(f"**{safe(coach or 'Not assigned')}**" + (f" / **{safe(berth)}**" if berth else ""))
                                    with passenger_col3:
                                        st.caption("PREDICTION")
                                        st.write(prediction)
                        else:
                            st.info("The provider did not return passenger status details.")
                        st.html('<div class="pnr-panel-title">Additional information</div>')
                        info_col1, info_col2, info_col3 = st.columns(3)
                        chart_prepared = pnr_data.get("chartPrepared")
                        chart_text = "Yes" if chart_prepared is True else "No" if chart_prepared is False else "Not available"
                        fare = pnr_data.get("ticketFare") or pnr_data.get("bookingFare")
                        with info_col1: st.metric("Chart prepared", chart_text)
                        with info_col2: st.metric("Expected platform", pnr_data.get("expectedPlatformNo") or "N/A")
                        with info_col3: st.metric("Ticket fare", f"₹{fare}" if fare is not None else "N/A")
                        st.html('<div class="pnr-help-note">PNR information can change. Please verify the latest reservation status with official Indian Railways sources before travelling.</div>')
                except Exception as exc:
                    st.error(f"Could not retrieve PNR status: {exc}")
                    st.info("The PNR layout is ready, but live status depends on a successful response from the configured data provider.")


def _ntes_text(node) -> str:
    """Return compact visible text from a BeautifulSoup node."""
    return " ".join(node.stripped_strings) if node else ""


def _parse_ntes_running_status(page_html: str, train_number: str, running_date: date) -> dict:
    """Parse the NTES HTML response for one requested running-date tab."""
    from bs4 import BeautifulSoup
    import re
    if not page_html or not page_html.strip():
        raise RuntimeError(
            "NTES returned an empty response for the running-status request. "
            "The site may be temporarily unavailable or blocking automated requests. "
            "No timetable fallback was used."
        )
    soup = BeautifulSoup(page_html, "html.parser")
    tab_id = f"train{running_date.day}-{running_date.strftime('%b').lower()}-{running_date.year}"
    tab = soup.find(id=tab_id)
    if tab is None:
        wanted = tab_id.lower()
        tab = next((el for el in soup.find_all(id=True) if str(el.get("id", "")).lower() == wanted), None)
    if tab is None:
        page_title = _ntes_text(soup.title) if soup.title else "(no page title)"
        date_panel_ids = [str(el.get("id")) for el in soup.find_all(id=True) if re.fullmatch(r"train\d{1,2}-[a-z]{3}-\d{4}", str(el.get("id", "")), re.I)]
        stop_row_count = len(soup.select(".stopRow"))
        form_names = [str(form.get("name") or form.get("id") or "unnamed") for form in soup.find_all("form")[:8]]
        body_preview = _ntes_text(soup.body or soup)[:700]
        raise RuntimeError(
            "NTES LIVE-STATUS DIAGNOSTIC: requested panel not found. "
            f"Requested panel ID={tab_id!r}; HTTP page title={page_title!r}; "
            f"date panels={date_panel_ids or 'none'}; station rows={stop_row_count}; "
            f"forms={form_names or 'none'}; response preview={body_preview!r}. "
            "The site may have returned a generic page, a session/redirect page, or changed its HTML."
        )
    title_node = tab.select_one("header h5")
    title = _ntes_text(title_node).split(" Average Delay")[0].strip() if title_node else "Train running status"
    title = re.sub(r"\s+Average Delay.*$", "", title, flags=re.I).strip()
    rows = []
    for row in tab.select(".stopRow"):
        direct_divs = row.find_all("div", recursive=False)
        if len(direct_divs) < 3:
            continue
        arrival_col, center_col = direct_divs[0], direct_divs[2]
        center_divs = center_col.find_all("div", recursive=False)
        station_col = next((div for div in center_divs if "flex:1" in str(div.get("style", "")).replace(" ", "")), center_divs[0] if center_divs else center_col)
        departure_col = next((div for div in center_divs if "text-align:right" in str(div.get("style", ""))), None)
        station_name_node = station_col.find("b") if station_col else None
        station_name = _ntes_text(station_name_node) if station_name_node else ""
        station_code = ""
        code_container = station_col.select_one("div div") if station_col else None
        if code_container:
            match = re.match(r"([A-Z0-9]{2,6})\b", _ntes_text(code_container))
            if match:
                station_code = match.group(1)
        platform = ""
        for badge in station_col.select(".w3-round") if station_col else []:
            badge_text = _ntes_text(badge)
            if re.search(r"\bPF\s*\w+", badge_text, re.I):
                platform = re.sub(r"\s+", " ", badge_text)
                break

        def time_pair(column):
            if not column:
                return "", "", ""
            spans = column.find_all("span", recursive=False)
            if len(spans) < 2:
                spans = column.find_all("span")[:2]
            scheduled = _ntes_text(spans[0].find("b") or spans[0]) if spans else ""
            reported = _ntes_text(spans[1].find("b") or spans[1]) if len(spans) > 1 else ""
            badge_text = ""
            if len(spans) > 1:
                for badge in spans[1].select(".w3-round"):
                    badge_text = _ntes_text(badge)
                    if badge_text:
                        break
            if not badge_text:
                for badge in column.select(".w3-round"):
                    badge_text = _ntes_text(badge)
                    if badge_text:
                        break
            return scheduled, reported, badge_text

        scheduled_arrival, reported_arrival, arrival_status = time_pair(arrival_col)
        scheduled_departure, reported_departure, departure_status = time_pair(departure_col)
        distance_match = re.search(r"\b(\d{1,4})\s*KMs?\b", _ntes_text(station_col), re.I)
        distance_km = distance_match.group(1) if distance_match else ""
        if station_name:
            rows.append({
                "station": station_name, "station_code": station_code, "platform": platform,
                "distance_km": distance_km, "scheduled_arrival": scheduled_arrival,
                "reported_arrival": reported_arrival, "arrival_status": arrival_status,
                "scheduled_departure": scheduled_departure, "reported_departure": reported_departure,
                "departure_status": departure_status,
            })
    # NTES often renders non-stopping locations as plain text between the normal
    # .stopRow elements rather than as schedule rows or a JSON field. Extract only
    # explicit NAME - CODE / NAME (CODE) station labels from that DOM and attach
    # each one to the preceding scheduled halt. Never create station names.
    stop_rows_dom = list(tab.select(".stopRow"))
    station_label_re = re.compile(
        r"^\s*([A-Z][A-Z0-9 ./'()-]{1,70}?)\s*(?:[-–—]|\()\s*([A-Z0-9]{2,6})\)?\s*$",
        re.I,
    )
    seen_nonstop = set()
    for text_node in tab.find_all(string=True):
        label = re.sub(r"\s+", " ", str(text_node)).strip()
        if not label or len(label) > 100:
            continue
        match = station_label_re.match(label)
        if not match:
            continue
        parent = text_node.parent
        # Ignore any station label already inside a normal stopping row.
        if parent and parent.find_parent(class_="stopRow") is not None:
            continue
        station_name, station_code = match.group(1).strip(" -–—("), match.group(2).upper()
        # Exclude headings and duplicate appearances of the same DOM label.
        if not station_name or station_name.lower() in {"non-stopping stations", "stopping stations"}:
            continue
        previous_row = parent.find_previous(class_="stopRow") if parent else None
        if previous_row is None:
            continue
        try:
            owner_index = stop_rows_dom.index(previous_row)
        except ValueError:
            continue
        identity = (owner_index, station_code)
        if identity in seen_nonstop:
            continue
        seen_nonstop.add(identity)
        if owner_index >= len(rows):
            continue
        rows[owner_index].setdefault("intermediate_stations", []).append({
            "station": station_name, "station_code": station_code, "is_passing": True
        })

    if not rows:
        raise RuntimeError("NTES returned a page, but no station rows could be extracted. The page format may have changed; no timetable fallback was used.")
    page_text = _ntes_text(tab)
    journey_state = next((phrase for phrase in ("Yet to start from its source", "Train has arrived", "Train has been diverted", "Cancelled") if phrase.lower() in page_text.lower()), "")
    return {
        "train_number": train_number, "train_name": title or "Train running status",
        "running_date": running_date.isoformat(), "fetched_at": datetime.now().strftime("%d %b %Y, %I:%M:%S %p"),
        "journey_state": journey_state, "stations": rows, "source": "NTES (National Train Enquiry System)",
    }


def _fetch_live_train_status(params: dict) -> dict:
    """Fetch NTES status, falling back to NTES train-instance metadata.

    The unofficial client has returned successful but differently-shaped payloads
    for some trains. Normalize common field names and use train_info() as a fallback
    before declaring that no status is available. Never fabricate a live location.
    """
    train_number = str(params.get("train_number", "")).strip()
    running_date = date.fromisoformat(str(params["running_date"]))
    if not (train_number.isascii() and train_number.isdigit() and len(train_number) == 5):
        raise RuntimeError("Enter the 5-digit train number (digits only).")

    try:
        from ntes import NTESClient
    except ImportError:
        install_command = [sys.executable, "-m", "pip", "install", "ntes-client"]
        try:
            install_result = subprocess.run(install_command, capture_output=True, text=True, timeout=120, check=False)
        except Exception as exc:
            raise RuntimeError(
                "The NTES client package is missing and automatic installation failed. "
                f'Run this in the same Python environment as Streamlit: "{sys.executable}" -m pip install ntes-client. Details: {exc}'
            ) from exc
        if install_result.returncode != 0:
            details = (install_result.stderr or install_result.stdout or "").strip()[-1200:]
            raise RuntimeError(
                "Could not install ntes-client automatically. Run this in the same environment as Streamlit: "
                f'"{sys.executable}" -m pip install ntes-client. Installer details: {details}'
            )
        try:
            from ntes import NTESClient
        except ImportError as exc:
            raise RuntimeError(
                "ntes-client installation completed but the package still cannot be imported. "
                f'Run "{sys.executable}" -m pip show ntes-client, then restart Streamlit.'
            ) from exc

    client = NTESClient(timeout=20, retries=2)
    formatted_date = running_date.strftime("%d-%b-%Y")
    raw_status = {}
    live_error = None
    try:
        response = client.live_status(train_number, formatted_date)
        if isinstance(response, dict):
            raw_status = response
        elif isinstance(response, list) and response and isinstance(response[0], dict):
            raw_status = response[0]
    except Exception as exc:
        live_error = f"{type(exc).__name__}: {str(exc)[:250]}"

    def clean(value):
        value = str(value or "").strip()
        return "" if value.lower() in {"none", "null", "n/a", "na", "**ua**", "ua", "-"} else value

    def candidates(payload):
        """Return likely payload dictionaries, including common nested wrappers."""
        found = []
        if isinstance(payload, dict):
            found.append(payload)
            for key in ("data", "result", "status", "trainStatus", "response", "TrainRunningStatus"):
                nested = payload.get(key)
                if isinstance(nested, dict):
                    found.append(nested)
                elif isinstance(nested, list):
                    found.extend(item for item in nested if isinstance(item, dict))
        elif isinstance(payload, list):
            found.extend(item for item in payload if isinstance(item, dict))
        return found

    status_candidates = candidates(raw_status)
    def pick(keys):
        for obj in status_candidates:
            for key in keys:
                value = clean(obj.get(key))
                if value:
                    return value
        return ""

    train_name = pick(("TrainName", "trainName", "train_name", "name")) or "Train running status"
    current_station = pick(("CurrentStationName", "currentStationName", "current_station_name", "currentStation", "current_station"))
    current_code = pick(("CurrentStation", "CurrentStationCode", "currentStationCode", "current_station_code", "stationCode"))
    next_station = pick(("NextStationName", "nextStationName", "next_station_name"))
    next_code = pick(("NextStationCode", "nextStationCode", "next_station_code"))
    last_update = pick(("LastUpdate", "lastUpdate", "last_update", "CurrentStatus", "currentStatus", "statusMessage", "message"))
    delay = pick(("DelayDep", "DelayArr", "delay", "delayStatus", "Delay"))
    platform = pick(("Platform", "platform", "PlatformNo", "platformNo"))
    position = pick(("trainPosition", "TrainPosition", "train_position", "position", "TrainStatus", "trainStatus"))

    # The live_status method sometimes returns a sparse response. train_info()
    # includes journey instances and can at least tell us the instance's status.
    instance_status = ""
    instance_date = ""
    instance_name = ""
    info_error = None
    if not any((current_station, current_code, next_station, last_update, delay, position)):
        try:
            info = client.train_info(train_number)
            if isinstance(info, dict):
                instance_name = clean(info.get("TrainName") or info.get("trainName"))
                instances = info.get("vInstanceList") or info.get("instances") or info.get("trainInstances") or []
                if isinstance(instances, dict):
                    instances = [instances]
                target_date = running_date.strftime("%d-%b-%Y").lower()
                for instance in instances if isinstance(instances, list) else []:
                    if not isinstance(instance, dict):
                        continue
                    start_value = clean(instance.get("startDate") or instance.get("StartDate") or instance.get("journeyDate"))
                    normalized_start = start_value.lower()
                    matches = normalized_start == target_date or normalized_start == running_date.isoformat().lower()
                    if not start_value or matches:
                        instance_date = start_value
                        instance_status = clean(
                            instance.get("trainPosition") or instance.get("TrainPosition") or
                            instance.get("trainStatusText") or instance.get("statusText") or
                            instance.get("statusMessage") or instance.get("status")
                        )
                        if not instance_status and instance.get("trainStatus") not in (None, ""):
                            instance_status = f"NTES instance status code: {instance.get('trainStatus')}"
                        if matches or not start_value:
                            break
        except Exception as exc:
            info_error = f"{type(exc).__name__}: {str(exc)[:200]}"

    if not train_name or train_name == "Train running status":
        train_name = instance_name or train_name
    journey_state = last_update or position or instance_status or delay

    # Fetch the complete scheduled route separately from the live-position endpoint.
    normalized_stations = []
    schedule_error = None
    # Diagnostic summary is returned with the result so the UI can show why
    # intermediate stations were not parsed, rather than displaying a vague message.
    railgeo_error = None
    diagnostics = {
        "regular_schedule_rows": 0,
        "railgeo_http_status": None,
        "railgeo_content_type": "",
        "railgeo_response_bytes": 0,
        "railgeo_root_type": "not received",
        "railgeo_route_rows": 0,
        "selected_route_source": "regular NTES schedule",
        "selected_route_rows": 0,
        "sample_station_row_keys": [],
        "parsed_stopping_stations": 0,
        "parsed_passing_rows": 0,
        "attached_intermediate_stations": 0,
        "regular_schedule_error": "",
        "railgeo_error": "",
    }
    try:
        schedule_data = client.schedule(train_number, formatted_date)

        # NTES wrappers vary by train/date and package version. Search known route
        # containers recursively instead of assuming the route is always at data.stations.
        route_container_keys = (
            "stations", "Stations", "stationList", "StationList", "trainSchedule",
            "TrainSchedule", "schedule", "Schedule", "route", "Route", "stops",
            "Stops", "routeStations", "RouteStations", "stationDetails", "StationDetails",
            "routeDetails", "RouteDetails", "stationSequence", "StationSequence",
        )
        def _looks_like_station_record(value):
            if not isinstance(value, dict):
                return False
            keys = {str(key).lower() for key in value}
            return bool(keys.intersection({
                "stationname", "station_name", "station", "name", "stnname",
                "stationcode", "station_code", "code", "stncode",
            }))

        def _find_route_rows(payload, depth=0):
            if depth > 7:
                return []
            if isinstance(payload, list):
                if payload and any(_looks_like_station_record(item) for item in payload):
                    return payload
                for item in payload:
                    found = _find_route_rows(item, depth + 1)
                    if found:
                        return found
                return []
            if not isinstance(payload, dict):
                return []
            # Prefer explicitly named route arrays, preserving source order.
            for key in route_container_keys:
                candidate = payload.get(key)
                if isinstance(candidate, list) and candidate and any(_looks_like_station_record(item) for item in candidate):
                    return candidate
            # Handle wrappers where the route itself is nested one or more levels deep.
            for key in route_container_keys:
                candidate = payload.get(key)
                if isinstance(candidate, (dict, list)):
                    found = _find_route_rows(candidate, depth + 1)
                    if found:
                        return found
            for key in ("data", "result", "response", "payload", "TrainRoute", "trainRoute"):
                candidate = payload.get(key)
                if isinstance(candidate, (dict, list)):
                    found = _find_route_rows(candidate, depth + 1)
                    if found:
                        return found
            return []

        route_rows = _find_route_rows(schedule_data)
        diagnostics["regular_schedule_rows"] = len(route_rows)

        # NTES's normal train schedule often contains halting stations only.
        # Its separate RailGeo schedule endpoint has historically exposed the
        # ordered route sequence, including stations passed without a halt.
        # Try that source as well and prefer it when it returns a longer route.
        railgeo_data = None
        railgeo_rows = []
        railgeo_error = None
        try:
            railgeo_url = "https://enquiry.indianrail.gov.in/ntes/RailGeo"
            railgeo_response = requests.get(
                railgeo_url,
                params={
                    "action": "getTrainSchedule",
                    "trainNo": train_number,
                    "trainStartDate": running_date.strftime("%-d %b %Y") if os.name != "nt" else running_date.strftime("%#d %b %Y"),
                },
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
                    "Accept": "application/json, text/plain, */*",
                    "Referer": "https://enquiry.indianrail.gov.in/ntes/",
                },
                timeout=18,
            )
            diagnostics["railgeo_http_status"] = railgeo_response.status_code
            diagnostics["railgeo_content_type"] = str(railgeo_response.headers.get("Content-Type", ""))
            diagnostics["railgeo_response_bytes"] = len(railgeo_response.content or b"")
            railgeo_response.raise_for_status()
            try:
                railgeo_data = railgeo_response.json()
            except Exception:
                # Some NTES responses wrap JSON in a text/HTML response.
                response_text = railgeo_response.text.strip()
                json_match = re.search(r"(?:var\s+\w+\s*=\s*)?(\[.*\]|\{.*\})\s*;?\s*$", response_text, re.S)
                if json_match:
                    railgeo_data = json.loads(json_match.group(1))
            if railgeo_data is not None:
                diagnostics["railgeo_root_type"] = type(railgeo_data).__name__
                railgeo_rows = _find_route_rows(railgeo_data)
                diagnostics["railgeo_route_rows"] = len(railgeo_rows)
        except Exception as exc:
            railgeo_error = f"{type(exc).__name__}: {str(exc)[:180]}"
            diagnostics["railgeo_error"] = railgeo_error

        # Prefer the all-stations RailGeo sequence if it is more complete than
        # the regular schedule response. Keep the original source order.
        if railgeo_rows and len(railgeo_rows) > len(route_rows):
            route_rows = railgeo_rows
            schedule_data = railgeo_data
            diagnostics["selected_route_source"] = "NTES RailGeo"
        diagnostics["selected_route_rows"] = len(route_rows)
        if route_rows and isinstance(route_rows[0], dict):
            diagnostics["sample_station_row_keys"] = [str(k) for k in list(route_rows[0].keys())[:60]]

        # Search the complete response (not just its root) for explicit no-halt
        # lists. Several NTES wrappers nest these under data/result/route metadata.
        # Keep the source's original order and de-duplicate the same list if it is
        # exposed through more than one wrapper.
        nonstop_key_names = {
            "nonstoppingstations", "non_stopping_stations", "passingstations",
            "passing_stations", "nonhaltstations", "non_halt_stations",
            "intermediatestations", "intermediate_stations", "nonstoppingstationlist",
            "non_stopping_station_list", "passingstationlist", "passing_station_list",
            "nohaltstations", "no_halt_stations", "betweenstations",
        }
        global_nonstop = []
        seen_nonstop_lists = set()
        def _collect_nonstop_lists(payload, depth=0):
            if depth > 10:
                return
            if isinstance(payload, dict):
                for key, value in payload.items():
                    normalized_key = re.sub(r"[^a-z_]", "", str(key).lower())
                    normalized_key = normalized_key.replace("__", "_")
                    compact_key = normalized_key.replace("_", "")
                    is_nonstop_key = normalized_key in nonstop_key_names or compact_key in {
                        "nonstoppingstations", "passingstations", "nonhaltstations",
                        "intermediatestations", "nonstoppingstationlist", "passingstationlist",
                        "nohaltstations", "betweenstations",
                    }
                    if is_nonstop_key and isinstance(value, (list, tuple)) and value:
                        try:
                            signature = json.dumps(value, sort_keys=True, default=str)
                        except Exception:
                            signature = repr(value)
                        if signature not in seen_nonstop_lists:
                            seen_nonstop_lists.add(signature)
                            global_nonstop.extend(value)
                    if isinstance(value, (dict, list, tuple)):
                        _collect_nonstop_lists(value, depth + 1)
            elif isinstance(payload, (list, tuple)):
                for item in payload:
                    if isinstance(item, (dict, list, tuple)):
                        _collect_nonstop_lists(item, depth + 1)
        _collect_nonstop_lists(schedule_data)
        global_nonstop = global_nonstop or None

        for row in route_rows if isinstance(route_rows, list) else []:
                if not isinstance(row, dict):
                    continue
                station_name = clean(row.get("StationName") or row.get("stationName") or row.get("station_name") or row.get("station") or row.get("name") or row.get("stnName") or row.get("stn_name") or row.get("Station") or row.get("STATION_NAME"))
                station_code = clean(row.get("StationCode") or row.get("stationCode") or row.get("station_code") or row.get("code") or row.get("stnCode") or row.get("stn_code") or row.get("STN") or row.get("STATION_CODE"))
                if not station_name and not station_code:
                    continue
                # Preserve any intermediate / non-stopping stations supplied by the source.
                intermediate_raw = None
                for intermediate_key in (
                    "nonStoppingStations", "non_stopping_stations", "nonStopping", "non_stopping",
                    "intermediateStations", "intermediate_stations", "passingStations",
                    "passing_stations", "nonHaltStations", "non_halt_stations", "betweenStations",
                    "nonStoppingStationList", "non_stopping_station_list", "intermediateStationList",
                    "intermediate_station_list", "passingStationList", "passing_station_list",
                    "nonHaltStationList", "non_halt_station_list", "noHaltStations", "no_halt_stations",
                ):
                    candidate = row.get(intermediate_key)
                    if isinstance(candidate, (list, tuple)) and candidate:
                        intermediate_raw = list(candidate)
                        break
                    # Some wrappers serialize the list as text instead of JSON.
                    if isinstance(candidate, str) and candidate.strip():
                        parsed = None
                        try:
                            parsed = json.loads(candidate)
                        except Exception:
                            pass
                        if isinstance(parsed, list):
                            intermediate_raw = parsed
                            break
                        # Only split explicit station separators; do not guess from arbitrary prose.
                        pieces = [part.strip() for part in re.split(r"\s*[;|]\s*", candidate) if part.strip()]
                        if pieces:
                            intermediate_raw = pieces
                            break
                intermediate_stations = []
                for item in intermediate_raw or []:
                    if isinstance(item, str):
                        item_text = clean(item)
                        # NTES commonly formats a station as "NAME - CODE".
                        pair = re.match(r"^(.+?)\s+[-–—]\s+([A-Z0-9]{2,6})$", item_text, re.I)
                        item_name, item_code, item_distance = (pair.group(1).strip(), pair.group(2).strip().upper(), "") if pair else (item_text, "", "")
                    elif isinstance(item, dict):
                        item_name = clean(item.get("StationName") or item.get("stationName") or item.get("station_name") or item.get("station") or item.get("name") or item.get("stnName"))
                        item_code = clean(item.get("StationCode") or item.get("stationCode") or item.get("station_code") or item.get("code") or item.get("stnCode"))
                        item_distance = clean(item.get("Distance") or item.get("distance") or item.get("distance_km"))
                    else:
                        continue
                    if item_name or item_code:
                        intermediate_stations.append({"station": item_name or item_code, "station_code": item_code, "distance_km": item_distance, "is_passing": True})
                # A source may return a full route with an explicit no-halt flag.
                stop_flag = row.get("isStopping")
                if stop_flag is None: stop_flag = row.get("is_stopping")
                if stop_flag is None: stop_flag = row.get("halts")
                if stop_flag is None: stop_flag = row.get("isHalt")
                if stop_flag is None: stop_flag = row.get("is_halt")
                if stop_flag is None: stop_flag = row.get("halt")
                if stop_flag is None: stop_flag = row.get("stopping")
                if stop_flag is None: stop_flag = row.get("stop")
                if stop_flag is None: stop_flag = row.get("isHaltStation")
                if stop_flag is None: stop_flag = row.get("haltFlag")
                if stop_flag is None: stop_flag = row.get("stopFlag")
                if stop_flag is None: stop_flag = row.get("isStop")
                stop_type = clean(
                    row.get("stopType") or row.get("stop_type") or row.get("haltType") or
                    row.get("halt_type") or row.get("stationType") or row.get("station_type") or
                    row.get("stopStatus") or row.get("stop_status") or row.get("haltStatus") or
                    row.get("halt_status") or row.get("stationCategory") or row.get("station_category")
                ).lower()
                arrival_value = clean(row.get("STA") or row.get("arrival") or row.get("arrivalTime") or row.get("scheduled_arrival") or row.get("arrTime") or row.get("arr_time") or row.get("STA_TIME") or row.get("arrival_time"))
                departure_value = clean(row.get("STD") or row.get("departure") or row.get("departureTime") or row.get("scheduled_departure") or row.get("depTime") or row.get("dep_time") or row.get("STD_TIME") or row.get("departure_time"))
                explicit_passing = (
                    stop_flag is False or str(stop_flag).strip().lower() in {"0", "false", "no", "n"} or
                    any(token in stop_type for token in ("non-stop", "nonstop", "passing", "no halt", "pass-through", "pass through", "no stoppage", "intermediate"))
                )
                # RailGeo's full route has also used blank/UA time fields for
                # stations passed without a scheduled halt. Treat a row as
                # passing only when both halt times are absent; do not infer a
                # passing station from a missing single arrival/departure.
                passing_flag = explicit_passing or (not arrival_value and not departure_value)
                normalized_stations.append({
                    "station": station_name or station_code,
                    "station_code": station_code,
                    "scheduled_arrival": arrival_value,
                    "scheduled_departure": departure_value,
                    "reported_arrival": clean(row.get("actualArrival") or row.get("reported_arrival")),
                    "reported_departure": clean(row.get("actualDeparture") or row.get("reported_departure")),
                    "platform": clean(row.get("Platform") or row.get("platform")),
                    "distance_km": clean(row.get("Distance") or row.get("distance") or row.get("distance_km") or row.get("distanceKm") or row.get("distKm") or row.get("routeDistance")),
                    "day": clean(row.get("Day") or row.get("day") or "1"),
                    "intermediate_stations": intermediate_stations,
                    "is_passing": passing_flag,
                })
        # If the provider supplies a top-level non-stopping list, preserve it in
        # the first stopping section rather than silently discarding it.
        if global_nonstop and normalized_stations:
            # Attach explicit top-level/nested passing stations to the preceding
            # halt using route distance when supplied. If no distance is supplied,
            # use the source order and keep them in the first section only as a
            # last resort; never create names that are absent from NTES.
            for item in global_nonstop:
                if isinstance(item, str):
                    item_text = clean(item)
                    match = re.match(r"^(.+?)\s+[-–—]\s+([A-Z0-9]{2,6})$", item_text, re.I)
                    item_name, item_code, item_distance = (match.group(1).strip(), match.group(2).upper(), "") if match else (item_text, "", "")
                elif isinstance(item, dict):
                    item_name = clean(item.get("StationName") or item.get("stationName") or item.get("station_name") or item.get("station") or item.get("name") or item.get("stnName"))
                    item_code = clean(item.get("StationCode") or item.get("stationCode") or item.get("station_code") or item.get("code") or item.get("stnCode"))
                    item_distance = clean(item.get("Distance") or item.get("distance") or item.get("distance_km"))
                else:
                    continue
                if not (item_name or item_code):
                    continue
                # Do not duplicate an item already included in a row-level list.
                identity = (item_name.casefold(), item_code.upper())
                if any((str(existing.get("station", "")).casefold(), str(existing.get("station_code", "")).upper()) == identity
                       for halt in normalized_stations for existing in (halt.get("intermediate_stations") or [])):
                    continue
                owner = None
                if item_distance:
                    try:
                        d = float(re.search(r"\d+(?:\.\d+)?", item_distance).group(0))
                        eligible = []
                        for halt in normalized_stations:
                            if halt.get("is_passing"):
                                continue
                            try:
                                hd = float(re.search(r"\d+(?:\.\d+)?", str(halt.get("distance_km", ""))).group(0))
                            except Exception:
                                continue
                            if hd <= d:
                                eligible.append((hd, halt))
                        if eligible:
                            owner = max(eligible, key=lambda pair: pair[0])[1]
                    except Exception:
                        pass
                if owner is None:
                    # If the provider supplied an ordered full route, use the
                    # closest preceding stopping row based on the item's index.
                    # A global unpositioned list cannot be safely distributed.
                    continue
                owner.setdefault("intermediate_stations", []).append({
                    "station": item_name or item_code, "station_code": item_code,
                    "distance_km": item_distance, "is_passing": True,
                })
    except Exception as exc:
        schedule_error = f"{type(exc).__name__}: {str(exc)[:200]}"
        diagnostics["regular_schedule_error"] = schedule_error

    diagnostics["parsed_stopping_stations"] = sum(1 for item in normalized_stations if not item.get("is_passing"))
    diagnostics["parsed_passing_rows"] = sum(1 for item in normalized_stations if item.get("is_passing"))
    diagnostics["attached_intermediate_stations"] = sum(len(item.get("intermediate_stations") or []) for item in normalized_stations)
    diagnostics["regular_schedule_error"] = diagnostics["regular_schedule_error"] or (schedule_error or "")
    diagnostics["railgeo_error"] = diagnostics["railgeo_error"] or (railgeo_error or "")

    if not normalized_stations and schedule_error and railgeo_error:
        schedule_error += f"; RailGeo all-stations request also failed: {railgeo_error}"

    if not normalized_stations and not any((current_station, current_code, next_station, next_code, journey_state, delay, platform)):
        details = []
        if live_error:
            details.append(f"live_status failed: {live_error}")
        if info_error:
            details.append(f"train_info fallback failed: {info_error}")
        suffix = " Details: " + " | ".join(details) if details else ""
        raise RuntimeError(
            "NTES did not provide usable running-position or journey-instance fields for train "
            f"{train_number} on {running_date.isoformat()}. This is an upstream data/protocol limitation, "
            "not a train-number format error. Check the selected journey date and verify the result on official NTES."
            + suffix
        )

    return {
        "train_number": train_number,
        "train_name": train_name,
        "running_date": running_date.isoformat(),
        "fetched_at": datetime.now().strftime("%d %b %Y, %I:%M:%S %p"),
        "journey_state": journey_state or "NTES returned limited information; no current station was provided.",
        "stations": normalized_stations,
        "summary_only": not bool(normalized_stations),
        "schedule_error": schedule_error,
        "ntes_diagnostics": diagnostics,
        "current_station": current_station,
        "current_station_code": current_code,
        "next_station": next_station,
        "next_station_code": next_code,
        "delay": delay,
        "platform": platform,
        "instance_date": instance_date,
        "source": "NTES",
    }


if st.session_state.railconnect_page == "Live Train Status":
    st.html("""
<div class="pnr-hero"><div class="pnr-eyebrow">RailConnect · NTES live information</div><div class="pnr-title">Train Running Status</div><div class="pnr-description">Look up a train directly by train number and journey date. This page reads the NTES running-status page and does not display seat availability or fares.</div></div>
""")
    with st.container(border=True):
        search_col1, search_col2 = st.columns([1, 1])
        with search_col1:
            train_number = st.text_input("Train number (5 digits)", placeholder="e.g. 19665", max_chars=5, key="live_status_train_number").strip()
        with search_col2:
            running_date = st.date_input("Running date", value=date.today(), key="live_status_running_date", help="Choose the date for the train running-status lookup.")
        clicked = st.button("Check live running status", type="primary", use_container_width=True, key="live_status_submit")
    if clicked:
        if not (train_number.isascii() and train_number.isdigit() and len(train_number) == 5):
            st.session_state.live_status_result = None
            st.session_state.live_status_error = "Enter the 5-digit train number (digits only)."
        else:
            try:
                with st.spinner("Connecting to NTES and retrieving running status..."):
                    live_status_result = _fetch_live_train_status({"train_number": train_number, "running_date": running_date.isoformat()})
                st.session_state.live_status_result = live_status_result
                st.session_state.live_status_query = {"train_number": train_number, "running_date": running_date.isoformat()}
                st.session_state.live_status_error = None
            except Exception as exc:
                st.session_state.live_status_result = None
                st.session_state.live_status_error = str(exc)
    if st.session_state.get("live_status_error"):
        st.error(st.session_state.live_status_error)
    elif st.session_state.get("live_status_result") is not None:
        result = st.session_state.live_status_result
        # Keep refresh and official verification actions at the top, where users expect them.
        top_refresh_col, top_official_col = st.columns([1, 1])
        with top_refresh_col:
            if st.button("↻ Refresh live status", use_container_width=True, key="refresh_live_status_top"):
                saved_query = st.session_state.get("live_status_query") or {
                    "train_number": str(result.get("train_number") or ""),
                    "running_date": str(result.get("running_date") or date.today().isoformat()),
                }
                try:
                    with st.spinner("Refreshing live train status..."):
                        st.session_state.live_status_result = _fetch_live_train_status(saved_query)
                    st.session_state.live_status_error = None
                    st.rerun()
                except Exception as exc:
                    st.session_state.live_status_error = str(exc)
                    st.error(st.session_state.live_status_error)
        with top_official_col:
            st.link_button("Check official NTES ↗", "https://enquiry.indianrail.gov.in/mntes/", use_container_width=True)
        st.html('<div class="section-heading">Live running details</div>')
        train_name = html.escape(str(result.get("train_name") or "Train running status"))
        train_no = html.escape(str(result.get("train_number") or ""))
        journey_date = html.escape(str(result.get("running_date") or ""))
        fetched = html.escape(str(result.get("fetched_at") or ""))
        st.markdown(f"### {train_name} · Train no. {train_no}")
        st.caption(f"Journey date: {journey_date} · Last refreshed: {fetched}")
        journey_state = str(result.get("journey_state") or "").strip()

        # Some NTES responses include the live event as a sentence instead of
        # populating CurrentStationName / CurrentStation fields.
        current_station = str(result.get("current_station") or "").strip()
        current_code = str(result.get("current_station_code") or "").strip()
        delay_value = str(result.get("delay") or "").strip()
        event_time = ""
        if journey_state:
            match = re.search(
                r"(?:arrived|departed|at)\s+(?:(?:from|at)\s+)?(.+?)\s*\(([A-Z0-9]{2,6})\)\s+at\s+(\d{1,2}:\d{2})",
                journey_state, re.I
            )
            if match:
                # The event sentence is often the most precise location source
                # (e.g. "Departed from CHARKHERA KHURD(CKKD) at 20:42 26-Oct").
                # Prefer its parsed station for timeline matching over generic API fields.
                event_station = match.group(1).strip()
                event_code = match.group(2).strip().upper()
                if event_station:
                    current_station = event_station
                if event_code:
                    current_code = event_code
                event_time = match.group(3)
            elif not current_station:
                match = re.search(r"(?:arrived|departed|at)\s+(?:at\s+)?([A-Z][A-Z0-9 .'-]{2,})", journey_state, re.I)
                if match:
                    current_station = match.group(1).strip(" .")
            if not delay_value:
                delay_match = re.search(r"delay\s*:\s*([0-9: ]+(?:min|mins|minutes)?)", journey_state, re.I)
                if delay_match:
                    delay_value = delay_match.group(1).strip()

        # Light, rail-timeline presentation inspired by the requested reference.
        st.markdown("""
<style>
.rc-live-wrap{background:#f1f3f5;color:#20252b;border-radius:14px;overflow:hidden;border:1px solid #d8dee5;margin:.6rem 0 1rem}
.rc-live-top{background:#1766a8;color:#fff;padding:16px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap}
.rc-live-kicker{color:#e4f1ff;font-size:12px;letter-spacing:.08em;text-transform:uppercase}
.rc-live-date{font-size:17px;font-weight:700;margin-top:4px;color:#fff}
.rc-live-event-banner{margin:12px 14px 0;padding:13px 16px;border:1px solid #9ecdf5;border-left:5px solid #087bd5;border-radius:10px;background:#e2f2ff;color:#064f8b;font-size:17px;font-weight:850;line-height:1.45}
.rc-live-event-banner .rc-live-event-label{font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:#1766a8;font-weight:800;margin-bottom:3px}
.rc-live-pill{background:#fff;border:1px solid #d7e4f1;border-radius:22px;padding:8px 12px;color:#165b98;font-size:13px}
.rc-live-head{display:grid;grid-template-columns:90px 44px minmax(0,1fr) 90px;gap:12px;background:#ffffff;color:#263746;padding:12px 14px;font-weight:650;border-bottom:1px solid #cbd5df}
.rc-live-stop{display:grid;grid-template-columns:90px 44px minmax(0,1fr) 90px;gap:12px;padding:20px 14px;min-height:110px;align-items:center;border-bottom:1px solid #dfe4e9;background:#ffffff}
        .rc-live-stop-start .rc-live-track:before{top:50%;bottom:-25px}
        .rc-live-stop-end .rc-live-track:before{top:-25px;bottom:50%}
.rc-live-times{font-size:16px;font-weight:800;line-height:1.8;color:#111827;font-variant-numeric:tabular-nums}
.rc-live-actual{color:#111827;font-weight:900;font-size:16px;line-height:1.5;font-variant-numeric:tabular-nums}
.rc-live-actual.is-late{color:#d52b22}
.rc-live-passing{min-height:58px!important;padding-top:8px!important;padding-bottom:8px!important;background:#f8fafc!important}
.rc-live-passing .rc-live-station{font-size:14px!important;color:#536273!important}
.rc-live-passing-label{display:inline-block;margin-left:7px;padding:2px 7px;border-radius:10px;background:#e8eef5;color:#526174;font-size:10px;font-weight:800;vertical-align:middle}
.rc-live-late{display:inline-block;margin:8px 14px 0;padding:8px 12px;border-radius:8px;background:#fff0ef;border:1px solid #ffc7c2;color:#b42318;font-weight:850;font-size:14px}
.rc-live-track{height:100%;min-height:110px;align-self:stretch;position:relative;display:flex;justify-content:center;align-items:center;overflow:visible}
.rc-live-track:before{content:"";position:absolute;top:-25px;bottom:-25px;left:50%;transform:translateX(-50%);width:5px;background:#8dcff0;border-radius:4px;z-index:0}
.rc-live-dot{position:relative;z-index:2;width:13px;height:13px;border-radius:50%;background:#1766a8;border:2px solid #d7efff;margin-top:6px;display:block}
.rc-live-track{position:relative;min-width:42px;width:42px;justify-self:center}
.rc-live-train-marker{position:relative;z-index:5;width:42px;height:42px;min-width:42px;flex:0 0 42px;border-radius:50%;background:#087bd5;border:3px solid #eaf6ff;box-shadow:0 2px 7px #0002;display:flex!important;align-items:center;justify-content:center;font-size:25px;line-height:1;margin:0;color:#fff;visibility:visible;opacity:1}
.rc-live-stop.rc-live-stop-current{background:#e2f2ff;border-bottom-color:#b6dfff}
.rc-live-stop-current .rc-live-station{color:#075da5;font-weight:750}
.rc-live-current{background:#dceeff;color:#145b96;border:1px solid #b7d9f7;padding:10px 12px;border-radius:8px;font-weight:650;display:inline-block;margin-top:8px}
.rc-live-station{font-size:16px;font-weight:650;color:#20252b}
.rc-live-meta{font-size:14px;color:#586572;margin-top:8px;font-weight:650}.rc-live-distance{font-size:16px;font-weight:800;color:#174f7d}.rc-live-stop-date{font-size:12px;color:#657487;font-weight:600;margin-top:4px}
.rc-live-note{padding:12px 16px;color:#536170;font-size:12px;background:#ffffff;border-top:1px solid #e7edf2}
.rc-live-intermediate{margin-top:10px;max-width:100%;border:1px solid #d8e1eb;border-radius:8px;background:#ffffff;color:#18283b;overflow:hidden}
.rc-live-intermediate summary{cursor:pointer;list-style:none;padding:9px 12px;color:#175e9b;font-size:12px;font-weight:800;user-select:none;background:#ffffff}
.rc-live-intermediate summary::-webkit-details-marker{display:none}
.rc-live-intermediate summary:after{content:"⌄";display:inline-block;margin-left:7px;color:#168cff;font-size:16px;transition:transform .15s}
.rc-live-intermediate[open] summary:after{transform:rotate(180deg)}
.rc-live-intermediate-list{padding:0 12px 8px;background:#ffffff}
.rc-live-intermediate-item{display:flex;justify-content:space-between;gap:12px;padding:8px 0;border-top:1px solid #e6ebf1;font-size:12px;color:#24364b}
.rc-live-intermediate-item .pass-label{color:#66778b;font-size:10px;font-weight:800;white-space:nowrap}
div[data-testid="stButton"] button{border:1px solid #c8d9ea!important;border-radius:12px!important;background:linear-gradient(110deg,#ffffff,#edf6ff)!important;color:#145b96!important;font-weight:800!important;box-shadow:0 4px 12px #182d5018!important;transition:transform .15s,box-shadow .15s!important}
div[data-testid="stButton"] button[kind="primary"]{border:0!important;border-radius:12px!important;background:linear-gradient(110deg,#1766a8,#087bd5)!important;color:#fff!important;font-weight:800!important;box-shadow:0 5px 14px #182d5030!important;transition:transform .15s,box-shadow .15s!important}
div[data-testid="stButton"] button[kind="primary"]:hover{transform:translateY(-1px);box-shadow:0 8px 18px #182d5040!important}
div[data-testid="stLinkButton"] a{border:1px solid #1684d2!important;border-radius:10px!important;background:#172b46!important;color:#fff!important;font-weight:800!important;box-shadow:0 4px 12px #182d5030!important}
div[data-testid="stLinkButton"] a:hover{background:#20446c!important;border-color:#48b4ff!important}
@media(max-width:720px){div[data-testid="stRadio"]{width:calc(100% - 16px)!important;max-width:calc(100% - 16px)!important;margin:14px auto 20px!important;padding:5px!important}div[data-testid="stRadio"] div[role="radiogroup"] label{flex:1 1 42%!important;padding:10px 8px!important;font-size:11px!important}.rc-live-head{grid-template-columns:62px 42px minmax(0,1fr) 62px;font-size:12px}.rc-live-stop{grid-template-columns:62px 42px minmax(0,1fr) 62px;gap:7px;padding:15px 8px}.rc-live-times{font-size:11px}.rc-live-station{font-size:14px}}
/* Final navigation sizing override: avoid forced 150px options and excess outer margins. */
div[data-testid="stRadio"]{width:fit-content!important;max-width:calc(100% - 32px)!important;margin:14px auto 20px!important;padding:5px!important;box-sizing:border-box!important}
div[data-testid="stRadio"] div[role="radiogroup"]{display:flex!important;flex-flow:row wrap!important;justify-content:center!important;gap:4px!important}
div[data-testid="stRadio"] div[role="radiogroup"] label{min-width:0!important;flex:0 1 auto!important;white-space:nowrap!important;padding:10px clamp(10px,1.35vw,19px)!important;margin:0!important;font-size:12px!important}
@media(max-width:720px){div[data-testid="stRadio"]{width:calc(100% - 20px)!important;max-width:calc(100% - 20px)!important;margin:12px auto 16px!important}div[data-testid="stRadio"] div[role="radiogroup"] label{flex:1 1 42%!important;white-space:normal!important;padding:10px 7px!important;font-size:11px!important}}
</style>
""", unsafe_allow_html=True)
        stations = result.get("stations") or []
        state_safe = html.escape(journey_state or "Live status received from NTES.")
        # Show lateness explicitly in red when NTES provides a delay value or embeds it in the event.
        delay_for_badge = str(delay_value or "").strip()
        if not delay_for_badge:
            delay_match_for_badge = re.search(r"(?:delay\s*:?\s*|late by\s+)([0-9]{1,2}:[0-9]{2}|[0-9]+\s*(?:min|mins|minutes))", journey_state, re.I)
            if delay_match_for_badge:
                delay_for_badge = delay_match_for_badge.group(1).strip()
        delay_is_late = bool(delay_for_badge and not re.search(r"on\s*time|right\s*time|0{1,2}:?0{2}", delay_for_badge, re.I))
        delay_badge_html = (f'<div class="rc-live-late">Running late · {html.escape(delay_for_badge)}</div>' if delay_is_late else "")
        if stations:
            timeline_html = [
                '<div class="rc-live-wrap">',
                f'<div class="rc-live-top"><div><div class="rc-live-kicker">Live train status</div><div class="rc-live-date">{train_name} · {train_no}</div></div><div class="rc-live-pill">Journey date · {journey_date}</div></div>',
                f'<div class="rc-live-event-banner"><div class="rc-live-event-label">Latest live update</div>{html.escape(journey_state or "Live status received from NTES.")}</div>',
                delay_badge_html,
                '<div class="rc-live-head"><div>Arrival</div><div style="grid-column:2/4;text-align:center">Station / running update</div><div style="text-align:right">Departure</div></div>'
            ]
            # Match the live station to the scheduled route. Prefer station code,
            # then compare normalized station names. Never mark a random stop as current.
            def _station_key(value):
                return re.sub(r"[^a-z0-9]", "", str(value or "").lower())

            live_code_key = _station_key(current_code)
            live_name_key = _station_key(current_station)
            current_idx = None

            # Match station CODE first: codes are much less ambiguous than
            # names (e.g. abbreviations, "M RD" vs "Mahwa Road", punctuation).
            if live_code_key:
                for match_idx, match_stop in enumerate(stations):
                    stop_code_key = _station_key(match_stop.get("station_code"))
                    if stop_code_key and live_code_key == stop_code_key:
                        current_idx = match_idx
                        break

            # If the code is absent or doesn't match this schedule, compare
            # normalized names. Exact name wins; fuzzy matches are only a fallback.
            if current_idx is None and live_name_key:
                exact_candidates = []
                fuzzy_candidates = []
                for match_idx, match_stop in enumerate(stations):
                    stop_name_key = _station_key(match_stop.get("station"))
                    if not stop_name_key:
                        continue
                    if live_name_key == stop_name_key:
                        exact_candidates.append(match_idx)
                    elif len(live_name_key) >= 4 and (
                        live_name_key in stop_name_key or stop_name_key in live_name_key
                    ):
                        fuzzy_candidates.append(
                            (abs(len(stop_name_key) - len(live_name_key)), match_idx)
                        )
                if exact_candidates:
                    current_idx = exact_candidates[0]
                elif fuzzy_candidates:
                    current_idx = min(fuzzy_candidates)[1]

            # Some NTES live events name a station where the train passes through,
            # but which is not a scheduled halt (e.g. DATIA between GWALIOR and
            # VIRANGANA LAKSHMIBAI JHANSI). In that case, place a synthetic live
            # row between the adjacent scheduled stops using the event clock time.
            # This makes the train marker visible without falsely pinning it to
            # an unrelated scheduled station.
            if current_idx is None and current_station and event_time and len(stations) >= 2:
                def _clock_minutes(value):
                    m = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", str(value or ""), re.I)
                    if not m:
                        return None
                    hh, mm = int(m.group(1)), int(m.group(2))
                    ap = (m.group(3) or "").upper()
                    if ap:
                        hh = hh % 12 + (12 if ap == "PM" else 0)
                    return hh * 60 + mm

                event_minutes = _clock_minutes(event_time)
                route_minutes = []
                day_offset = 0
                previous_minute = None
                for route_stop in stations:
                    clock = _clock_minutes(
                        route_stop.get("scheduled_departure")
                        or route_stop.get("scheduled_arrival")
                    )
                    if clock is not None and previous_minute is not None and clock < previous_minute - 360:
                        day_offset += 1440
                    route_minutes.append(None if clock is None else clock + day_offset)
                    if clock is not None:
                        previous_minute = clock

                if event_minutes is not None:
                    # Try event time on the schedule's base day and adjacent days.
                    inserted_at = None
                    for i in range(len(stations) - 1):
                        left = route_minutes[i]
                        right = route_minutes[i + 1]
                        if left is None or right is None:
                            continue
                        if right < left:
                            right += 1440
                        candidates = [event_minutes + shift for shift in (-1440, 0, 1440)]
                        if any(left <= candidate <= right for candidate in candidates):
                            inserted_at = i + 1
                            break
                    if inserted_at is not None:
                        live_stop = {
                            "station": current_station,
                            "station_code": current_code,
                            "is_passing": True,
                            "scheduled_arrival": "—",
                            "reported_arrival": event_time,
                            "scheduled_departure": "—",
                            "reported_departure": "",
                            "distance_km": "",
                            "platform": "",
                        }
                        stations.insert(inserted_at, live_stop)
                        current_idx = inserted_at

            # Keep the main timeline limited to scheduled stopping stations.
            # Any live-only passing location is nested under the previous halt and
            # appears only when that halt's Non-Stopping Stations arrow is expanded.
            if stations:
                stopping_stations = []
                last_halt = None
                old_to_new = {}
                for old_idx, route_stop in enumerate(stations):
                    if route_stop.get("is_passing"):
                        if last_halt is not None:
                            passing_items = last_halt.setdefault("intermediate_stations", [])
                            passing_items.append({
                                "station": route_stop.get("station") or "Intermediate station",
                                "station_code": route_stop.get("station_code") or "",
                                "distance_km": route_stop.get("distance_km") or "",
                                "is_passing": True,
                                "live_time": route_stop.get("reported_arrival") or route_stop.get("reported_departure") or "",
                                "is_live_location": old_to_new.get(old_idx) is None,
                            })
                        continue
                    old_to_new[old_idx] = len(stopping_stations)
                    stopping_stations.append(route_stop)
                    last_halt = route_stop
                if stopping_stations:
                    if current_idx is not None:
                        if current_idx in old_to_new:
                            current_idx = old_to_new[current_idx]
                        else:
                            # The current live position was a passing-through point;
                            # keep the train marker on the preceding stopping station.
                            previous_halts = [old for old in old_to_new if old < current_idx]
                            current_idx = old_to_new[previous_halts[-1]] if previous_halts else 0
                    stations = stopping_stations

            # Infer each stop's calendar date from scheduled times crossing midnight.
            # The journey date is the first stop's date; a clock rollback indicates overnight travel.
            try:
                route_day = date.fromisoformat(str(result.get("running_date") or journey_date))
            except Exception:
                route_day = date.today()
            previous_clock = None
            stop_dates = []
            for date_stop in stations:
                raw_clock = str(date_stop.get("scheduled_arrival") or date_stop.get("scheduled_departure") or "").strip()
                clock_match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", raw_clock, re.I)
                if clock_match:
                    hour = int(clock_match.group(1))
                    minute = int(clock_match.group(2))
                    ampm = (clock_match.group(3) or "").upper()
                    if ampm:
                        hour = hour % 12 + (12 if ampm == "PM" else 0)
                    clock_minutes = hour * 60 + minute
                    if previous_clock is not None and clock_minutes < previous_clock - 360:
                        route_day += timedelta(days=1)
                    previous_clock = clock_minutes
                stop_dates.append(route_day.strftime("%a, %d %b %Y"))

            for idx, stop in enumerate(stations):
                station = html.escape(str(stop.get("station") or "Station"))
                raw_code = str(stop.get("station_code") or "")
                code = html.escape(raw_code)
                scheduled_arr = html.escape(str(stop.get("scheduled_arrival") or "—"))
                reported_arr = html.escape(str(stop.get("reported_arrival") or ""))
                scheduled_dep = html.escape(str(stop.get("scheduled_departure") or "—"))
                reported_dep = html.escape(str(stop.get("reported_departure") or ""))
                platform = html.escape(str(stop.get("platform") or ""))
                distance = html.escape(str(stop.get("distance_km") or ""))
                def _clock_value(value):
                    match = re.search(r"(\d{1,2}):(\d{2})\s*(AM|PM)?", str(value or ""), re.I)
                    if not match:
                        return None
                    hour, minute = int(match.group(1)), int(match.group(2))
                    suffix = (match.group(3) or "").upper()
                    if suffix:
                        hour = hour % 12 + (12 if suffix == "PM" else 0)
                    if hour > 23 or minute > 59:
                        return None
                    return hour * 60 + minute

                def _is_late(scheduled, reported):
                    scheduled_minute, reported_minute = _clock_value(scheduled), _clock_value(reported)
                    if scheduled_minute is None or reported_minute is None:
                        return False
                    # A small clock difference across midnight should be treated as next-day time.
                    while reported_minute < scheduled_minute - 720:
                        reported_minute += 1440
                    return reported_minute > scheduled_minute + 1

                actual_arr_class = "rc-live-actual is-late" if _is_late(stop.get("scheduled_arrival"), stop.get("reported_arrival")) else "rc-live-actual"
                actual_dep_class = "rc-live-actual is-late" if _is_late(stop.get("scheduled_departure"), stop.get("reported_departure")) else "rc-live-actual"
                actual_arr = f'<div class="{actual_arr_class}">{reported_arr}</div>' if reported_arr else ""
                actual_dep = f'<div class="{actual_dep_class}">{reported_dep}</div>' if reported_dep else ""
                meta_parts = []
                if platform:
                    meta_parts.append(f"Platform {platform}")
                if distance:
                    meta_parts.append(f'<span class="rc-live-distance">{distance} km</span>')
                meta_html = f'<div class="rc-live-meta">{" · ".join(meta_parts)}</div>' if meta_parts else ""
                stop_date_html = f'<div class="rc-live-stop-date">{html.escape(stop_dates[idx])}</div>' 
                is_current = current_idx == idx
                row_classes = ["rc-live-stop"]
                is_passing = bool(stop.get("is_passing"))
                if is_passing:
                    row_classes.append("rc-live-passing")
                if is_current:
                    row_classes.append("rc-live-stop-current")
                if idx == 0:
                    row_classes.append("rc-live-stop-start")
                if idx == len(stations) - 1:
                    row_classes.append("rc-live-stop-end")
                row_class = " ".join(row_classes)
                marker = '<span class="rc-live-train-marker" title="Current train location" aria-label="Train is here">🚆</span>' if is_current else '<span class="rc-live-dot"></span>'
                live_event_text = html.escape(journey_state or "Live train location")
                current_badge = f'<div class="rc-live-current">🚆 LIVE HERE · {live_event_text}</div>' if is_current else ""
                passing_label = '<span class="rc-live-passing-label">PASSING THROUGH · NO HALT</span>' if is_passing else ""
                intermediate = stop.get("intermediate_stations") or stop.get("non_stopping_stations") or []
                intermediate_html = ""
                intermediate_items = []
                for intermediate_stop in intermediate:
                    if isinstance(intermediate_stop, str):
                        intermediate_stop = {"station": intermediate_stop}
                    if not isinstance(intermediate_stop, dict):
                        continue
                    intermediate_name = html.escape(str(intermediate_stop.get("station") or intermediate_stop.get("name") or "Intermediate station"))
                    intermediate_code = html.escape(str(intermediate_stop.get("station_code") or intermediate_stop.get("code") or ""))
                    intermediate_distance = html.escape(str(intermediate_stop.get("distance_km") or intermediate_stop.get("distance") or ""))
                    intermediate_live_time = html.escape(str(intermediate_stop.get("live_time") or ""))
                    intermediate_items.append(
                        '<div class="rc-live-intermediate-item"><span>' + intermediate_name +
                        (f' ({intermediate_code})' if intermediate_code else "") +
                        (f' · {intermediate_distance} km' if intermediate_distance else "") +
                        (f' · <strong>{intermediate_live_time}</strong>' if intermediate_live_time else "") +
                        '</span><span class="pass-label">NON-STOPPING</span></div>'
                    )
                # Keep every scheduled halt as the only main timeline row. The native
                # HTML details element provides a real click-to-expand/collapse arrow.
                # Never fabricate intermediate station names when NTES supplies none.
                intermediate_content = ''.join(intermediate_items) if intermediate_items else (
                    '<div class="rc-live-intermediate-item"><span>The NTES schedule response contains no non-stopping station records for this section.</span></div>'
                )
                intermediate_count = str(len(intermediate_items)) if intermediate_items else 'details unavailable'
                intermediate_html = (
                    '<details class="rc-live-intermediate"><summary>▸ Non-Stopping Stations (' +
                    intermediate_count + ') </summary><div class="rc-live-intermediate-list">' +
                    intermediate_content + '</div></details>'
                )
                timeline_html.append(
                    f'<div id="rc-live-stop-{idx}" class="{row_class}"><div class="rc-live-times">{scheduled_arr}{actual_arr}</div>'
                    f'<div class="rc-live-track">{marker}</div>'
                    f'<div><div class="rc-live-station">{station} {f"({code})" if code else ""}{passing_label}</div>{stop_date_html}{current_badge}{meta_html}{intermediate_html}</div>'
                    f'<div class="rc-live-times" style="text-align:right">{scheduled_dep}{actual_dep}</div></div>'
                )
            timeline_html.append(f'<div class="rc-live-note">{state_safe} · Black times are on time; red actual times indicate a delay against the scheduled time. Only scheduled stopping stations appear on the main timeline; expand Non-Stopping Stations under a halt to view intermediate locations supplied by NTES.</div></div>')
            st.markdown("".join(timeline_html), unsafe_allow_html=True)
            # Explain the actual source/parser state in the running app. This is
            # deliberately metadata-only: no cookies, headers, or raw response body.
            with st.expander("NTES diagnostics — why intermediate stations are missing", expanded=False):
                diag = result.get("ntes_diagnostics") or {}
                st.write("These values are collected by the current run; they are not estimates.")
                st.json(diag)
                if diag.get("railgeo_error"):
                    st.error("The RailGeo request failed. See railgeo_error above.")
                elif diag.get("railgeo_http_status") not in (None, 200):
                    st.warning("RailGeo returned a non-200 status. The endpoint may be blocking or redirecting the request.")
                elif not diag.get("railgeo_route_rows"):
                    st.warning("No station rows were recognized in the RailGeo response. Check response type, content type, and sample row keys; the endpoint may return a different schema or no JSON route data.")
                elif not diag.get("parsed_passing_rows") and not diag.get("attached_intermediate_stations"):
                    st.warning("RailGeo rows were found, but none were classified/attached as passing stations. The sample row keys above will guide the parser correction.")
            if current_idx is not None:
                # st.html scripts run in the app document, so this scrolls to the
                # live row even when it is near the very top or bottom of the route.
                st.html(f"""<script>
                (() => {{
                  const targetId = 'rc-live-stop-{int(current_idx)}';
                  const scrollToLive = () => {{
                    const target = window.parent.document.getElementById(targetId);
                    if (target) target.scrollIntoView({{behavior: 'smooth', block: 'center', inline: 'nearest'}});
                  }};
                  requestAnimationFrame(() => setTimeout(scrollToLive, 180));
                }})();
                </script>""")
        else:
            station_label = current_station or "Station not identified by NTES"
            code_label = f" ({current_code})" if current_code else ""
            time_label = f" · {html.escape(event_time)}" if event_time else ""
            delay_label = html.escape(delay_value or "Not provided")
            platform_label = html.escape(str(result.get("platform") or "Not provided"))
            next_label = html.escape(str(result.get("next_station") or "Not provided by NTES"))
            st.markdown(
                f'<div class="rc-live-wrap">'
                f'<div class="rc-live-top"><div><div class="rc-live-kicker">Live train status</div>'
                f'<div class="rc-live-date">{train_name} · {train_no}</div></div>'
                f'<div class="rc-live-pill">Journey date · {journey_date}</div></div>'
                f'{delay_badge_html}'
                f'<div class="rc-live-head"><div>Arrival</div><div style="grid-column:2/4;text-align:center">Live running update</div><div style="text-align:right">Departure</div></div>'
                f'<div class="rc-live-stop"><div class="rc-live-times">—</div><div class="rc-live-track"><span class="rc-live-dot"></span></div>'
                f'<div><div class="rc-live-station">{html.escape(station_label)}{html.escape(code_label)}</div>'
                f'<div class="rc-live-current">{state_safe}</div>'
                f'<div class="rc-live-meta">Next station: {next_label} · Delay: {delay_label} · Platform: {platform_label}</div></div>'
                f'<div class="rc-live-times" style="text-align:right">—</div></div>'
                f'<div class="rc-live-note">Station-by-station schedule is shown only when NTES supplies it. This view does not invent missing station times.</div></div>',
                unsafe_allow_html=True
            )
        st.caption("Live location, schedule and platform details depend on data returned by NTES. Verify important travel decisions on the official NTES website.")


if st.session_state.railconnect_page == "Train Availability":
    from railway.train_available import render_train_availability
    render_train_availability(stations=stations, data=data, find_journeys=find_journeys,
                              deduplicate_journeys=deduplicate_journeys, safe=safe, render_journey=render_journey)


# ----------------------------- Footer -----------------------------

st.html("""
<div class="helper">
    <h3>Plan your journey with confidence</h3>
    <p>RailConnect is an independent route-planning project and is not an official railway service. Schedules and route data may be incomplete or inaccurate. Always verify train operations, cancellations, platforms and current information with NTES and official Indian Railways sources before travelling.</p>
    <p>Help or suggestions: <a href="mailto:par305065@gmail.com">par305065@gmail.com</a></p>
</div>
<div class="footer">© 2026 RailConnect · Train Route Finder · All rights reserved</div>
""")

# ---------------- Navigation spacing correction ----------------
st.html("""
<style>
/* Keep all four navigation options on a single horizontal row at every viewport size. */
div[data-testid="stRadio"] {
    width: 100% !important;
    max-width: 100% !important;
    margin: 16px 0 22px !important;
    padding: 0 !important;
    box-sizing: border-box !important;
    border: 0 !important;
    border-radius: 0 !important;
    background: transparent !important;
    box-shadow: none !important;
    backdrop-filter: none !important;
    display: flex !important;
    justify-content: center !important;
}
div[data-testid="stRadio"] > div[role="radiogroup"] {
    width: 100% !important;
    max-width: 100% !important;
    min-width: 0 !important;
    box-sizing: border-box !important;
    display: flex !important;
    flex-flow: row nowrap !important;
    align-items: center !important;
    justify-content: space-between !important;
    gap: 4px !important;
    margin: 0 auto !important;
    padding: 6px !important;
    border: 1px solid rgba(205, 216, 239, .9) !important;
    border-radius: 16px !important;
    background: rgba(255,255,255,.92) !important;
    box-shadow: 0 8px 22px rgba(35,57,102,.08) !important;
    overflow-x: auto !important;
    flex-wrap: nowrap !important;
}
div[data-testid="stRadio"] div[role="radiogroup"] label {
    flex: 1 1 0 !important;
    min-width: 0 !important;
    margin: 0 !important;
    white-space: nowrap !important;
    text-align: center !important;
    justify-content: center !important;
    padding: 10px clamp(4px, 0.8vw, 12px) !important;
    font-size: clamp(9px, 1.05vw, 12px) !important;
    box-sizing: border-box !important;
}
@media (max-width: 720px) {
    div[data-testid="stRadio"] { margin: 12px 0 18px !important; }
    div[data-testid="stRadio"] > div[role="radiogroup"] {
        width: 100% !important;
        max-width: 100% !important;
        gap: 2px !important;
        padding: 4px !important;
    }
    div[data-testid="stRadio"] div[role="radiogroup"] label {
        flex: 1 1 0 !important;
        min-width: 0 !important;
        white-space: nowrap !important;
        padding: 9px 3px !important;
        font-size: clamp(8px, 1.65vw, 11px) !important;
    }
}
</style>
""")
