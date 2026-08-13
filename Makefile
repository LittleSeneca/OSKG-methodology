PYTHON ?= python3
PREFIX ?= $(HOME)/.local
SKILLS ?= $(HOME)/.hermes/skills/research

.PHONY: help test lint install uninstall install-skill check clean

help:
	@echo "make test           run the test suite (stdlib unittest, no network)"
	@echo "make check          test + a scaffold/dry-run smoke test"
	@echo "make install        symlink oskg into $(PREFIX)/bin"
	@echo "make install-skill  copy the Hermes skill into $(SKILLS)"
	@echo "make uninstall      remove the symlink"

test:
	@$(PYTHON) -m unittest discover -s tests -t . -v

# The dry run exercises scaffolding, manifest round-tripping, every phase
# driver's plan(), and the projection — without a single model call.
check: test
	@rm -rf .check && mkdir -p .check
	@$(PYTHON) -m oskg build "a smoke test topic for the check target" \
		--parent .check --budget 20 --dry-run --no-git >/dev/null
	@$(PYTHON) -m oskg validate .check/OSKG-SmokeTestTopic
	@rm -rf .check
	@echo "check: ok"

install:
	@mkdir -p $(PREFIX)/bin
	@ln -sf $(CURDIR)/bin/oskg $(PREFIX)/bin/oskg
	@echo "installed: $(PREFIX)/bin/oskg -> $(CURDIR)/bin/oskg"
	@command -v oskg >/dev/null || echo "note: $(PREFIX)/bin is not on your PATH"

uninstall:
	@rm -f $(PREFIX)/bin/oskg
	@echo "removed $(PREFIX)/bin/oskg"

install-skill:
	@mkdir -p $(SKILLS)
	@cp -R skills/oskg-pipeline $(SKILLS)/
	@echo "installed: $(SKILLS)/oskg-pipeline"
	@echo 'try: hermes chat  ->  "build me a knowledge graph about X"'

clean:
	@find . -name '__pycache__' -type d -prune -exec rm -rf {} + 2>/dev/null || true
	@rm -rf .check build dist *.egg-info
