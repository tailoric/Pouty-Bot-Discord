# syntax=docker/dockerfile:1

FROM python:3.9

WORKDIR /bot
COPY requirements.txt requirements.txt
COPY data/credentials.json data/postgres.json data/initial_cogs.json ./data/
RUN python3 -m pip install -r requirements.txt
COPY cogs/ cogs/
COPY bot.py .
CMD ["python", "bot.py"]
