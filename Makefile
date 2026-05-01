# =============================================================================
# RafRaf - Dev Environment Makefile
# =============================================================================

COMPOSE_FILE := infra/docker/docker-compose.dev.yml
COMPOSE_CMD := docker compose -f $(COMPOSE_FILE)

# .env dosyasi yoksa .env.example'dan kopyala
ifeq (,$(wildcard .env))
$(shell cp .env.example .env 2>/dev/null)
endif

# Env dosyasini yukle
ifneq (,$(wildcard .env))
include .env
export
endif

.PHONY: help up down restart status logs reset ps \
        db-shell redis-shell db-reset

# ---------- Yardim ----------

help: ## Bu yardim mesajini goster
	@echo "RafRaf Dev Environment"
	@echo "====================="
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

# ---------- Docker Compose ----------

up: ## Tum servisleri baslat (postgres, redis)
	$(COMPOSE_CMD) up -d
	@echo ""
	@echo "Servisler baslatildi. Durum kontrol: make status"

down: ## Tum servisleri durdur
	$(COMPOSE_CMD) down

restart: ## Tum servisleri yeniden baslat
	$(COMPOSE_CMD) restart

status: ## Servis durumlarini goster
	$(COMPOSE_CMD) ps

logs: ## Tum servislerin loglarini goster
	$(COMPOSE_CMD) logs -f

ps: ## Calisan container'lari listele
	$(COMPOSE_CMD) ps

# ---------- Veritabani ----------

db-shell: ## PostgreSQL shell ac
	$(COMPOSE_CMD) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

redis-shell: ## Redis CLI ac
	$(COMPOSE_CMD) exec redis redis-cli

db-reset: ## Veritabanini sifirla (volume sil + yeniden olustur)
	$(COMPOSE_CMD) down -v
	$(COMPOSE_CMD) up -d postgres redis
	@echo "Veritabani sifirlandi. PostgreSQL ve Redis yeniden baslatildi."

# ---------- Tam Reset ----------

reset: ## Tum servisleri ve volume'leri sil, sifirdan baslat
	$(COMPOSE_CMD) down -v --remove-orphans
	$(COMPOSE_CMD) up -d
	@echo ""
	@echo "Tum servisler sifirdan baslatildi."
