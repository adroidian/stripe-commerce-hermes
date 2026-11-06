# stripe-commerce for Hermes — 0.2.0

**Merchant catalog operations with restricted keys, exact offline previews and native Telegram/Discord one-operation human consent.** Native Hermes plugin; Python standard library only. Not an official Stripe product.

Create products, prices and Stripe-hosted payment links; inspect subscriptions and customer-portal configuration. Every mutation defaults to an **offline dry run**. Setting `dry_run:false` alone cannot write: all six mutations require an unexpired matching `preview_id` **and a fresh human answer in a native Telegram or Discord gateway UI**. CLI/TUI, QQ and every other unverified surface are read/preview-only; execution is refused before a human prompt or POST, even with a custom CLI callback. No refunds, payouts, balance access, charges, payment intents, customer payment methods, subscription cancellation or portal-session creation are exposed.

## Install and configure

Requires Hermes **>=0.21.0**, Python 3.10+ and a Stripe account. From this repository, use the normal local-plugin workflow for your Hermes build (`hermes plugins install /absolute/path/to/stripe-commerce-hermes`), then enable `stripe-commerce` if not enabled. No Python packages, Stripe SDK, hosted connector, MCP server or telemetry service are required.

**Execution compatibility is feature-detected, not guaranteed by a version number.** This release uses Hermes' internal native MCP consent helper `tools.approval_prompt.request_elicitation_consent`, not a documented stable general plugin API. The source compatibility reference is Hermes commit **`ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`**; see [VALIDATION.md](VALIDATION.md) for the distinction between contract-mocked unit tests and real-host integration acceptance. Missing/incompatible native consent or context APIs deny execution, while read tools and offline previews remain available when their credential/context APIs work. Internal host imports can produce catalog compatibility warnings; no zero-warning or cross-version guarantee is made. No Hermes core monkeypatch or new core infrastructure is installed.

Create a **restricted** key in Stripe Dashboard → Developers → API keys → restricted keys. Start in test mode. Grant Write only for Products, Prices and Payment Links; Read for Subscriptions, Customers and Checkout as needed. Account read and Billing Portal configuration read may also be required for the corresponding tools. Leave unrelated write scopes disabled. Follow the bundled `stripe-selling` skill for the permission walkthrough, approval discipline and currency details.

Set **STRIPE_API_KEY** privately for the active Hermes profile. Never paste a key in chat or commit it. The plugin uses **`agent.secret_scope.get_secret('STRIPE_API_KEY')`** when Hermes is present, including registration, readiness checks, redaction and every request. Resolver failures or incompatible Hermes credential APIs fail closed; the plugin never falls back to another profile's process key on error. Only standalone use without Hermes falls back to the process environment. No `.env`, token file or credential store is read directly by the plugin. `config_schema.stripe_api_key` is documentation only: config values are not read. Missing credentials allow offline install/doctor but hide tools via their requirement check; invalid nonempty keys make registration fail closed. Every registered tool declares `requires_env: [STRIPE_API_KEY]`.

## Tools

| Tool | Operation |
|---|---|
| `stripe_whoami` | Account ID, mode inferred from restricted-key prefix, last four characters only |
| `stripe_list_products` | Read products |
| `stripe_create_product(name, description?, dry_run?, preview_id?)` | Create product |
| `stripe_archive_product(id, dry_run?, preview_id?)` | Set product active=false |
| `stripe_list_prices(product_id?)` | Read prices |
| `stripe_create_price(product_id, amount_cents, currency, interval?, dry_run?, preview_id?)` | Create one-time or recurring price |
| `stripe_deactivate_price(id, dry_run?, preview_id?)` | Set price active=false |
| `stripe_create_payment_link(price_id, redirect_url?, dry_run?, preview_id?)` | Hosted checkout link for one unit |
| `stripe_list_payment_links(active_only?)` | Read links; false/unset includes inactive links |
| `stripe_deactivate_payment_link(id, dry_run?, preview_id?)` | Set link active=false |
| `stripe_list_subscriptions(status?)` | Read state only; Stripe's default status selection when omitted |
| `stripe_get_subscription(id)` | Read selected state fields only |
| `stripe_portal_config()` | Read whether configurations exist and cancellation is enabled per configuration |

List tools and portal configuration accept `starting_after`. Pages are capped at 25; follow `has_more` and `next_starting_after`. No hidden auto-pagination. Portal existence is about configurations returned by Stripe, not a generated portal URL or a guarantee a customer can cancel.

All handlers return redacted JSON strings, including validation, authorization and network errors. Amounts are positive integer **Stripe minor units**, despite the `amount_cents` parameter name. For USD, 1299 means $12.99; for JPY, 1299 means ¥1299. Currency must be lowercase three-letter syntax; Stripe verifies support and special currency limits. Intervals: day, week, month, year.

## Exact preview → human consent → one attempt

1. Pass this to `stripe_create_product` (or omit `dry_run`, which defaults to true):

   ```json
   {"name":"Example membership","description":"Monthly access","dry_run":true}
   ```

   The result includes an opaque random `preview_id`, exact `origin`, `method`, `path`, `would_create_or_update` form parameters, sorted URL-encoded `encoded_form`, per-preview `idempotency_key`, and `expires_in_seconds:300`. **No HTTP call is made.** There is no object ID, permission check, account lookup or remote business validation.

2. Within **300 seconds**, call **the same tool in the same native Telegram/Discord gateway context** with the original business arguments, the returned `preview_id`, and `dry_run:false`. A preview made on another platform cannot be moved into Telegram/Discord for execution; create a fresh preview there:

   ```json
   {"name":"Example membership","description":"Monthly access","preview_id":"<the actual preview_id>","dry_run":false}
   ```

   A preview identifier is a reference, **never authority**. There is no model-callable “approve tool,” `approved` flag or chat-token approval. Missing, unknown, expired, consumed or mismatched previews are rejected before any UI or HTTP. A valid token is atomically removed before prompting, so simultaneous calls cannot share it. A mismatched execution attempt also consumes that token.

3. Only the allowlisted native **Telegram/Discord gateway UI** may receive this request. It must show the full encoded request with method/origin/path, preview ID, mode and a short safe SHA-256 key reference. Consent is one operation only: `remember_key=None`, no session/permanent scope and no saved grant. The native helper's explicit `accept` result is required; denial, timeout, cancellation, malformed results, errors and unavailable APIs block the write. The host must report `_no_user_can_answer() is False`, `_is_gateway_approval_context() is True`, and a plain-string `_get_session_platform()` of exactly `telegram` or `discord`; missing/incompatible platform APIs deny writes without disabling otherwise working reads/previews. Yolo, smart policies, allowlists, cached approvals, unattended/cron/single-query sessions and attributed subagents cannot substitute for this human interaction. No CLI callback is accepted. The plugin uses the existing host gateway UI, not its own UI.

   **Native display limit (Telegram/Discord only):** the escaped ASCII message + description + title + 300 characters reserved for native UI chrome must fit **750 characters**. The full form, preview ID, mode and key reference are in the command itself, not a potentially truncated reason. This conservative cap does not establish a minimum across all Hermes surfaces: the classic CLI can collapse even a short request and QQ truncates commands at 300 characters, so both are denied regardless of request length. Oversized names, descriptions or redirect URLs can still be previewed, but execution fails closed before prompting; shorten fields and request a new preview. The plugin also checks the real native `redact_approval_display(..., force=True)` transformation before asking for consent. If any prompt field would be masked or sanitized, execution is refused. Missing or incompatible display-integrity support blocks writes; host redaction is never disabled to expose a hidden value. Native Telegram/Discord renderer acceptance remains a separate release gate; see VALIDATION. Arbitrary modified/third-party UIs are not covered.

4. After the wait, expiry, interruption, profile/session/task/**native platform** context and the complete restricted-key binding are rechecked, then checked again after TLS/opener setup immediately before constructing the POST. Switching Telegram → Discord invalidates consent even when the session key and injected IDs are unchanged. The original immutable bytes are sent with the captured expected key, not rebuilt from mutable caller arguments. The per-preview `Idempotency-Key` is `stripe-preview-` plus the random preview ID. It is not a reusable execution grant.

5. The claimed preview remains consumed after **every outcome**, including denial, UI error, network error and uncertain outcome; it cannot be replayed. There is no automatic retry. An accepted write still gets the existing strict GET readback: `verified:false` or a readback failure retains the returned object ID and warns against blind retry. Inspect Dashboard before deciding whether a new preview/action is appropriate.

Pending previews are process-local memory only, **maximum 256**, with expired entries cleaned on subsequent operations. At capacity new previews are refused until space is available; valid entries are not silently evicted. Process restart invalidates previews; reloading the preview-state module also discards them. Bindings include canonical HTTPS origin, method, path, sorted encoded form bytes, tool and original business arguments, a **full private SHA-256 fingerprint** of the restricted key, active profile home, native session key, native platform, and handler-injected `session_id`/`task_id` where available. The full fingerprint and raw key are not returned to the model. The key binds account/mode without an additional account-read permission; `stripe_whoami` remains the explicit account check.

## Security and honest limits

- Hard-coded HTTPS origin **https://api.stripe.com**, validated TLS, explicit method/path allowlist. Redirects and environment proxies are disabled, including same-origin redirects. Redirect URLs are stored as Stripe parameters, never fetched. No arbitrary HTTP tool exists.
- Key must match `rk_test_...` or `rk_live_...` with an alphanumeric suffix, at registration and on every call/request, including previews. This enforces key *type*, not scope: configure restricted permissions correctly. The plugin cannot inspect a key's full permission policy. Rotation to any other key invalidates a preview even if its last four characters match.
- No operation directly moves money, collects a payment, refunds a charge, initiates a payout or changes customer payment methods. **A payment link is commercially consequential:** if shared, a customer can complete checkout and Stripe can collect payment. Recurring prices can lead to ongoing billing when a customer subscribes. Catalog deactivation does not stop existing subscription billing.
- Stripe receives authorization, catalog parameters and request metadata over TLS and records requests in its API logs according to its retention/access policy. Do not expect anonymous actions or a separate agent identity: this plugin uses the merchant's restricted key, with user agent `stripe-commerce-hermes/0.2.0`.
- Stripe-returned names, descriptions, product IDs, subscription state and payment-link URLs enter Hermes tool output and may be retained in session logs. Preview payloads and native approval UI/hooks can also enter host logs. Customer details, metadata and payment methods are deliberately projected out. Key-shaped strings are redacted; this is not a universal PII scrubber.
- **No plugin-owned disk persistence:** no local credential/catalog/preview/grant/idempotency database, telemetry, background tasks or outbound host other than Stripe. Host session/approval logs and Stripe's logs are separate. HTTP timeout 20 seconds; response cap 1 MiB. No SDK or automatic retries. A timed-out POST may already have succeeded: inspect Dashboard before requesting a new action.
- Native plugins execute arbitrary Python with host trust, **not in a security sandbox**. These rails constrain this plugin's exposed handlers, not machine-wide malicious plugins, other agent tools, modified host UI/resolvers or Python running in the same process. Keep least privilege at Stripe itself.

## Verification and offline demo

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
./demo/run_demo.sh
```

The default demo is now **entirely offline and credential-free**. It injects a synthetic restricted key, blocks the HTTP entry point and real sockets, previews all six mutations with symbolic IDs, and checks missing-token, changed-body, unavailable-human-UI and replay rejection. It never reads a credential file or performs even a live Stripe GET. No object is remotely created or verified, and it does not pretend a simulated UI is a real human. Unit tests exercise allowed POST/readback with explicitly test-only host UI doubles and mocked HTTP. Real native-bridge integration, formatter proof, plugin/catalog validation and any merchant-approved Stripe workflow are separate acceptance steps; see [VALIDATION.md](VALIDATION.md).

## License

Apache-2.0. No Stripe code is vendored. Stripe and Hermes names identify interoperability, not endorsement.
