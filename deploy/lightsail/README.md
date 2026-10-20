# Release Atlas on AWS Lightsail

This deployment runs the existing Python application on one Linux virtual server. Caddy terminates HTTPS; Atlas is accessible only on the Docker network. The separate GPT Site forwards to this backend using a private gateway token, and Atlas still requires the workspace access code before reading, editing or calling OpenAI.

## Resources

The proposed Linux IPv4 bundle has 1 GB memory, two burstable vCPUs and a 40 GB SSD for a listed $7/month before taxes and overages. Use an available US West region near the owner. Confirm the selected bundle and account charges at provisioning. Do not create a load balancer, managed database, extra disk, snapshots or paid support without a separate need and approval. OpenAI API usage is separate. An instance is not a highly available service.

Attach a static IP to the instance and point the approved backend hostname's DNS A record to it. Keep the existing GPT Site and portfolio DNS unchanged. Allow inbound TCP 80/443 for HTTPS and certificate validation. Restrict SSH to the operator's IP or Lightsail browser SSH; never expose port 8765. Do not change a user's existing firewall rules on unrelated instances.

## Host and private configuration

Use a current Ubuntu LTS image and Docker Engine with Compose 2.30 or newer. Clone the canonical repository, check out the reviewed deployment commit and build on the host, or transfer a matching image built for the host architecture. Do not deploy an arbitrary moving branch without recording its commit. The included Caddy image is pinned by digest; refresh it deliberately with validation.

Store public deployment configuration in `/etc/release-atlas/site.env` with these assignments:

- `ATLAS_SITE_ORIGIN`: exact HTTPS GPT Site origin, without a path.
- `ATLAS_BACKEND_HOSTNAME`: approved backend DNS name, without scheme or path.
- `ATLAS_IMAGE_TAG`: recorded image tag for this deployment, default `local`.

Store secret assignments in root-owned `/etc/release-atlas/runtime.env`, mode 0600, inside a root-owned 0700 configuration directory. Supply `OPENAI_API_KEY`, a random URL-safe `ATLAS_GATEWAY_TOKEN` of at least 32 characters, and a separate private `ATLAS_ACCESS_CODE` of at least 32 ASCII characters. Use encrypted SSH input or a private operator secret flow. Never put these values in Git, cloud-init/user-data, shell history, build arguments or command-line arguments. The Compose runtime file uses raw parsing so characters in credentials are not expanded. Caddy receives only the public hostname, never model credentials or the gateway token.

The operator runs Compose with the public file via `--env-file /etc/release-atlas/site.env` and `-f deploy/lightsail/compose.yaml`. Use `config --quiet` for validation; unfiltered `config` output can expose resolved runtime secrets. Run `build atlas`, then `up -d` after DNS is correct. The Atlas container uses a read-only root filesystem, a non-root user, a private data volume, bounded temporary storage and no host port. Caddy owns ports 80/443 and separate persistent certificate volumes. The kernel and Docker daemon still need ordinary OS updates.

## Storage and recovery

The `atlas_data` named volume contains the SQLite workspace database on the instance's persistent SSD. It survives container replacement, application redeploy and server reboot. It does not survive deleting the underlying instance. Keep important workspace exports off the instance. Do not run Compose `down --volumes`, Docker volume pruning, or instance deletion against a live deployment. Keep the Compose project name `release-atlas` stable so updates reuse the same named volumes. Access sessions are in memory, so a backend restart requires sign-in again.

For rollback, retain the previous verified application image tag and commit. Point `ATLAS_IMAGE_TAG` to that image and recreate the Atlas container with the existing volume. Application/schema changes need separate migration review before assuming downgrade compatibility.

## Connection and acceptance

Once Caddy has a valid public certificate, configure the Site runtime with `ATLAS_BACKEND_ORIGIN` and the matching secret `ATLAS_GATEWAY_TOKEN`. The OpenAI key stays on the Python server. Confirm direct backend requests without the gateway token return 403, sign-in is still required through the Site, document analysis runs, profile/review writes work, streaming delivers context before the final answer, and a real OpenAI response succeeds. Restart the backend and check that saved work remains. Deploy the prepared Site version only after those checks pass.

The optional MiniLM interpreter/model is not in the base image. This deployment retains the statistical retrieval path and live OpenAI generation. Local Compose validation and cloud TLS/provider validation are distinct; do not claim a live service until the cloud checks succeed.

References: [Lightsail pricing](https://aws.amazon.com/lightsail/pricing/), [Caddy automatic HTTPS](https://caddyserver.com/docs/automatic-https), [Caddy reverse proxy](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).
