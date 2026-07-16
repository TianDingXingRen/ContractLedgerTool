"""Blueprint compatibility helpers for preserving legacy endpoint names."""

from __future__ import annotations

from flask import Blueprint
from flask.sansio.blueprints import BlueprintSetupState


class _LegacyEndpointSetupState(BlueprintSetupState):
    """Register Blueprint rules without prefixing their endpoint names.

    The application historically exposed unqualified Flask endpoint names to
    templates and extensions. URLs remain unchanged and endpoint names keep
    working while route ownership moves to real Blueprints.
    """

    def add_url_rule(self, rule, endpoint=None, view_func=None, **options):
        if self.url_prefix is not None:
            if rule:
                rule = "/".join((self.url_prefix.rstrip("/"), rule.lstrip("/")))
            else:
                rule = self.url_prefix
        options.setdefault("subdomain", self.subdomain)
        endpoint = endpoint or view_func.__name__
        defaults = self.url_defaults
        if "defaults" in options:
            defaults = dict(defaults, **options.pop("defaults"))
        self.app.add_url_rule(
            rule,
            endpoint,
            view_func,
            defaults=defaults,
            **options,
        )


class LegacyEndpointBlueprint(Blueprint):
    """A Blueprint that retains the application's existing endpoint names."""

    def make_setup_state(self, app, options, first_registration=False):
        return _LegacyEndpointSetupState(self, app, options, first_registration)
