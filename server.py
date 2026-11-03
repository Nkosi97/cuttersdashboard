import json
import mimetypes
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from openpyxl import Workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Font, PatternFill


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(
    os.environ.get("DB_PATH", ROOT.parent / f"{ROOT.name}-data" / "orders.sqlite3")
)
PORT = int(os.environ.get("PORT", "8000"))
HOST = os.environ.get("HOST", "127.0.0.1")
ORDER_ROUTE = re.compile(r"^/api/orders/(\d+)(/ready)?$")


def connect_database():
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


@contextmanager
def database():
    connection = connect_database()
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize_database():
    with database() as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS orders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                order_number INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                ready_at TEXT,
                collected_at TEXT
            )
            """
        )
        connection.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_order_per_number
            ON orders (order_number)
            WHERE collected_at IS NULL
            """
        )


def current_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_timestamp(value):
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise ValueError("Start and end must be valid ISO timestamps.")
    if timestamp.tzinfo is None:
        raise ValueError("Start and end must include a timezone.")
    return timestamp.astimezone(timezone.utc)


class DashboardHandler(BaseHTTPRequestHandler):
    def send_json(self, status, payload):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                raise ValueError("Request body must be valid JSON under 16 KB.")
            payload = json.loads(self.rfile.read(length))
        except (ValueError, json.JSONDecodeError):
            raise ValueError("Request body must contain valid JSON.")
        if not isinstance(payload, dict):
            raise ValueError("Request body must be a JSON object.")
        return payload

    def do_GET(self):
        request = urlsplit(self.path)
        if request.path == "/api/orders":
            self.get_orders()
        elif request.path == "/api/orders/history":
            self.get_order_history(parse_qs(request.query))
        elif request.path == "/api/stats":
            self.get_statistics(parse_qs(request.query))
        elif request.path == "/api/reports/daily.xlsx":
            self.export_daily_report(parse_qs(request.query))
        else:
            self.serve_static(request.path)

    def get_orders(self):
        with database() as connection:
            rows = connection.execute(
                """
                SELECT id, order_number, ready_at
                FROM orders
                WHERE collected_at IS NULL
                ORDER BY id
                """
            ).fetchall()
        orders = {"preparing": [], "ready": []}
        for row in rows:
            status = "ready" if row["ready_at"] else "preparing"
            orders[status].append(
                {"id": row["id"], "orderNumber": row["order_number"]}
            )
        self.send_json(200, orders)

    def get_order_history(self, query):
        try:
            start = parse_timestamp(query["start"][0])
            end = parse_timestamp(query["end"][0])
        except (KeyError, IndexError, ValueError) as error:
            self.send_json(400, {"error": str(error) or "A date range is required."})
            return

        if end <= start:
            self.send_json(400, {"error": "End time must be after start time."})
            return

        with database() as connection:
            rows = connection.execute(
                """
                SELECT
                    id,
                    order_number,
                    created_at,
                    ready_at,
                    collected_at,
                    CASE
                        WHEN collected_at IS NOT NULL THEN 'collected'
                        WHEN ready_at IS NOT NULL THEN 'ready'
                        ELSE 'preparing'
                    END AS status
                FROM orders
                WHERE julianday(created_at) >= julianday(?)
                    AND julianday(created_at) < julianday(?)
                ORDER BY created_at DESC, id DESC
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()

        self.send_json(
            200,
            {
                "orders": [
                    {
                        "id": row["id"],
                        "orderNumber": row["order_number"],
                        "createdAt": row["created_at"],
                        "readyAt": row["ready_at"],
                        "collectedAt": row["collected_at"],
                        "status": row["status"],
                    }
                    for row in rows
                ]
            },
        )

    def get_statistics(self, query):
        try:
            start = parse_timestamp(query["start"][0])
            end = parse_timestamp(query["end"][0])
        except (KeyError, IndexError, ValueError) as error:
            self.send_json(400, {"error": str(error) or "A date range is required."})
            return

        if end <= start:
            self.send_json(400, {"error": "End time must be after start time."})
            return

        with database() as connection:
            stats = connection.execute(
                """
                SELECT
                    COUNT(*) AS total_orders,
                    COUNT(ready_at) AS ready_orders,
                    COUNT(collected_at) AS collected_orders,
                    AVG(
                        CASE WHEN ready_at IS NOT NULL
                        THEN (julianday(ready_at) - julianday(created_at)) * 86400
                        END
                    ) AS average_preparation_seconds,
                    AVG(
                        CASE WHEN collected_at IS NOT NULL
                        THEN (julianday(collected_at) - julianday(ready_at)) * 86400
                        END
                    ) AS average_collection_seconds
                FROM orders
                WHERE julianday(created_at) >= julianday(?)
                    AND julianday(created_at) < julianday(?)
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchone()

        self.send_json(
            200,
            {
                "totalOrders": stats["total_orders"],
                "readyOrders": stats["ready_orders"],
                "collectedOrders": stats["collected_orders"],
                "averagePreparationSeconds": stats["average_preparation_seconds"],
                "averageCollectionSeconds": stats["average_collection_seconds"],
            },
        )

    def export_daily_report(self, query):
        try:
            start = parse_timestamp(query["start"][0])
            end = parse_timestamp(query["end"][0])
            local_timezone = ZoneInfo(query.get("timezone", ["UTC"])[0])
        except (KeyError, IndexError, ValueError, ZoneInfoNotFoundError) as error:
            self.send_json(400, {"error": str(error) or "A valid date range is required."})
            return

        if end <= start:
            self.send_json(400, {"error": "End time must be after start time."})
            return

        with database() as connection:
            rows = connection.execute(
                """
                SELECT id, order_number, created_at, ready_at, collected_at,
                    CASE
                        WHEN collected_at IS NOT NULL THEN 'collected'
                        WHEN ready_at IS NOT NULL THEN 'ready'
                        ELSE 'preparing'
                    END AS status
                FROM orders
                WHERE julianday(created_at) >= julianday(?)
                    AND julianday(created_at) < julianday(?)
                ORDER BY created_at, id
                """,
                (start.isoformat(), end.isoformat()),
            ).fetchall()

        def parse_local(value):
            if value is None:
                return None
            return datetime.fromisoformat(value).astimezone(local_timezone)

        orders = []
        collected_orders = []
        collected_by_hour = [0] * 24
        preparation_seconds = []
        collection_seconds = []

        for row in rows:
            created_at = datetime.fromisoformat(row["created_at"])
            ready_at = datetime.fromisoformat(row["ready_at"]) if row["ready_at"] else None
            collected_at = datetime.fromisoformat(row["collected_at"]) if row["collected_at"] else None
            preparation = (
                (ready_at - created_at).total_seconds() if ready_at else None
            )
            collection = (
                (collected_at - ready_at).total_seconds()
                if collected_at and ready_at
                else None
            )
            if preparation is not None:
                preparation_seconds.append(preparation)
            if collection is not None:
                collection_seconds.append(collection)

            order = {
                "number": row["order_number"],
                "status": row["status"],
                "created": parse_local(row["created_at"]),
                "ready": parse_local(row["ready_at"]),
                "collected": parse_local(row["collected_at"]),
                "preparation": round(preparation / 60, 2) if preparation is not None else None,
                "collection": round(collection / 60, 2) if collection is not None else None,
            }
            orders.append(order)
            if order["collected"]:
                order["collected_hour"] = order["collected"].hour
                collected_by_hour[order["collected_hour"]] += 1
                collected_orders.append(order)

        report_date = start.astimezone(local_timezone).date().isoformat()
        workbook = Workbook()
        summary = workbook.active
        summary.title = "Daily Summary"
        summary.append([f"Daily Order Report - {report_date}"])
        summary.merge_cells("A1:B1")
        summary["A1"].font = Font(size=16, bold=True, color="FFFFFF")
        summary["A1"].fill = PatternFill("solid", fgColor="17324D")
        summary.append([])
        summary.append(["Metric", "Value"])
        summary_rows = [
            ("Orders added", len(orders)),
            ("Orders marked ready", sum(order["ready"] is not None for order in orders)),
            ("Orders collected", len(collected_orders)),
            (
                "Average preparation (minutes)",
                round(sum(preparation_seconds) / len(preparation_seconds) / 60, 2)
                if preparation_seconds
                else None,
            ),
            (
                "Average ready to collected (minutes)",
                round(sum(collection_seconds) / len(collection_seconds) / 60, 2)
                if collection_seconds
                else None,
            ),
        ]
        for metric in summary_rows:
            summary.append(metric)
        summary["A3"].font = Font(bold=True, color="FFFFFF")
        summary["B3"].font = Font(bold=True, color="FFFFFF")
        summary["A3"].fill = PatternFill("solid", fgColor="287271")
        summary["B3"].fill = PatternFill("solid", fgColor="287271")
        summary.column_dimensions["A"].width = 38
        summary.column_dimensions["B"].width = 22
        summary.column_dimensions["C"].width = 3
        summary.column_dimensions["D"].width = 16

        order_sheet = workbook.create_sheet("Orders")
        order_sheet.append(
            [
                "Order Number",
                "Status",
                "Added At (Local)",
                "Ready At (Local)",
                "Collected At (Local)",
                "Preparation (Minutes)",
                "Ready to Collected (Minutes)",
            ]
        )
        for order in orders:
            order_sheet.append(
                [
                    order["number"],
                    order["status"],
                    order["created"].replace(tzinfo=None),
                    order["ready"].replace(tzinfo=None) if order["ready"] else None,
                    order["collected"].replace(tzinfo=None) if order["collected"] else None,
                    order["preparation"],
                    order["collection"],
                ]
            )

        collected_sheet = workbook.create_sheet("Collected Orders")
        collected_sheet.append(
            [
                "Order Number",
                "Added At (Local)",
                "Ready At (Local)",
                "Collected At (Local)",
                "Preparation (Minutes)",
                "Ready to Collected (Minutes)",
                "Collected Hour (Local)",
            ]
        )
        for order in collected_orders:
            collected_sheet.append(
                [
                    order["number"],
                    order["created"].replace(tzinfo=None),
                    order["ready"].replace(tzinfo=None),
                    order["collected"].replace(tzinfo=None),
                    order["preparation"],
                    order["collection"],
                    order["collected_hour"],
                ]
            )

        hourly_sheet = workbook.create_sheet("Hourly Collections")
        hourly_sheet.append(["Hour (Local)", "Orders Collected"])
        for hour, count in enumerate(collected_by_hour):
            hourly_sheet.append([f"{hour:02}:00", count])

        for sheet, widths in (
            (order_sheet, [16, 16, 24, 24, 24, 24, 30]),
            (collected_sheet, [16, 24, 24, 24, 24, 30, 24]),
            (hourly_sheet, [18, 22]),
        ):
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            sheet.sheet_view.showGridLines = False
            for cell in sheet[1]:
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill("solid", fgColor="287271")
            for column, width in enumerate(widths, start=1):
                sheet.column_dimensions[chr(64 + column)].width = width

        for sheet, timestamp_columns in (
            (order_sheet, (3, 5)),
            (collected_sheet, (2, 4)),
        ):
            for row in sheet.iter_rows(
                min_row=2,
                min_col=timestamp_columns[0],
                max_col=timestamp_columns[1],
            ):
                for cell in row:
                    cell.number_format = "yyyy-mm-dd hh:mm"
        for sheet in (order_sheet, collected_sheet):
            for row in sheet.iter_rows(min_row=2):
                for cell in row:
                    if cell.column in (6, 7):
                        cell.number_format = "0.00"

        chart = BarChart()
        chart.type = "col"
        chart.style = 10
        chart.title = "Orders Collected by Hour"
        chart.y_axis.title = "Orders"
        chart.x_axis.title = "Local Hour"
        chart.add_data(Reference(hourly_sheet, min_col=2, min_row=1, max_row=25), titles_from_data=True)
        chart.set_categories(Reference(hourly_sheet, min_col=1, min_row=2, max_row=25))
        chart.height = 8
        chart.width = 16
        summary.add_chart(chart, "D3")

        output = BytesIO()
        workbook.save(output)
        body = output.getvalue()
        self.send_response(200)
        self.send_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.send_header(
            "Content-Disposition",
            f'attachment; filename="daily-orders-{report_date}.xlsx"',
        )
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path == "/api/orders":
            self.create_order()
            return

        match = ORDER_ROUTE.fullmatch(urlsplit(self.path).path)
        if match and match.group(2) == "/ready":
            self.mark_order_ready(int(match.group(1)))
            return

        self.send_json(404, {"error": "API route not found."})

    def create_order(self):
        try:
            payload = self.read_json()
            order_number = payload.get("orderNumber")
            if (
                isinstance(order_number, bool)
                or not isinstance(order_number, int)
                or order_number < 1
                or order_number > 9_007_199_254_740_991
            ):
                raise ValueError("Order number must be a positive safe whole number.")
        except ValueError as error:
            self.send_json(400, {"error": str(error)})
            return

        try:
            with database() as connection:
                cursor = connection.execute(
                    "INSERT INTO orders (order_number, created_at) VALUES (?, ?)",
                    (order_number, current_timestamp()),
                )
        except sqlite3.IntegrityError:
            self.send_json(409, {"error": f"Order #{order_number} is already active."})
            return

        self.send_json(201, {"id": cursor.lastrowid, "orderNumber": order_number})

    def mark_order_ready(self, order_id):
        with database() as connection:
            cursor = connection.execute(
                """
                UPDATE orders SET ready_at = ?
                WHERE id = ? AND ready_at IS NULL AND collected_at IS NULL
                """,
                (current_timestamp(), order_id),
            )
        if cursor.rowcount == 0:
            self.send_json(409, {"error": "Order is missing or is no longer preparing."})
            return
        self.send_json(200, {"status": "ready"})

    def do_DELETE(self):
        match = ORDER_ROUTE.fullmatch(urlsplit(self.path).path)
        if not match or match.group(2):
            self.send_json(404, {"error": "API route not found."})
            return

        with database() as connection:
            cursor = connection.execute(
                """
                UPDATE orders SET collected_at = ?
                WHERE id = ? AND ready_at IS NOT NULL AND collected_at IS NULL
                """,
                (current_timestamp(), int(match.group(1))),
            )
        if cursor.rowcount == 0:
            self.send_json(409, {"error": "Order is missing or is not ready to collect."})
            return
        self.send_json(200, {"status": "collected"})

    def serve_static(self, request_path):
        relative_path = unquote(request_path).lstrip("/") or "index.html"
        file_path = (ROOT / relative_path).resolve()
        try:
            file_path.relative_to(ROOT)
        except ValueError:
            self.send_json(404, {"error": "File not found."})
            return

        if not file_path.is_file():
            self.send_json(404, {"error": "File not found."})
            return

        body = file_path.read_bytes()
        content_type = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", f"{content_type}; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    initialize_database()
    server = ThreadingHTTPServer((HOST, PORT), DashboardHandler)
    print(f"Order dashboard listening on port {PORT}", flush=True)
    server.serve_forever()
