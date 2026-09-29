import os
import requests
from fastapi import FastAPI, HTTPException, Form, Request, Response, UploadFile, File
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from collections import defaultdict
import math
import random

from sqlalchemy import func
from database import SessionLocal
from models import PriceEstimate, FairValueHistory, ActivityRecord
from pricing import fair_value
from datetime import date, timedelta
from pathlib import Path
import uuid


app = FastAPI(title="Fair Value Engine")

# ----------------------------
# Templates & static files
# ----------------------------
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")


# ----------------------------
# HOME
# ----------------------------
@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# ----------------------------
# SUBMIT PRICE
# ----------------------------
@app.post("/submit", response_class=HTMLResponse)
def submit_price(
    request: Request,
    item_id: str = Form(...),
    price_value: float = Form(...),
    price_unit: float = Form(...)
):
    db = SessionLocal()
    try:
        item = item_id.lower().strip()
        price = price_value * price_unit

        if price <= 0:
            raise HTTPException(status_code=400, detail="Invalid price")

        if price > 1_000_000_000_000:
            raise HTTPException(status_code=400, detail="Price unrealistically high")

        db.add(PriceEstimate(item_id=item, price=price))
        db.commit()

        return templates.TemplateResponse(
            "index.html",
            {"request": request, "message": "Price submitted successfully"}
        )
    finally:
        db.close()


# ----------------------------
# API: FAIR VALUE
# ----------------------------
@app.get("/api/fair-value/{item_id}")
def api_fair_value(item_id: str):
    db = SessionLocal()
    try:
        item = item_id.lower().strip()
        rows = db.query(PriceEstimate.price).filter(
            PriceEstimate.item_id == item
        ).all()

        prices = [float(r[0]) for r in rows]

        if len(prices) < 3:
            return {"error": "Not enough data"}

        result = fair_value(prices)

        db.add(
            FairValueHistory(
                item_id=item,
                fair_value=result["fair_value"],
                median=result["median"],
                trimmed_mean=result["trimmed_mean"],
                data_points_used=result["data_points_used"],
                confidence=result["confidence"]
            )
        )
        db.commit()

        return result

    except Exception:
        return {"error": "Temporarily unavailable"}

    finally:
        db.close()


# ----------------------------
# API: CHART DATA
# ----------------------------
@app.get("/chart-data/{item_id}")
def chart_data(item_id: str):
    db = SessionLocal()
    try:
        item = item_id.lower().strip()
        rows = (
            db.query(FairValueHistory)
            .filter(FairValueHistory.item_id == item)
            .order_by(FairValueHistory.timestamp.asc())
            .all()
        )

        if not rows:
            return {"timestamps": [], "fair_value": [], "median": [], "trimmed_mean": []}

        daily = defaultdict(lambda: {"fair_value": [], "median": [], "trimmed_mean": []})

        for r in rows:
            day = r.timestamp.strftime("%Y-%m-%d")
            daily[day]["fair_value"].append(r.fair_value)
            daily[day]["median"].append(r.median)
            daily[day]["trimmed_mean"].append(r.trimmed_mean)

        dates = sorted(daily.keys())

        return {
            "timestamps": dates,
            "fair_value": [round(sum(daily[d]["fair_value"]) / len(daily[d]["fair_value"]), 2) for d in dates],
            "median": [round(sum(daily[d]["median"]) / len(daily[d]["median"]), 2) for d in dates],
            "trimmed_mean": [round(sum(daily[d]["trimmed_mean"]) / len(daily[d]["trimmed_mean"]), 2) for d in dates],
        }

    except Exception:
        return {"timestamps": [], "fair_value": [], "median": [], "trimmed_mean": []}

    finally:
        db.close()


# ----------------------------
# API: FEATURED PRICES
# ----------------------------
@app.get("/featured-prices")
def featured_prices():
    db = SessionLocal()
    try:
        rows = (
            db.query(
                FairValueHistory.item_id,
                FairValueHistory.fair_value,
                FairValueHistory.data_points_used,
                FairValueHistory.timestamp
            )
            .order_by(FairValueHistory.timestamp.desc())
            .limit(2)
            .all()
        )

        return [
            {
                "item_id": r.item_id,
                "fair_value": round(r.fair_value, 2),
                "data_points": r.data_points_used,
                "date": r.timestamp.strftime("%Y-%m-%d")
            }
            for r in rows
        ]

    except Exception:
        return []

    finally:
        db.close()


# ----------------------------
# API: DID YOU KNOW
# ----------------------------
@app.get("/did-you-know")
def did_you_know():
    db = SessionLocal()
    try:
        subq = (
            db.query(
                FairValueHistory.item_id,
                func.max(FairValueHistory.timestamp).label("latest")
            )
            .group_by(FairValueHistory.item_id)
            .subquery()
        )

        rows = (
            db.query(FairValueHistory)
            .join(
                subq,
                (FairValueHistory.item_id == subq.c.item_id) &
                (FairValueHistory.timestamp == subq.c.latest)
            )
            .all()
        )

        if len(rows) < 3:
            return {"text": "More data is needed to generate insights."}

        rows.sort(key=lambda r: r.fair_value, reverse=True)
        insights = []

        history = defaultdict(list)
        all_rows = (
            db.query(FairValueHistory)
            .order_by(FairValueHistory.item_id, FairValueHistory.timestamp.desc())
            .all()
        )

        for r in all_rows:
            history[r.item_id].append(r)

        snapshots = {
            item: {"today": vals[0].fair_value, "yesterday": vals[1].fair_value}
            for item, vals in history.items()
            if len(vals) >= 2
        }

        items = list(snapshots.keys())
        for i in range(len(items)):
            for j in range(i + 1, len(items)):
                a, b = items[i], items[j]
                ay, at = snapshots[a]["yesterday"], snapshots[a]["today"]
                by, bt = snapshots[b]["yesterday"], snapshots[b]["today"]

                if ay < by and at > bt:
                    insights.append(f"{a.replace('_',' ')} just overtook {b.replace('_',' ')}.")
                if by < ay and bt > at:
                    insights.append(f"{b.replace('_',' ')} just overtook {a.replace('_',' ')}.")

        if insights:
            return {"text": random.choice(insights)}

        return {"text": "Crowd valuations are stabilizing across items."}

    except Exception:
        return {"text": "Insight temporarily unavailable."}

    finally:
        db.close()


@app.get("/valuation-glossary", response_class=HTMLResponse)
def valuation_glossary(request: Request):
    return templates.TemplateResponse(
        "valuation_glossary.html",
        {"request": request}
    )


# Serp API --------------

@app.get("/api/market-prices")

def market_prices(q: str):
    SERPAPI_KEY = os.getenv("SERPAPI_KEY")
    
    if not SERPAPI_KEY:
        return {"error": "SERPAPI_KEY not configured"}

    params = {
        "engine": "google_shopping",
        "q": q,
        "gl": "in",
        "hl": "en",
        "api_key": SERPAPI_KEY
    }

    try:
        r = requests.get("https://serpapi.com/search", params=params, timeout=10)
        data = r.json()
    except Exception:
        return {"error": "SERP API unreachable"}

    amazon = None
    flipkart = None

    for item in data.get("shopping_results", []):
        source = (item.get("source") or "").lower()
        price = item.get("extracted_price")
        link = item.get("link")
        title = item.get("title")

        if not price:
            continue

        if "amazon" in source and not amazon:
            amazon = {"price": price, "title": title, "url": link}

        if "flipkart" in source and not flipkart:
            flipkart = {"price": price, "title": title, "url": link}

    return {
        "amazon": amazon,
        "flipkart": flipkart
    }

# ----------------------------
# ACTIVITY TRACKER
# ----------------------------
ACTIVITIES = ["Gym", "Eating", "Utensils", "Grooming"]
PROOF_DIR = Path("static/activity_proofs")
PROOF_DIR.mkdir(parents=True, exist_ok=True)

@app.get("/activity-tracker", response_class=HTMLResponse)
def activity_tracker_page(request: Request):
    return templates.TemplateResponse("activity_tracker.html", {"request": request})


def _ensure_activity_table(db):
    ActivityRecord.__table__.create(bind=db.get_bind(), checkfirst=True)


def _tracker_dates():
    # Seven-day rolling window ending today.
    today = date.today()
    return [(today - timedelta(days=i)).isoformat() for i in range(6, -1, -1)]


@app.get("/api/activity-tracker")
def activity_tracker_data():
    db = SessionLocal()
    try:
        _ensure_activity_table(db)
        dates = _tracker_dates()
        rows = db.query(ActivityRecord).filter(ActivityRecord.activity_date.in_(dates)).all()
        records = {}
        for row in rows:
            records[f"{row.activity}|{row.activity_date}"] = {
                "activity": row.activity,
                "date": row.activity_date,
                "proof_image_url": row.proof_image_url,
                "score": row.invigilator_score,
            }
        return {"dates": dates, "activities": ACTIVITIES, "records": records}
    finally:
        db.close()


@app.post("/api/activity-tracker/proof")
async def upload_activity_proof(
    activity: str = Form(...),
    activity_date: str = Form(...),
    proof: UploadFile = File(...),
):
    if activity not in ACTIVITIES:
        raise HTTPException(status_code=400, detail="Invalid activity")
    try:
        selected_date = date.fromisoformat(activity_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date")
    if selected_date not in [date.fromisoformat(d) for d in _tracker_dates()]:
        raise HTTPException(status_code=400, detail="Date is outside the current 7-day window")
    if not proof.content_type or not proof.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Please upload an image")

    content = await proof.read()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Image must be 8 MB or smaller")

    suffix = Path(proof.filename or "proof.jpg").suffix.lower() or ".jpg"
    if suffix not in {".jpg", ".jpeg", ".png", ".webp", ".gif"}:
        suffix = ".jpg"
    filename = f"{activity.lower()}_{activity_date}_{uuid.uuid4().hex}{suffix}"
    target = PROOF_DIR / filename
    target.write_bytes(content)

    db = SessionLocal()
    try:
        _ensure_activity_table(db)
        row = db.query(ActivityRecord).filter(
            ActivityRecord.activity == activity,
            ActivityRecord.activity_date == activity_date
        ).first()
        if row is None:
            row = ActivityRecord(activity=activity, activity_date=activity_date)
            db.add(row)
        elif row.proof_image_url:
            old_path = Path(row.proof_image_url.lstrip("/"))
            if old_path.exists():
                old_path.unlink(missing_ok=True)

        row.proof_image_url = f"/static/activity_proofs/{filename}"
        db.commit()
        return {"success": True, "proof_image_url": row.proof_image_url}
    finally:
        db.close()


@app.post("/api/activity-tracker/score")
def save_activity_score(activity: str = Form(...), activity_date: str = Form(...), score: int = Form(...)):
    if activity not in ACTIVITIES:
        raise HTTPException(status_code=400, detail="Invalid activity")
    if score < 0 or score > 10:
        raise HTTPException(status_code=400, detail="Score must be between 0 and 10")
    try:
        selected_date = date.fromisoformat(activity_date)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date")
    if selected_date not in [date.fromisoformat(d) for d in _tracker_dates()]:
        raise HTTPException(status_code=400, detail="Date is outside the current 7-day window")

    db = SessionLocal()
    try:
        _ensure_activity_table(db)
        row = db.query(ActivityRecord).filter(
            ActivityRecord.activity == activity,
            ActivityRecord.activity_date == activity_date
        ).first()
        if row is None:
            row = ActivityRecord(activity=activity, activity_date=activity_date)
            db.add(row)
        row.invigilator_score = score
        db.commit()
        return {"success": True, "score": score}
    finally:
        db.close()


# ----------------------------
# HEALTH (KEEP ALIVE)
# ----------------------------
@app.api_route("/health", methods=["GET", "HEAD"])
def health(response: Response):
    return {"status": "ok"}

