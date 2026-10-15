# The test configuration of the core

A configuration as a configuration repository holds it (ws help plan-v2,
8.11), with made-up values: one host per hardware adapter (t2-mbp16,
legion-go, generic-pc, container) and catalogs with several positions.

- The flake checks of the core build it (home-HOST, system-HOST; CI).
- The Python tests read its hosts and catalogs.
- ws setup --new (stage 9) starts a configuration from it.

The real configurations are repositories of their own (`ws help
architecture-v2`).
