DOMAIN = "kitsap_library"

LIBRARY_SUBDOMAIN = "krl"
LOGIN_URL = "https://krl.bibliocommons.com/user/login"
GATEWAY_BASE = "https://gateway.bibliocommons.com/v2/libraries"
CHECKOUTS_URL = f"{GATEWAY_BASE}/{LIBRARY_SUBDOMAIN}/checkouts"
HOLDS_URL = f"{GATEWAY_BASE}/{LIBRARY_SUBDOMAIN}/holds"

CONF_USERNAME = "username"
CONF_PASSWORD = "password"

SCAN_INTERVAL_HOURS = 1

SENSOR_ITEMS_CHECKED_OUT = "items_checked_out"
SENSOR_NEXT_DUE_DATE = "next_due_date"
SENSOR_OVERDUE_ITEMS = "overdue_items"
SENSOR_HOLDS_READY = "holds_ready"
SENSOR_HOLDS_WAITING = "holds_waiting"
