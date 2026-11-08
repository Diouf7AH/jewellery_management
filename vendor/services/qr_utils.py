from uuid import UUID


def decode_etiquette_qr(qr_content: str) -> UUID:
    """
    Format attendu : PL:<uuid ProduitLine>
    """

    if not isinstance(qr_content, str):
        raise ValueError(
            "Le QR code doit être une chaîne."
        )

    code = qr_content.strip()

    if not code.startswith("PL:"):
        raise ValueError(
            "Format QR invalide. Préfixe PL: attendu."
        )

    try:
        return UUID(code[3:])

    except (ValueError, TypeError, AttributeError) as exc:
        raise ValueError(
            "UUID de l'étiquette invalide."
        ) from exc
        
        