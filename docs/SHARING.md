# HTTPS sharing with Tailscale

FlowPilot keeps its normal console at `http://127.0.0.1:8766/`.
An optional public demo gateway on `127.0.0.1:8767` lets Tailscale
Funnel expose the same running application under `/flowpilot/`. The HTTPS
address works over the internet and on devices connected to the tailnet.
The Mac, FlowPilot and Tailscale must remain running.

The demo opens directly without a login, including starting investigations.
The gateway forwards requests to the existing local server;
it does not start another investigation engine or open another database.
Local access keeps its existing behaviour. All consequential actions still
require the application's simulated human approvals.

## Local configuration

Keep the machine-specific address outside Git in `.runtime/share.json`, with file permissions 0600:

```json
{
  "url": "https://YOUR-MAC.YOUR-TAILNET.ts.net:8443/flowpilot/"
}
```

Remote access uses HTTPS and does not require credentials.

Start the main application normally, then run:

```sh
.venv/bin/python -m flowpilot.share --config .runtime/share.json --port 8767
tailscale funnel --bg --https=8443 --set-path=/flowpilot http://127.0.0.1:8767
```

The first command stays in the foreground; run the Tailscale command in a
second terminal, or supervise the gateway with a per-user LaunchAgent.
Always inspect `tailscale funnel status` before choosing a port. Ports 443,
8443 and 10000 support Funnel. Adding a path on an already-public port preserves
its other handlers; do not enable Funnel on a private Serve port that hosts
other applications unless you intend to expose those applications too.

On the owner's Mac, `com.davrob.flowpilot-share` supervises the gateway and the
local `.runtime/share-access.txt` contains its URL. The main
`com.davrob.flowpilot` service continues to supervise the local console.
Restart only the sharing service after changing its configuration:

```sh
launchctl kickstart -k gui/$(id -u)/com.davrob.flowpilot-share
```

## Disable this share

Remove only FlowPilot's handler, preserving other applications on the port:

```sh
tailscale funnel --https=8443 --set-path=/flowpilot off
```

Local access continues working. Avoid `tailscale funnel reset` or disabling the
whole port when other applications share it.

## Checks

```sh
.venv/bin/python -m pytest tests/test_share.py -q
npm --prefix frontend test
```

The gateway rejects unexpected hosts, cross-site writes and
oversized request bodies. Credentials, cookies and forwarded identity headers
are not sent to the investigation server. Gateway access logs are disabled;
responses use `Cache-Control: no-store`. Assets and API calls resolve relative
to the app's URL prefix, so existing local and shared links use the same build.
