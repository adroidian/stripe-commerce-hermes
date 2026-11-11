# stripe-commerce for Hermes — 0.2.0

**Merchant catalog operations with restricted keys, exact offline previews and native Telegram/Discord one-operation human consent.** Native Hermes plugin; Python standard library only. Not an official Stripe product.

Create products, prices and Stripe-hosted payment links; inspect subscriptions and customer-portal configuration. Every mutation defaults to an **offline dry run**. Setting `dry_run:false` alone cannot write: all six mutations require an unexpired matching `preview_id` **and a fresh human answer in a native Telegram or Discord gateway UI**. CLI/TUI, QQ and every other unverified surface are read/preview-only; execution is refused before a human prompt or POST, even with a custom CLI callback. No refunds, payouts, balance access, charges, payment intents, customer payment methods, subscription cancellation or portal-session creation are exposed.

## Install and configure

Requires Hermes **>=0.21.0**, Python 3.10+ and a Stripe account. From this repository, use the normal local-plugin workflow for your Hermes build (`hermes plugins install /absolute/path/to/stripe-commerce-hermes`), then enable `stripe-commerce` if not enabled. No Python packages, Stripe SDK, hosted connector, MCP server or telemetry service are required.

**Writes depend on pending Hermes core work; they are not supported by the current stable release.** The public mandatory policy originated in [PR #146488](https://github.com/NousResearch/hermes-agent/pull/146488). Exact request selection, unavailable-native handling and the public API declaration were qualified through [PR #153349](https://github.com/NousResearch/hermes-agent/pull/153349), core **`826087f934aaef7ca11391101b8957f70eb8bf42`**. Installing the original feature-only `f2d5700` fixture does not qualify its callback routing for writes. Wait for the integrated host work or use the exact qualified source in an isolated development environment.

Writes feature-detect the documented `hermes_cli.plugins.VALID_TOOL_APPROVAL_POLICIES` capability, public approval observers and execution middleware. Missing or invalid support blocks execution; stable v0.23.0 remains **read/preview-only**. A capability advertisement is a host contract, not an independent attestation that a modified host implements it correctly. There is no ordinary-policy, remembered, YOLO or internal-helper fallback and no core monkeypatch. Runtime approval code uses public plugin registration and `ctx.session_surface()`, not private approval/context/interrupt/delegation/redactor imports. The existing credential resolver and public home lookup are unchanged. See [VALIDATION.md](VALIDATION.md) for exact qualification and limits.

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

3. The plugin reserves/removes the preview before returning a public `pre_tool_call` directive with `action:approve`, a unique attempt `rule_key`, `approval_policy:mandatory`, and the exact HTTP description. Only a fresh native **Once** can pass the host gate. Session/always, denial, timeout, cancellation, unavailable delivery and gate errors cannot authorize it. YOLO, approvals off/smart and remembered grants do not replace a fresh answer. Cron/single-query and delegated autoapproval paths cannot substitute for the native human channel. CLI, QQ and custom approval transports are not qualified write routes.

   **Two complete canonical display projections:** the host command is JSON containing the tool name, unique `preview_id`, `dry_run:false` and every original business argument. The compact description is exactly `MODE key-sha256=SHORT_FINGERPRINT`, newline, `POST https://api.stripe.com/PATH`, newline, `form: COMPLETE_SORTED_ENCODED_FORM`. It does not duplicate the preview ID/tool name. Both entire strings must equal the host-redacted `pre_approval_request` and `post_approval_response` observer payloads with matching native gateway/session/turn/tool-call correlation and `choice:once`. Observers only record facts; they cannot veto or grant approval. Missing observers, any masking/transformation, or a different/custom transport yields no execution lease even if the human answers Once. Raw arguments are checked independently of URL form encoding; no encoded-secret bypass is used.

   **Display limits:** escaped ASCII description ≤ **300**, escaped command ≤ **1000**, and both together + **500** reserved native chrome characters ≤ **1800**. This respects Discord's actual 300-character reason cap rather than moving the old 750-character block into it. Non-ASCII raw arguments and backtick fences are conservatively execution-ineligible; previews remain available. Long descriptions/redirects may preview but cannot execute. Short ordinary examples of all six mutations pass on the pending host. These bounds apply only to the qualified stock SDK/card paths; real client rendering and arbitrary locale/mention/adapter customization remain unverified. Never disable masking or approve a truncated tail.

4. Normal post-gate `tool_execution` middleware must observe the correlated facts and mint an opaque, dynamically scoped, one-use handler lease. A direct handler, skipped pre-hook/middleware, middleware fail-open, or post-consent argument rewrite cannot send. The handler reconstructs and compares every final business argument and origin/method/path/body/encoded byte against the immutable preview. Expiry, complete key/mode, active home, session/task and **native platform** are rechecked, including **after opener/SSL-context setup, immediately before request construction/network dispatch**. This is before the real TLS handshake in `opener.open()`, not a post-handshake guarantee. Only the frozen bytes and captured key are sent, with `Idempotency-Key: stripe-preview-PREVIEW_ID`.

   **Cancellation boundary:** native waiting/cancellation outcomes block. **After fresh Once and host admission for execution, Stop cannot guarantee abort of that approved operation.** No atomic post-gate/pre-handler Stop guarantee or private last-moment interrupt check is claimed. Lifecycle hooks retire pending/waiting state where observed; local expiry/key/scope/request guards remain in place and are not a substitute for that unavailable guarantee.

5. The claimed preview remains consumed after **every outcome**, including denial, UI error, network error and uncertain outcome; it cannot be replayed. There is no automatic retry. An accepted write still gets the existing strict GET readback: `verified:false` or a readback failure retains the returned object ID and warns against blind retry. Inspect Dashboard before deciding whether a new preview/action is appropriate.

Pending previews/attempts are process-local memory only, **maximum 256 retained entries**, with expired entries cleaned on subsequent operations. At capacity new previews are refused; valid entries are not evicted. Restart invalidates them. Bindings include canonical HTTPS origin, method, path, sorted encoded form bytes, tool/business arguments, a **full private SHA-256 key fingerprint**, mode, active public Hermes home, native platform, and handler-injected session/task IDs (None normalized to the host hook's empty string). Native session/turn/tool-call IDs correlate observers and middleware; the observer's native route key must be identical across pre/post. No invented `ctx.session_key()` API is used. The full fingerprint/raw key are not returned to the model. `stripe_whoami` remains the explicit account check.

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
# With an existing Hermes developer interpreter and disposable credential-free HOME:
python -m pytest tests --import-mode=importlib -v
python3 -m compileall -q .
hermes plugins validate . --install-deps
hermes plugins doctor . --ci
./demo/run_demo.sh
```

The default demo is **entirely offline and credential-free**: synthetic key, blocked HTTP/sockets, six symbolic previews and direct-handler refusal without execution leases. It is not an approval/replay acceptance test. Native tests use actual PluginContext/manager → model_tools dispatch → mandatory policy/queue/observers → execution middleware → actual handlers, with simulated delivery/human answers and mocked Stripe HTTP. SDK card tests are serialization evidence, not a real human or client-rendering claim. See [VALIDATION.md](VALIDATION.md).

## License

Apache-2.0. No Stripe code is vendored. Stripe and Hermes names identify interoperability, not endorsement.
