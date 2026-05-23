FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY wwtracked.py gsheets.py scheduler.py ./

RUN mkdir -p reports

CMD ["python", "scheduler.py"]
