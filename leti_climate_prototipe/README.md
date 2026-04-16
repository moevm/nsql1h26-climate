# ЛЭТИ — Система мониторинга микроклимата

Веб-приложение для мониторинга показаний датчиков микроклимата (температура, влажность, CO₂) в учебных корпусах ЛЭТИ.

## Тестовые пользователи

| Логин | Пароль | Роль | Возможности |
|---|---|---|---|
| `admin` | `admin123` | Администратор | Просмотр + создание / редактирование / удаление всех сущностей, импорт данных |
| `viewer` | `viewer123` | Посетитель | Только просмотр данных и аналитики, экспорт |

## Быстрый старт (Docker Compose)

### Требования

- Docker Engine 24+ и Docker Compose v2
- Свободный порт **8080** на локальном хосте

### Ubuntu 22.04+

```bash
# 1. Установить Docker (если не установлен)
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 2. Клонировать репозиторий
git clone <https://github.com/moevm/nsql1h26-climate>
cd <https://github.com/moevm/nsql1h26-climate/tree/main/leti_climate_prototipe>

# 3. Собрать и запустить
docker compose build --no-cache
docker compose up -d

# 4. Открыть браузер
xdg-open http://localhost:8080
```

Приложение запустится через **15–30 секунд**. При первом запуске автоматически создаётся тестовый набор данных (8 корпусов, ~27 этажей, ~108 помещений, ~324 датчика, показания за последние 24 часа).


## Управление контейнерами

```
bash
# Посмотреть логи
docker compose logs -f

# Посмотреть логи только бэкенда
docker compose logs -f backend

# Остановить
docker compose down

# Остановить и удалить данные БД (полный сброс)
docker compose down -v

# Перезапустить после изменений кода
docker compose build --no-cache
docker compose up -d
```
# Интерактивная документация Swagger 
доступна по адресу: **http://localhost:8080/docs** (если хост был поменян то меняем его и тут)

## Решение проблем

**Приложение не открывается сразу:** подождите 20–30 секунд — InfluxDB проходит инициализацию. Backend ждёт её завершения (healthcheck в compose).

**Ошибка `port is already allocated`:** порт 8080 занят другим процессом. Измените `"127.0.0.1:8080:8080"` на другой порт в `docker-compose.yml`, например `"127.0.0.1:8090:8080"`.

**Данные не появляются:** проверьте логи `docker compose logs backend`. Seed пишет `Seed/refresh complete` при успешной инициализации.

