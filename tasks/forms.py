from django import forms

from tasks.models import Task


class BootstrapFormMixin:
    """Aplica classes do Bootstrap aos widgets: `form-check-input` para
    checkboxes, `form-control` para os demais (inclusive selects, que o
    Bootstrap 5 também estiliza com `form-select`, tratado à parte quando
    necessário).
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            existing = field.widget.attrs.get("class", "")
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs["class"] = (existing + " form-check-input").strip()
            else:
                field.widget.attrs["class"] = (existing + " form-control").strip()


class TaskForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Task
        fields = [
            "title",
            "notes",
            "scheduled_for",
            "status",
            "remind_enabled",
            "remind_minutes_before",
        ]
        widgets = {
            "scheduled_for": forms.DateTimeInput(
                attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"
            ),
            "notes": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["scheduled_for"].input_formats = ["%Y-%m-%dT%H:%M"]
        self.fields["remind_minutes_before"].required = False

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("remind_enabled") and not cleaned.get("remind_minutes_before"):
            self.add_error(
                "remind_minutes_before",
                "Escolha com quanto tempo de antecedência avisar.",
            )
        if not cleaned.get("remind_enabled"):
            cleaned["remind_minutes_before"] = None
        return cleaned
