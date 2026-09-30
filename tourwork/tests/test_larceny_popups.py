import asyncio
import unittest
from unittest.mock import AsyncMock
from larceny_flavor import LARCENY_SCENES, random_larceny_scene
from temporary_popups import send_temporary_followup

class LarcenyPopupTests(unittest.IsolatedAsyncioTestCase):
    def test_scenes(self):
        self.assertGreaterEqual(len(LARCENY_SCENES), 10)
        self.assertIn(random_larceny_scene(), LARCENY_SCENES)

    async def test_temporary_popup(self):
        class Interaction:
            pass
        i = Interaction()
        i.followup = AsyncMock()
        i.followup.send.return_value.id = 123
        await send_temporary_followup(i, 'test', seconds=0)
        await asyncio.sleep(.01)
        i.followup.send.assert_awaited_once_with('test', ephemeral=True, wait=True)
        i.followup.delete_message.assert_awaited_once_with(123)
