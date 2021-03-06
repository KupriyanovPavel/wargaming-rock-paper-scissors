import asyncio
import logging
from concurrent.futures import TimeoutError

from websockets.exceptions import ConnectionClosed

from .utils import Action, Pick, OPPONENTS


class Player:

    def __init__(self, connection, session):
        self.connection = connection
        self.session = session
        self.user = connection.user

    def __str__(self):
        return str(f"<Player {self.user.nickname}>.")

    async def keep(self):
        """
        Keep and correct close player connection.
        :return: None
        """
        await self.connection.keep()
        logging.info(f"{self} disconnected from {self.session}.")
        await self.close()

    async def send(self, action, payload):
        """
        Send message to player.
        :param action: type of message
        :param payload: data of message
        :return: None
        """
        try:
            await self.connection.send(action, payload)
        except ConnectionClosed:
            logging.warning(f"Send failed: {self} connection closed.")
            await self.close()

    async def recv(self, timeout=None):
        """
        Read message from connection.
        :param timeout: number of second to close by timeout.
        :return: message or None
        """
        try:
            return await asyncio.wait_for(self.connection.recv(), timeout=timeout)
        except (ConnectionError, TimeoutError) as e:
            logging.warning(f"Failed to read from {self}: {str(e)}.")
        except ConnectionClosed:
            logging.warning(f"Read failed: {self} connection closed.")
            await self.close()
        return None

    async def send_and_recv(self, action, payload, timeout=None):
        """
        Shortcut for send and recv
        :param action: type of message
        :param payload: data of message
        :param timeout: number of second to close by timeout.
        :return: message or None
        """
        await self.send(action, payload)
        return await self.recv(timeout)

    async def remove_if_not_ready(self):
        """
        Confirm what player is ready or close connection.
        :return: bool - ready player or not
        """
        timeout = self.session.ready_timeout
        res = await self.send_and_recv(Action.READY_CHECK, {"timeout": timeout}, timeout)
        if res and res.get("action") == Action.READY_CHECK:
            await self.send(Action.READY_CHECK, {"status": True})
            return True
        logging.info(f"{self} is not ready. Disconnect.")
        await self.close()
        return False

    async def get_pick(self, current_round):
        """
        Get pick from player
        :param current_round: number of current game round
        :return: Pick of user
        """
        timeout = self.session.pick_timeout
        res = await self.send_and_recv(Action.PICK, {"timeout": timeout, "current_round": current_round}, timeout)

        if res is None:
            logging.info(f"{self} is not pick anything.")
            await self.send(Action.PICK, {"status": False})
            return Pick(self, None)

        action, payload = res.get("action"), res.get("payload")
        if action == "pick" and payload.get("pick") in OPPONENTS.keys():
            await self.send(Action.PICK, {"status": True})
            return Pick(self, payload.get("pick"))
        else:
            await self.send(Action.PICK, {"status": False})
            return Pick(self, None)

    async def close(self):
        """
        Call session disconnect method and close connection
        :return: None
        """
        await self.session.disconnect(self)
        await self.connection.close()
