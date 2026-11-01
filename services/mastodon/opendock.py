"""Mastodon-specific generated credential bundles."""

from opendock_capabilities import (
    SecretGenerationContext,
    SecretPlan,
    SecretPlanningContext,
    ValidationContext,
    ValidationResult,
)


OPENDOCK_CAPABILITY_API_VERSION = 1

MASTODON_RAILS_KEYS = {
    "MASTODON_SECRET_KEY_BASE",
    "MASTODON_OTP_SECRET",
}
MASTODON_VAPID_KEYS = {
    "MASTODON_VAPID_PRIVATE_KEY",
    "MASTODON_VAPID_PUBLIC_KEY",
}


def _placeholder(value: str) -> bool:
    normalized = value.strip().lower()
    return (
        not normalized
        or normalized.startswith("change")
        or normalized.startswith("changeme")
        or normalized == "password"
    )


def plan_secrets(context: SecretPlanningContext) -> SecretPlan:
    """Regenerate each missing VAPID pair together; other values are independent."""
    planned = {
        key for key in context.selected_keys
        if key in MASTODON_RAILS_KEYS | MASTODON_VAPID_KEYS
        and _placeholder(context.settings.get(key, ""))
    }
    if planned & MASTODON_VAPID_KEYS:
        planned.update(MASTODON_VAPID_KEYS)
    return SecretPlan(frozenset(planned))


def generate_secrets(context: SecretGenerationContext) -> dict[str, str]:
    """Use Mastodon's own Rails commands for Rails and VAPID credentials."""
    version = context.settings.get("MASTODON_VERSION", "v4.4.3")
    image = f"ghcr.io/mastodon/mastodon:{version}"
    context.report(f"generating Mastodon secrets with {image}")
    generated = {}

    for key in sorted(context.requested_keys & MASTODON_RAILS_KEYS):
        generated[key] = context.run_image(
            image, "bundle", "exec", "rails", "secret"
        )

    if context.requested_keys & MASTODON_VAPID_KEYS:
        output = context.run_image(
            image,
            "bundle",
            "exec",
            "rails",
            "mastodon:webpush:generate_vapid_key",
        )
        values = {}
        for line in output.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                values[key.strip()] = value.strip()
        if not {"VAPID_PRIVATE_KEY", "VAPID_PUBLIC_KEY"}.issubset(values):
            raise RuntimeError("Mastodon VAPID generator returned an unexpected result.")
        generated["MASTODON_VAPID_PRIVATE_KEY"] = values["VAPID_PRIVATE_KEY"]
        generated["MASTODON_VAPID_PUBLIC_KEY"] = values["VAPID_PUBLIC_KEY"]

    return generated


def validate_config(context: ValidationContext) -> ValidationResult:
    username = context.settings.get("MASTODON_ADMIN_USERNAME", "").strip().lower()
    if username == "admin":
        return ValidationResult(("MASTODON_ADMIN_USERNAME (choose a non-default username)",))
    return ValidationResult()
