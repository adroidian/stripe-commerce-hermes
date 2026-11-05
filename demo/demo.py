"""Read-only live showcase plus honest offline mutation previews."""
import importlib.util
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("stripe_commerce", ROOT / "__init__.py", submodule_search_locations=[str(ROOT)])
assert spec is not None and spec.loader is not None
plugin = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = plugin
spec.loader.exec_module(plugin)
from stripe_commerce import tools, stripe_client as client


def main():
    if not os.environ.get("STRIPE_API_KEY") and os.environ.get("STRIPE_KEY_FILE"):
        os.environ["STRIPE_API_KEY"] = Path(os.environ["STRIPE_KEY_FILE"]).read_text().strip()
    original = client.request
    reads = []
    def get_only(method, path, params=None):
        if method != "GET":
            raise client.StripeError("Demo hard stop: live mutations prohibited.")
        reads.append(path)
        return original(method, path, params)
    client.request = get_only
    def call(tool_name, args):
        result = json.loads(tools.handler(tool_name)(args))
        if not result.get("success"):
            print(json.dumps({"tool": tool_name, **result}))
            raise SystemExit(1)
        return result
    def display(tool_name, args):
        result = call(tool_name, args)
        if tool_name == "stripe_whoami":
            result["account_id"] = "acct_REDACTED"
        if tool_name == "stripe_list_products":
            result["data"] = [{"id": "prod_REDACTED_" + str(i + 1), "name": "Product " + chr(65 + i),
                               "active": row.get("active"), "livemode": row.get("livemode")}
                              for i, row in enumerate(result["data"])]
            if result.get("next_starting_after"):
                result["next_starting_after"] = "prod_REDACTED"
        if tool_name == "stripe_portal_config":
            for row in result["data"]:
                row["id"] = "bpc_REDACTED"
                row.pop("created", None)
            if result.get("next_starting_after"):
                result["next_starting_after"] = "bpc_REDACTED"
        print(json.dumps({"tool": tool_name, **result}, sort_keys=True))
    for name in ("stripe_whoami", "stripe_list_products", "stripe_portal_config"):
        display(name, {})
    print("OFFLINE PREVIEW CYCLE: symbolic IDs only; no remote objects created or verified.")
    steps = [
        ("stripe_create_product", {"name": "Demo membership", "description": "Offline preview"}),
        ("stripe_create_price", {"product_id": "prod_Demo", "amount_cents": 1299, "currency": "usd", "interval": "month"}),
        ("stripe_create_payment_link", {"price_id": "price_Demo", "redirect_url": "https://example.com/thanks"}),
        ("stripe_deactivate_payment_link", {"id": "plink_Demo"}),
        ("stripe_deactivate_price", {"id": "price_Demo"}),
        ("stripe_archive_product", {"id": "prod_Demo"}),
    ]
    for name, args in steps:
        result = call(name, {**args, "dry_run": True})
        if result.get("dry_run") is not True or result.get("method") != "POST" or "id" in result:
            raise SystemExit("Invalid preview structure")
        print(json.dumps({"tool": name, **result}, sort_keys=True))
    if reads != ["/v1/account", "/v1/products", "/v1/billing_portal/configurations"]:
        raise SystemExit("Unexpected demo network calls")
    print("PASS: 3 read-only calls; 6 offline mutation previews verified; 0 live writes.")

if __name__ == "__main__":
    main()
