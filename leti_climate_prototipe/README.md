# ЛЭТИ — Система мониторинга микроклимата

Веб-приложение для мониторинга показаний датчиков микроклимата (температура, влажность, CO₂) в учебных корпусах СПбГЭТУ «ЛЭТИ».

## Структура репозитория

```
nsql1h26-climate/
├── leti_climate_prototipe/          # Основное приложение
│   ├── docker-compose.yml           # Конфигурация Docker Compose
│   └── backend/
│       ├── Dockerfile
│       ├── requirements.txt
│       └── app/
│           ├── main.py              # Точка входа FastAPI, фоновый поток показаний
│           ├── auth.py              # JWT-аутентификация
│           ├── influx.py            # Клиент InfluxDB, вспомогательные функции
│           ├── seed.py              # Первичное заполнение БД тестовыми данными
│           ├── routers/
│           │   ├── buildings.py     # CRUD корпусов
│           │   ├── floors.py        # CRUD этажей
│           │   ├── rooms.py         # CRUD помещений
│           │   ├── sensors.py       # CRUD датчиков
│           │   ├── readings.py      # Запросы показаний (последние, история)
│           │   ├── io.py            # Импорт / Экспорт
│           │   └── auth.py          # Эндпоинт логина
│           └── static/
│               └── index.html       # Браузерный SPA-клиент (Bootstrap 5 + Chart.js)
├── report.docx                      # Пояснительная записка
├── report.pdf
├── playground/
│   ├── wiki_model_data.md           # Модель данных (InfluxDB vs PostgreSQL)
│   ├── scripts/                     # Скрипты сравнительного анализа производительности
│   └── results/                     # Графики результатов экспериментов
└── .github/workflows/               # CI-проверки
```

---

## Быстрый старт

### Требования

- Docker Engine 24+ и Docker Compose v2
- Свободный порт **8080** на локальном хосте

### Запуск

```bash
# 1. Клонировать репозиторий
git clone https://github.com/moevm/nsql1h26-climate
cd nsql1h26-climate

# 2. Собрать и запустить
docker compose -f leti_climate_prototipe/docker-compose.yml up --build -d

# 3. Открыть в браузере
http://localhost:8080
```

Приложение запустится через **15–30 секунд**. При первом запуске автоматически создаётся тестовый набор данных: 8 корпусов, ~27 этажей, ~115 помещений, ~345 датчиков, показания за последние 24 часа.

### Установка Docker (Ubuntu 22.04+)

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
  https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
```

---

## Тестовые пользователи

| Логин | Пароль | Роль | Возможности |
|---|---|---|---|
| `admin` | `admin123` | Администратор | Просмотр + создание / редактирование / удаление всех сущностей, импорт данных |
| `viewer` | `viewer123` | Наблюдатель | Только просмотр данных, аналитика, экспорт |

---

## Функциональность

### Дашборд
- Сводные счётчики: количество корпусов, этажей, помещений, датчиков
- Таблица средних значений температуры, влажности и CO₂ по каждому корпусу
- Фильтрация по диапазонам всех трёх метрик

### Корпуса
- Список с пагинацией и фильтрами по названию, адресу, статусу, количеству этажей, дате создания/редактирования
- Детальная страница корпуса: вложенные этажи с помещениями и датчиками
- CRUD-операции для администратора

### Этажи
- Фильтры по номеру этажа, статусу, дате создания/редактирования
- Фильтры по средним значениям температуры, влажности, CO₂ на этаже

### Помещения
- Фильтры по номеру, типу, площади, статусу
- Фильтры по текущим значениям температуры, влажности, CO₂ в помещении

### Датчики
- Фильтры по типу метрики, модели, статусу, корпусу, этажу, помещению
- Фильтры по дате создания/редактирования
- Последнее показание датчика отображается прямо в строке таблицы
- История показаний конкретного датчика в виде графика

### Статистика
- Линейный график с агрегацией показаний за выбранный период (1 ч / 2 ч / 6 ч / 12 ч / 24 ч)
- **Анализ распределения** — настраиваемая сгруппированная диаграмма:
  - Выбор типа объектов: датчики или помещения
  - Многокритериальный фильтр (корпус, тип метрики, статус, тип помещения)
  - Выбор атрибута по оси X и атрибута группировки

### Импорт / Экспорт
- Экспорт любых сущностей в JSON
- Экспорт показаний в CSV
- Импорт корпусов, этажей, помещений, датчиков и показаний из JSON-файла

### Серверная пагинация
- Все таблицы используют серверную пагинацию (25 записей на страницу по умолчанию)
- Под каждой таблицей отображается общее количество найденных записей

---

## REST API

Интерактивная документация Swagger доступна по адресу:
**http://localhost:8080/docs**

Основные эндпоинты:

| Метод | Путь | Описание |
|---|---|---|
| POST | `/api/auth/login` | Получить JWT-токен |
| GET | `/api/buildings` | Список корпусов (пагинация + фильтры) |
| GET | `/api/floors` | Список этажей |
| GET | `/api/rooms` | Список помещений |
| GET | `/api/sensors` | Список датчиков |
| GET | `/api/readings/latest` | Последние показания |
| GET | `/api/readings/range` | Показания за период с агрегацией |
| GET | `/api/export/{entity}` | Экспорт в JSON/CSV |
| POST | `/api/import/{entity}` | Импорт из файла |

---

## Управление контейнерами

```bash
# Посмотреть логи
docker compose -f leti_climate_prototipe/docker-compose.yml logs -f

# Посмотреть логи только бэкенда
docker compose -f leti_climate_prototipe/docker-compose.yml logs -f backend

# Остановить
docker compose -f leti_climate_prototipe/docker-compose.yml down

# Остановить и удалить данные БД (полный сброс)
docker compose -f leti_climate_prototipe/docker-compose.yml down -v

# Пересобрать после изменений кода
docker compose -f leti_climate_prototipe/docker-compose.yml up --build -d
```

---

## Решение проблем

**Приложение не открывается сразу** — подождите 20–30 секунд: InfluxDB проходит инициализацию, бэкенд ждёт её завершения через healthcheck.

**Ошибка `port is already allocated`** — порт 8080 занят. Измените `"127.0.0.1:8080:8080"` на другой порт в `leti_climate_prototipe/docker-compose.yml`, например `"127.0.0.1:8090:8080"`, и откройте `http://localhost:8090`.

**Данные не появляются** — проверьте логи: `docker compose -f leti_climate_prototipe/docker-compose.yml logs backend`. При успешной инициализации там будет строка `Seed/refresh complete`.

---

## Технологии

| Компонент | Технология |
|---|---|
| Бэкенд | Python 3.11 / FastAPI 0.111 / Uvicorn 0.29 |
| База данных | InfluxDB 2.7 |
| Аутентификация | PyJWT 2.8 / Pydantic v2 |
| Фронтенд | Bootstrap 5.3 / Chart.js 4.4 |
| Контейнеризация | Docker Compose |
