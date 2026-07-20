"""Custom form fields — currently just the natural-language date field used
across admin (core/admin.py's NATURAL_DATE_OVERRIDES)."""

import datetime as dt

from django import forms
from django.utils.dateparse import parse_date

from engine.dateparse import parse_natural_date

_PLACEHOLDER = "e.g. 2026-08-01, next friday, in 3 days"


class NaturalDateField(forms.CharField):
    """A plain text date field that accepts either a strict ISO date or a
    handful of natural-language phrases (plan §11 item 3), instead of a
    click-only calendar widget."""

    widget = forms.TextInput(attrs={"placeholder": _PLACEHOLDER})

    def to_python(self, value):
        value = (value or "").strip()
        if not value:
            return None
        parsed = parse_date(value) or parse_natural_date(value, dt.date.today())
        if parsed is None:
            raise forms.ValidationError(
                "Couldn't understand that date. Try YYYY-MM-DD, \"today\", "
                "\"tomorrow\", \"next friday\", or \"in 5 days\".")
        return parsed

    def prepare_value(self, value):
        if isinstance(value, dt.date):
            return value.isoformat()
        return value
