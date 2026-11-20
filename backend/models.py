from pydantic import BaseModel
from typing import Optional


class Auction(BaseModel):
    auction_id: str
    region_id: Optional[str] = None
    seller_name: Optional[str] = None
    seller_city: Optional[str] = None
    seller_state: Optional[str] = None
    auction_status: Optional[str] = None
    vehicles_listed: Optional[int] = None
    last_discovered: Optional[str] = None
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
    min_bid: Optional[float] = None
    reserve_met: Optional[bool] = None
    bidding_status: Optional[str] = None
    bidding_start: Optional[str] = None
    run_number: Optional[int] = None
    platform_fee_rate: Optional[float] = None
    platform_fee_min: Optional[float] = None
    platform_fee_max: Optional[float] = None
    card_fee_rate: Optional[float] = None
    extra_fees: Optional[float] = None
    seller_notes: Optional[str] = None
    images: Optional[str] = None
    images_count: Optional[int] = None
    published_at: Optional[str] = None
    last_recorded_odo: Optional[str] = None
    autura_odo: Optional[int] = None
    autura_odo_at: Optional[str] = None
    odo_rollback: Optional[bool] = False
    seller_name: Optional[str] = None
    closes_at: Optional[str] = None


class GarageVehicle(Vehicle):
    liked_at: Optional[str] = None


