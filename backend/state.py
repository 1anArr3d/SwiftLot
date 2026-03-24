# Shared in-memory job status tracking
# auction_id / state_key -> "running" | "done" | "failed"

scrape_status: dict[str, str] = {}
discovery_status: dict[str, str] = {}
inspection_status: dict[str, str] = {}
