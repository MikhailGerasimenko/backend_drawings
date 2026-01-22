.PHONY: help install install-dev run run-prod format format-check lint clean test test-cov docker-build docker-run docker-stop docker-logs docker-shell docker-rm docker-clean

# Переменные
PYTHON := python
POETRY := poetry
APP := app.main:app
HOST := 0.0.0.0
PORT := 8000
DOCKER_IMAGE := fastapi-template
DOCKER_CONTAINER := fastapi-template
DOCKER_TAG := latest

# Цвета для вывода
CYAN := \033[0;36m
GREEN := \033[0;32m
YELLOW := \033[0;33m
NC := \033[0m # No Color

help: ## Показать справку по командам
	@echo "$(CYAN)Доступные команды:$(NC)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-15s$(NC) %s\n", $$1, $$2}'

install: ## Установить зависимости проекта
	@echo "$(CYAN)Установка зависимостей...$(NC)"
	$(POETRY) install --no-root

install-dev: ## Установить зависимости проекта (включая dev)
	@echo "$(CYAN)Установка зависимостей (включая dev)...$(NC)"
	$(POETRY) install --no-root --with dev

run: ## Запустить приложение в режиме разработки (с hot reload)
	@echo "$(CYAN)Запуск приложения в режиме разработки...$(NC)"
	$(POETRY) run uvicorn $(APP) --reload --host $(HOST) --port $(PORT)

run-prod: ## Запустить приложение в production режиме (с Gunicorn)
	@echo "$(CYAN)Запуск приложения в production режиме...$(NC)"
	$(POETRY) run gunicorn $(APP) -c config/gunicorn_conf.py

format: ## Форматировать код (black + isort)
	@echo "$(CYAN)Форматирование кода...$(NC)"
	$(POETRY) run black app
	$(POETRY) run isort app

format-check: ## Проверить форматирование кода без изменений
	@echo "$(CYAN)Проверка форматирования кода...$(NC)"
	$(POETRY) run black --check app
	$(POETRY) run isort --check-only app

lint: format-check ## Проверить форматирование кода (алиас для format-check)

clean: ## Очистить кэш и временные файлы
	@echo "$(CYAN)Очистка кэша...$(NC)"
	find . -type d -name "__pycache__" -exec rm -r {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	find . -type d -name "*.egg-info" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -r {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -r {} + 2>/dev/null || true
	@echo "$(GREEN)Кэш очищен!$(NC)"

test: ## Run tests
	@echo "$(CYAN)Running tests...$(NC)"
	$(POETRY) run pytest

test-cov: ## Run tests with coverage
	@echo "$(CYAN)Running tests with coverage...$(NC)"
	$(POETRY) run pytest --cov=app --cov-report=term-missing

shell: ## Открыть Python shell с загруженным окружением
	@echo "$(CYAN)Запуск Python shell...$(NC)"
	$(POETRY) run python

update: ## Обновить зависимости
	@echo "$(CYAN)Обновление зависимостей...$(NC)"
	$(POETRY) update

lock: ## Обновить poetry.lock
	@echo "$(CYAN)Обновление poetry.lock...$(NC)"
	$(POETRY) lock --no-update

show-env: ## Показать текущие переменные окружения
	@echo "$(CYAN)Переменные окружения:$(NC)"
	@env | grep -E "(APP_|DEBUG|HOST|PORT|LOG_)" || echo "Переменные окружения не найдены"

docker-build: ## Собрать Docker образ
	@echo "$(CYAN)Сборка Docker образа...$(NC)"
	docker build -t $(DOCKER_IMAGE):$(DOCKER_TAG) .
	@echo "$(GREEN)Docker образ собран: $(DOCKER_IMAGE):$(DOCKER_TAG)$(NC)"

docker-run: ## Запустить Docker контейнер
	@echo "$(CYAN)Запуск Docker контейнера...$(NC)"
	@if [ -f .env ]; then \
		docker run -d \
			--name $(DOCKER_CONTAINER) \
			-p $(PORT):8000 \
			--env-file .env \
			$(DOCKER_IMAGE):$(DOCKER_TAG); \
	else \
		docker run -d \
			--name $(DOCKER_CONTAINER) \
			-p $(PORT):8000 \
			$(DOCKER_IMAGE):$(DOCKER_TAG); \
	fi
	@echo "$(GREEN)Контейнер запущен: $(DOCKER_CONTAINER)$(NC)"
	@echo "$(CYAN)Приложение доступно по адресу: http://localhost:$(PORT)$(NC)"

docker-stop: ## Остановить Docker контейнер
	@echo "$(CYAN)Остановка Docker контейнера...$(NC)"
	docker stop $(DOCKER_CONTAINER) 2>/dev/null || echo "$(YELLOW)Контейнер не запущен$(NC)"
	@echo "$(GREEN)Контейнер остановлен$(NC)"

docker-logs: ## Показать логи Docker контейнера
	@echo "$(CYAN)Логи Docker контейнера:$(NC)"
	docker logs -f $(DOCKER_CONTAINER)

docker-shell: ## Войти в shell Docker контейнера
	@echo "$(CYAN)Вход в Docker контейнер...$(NC)"
	docker exec -it $(DOCKER_CONTAINER) /bin/bash

docker-rm: ## Удалить Docker контейнер
	@echo "$(CYAN)Удаление Docker контейнера...$(NC)"
	docker rm $(DOCKER_CONTAINER) 2>/dev/null || echo "$(YELLOW)Контейнер не существует$(NC)"
	@echo "$(GREEN)Контейнер удален$(NC)"

docker-clean: docker-stop docker-rm ## Остановить и удалить Docker контейнер
	@echo "$(GREEN)Docker контейнер очищен$(NC)"

docker-up: docker-clean docker-build docker-run ## Собрать и запустить Docker контейнер
	@echo "$(GREEN)Docker контейнер запущен$(NC)"
	@echo "$(CYAN)Приложение доступно по адресу: http://localhost:$(PORT)$(NC)"