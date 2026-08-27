ROOT := $(CURDIR)
GROUPS_FILE := $(ROOT)/services/groups.conf
CHECKED_COMMANDS := up restart start build config
UNCHECKED_COMMANDS := down stop ps pull
COMMANDS := list check-config $(CHECKED_COMMANDS) $(UNCHECKED_COMMANDS) logs publish launch setup secrets action wp-multisite sync sync-dry-run
COMMAND := $(firstword $(MAKECMDGOALS))
REQUESTED_TARGET := $(word 2,$(MAKECMDGOALS))
TARGET := $(if $(REQUESTED_TARGET),$(REQUESTED_TARGET),$(if $(filter config ps,$(COMMAND)),all))
ACTION := $(word 3,$(MAKECMDGOALS))

-include .sync.env
.EXPORT_ALL_VARIABLES:

.PHONY: help list services $(COMMANDS) infra gateway all test

help:
	@printf '%s\n' \
		"OpenDock command guide" \
		"" \
		"Quick start:" \
		"  make setup                     Create/review local config and generate secrets" \
		"  make launch [target]           Recommended: prepare, start, check, and publish" \
		"  make list                      Show every discovered service and group" \
		"" \
		"Target syntax:" \
		"  [target]  optional; omitted means all where supported" \
		"  <target>  required" \
		"  <service> one services/<name>/compose.yml project (example: supabase)" \
		"  <group>   purpose-based alias from services/groups.conf (example: media)" \
		"  services  every application service; excludes infra and gateway" \
		"  all       infra + gateway + every application service" \
		"  infra     shared databases, Redis, and Docker network" \
		"  gateway   Caddy only" \
		"  mail      setup-only target for shared SMTP settings" \
		"  Discover names with: make list | make list services | make list groups" \
		"" \
		"Configuration:" \
		"  make setup [target]            Interactive config; keeps existing values" \
		"  make check-config [target]     Read-only validation; changes nothing" \
		"  make secrets [target]          Generate only missing passwords and keys" \
		"" \
		"Start and lifecycle:" \
		"  make launch [target]           Starts infra, target, service hooks, gateway, and routes" \
		"  make up <target>               Compose up/create/recreate; no prerequisites or publishing" \
		"  make start <target>            Start existing stopped containers" \
		"  make restart <target>          Restart existing containers; does not apply env/config changes" \
		"  make stop <target>             Stop containers without removing them" \
		"  make down <target>             Remove containers/network; persistent data is kept" \
		"  make services                  Shortcut for make up services; infra must already exist" \
		"" \
		"Inspect and update:" \
		"  make ps [target]               Show status; omitted target means all" \
		"  make logs <target>             Follow one project; groups/services/all are unsupported" \
		"  make config [target]           Render Compose config; omitted target means all" \
		"  make pull <target>             Pull service images" \
		"  make build <target>            Build images declared by the service" \
		"" \
		"Routing and publishing:" \
		"  make publish [target]          Sync/print routes only; does not start containers" \
		"  make launch [target]           Start and publish in one workflow" \
		"" \
		"Service-specific actions:" \
		"  make action <service>          List actions available for that service" \
		"  make action <service> <action> Run one action" \
		"  make action supabase api-keys  Print the client-safe URL and publishable key" \
		"  make action supabase functions-secrets" \
		"                                Inspect Edge Function secret names/instructions" \
		"  make action wordpress multisite" \
		"                                Convert WordPress to subdirectory multisite" \
		"" \
		"Test-machine sync (configured in .sync.env):" \
		"  make sync-dry-run <name>       Preview rsync changes first" \
		"  make sync <name>               Apply rsync to the named remote" \
		"" \
		"Common examples:" \
		"  make launch supabase           Launch one service with prerequisites" \
		"  make launch media              Launch the Immich + Jellyfin group" \
		"  make logs wordpress            Follow WordPress logs" \
		"  make ps all                    Show status across the whole stack" \
		"" \
		"Deprecated: make wp-multisite (use make action wordpress multisite)"

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
		--exclude="services/supabase/functions.env" \
		--include="services/supabase/functions.env.example" \
		--exclude="services/*/data/" \
		--exclude="**/data/" \
		--exclude=".DS_Store" \
		"$(ROOT)/" "$$remote:$$path/"; \
	echo "Done."

%:
	@:

infra gateway all test:
	@:
