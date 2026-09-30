"""Notifications Discord éphémères supprimées après un délai, sans rafraîchissement."""
import asyncio
import logging

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
    """Envoie une notification personnelle et programme sa suppression après 30 s."""
    message = await interaction.followup.send(content, ephemeral=True, wait=True)
    asyncio.create_task(_remove_after(interaction, message.id, seconds))
    return message
