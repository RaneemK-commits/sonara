# Phone alerts: proposed opt-in Web Push

Status: human explicitly approved optional internet-enabled Web Push on 2026-11-13.
Backend implemented; phone subscription and real lock-screen delivery still require validation.

## Required product decision

The requested behavior is an iPhone alert while Safari is closed or the phone locked.
The existing local HTTP dashboard and WebSocket cannot provide this. Apple's Web Push
requires a compatible iOS Home Screen web app, notification permission and internet access.
Service workers and push subscription require a trusted HTTPS origin.

This is an explicit opt-in exception to the offline-at-runtime rule. All speech processing
and request state remain local. Push does not change receipt/acknowledgment semantics.

## Concrete proposed behavior

- Keep recognition, confirmation, SQLite and caregiver receipt/acknowledgment local.
- Optional, default-off Web Push sends only a generic “New Sonara request” notification.
  No phrase, bed, patient identifier, audio or recognition score appears in its payload.
- A new confirmed QUEUED request triggers push to explicitly subscribed phones. Neither
  submitting push nor a delivery response sets DISPLAYED or ACKNOWLEDGED.
- On opening the alert, the authenticated dashboard must visibly render the request
  before sending its existing receipt. A caregiver must still click Acknowledge.
- With no internet, the local dashboard still works and the existing no-receipt timeout
  remains honest. No promise of reliable/clinical paging or help coming.
- Expire pending push messages after a short interval, avoid periodic repeated alerts,
  remove revoked subscriptions, and make unsubscribe available. Recheck current request
  state on opening so resolved requests are not presented as outstanding.

## Implemented backend

Device: explicit opt-in push config, authenticated subscription storage/endpoints,
bounded delivery worker with timeouts, private local VAPID keys, and tests ensuring
push never changes request status. No secrets or subscriptions committed.
Delivery is best effort: one send attempt per request/phone, at most 120 seconds after
creation; failed sends are not automatically retried. Acknowledged/completed/cancelled
requests are skipped. The worker never sends request text or IDs to the push provider.

UI: manifest, icons, service worker, Home Screen/permission setup, subscribe/unsubscribe
controls, honest permission/network status, generic notification and local dashboard link.

Deployment: trusted HTTPS hostname reachable by the phones on the LAN, certificate
provisioning/renewal, and outbound internet for the enabled sender and phones. HTTPS
and installation details must be resolved before claiming this works on an iPhone.

## Local HTTPS demo setup

`deploy/Caddyfile` and `deploy/sonara-https.service` provide HTTPS at
`https://192.168.1.242:8443/caregiver` on the existing LAN. No public tunnel or router
port forwarding. Caddy is extracted from Debian's package into ignored `data/caddy/`;
its private CA material is in ignored `data/tls/` with user-service UMask=0077.
The HTTP dashboard remains on port 8000 for existing clients.

The phone owner must explicitly install the public certificate from
`http://192.168.1.242:8000/sonara-demo-ca.crt`, then enable full trust under
Settings → General → About → Certificate Trust Settings. This trusts a demo CA;
remove the profile after the demo. Do not install if the displayed fingerprint differs:
`FA:43:C8:ED:24:32:25:DF:78:35:B3:9E:D9:61:EC:F4:CC:60:22:C0:83:6E:E4:CC:76:89:88:30:53:8B:B2:92`.

Only then open the HTTPS caregiver page, Add to Home Screen, open that app, enter the
existing caregiver token, and explicitly enable notifications. HTTPS has separate
browser storage from HTTP, so the token may need entering again. Live notification
receipt on a locked iPhone is still an empirical test, not established by unit tests.

Board-only configuration in `data/local.toml`:
```toml
[push]
enabled = true
private_key = "data/webpush-private.pem"
subject = "https://github.com/RaneemK-commits/sonara"
```
Generate the key once with `python -m sonara.server.push --init-key data/webpush-private.pem`.
The subject is the project contact URL sent in VAPID claims, not patient information.

Privacy review: even with generic text, push subscription endpoints, public keys and
delivery timing are processed by the browser push service. A generic payload does not
make delivery fully offline or metadata-free.

Alternative: preserve strict offline runtime and provide only sound/visual alerts while
the dashboard is open. These are not lock-screen or closed-browser notifications.

Sources:
- https://developer.apple.com/documentation/usernotifications/sending-web-push-notifications-in-web-apps-and-browsers
- https://developer.mozilla.org/en-US/docs/Web/API/Notifications_API
