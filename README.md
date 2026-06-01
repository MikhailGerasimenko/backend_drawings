# FastAPI Template

Шаблон проекта на FastAPI.

## Структура шаблона

```
fastapi-template/
├── app/
│   ├── __init__.py
│   ├── main.py              # Точка входа FastAPI приложения
│   ├── core/
│   │   ├── __init__.py
│   │   ├── config.py        # Настройки через pydantic-settings
│   │   ├── utils.py         # Утилиты (работа с timezone и т.д.)
│   │   ├── middleware.py    # Request ID middleware
│   │   ├── exceptions.py    # Кастомные исключения
│   │   └── handlers.py      # Обработчики исключений
│   └── api/
│       └── v1/
│           ├── __init__.py
│           ├── router.py    # Главный роутер API v1
│           ├── schemas/
│           │   ├── __init__.py
│           │   ├── responses.py  # Базовые схемы ответов
│           │   ├── health.py
│           │   ├── hello.py      # Схемы для hello endpoints
│           │   └── example.py    # Схемы для example endpoints
│           └── endpoints/
│               ├── __init__.py
│               ├── health.py
│               ├── hello.py
│               └── example.py    # Примеры использования
├── config/
│   └── gunicorn_conf.py     # Конфигурация Gunicorn
├── docker/                  # Локальный Jaeger для трейсинга (OTLP)
│   ├── docker-compose.jaeger.yml
│   └── jaeger-config.yaml
├── tests/                   # Тесты проекта
│   ├── __init__.py
│   ├── conftest.py          # Фикстуры для тестов
│   ├── test_main.py         # Тесты для root endpoint
│   ├── test_health.py       # Тесты для health endpoint
│   ├── test_hello.py         # Тесты для hello endpoints
│   ├── test_example.py       # Тесты для example endpoint
│   ├── test_utils.py         # Тесты для утилит
│   ├── test_middleware.py    # Тесты для middleware
│   ├── test_handlers.py      # Тесты для обработчиков исключений
│   └── test_exceptions.py    # Тесты для кастомных исключений
├── pyproject.toml           # Зависимости проекта
├── Makefile                 # Команды для удобной работы с проектом
└── README.md
```

## Установка

```bash
poetry install --no-root
```

Или используйте Makefile:

```bash
make install        # Установить зависимости
make install-dev    # Установить зависимости (включая dev)
```

## Настройка

Создайте файл `.env` на основе `.env.example` (если нужно изменить настройки по умолчанию):

```bash
APP_NAME="FastAPI Template"
APP_VERSION=1.0.0
DEBUG=false
HOST=0.0.0.0
PORT=8000
LOG_LEVEL=info
TIME_ZONE=Europe/Moscow
```

## Запуск

### Разработка (с hot reload)

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Или через Makefile:

```bash
make run
```

С OpenTelemetry (экспорт трейсов через OTLP):

```bash
make run-otel
```

### Production (с Gunicorn + Uvicorn workers)

```bash
gunicorn app.main:app -c config/gunicorn_conf.py
```

Или через Makefile:

```bash
make run-prod
```

Production c OpenTelemetry:

```bash
make run-prod-otel
```

Или с указанием параметров:

```bash
gunicorn app.main:app \
    --workers 4 \
    --worker-class uvicorn.workers.UvicornWorker \
    --bind 0.0.0.0:8000
```

Приложение будет доступно по адресу: http://localhost:8000

## OpenTelemetry

Zero-code трейсинг: приложение запускается через `opentelemetry-instrument`, который
подключает инструментацию FastAPI/Starlette и отправляет спаны по OTLP.

Добавленные зависимости:
- `opentelemetry-distro`
- `opentelemetry-exporter-otlp`
- `opentelemetry-instrumentation-fastapi`

Базовые переменные окружения (см. `.env.example`):

```bash
OTEL_SERVICE_NAME=fastapi-template
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_TRACES_EXPORTER=otlp
OTEL_TRACES_SAMPLER=always_on
OTEL_METRICS_EXPORTER=none
OTEL_LOGS_EXPORTER=none
```

### Локальный Jaeger (в этом репозитории)

Нужен **Docker** (демон отвечает на `docker info`) или **Podman**. В `Makefile` сначала
используется Docker, иначе Podman; `make check-runtime` покажет выбранные команды. Из корня
шаблона:

```bash
make jaeger-up
```

- UI: [http://localhost:16686](http://localhost:16686)
- OTLP HTTP: `http://localhost:4318` (как в `.env.example`)

Дальше скопируйте `OTEL_*` из `.env.example` в `.env` и запускайте приложение одним из двух способов:

1) Разовый запуск с явными OTEL переменными:

```bash
OTEL_SERVICE_NAME=fastapi-template \
OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4318 \
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf \
OTEL_TRACES_EXPORTER=otlp \
OTEL_TRACES_SAMPLER=always_on \
OTEL_METRICS_EXPORTER=none \
OTEL_LOGS_EXPORTER=none \
make run-otel
```

2) Подгрузить `.env` в текущую shell-сессию и запускать через Makefile:

```bash
set -a
source .env
set +a
make run-otel
```

3) Использовать отдельную цель Makefile с автоподгрузкой `.env`:

```bash
make run-otel-env
```

После запуска откройте API (например, `/api/v1/health`) и в Jaeger выберите сервис `OTEL_SERVICE_NAME` (по умолчанию `fastapi-template`).

Если в Jaeger отображается `unknown_service`, значит не подхватился `OTEL_SERVICE_NAME`: проверьте, что shell загрузила `.env`, и что значения с пробелами в `.env` указаны в кавычках (например, `APP_NAME="FastAPI Template"`).

```bash
make jaeger-down   # остановить Jaeger; том с Badger сохраняется
make jaeger-logs   # логи
```

Для контейнерного запуска приложения endpoint в `OTEL_EXPORTER_OTLP_*` должен указывать на
OTLP, доступный **из контейнера** (часто `http://host.docker.internal:4318` или DNS сервиса в k8s), а не `localhost` с хоста.

## Тестирование

Проект включает набор тестов для всех основных компонентов.

### Запуск тестов

```bash
# Запустить все тесты
make test

# Запустить тесты с покрытием кода
make test-cov

# Или напрямую через pytest
poetry run pytest
poetry run pytest --cov=app --cov-report=term-missing
```

### Структура тестов

Тесты организованы по модулям:
- `test_main.py` - тесты для root endpoint
- `test_health.py` - тесты для health check endpoint
- `test_hello.py` - тесты для hello endpoints
- `test_example.py` - тесты для example endpoint с обработкой ошибок
- `test_utils.py` - тесты для утилит (timezone и т.д.)
- `test_middleware.py` - тесты для RequestIDMiddleware
- `test_handlers.py` - тесты для обработчиков исключений
- `test_exceptions.py` - тесты для кастомных исключений

Все тесты используют маркер `@pytest.mark.unit` для категоризации.

## Эндпоинты

### Root
- **GET** `/` - Корневой эндпоинт с информацией о приложении

### Health Check
- **GET** `/api/v1/health` - Проверка состояния сервиса

### Hello World
- **GET** `/api/v1/` - Базовое приветствие (простой формат)
- **GET** `/api/v1/hello/{name}` - Персонализированное приветствие (простой формат)
- **GET** `/api/v1/hello-formatted/{name}` - Персонализированное приветствие (единый формат)

### Example
- **GET** `/api/v1/example/{item_id}` - Пример эндпоинта с единым форматом и обработкой ошибок

## Документация API

После запуска приложения доступна автоматическая документация:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## Возможности шаблона

### Request ID Middleware
Каждый запрос автоматически получает уникальный `request_id`, который:
- Добавляется в заголовок `X-Request-ID` ответа
- Доступен в эндпоинтах через `request.state.request_id`
- Полезен для трейсинга и логирования

### Единый формат ответа (опционально)
Шаблон поддерживает два подхода к формату ответов:

1. **Простой формат** (по умолчанию) - возвращайте данные напрямую:
```python
@router.get("/simple")
async def simple_endpoint():
    return {"message": "Hello"}
```

2. **Единый формат** - используйте обертку с `request_id` и `timestamp`.

   **Важно:** Для корректного отображения структуры данных в Swagger/ReDoc документации создавайте конкретные схемы данных и наследуйте от `BaseResponse`:

```python
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from app.api.v1.schemas.responses import BaseResponse
from app.core.utils import get_current_timestamp

# 1. Создайте схему данных
class ItemData(BaseModel):
    """Данные элемента."""
    id: int = Field(..., description="Идентификатор")
    name: str = Field(..., description="Название")
    status: str = Field(..., description="Статус")

# 2. Создайте схему ответа с явным типом data
class ItemResponse(BaseResponse[ItemData]):
    """Ответ с данными элемента."""
    data: ItemData = Field(..., description="Данные элемента")

# 3. Используйте в эндпоинте
@router.get("/items/{item_id}", response_model=ItemResponse)
async def get_item(item_id: int, request: Request):
    data = ItemData(id=item_id, name=f"Item {item_id}", status="active")
    return ItemResponse(
        request_id=request.state.request_id,
        timestamp=get_current_timestamp(),
        data=data,
    )
```

   Это обеспечит правильное отображение структуры `data` в документации API вместо пустого объекта `{}`.

### Обработка ошибок
Шаблон включает единую обработку ошибок:
- Автоматический формат ошибок с `request_id` и `timestamp`
- Кастомные исключения в `app/core/exceptions.py`
- Валидация ошибок с детальной информацией о полях

Пример использования:
```python
from app.core.exceptions import NotFoundError

@router.get("/items/{item_id}")
async def get_item(item_id: int):
    if item_id < 1:
        raise NotFoundError(f"Item {item_id} not found")
    return {"id": item_id}
```

### Timezone
Шаблон поддерживает настройку timezone для временных меток:
- По умолчанию используется `Europe/Moscow`
- Настраивается через переменную окружения `TIME_ZONE`
- Все временные метки в ответах API используют настроенный timezone
- Утилита `get_current_timestamp()` из `app/core/utils.py` возвращает время в формате ISO с учетом timezone

Пример:
```python
from app.core.utils import get_current_timestamp

# Вернет время в формате: "2026-01-22T15:00:00+03:00" (для Europe/Moscow)
timestamp = get_current_timestamp()
```

### Тестирование
Шаблон включает полный набор тестов:
- Unit тесты для всех компонентов (эндпоинты, middleware, handlers, utils)
- Использование моков для изоляции тестов
- Покрытие кода через pytest-cov

### Makefile
Проект включает Makefile с удобными командами:

```bash
make help          # Показать все доступные команды
make install       # Установить зависимости
make install-dev   # Установить зависимости (включая dev)
make run           # Запустить в режиме разработки
make run-prod      # Запустить в production режиме
make test          # Запустить тесты
make test-cov      # Запустить тесты с покрытием кода
make format        # Форматировать код (black + isort)
make lint          # Проверить форматирование
make clean         # Очистить кэш
make check-runtime # Какой выбран Docker / Podman
make jaeger-up     # Локальный Jaeger (трейсы)
make jaeger-down   # Остановить Jaeger
make docker-build  # Собрать образ (docker/podman build)
make docker-run    # Запустить контейнер
```

Полный список команд: `make help`