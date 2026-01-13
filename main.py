from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime, timedelta
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import pandas as pd
import requests
import json
import os
import math

# ================= APP SETUP =================

app = FastAPI(title="Hackathon & Contest Tracker")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

CSV_FILE = "/tmp/unstop_hackathons.csv"

# ================= UTILITIES =================

def sanitize_json(data):
    """Remove NaN / inf values before JSON serialization"""
    if isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return ""
        return data
    if isinstance(data, dict):
        return {k: sanitize_json(v) for k, v in data.items()}
    if isinstance(data, list):
        return [sanitize_json(i) for i in data]
    return data


def parse_datetime_safe(date_str):
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M")
    except Exception:
        return None


# ================= UNSTOP SCRAPER =================

def fetch_and_save_unstop_hackathons(csv_path=CSV_FILE, pages=5):
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/json",
        "Referer": "https://unstop.com",
        "Origin": "https://unstop.com",
    }

    hackathons = []

    for status in ["open", "expired"]:
        for page in range(1, pages + 1):
            url = (
                "https://unstop.com/api/public/opportunity/search-result"
                f"?opportunity=hackathons&page={page}&per_page=10"
                f"&oppstatus={status}&course=6&usertype=students"
            )
            try:
                resp = requests.get(url, headers=headers, timeout=10)
                resp.raise_for_status()
                data = resp.json()
            except Exception as e:
                print("Unstop API error:", e)
                continue

            for item in data.get("data", {}).get("data", []):
                hackathons.append({
                    "Title": item.get("title", ""),
                    "Start Date": item.get("start_date", ""),
                    "End Date": item.get("end_date", ""),
                    "Apply Link": item.get("seo_url", ""),
                    "Status": status,
                })

    pd.DataFrame(hackathons).to_csv(csv_path, index=False)
    print(f"✅ Saved {len(hackathons)} hackathons")


def load_hackathons_df():
    if os.path.exists(CSV_FILE):
        return pd.read_csv(CSV_FILE).fillna("")
    return pd.DataFrame()


def get_hackathons():
    df = load_hackathons_df()
    results = []

    for _, row in df.iterrows():
        results.append({
            "title": row.get("Title", ""),
            "platform": "Unstop",
            "start_date": row.get("Start Date", ""),
            "end_date": row.get("End Date", ""),
            "apply_link": row.get("Apply Link", ""),
            "category": "hackathon",
            "status": row.get("Status", ""),
        })

    return results


# ================= CODEFORCES =================

CODEFORCES_CACHE = {"data": [], "time": None}
CACHE_TTL = timedelta(minutes=10)

def fetch_codeforces_contests():
    contests = []
    try:
        res = requests.get("https://codeforces.com/api/contest.list", timeout=10)
        data = res.json().get("result", [])
        for c in data:
            start = datetime.utcfromtimestamp(c["startTimeSeconds"])
            end = start + timedelta(seconds=c.get("durationSeconds", 0))
            contests.append({
                "title": c["name"],
                "platform": "Codeforces",
                "start_date": start.strftime("%Y-%m-%d %H:%M"),
                "end_date": end.strftime("%Y-%m-%d %H:%M"),
                "apply_link": f"https://codeforces.com/contest/{c['id']}",
                "category": "contest",
                "phase": c.get("phase", ""),
            })
    except Exception as e:
        print("Codeforces error:", e)
    return contests


def get_codeforces_cached():
    now = datetime.utcnow()
    if CODEFORCES_CACHE["time"] and now - CODEFORCES_CACHE["time"] < CACHE_TTL:
        return CODEFORCES_CACHE["data"]

    data = fetch_codeforces_contests()
    CODEFORCES_CACHE["data"] = data
    CODEFORCES_CACHE["time"] = now
    return data


# ================= CODECHEF =================

def fetch_codechef_contests():
    contests = []
    path = "codechef_contests.json"

    if not os.path.exists(path):
        return contests

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    for c in data.get("future_contests", []) + data.get("past_contests", []):
        contests.append({
            "title": c.get("contest_name", ""),
            "platform": "CodeChef",
            "start_date": c.get("contest_start_date_iso", "").replace("T", " "),
            "end_date": c.get("contest_end_date_iso", "").replace("T", " "),
            "apply_link": f"https://www.codechef.com/{c.get('contest_code', '')}",
            "category": "contest",
        })

    return contests


# ================= FILTER =================

def filter_by_status(items, status):
    now = datetime.utcnow()
    result = []

    for c in items:
        if c["category"] == "hackathon":
            if status == "live" and c["status"] == "open":
                result.append(c)
            elif status == "past" and c["status"] == "expired":
                result.append(c)
        else:
            start = parse_datetime_safe(c.get("start_date", ""))
            end = parse_datetime_safe(c.get("end_date", ""))
            phase = c.get("phase", "").upper()

            if status == "upcoming" and start and start > now:
                result.append(c)
            elif status == "live" and ((start and end and start <= now <= end) or phase == "CODING"):
                result.append(c)
            elif status == "past" and end and end < now:
                result.append(c)

    return result


# ================= SCHEDULER =================

scheduler = BackgroundScheduler(timezone="Asia/Kolkata")

def daily_scrape_job():
    print("⏰ Running daily Unstop scrape")
    fetch_and_save_unstop_hackathons(CSV_FILE)

scheduler.add_job(
    daily_scrape_job,
    CronTrigger(hour=5, minute=0),
    id="daily_unstop",
    replace_existing=True
)

@app.on_event("startup")
def startup():
    if not os.path.exists(CSV_FILE):
        daily_scrape_job()
    scheduler.start()
    print("🟢 Scheduler started")


# ================= ROUTES =================

@app.get("/")
def home():
    return {"message": "Hackathon Tracker running 🚀"}


@app.get("/api/all")
def get_all(type: str = Query(None), status: str = Query(None)):
    all_items = []

    try:
        all_items += get_hackathons()
    except Exception as e:
        print("Hackathon read error:", e)

    try:
        all_items += get_codeforces_cached()
    except Exception as e:
        print("Codeforces error:", e)

    try:
        all_items += fetch_codechef_contests()
    except Exception as e:
        print("CodeChef error:", e)

    if type:
        all_items = [c for c in all_items if c["category"] == type]

    if status:
        all_items = filter_by_status(all_items, status)

    return sanitize_json(all_items)
