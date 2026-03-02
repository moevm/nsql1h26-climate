import os
import time
from datetime import datetime, timezone
from dotenv import load_dotenv
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS


load_dotenv()


def get_client():
    url = os.getenv("INFLUX_URL")
    token = os.getenv("INFLUX_TOKEN")
    org = os.getenv("INFLUX_ORG")
    return InfluxDBClient(url=url, token=token, org=org)


def write_data(client, bucket):
    print("Запись данных в БД")
    write_api = client.write_api(write_options=SYNCHRONOUS)

    # Создаем точку данных (измерение: microclimate)
    point = Point("microclimate") \
        .tag("building", "LETI_A") \
        .tag("floor", "3") \
        .tag("room", "301") \
        .field("temperature", 22.5) \
        .field("humidity", 45.0) \
        .time(datetime.now(timezone.utc), WritePrecision.NS)

    write_api.write(bucket=bucket, record=point)
    print("Данные успешно записаны")


def read_data(client, bucket):
    print("Чтение данных из БД")
    query_api = client.query_api()

    query = f'''
    from(bucket: "{bucket}")
      |> range(start: -1h)
      |> filter(fn: (r) => r["_measurement"] == "microclimate")
      |> filter(fn: (r) => r["room"] == "301")
    '''

    tables = query_api.query(query)

    if not tables:
        print("Данные не найдены")
        return

    for table in tables:
        for record in table.records:
            print(f"Time: {record.get_time()}, Temp: {record['_value']}, Room: {record['room']}")

    print("Чтение завершено")


def main():
    bucket = os.getenv("INFLUX_BUCKET")

    if not all([os.getenv("INFLUX_URL"), os.getenv("INFLUX_TOKEN")]):
        print("ОШИБКА: Не настроены переменные окружения (.env файл)")
        return

    try:
        client = get_client()
        client.ping()
        print("Подключение к InfluxDB успешно\n")

        write_data(client, bucket)
        time.sleep(1)
        read_data(client, bucket)

        client.close()
    except Exception as e:
        print(f"Произошла ошибка: {e}")


if __name__ == "__main__":
    main()