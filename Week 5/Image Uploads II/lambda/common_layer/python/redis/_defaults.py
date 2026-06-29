"""Internal default helper functions shared across redis-py modules."""

import socket


DEFAULT_SOCKET_TIMEOUT = 5 
DEFAULT_SOCKET_CONNECT_TIMEOUT = DEFAULT_SOCKET_TIMEOUT
DEFAULT_SOCKET_READ_SIZE = 32768 


def get_default_socket_keepalive_options() -> dict[int, int]:
    options = {}

    tcp_keepidle = getattr(socket, "TCP_KEEPIDLE", None)
    if tcp_keepidle is None:
        tcp_keepidle = getattr(socket, "TCP_KEEPALIVE", None)
    if tcp_keepidle is not None:
        options[tcp_keepidle] = 30

    tcp_keepintvl = getattr(socket, "TCP_KEEPINTVL", None)
    if tcp_keepintvl is not None:
        options[tcp_keepintvl] = 5

    tcp_keepcnt = getattr(socket, "TCP_KEEPCNT", None)
    if tcp_keepcnt is not None:
        options[tcp_keepcnt] = 3

    return options


DEFAULT_RETRY_COUNT = 10
DEFAULT_RETRY_BASE = 0.01 
DEFAULT_RETRY_CAP = 1 
