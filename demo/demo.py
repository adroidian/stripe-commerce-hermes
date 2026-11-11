"""Entirely offline preview/rejection showcase, with HTTP and sockets blocked.

No real credential lookup, host human impersonation, Stripe reads or writes.
Allowed write/readback behavior belongs to the transport-mocked unit suite;
real native-human bridge acceptance is a separate host integration check.
"""
import importlib.util
import json
from pathlib import Path
import sys
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stripe_commerce", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
assert spec is not None and spec.loader is not None
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
from stripe_commerce import tools, stripe_client as client

STEPS = [
    ("stripe_create_product", {"name": "Demo membership", "description": "Offline preview"}),
    ("stripe_create_price", {"product_id": "prod_Demo", "amount_cents": 1299, "currency": "usd", "interval": "month"}),
    ("stripe_create_payment_link", {"price_id": "price_Demo", "redirect_url": "https://example.com/thanks"}),
    ("stripe_deactivate_payment_link", {"id": "plink_Demo"}),
    ("stripe_deactivate_price", {"id": "price_Demo"}),
    ("stripe_archive_product", {"id": "prod_Demo"}),
]


def call(name, args):
    return json.loads(tools.handler(name)(args, session_id="offline-demo", task_id="demo"))


def main():
    print("OFFLINE ONLY: synthetic key and symbolic IDs; no objects created or remotely verified.")
    with (patch.object(client, "configured_key", return_value="rk_test_OfflineDemoOnly1234"),
          patch("urllib.request.OpenerDirector.open", side_effect=AssertionError("Demo prohibits every HTTP request")) as http,
          patch("socket.socket", side_effect=AssertionError("Demo prohibits real sockets")) as sockets):
        previews = []
        for name, args in STEPS:
            preview = call(name, {**args, "dry_run": True})
            assert preview.get("success") is True, preview
            assert preview["dry_run"] is True and preview["method"] == "POST" and "id" not in preview
            assert len(preview["preview_id"]) == 43 and preview["expires_in_seconds"] == 300
            previews.append((name, args, preview))
            print(json.dumps({"tool": name, **preview}, sort_keys=True))

        rejected = 0
        for name, args, preview in previews:
            attempts = [
                ("missing preview", {**args, "dry_run": False}),
                ("no native human UI", {**args, "preview_id": preview["preview_id"], "dry_run": False}),
                ("direct handler still lacks execution lease", {**args, "preview_id": preview["preview_id"], "dry_run": False}),
            ]
            for reason, attempt in attempts:
                result = call(name, attempt)
                assert result.get("success") is False, (reason, result)
                print(json.dumps({"tool": name, "case": reason, **result}, sort_keys=True))
                rejected += 1
        name, args = STEPS[0]
        preview = call(name, args)
        result = call(name, {**args, "name": "Changed after preview", "preview_id": preview["preview_id"], "dry_run": False})
        assert result.get("success") is False, result
        print(json.dumps({"tool": name, "case": "changed body", **result}, sort_keys=True))
        rejected += 1
        http.assert_not_called()
        sockets.assert_not_called()
        print(f"PASS: {len(previews)} exact offline previews; {rejected} rejected execution attempts; 0 HTTP calls; 0 real sockets; no real human consent simulated.")


if __name__ == "__main__":
    main()
