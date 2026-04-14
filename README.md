# BiblioCommons Library Monitor — Home Assistant Integration

A custom Home Assistant integration for tracking library books at **any library that uses [BiblioCommons](https://www.bibliocommons.com/libraries-we-work-with)** — including Boston Public Library, Seattle Public Library, San Francisco Public Library, and hundreds more.

Tracks checked-out items, due dates, overdue books, holds, book cover images, and household member assignments.

## Finding your library's subdomain

Your library's BiblioCommons subdomain is the prefix in your catalog URL. For example:

| Library | Catalog URL | Subdomain |
|---|---|---|
| Boston Public Library | `bpl.bibliocommons.com` | `bpl` |
| Seattle Public Library | `seattle.bibliocommons.com` | `seattle` |
| San Francisco Public Library | `sfpl.bibliocommons.com` | `sfpl` |

See the full list at [bibliocommons.com/libraries-we-work-with](https://www.bibliocommons.com/libraries-we-work-with).

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

Call `bibliocommons.assign_item` with the `checkout_id` from the book sensor's attributes:

```yaml
service: bibliocommons.assign_item
data:
  checkout_id: "abc123"
  person: "Gavin"
```

### Removing an assignment

```yaml
service: bibliocommons.unassign_item
data:
  checkout_id: "abc123"
```

Assignments persist across restarts and are cleaned up automatically when a book is returned.

## Installation

### Option A — HACS (recommended)

1. In Home Assistant, open **HACS** from the sidebar.
2. Go to **Integrations** and click the three-dot menu (⋮) in the top-right corner.
3. Choose **Custom repositories**.
4. Paste the repository URL and set the category to **Integration**, then click **Add**.
5. Close the dialog. Search for **BiblioCommons Library** in the HACS Integrations list and click it.
6. Click **Download** and confirm.
7. **Restart Home Assistant.**
8. Go to **Settings → Devices & Services → Add Integration**, search for **BiblioCommons Library**, and follow the setup prompts.

### Option B — Manual

1. Copy the `custom_components/bibliocommons/` directory into your Home Assistant config directory:
   ```
   config/
   └── custom_components/
       └── bibliocommons/
   ```
2. **Restart Home Assistant.**
3. Go to **Settings → Devices & Services → Add Integration**, search for **BiblioCommons Library**, and follow the setup prompts.

### Setup prompts

When adding the integration you will be asked for:
- **Library Subdomain** — e.g. `krl` for Kitsap Regional Library (see table above)
- **Card Number / Username** — your library card barcode or account username
- **PIN / Password** — your library account PIN

The integration will automatically detect and display your library's full name.

## Notes

- Data refreshes every hour.
- Book covers are fetched from [Open Library](https://openlibrary.org/dev/docs/api#anchor_covers) using the item's ISBN. Not all items have covers.
- Holds tracking requires the holds API endpoint to be available for your library; if unavailable, holds sensors show `0` without error.
- Multiple library accounts (even across different BiblioCommons libraries) can be configured simultaneously.
