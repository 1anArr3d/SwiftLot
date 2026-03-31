from pydantic import BaseModel
from typing import Optional


class Auction(BaseModel):
    auction_id: str
    region_id: Optional[str] = None
    seller_name: Optional[str] = None
    auction_status: Optional[str] = None
    vehicles_listed: Optional[int] = None
    last_discovered: Optional[str] = None
    last_scraped_count: Optional[int] = None
    series_key: Optional[str] = None
    minimum_bid: Optional[float] = None
    sales_tax: Optional[float] = None
    ended_at: Optional[str] = None
    closes_at: Optional[str] = None


class Vehicle(BaseModel):
    vin: str
    year: Optional[int] = None
    make: Optional[str] = None
    model: Optional[str] = None
    body_type: Optional[str] = None
    color: Optional[str] = None
    key_status: Optional[str] = None
    catalytic_converter: Optional[str] = None
    start_status: Optional[str] = None
    engine_type: Optional[str] = None
    drivetrain: Optional[str] = None
    fuel_type: Optional[str] = None
    num_cylinders: Optional[str] = None
    documentation_type: Optional[str] = None
    auction_id: Optional[str] = None
    region_id: Optional[str] = None
    seller_id: Optional[str] = None
    item_id: Optional[str] = None
    item_key: Optional[str] = None
    current_bid: Optional[float] = None
    bid_expiration: Optional[str] = None
    reserve_price: Optional[float] = None
    fee_price: Optional[float] = None
    seller_notes: Optional[str] = None
    images: Optional[str] = None
    images_count: Optional[int] = None
    published_at: Optional[str] = None
    last_recorded_odo: Optional[str] = None


class WatchlistVehicle(Vehicle):
    liked_at: Optional[str] = None


class SavedAuction(BaseModel):
    auction_id: str
    region_id: Optional[str] = None
    seller_name: Optional[str] = None
    auction_status: Optional[str] = None
    vehicles_listed: Optional[int] = None
    closes_at: Optional[str] = None
    saved_at: Optional[str] = None


class OdometerEntry(BaseModel):
    row_id: str
    vin: str
    inspection_date: Optional[str] = None
    mileage: Optional[int] = None


class JobStatus(BaseModel):
    id: str
    status: str
