# syntax=docker/dockerfile:1

FROM python:3.11.8

WORKDIR /bot
COPY requirements.txt requirements.txt
COPY data/credentials.json data/postgres.json data/initial_cogs.json ./data/
RUN python -m pip install --no-cache-dir -r requirements.txt --extra-index-url https://abstractumbra.github.io/pip/
COPY cogs/ cogs/
COPY bot.py .
CMD ["python", "-u", "bot.py"]
