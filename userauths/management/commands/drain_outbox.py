import logging
from datetime import timedelta
from smtplib import (SMTPDataError, SMTPException, SMTPRecipientsRefused,
                     SMTPSenderRefused)
from time import sleep

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import OutboxEmail
from ...utils import send_confirmation_email

logger = logging.getLogger("mailer")

BACKOFFS_MIN = [1, 5, 15, 30, 60, 120]  # exponentiel light
MAX_ATTEMPTS = 8

class Command(BaseCommand):
    help = "Envoie les emails en file d’attente avec retry/backoff."

    def handle(self, *args, **opts):
        User = get_user_model()
        now = timezone.now()
        qs = OutboxEmail.objects.filter(next_try_at__lte=now).order_by("created_at")[:200]

        for msg in qs:
            # 1) Arrêt définitif si trop de tentatives
            if msg.attempts >= MAX_ATTEMPTS:
                logger.warning(f"[OUTBOX DROP] to={msg.to} template={msg.template} attempts={msg.attempts} -> delete")
                msg.delete()
                continue

            try:
                # 2) Routage par template
                if msg.template == "confirm_email":
                    user_id = msg.context.get("user_id")
                    if not user_id:
                        logger.error(f"[OUTBOX BADCTX] missing user_id in context, to={msg.to}")
                        msg.delete()
                        continue

                    try:
                        user = User.objects.get(id=user_id)
                    except User.DoesNotExist:
                        logger.error(f"[OUTBOX BADCTX] user {user_id} not found, to={msg.to}")
                        msg.delete()
                        continue

                    send_confirmation_email(
                        user,
                        request=None,
                        confirm_url=msg.context.get("confirm_url"),
                        home_url=msg.context.get("home_url"),
                    )
                else:
                    logger.error(f"[OUTBOX UNKNOWN TEMPLATE] {msg.template}, to={msg.to} -> delete")
                    msg.delete()
                    continue

                # 3) Succès → suppression
                logger.info(f"[OUTBOX SENT] to={msg.to} template={msg.template}")
                msg.delete()

            except (SMTPRecipientsRefused, SMTPDataError, SMTPSenderRefused, SMTPException) as e:
                # 4) Erreurs SMTP → retry avec backoff exponentiel
                msg.attempts += 1
                idx = min(msg.attempts - 1, len(BACKOFFS_MIN) - 1)
                delay_min = BACKOFFS_MIN[idx]
                msg.next_try_at = timezone.now() + timedelta(minutes=delay_min)
                msg.last_error = str(e)
                msg.save(update_fields=["attempts", "next_try_at", "last_error"])
                logger.warning(f"[OUTBOX RETRY] to={msg.to} attempts={msg.attempts} in {delay_min}m err={e}")

            except Exception as e:
                # 5) Autres erreurs → petit backoff générique
                msg.attempts += 1
                msg.next_try_at = timezone.now() + timedelta(minutes=5)
                msg.last_error = str(e)
                msg.save(update_fields=["attempts", "next_try_at", "last_error"])
                logger.exception(f"[OUTBOX RETRY-GENERIC] to={msg.to} attempts={msg.attempts} in 5m")

            # 6) Anti-burst
            sleep(0.05)
            