ROOT := $(CURDIR)
CHECKED_COMMANDS := up restart start build config
UNCHECKED_COMMANDS := down stop ps pull
COMMANDS := list check-config $(CHECKED_COMMANDS) $(UNCHECKED_COMMANDS) logs publish launch wp-multisite sync sync-dry-run
TARGET := $(word 2,$(MAKECMDGOALS))

-include .sync.env
.EXPORT_ALL_VARIABLES:

.PHONY: help list services $(COMMANDS) infra gateway all test

help:
	@echo "Usage:"
	@echo "  make <command> <target>"
	@echo
	@echo "Commands:"
	@echo "  list"
	@echo "  check-config"
	@echo "  up down restart stop start ps logs pull build config"
	@echo "  publish launch"
	@echo "  wp-multisite"
	@echo "  sync sync-dry-run"
	@echo
	@echo "Targets:"
	@echo "  infra, gateway, services, all, or any directory under services/"
	@echo
	@echo "Examples:"
	@echo "  make list"
	@echo "  make list services"
	@echo "  make check-config"
	@echo "  make check-config immich"
	@echo "  make up infra"
	@echo "  make up wordpress"
	@echo "  make logs wordpress"
	@echo "  make ps all"
	@echo "  make publish"
	@echo "  make publish services"
	@echo "  make launch"
	@echo "  make wp-multisite"
	@echo "  make services"
	@echo "  make up services"
	@echo "  make sync-dry-run test"
	@echo "  make sync test"

list:
	@if [ "$(TARGET)" = "services" ]; then \
		if [ -z "$(strip $(call service_targets))" ]; then \
			echo "No services found under services/*/compose.yml"; \
			exit 1; \
		fi; \
		printf '%s\n' $(call service_targets) | sort; \
	elif [ -n "$(TARGET)" ]; then \
		echo "Usage: make list [services]"; \
		exit 1; \
	else \
		echo "Core:"; \
		echo "  infra"; \
		if [ -f "$(ROOT)/gateway/compose.yml" ]; then echo "  gateway"; fi; \
		echo; \
		echo "Services:"; \
		if [ -z "$(strip $(call service_targets))" ]; then \
			echo "  (none)"; \
		else \
			printf '  %s\n' $(call service_targets) | sort; \
		fi; \
	fi

define target_dir
$(if $(filter infra gateway,$(1)),$(ROOT)/$(1),$(ROOT)/services/$(1))
endef

define require_target
	test -n "$(TARGET)" || { echo "Usage: make $(1) <target>"; exit 1; }
endef

define require_compose
	test "$(1)" = "all" -o -f "$(call target_dir,$(1))/compose.yml" || \
		{ echo "Unknown target or missing compose.yml: $(1)"; exit 1; }
endef

define check_config
	"$(ROOT)/scripts/check-config.sh" "$(1)"
endef

define check_config_quiet
	CHECK_CONFIG_QUIET=1 "$(ROOT)/scripts/check-config.sh" "$(1)"
endef

define compose_cmd
run_compose() { \
	compose_target="$$1"; shift; \
	case "$$compose_target" in \
		infra|gateway) dir="$(ROOT)/$$compose_target" ;; \
		*) dir="$(ROOT)/services/$$compose_target" ;; \
	esac; \
	test -f "$$dir/compose.yml" || { echo "Unknown target or missing compose.yml: $$compose_target"; exit 1; }; \
	test -f "$(ROOT)/common.env" || { printf '%s\n' "Missing required file: common.env" "" "To continue:" "  cp common.env.example common.env" "  nano common.env" "  make check-config"; exit 1; }; \
	env_files="--env-file $(ROOT)/common.env"; \
	if [ -f "$$dir/.env" ]; then env_files="$$env_files --env-file $$dir/.env"; fi; \
	docker compose --project-directory "$$dir" $$env_files -f "$$dir/compose.yml" -p "$$compose_target" "$$@"; \
}; run_compose
endef

define all_targets
infra $(if $(wildcard $(ROOT)/gateway/compose.yml),gateway) $(call service_targets)
endef

define service_targets
$(shell find "$(ROOT)/services" -mindepth 2 -maxdepth 2 -name compose.yml -exec sh -c 'basename "$$(dirname "$$1")"' _ {} \; 2>/dev/null)
endef

define reload_gateway
	if [ -f "$(ROOT)/gateway/compose.yml" ]; then \
		if docker ps --format '{{.Names}}' | grep -qx caddy; then \
			echo "==> gateway: caddy reload"; \
			docker exec caddy caddy reload --config /etc/caddy/Caddyfile; \
		else \
			echo "==> gateway: docker compose up"; \
			$(call compose_cmd) "gateway" up -d; \
		fi; \
	fi
endef

check-config:
	@target="$(TARGET)"; \
	if [ -z "$$target" ]; then target="all"; fi; \
	$(call check_config,$$target)

$(CHECKED_COMMANDS):
	@$(call require_target,$@)
	@if [ "$(TARGET)" = "all" ]; then \
		for target in $(call all_targets); do \
			$(call check_config_quiet,$$target) || exit $$?; \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ $(if $(filter up,$@),-d) || exit $$?; \
		done; \
	elif [ "$(TARGET)" = "services" ]; then \
		for target in $(call service_targets); do \
			$(call check_config_quiet,$$target) || exit $$?; \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ $(if $(filter up,$@),-d) || exit $$?; \
		done; \
	else \
		$(call require_compose,$(TARGET)); \
		$(call check_config_quiet,$(TARGET)) || exit $$?; \
		echo "==> $(TARGET): docker compose $@"; \
		$(call compose_cmd) "$(TARGET)" $@ $(if $(filter up,$@),-d); \
	fi

$(UNCHECKED_COMMANDS):
	@$(call require_target,$@)
	@if [ "$(TARGET)" = "all" ]; then \
		for target in $(call all_targets); do \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ || exit $$?; \
		done; \
	elif [ "$(TARGET)" = "services" ]; then \
		for target in $(call service_targets); do \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ || exit $$?; \
		done; \
	else \
		$(call require_compose,$(TARGET)); \
		echo "==> $(TARGET): docker compose $@"; \
		$(call compose_cmd) "$(TARGET)" $@ $(if $(filter up,$@),-d); \
	fi

services:
	@if [ "$(firstword $(MAKECMDGOALS))" != "services" ]; then \
		:; \
	elif [ -z "$(strip $(call service_targets))" ]; then \
		echo "No services found under services/*/compose.yml"; \
		exit 1; \
	else \
		for target in $(call service_targets); do \
			$(call check_config_quiet,$$target) || exit $$?; \
			echo "==> $$target: docker compose up"; \
			$(call compose_cmd) "$$target" up -d || exit $$?; \
		done; \
	fi

logs:
	@$(call require_target,$@)
	@if [ "$(TARGET)" = "all" ]; then \
		echo "Usage: make logs <target>"; \
		exit 1; \
	else \
		$(call require_compose,$(TARGET)); \
		$(call compose_cmd) "$(TARGET)" logs -f; \
	fi

publish:
	@target="$(TARGET)"; \
	if [ -z "$$target" ]; then target="all"; fi; \
	"$(ROOT)/scripts/publish-cloudflare.sh" "$$target"

launch:
	@launch_target="$(TARGET)"; \
	if [ -z "$$launch_target" ]; then launch_target="all"; fi; \
	if [ "$$launch_target" != "all" ] && [ "$$launch_target" != "infra" ]; then \
		echo "==> infra: launch prerequisite"; \
		$(MAKE) --no-print-directory up infra || exit $$?; \
	fi; \
	$(MAKE) --no-print-directory up "$$launch_target"; \
	if [ "$$launch_target" != "infra" ]; then \
		$(call reload_gateway); \
	fi; \
	$(MAKE) --no-print-directory publish "$$launch_target"

wp-multisite:
	@python3 "$(ROOT)/scripts/wp-multisite.py" $(if $(YES),--yes)

sync sync-dry-run:
	@$(call require_target,$@)
	@upper=$$(printf '%s' "$(TARGET)" | tr '[:lower:]' '[:upper:]' | tr '-' '_'); \
	eval "remote=\$${SYNC_$${upper}_REMOTE}"; \
	eval "path=\$${SYNC_$${upper}_PATH}"; \
	eval "port=\$${SYNC_$${upper}_SSH_PORT}"; \
	test -n "$$remote" || { echo "Missing SYNC_$${upper}_REMOTE in .sync.env"; exit 1; }; \
	test -n "$$path" || { echo "Missing SYNC_$${upper}_PATH in .sync.env"; exit 1; }; \
	if [ -n "$$port" ]; then export RSYNC_RSH="ssh -p $$port"; fi; \
	dry_run=""; \
	if [ "$@" = "sync-dry-run" ]; then dry_run="--dry-run"; fi; \
	echo "Sync target: $(TARGET)"; \
	echo "Source: $(ROOT)/"; \
	echo "Destination: $$remote:$$path/"; \
	if [ "$@" = "sync-dry-run" ]; then echo "Mode: dry-run"; fi; \
	rsync -azih --delete $$dry_run \
		--exclude=".git/" \
		--exclude=".sync.env" \
		--exclude="common.env" \
		--include="common.env.example" \
		--exclude="cloudflare.env" \
		--include="cloudflare.env.example" \
		--exclude="services/*/data/" \
		--exclude="**/data/" \
		--exclude=".DS_Store" \
		"$(ROOT)/" "$$remote:$$path/"; \
	echo "Done."

%:
	@:

infra gateway all test:
	@:
