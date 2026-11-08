# Customer Order Dashboard

## Run with Docker

Install Docker Desktop, then run this command from the project folder:

```sh
docker compose up --build
```

Open the cashier screen at [http://localhost:8080/cashier.html](http://localhost:8080/cashier.html). Open [http://localhost:8080/](http://localhost:8080/) on the customer display. Both pages use the same SQLite database and refresh order status automatically.

The `order-data` Docker volume persists order history and statistics if the container restarts or is rebuilt. Back up this volume to retain the data. Do not remove it with `docker compose down -v` unless you intend to delete the stored orders.

## Deploy to Railway

1. In Railway, create a project and deploy this GitHub repository as a service. Railway will build the included `Dockerfile`. To verify an existing connection, check that the service's source repository and branch point to this repository and that a deployment has completed successfully. The repository itself cannot show whether it is linked to a Railway project.
2. Add a volume to the service and set its mount path to `/data`. The app stores the SQLite database at `/data/orders.sqlite3`; without the volume, order data will not persist across redeploys.
3. Generate a public domain in the service's **Settings → Networking**. The customer display is at `/`, and the cashier screen is at `/cashier.html`.

Both screens and the order API are public, and the app has no authentication. Anyone with the domain can view orders and use the cashier screen to change them. Do not expose it publicly or use it for sensitive customer information unless you add appropriate access controls.

## Daily statistics

The cashier screen reports the selected local calendar day:

- Orders added, orders marked ready, and orders collected
- Average preparation time (added to ready)
- Average collection time (ready to collected)
- Order history for that day, including each order's status and event times

Use **Download Excel** to save the selected day as an `.xlsx` workbook. It includes a daily summary, all orders, collected-order details, and a chart of collections by local hour. The collected-order worksheet is also ready for owners to build their own Excel charts.

Order timestamps are stored in UTC. Daily totals use the local day boundaries selected in the cashier's browser. The app starts with an empty order history so sample orders are not counted as real sales.

The dashboard has no user authentication. Keep it on a trusted network or add appropriate access controls before exposing it to the public internet.
# cuttersdashboard
