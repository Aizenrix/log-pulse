# LogPulse
Автор: Васильев Данил Вячеславович. Индивидуальный проект по дисциплине «Внедрение и поддержка компьютерных систем».

## Архитектура
Клиент -> FastAPI -> Redis Stream -> Worker -> Redis Hash / Sorted Set.
API отдельно читает статистику из Redis. Схема: architecture.drawio.

## Запуск
Требования: Docker Engine с Docker Compose v2.
```sh
cp .env.example .env
docker compose up --build -d
docker compose ps
docker compose logs --tail=50 api worker redis
docker compose exec api pytest -q
```
HTTP: http://127.0.0.1:8000; Swagger: http://127.0.0.1:8000/docs; OpenAPI: http://127.0.0.1:8000/openapi.json.
Redis не публикует порт. Redis использует AOF appendfsync always и volume redis-data.

## Примеры запросов
```sh
curl http://127.0.0.1:8000/health
python -c 'import json,pathlib; print(json.dumps({"lines":pathlib.Path("data/sample.log").read_text().splitlines()}))' > /tmp/logpulse-input.json
curl -H 'Content-Type: application/json' --data-binary @/tmp/logpulse-input.json http://127.0.0.1:8000/ingest
curl http://127.0.0.1:8000/stats
curl 'http://127.0.0.1:8000/events?limit=10'
docker compose exec redis redis-cli XINFO STREAM logpulse:events
docker compose exec redis redis-cli XLEN logpulse:events
docker compose exec redis redis-cli HGETALL logpulse:stats:level
docker compose exec redis redis-cli ZREVRANGE logpulse:slow 0 4 WITHSCORES
```
`IngestRequest.lines`: 1–100 строк по 1–500 символов. Пустую строку Pydantic отклоняет как ошибку структуры всего запроса 422; парсер также проверяет её отдельным тестом.
`IngestResponse`: accepted, rejected, errors (номер и причина). `HealthResponse`: status и redis. `StatsResponse`: queued_total (длина сохраняемого Stream), processed_total, level, service, status, top_slow. `EventResponse`: id и fields. Ошибки 422 и 503 имеют оболочку error с code и message. Отклонённые лог-записи возвращаются в errors при HTTP 200.

## Восстановление
Сначала загрузите sample.log, дождитесь processed_total=36. Сохраните /stats.
```sh
docker compose restart redis
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/stats
```
При недоступном Redis API отвечает 503, worker повторяет соединение через 1 секунду. После готовности API автоматически соединяется заново. Worker читает свои pending записи и забирает чужие старше 30 секунд через XAUTOCLAIM. Не применяйте down -v: команда удаляет данные.
Автоматизированная проверка: `docker compose exec api python scripts/verify.py` (без рестарта); подробный порядок и факты локальной проверки см. evidence/integration.json и отчёт. Docker в среде подготовки отсутствовал: его команды не выдаются за выполненные.

## Тесты и история
`python -m pytest -q`: изолированный fakeredis на каждый тест, рабочая база не затрагивается. Настоящий Redis проверен отдельно; это не заменяет проверку Compose.
```sh
git log --graph --oneline --all --decorate
git bundle verify history.bundle
git clone -b main history.bundle logpulse-restored
```
Bundle передаётся рядом с проектом. История содержит feature/parser, feature/redis и merge-коммиты.

## Ограничения
Учебная система без авторизации, для локального запуска. Не открывайте API в Интернет. Stream и множество обработанных ID растут без очистки. Идемпотентность действует по ID сообщения Stream, повторный POST создаёт новые события и снова увеличивает счётчики. При потере ответа на EXEC клиент не знает, был ли пакет принят: автоматический повтор POST может создать дубли. rid предполагается уникальным у исходных событий; повтор rid заменяет элемент рейтинга. Чтение разных статистических структур не является единым снимком при одновременной обработке. AOF не заменяет резервное копирование. Redis Lua не откатывает уже выполненные команды при ошибке типов: ключи проекта не следует изменять вручную. Метрики и ACL для промышленной среды не настроены.
