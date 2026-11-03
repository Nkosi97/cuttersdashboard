# Customer Order Dashboard

## Run with Docker

Install Docker Desktop, then run this command from the project folder:

```sh
docker compose up --build
```

Open the cashier screen at [http://localhost:8000/cashier.html](http://localhost:8000/cashier.html). Open [http://localhost:8000/](http://localhost:8000/) on the customer display. Both pages use the same SQLite database and refresh order status automatically.

The `order-data` Docker volume persists order history and statistics if the container restarts or is rebuilt. Back up this volume to retain the data. Do not remove it with `docker compose down -v` unless you intend to delete the stored orders.

## Daily statistics

The cashier screen reports the selected local calendar day:

- Orders added, orders marked ready, and orders collected
- Average preparation time (added to ready)
- Average collection time (ready to collected)
- Order history for that day, including each order's status and event times

Use **Download Excel** to save the selected day as an `.xlsx` workbook. It includes a daily summary, all orders, collected-order details, and a chart of collections by local hour. The collected-order worksheet is also ready for owners to build their own Excel charts.

Order timestamps are stored in UTC. Daily totals use the local day boundaries selected in the cashier's browser. The app starts with an empty order history so sample orders are not counted as real sales.

The dashboard has no user authentication. Keep it on a trusted network; do not expose it directly to the public internet.
# cuttersdashboard
