ROOT := $(CURDIR)
GROUPS_FILE := $(ROOT)/services/groups.conf
CHECKED_COMMANDS := up restart start build config
UNCHECKED_COMMANDS := down stop ps pull
COMMANDS := list check-config $(CHECKED_COMMANDS) $(UNCHECKED_COMMANDS) logs publish launch setup secrets action wp-multisite sync sync-dry-run
TARGET := $(word 2,$(MAKECMDGOALS))
ACTION := $(word 3,$(MAKECMDGOALS))

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
	@echo "  setup"
	@echo "  secrets"
	@echo "  action"
	@echo "  wp-multisite"
	@echo "  sync sync-dry-run"
	@echo
	@echo "Targets:"
	@echo "  infra, gateway, services, all, or any directory under services/"
	@echo "  service groups from services/groups.conf"
	@echo "  setup also supports mail"
	@echo
	@echo "Examples:"
	@echo "  Discover:"
	@echo "    make list"
	@echo "    make list services"
	@echo "    make list groups"
	@echo
	@echo "  Check:"
	@echo "    make check-config"
	@echo "    make check-config immich"
	@echo
	@echo "  Setup:"
	@echo "    make setup"
	@echo "    make setup mail"
	@echo "    make setup mastodon"
	@echo "    make setup media"
	@echo "    make secrets"
	@echo "    make secrets nextcloud"
	@echo
	@echo "  Start:"
	@echo "    make up infra"
	@echo "    make up wordpress"
	@echo "    make up media"
	@echo "    make up services"
	@echo "    make services"
	@echo "    make launch"
	@echo
	@echo "  Publish:"
	@echo "    make publish"
	@echo "    make publish services"
	@echo
	@echo "  Inspect:"
	@echo "    make logs wordpress"
	@echo "    make ps all"
	@echo
	@echo "  Service-specific:"
	@echo "    make action wordpress"
	@echo "    make action wordpress multisite"
	@echo "    make wp-multisite  # deprecated"
	@echo
	@echo "  Sync:"
	@echo "    make sync-dry-run test"
	@echo "    make sync test"

list:
	@if [ "$(TARGET)" = "groups" ]; then \
		if [ ! -f "$(GROUPS_FILE)" ]; then \
			echo "No service groups found."; \
		else \
			awk -F: 'NF >= 2 && $$1 !~ /^[[:space:]]*(#|$$)/ { gsub(/^[[:space:]]+|[[:space:]]+$$/, "", $$1); gsub(/^[[:space:]]+|[[:space:]]+$$/, "", $$2); printf "%s: %s\n", $$1, $$2 }' "$(GROUPS_FILE)"; \
		fi; \
	elif [ "$(TARGET)" = "services" ]; then \
		if [ -z "$(strip $(call service_targets))" ]; then \
			echo "No services found under services/*/compose.yml"; \
			exit 1; \
		fi; \
		printf '%s\n' $(call service_targets) | sort; \
	elif [ -n "$(TARGET)" ]; then \
		echo "Usage: make list [services|groups]"; \
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
		echo; \
		echo "Groups:"; \
		if [ ! -f "$(GROUPS_FILE)" ]; then \
			echo "  (none)"; \
		else \
			awk -F: 'NF >= 2 && $$1 !~ /^[[:space:]]*(#|$$)/ { gsub(/^[[:space:]]+|[[:space:]]+$$/, "", $$1); printf "  %s\n", $$1 }' "$(GROUPS_FILE)"; \
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

define group_targets
$(shell awk -F: -v group="$(1)" 'NF >= 2 { name=$$1; gsub(/^[[:space:]]+|[[:space:]]+$$/, "", name); if (name == group) { services=$$2; gsub(/^[[:space:]]+|[[:space:]]+$$/, "", services); print services; exit } }' "$(GROUPS_FILE)" 2>/dev/null)
endef

define reload_gateway
	if [ -f "$(ROOT)/gateway/compose.yml" ]; then \
		if docker ps --format '{{.Names}}' | grep -qx caddy; then \
			echo "==> gateway: caddy reload"; \
			docker exec caddy caddy reload --config /etc/caddy/Caddyfile || exit $$?; \
		else \
			echo "==> gateway: docker compose up"; \
			$(call compose_cmd) "gateway" up -d || exit $$?; \
		fi; \
	fi
endef

define ensure_generated_secrets
	OPEN_DOCK_QUIET_SECRETS=1 python3 "$(ROOT)/scripts/opendock-secrets.py" "$(1)"
endef

define run_post_launch_hooks
	run_post_launch_hook() { \
		hook_target="$$1"; \
		hook="$(ROOT)/services/$$hook_target/opendock-post-launch.py"; \
		if [ -f "$$hook" ]; then \
			echo "==> $$hook_target: post-launch"; \
			python3 "$$hook" || exit $$?; \
		fi; \
	}; \
	run_post_launch_target_hooks() { \
		hook_request="$$1"; \
		if [ -f "$(ROOT)/services/$$hook_request/compose.yml" ]; then \
			run_post_launch_hook "$$hook_request"; \
			return; \
		fi; \
		group_members="$$(awk -F: -v group="$$hook_request" 'NF >= 2 { name=$$1; gsub(/^[[:space:]]+|[[:space:]]+$$/, "", name); if (name == group) { services=$$2; gsub(/^[[:space:]]+|[[:space:]]+$$/, "", services); print services; exit } }' "$(GROUPS_FILE)" 2>/dev/null)"; \
		if [ -n "$$group_members" ]; then \
			for hook_target in $$group_members; do run_post_launch_hook "$$hook_target" || exit $$?; done; \
		else \
			run_post_launch_hook "$$hook_request"; \
		fi; \
	}; \
	case "$(1)" in \
		all|services) for hook_target in $(call service_targets); do run_post_launch_hook "$$hook_target" || exit $$?; done ;; \
		infra|gateway) : ;; \
		*) run_post_launch_target_hooks "$(1)" ;; \
	esac
endef

check-config:
	@target="$(TARGET)"; \
	if [ -z "$$target" ]; then target="all"; fi; \
	$(call check_config,$$target) || { \
		printf '%s\n' "Configuration is not ready. No services were changed."; \
		exit 0; \
	}

$(CHECKED_COMMANDS):
	@$(call require_target,$@)
	@if [ "$(TARGET)" = "all" ]; then \
		for target in $(call all_targets); do \
			if [ "$@" = "up" ]; then $(call ensure_generated_secrets,$$target) || exit $$?; fi; \
			$(call check_config_quiet,$$target) || exit $$?; \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ $(if $(filter up,$@),-d) || exit $$?; \
		done; \
	elif [ "$(TARGET)" = "services" ]; then \
		for target in $(call service_targets); do \
			if [ "$@" = "up" ]; then $(call ensure_generated_secrets,$$target) || exit $$?; fi; \
			$(call check_config_quiet,$$target) || exit $$?; \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ $(if $(filter up,$@),-d) || exit $$?; \
		done; \
	elif [ ! -f "$(ROOT)/services/$(TARGET)/compose.yml" ] && [ -n "$(strip $(call group_targets,$(TARGET)))" ]; then \
		for target in $(call group_targets,$(TARGET)); do \
			if [ "$@" = "up" ]; then $(call ensure_generated_secrets,$$target) || exit $$?; fi; \
			$(call check_config_quiet,$$target) || exit $$?; \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ $(if $(filter up,$@),-d) || exit $$?; \
		done; \
	else \
		$(call require_compose,$(TARGET)); \
		if [ "$@" = "up" ]; then $(call ensure_generated_secrets,$(TARGET)) || exit $$?; fi; \
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
	elif [ ! -f "$(ROOT)/services/$(TARGET)/compose.yml" ] && [ -n "$(strip $(call group_targets,$(TARGET)))" ]; then \
		for target in $(call group_targets,$(TARGET)); do \
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
			$(call ensure_generated_secrets,$$target) || exit $$?; \
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
	$(MAKE) --no-print-directory up "$$launch_target" || exit $$?; \
	$(call run_post_launch_hooks,$$launch_target); \
	if [ "$$launch_target" != "infra" ]; then \
		$(call reload_gateway); \
	fi; \
	$(MAKE) --no-print-directory publish "$$launch_target" || exit $$?

setup:
	@target="$(TARGET)"; \
	if [ -z "$$target" ]; then target="all"; fi; \
	python3 "$(ROOT)/scripts/opendock-config.py" "$$target"

secrets:
	@target="$(TARGET)"; \
	if [ -z "$$target" ]; then target="all"; fi; \
	python3 "$(ROOT)/scripts/opendock-secrets.py" "$$target"

action:
	@python3 "$(ROOT)/scripts/opendock-action.py" "$(TARGET)" "$(ACTION)"

wp-multisite:
	@printf '%s\n\n' "Deprecated: use 'make action wordpress multisite'."
	@$(MAKE) --no-print-directory action wordpress multisite

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
