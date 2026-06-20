ROOT := $(CURDIR)
COMMANDS := up down restart stop start ps logs pull build config
TARGET := $(word 2,$(MAKECMDGOALS))

.PHONY: help list $(COMMANDS) infra gateway all

help:
	@echo "Usage:"
	@echo "  make <command> <target>"
	@echo
	@echo "Commands:"
	@echo "  up down restart stop start ps logs pull build config"
	@echo
	@echo "Targets:"
	@echo "  infra, gateway, all, or any directory under services/"
	@echo
	@echo "Examples:"
	@echo "  make up infra"
	@echo "  make up wordpress"
	@echo "  make logs wordpress"
	@echo "  make ps all"

list:
	@echo "infra"
	@if [ -f "$(ROOT)/gateway/compose.yml" ]; then echo "gateway"; fi
	@find "$(ROOT)/services" -mindepth 2 -maxdepth 2 -name compose.yml -exec dirname {} \; 2>/dev/null | xargs -n 1 basename | sort

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

define compose_cmd
run_compose() { \
	target="$$1"; shift; \
	case "$$target" in \
		infra|gateway) dir="$(ROOT)/$$target" ;; \
		*) dir="$(ROOT)/services/$$target" ;; \
	esac; \
	test -f "$$dir/compose.yml" || { echo "Unknown target or missing compose.yml: $$target"; exit 1; }; \
	docker compose --project-directory "$$dir" -f "$$dir/compose.yml" -p "$$target" "$$@"; \
}; run_compose
endef

define all_targets
infra $(if $(wildcard $(ROOT)/gateway/compose.yml),gateway) $(shell find "$(ROOT)/services" -mindepth 2 -maxdepth 2 -name compose.yml -exec dirname {} \; 2>/dev/null | xargs -n 1 basename)
endef

up down restart stop start ps pull build config:
	@$(call require_target,$@)
	@if [ "$(TARGET)" = "all" ]; then \
		for target in $(call all_targets); do \
			echo "==> $$target: docker compose $@"; \
			$(call compose_cmd) "$$target" $@ $(if $(filter up,$@),-d) || exit $$?; \
		done; \
	else \
		$(call require_compose,$(TARGET)); \
		$(call compose_cmd) "$(TARGET)" $@ $(if $(filter up,$@),-d); \
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

%:
	@:

infra gateway all:
	@:
