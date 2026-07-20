FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

EXPOSE 8000

# migrate always; seed_demo only on a genuinely fresh database, so a
# container restart never wipes real data. DJANGO_SECRET_KEY/DEBUG come
# from docker-compose.yml's environment block, not baked in here.
CMD ["sh", "-c", "python manage.py migrate && (test -f db.sqlite3.seeded || (python manage.py seed_demo && touch db.sqlite3.seeded)) && python manage.py runserver 0.0.0.0:8000"]
