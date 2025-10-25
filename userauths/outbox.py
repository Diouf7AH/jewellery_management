from django.utils import timezone

from .models import OutboxEmail


def enqueue_email(*, to, template, context, reason=""):
    return OutboxEmail.objects.create(
        to=to, template=template, context=context, reason=reason,
        next_try_at=timezone.now()
    )

