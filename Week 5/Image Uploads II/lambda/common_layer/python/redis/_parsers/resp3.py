from logging import getLogger
from typing import Any, Union

from ..exceptions import ConnectionError, InvalidResponse, ResponseError
from ..typing import EncodableT
from ..utils import SENTINEL
from .base import (
    AsyncPushNotificationsParser,
    PushNotificationsParser,
    _AsyncRESPBase,
    _RESPBase,
)
from .socket import SERVER_CLOSED_CONNECTION_ERROR


class _RESP3Parser(_RESPBase, PushNotificationsParser):
    """RESP3 protocol implementation"""

    def __init__(self, socket_read_size):
        super().__init__(socket_read_size)
        self.pubsub_push_handler_func = self.handle_pubsub_push_response
        self.node_moving_push_handler_func = None
        self.maintenance_push_handler_func = None
        self.oss_cluster_maint_push_handler_func = None
        self.invalidation_push_handler_func = None

    def handle_pubsub_push_response(self, response):
        logger = getLogger("push_response")
        logger.debug("Push response: " + str(response))
        return response

    def read_response(
        self,
        disable_decoding=False,
        push_request=False,
        timeout: Union[float, object] = SENTINEL,
    ):
        pos = self._buffer.get_pos() if self._buffer is not None else None
        try:
            result = self._read_response(
                disable_decoding=disable_decoding,
                push_request=push_request,
                timeout=timeout,
            )
        except BaseException:
            if self._buffer is not None:
                self._buffer.rewind(pos)
            raise
        else:
            if self._buffer is not None:
                try:
                    self._buffer.purge()
                except AttributeError:
                    pass
            return result

    def _read_response(
        self,
        disable_decoding=False,
        push_request=False,
        timeout: Union[float, object] = SENTINEL,
    ):
        raw = self._buffer.readline(timeout=timeout)
        if not raw:
            raise ConnectionError(SERVER_CLOSED_CONNECTION_ERROR)

        byte, response = raw[:1], raw[1:]

        if byte in (b"-", b"!"):
            if byte == b"!":
                response = self._buffer.read(int(response), timeout=timeout)
            response = response.decode("utf-8", errors="replace")
            error = self.parse_error(response)
            if isinstance(error, ConnectionError):
                raise error
            return error
        elif byte == b"+":
            pass
        elif byte == b"_":
            return None
        elif byte in (b":", b"("):
            return int(response)
        elif byte == b",":
            return float(response)
        elif byte == b"#":
            return response == b"t"
        elif byte == b"$":
            response = self._buffer.read(int(response), timeout=timeout)
        elif byte == b"=":
            response = self._buffer.read(int(response), timeout=timeout)[4:]
        elif byte == b"*":
            response = [
                self._read_response(disable_decoding=disable_decoding, timeout=timeout)
                for _ in range(int(response))
            ]
        elif byte == b"~":
            response = [
                self._read_response(disable_decoding=disable_decoding, timeout=timeout)
                for _ in range(int(response))
            ]
        elif byte == b"%":
            resp_dict = {}
            for _ in range(int(response)):
                key = self._read_response(
                    disable_decoding=disable_decoding, timeout=timeout
                )
                resp_dict[key] = self._read_response(
                    disable_decoding=disable_decoding,
                    push_request=push_request,
                    timeout=timeout,
                )
            response = resp_dict
        elif byte == b">":
            response = [
                self._read_response(
                    disable_decoding=disable_decoding,
                    push_request=push_request,
                    timeout=timeout,
                )
                for _ in range(int(response))
            ]
            response = self.handle_push_response(response)

            if push_request:
                return response

            return self._read_response(
                disable_decoding=disable_decoding,
                push_request=push_request,
            )
        else:
            raise InvalidResponse(f"Protocol Error: {raw!r}")

        if isinstance(response, bytes) and disable_decoding is False:
            response = self.encoder.decode(response)

        return response


class _AsyncRESP3Parser(_AsyncRESPBase, AsyncPushNotificationsParser):
    def __init__(self, socket_read_size):
        super().__init__(socket_read_size)
        self.pubsub_push_handler_func = self.handle_pubsub_push_response
        self.invalidation_push_handler_func = None

    async def handle_pubsub_push_response(self, response):
        logger = getLogger("push_response")
        logger.debug("Push response: " + str(response))
        return response

    async def read_response(
        self, disable_decoding: bool = False, push_request: bool = False
    ):
        if self._chunks:
            self._buffer += b"".join(self._chunks)
            self._chunks.clear()
        self._pos = 0
        response = await self._read_response(
            disable_decoding=disable_decoding, push_request=push_request
        )
        self._clear()
        return response

    async def _read_response(
        self, disable_decoding: bool = False, push_request: bool = False
    ) -> Union[EncodableT, ResponseError, None]:
        if not self._stream or not self.encoder:
            raise ConnectionError(SERVER_CLOSED_CONNECTION_ERROR)
        raw = await self._readline()
        response: Any
        byte, response = raw[:1], raw[1:]


        if byte in (b"-", b"!"):
            if byte == b"!":
                response = await self._read(int(response))
            response = response.decode("utf-8", errors="replace")
            error = self.parse_error(response)
            if isinstance(error, ConnectionError):
                self._clear() 
                raise error
            return error
        elif byte == b"+":
            pass
        elif byte == b"_":
            return None
        elif byte in (b":", b"("):
            return int(response)
        elif byte == b",":
            return float(response)
        elif byte == b"#":
            return response == b"t"
        elif byte == b"$":
            response = await self._read(int(response))
        elif byte == b"=":
            response = (await self._read(int(response)))[4:]
        elif byte == b"*":
            response = [
                (await self._read_response(disable_decoding=disable_decoding))
                for _ in range(int(response))
            ]
        elif byte == b"~":
            response = [
                (await self._read_response(disable_decoding=disable_decoding))
                for _ in range(int(response))
            ]
        elif byte == b"%":
            resp_dict = {}
            for _ in range(int(response)):
                key = await self._read_response(disable_decoding=disable_decoding)
                resp_dict[key] = await self._read_response(
                    disable_decoding=disable_decoding, push_request=push_request
                )
            response = resp_dict
        elif byte == b">":
            response = [
                (
                    await self._read_response(
                        disable_decoding=disable_decoding, push_request=push_request
                    )
                )
                for _ in range(int(response))
            ]
            response = await self.handle_push_response(response)
            if not push_request:
                return await self._read_response(
                    disable_decoding=disable_decoding, push_request=push_request
                )
            else:
                return response
        else:
            raise InvalidResponse(f"Protocol Error: {raw!r}")

        if isinstance(response, bytes) and disable_decoding is False:
            response = self.encoder.decode(response)
        return response
