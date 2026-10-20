# Hosted deployment validation

Prepared October 19, 2026. This record describes a deployment candidate, not a live cloud release.

## Acceptance criteria

Use the existing GPT Site URL for the live Atlas HTML and API. Preserve the Python analysis implementation, workspace persistence, revision checks, streaming updates and Ask Atlas. Require a private gateway connection and user sign-in before workspace access or model calls. Keep API credentials out of Git, browser assets, responses and logs. Verify a real provider response only after provisioning.

## Cycle ledger

| Cycle | Change | Validation | Review and improvement | Next action |
| --- | --- | --- | --- | --- |
| 1 | Added hosted startup validation, private gateway guard and Site reverse proxy. | 425 Python tests passed; initial 10 proxy tests, typecheck and Worker build passed. | Review found PUT was missing from the proxy, affecting profiles and reviews. | Add PUT and a cross-service probe. |
| 2 | Added PUT, strict cookie forwarding, matching secure logout attributes and real-HTTP gateway probe. | 11 proxy tests and real-HTTP sign-in, analysis, review, profile, SSE and chat-stream checks passed. | Initial probe correctly dropped an insecure cookie because its synthetic environment patch ended too early. Kept the patch active for the complete test. Generation remains explicitly mocked. | Validate container storage and restart. |
| 3 | Added Render configuration and custom-port Docker health check; exercised a disposable container/disk. | Docker build succeeded. Non-root startup, real analysis/review, 512 MB limit and persistence across restart passed. Sample memory: 131.1 MiB. | Initial restart probe used Docker's old ephemeral host port. Resolving the mapped port after restart fixed the test harness. No application data failure occurred. | Final regression, secret scan, source commit/package. |
| 4 | Updated deployment documentation and reviewed the candidate. | 425 Python tests, 11 proxy tests, TypeScript check, Worker build, real-HTTP gateway probe and Docker persistence probe passed. | No remaining material local integration finding. Cloud deployment and actual OpenAI access are still unverified. | Connect hosting account, approve charges, provision secrets/disk, then deploy and smoke-test production. |

## Lightsail deployment cycle

The hosting target changed to AWS Lightsail. The Render configuration remains optional and was not provisioned. `deploy/lightsail/` prepares a single Linux virtual server with a private Atlas container, a pinned Caddy HTTPS proxy and named data/certificate volumes.

| Cycle | Change | Validation | Review and improvement | Next action |
| --- | --- | --- | --- | --- |
| 5 | Added Lightsail Compose deployment, Caddy configuration, private runtime-file instructions, backup/rollback boundaries and a disposable stack probe. | Linux AMD64 image built successfully. The production Caddy configuration passed `caddy validate`; public certificate issuance remains pending. `tools/lightsail_probe.py` passed against the actual Compose settings: non-root read-only app, private gateway and user auth, real analysis/reviews through Caddy, SSE and restart persistence. | The app has no host port. Caddy receives no OpenAI/gateway secrets. Test resources were isolated and removed. Public TLS, DNS, AWS availability and real OpenAI remain unverified. | Complete AWS account access and confirm the concrete bundle charge, provision the VM/static IP, point the approved hostname at it, then perform live acceptance. |

[lightsail-compose-results.json](lightsail-compose-results.json) records the checks and limits. The probe substitutes loopback HTTP for public HTTPS to avoid requesting test certificates; it does not claim to validate cloud certificate issuance. A follow-up run of `tests/test_hosted_gateway.py` passed all 20 cases after the AWS CLI installation. The initial command used a nonexistent test filename and ran no tests; the corrected path passed. Credential-pattern review of all eight changed files and `git diff --check` passed. Docker Desktop runs the AMD64 application under emulation. Earlier ARM64 measurements are not a performance guarantee for Lightsail.

## Evidence and limits

- Python: `PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -q` reports 425 passed. One existing Starlette/httpx deprecation warning remains.
- Site: `npm test` reports 11 passed; `npm run typecheck` and the Sites `build-site.mjs` helper succeed.
- Gateway: `tools/hosted_probe.py` with the separate Site `server/gateway.mjs` path produces [hosted-gateway-results.json](hosted-gateway-results.json). It exercises real HTTP and the actual proxy/Python code with held synthetic generation. It does not test cloud TLS or a real OpenAI account.
- Docker: build `release-atlas:hosted-check`, then run `tools/container_probe.py`. [hosted-container-results.json](hosted-container-results.json) records the result. The probe removes its own container and volume. This earlier probe tested Docker Desktop Linux ARM64. Cycle 5 additionally checks the AMD64 image under emulation; AWS infrastructure and heavy workloads remain untested.
- No real OpenAI calls or saved user workspace reads were performed for these checks. No browser interaction was used as evidence of local correctness. The visible hosted Site remains the prior demo until the replacement is deployed.
- The base container uses statistical retrieval. Its optional MiniLM worker is not configured. Do not label the deployment as neural retrieval without an additional verified setup.
- AWS account access and approval of the concrete Lightsail charges remain prerequisites to provisioning. The proposed current service is a Linux IPv4 virtual server with 1 GB RAM and a 40 GB disk. The earlier Render proposal is not active. Native deployment acceptance must confirm actual charges and successful startup; local configuration alone does not establish success.
