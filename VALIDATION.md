# Validation evidence

## 0.2.0 — exact preview + one-operation human consent

This section supersedes earlier safety/default-demo statements. Older sections
below are historical evidence. All current authorization/host acceptance uses
synthetic credentials, simulated human decisions and mocked Stripe HTTP; it
makes no claim of a new live Stripe request or real merchant approval.

### R2 / Q1–Q2 — current native Telegram/Discord-only write boundary

This section supersedes the CLI/generic-gateway execution and display-budget
claims in the historical receipts below. The independent v2 quality review
found two real shipped-UI counterexamples, despite the earlier **92 passing
unit tests / 11 native integration checks**:

- **Q1:** the real classic CLI panel can collapse even `name=Tea`, displaying
  only three wrapped command rows plus an optional View choice. Allow once
  remains available without viewing the form or endpoint
  (`hermes_cli/cli_tui_mixin.py:148–230` in the reference host).
- **Q2:** the shipped QQ card uses `command_preview[:300]`
  (`plugins/platforms/qqbot/keyboards.py:139`). A valid product name ending in
  `HIDDEN_TAIL` could pass the plugin's 750-character preflight but be hidden
  on that card. The previous claim of an 800-character minimum across shipped
  gateway renderers was false; a generic formatter test did not cover QQ.

The bounded correction does not alter Hermes core or add UI machinery. All six
writes now require the host's native platform signal to be a plain string of
exactly `telegram` or `discord`, `_no_user_can_answer() is False`,
`_is_gateway_approval_context() is True`, and no attributed subagent. No CLI
callback is imported or accepted, including custom full-prompt test callbacks.
CLI/TUI, QQ and every other unverified surface fail before native consent or
HTTP, while reads and offline previews remain available when their baseline
credential/context APIs work. Missing, throwing or incompatible platform APIs
also deny writes without disabling those reads/previews.

Native platform is part of the immutable preview context. A platform switch,
including Telegram → Discord with unchanged session key/injected IDs, invalidates
the reference before the prompt; a switch during consent or after TLS/opener
setup invalidates it before HTTP. Claimed references remain single-use. The R1
forced native redactor-equality preflight, 750-character scoped display cap,
full key/profile/session/task/request binding, 300-second TTL, 256-entry cap,
atomic claim, captured-byte transport, idempotency and strict readback remain.
The display cap applies only to the allowlisted renderers, not a universal UI
minimum or an attestation of arbitrary third-party/modified UI behavior.

Actual offline execution for this correction, Python 3.11.15:

- Pre-correction source: **92 tests, OK**.
- Initial nine R2 regression methods against v2: **9 tests, FAILED
  (failures=94)**, exit 1; subtest failures are counted individually. No import
  errors. Unsupported writes reached mocked POST/GET and platform switches were
  not bound. The pre-claim matrix was subsequently extended to unsupported →
  supported switches as well.
- Focused `python3 -m unittest discover -s tests -p test_preview_binding.py -v`:
  **50 tests, OK**. The nine new methods cover all six CLI/TUI and QQ/unverified
  refusals before UI/HTTP; all-six exact POST/readback paths on both Telegram and
  Discord; platform changes before/during UI and after TLS; missing/incompatible
  platform APIs; and ambiguous non-boolean human/gateway signals.
- Full `python3 -m unittest discover -s tests -v`: **101 tests, OK**. Existing
  write/readback tests now explicitly receive a fresh test-only gateway UI
  response. Earlier CLI-positive binding fixtures were moved to the supported
  gateway path; strict transport/readback assertions were retained.
- `./demo/run_demo.sh`, exit 0:
  `PASS: 6 exact offline previews; 19 rejected execution attempts; 0 HTTP calls; 0 real sockets; no real human consent simulated.`
- `python3 -m compileall -q .` and `git diff --check`: exit 0.

Controller acceptance reran **101 tests on Python 3.11.15 and 101 on the
reference Hermes Python 3.14 runtime**, plus compile, the zero-HTTP demo,
post-TLS expiry refusal, plugin validation and diff checks. Validation passes
with the disclosed internal-API compatibility warning, not a warning-free result.

The controller also exercised **11 native integration scenarios**: Telegram and
Discord each used the real native queue/resolver/redactor and the actual final
adapter send methods, with simulated delivery/human decisions and mocked Stripe
HTTP. Complete request blocks survived both final cards; only once/deny controls
were offered. CLI, QQ and unverified channels refused before UI/HTTP. The checks
also covered platform/key/profile changes, redaction, denial/replay, immutable
caller inputs and cron refusal under YOLO. Real socket attempts remained zero.

A separate native serialization run passed **8 positive and 3 negative cases**,
including maximal permitted escaped-display cost, encoded tails, HTML escaping,
Discord mentions and deliberate overflow/fence failures. It ran the pinned
reference host's real Telegram/Discord formatting, card/view construction and
send shells with the already-installed Telegram 22.8 / Discord 2.7.1 SDKs.
Only outbound delivery/channel lookup/settle observation were simulated. No
package was installed, no human actually approved, and no client rendering or
live merchant acceptance is claimed. A generic formatter or unit UI double is
not a substitute for these final-card checks.

Source freeze and independent spec/quality gates are release requirements;
catalog admission remains the maintainer's decision. No live Stripe request,
real merchant approval, installation or core change was performed. Raw local
RED, focused, full-suite, native-card and demo receipts remain outside the source
repository. The historical receipts below are retained with their limitations.

### Historical R1 display-integrity review fix and acceptance

An independent specification review of the initial candidate found that the
native host redactor could hide a non-Stripe token-shaped form value while the
plugin posted the original bytes. The old Stripe-only preflight redactor did
not prove that a human saw the entire request. This was independently reproduced
through the genuine CLI helper and the gateway's exact redaction wrapper:
four synthetic cases returned success with mocked POST/GET, while the full form
was absent from the displayed command. No real credentials or traffic were used.

The plugin now calls the real native
`agent.redact.redact_approval_display(..., force=True)` for command, description
and title before seeking consent. Any masking/sanitization, missing API,
incompatible result or error fails closed; the reference remains consumed.
Host redaction is not disabled and hidden values are not revealed.

- Before the correction: the expanded **41-test** binding regression file failed
  with **8 failures**; four real-native redaction cases also failed the no-POST
  assertion, reaching mocked HTTP despite hidden values.
- After the correction: **92 unit tests pass** on both Python 3.11.15 and the
  Hermes checkout's Python 3.14 runtime, including **41 binding regressions**.
- **11 native integration checks pass**, including real CLI redaction and the
  unchanged gateway redaction function plus actual formatter. All four synthetic
  masked-value cases now have success false, zero consent callbacks and zero HTTP.
  Ordinary exact-visible CLI/gateway requests still complete strict mocked readback.
- Offline demo still reports **6 previews, 19 rejections, HTTP 0 and sockets 0**.
  The slow-TLS expiry probe, `compileall` and `git diff --check` pass.
- Plugin validation passes all checks, safe scan and no core overrides, with
  **one internal-API compatibility warning**, as described below. The display
  primitive is also feature-detected internal coupling, not a stable public seam.

The initial candidate's receipts below are retained as historical evidence.
R1's results superseded their test and host-integration totals at that time;
R2 above is the current scope and does not treat CLI acceptance as valid consent.

### Local execution and RED → GREEN

- Unmodified implementation baseline:
  `14fd9b75c113e5f7cf9849c0da9e05329ce39869`.
  `python3 -m unittest discover -s tests -v`: **51 tests, OK**, exit 0.
- The new regression file was first run before implementing preview enforcement:
  **29 tests, FAILED (failures=22, errors=2)**, exit 1. Missing-preview writes
  reached mocked HTTP, and previews had no bound identifier.
- After the native-consent/profile/display-limit requirements were incorporated,
  the final regression file and its test-only UI fixture were copied into an
  isolated `git archive` of the same baseline. The production implementation
  in that temporary directory was unchanged. Command:
  `python3 -m unittest discover -s tests -p test_preview_binding.py -v`.
  Actual result: **38 tests, FAILED (failures=25, errors=2)**, exit 1. Failures
  include missing-token writes, missing bounded preview state, missing human
  prompts, replay/race controls, oversized UI requests and profile-scoped keys.
  Feature-field errors are part of the missing baseline behavior, not import
  failures. Temporary baseline files were removed after execution.
- Hardened worktree:
  `python3 -m unittest discover -s tests -v`: **89 tests in 2.361s, OK**, exit 0.
  These are the original 51 test methods plus 38 hardening regressions. Original
  write/readback fixtures now explicitly preview and install a **test-only**
  host-human UI response; readback and transport assertions were not weakened.
- `git diff --check`: exit 0, no output.
- `python3 -m compileall -q .`: exit 0, no output.
- `./demo/run_demo.sh`: exit 0. Actual final line:
  `PASS: 6 exact offline previews; 19 rejected execution attempts; 0 HTTP calls; 0 real sockets; no real human consent simulated.`

Raw RED/GREEN/demo logs are retained privately outside this source repository.
All tests are credential-free: only synthetic keys, an HTTP-entry-point mock
and a real-socket hard stop. No secret files or real scoped secrets were read;
no real Stripe GET or POST occurred.

### What the new tests prove

Real registered/exposed handlers and the actual transport/approval binding are
invoked; the plugin's authorization function is not replaced with an automatic
approval mock. A separate test-only host contract fixture supplies UI responses.
Tests cover all six mutations with missing previews and missing human UI;
all-six exact POST bytes, URL and headers followed by strict readback; changed
fields/IDs/tool/key/mode/profile/session/task/native routing; expiry before and
during CLI/gateway approval; 256-entry capacity and expiry cleanup; restart;
consume on deny/UI error/network uncertainty/success; atomic concurrent claim;
unattended/delegation/automatic-callback refusal under yolo; missing/incompatible
host APIs; malformed native-helper results; mutable caller arguments during
prompt; key rotation after approval; expiry/profile/interrupt changes during
opener setup; native display overflow; secret-shaped text refusal/redaction.

### Historical native host coupling and acceptance

The source compatibility reference is Hermes
`ed1afb082eb3e46cf2edae9d8f68fb67b09ee4df`. Its exact native consent implementation
(`tools/approval_prompt.py`, `request_elicitation_consent`) was inspected along
with the protected-instruction-file one-operation guard and the relevant
context/credential/delegation/interrupt primitives. The plugin requests
`remember_key=None` and only accepts the helper's exact `accept` result. The
helper offers once/deny and does not persist consent; legacy broad UI responses,
if any, are interpreted by the host as this call only. Generic policy approval,
yolo, smart mode, allowlists and cached decisions are never consulted.

These are **internal feature-detected APIs**, not a stable documented general
plugin approval API. Missing/incompatible APIs fail closed for writes. Read
and preview availability still depends on working profile credential/context
APIs. No core monkeypatch or infrastructure change was made. Internal imports
may generate catalog compatibility warnings; this release does not claim
zero warnings or compatibility with every build satisfying the version floor.

The earlier candidate limited escaped ASCII approval message + description +
title + 300 reserved native UI characters to 750, putting complete
form/mode/key reference and preview ID in the command. Its generic formatter
probe used an 800-character command budget. **That was not a shipped-renderer
minimum:** Q1/Q2 above disproved the universal display claim. These receipts
are historical, not current CLI or QQ authorization evidence.
**Initial candidate controller acceptance (before the display-integrity fix):** isolated controller runs passed
89 unit tests on Python 3.11.15 and on the Hermes checkout's Python 3.14 runtime,
`compileall`, `git diff --check`, and the offline demo quoted above. Nine extra
integration checks exercised the real native CLI callback and gateway queue /
resolver with simulated human decisions and mocked Stripe HTTP, plus the real
host formatter at its minimum 800-character command budget. They verified
complete request rendering, YOLO non-bypass, single use, denial, key rotation,
immutable caller arguments, active profile-scoped credentials and cron refusal.
An additional slow-TLS probe expired the preview during opener setup and saw
zero HTTP calls. These are simulated decisions, not a real merchant approval
or a live Stripe API compatibility test.

`hermes plugins validate <plugin-dir> --install-deps --json` passed every check,
including isolated registration, matching capabilities, security scan (`safe`)
and no core overrides. It emitted **one compatibility warning**, listing the
internal approval/context/delegation/interrupt imports above. This is an explicit
catalog review item: Hermes does not currently provide a documented public
plugin seam for this strict one-operation consent flow. Feature detection and
fail-closed writes bound runtime failure; they do not make internal APIs stable.
No zero-warning result or universal version-floor compatibility is claimed.

Plugin source remains uninstalled in any live profile. No real Stripe request,
real credential lookup or billing change was made for this release. Catalog
schema validation, independent source review and final pinned-SHA readback are
separate release gates.

## Adversarial remediation — SC-01, SC-02, SC-03

The original evidence below is retained as historical baseline. This section
supersedes its test count and its statement that no adversarial review occurred.
Starting point: `main` at `f4d28d8`, clean working tree, 35 tests passing.

### Attack reproduction and fixes

- **SC-01:** Mocked Stripe readback changed monthly recurrence to yearly; changed
  link price, quantity, completion type, redirect URL or active state; omitted
  evidence; returned incomplete or extra line items. Previously these could
  report `verified:true`. Readback now strictly compares requested price fields
  (including recurrence, or explicit one-time state), link price/quantity,
  completion behavior/URL and active state. Link readback requests
  `expand[]=line_items` on the existing allowlisted GET endpoint; it does not add
  an endpoint or fetch any redirect URL. Missing/incomplete evidence returns
  `verified:false` and `unverifiable_fields`; observed differences return
  `mismatched_fields`. Failed readback retains the accepted object ID and lists
  unverifiable fields. Product descriptions are also checked when requested.
  The original price happy-path fixture now supplies the recurrence it claims
  to verify; its assertion was not removed or weakened.
- **SC-02:** Mocked pages used non-boolean/missing `has_more`, 26 rows, empty pages
  with more results, missing/wrong-prefix cursor IDs, duplicate rows or a request
  cursor reappearing anywhere in the page. All now produce clear JSON pagination
  errors. Valid empty terminal pages and 25-row pages still work. The shared
  checks cover all five list tools. Stripe IDs are opaque, so lexical ordering
  is deliberately not treated as chronology; the plugin rejects observable
  repeated/regressing pages, but does not claim to detect arbitrary cycles
  spanning independent stateless calls without supplied cursor history.
- **SC-03:** Mocked HTTP errors proved lost currency/reference/permission codes
  and lost 429 retry timing. Errors now retain only optional `error_details`
  fields `type`, `code`, `param`, `retry_after_seconds`. String fields must be
  1–128 ASCII token/bracket characters, pass existing key redaction unchanged,
  and are dropped rather than truncated if unsafe or oversized. Retry timing
  must be an integer header string of at most 64 characters and is clamped to
  0–3600 seconds. Body reads remain capped at 1 MiB; malformed or oversized
  bodies fall back to generic errors. Messages, bodies, URLs, arbitrary headers,
  non-string values and credential-shaped values are not echoed. No retry is
  performed, including on 429.

The final 16 regression methods were exercised against the original committed
implementation in a temporary directory: process exit **1**, `Ran 16 tests`,
`FAILED (failures=30, errors=3)` (subtest failures are counted separately).
The errors were missing diagnostic/unverifiable fields, not import failures.
The same regressions pass against the fix. Baseline reproduction logs remained
outside the repository; they contain synthetic fixtures only.

### Final acceptance results

```text
python3 -m unittest discover -s tests -q
Ran 51 tests in 3.326s
OK
```

This includes the original 35 tests and 16 new adversarial regression methods.

- `python3 -m compileall -q .`: exit 0, no output.
- `git diff --check`: exit 0, no output.
- `$HERMES_MAIN/.venv/bin/hermes plugins validate . --install-deps`: exit 0,
  `Validation passed.` All manifest, registration, collision and security checks
  passed; no new warnings. The same pre-existing host `sitecustomize` /
  `pysqlite3._sqlite3` warning remains; host isolation remains informational.
- `STRIPE_KEY_FILE=$STRIPE_KEY_FILE bash demo/run_demo.sh`: exit 0,
  `PASS: 3 read-only calls; 6 offline mutation previews verified; 0 live writes.`
  The first invocation without either credential environment variable correctly
  failed closed (exit 1); rerun used the existing private restricted-key file,
  with no credential printed or copied into the repository.
- The initial commit attempt found no configured Git author identity. The final
  commit uses the existing baseline contributor identity via command-scoped Git
  options; no global or repository identity configuration was changed.

Safety rails are unchanged: restricted `rk_` keys only on every request,
`api.stripe.com` only, verified TLS, redirects/proxies disabled, no automatic
retry, dry-run defaults, and no money endpoints. No live mutation was executed.
Commercial write/readback compatibility and error variants remain
transport-mocked, not a claim of test-mode or live-write validation. The demo
performed only account, product-list and portal-configuration GETs. No push,
publication or catalog submission was made.

## Historical initial validation

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
