FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py ./

# A numeric uid, not a name: a cluster enforcing runAsNonRoot cannot verify a
# named user and refuses to start the container.
RUN useradd --uid 10001 --create-home appuser
USER 10001

EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
