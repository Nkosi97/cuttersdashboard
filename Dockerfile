FROM python:3.13-slim-trixie

RUN apt-get update \
	&& apt-get upgrade -y --no-install-recommends \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .

ENV PORT=8080
ENV HOST=0.0.0.0
ENV DB_PATH=/data/orders.sqlite3
EXPOSE 8080

CMD ["python", "server.py"]
