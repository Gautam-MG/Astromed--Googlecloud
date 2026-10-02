# =======================================================================
# STAGE 1: The Build Environment (Heavy Lift Compiler Stage)
# =======================================================================
FROM python:3.11-slim AS builder
WORKDIR /app
RUN pip install --no-cache-dir --upgrade pip
COPY astrohealth-app-main/requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# =======================================================================
# STAGE 2: The Lean Runtime Environment (Production Delivery Stage)
# =======================================================================
FROM python:3.11-slim
WORKDIR /app
COPY --from=builder /root/.local /root/.local
COPY . .

ENV PATH=/root/.local/bin:$PATH
ENV PYTHONUNBUFFERED=1

# Step inside the inner folder room where server.py lives
WORKDIR /app/astrohealth-app-main
EXPOSE 5000

# Launch using the production Gunicorn engine
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "server:app"]
