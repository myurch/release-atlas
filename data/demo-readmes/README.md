# Bundled public README examples

Historical public README snapshots captured on 2026-10-18. These remain as licensed regression fixtures for existing graph tests. The Sources demo button now imports the original [synthetic versioned corpus](../demo-documents/README.md), not these files. Builds do not refresh these snapshots.

README text is preserved verbatim in snapshots.json. Source IDs and SHA-256 fingerprints use the normal Atlas source format. Immutable origins and upstream license URLs are recorded alongside each source. Full copyright and license notices are in licenses/.

| Repository | Commit | License |
| --- | --- | --- |
| [myurch/werkzeug](https://github.com/myurch/werkzeug/blob/8393ee88aaacf7bcd3a0b1d604511f70c222df25/README.rst) | `8393ee88aaacf7bcd3a0b1d604511f70c222df25` | [BSD-3-Clause](licenses/myurch-werkzeug.txt) |
| [pallets/flask](https://github.com/pallets/flask/blob/d086db856be187255b8ec61ef409357393020f32/README.md) | `d086db856be187255b8ec61ef409357393020f32` | [BSD-3-Clause](licenses/pallets-flask.txt) |
| [pallets/jinja](https://github.com/pallets/jinja/blob/5ef70112a1ff19c05324ff889dd30405b1002044/README.md) | `5ef70112a1ff19c05324ff889dd30405b1002044` | [BSD-3-Clause](licenses/pallets-jinja.txt) |
| [pallets/click](https://github.com/pallets/click/blob/2247b35ea1c47c727d7a06e51fa280e12a863ff6/README.md) | `2247b35ea1c47c727d7a06e51fa280e12a863ff6` | [BSD-3-Clause](licenses/pallets-click.txt) |
| [pallets/markupsafe](https://github.com/pallets/markupsafe/blob/4e111271b1494995708a9e878a10829b5e10c7ba/README.md) | `4e111271b1494995708a9e878a10829b5e10c7ba` | [BSD-3-Clause](licenses/pallets-markupsafe.txt) |
| [pallets/quart](https://github.com/pallets/quart/blob/29d339c87f9efd1ba5268666e2404530fe078911/README.md) | `29d339c87f9efd1ba5268666e2404530fe078911` | [MIT](licenses/pallets-quart.txt) |

Snapshot acquisition used unauthenticated public Git HEAD resolution and HTTPS raw files pinned to the resolved commit, with no repository credentials. GitHub REST quota was exhausted during validation, confirming why runtime demo imports must not use that API. To intentionally refresh the bundle, resolve each public repository to an immutable commit, retrieve its README and license from that commit, preserve exact text, regenerate Source IDs/hashes, and rerun the bundle/import tests. Never silently replace the pinned data during startup or builds.
