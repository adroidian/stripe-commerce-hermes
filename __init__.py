"""Offline registration, with fail-closed credential validation."""
import os
from pathlib import Path
from .stripe_client import require_key
from .tools import SCHEMAS, handler


def register(ctx):
    # Missing credentials are allowed for installation/doctor, never for tool use.
    if os.environ.get("STRIPE_API_KEY"):
        require_key()
    for name, schema in SCHEMAS.items():
        ctx.register_tool(name=name, toolset="stripe-commerce", schema=schema,
                          handler=handler(name), requires_env=["STRIPE_API_KEY"],
                          check_fn=key_ready)
    ctx.register_skill("stripe-selling", Path(__file__).parent / "skills/stripe-selling/SKILL.md",
                       description="Restricted-key Stripe setup and safe catalog selling workflows.")


def key_ready():
    try:
        require_key()
        return True
    except Exception:
        return False
