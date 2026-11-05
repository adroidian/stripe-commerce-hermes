# Validation evidence

Release candidate 0.1.0. The following outputs were captured from actual local execution, not synthesized.

## Scope and environment

- `PLUGIN_DIR` is this repository's absolute path; `HERMES_MAIN` is the supplied source-main Hermes checkout. Commands below preserve invocation structure with those two private local paths replaced by variables.
- `STRIPE_KEY_FILE` is an existing private mode-0600 restricted live credential file outside the repository. Its contents were read only into process memory and never printed. The demo also accepts an existing `STRIPE_API_KEY` environment variable.
- Account and product/configuration identifiers are redacted. Product names are replaced with Product A/B/C and product descriptions omitted by the demo before printing. Only the permitted key last four characters remain. All previews use symbolic demo IDs, never IDs for newly created objects.
- This release made **no live mutation**. The demo's transport wrapper refuses every non-GET request and asserts the complete read-path sequence. Preview verification is local structure checking, not remote object verification.

## Results

### Unit tests

```sh
python3 -m unittest discover -s tests -v
```

```text
test_accept_live_key (test_stripe.StripeTests.test_accept_live_key) ... ok
test_accept_test_key (test_stripe.StripeTests.test_accept_test_key) ... ok
test_all_mutations_default_dry (test_stripe.StripeTests.test_all_mutations_default_dry) ... ok
test_archive_readback (test_stripe.StripeTests.test_archive_readback) ... ok
test_boolean_dry_run_strict (test_stripe.StripeTests.test_boolean_dry_run_strict) ... ok
test_currency_and_interval_checks (test_stripe.StripeTests.test_currency_and_interval_checks) ... ok
test_dry_run_still_guards_key (test_stripe.StripeTests.test_dry_run_still_guards_key) ... ok
test_endpoint_allowlist (test_stripe.StripeTests.test_endpoint_allowlist) ... ok
test_guard_on_registration (test_stripe.StripeTests.test_guard_on_registration) ... ok
test_http_errors_json (test_stripe.StripeTests.test_http_errors_json) ... ok
test_invalid_amounts (test_stripe.StripeTests.test_invalid_amounts) ... ok
test_invalid_id_no_http (test_stripe.StripeTests.test_invalid_id_no_http) ... ok
test_invalid_redirects (test_stripe.StripeTests.test_invalid_redirects) ... ok
test_malformed_list_json_error (test_stripe.StripeTests.test_malformed_list_json_error) ... ok
test_malformed_response (test_stripe.StripeTests.test_malformed_response) ... ok
test_missing_key_check_and_registration (test_stripe.StripeTests.test_missing_key_check_and_registration) ... ok
test_network_failure_json (test_stripe.StripeTests.test_network_failure_json) ... ok
test_no_pii_expansion (test_stripe.StripeTests.test_no_pii_expansion) ... ok
test_no_proxy_and_verified_tls (test_stripe.StripeTests.test_no_proxy_and_verified_tls) ... ok
test_no_write_id_is_not_success (test_stripe.StripeTests.test_no_write_id_is_not_success) ... ok
test_output_redaction (test_stripe.StripeTests.test_output_redaction) ... ok
test_pagination (test_stripe.StripeTests.test_pagination) ... ok
test_portal_summary (test_stripe.StripeTests.test_portal_summary) ... ok
test_price_encoding_and_readback (test_stripe.StripeTests.test_price_encoding_and_readback) ... ok
test_readback_mismatch (test_stripe.StripeTests.test_readback_mismatch) ... ok
test_redirect_block (test_stripe.StripeTests.test_redirect_block) ... ok
test_redirect_url_not_fetched (test_stripe.StripeTests.test_redirect_url_not_fetched) ... ok
test_registration_and_manifest_surface (test_stripe.StripeTests.test_registration_and_manifest_surface) ... ok
test_reject_secret_keys (test_stripe.StripeTests.test_reject_secret_keys) ... ok
test_rotation_guard (test_stripe.StripeTests.test_rotation_guard) ... ok
test_subscription_status_validation (test_stripe.StripeTests.test_subscription_status_validation) ... ok
test_unexpected_response_origin (test_stripe.StripeTests.test_unexpected_response_origin) ... ok
test_unknown_arguments (test_stripe.StripeTests.test_unknown_arguments) ... ok
test_unknown_tool_and_bad_args (test_stripe.StripeTests.test_unknown_tool_and_bad_args) ... ok
test_write_readback_failure_preserves_id (test_stripe.StripeTests.test_write_readback_failure_preserves_id) ... ok

----------------------------------------------------------------------
Ran 35 tests in 1.243s

OK
```

Exit code: 0.

### Compile

```sh
python3 -m compileall -q .
```

```text

```

Exit code: 0.

### Catalog validator

```sh
$HERMES_MAIN/.venv/bin/hermes plugins validate $PLUGIN_DIR --install-deps
```

```text
Error in sitecustomize; set PYTHONVERBOSE for traceback:
ModuleNotFoundError: No module named 'pysqlite3._sqlite3'

✓ manifest — plugin.yaml parses
✓ manifest fields — name, version, description present
✓ requires_hermes — spec '>=0.21.0' parses
✓ config schema — shape valid
✓ requires_env — all entries UPPER_SNAKE
✓ oauth — not declared
✓ loadable — entry: __init__.py
✓ python dependencies — none declared
✓ capability probe — register() ran in isolation
✓ declared tools — matches registrations
✓ declared hooks — matches registrations
✓ declared middleware — matches registrations
✓ built-in tool collisions — no collisions
✓ security scan — safe
✓ no core override — no runtime rebinds of Hermes core
◆ Isolation — runs in the plugin host (plugins.isolation: host)

Validation passed.
```

Exit code: 0.

### Plugin doctor

```sh
$HERMES_MAIN/.venv/bin/hermes plugins doctor $PLUGIN_DIR --ci
```

```text
Error in sitecustomize; set PYTHONVERBOSE for traceback:
ModuleNotFoundError: No module named 'pysqlite3._sqlite3'
Plugin Doctor: $PLUGIN_DIR
  manifest: stripe-commerce 0.1.0 (standalone)
  OK: runtime discovery, manifest parsing, import, and registration passed
  registrations: 13 tool(s), 0 hook(s)
```

Exit code: 0.

### Read-only live demo

```sh
STRIPE_KEY_FILE=$STRIPE_KEY_FILE ./demo/run_demo.sh
```

```text
{"account_id": "acct_REDACTED", "key_last4": "MbxF", "mode": "live", "success": true, "tool": "stripe_whoami"}
{"data": [{"active": true, "id": "prod_REDACTED_1", "livemode": true, "name": "Product A"}, {"active": true, "id": "prod_REDACTED_2", "livemode": true, "name": "Product B"}, {"active": true, "id": "prod_REDACTED_3", "livemode": true, "name": "Product C"}], "has_more": false, "next_starting_after": null, "success": true, "tool": "stripe_list_products"}
{"data": [{"active": true, "cancellation_enabled": true, "id": "bpc_REDACTED", "livemode": true, "name": null, "object": "billing_portal.configuration"}], "exists": true, "has_more": false, "next_starting_after": null, "success": true, "tool": "stripe_portal_config"}
OFFLINE PREVIEW CYCLE: symbolic IDs only; no remote objects created or verified.
{"dry_run": true, "method": "POST", "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified.", "path": "/v1/products", "success": true, "tool": "stripe_create_product", "would_create_or_update": {"description": "Offline preview", "name": "Demo membership"}}
{"dry_run": true, "method": "POST", "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified.", "path": "/v1/prices", "success": true, "tool": "stripe_create_price", "would_create_or_update": {"currency": "usd", "product": "prod_Demo", "recurring[interval]": "month", "unit_amount": 1299}}
{"dry_run": true, "method": "POST", "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified.", "path": "/v1/payment_links", "success": true, "tool": "stripe_create_payment_link", "would_create_or_update": {"after_completion[redirect][url]": "https://example.com/thanks", "after_completion[type]": "redirect", "line_items[0][price]": "price_Demo", "line_items[0][quantity]": 1}}
{"dry_run": true, "method": "POST", "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified.", "path": "/v1/payment_links/plink_Demo", "success": true, "tool": "stripe_deactivate_payment_link", "would_create_or_update": {"active": "false"}}
{"dry_run": true, "method": "POST", "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified.", "path": "/v1/prices/price_Demo", "success": true, "tool": "stripe_deactivate_price", "would_create_or_update": {"active": "false"}}
{"dry_run": true, "method": "POST", "note": "No API call made. No object exists from this preview; IDs, permissions, currency support and business validity are not remotely verified.", "path": "/v1/products/prod_Demo", "success": true, "tool": "stripe_archive_product", "would_create_or_update": {"active": "false"}}
PASS: 3 read-only calls; 6 offline mutation previews verified; 0 live writes.
```

Exit code: 0.

### Build provenance

```sh
date -u +%FT%TZ; git -C $HERMES_MAIN rev-parse HEAD
```

```text
2026-11-05T07:19:57Z
ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df
```

Exit code: 0.

## Warnings, corrections, and limits

- The source-main Hermes Python environment emits `Error in sitecustomize` / `ModuleNotFoundError: No module named 'pysqlite3._sqlite3'` at startup. Both real commands nevertheless complete with exit 0; catalog validation passes and doctor reports runtime discovery/import/registration passed with 13 tools and 0 hooks. This pre-existing host warning was not suppressed or “fixed” by modifying the environment. There are no plugin-validator warnings; host-trust isolation is informational.
- `capabilities: []` is intentional: the plugin registers tools and a skill but no privileged host capability such as LLM access, middleware, core overrides, hooks or providers. `provides_tools` and runtime registrations match. API access is ordinary stdlib HTTPS with `requires_env` declared both at manifest and tool registration.
- The initial test helper had a Python argument-name collision with product `name`; it was fixed before the final passing run. The first doctor probe ran before the bundled skill had been written and reported it missing; the completed artifact passes `doctor --ci` (which, unlike plain doctor, fails the process on registration errors).
- All mutation behavior, including form encoding, returned ID, GET readback, mismatches, and accepted-write/readback-failure handling, is **transport-mocked**, not proven against a real Stripe write. Default and explicit dry runs make no HTTP calls. The live key was used only for whoami, products, and portal configurations.
- No real test-mode credentials were provided. No live or test-mode product/price/link was created, archived or deactivated. No customer checkout, billing, subscription cancellation or payment was executed. Live prices, payment links and subscription reads were not exercised; their permissions and API response compatibility still need a merchant-approved test-mode run.
- No external review, CI on a public repository, catalog admission, GitHub push or video submission has been performed. A separate adversarial review and approved test-mode mutation video are appropriate before publication. This repository is prepared for the parent to publish and pin its commit, not already catalog-listed.
