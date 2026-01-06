from fastapi import FastAPI, HTTPException, Form, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles

from collections import defaultdict
import math
import random

from sqlalchemy import func
from database import SessionLocal
from models import PriceEstimate, FairValueHistory
from pricing import fair_value


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


# ----------------------------
# HEALTH (KEEP ALIVE)
# ----------------------------
@app.api_route("/health", methods=["GET", "HEAD"])
def health(response: Response):
    return {"status": "ok"}
