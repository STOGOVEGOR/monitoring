# 1) Базовый образ с Python 3.11
FROM python:3.11-slim

# 2) Рабочая директория внутри контейнера
WORKDIR /app

# 3) Копируем и ставим зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4) Копируем сам код
COPY . .

# 4) Добавляем healthcheck
HEALTHCHECK --interval=5m --timeout=10s CMD pgrep -f main.py || exit 1

# 5) По умолчанию запускаем main.py
CMD ["python", "main.py"]
