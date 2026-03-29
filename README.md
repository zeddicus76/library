# Kitsap Regional Library — Home Assistant Integration

A custom Home Assistant integration for tracking your [Kitsap Regional Library](https://www.krl.org) account: checked-out items, due dates, overdue books, and holds.

## Sensors

| Sensor | Description |
|---|---|
| **Items Checked Out** | Total number of currently checked-out items. Attributes include the full list with title, format, and due date. |
| **Next Due Date** | The soonest upcoming due date across all checkouts. Attributes include days until due and which items are due that day. |
| **Overdue Items** | Count of items past their due date. Attributes list each overdue item and how many days overdue. |
| **Holds Ready for Pickup** | Count of holds available at a branch. Attributes include pickup location and expiry date per item. |
| **Holds Waiting** | Count of holds still in queue. |

## Installation

1. Copy the `custom_components/kitsap_library/` directory into your Home Assistant config directory so the path looks like:
   ```
   config/
   └── custom_components/
       └── kitsap_library/
   ```
2. Restart Home Assistant.
3. Go to **Settings → Devices & Services → Add Integration**.
4. Search for **Kitsap Regional Library**.
5. Enter your KRL card number (or username) and PIN — the same credentials you use at [krl.org](https://www.krl.org).

## Notes

- Data refreshes every hour.
- Your card barcode number can be found on the back of your library card.
- Holds tracking requires the holds API to be available; if it is not, holds sensors will show `0` without error.
