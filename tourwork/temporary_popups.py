"""Notifications Discord éphémères supprimées après un délai, sans rafraîchissement."""
import asyncio
import logging
import discord

LOG = logging.getLogger(__name__)
DEFAULT_LIFETIME = 30


async def _remove_after(interaction, message_id, seconds):
    await asyncio.sleep(seconds)
    try:
        await interaction.followup.delete_message(message_id)
    except Exception as exc:
        # Les messages éphémères peuvent déjà avoir été fermés par le client.
        LOG.debug("Notification déjà fermée ou suppression indisponible : %s", exc)


async def send_temporary_followup(interaction, content, *, seconds=DEFAULT_LIFETIME):
    """Envoie une notification personnelle et programme sa suppression après 30 s.

    Une interaction dont le webhook est déjà expiré ne doit jamais faire planter
    le callback Discord : le message est simplement abandonné proprement.
    """
    try:
        message = await interaction.followup.send(content, ephemeral=True, wait=True)
    except Exception as exc:
        # Discord peut répondre 10015/10062 lorsque le token d'interaction
        # n'est plus utilisable (ancien composant, reconnexion, latence).
        if getattr(exc, "code", None) in (10015, 10062) or isinstance(exc, discord.NotFound):
            LOG.debug("Popup temporaire indisponible : %s", exc)
            return None
        raise
    if message is not None:
        asyncio.create_task(_remove_after(interaction, message.id, seconds))
    return message
