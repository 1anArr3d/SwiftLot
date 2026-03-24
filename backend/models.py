from pydantic import BaseModel
from typing import Optional


class Auction(BaseModel):
    auction_id: str
    region_id: Optional[str] = None
    seller_name: Optional[str] = None
    auction_status: Optional[str] = None
    vehicles_listed: Optional[int] = None
    auction_date: Optional[str] = None
    last_discovered: Optional[str] = None
    last_scraped_count: Optional[int] = None


class Vehicle(BaseModel):
    vin: str
    year: Optional[str] = None
    make: Optional[str] = None
    model: Optional[str] = None
    color: Optional[str] = None
    key_status: Optional[str] = None
    catalytic_converter: Optional[str] = None
    start_status: Optional[str] = None
    engine_type: Optional[str] = None
    transmission: Optional[str] = None
    auction_id: Optional[str] = None
    city: Optional[str] = None
    last_recorded_odo: Optional[str] = None
    images: Optional[str] = None


class WatchlistVehicle(Vehicle):
    liked_at: Optional[str] = None


class OdometerEntry(BaseModel):
    row_id: str
    vin: str
    inspection_date: Optional[str] = None
    mileage: Optional[int] = None


class JobStatus(BaseModel):
    id: str
    status: str
