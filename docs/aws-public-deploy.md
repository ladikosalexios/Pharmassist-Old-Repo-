# Cheap public demo backend on AWS

Stand up the **mock** PharmAssist backend + SPA on one small EC2 box with a real
HTTPS URL, so the desktop agent (and anyone) can hit it over the normal internet
— no VPN, no Tailscale, nothing to install on the pharmacy side.

## What you get

- One EC2 instance running `compose.prod.yaml` (Caddy + backend + Postgres).
- **Automatic HTTPS** with a valid cert, **no domain purchase** — the box uses
  `https://<public-ip>.sslip.io` (sslip.io resolves the embedded IP publicly, so
  Let's Encrypt issues a real cert). Bring your own domain instead if you prefer.
- `PHARMAPI_MOCK=true` — synthetic data, **no live ΗΔΥΚΑ, no real patient data**,
  so a public box is low-risk for a demo.

## Cost

- **t3.small** (2 GB — enough headroom to build the images): roughly **$15/mo**
  on-demand, or covered by credits / the free tier's larger allowances. Stop the
  instance between demos to pay only for storage.
- Elastic IP: free while attached to a running instance.

## Steps

### 1. Prep the bootstrap
Edit the CONFIG block in [`deploy/aws/user-data.sh`](../deploy/aws/user-data.sh):
- `GH_PAT` — a GitHub fine-grained read-only token (Contents: Read) for the
  private repo.
- `PHARMAPI_USERNAME` / `PASSWORD` / `API_KEY` — the ΗΔΥΚΑ **test-env** creds
  (only used by the one-time seed; test creds are fine).
- `PILOT_DOMAIN` — leave empty for auto `<ip>.sslip.io`, or set your domain.

### 2. Launch the instance
- **AMI:** Amazon Linux 2023 · **Type:** t3.small · **Storage:** 20 GB gp3.
- **Security group:** inbound **22** (SSH, your IP only), **80** + **443**
  (0.0.0.0/0 — ACME + the agent need these public).
- **User data:** paste the edited `user-data.sh`.
- Launch, then (optional) allocate + associate an **Elastic IP** so the sslip.io
  name is stable across stop/start.

### 3. Wait ~5 minutes
cloud-init installs Docker, builds the images, boots the stack, migrates, and
seeds. Watch it: `sudo tail -f /var/log/cloud-init-output.log`.

### 4. Reach it
`https://<public-ip>.sslip.io` — the SPA loads; `…/health` returns OK; the API
(`/auth`, `/prescriptions`, …) is proxied to the backend.

### 5. Point the agent at it
```bash
PHARMASSIST_BACKEND_URL=https://<public-ip>.sslip.io \
PHARMASSIST_WEBAPP_URL=https://<public-ip>.sslip.io \
open "PharmAssist Agent.app"
```
(For a double-clicked build, bake the URL into `agent/config.json` before
packaging, or ship a `.command` launcher that sets these.)

## Hygiene

- **Rotate the demo login** — the seeded `test1234` password is in the repo.
  Change it before sharing the URL (or before a pharmacy visit).
- **User-data isn't secret** — anyone with `ec2:DescribeInstanceAttribute` can
  read the CONFIG block. Only put test-env creds + a read-only token there, on a
  throwaway box. Never production secrets.
- **It's a demo box** — not hardened, not for real patient data.

## Teardown

Terminate the instance (and release the Elastic IP). Nothing else to clean up.

## One-shot launch (optional, aws CLI)

If you'd rather script it than click the console, the equivalent
`aws ec2 run-instances` (with a security group + the user-data file) does the
same — ask and it can be provided for your default VPC/region.
