from fastapi import FastAPI, Query
from fastapi.responses import  JSONResponse

import pandas as pd
import requests
import json
from datetime import datetime, timedelta
import os
from fastapi.middleware.cors import CORSMiddleware



app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # or ["http://127.0.0.1:5500"] if using Live Server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
def home():
    return {"message": "Hackathon Tracker is running 🚀"}

CSV_FILE = "/tmp/unstop_hackathons.csv"


# ------------------- Unstop Hackathons -------------------
def fetch_and_save_unstop_hackathons(csv_path=CSV_FILE, pages=5):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json, text/plain, */*",
        "Referer": "https://unstop.com/hackathons",
        "Origin": "https://unstop.com"
    }

    hackathons = []
    for status in ["open", "expired"]:
        for page in range(1, pages + 1):
            url = f"https://unstop.com/api/public/opportunity/search-result?opportunity=hackathons&page={page}&per_page=10&oppstatus={status}&course=6&usertype=students"
            resp = requests.get(url, headers=headers)
            data = resp.json()

            for item in data["data"]["data"]:
                hackathons.append({
                    "Title": item.get("title"),
                    "Start Date": item.get("start_date", "N/A"),
                    "End Date": item.get("end_date", "N/A"),
                    "Apply Link": item.get("seo_url"),
                    "Status": status
                })

    df = pd.DataFrame(hackathons)
    df.to_csv(csv_path, index=False)
    print("Saved", len(hackathons), "hackathons.")


# Fetch once at startup
fetch_and_save_unstop_hackathons(CSV_FILE)
hackathons_df = pd.read_csv(CSV_FILE) if os.path.exists(CSV_FILE) else pd.DataFrame()


def get_hackathons():
    hackathons = []
    for _, row in hackathons_df.iterrows():
        def parse_date(date_str):
            if not date_str or date_str == "N/A":
                return ""
            try:
                dt = pd.to_datetime(date_str)
                dt = dt.tz_localize(None) if dt.tzinfo else dt
                return dt.strftime("%Y-%m-%d %H:%M")
            except Exception:
                return date_str

        hackathons.append({
            "title": row.get("Title", "No Title"),
            "platform": "Unstop",
            "start_date": parse_date(row.get("Start Date", "")),
            "end_date": parse_date(row.get("End Date", "")),
            "apply_link": row.get("Apply Link", "#"),
            "category": "hackathon",
            "status": row.get("Status", "")
        })
    return hackathons


# ------------------- Codeforces -------------------
def fetch_codeforces_contests():
    contests = []
    try:
        url = "https://codeforces.com/api/contest.list"
        res = requests.get(url)
        data = res.json().get("result", [])
        for c in data:
            start_time = datetime.utcfromtimestamp(c["startTimeSeconds"])
            end_time = start_time + timedelta(seconds=c.get("durationSeconds", 0))
            contests.append({
                "title": c["name"],
                "platform": "Codeforces",
                "start_date": start_time.strftime("%Y-%m-%d %H:%M"),
                "end_date": end_time.strftime("%Y-%m-%d %H:%M"),
                "apply_link": f"https://codeforces.com/contests/{c['id']}",
                "category": "contest",
                "phase": c.get("phase", "")
            })
    except Exception as e:
        print("Error fetching Codeforces:", e)
    return contests


# ------------------- CodeChef -------------------
def fetch_codechef_contests():
    contests = []
    file_path = "codechef_contests.json"
    if os.path.exists(file_path):
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        for c in data.get("future_contests", []) + data.get("past_contests", []):
            contests.append({
                "title": c.get("contest_name"),
                "platform": "CodeChef",
                "start_date": c.get("contest_start_date_iso", "").replace("T", " "),
                "end_date": c.get("contest_end_date_iso", "").replace("T", " "),
                "apply_link": f"https://www.codechef.com/{c.get('contest_code')}",
                "category": "contest",
            })
    return contests


# ------------------- Filter Logic -------------------
def parse_datetime_safe(date_str):
    """Try parsing YYYY-MM-DD HH:MM safely."""
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    except Exception:
        return None


def filter_by_status(contests, status):
    now = datetime.utcnow()
    filtered = []

    for c in contests:
        if c["category"] == "hackathon":
            hack_status = c.get("status", "").lower()
            if status == "live" and hack_status == "open":
                filtered.append(c)
            elif status == "past" and hack_status == "expired":
                filtered.append(c)

        else:  # contests (Codeforces, CodeChef)
            start = parse_datetime_safe(c.get("start_date", ""))
            end = parse_datetime_safe(c.get("end_date", ""))
            phase = c.get("phase", "").upper() if "phase" in c else ""

            if status == "upcoming":
                if start and start > now:
                    filtered.append(c)
            elif status == "live":
                # Either within time range OR Codeforces says CODING
                if (start and end and start <= now <= end) or phase == "CODING":
                    filtered.append(c)
            elif status == "past":
                if end and end < now:
                    filtered.append(c)

    return filtered


# ------------------- Unified API -------------------
@app.get("/api/all")
def get_all_contests(
        type: str = Query(None, description="hackathon or contest"),
        status: str = Query(None, description="upcoming, live or past")
):
    hackathons = get_hackathons()
    codeforces = fetch_codeforces_contests()
    codechef = fetch_codechef_contests()

    all_contests = hackathons + codeforces + codechef

    if type:
        all_contests = [c for c in all_contests if c["category"] == type]

    if status:
        all_contests = filter_by_status(all_contests, status)

    return JSONResponse(all_contests)
