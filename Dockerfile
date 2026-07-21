FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000

# See docker-entrypoint.sh -- shared by Option A's docker-compose.yml
# (build-from-source, no JIMOTHY_DATA_DIR set) and the zero-clone `docker
# run` path documented in the README (JIMOTHY_DATA_DIR=/data, a named
# volume). DJANGO_SECRET_KEY/DEBUG come from docker-compose.yml's
# environment block for Option A; the entrypoint script generates one
# itself for the zero-clone path, where nothing else supplies one.
CMD ["./docker-entrypoint.sh"]
