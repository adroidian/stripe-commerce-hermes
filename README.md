# stripe-commerce for Hermes

**Merchant catalog operations with an enforced restricted-key boundary.** Native Hermes plugin; Python standard library only. Not an official Stripe product.

Create products, prices and Stripe-hosted payment links; inspect subscriptions and customer-portal configuration. Every mutation defaults to an **offline dry run**, and unrestricted `sk_` keys are rejected at plugin registration and on every call. No refunds, payouts, balance access, charges, payment intents, customer payment methods, subscription cancellation or portal-session creation are exposed.

## Install and configure

Requires Hermes **>=0.21.0**, Python 3.10+ and a Stripe account. From this repository, use the normal local-plugin workflow for your Hermes build (`hermes plugins install /absolute/path/to/stripe-commerce-hermes`), then enable `stripe-commerce` if not enabled. For source validation use the commands below. No Python packages, Stripe SDK, hosted connector, MCP server or telemetry service are required.

Create a **restricted** key in Stripe Dashboard → Developers → API keys → restricted keys. Start in test mode. Grant Write only for Products, Prices and Payment Links; Read for Subscriptions, Customers and Checkout as needed. Account read and Billing Portal configuration read may also be required for the corresponding tools. Leave unrelated write scopes disabled. Follow the bundled `stripe-selling` skill for the permission walkthrough, approval discipline and currency details.

Set **STRIPE_API_KEY** privately in the Hermes process environment or active profile `.env`. Never paste a key in chat or commit it. `config_schema.stripe_api_key` is documentation only: no config-file key is read. Missing credentials allow offline install/doctor but hide tools via their requirement check; an invalid nonempty key makes registration fail closed. Each registered tool declares `requires_env: [STRIPE_API_KEY]`. Rotating to an unrestricted key cannot bypass the runtime check.

## Tools

| Tool | Operation |
|---|---|
| `stripe_whoami` | Account ID, mode inferred from restricted-key prefix, last four characters only |
| `stripe_list_products` | Read products |
| `stripe_create_product(name, description?, dry_run?)` | Create product |
| `stripe_archive_product(id, dry_run?)` | Set product active=false |
| `stripe_list_prices(product_id?)` | Read prices |
| `stripe_create_price(product_id, amount_cents, currency, interval?, dry_run?)` | Create one-time or recurring price |
| `stripe_deactivate_price(id, dry_run?)` | Set price active=false |
| `stripe_create_payment_link(price_id, redirect_url?, dry_run?)` | Hosted checkout link for one unit |
| `stripe_list_payment_links(active_only?)` | Read links; false/unset includes inactive links |
| `stripe_deactivate_payment_link(id, dry_run?)` | Set link active=false |
| `stripe_list_subscriptions(status?)` | Read state only; Stripe's default status selection when omitted |
| `stripe_get_subscription(id)` | Read selected state fields only |
| `stripe_portal_config()` | Read whether configurations exist and cancellation is enabled per configuration |

List tools and portal configuration accept `starting_after`. Pages are capped at 25; follow `has_more` and `next_starting_after`. No hidden auto-pagination. Portal existence is about configurations returned by Stripe, not a generated portal URL or a guarantee a customer can cancel.

All handlers return JSON strings, including validation, authorization and network errors. Amounts are positive integer **Stripe minor units**, despite the `amount_cents` parameter name. For USD, 1299 means $12.99; for JPY, 1299 means ¥1299. Currency must be lowercase three-letter syntax; Stripe verifies support and special currency limits. Intervals: day, week, month, year.

### Preview example

```json
{"name":"Example membership","description":"Monthly access","dry_run":true}
```

Pass this to `stripe_create_product`. Its JSON preview contains the exact POST path and form parameters and makes **no HTTP call**. It does not fabricate an object ID. For execution, obtain merchant approval, explicitly pass `dry_run:false`, and use real IDs from each preceding create result. All six mutation tools support preview, including deactivation. Execution returns an `id` and a `verified` readback flag. A readback failure retains the created/updated ID and warns against retrying.

## Security and honest limits

- Hard-coded HTTPS origin **https://api.stripe.com**, validated TLS, explicit method/path allowlist. Redirects and environment proxies are disabled, including same-origin redirects. Redirect URLs are stored as Stripe parameters, never fetched. No arbitrary HTTP tool exists.
- Key must match `rk_test_...` or `rk_live_...` with an alphanumeric suffix. This enforces key *type*, not scope: configure the restricted permissions correctly. The plugin cannot inspect the full permission policy of a key.
- No operation can directly move money, collect a payment, refund a charge, initiate a payout or change customer payment methods. **A payment link is commercially consequential:** if shared, a customer can complete checkout and Stripe can collect payment. Recurring prices can lead to ongoing billing when a customer subscribes. Catalog deactivation does not stop existing subscription billing.
- Stripe receives authorization, catalog parameters and request metadata over TLS and records requests in its API logs; Dashboard request/activity logs can show endpoint, timestamp, object identifiers, parameters, response/error and key attribution according to Stripe's retention/access policy. Do not expect anonymous actions or a separate agent identity: this plugin uses the merchant's restricted key, with user agent `stripe-commerce-hermes/0.1.0`.
- Stripe-returned names, descriptions, product IDs, subscription state and payment-link URLs enter Hermes tool output and may be retained in session logs. Customer details, metadata and payment methods are deliberately projected out. Strings resembling Stripe secret keys are redacted; this is not a universal PII scrubber.
- No plugin telemetry, background tasks, local credential persistence or outbound host other than Stripe. HTTP timeout 20 seconds; response cap 1 MiB. No SDK, automatic retries or persisted idempotency keys. A timed-out POST may already have succeeded: inspect Dashboard before retrying. Readback adds a GET after an accepted write.
- `dry_run` validates local types, ranges, identifier shapes and URL syntax only; it does not contact Stripe to check object existence, account permissions or business validity. Tool approval is a merchant/Hermes responsibility; there is no plugin-owned confirmation UI. Defaults protect accidental execution, not a caller deliberately setting false.
- Native plugins execute with host trust, not in a security sandbox. These rails constrain this plugin's exposed operations; other agent tools or Python running in the same process could use an overprivileged key. Keep least privilege at Stripe itself.

## Verification and demo

```bash
python3 -m unittest discover -s tests -v
python3 -m compileall -q .
hermes plugins validate . --install-deps
hermes plugins doctor .
./demo/run_demo.sh
```

Demo reads `STRIPE_API_KEY` or, if absent, a file specified by `STRIPE_KEY_FILE`. It performs only `whoami`, one product-list page and portal-configuration reads against Stripe, with product names and account identifiers redacted for sharing. It then previews a complete product → price → payment-link → deactivate/archive workflow with symbolic demo IDs and verifies preview structure locally. **That is not a real create/verify/archive cycle**: no demo object is created or remotely verified. The demo rejects all non-GET transport calls even if preview logic regresses. It exits nonzero if any read/preview fails. Live writes require separate explicit approval and were not exercised for this release; see [VALIDATION.md](VALIDATION.md).

## License

Apache-2.0. No Stripe code is vendored. Stripe and Hermes names identify interoperability, not endorsement.
