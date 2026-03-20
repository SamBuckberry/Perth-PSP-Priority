FROM python:3.12-slim

WORKDIR /etl

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc libgeos-dev libproj-dev libgdal-dev \
    osmium-tool wget \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "-m", "scripts.run_all"]
