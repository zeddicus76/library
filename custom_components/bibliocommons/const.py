DOMAIN = "bibliocommons"

GATEWAY_BASE = "https://gateway.bibliocommons.com/v2/libraries"

CONF_LIBRARY_SUBDOMAIN = "library_subdomain"
CONF_LIBRARY_NAME = "library_name"
CONF_USERNAME = "username"
CONF_PASSWORD = "password"

SCAN_INTERVAL_HOURS = 1

SENSOR_ITEMS_CHECKED_OUT = "items_checked_out"
SENSOR_NEXT_DUE_DATE = "next_due_date"
SENSOR_OVERDUE_ITEMS = "overdue_items"
SENSOR_HOLDS_READY = "holds_ready"
SENSOR_HOLDS_WAITING = "holds_waiting"


def login_url(subdomain: str) -> str:
    return f"https://{subdomain}.bibliocommons.com/user/login"


def checkouts_url(subdomain: str) -> str:
    return f"{GATEWAY_BASE}/{subdomain}/checkouts"


def holds_url(subdomain: str) -> str:
    return f"{GATEWAY_BASE}/{subdomain}/holds"
