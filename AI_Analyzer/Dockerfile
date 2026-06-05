FROM python:3.11-slim

WORKDIR /app
ENV PYTHONPATH=/app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY nyse_impact_screener.py .
COPY backtesting_api.py .
COPY supabase_db.py .
COPY backend ./backend

EXPOSE 8765 8766

CMD ["python", "nyse_impact_screener.py"]
