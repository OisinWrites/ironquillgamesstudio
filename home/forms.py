from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError


class StaffAuthenticationForm(AuthenticationForm):
    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_staff:
            raise ValidationError(
                "This account does not have staff access.",
                code="not_staff",
            )
