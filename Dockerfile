# The recipe for the web app's image: a small Linux with Python 3.12, the
# project's libraries, and the code. "docker compose up" builds it once and
# reuses it until requirements.txt or this file changes.
FROM python:3.12-slim

# Don't write .pyc cache files, and print output straight away so the logs
# appear live in the terminal.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Everything happens in /app inside the container.
WORKDIR /app

# Install the libraries on their own first. Docker keeps each step as a
# cached layer, so editing your code later doesn't reinstall all of them:
# only a change to requirements.txt does.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then the code itself.
COPY . .

# The app listens on port 5000 inside the container.
EXPOSE 5000

# What runs when the container starts (docker-compose.yml can override it).
CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]