# Kitsap Regional Library — Home Assistant Integration

A custom Home Assistant integration for tracking your [Kitsap Regional Library](https://www.krl.org) account: checked-out items, due dates, overdue books, holds, book cover images, and household member assignments.

## Sensors

### Summary sensors

| Sensor | Description |
|---|---|
| **Items Checked Out** | Total number of currently checked-out items. Attributes include the full list with title, format, due date, cover image URL, and who it's assigned to. |
| **Next Due Date** | The soonest upcoming due date. Shows the cover image of that book as the entity picture. |
| **Overdue Items** | Count of items past their due date. Attributes list each overdue item with days overdue and assigned person. |
| **Holds Ready for Pickup** | Count of holds available at a branch. Attributes include pickup location and expiry date per item. |
| **Holds Waiting** | Count of holds still in queue. |

### Per-book sensors

A dedicated sensor is created automatically for **each checked-out book**. It shows:

- **State**: due date
- **Entity picture**: book cover (from Open Library, using ISBN)
- **Attributes**: title, subtitle, format, days until due, overdue flag, assigned person, image URL, ISBN

The sensor becomes unavailable automatically when the book is returned.

## Household assignments

Multiple people can share one library card. You can assign any checked-out item to a household member using HA services.

### Assigning a book

1. Open **Developer Tools → Services** (or use an automation/script).
2. Call `kitsap_library.assign_item` with:
   - `checkout_id`: found in the `items` attribute of the **Items Checked Out** sensor
   - `person`: name of the household member (e.g. `"Emma"`)

```yaml
service: kitsap_library.assign_item
data:
  checkout_id: "abc123"
  person: "Emma"
```

### Removing an assignment

```yaml
service: kitsap_library.unassign_item
data:
  checkout_id: "abc123"
```

Assignments are stored persistently and survive restarts. When a book is returned, its assignment is cleaned up automatically.

## Installation

1. Copy the `custom_components/kitsap_library/` directory into your Home Assistant config directory:
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
- Your card barcode number is on the back of your library card.
- Book covers are fetched from [Open Library](https://openlibrary.org/dev/docs/api#anchor_covers) using the item's ISBN. Not all items have covers.
- Holds tracking requires the holds API to be available; if it is not, holds sensors will show `0` without error.
