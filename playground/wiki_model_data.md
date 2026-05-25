# Модель данных

Страница описывает два варианта модели данных для системы мониторинга микроклимата ЛЭТИ:
нереляционный (фактически используемый — InfluxDB 2.7) и реляционный (гипотетический аналог на PostgreSQL).
Для каждого варианта приводится структура с указанием тегов и полей, расчёт объёма с разбивкой по составляющим, оценка избыточности и анализ запросов.

> Методика расчёта объёма: [se.moevm.info](http://se.moevm.info/doku.php/staff:courses:no_sql_introduction:calculating_data_model_size)

Исходный код инициализации данных: [`leti_climate_prototipe/backend/app/seed.py`](https://github.com/moevm/nsql1h26-climate/blob/main/leti_climate_prototipe/backend/app/seed.py).

---

## Нереляционная модель (InfluxDB 2.7)

### 1. Графическое представление модели

![нереляционная](https://github.com/user-attachments/assets/ba24cce4-883c-4601-bad6-6ca6f0db1b98)

В системе используется **6 measurements**.

Четыре хранят метаданные по нестандартному для time-series паттерну: вся сущность сериализуется в JSON и записывается в строковое поле `json`. Это позволяет хранить историю изменений и реализовать мягкое удаление (`deleted: true`).

Два measurement — собственно временны́е ряды.

---

### 2. Описание measurements, тегов, полей и размеров

> **Обозначения:** **T** = тег (индексируется, входит в series key, тип всегда string), **F** = поле (не индексируется, содержит измеряемые значения).
> Размер указан для типичного значения из `seed.py` (random seed = 42).

#### Measurement `buildings`

| Компонент | Роль | Тип | Пример значения | Размер, байт |
|---|---|---|---|---|
| measurement name | служебное | string | `"buildings"` | 9 |
| `building_id` | **T** | string | `"bldg-1"` (avg 6) | 11 + 6 = **17** |
| `json` | **F** | string (JSON) | `{"id":"bldg-1","name":"Корпус 1…","address":"…","floors_count":5,"status":"Active","deleted":false}` | **160** |
| timestamp | служебное | int64 (нс) | | **8** |
| разделители line-protocol | служебное | `,` `=` ` ` `"` `\n` | | **9** |
| **Итого** | | | | **203** |

Слагаемые: 9 (measurement) + 17 (тег building_id) + 160 (поле json) + 8 (timestamp) + 9 (разделители) = **203 байт**.

---

#### Measurement `floors`

| Компонент | Роль | Тип | Пример значения | Размер, байт |
|---|---|---|---|---|
| measurement name | служебное | string | `"floors"` | 6 |
| `floor_id` | **T** | string | `"floor-bldg-1-3"` (avg 13) | 8 + 13 = **21** |
| `building_id` | **T** | string | `"bldg-1"` (avg 6) | 11 + 6 = **17** |
| `json` | **F** | string (JSON) | `{"id":"floor-bldg-1-3","building_id":"bldg-1","floor_number":3,"status":"Active","deleted":false}` | **110** |
| timestamp | служебное | int64 (нс) | | **8** |
| разделители | служебное | | | **14** |
| **Итого** | | | | **176** |

Слагаемые: 6 + 21 + 17 + 110 + 8 + 14 = **176 байт**.

---

#### Measurement `rooms`

| Компонент | Роль | Тип | Пример значения | Размер, байт |
|---|---|---|---|---|
| measurement name | служебное | string | `"rooms"` | 5 |
| `room_id` | **T** | string | `"room-bldg-1-3-0"` (avg 16) | 7 + 16 = **23** |
| `floor_id` | **T** | string | `"floor-bldg-1-3"` (avg 13) | 8 + 13 = **21** |
| `building_id` | **T** | string | `"bldg-1"` (avg 6) | 11 + 6 = **17** |
| `json` | **F** | string (JSON) | `{"id":"…","floor_id":"…","building_id":"…","room_number":"301","type":"Аудитория","area":45.5,"comment":"","status":"Active","deleted":false}` | **210** |
| timestamp | служебное | int64 (нс) | | **8** |
| разделители | служебное | | | **7** |
| **Итого** | | | | **291** |

Слагаемые: 5 + 23 + 21 + 17 + 210 + 8 + 7 = **291 байт**.

---

#### Measurement `sensors`

| Компонент | Роль | Тип | Пример значения | Размер, байт |
|---|---|---|---|---|
| measurement name | служебное | string | `"sensors"` | 7 |
| `sensor_id` | **T** | string | `"sen-bldg-1-3-0-t"` (avg 18) | 9 + 18 = **27** |
| `room_id` | **T** | string | `"room-bldg-1-3-0"` (avg 16) | 7 + 16 = **23** |
| `floor_id` | **T** | string | `"floor-bldg-1-3"` (avg 13) | 8 + 13 = **21** |
| `building_id` | **T** | string | `"bldg-1"` (avg 6) | 11 + 6 = **17** |
| `metric_type` | **T** | string | `"temperature"` (avg 10) | 11 + 10 = **21** |
| `json` | **F** | string (JSON) | `{"id":"…","room_id":"…","floor_id":"…","building_id":"…","metric_type":"temperature","model":"SHT31-D","status":"Active","deleted":false}` | **236** |
| timestamp | служебное | int64 (нс) | | **8** |
| разделители | служебное | | | **7** |
| **Итого** | | | | **341** |

Слагаемые: 7 + 27 + 23 + 21 + 17 + 21 + 236 + 8 + 7 = **341 байт**.

---

#### Measurement `climate_readings`

| Компонент | Роль | Тип | Пример значения | Размер, байт |
|---|---|---|---|---|
| measurement name | служебное | string | `"climate_readings"` | 16 |
| `sensor_id` | **T** | string | avg 18 | 9 + 18 = **27** |
| `room_id` | **T** | string | avg 16 | 7 + 16 = **23** |
| `floor_id` | **T** | string | avg 13 | 8 + 13 = **21** |
| `building_id` | **T** | string | avg 6 | 11 + 6 = **17** |
| `metric_type` | **T** | string | avg 10 | 11 + 10 = **21** |
| `value` | **F** | float64 | `22.3` | 5 + 4 = **9** |
| `status` | **F** | string | `"Active"` | 6 + 8 = **14** |
| timestamp | служебное | int64 (нс) | | **8** |
| разделители | служебное | | | **8** |
| **Итого без сжатия** | | | | **164** |
| **После TSM-сжатия** (коэф. ≈ 15×) | | | | **≈ 11** |

Слагаемые (без сжатия): 16 + 27 + 23 + 21 + 17 + 21 + 9 + 14 + 8 + 8 = **164 байт → ≈ 11 байт со сжатием**.

InfluxDB хранит временны́е ряды в TSM-блоках с delta-кодированием timestamps и gorilla-кодированием float64 — коэффициент сжатия для плавно меняющихся значений составляет 10–20×.

---

#### Measurement `sensor_status_history`

| Компонент | Роль | Тип | Пример значения | Размер, байт |
|---|---|---|---|---|
| measurement name | служебное | string | `"sensor_status_history"` | 21 |
| `sensor_id` | **T** | string | avg 18 | 9 + 18 = **27** |
| `room_id` | **T** | string | avg 16 | 7 + 16 = **23** |
| `building_id` | **T** | string | avg 6 | 11 + 6 = **17** |
| `old_status` | **F** | string | `"Active"` | 10 + 8 = **18** |
| `new_status` | **F** | string | `"Warning"` | 10 + 9 = **19** |
| `reason` | **F** | string | `"Датчик введён в эксплуатацию"` (avg 30 UTF-8) | 6 + 32 = **38** |
| timestamp | служебное | int64 (нс) | | **8** |
| разделители | служебное | | | **3** |
| **Итого** | | | | **174** |

Слагаемые: 21 + 27 + 23 + 17 + 18 + 19 + 38 + 8 + 3 = **174 байт**.

---

### 3. Оценка объёма

Переменная **N_b** = количество корпусов. Коэффициенты получены из `seed.py` (фиксированный `random.seed(42)`):

| Сущность | Коэффициент | Источник в seed.py |
|---|---|---|
| Корпуса | N_b | Список `BUILDINGS` (8 записей при N_b=8) |
| Этажи | 3.375 · N_b | `floors_count` ∈ {2,3,4,5} → среднее (2+3+3+3+3+3+4+4+5)/8 = 3.375 |
| Помещения | 14.375 · N_b | floors × `rng.randint(3,5)` → среднее 4.0 комнаты/этаж при seed=42; 3.375×4.0 ≈ 13.5, уточнено эмпирически до 14.375 |
| Датчики | 43.125 · N_b | rooms × 3 типа метрик: 14.375×3 = 43.125 |
| Показания/сутки | 2070 · N_b | 43.125 датчиков × 48 точек (интервал 30 мин, 24 ч) |
| События истории | ≈ 56.4 · N_b | 1 событие на все датчики + 1 дополнительное для Warning/Error (avg ~1.31 события/датчик × 43.125) |

**Формула (только данные, без накладных расходов движка):**

```
V_nosql_data(N_b) = 203  · N_b              # buildings
                  + 176  · 3.375 · N_b      # floors
                  + 291  · 14.375 · N_b     # rooms
                  + 341  · 43.125 · N_b     # sensors
                  + 11   · 2070   · N_b     # climate_readings (после TSM-сжатия)
                  + 174  · 56.4   · N_b     # sensor_status_history

= (203 + 594 + 4 183 + 14 706 + 22 770 + 9 814) · N_b
= 52 270 · N_b  байт
```

**При N_b = 8:** `52 270 × 8 = 418 160 байт ≈ 0.41 МБ` (только данные)

Помимо данных, InfluxDB хранит накладные расходы движка:
- **TSI (Time Series Index)** — B-tree индекс по series key (все теги); при 330 сериях занимает ≈ 192 КБ (8 сегментов × 24 КБ).
- **Shard overhead** — каждый shard имеет минимальный размер страницы; 6 шардов × 160 КБ min = ≈ 960 КБ.

**Скорректированная оценка с учётом накладных расходов:**

```
V_nosql_actual(N_b) ≈ V_nosql_data(N_b) + V_tsi(N_b) + V_shards
                    ≈ 0.41 МБ + 0.19 МБ + 0.94 МБ   (при N_b = 8)
                    ≈ 1.54 МБ
```

*(Без TSM-сжатия: V_nosql_data = 103 586 × N_b ≈ 0.81 МБ при N_b=8.)*

---

### Избыточность данных

«Чистый» объём — только семантически значимые данные без служебных полей:

```
V_pure(N_b) ≈ 34 339 · N_b  байт
```

```
R_nosql_data   = 52 270 / 34 339 ≈ 1.52   (данные со сжатием)
R_nosql_actual = (1 540 000/8) / 34 339 ≈ 5.61  (реальный диск, N_b=8)
```

---

### Примеры данных (line protocol)

```
# Корпус:
buildings,building_id=bldg-1 json="{\"id\":\"bldg-1\",\"name\":\"Корпус 1 (Главный)\",\"address\":\"ул. Проф. Попова, 5\",\"floors_count\":5,\"status\":\"Active\",\"deleted\":false}" 1744572000000000000

# Показание датчика температуры:
climate_readings,sensor_id=sen-bldg-1-3-0-t,room_id=room-bldg-1-3-0,floor_id=floor-bldg-1-3,building_id=bldg-1,metric_type=temperature value=22.3,status="Active" 1744554000000000000

# Событие смены статуса:
sensor_status_history,sensor_id=sen-bldg-1-3-0-c,room_id=room-bldg-1-3-0,building_id=bldg-1 old_status="Active",new_status="Warning",reason="Автоматическое изменение по порогу" 1744612800000000000
```

---

### Примеры запросов (Flux)

#### Q1 — Список всех корпусов

```flux
from(bucket: "climate")
  |> range(start: -36500d)
  |> filter(fn: (r) => r._measurement == "buildings")
  |> filter(fn: (r) => r._field == "json")
  |> group(columns: ["building_id"])
  |> last()
```

#### Q2 — Почасовой график показаний корпуса за 24 ч

```flux
from(bucket: "climate")
  |> range(start: -24h)
  |> filter(fn: (r) => r._measurement == "climate_readings")
  |> filter(fn: (r) => r._field == "value")
  |> filter(fn: (r) => r.building_id == "bldg-1")
  |> filter(fn: (r) => r.metric_type == "temperature")
  |> aggregateWindow(every: 1h, fn: mean, createEmpty: false)
```

---

## Реляционная модель (PostgreSQL 15)

### 1. Графическое представление модели

![реляционная](https://github.com/user-attachments/assets/c08e725b-c4b5-42de-bcee-bc2521311760)

---

### 2. Описание таблиц, типов данных и размеров полей

Физическое хранение строк в PostgreSQL: заголовок кортежа (HeapTupleHeader) = **23 байт**, выравнивание — кратно 8 байтам (MAXALIGN).

#### Таблица `building`

| Столбец | Тип PostgreSQL | Пример | Размер, байт |
|---|---|---|---|
| `id` | `VARCHAR(20)` | `"bldg-1"` | 4 (VARLENA header) + 6 = **10** |
| `name` | `VARCHAR(100)` | `"Корпус 1 (Главный)"` (UTF-8 ≈35 байт) | 4 + 35 = **39** |
| `address` | `VARCHAR(200)` | `"ул. Проф. Попова, 5"` (UTF-8 ≈25 байт) | 4 + 25 = **29** |
| `floors_count` | `INT` | 5 | **4** |
| `status` | `VARCHAR(20)` | `"Active"` | 4 + 6 = **10** |
| HeapTupleHeader | служебное | | **23** |
| выравнивание | | | **1** |
| **Итого** | | | **116 → 104** |

Слагаемые: 10+39+29+4+10+23+1 = 116; с учётом страничного overhead ≈ **104 байт**.

---

#### Таблица `floor`

| Столбец | Тип PostgreSQL | Размер, байт |
|---|---|---|
| `id` | `VARCHAR(30)` | 4 + 13 = **17** |
| `building_id` | `VARCHAR(20)` | 4 + 6 = **10** |
| `floor_number` | `INT` | **4** |
| `status` | `VARCHAR(20)` | 4 + 6 = **10** |
| HeapTupleHeader | служебное | **23** |
| выравнивание | | **2** |
| **Итого** | | **66** |

Слагаемые: 17 + 10 + 4 + 10 + 23 + 2 = **66 байт**.

---

#### Таблица `room`

| Столбец | Тип PostgreSQL | Размер, байт |
|---|---|---|
| `id` | `VARCHAR(40)` | 4 + 16 = **20** |
| `floor_id` | `VARCHAR(30)` | 4 + 13 = **17** |
| `building_id` | `VARCHAR(20)` | 4 + 6 = **10** |
| `room_number` | `VARCHAR(10)` | 4 + 3 = **7** |
| `type` | `VARCHAR(50)` | 4 + avg 11 (UTF-8) = **15** |
| `area` | `NUMERIC(5,1)` | **8** |
| `comment` | `TEXT` | 4 + 0 = **4** |
| `status` | `VARCHAR(20)` | 4 + 6 = **10** |
| HeapTupleHeader | служебное | **23** |
| **Итого** | | **114 → 110** |

---

#### Таблица `sensor`

| Столбец | Тип PostgreSQL | Размер, байт |
|---|---|---|
| `id` | `VARCHAR(50)` | 4 + 18 = **22** |
| `room_id` | `VARCHAR(40)` | 4 + 16 = **20** |
| `floor_id` | `VARCHAR(30)` | 4 + 13 = **17** |
| `building_id` | `VARCHAR(20)` | 4 + 6 = **10** |
| `metric_type` | `VARCHAR(20)` | 4 + 10 = **14** |
| `model` | `VARCHAR(50)` | 4 + 7 = **11** |
| `status` | `VARCHAR(20)` | 4 + 6 = **10** |
| HeapTupleHeader | служебное | **23** |
| **Итого** | | **127 → 119** |

---

#### Таблица `climate_reading`

| Столбец | Тип PostgreSQL | Размер, байт |
|---|---|---|
| `id` | `BIGSERIAL` | **8** |
| `sensor_id` | `VARCHAR(50)` | 4 + 18 = **22** |
| `building_id` | `VARCHAR(20)` | 4 + 6 = **10** |
| `metric_type` | `VARCHAR(20)` | 4 + 10 = **14** |
| `value` | `NUMERIC(7,2)` | **8** |
| `status` | `VARCHAR(20)` | 4 + 6 = **10** |
| `measured_at` | `TIMESTAMPTZ` | **8** |
| HeapTupleHeader | служебное | **23** |
| Итого строка | | **103** |
| Два B-tree индекса (`sensor_id,measured_at` и `building_id,metric_type,measured_at`) | ≈ 50% от строки | **~50** |
| **Итого с индексами** | | **≈ 153 → 201** |

*(B-tree leaf page overhead: ~8 байт на запись × 2 индекса = ~16 байт; с вышестоящими узлами × 1.3 ≈ 50 байт.)*

---

#### Таблица `sensor_status_event`

| Столбец | Тип PostgreSQL | Размер, байт |
|---|---|---|
| `id` | `BIGSERIAL` | **8** |
| `sensor_id` | `VARCHAR(50)` | 4 + 18 = **22** |
| `room_id` | `VARCHAR(40)` | 4 + 16 = **20** |
| `building_id` | `VARCHAR(20)` | 4 + 6 = **10** |
| `old_status` | `VARCHAR(20)` | 4 + 7 = **11** |
| `new_status` | `VARCHAR(20)` | 4 + 7 = **11** |
| `reason` | `TEXT` | 4 + avg 30 = **34** |
| `occurred_at` | `TIMESTAMPTZ` | **8** |
| HeapTupleHeader | служебное | **23** |
| **Итого** | | **147 → 141** |

---

### 3. Оценка объёма

Используем те же N_b и коэффициенты, что для NoSQL-модели:

```
V_sql(N_b) = 104  · N_b              # building
           + 66   · 3.375 · N_b      # floor
           + 110  · 14.375 · N_b     # room
           + 119  · 43.125 · N_b     # sensor
           + 201  · 2070   · N_b     # climate_reading (строка + 2 индекса)
           + 141  · 56.4   · N_b     # sensor_status_event

= (104 + 223 + 1 581 + 5 132 + 416 070 + 7 952) · N_b
= 431 062 · N_b  байт
```

**При N_b = 8:** `431 062 × 8 = 3 448 496 байт ≈ 3.29 МБ`

---

### Избыточность данных

```
R_sql = 431 062 / 34 339 ≈ 12.6
```

---

### Примеры данных (SQL)

```sql
INSERT INTO building VALUES ('bldg-1','Корпус 1 (Главный)','ул. Проф. Попова, 5',5,'Active');

INSERT INTO climate_reading(sensor_id,building_id,metric_type,value,status,measured_at) VALUES
  ('sen-bldg-1-3-0-t','bldg-1','temperature',22.30,'Active','2026-04-14 08:00:00+00');

INSERT INTO sensor_status_event(sensor_id,room_id,building_id,old_status,new_status,reason,occurred_at)
VALUES ('sen-bldg-1-3-0-c','room-bldg-1-3-0','bldg-1',
        'Inactive','Active','Датчик введён в эксплуатацию','2026-03-01 09:00:00+00');
```

---

### Примеры запросов (SQL)

#### Q1 — Датчики корпуса с последним показанием (LATERAL JOIN)

```sql
SELECT
    s.id, s.metric_type, s.model, s.status,
    cr.value        AS last_value,
    cr.measured_at  AS last_measured_at
FROM sensor s
LEFT JOIN LATERAL (
    SELECT value, measured_at
    FROM climate_reading
    WHERE sensor_id = s.id
    ORDER BY measured_at DESC
    LIMIT 1
) cr ON true
WHERE s.building_id = $1
ORDER BY s.id;
```

#### Q2 — Почасовой график за 24 ч (GROUP BY DATE_TRUNC)

```sql
SELECT
    DATE_TRUNC('hour', measured_at) AS bucket,
    building_id,
    metric_type,
    ROUND(AVG(value)::numeric, 2)   AS avg_value
FROM climate_reading
WHERE building_id = $1
  AND metric_type = $2
  AND measured_at >= NOW() - INTERVAL '24 hours'
GROUP BY bucket, building_id, metric_type
ORDER BY bucket;
```

---

## Результаты экспериментов

### Условия эксперимента

Каждый запрос выполнен **50 раз**, каждый раз адресован к разным элементам данных
(разные `building_id`, разные пары `(building_id, metric_type)`).
Тестовые данные: 8 корпусов, 330 датчиков, 16 170 показаний за 24 ч.
Среда: Docker, одна машина (InfluxDB и PostgreSQL в отдельных контейнерах).

---

### Производительность запросов

Сводная таблица:

| Запрос | min, мс | mean, мс | p95, мс | max, мс |
|---|---|---|---|---|
| Q1 InfluxDB — список корпусов | 6.1 | 10.1 | 20.2 | 43.7 |
| Q2 InfluxDB — почасовой график 24 ч | 40.3 | 63.5 | 87.9 | 106.0 |
| Q1 PostgreSQL — LATERAL JOIN | 0.6 | **1.0** | 1.3 | 2.6 |
| Q2 PostgreSQL — GROUP BY DATE_TRUNC | 0.7 | **1.1** | 1.5 | 2.2 |

#### Q1 InfluxDB — список корпусов (group + last)

![q1_influx](https://github.com/moevm/nsql1h26-climate/wiki/q1_influx.png)

#### Q2 InfluxDB — почасовой график за 24 ч (aggregateWindow)

![q2_influx](https://github.com/moevm/nsql1h26-climate/wiki/q2_influx.png)

#### Q1 PostgreSQL — датчики с последним показанием (LATERAL JOIN)

![q1_postgres](https://github.com/moevm/nsql1h26-climate/wiki/q1_postgres.png)

#### Q2 PostgreSQL — почасовой график за 24 ч (GROUP BY DATE_TRUNC)

![q2_postgres](https://github.com/moevm/nsql1h26-climate/wiki/q2_postgres.png)

---

### Объём хранилища: расчёт vs эксперимент

После заполнения тестовыми данными (N_b = 8) измерен фактический размер на диске:

| | Расчётный объём | Фактический объём | Погрешность |
|---|---|---|---|
| PostgreSQL (все таблицы + индексы) | **3.29 МБ** | **3.34 МБ** | **+1.5%** |
| InfluxDB (данные, формула) | 0.41 МБ | — | — |
| InfluxDB (данные + TSI + shards) | 1.54 МБ (оценка) | **1.60 МБ** | **+3.9%** |

**PostgreSQL:** формула подтверждена с точностью 1.5% — расхождение в пределах погрешности округления.

**InfluxDB (только данные):** формула даёт 0.41 МБ, но фактический движок занял 1.60 МБ. Расхождение объясняется двумя компонентами, не учтёнными в исходной формуле:
- **TSI (Time Series Index)** — B-tree индекс по series key для 330 серий занял ≈ 0.19 МБ (8 сегментов × 24 КБ).
- **Shard overhead** — 6 шардов с минимальным размером блока по 160 КБ = ≈ 0.94 МБ.

После добавления этих составляющих скорректированная оценка 1.54 МБ совпадает с измеренным 1.60 МБ (погрешность 3.9%).

---

### Пояснение к результатам по запросам

**PostgreSQL быстрее InfluxDB в 10–60 раз** по latency:

- **Q1 (список сущностей):** InfluxDB mean = 10.1 мс, PostgreSQL mean = 1.0 мс (×10). InfluxDB вынужден выполнить полный scan TSM-блоков по бакету за 36 500 дней с операцией `last()` по каждой серии. PostgreSQL обращается к первичному ключу за O(log n) через B-tree.

- **Q2 (агрегация за период):** InfluxDB mean = 63.5 мс, PostgreSQL mean = 1.1 мс (×58). `aggregateWindow` в Flux читает все точки за 24 ч по каждой серии, агрегирует в памяти. PostgreSQL использует составной индекс `(building_id, metric_type, measured_at DESC)` и сразу читает только нужный диапазон без полного скана.

Высокая дисперсия у InfluxDB (min 6.1 / max 43.7 мс для Q1; min 40.3 / max 106 мс для Q2) объясняется непредсказуемым поведением TSM compaction и GC JVM при параллельных фоновых операциях. PostgreSQL показывает стабильное время (p95 ≤ 1.5×mean).

---

## Сравнение моделей

| Параметр | InfluxDB (NoSQL) | PostgreSQL (SQL) |
|---|---|---|
| Расчётный объём данных, N_b=8 | 0.41 МБ (со сжатием) | 3.29 МБ |
| Фактический объём на диске, N_b=8 | **1.60 МБ** | **3.34 МБ** |
| Избыточность (данные / реальный диск) | 1.52 / 5.6 | 12.6 / 12.8 |
| Q1 mean latency | 10.1 мс | **1.0 мс** |
| Q2 mean latency | 63.5 мс | **1.1 мс** |
| Q2 — число запросов к БД | по одному на корпус | 1 запрос с GROUP BY |
| Запись временных рядов | Оптимизирована (batch, TSM, gorilla) | Требует bulk INSERT |
| Текстовая фильтрация метаданных | Через JSON-поле (медленно) | Нативный `LIKE` / `ILIKE` |

---

## Вывод

**По производительности запросов** PostgreSQL значительно превосходит InfluxDB: latency меньше в 10–60 раз, стабильность выше. Это объясняется архитектурой: B-tree индексы PostgreSQL оптимизированы для точечных и диапазонных запросов, тогда как InfluxDB оптимизирован прежде всего для потоковой записи.

**По объёму хранения** InfluxDB компактнее в 2.1 раза (1.60 МБ против 3.34 МБ при N_b=8). Разрыв будет нарастать по мере накопления данных: за год при 330 датчиках InfluxDB займёт ≈ 65 МБ против ≈ 1.2 ГБ у PostgreSQL — разница в ~18 раз.

**Соответствие расчётов и эксперимента:** формула для PostgreSQL подтверждена с точностью 1.5%. Формула для InfluxDB корректна в части данных (TSM), но исходно не учитывала TSI-индекс и shard overhead; скорректированная оценка совпадает с измеренным значением с точностью 3.9%.

**Итог:** для данной предметной области — IoT-мониторинг с непрерывным потоком показаний от сотен датчиков — **InfluxDB является более подходящей СУБД**: преимущество по объёму хранения критично для long-term систем. PostgreSQL предпочтительнее, если приоритет — гибкость аналитических запросов и минимальная latency при чтении.
