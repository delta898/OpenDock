# Compatibility entry point. New usage: ./opendock <command> [arguments]
.DEFAULT_GOAL := help
.EXPORT_ALL_VARIABLES:
COMMAND := $(firstword $(MAKECMDGOALS))
ARGS := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
ARG_GOALS := $(filter-out $(COMMAND),$(ARGS))

.PHONY: help $(COMMAND) $(ARG_GOALS)
help:
	@./opendock help

ifneq ($(COMMAND),)
ifneq ($(COMMAND),help)
$(COMMAND):
	@./opendock $(COMMAND) $(ARGS)
endif
endif

ifneq ($(ARG_GOALS),)
$(ARG_GOALS):
	@:
endif

%:
	@:
