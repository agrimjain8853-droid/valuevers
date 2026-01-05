from sqlalchemy import Column, Integer, String, Float, DateTime
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class PriceEstimate(Base):
    __tablename__ = "price_estimates"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, index=True, nullable=False)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class FairValueHistory(Base):
    __tablename__ = "fair_value_history"

    id = Column(Integer, primary_key=True, index=True)
    item_id = Column(String, index=True, nullable=False)
    fair_value = Column(Float, nullable=False)
    median = Column(Float, nullable=False)
    trimmed_mean = Column(Float, nullable=False)
    data_points_used = Column(Integer, nullable=False)
    confidence = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
