FROM python:3.11-slim

WORKDIR /app

# Install runtime deps
RUN pip install --no-cache-dir -U pip

COPY pyproject.toml /app/pyproject.toml
COPY polytrader /app/polytrader
COPY README.md /app/README.md

RUN pip install --no-cache-dir -e .

ENV POLYTRADER_MODE=paper \
    POLYTRADER_INTERVAL_SECONDS=600

CMD ["polytrader", "run"]
