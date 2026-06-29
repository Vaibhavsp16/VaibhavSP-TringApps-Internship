import asyncio
import collections
import logging
import random
import socket
import threading
import time
import warnings
import weakref
from abc import ABC, abstractmethod
from collections import defaultdict
from copy import copy
from itertools import chain
from types import MethodType
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Coroutine,
    Deque,
    Dict,
    Generator,
    List,
    Literal,
    Mapping,
    Optional,
    Set,
    Tuple,
    Type,
    TypeVar,
    Union,
)

if TYPE_CHECKING:
    from redis.asyncio.keyspace_notifications import (
        AsyncClusterKeyspaceNotifications,
    )

from redis._defaults import (
    DEFAULT_RETRY_BASE,
    DEFAULT_RETRY_CAP,
    DEFAULT_RETRY_COUNT,
    DEFAULT_SOCKET_CONNECT_TIMEOUT,
    DEFAULT_SOCKET_READ_SIZE,
    DEFAULT_SOCKET_TIMEOUT,
)
from redis._parsers import AsyncCommandsParser, Encoder
from redis._parsers.commands import CommandPolicies, RequestPolicy, ResponsePolicy
from redis._parsers.helpers import get_response_callbacks
from redis.asyncio.client import PubSub, ResponseCallbackT
from redis.asyncio.connection import (
    AbstractConnection,
    Connection,
    ConnectionPoolInterface,
    SSLConnection,
    parse_url,
)
from redis.asyncio.lock import Lock
from redis.asyncio.observability.recorder import (
    record_error_count,
    record_operation_duration,
)
from redis.asyncio.retry import Retry
from redis.auth.token import TokenInterface
from redis.backoff import ExponentialWithJitterBackoff, NoBackoff
from redis.client import EMPTY_RESPONSE, NEVER_DECODE, AbstractRedis
from redis.cluster import (
    PIPELINE_BLOCKED_COMMANDS,
    PRIMARY,
    REPLICA,
    SLOT_ID,
    AbstractRedisCluster,
    LoadBalancer,
    LoadBalancingStrategy,
    block_pipeline_command,
    get_node_name,
    parse_cluster_shards,
    parse_cluster_shards_unified,
    parse_cluster_shards_with_str_keys,
    parse_cluster_slots,
)
from redis.commands import READ_COMMANDS, AsyncRedisClusterCommands
from redis.commands.helpers import list_or_args, parse_pubsub_subscriptions
from redis.commands.policies import AsyncPolicyResolver, AsyncStaticPolicyResolver
from redis.crc import REDIS_CLUSTER_HASH_SLOTS, key_slot
from redis.credentials import CredentialProvider
from redis.driver_info import DriverInfo, resolve_driver_info
from redis.event import (
    AfterAsyncClusterInstantiationEvent,
    AsyncAfterSlotsCacheRefreshEvent,
    AsyncEventListenerInterface,
    EventDispatcher,
)
from redis.exceptions import (
    AskError,
    BusyLoadingError,
    ClusterDownError,
    ClusterError,
    ConnectionError,
    CrossSlotTransactionError,
    DataError,
    ExecAbortError,
    InvalidPipelineStack,
    MaxConnectionsError,
    MovedError,
    RedisClusterException,
    RedisError,
    ResponseError,
    SlotNotCoveredError,
    TimeoutError,
    TryAgainError,
    WatchError,
)
from redis.typing import (
    AnyKeyT,
    ChannelT,
    EncodableT,
    KeyT,
    PubSubHandler,
    Subscription,
)
from redis.utils import (
    SENTINEL,
    SSL_AVAILABLE,
    deprecated_args,
    deprecated_function,
    safe_str,
    str_if_bytes,
    truncate_text,
)

if SSL_AVAILABLE:
    from ssl import TLSVersion, VerifyFlags, VerifyMode
else:
    TLSVersion = None
    VerifyMode = None
    VerifyFlags = None

logger = logging.getLogger(__name__)

TargetNodesT = TypeVar(
    "TargetNodesT", str, "ClusterNode", List["ClusterNode"], Dict[Any, "ClusterNode"]
)


class RedisCluster(AbstractRedis, AbstractRedisCluster, AsyncRedisClusterCommands):
    """
    Create a new RedisCluster client.

    Pass one of parameters:

      - `host` & `port`
      - `startup_nodes`

    | Use ``await`` :meth:`initialize` to find cluster nodes & create connections.
    | Use ``await`` :meth:`close` to disconnect connections & close client.

    Many commands support the target_nodes kwarg. It can be one of the
    :attr:`NODE_FLAGS`:

      - :attr:`PRIMARIES`
      - :attr:`REPLICAS`
      - :attr:`ALL_NODES`
      - :attr:`RANDOM`
      - :attr:`DEFAULT_NODE`

    Note: This client is not thread/process/fork safe.

    :param host:
        | Can be used to point to a startup node
    :param port:
        | Port used if **host** is provided
    :param startup_nodes:
        | :class:`~.ClusterNode` to used as a startup node
    :param require_full_coverage:
        | When set to ``False``: the client will not require a full coverage of
          the slots. However, if not all slots are covered, and at least one node
          has ``cluster-require-full-coverage`` set to ``yes``, the server will throw
          a :class:`~.ClusterDownError` for some key-based commands.
        | When set to ``True``: all slots must be covered to construct the cluster
          client. If not all slots are covered, :class:`~.RedisClusterException` will be
          thrown.
        | See:
          https://redis.io/docs/manual/scaling/#redis-cluster-configuration-parameters
    :param read_from_replicas:
        | @deprecated - please use load_balancing_strategy instead
        | Enable read from replicas in READONLY mode.
          When set to true, read commands will be assigned between the primary and
          its replications in a Round-Robin manner.
          The data read from replicas is eventually consistent with the data in primary nodes.
    :param load_balancing_strategy:
        | Enable read from replicas in READONLY mode and defines the load balancing
          strategy that will be used for cluster node selection.
          The data read from replicas is eventually consistent with the data in primary nodes.
    :param dynamic_startup_nodes:
        | Set the RedisCluster's startup nodes to all the discovered nodes.
          If true (default value), the cluster's discovered nodes will be used to
          determine the cluster nodes-slots mapping in the next topology refresh.
          It will remove the initial passed startup nodes if their endpoints aren't
          listed in the CLUSTER SLOTS output.
          If you use dynamic DNS endpoints for startup nodes but CLUSTER SLOTS lists
          specific IP addresses, it is best to set it to false.
    :param reinitialize_steps:
        | Specifies the number of MOVED errors that need to occur before reinitializing
          the whole cluster topology. If a MOVED error occurs and the cluster does not
          need to be reinitialized on this current error handling, only the MOVED slot
          will be patched with the redirected node.
          To reinitialize the cluster on every MOVED error, set reinitialize_steps to 1.
          To avoid reinitializing the cluster on moved errors, set reinitialize_steps to
          0.
    :param cluster_error_retry_attempts:
        | @deprecated - Please configure the 'retry' object instead
          In case 'retry' object is set - this argument is ignored!

          Number of times to retry before raising an error when :class:`~.TimeoutError`,
          :class:`~.ConnectionError`, :class:`~.SlotNotCoveredError`
          or :class:`~.ClusterDownError` are encountered
    :param retry:
        | A retry object that defines the retry strategy and the number of
          retries for the cluster client.
          In current implementation for the cluster client (starting form redis-py version 6.0.0)
          the retry object is not yet fully utilized, instead it is used just to determine
          the number of retries for the cluster client.
          In the future releases the retry object will be used to handle the cluster client retries!
    :param max_connections:
        | Maximum number of connections per node. If there are no free connections & the
          maximum number of connections are already created, a
          :class:`~.MaxConnectionsError` is raised.
    :param socket_keepalive:
        | If ``True``, TCP keepalive is enabled for TCP socket connections.
    :param socket_keepalive_options:
        | Mapping of TCP keepalive socket option constants to values, for
          example ``{socket.TCP_KEEPIDLE: 30}``. If left unspecified, redis-py
          uses TCP keepalive defaults when ``socket_keepalive`` is enabled:
          idle 30 seconds, interval 5 seconds, and 3 probes.
          Platform-specific options that are not available are skipped.
          Pass ``None`` or ``{}`` to avoid setting additional TCP keepalive
          options.
    :param address_remap:
        | An optional callable which, when provided with an internal network
          address of a node, e.g. a `(host, port)` tuple, will return the address
          where the node is reachable.  This can be used to map the addresses at
          which the nodes _think_ they are, to addresses at which a client may
          reach them, such as when they sit behind a proxy.

    | Rest of the arguments will be passed to the
      :class:`~redis.asyncio.connection.Connection` instances when created

    :raises RedisClusterException:
        if any arguments are invalid or unknown. Eg:

        - `db` != 0 or None
        - `path` argument for unix socket connection
        - none of the `host`/`port` & `startup_nodes` were provided

    """

    @classmethod
    def from_url(cls, url: str, **kwargs: Any) -> "RedisCluster":
        """
        Return a Redis client object configured from the given URL.

        For example::

            redis://[[username]:[password]]@localhost:6379/0
            rediss://[[username]:[password]]@localhost:6379/0

        Three URL schemes are supported:

        - `redis://` creates a TCP socket connection. See more at:
          <https://www.iana.org/assignments/uri-schemes/prov/redis>
        - `rediss://` creates a SSL wrapped TCP socket connection. See more at:
          <https://www.iana.org/assignments/uri-schemes/prov/rediss>

        The username, password, hostname, path and all querystring values are passed
        through ``urllib.parse.unquote`` in order to replace any percent-encoded values
        with their corresponding characters.

        All querystring options are cast to their appropriate Python types. Boolean
        arguments can be specified with string values "True"/"False" or "Yes"/"No".
        Values that cannot be properly cast cause a ``ValueError`` to be raised. Once
        parsed, the querystring arguments and keyword arguments are passed to
        :class:`~redis.asyncio.connection.Connection` when created.
        In the case of conflicting arguments, querystring arguments are used.
        """
        kwargs.update(parse_url(url))
        if kwargs.pop("connection_class", None) is SSLConnection:
            kwargs["ssl"] = True
        return cls(**kwargs)

    _is_async_client: Literal[True] = True

    __slots__ = (
        "_initialize",
        "_lock",
        "retry",
        "command_flags",
        "commands_parser",
        "connection_kwargs",
        "encoder",
        "node_flags",
        "nodes_manager",
        "read_from_replicas",
        "reinitialize_counter",
        "reinitialize_steps",
        "response_callbacks",
        "result_callbacks",
    )

    @deprecated_args(
        args_to_warn=["read_from_replicas"],
        reason="Please configure the 'load_balancing_strategy' instead",
        version="5.3.0",
    )
    @deprecated_args(
        args_to_warn=[
            "cluster_error_retry_attempts",
        ],
        reason="Please configure the 'retry' object instead",
        version="6.0.0",
    )
    @deprecated_args(
        args_to_warn=["lib_name", "lib_version"],
        reason="Use 'driver_info' parameter instead. "
        "lib_name and lib_version will be removed in a future version.",
    )
    def __init__(
        self,
        host: str | None = None,
        port: str | int = 6379,
        startup_nodes: List["ClusterNode"] | None = None,
        require_full_coverage: bool = True,
        read_from_replicas: bool = False,
        load_balancing_strategy: LoadBalancingStrategy | None = None,
        dynamic_startup_nodes: bool = True,
        reinitialize_steps: int = 5,
        cluster_error_retry_attempts: int = DEFAULT_RETRY_COUNT,
        max_connections: int = 100,
        retry: Retry | None = None,
        retry_on_error: List[Type[Exception]] | None = None,
        db: str | int = 0,
        path: str | None = None,
        credential_provider: CredentialProvider | None = None,
        username: str | None = None,
        password: str | None = None,
        client_name: str | None = None,
        lib_name: str | object | None = SENTINEL,
        lib_version: str | object | None = SENTINEL,
        driver_info: DriverInfo | object | None = SENTINEL,
        encoding: str = "utf-8",
        encoding_errors: str = "strict",
        decode_responses: bool = False,
        health_check_interval: float = 0,
        socket_timeout: float | None = DEFAULT_SOCKET_TIMEOUT,
        socket_connect_timeout: float | None = DEFAULT_SOCKET_CONNECT_TIMEOUT,
        socket_read_size: int = DEFAULT_SOCKET_READ_SIZE,
        socket_keepalive: bool = True,
        socket_keepalive_options: Mapping[int, int | bytes] | object | None = SENTINEL,
        ssl: bool = False,
        ssl_ca_certs: str | None = None,
        ssl_ca_data: str | None = None,
        ssl_cert_reqs: "str | VerifyMode" = "required",
        ssl_include_verify_flags: List["VerifyFlags"] | None = None,
        ssl_exclude_verify_flags: List["VerifyFlags"] | None = None,
        ssl_certfile: str | None = None,
        ssl_check_hostname: bool = True,
        ssl_keyfile: str | None = None,
        ssl_min_version: "TLSVersion | None" = None,
        ssl_ciphers: str | None = None,
        protocol: int | None = None,
        legacy_responses: bool = True,
        address_remap: Callable[[Tuple[str, int]], Tuple[str, int]] | None = None,
        event_dispatcher: EventDispatcher | None = None,
        policy_resolver: AsyncPolicyResolver = AsyncStaticPolicyResolver(),
    ) -> None:
        if db:
            raise RedisClusterException(
                "Argument 'db' must be 0 or None in cluster mode"
            )

        if path:
            raise RedisClusterException(
                "Unix domain socket is not supported in cluster mode"
            )

        if (not host or not port) and not startup_nodes:
            raise RedisClusterException(
                "RedisCluster requires at least one node to discover the cluster.\n"
                "Please provide one of the following or use RedisCluster.from_url:\n"
                '   - host and port: RedisCluster(host="localhost", port=6379)\n'
                "   - startup_nodes: RedisCluster(startup_nodes=["
                'ClusterNode("localhost", 6379), ClusterNode("localhost", 6380)])'
            )

        computed_driver_info = resolve_driver_info(driver_info, lib_name, lib_version)

        kwargs: Dict[str, Any] = {
            "max_connections": max_connections,
            "connection_class": Connection,
            "credential_provider": credential_provider,
            "username": username,
            "password": password,
            "client_name": client_name,
            "driver_info": computed_driver_info,
            "encoding": encoding,
            "encoding_errors": encoding_errors,
            "decode_responses": decode_responses,
            "health_check_interval": health_check_interval,
            "socket_connect_timeout": socket_connect_timeout,
            "socket_keepalive": socket_keepalive,
            "socket_keepalive_options": socket_keepalive_options,
            "socket_read_size": socket_read_size,
            "socket_timeout": socket_timeout,
            "protocol": protocol,
            "legacy_responses": legacy_responses,
        }

        if ssl:
            kwargs.update(
                {
                    "connection_class": SSLConnection,
                    "ssl_ca_certs": ssl_ca_certs,
                    "ssl_ca_data": ssl_ca_data,
                    "ssl_cert_reqs": ssl_cert_reqs,
                    "ssl_include_verify_flags": ssl_include_verify_flags,
                    "ssl_exclude_verify_flags": ssl_exclude_verify_flags,
                    "ssl_certfile": ssl_certfile,
                    "ssl_check_hostname": ssl_check_hostname,
                    "ssl_keyfile": ssl_keyfile,
                    "ssl_min_version": ssl_min_version,
                    "ssl_ciphers": ssl_ciphers,
                }
            )

        if read_from_replicas or load_balancing_strategy:
            kwargs["redis_connect_func"] = self.on_connect

        if retry:
            self.retry = retry
        else:
            self.retry = Retry(
                backoff=ExponentialWithJitterBackoff(
                    base=DEFAULT_RETRY_BASE, cap=DEFAULT_RETRY_CAP
                ),
                retries=cluster_error_retry_attempts,
            )
        if retry_on_error:
            self.retry.update_supported_errors(retry_on_error)

        kwargs["response_callbacks"] = get_response_callbacks(
            user_protocol=kwargs.get("protocol"),
            legacy_responses=kwargs.get("legacy_responses", True),
        )
        if not kwargs.get("legacy_responses", True):
            kwargs["response_callbacks"]["CLUSTER SHARDS"] = (
                parse_cluster_shards_unified
            )
        elif kwargs.get("protocol") is None:
            kwargs["response_callbacks"]["CLUSTER SHARDS"] = (
                parse_cluster_shards_with_str_keys
            )
        else:
            kwargs["response_callbacks"]["CLUSTER SHARDS"] = parse_cluster_shards
        self.connection_kwargs = kwargs

        if startup_nodes:
            passed_nodes = []
            for node in startup_nodes:
                passed_nodes.append(
                    ClusterNode(node.host, node.port, **self.connection_kwargs)
                )
            startup_nodes = passed_nodes
        else:
            startup_nodes = []
        if host and port:
            startup_nodes.append(ClusterNode(host, port, **self.connection_kwargs))

        if event_dispatcher is None:
            self._event_dispatcher = EventDispatcher()
        else:
            self._event_dispatcher = event_dispatcher

        self.startup_nodes = startup_nodes
        self.nodes_manager = NodesManager(
            startup_nodes,
            require_full_coverage,
            kwargs,
            dynamic_startup_nodes=dynamic_startup_nodes,
            address_remap=address_remap,
            event_dispatcher=self._event_dispatcher,
        )
        self.encoder = Encoder(encoding, encoding_errors, decode_responses)
        self.read_from_replicas = read_from_replicas
        self.load_balancing_strategy = load_balancing_strategy
        self.reinitialize_steps = reinitialize_steps
        self.reinitialize_counter = 0

        self._command_flags_mapping: dict[str, Union[RequestPolicy, ResponsePolicy]] = {
            self.__class__.RANDOM: RequestPolicy.DEFAULT_KEYLESS,
            self.__class__.PRIMARIES: RequestPolicy.ALL_SHARDS,
            self.__class__.ALL_NODES: RequestPolicy.ALL_NODES,
            self.__class__.REPLICAS: RequestPolicy.ALL_REPLICAS,
            self.__class__.DEFAULT_NODE: RequestPolicy.DEFAULT_NODE,
            SLOT_ID: RequestPolicy.DEFAULT_KEYED,
        }

        self._policies_callback_mapping: dict[
            Union[RequestPolicy, ResponsePolicy], Callable
        ] = {
            RequestPolicy.DEFAULT_KEYLESS: lambda command_name: [
                self.get_random_primary_or_all_nodes(command_name)
            ],
            RequestPolicy.DEFAULT_KEYED: self.get_nodes_from_slot,
            RequestPolicy.DEFAULT_NODE: lambda: [self.get_default_node()],
            RequestPolicy.ALL_SHARDS: self.get_primaries,
            RequestPolicy.ALL_NODES: self.get_nodes,
            RequestPolicy.ALL_REPLICAS: self.get_replicas,
            RequestPolicy.SPECIAL: self.get_special_nodes,
            ResponsePolicy.DEFAULT_KEYLESS: lambda res: res,
            ResponsePolicy.DEFAULT_KEYED: lambda res: res,
        }

        self._policy_resolver = policy_resolver
        self.commands_parser = AsyncCommandsParser()
        self._aggregate_nodes = None
        self.node_flags = self.__class__.NODE_FLAGS.copy()
        self.command_flags = self.__class__.COMMAND_FLAGS.copy()
        self.response_callbacks = kwargs["response_callbacks"]
        self.result_callbacks = self.__class__.RESULT_CALLBACKS.copy()
        self.result_callbacks["CLUSTER SLOTS"] = (
            lambda cmd, res, **kwargs: parse_cluster_slots(
                list(res.values())[0], **kwargs
            )
        )

        self._initialize = True
        self._lock: Optional[asyncio.Lock] = None

        self._usage_counter = 0
        self._usage_lock = asyncio.Lock()

    async def initialize(
        self,
        additional_startup_nodes_info: Optional[List[Tuple[str, int]]] = None,
        last_failed_node_name: Optional[str] = None,
    ) -> "RedisCluster":
        """Get all nodes from startup nodes & creates connections if not initialized."""
        if self._initialize:
            if not self._lock:
                self._lock = asyncio.Lock()
            async with self._lock:
                if self._initialize:
                    try:
                        await self.nodes_manager.initialize(
                            additional_startup_nodes_info=additional_startup_nodes_info,
                            last_failed_node_name=last_failed_node_name,
                        )
                        await self.commands_parser.initialize(
                            self.nodes_manager.default_node
                        )
                        self._initialize = False
                    except BaseException:
                        await self.nodes_manager.aclose()
                        await self.nodes_manager.aclose("startup_nodes")
                        raise
        return self

    async def aclose(self) -> None:
        """Close all connections & client if initialized."""
        if not self._initialize:
            if not self._lock:
                self._lock = asyncio.Lock()
            async with self._lock:
                if not self._initialize:
                    self._initialize = True
                    await self.nodes_manager.aclose()
                    await self.nodes_manager.aclose("startup_nodes")

    @deprecated_function(version="5.0.0", reason="Use aclose() instead", name="close")
    async def close(self) -> None:
        """alias for aclose() for backwards compatibility"""
        await self.aclose()

    async def __aenter__(self) -> "RedisCluster":
        """
        Async context manager entry. Increments a usage counter so that the
        connection pool is only closed (via aclose()) when no context is using
        the client.
        """
        await self._increment_usage()
        try:
            return await self.initialize()
        except Exception:
            await self._decrement_usage()
            raise

    async def _increment_usage(self) -> int:
        """
        Helper coroutine to increment the usage counter while holding the lock.
        Returns the new value of the usage counter.
        """
        async with self._usage_lock:
            self._usage_counter += 1
            return self._usage_counter

    async def _decrement_usage(self) -> int:
        """
        Helper coroutine to decrement the usage counter while holding the lock.
        Returns the new value of the usage counter.
        """
        async with self._usage_lock:
            self._usage_counter -= 1
            return self._usage_counter

    async def __aexit__(self, exc_type, exc_value, traceback):
        """
        Async context manager exit. Decrements a usage counter. If this is the
        last exit (counter becomes zero), the client closes its connection pool.
        """
        current_usage = await asyncio.shield(self._decrement_usage())
        if current_usage == 0:
            await asyncio.shield(self.aclose())

    def __await__(self) -> Generator[Any, None, "RedisCluster"]:
        return self.initialize().__await__()

    _DEL_MESSAGE = "Unclosed RedisCluster client"

    def __del__(
        self,
        _warn: Any = warnings.warn,
        _grl: Any = asyncio.get_running_loop,
    ) -> None:
        if hasattr(self, "_initialize") and not self._initialize:
            _warn(f"{self._DEL_MESSAGE} {self!r}", ResourceWarning, source=self)
            try:
                context = {"client": self, "message": self._DEL_MESSAGE}
                _grl().call_exception_handler(context)
            except RuntimeError:
                pass

    async def on_connect(self, connection: Connection) -> None:
        await connection.on_connect()

        await connection.send_command("READONLY")
        if str_if_bytes(await connection.read_response()) != "OK":
            raise ConnectionError("READONLY command failed")

    def get_nodes(self) -> List["ClusterNode"]:
        """Get all nodes of the cluster."""
        return list(self.nodes_manager.nodes_cache.values())

    def get_primaries(self) -> List["ClusterNode"]:
        """Get the primary nodes of the cluster."""
        return self.nodes_manager.get_nodes_by_server_type(PRIMARY)

    def get_replicas(self) -> List["ClusterNode"]:
        """Get the replica nodes of the cluster."""
        return self.nodes_manager.get_nodes_by_server_type(REPLICA)

    def get_random_node(self) -> "ClusterNode":
        """Get a random node of the cluster."""
        return random.choice(list(self.nodes_manager.nodes_cache.values()))

    def get_default_node(self) -> "ClusterNode":
        """Get the default node of the client."""
        return self.nodes_manager.default_node

    def set_default_node(self, node: "ClusterNode") -> None:
        """
        Set the default node of the client.

        :raises DataError: if None is passed or node does not exist in cluster.
        """
        if not node or not self.get_node(node_name=node.name):
            raise DataError("The requested node does not exist in the cluster.")

        self.nodes_manager.default_node = node

    def get_node(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        node_name: Optional[str] = None,
    ) -> Optional["ClusterNode"]:
        """Get node by (host, port) or node_name."""
        return self.nodes_manager.get_node(host, port, node_name)

    def get_node_from_key(
        self, key: str, replica: bool = False
    ) -> Optional["ClusterNode"]:
        """
        Get the cluster node corresponding to the provided key.

        :param key:
        :param replica:
            | Indicates if a replica should be returned
            |
              None will returned if no replica holds this key

        :raises SlotNotCoveredError: if the key is not covered by any slot.
        """
        slot = self.keyslot(key)
        slot_cache = self.nodes_manager.slots_cache.get(slot)
        if not slot_cache:
            raise SlotNotCoveredError(f'Slot "{slot}" is not covered by the cluster.')

        if replica:
            if len(self.nodes_manager.slots_cache[slot]) < 2:
                return None
            node_idx = 1
        else:
            node_idx = 0

        return slot_cache[node_idx]

    def get_random_primary_or_all_nodes(self, command_name):
        """
        Returns random primary or all nodes depends on READONLY mode.
        """
        if self.read_from_replicas and command_name in READ_COMMANDS:
            return self.get_random_node()

        return self.get_random_primary_node()

    def get_random_primary_node(self) -> "ClusterNode":
        """
        Returns a random primary node
        """
        return random.choice(self.get_primaries())

    async def get_nodes_from_slot(self, command: str, *args):
        """
        Returns a list of nodes that hold the specified keys' slots.
        """
        return [
            self.nodes_manager.get_node_from_slot(
                await self._determine_slot(command, *args),
                self.read_from_replicas and command in READ_COMMANDS,
                self.load_balancing_strategy if command in READ_COMMANDS else None,
            )
        ]

    def get_special_nodes(self) -> Optional[list["ClusterNode"]]:
        """
        Returns a list of nodes for commands with a special policy.
        """
        if not self._aggregate_nodes:
            raise RedisClusterException(
                "Cannot execute FT.CURSOR commands without FT.AGGREGATE"
            )

        return self._aggregate_nodes

    def keyslot(self, key: EncodableT) -> int:
        """
        Find the keyslot for a given key.

        See: https://redis.io/docs/manual/scaling/#redis-cluster-data-sharding
        """
        return key_slot(self.encoder.encode(key))

    def get_encoder(self) -> Encoder:
        """Get the encoder object of the client."""
        return self.encoder

    def get_connection_kwargs(self) -> Dict[str, Optional[Any]]:
        """Get the kwargs passed to :class:`~redis.asyncio.connection.Connection`."""
        return self.connection_kwargs

    def set_retry(self, retry: Retry) -> None:
        self.retry = retry

    def set_response_callback(self, command: str, callback: ResponseCallbackT) -> None:
        """Set a custom response callback."""
        self.response_callbacks[command] = callback

    async def _determine_nodes(
        self,
        command: str,
        *args: Any,
        request_policy: RequestPolicy,
        node_flag: Optional[str] = None,
    ) -> List["ClusterNode"]:
        if not node_flag:
            node_flag = self.command_flags.get(command)

        if node_flag in self._command_flags_mapping:
            request_policy = self._command_flags_mapping[node_flag]

        policy_callback = self._policies_callback_mapping[request_policy]

        if request_policy == RequestPolicy.DEFAULT_KEYED:
            nodes = await policy_callback(command, *args)
        elif request_policy == RequestPolicy.DEFAULT_KEYLESS:
            nodes = policy_callback(command)
        else:
            nodes = policy_callback()

        if command.lower() == "ft.aggregate":
            self._aggregate_nodes = nodes

        return nodes

    async def _determine_slot(self, command: str, *args: Any) -> int:
        if self.command_flags.get(command) == SLOT_ID:
            return int(args[0])


        if command.upper() in ("EVAL", "EVALSHA"):
            if len(args) < 2:
                raise RedisClusterException(
                    f"Invalid args in command: {command, *args}"
                )
            keys = args[2 : 2 + int(args[1])]
            if not keys:
                return random.randrange(0, REDIS_CLUSTER_HASH_SLOTS)
        else:
            keys = await self.commands_parser.get_keys(command, *args)
            if not keys:
                if command.upper() in ("FCALL", "FCALL_RO"):
                    return random.randrange(0, REDIS_CLUSTER_HASH_SLOTS)
                raise RedisClusterException(
                    "No way to dispatch this command to Redis Cluster. "
                    "Missing key.\nYou can execute the command by specifying "
                    f"target nodes.\nCommand: {args}"
                )

        if len(keys) == 1:
            return self.keyslot(keys[0])

        slots = {self.keyslot(key) for key in keys}
        if len(slots) != 1:
            raise RedisClusterException(
                f"{command} - all keys must map to the same key slot"
            )

        return slots.pop()

    def _is_node_flag(self, target_nodes: Any) -> bool:
        return isinstance(target_nodes, str) and target_nodes in self.node_flags

    def _parse_target_nodes(self, target_nodes: Any) -> List["ClusterNode"]:
        if isinstance(target_nodes, list):
            nodes = target_nodes
        elif isinstance(target_nodes, ClusterNode):
            nodes = [target_nodes]
        elif isinstance(target_nodes, dict):
            nodes = list(target_nodes.values())
        else:
            raise TypeError(
                "target_nodes type can be one of the following: "
                "node_flag (PRIMARIES, REPLICAS, RANDOM, ALL_NODES),"
                "ClusterNode, list<ClusterNode>, or dict<any, ClusterNode>. "
                f"The passed type is {type(target_nodes)}"
            )
        return nodes

    async def _record_error_metric(
        self,
        error: Exception,
        connection: Union[Connection, "ClusterNode"],
        is_internal: bool = True,
        retry_attempts: Optional[int] = None,
    ):
        """
        Records error count metric directly.
        Accepts either a Connection or ClusterNode object.
        """
        await record_error_count(
            server_address=connection.host,
            server_port=connection.port,
            network_peer_address=connection.host,
            network_peer_port=connection.port,
            error_type=error,
            retry_attempts=retry_attempts if retry_attempts is not None else 0,
            is_internal=is_internal,
        )

    async def _record_command_metric(
        self,
        command_name: str,
        duration_seconds: float,
        connection: Union[Connection, "ClusterNode"],
        error: Optional[Exception] = None,
    ):
        """
        Records operation duration metric directly.
        Accepts either a Connection or ClusterNode object.
        """
        if hasattr(connection, "db"):
            db = connection.db
        else:
            db = connection.connection_kwargs.get("db", 0)
        await record_operation_duration(
            command_name=command_name,
            duration_seconds=duration_seconds,
            server_address=connection.host,
            server_port=connection.port,
            db_namespace=str(db) if db is not None else None,
            error=error,
        )

    async def execute_command(self, *args: EncodableT, **kwargs: Any) -> Any:
        """
        Execute a raw command on the appropriate cluster node or target_nodes.

        It will retry the command as specified by the retries property of
        the :attr:`retry` & then raise an exception.

        :param args:
            | Raw command args
        :param kwargs:

            - target_nodes: :attr:`NODE_FLAGS` or :class:`~.ClusterNode`
              or List[:class:`~.ClusterNode`] or Dict[Any, :class:`~.ClusterNode`]
            - Rest of the kwargs are passed to the Redis connection

        :raises RedisClusterException: if target_nodes is not provided & the command
            can't be mapped to a slot
        """
        command = args[0]
        target_nodes = []
        target_nodes_specified = False
        retry_attempts = self.retry.get_retries()

        passed_targets = kwargs.pop("target_nodes", None)
        if passed_targets and not self._is_node_flag(passed_targets):
            target_nodes = self._parse_target_nodes(passed_targets)
            target_nodes_specified = True
            retry_attempts = 0

        command_policies = await self._policy_resolver.resolve(args[0].lower())

        if not command_policies and not target_nodes_specified:
            command_flag = self.command_flags.get(command)
            if not command_flag:
                if not self.get_default_node():
                    slot = None
                else:
                    slot = await self._determine_slot(*args)
                if slot is None:
                    command_policies = CommandPolicies()
                else:
                    command_policies = CommandPolicies(
                        request_policy=RequestPolicy.DEFAULT_KEYED,
                        response_policy=ResponsePolicy.DEFAULT_KEYED,
                    )
            else:
                if command_flag in self._command_flags_mapping:
                    command_policies = CommandPolicies(
                        request_policy=self._command_flags_mapping[command_flag]
                    )
                else:
                    command_policies = CommandPolicies()
        elif not command_policies and target_nodes_specified:
            command_policies = CommandPolicies()

        execute_attempts = 1 + retry_attempts
        failure_count = 0

        start_time = time.monotonic()
        last_failed_node_name = None

        for _ in range(execute_attempts):
            if self._initialize:
                await self.initialize(last_failed_node_name=last_failed_node_name)
                last_failed_node_name = None
                if (
                    len(target_nodes) == 1
                    and target_nodes[0] == self.get_default_node()
                ):
                    self.replace_default_node()
            try:
                if not target_nodes_specified:
                    target_nodes = await self._determine_nodes(
                        *args,
                        request_policy=command_policies.request_policy,
                        node_flag=passed_targets,
                    )
                    if not target_nodes:
                        raise RedisClusterException(
                            f"No targets were found to execute {args} command on"
                        )

                if len(target_nodes) == 1:
                    ret = await self._execute_command(target_nodes[0], *args, **kwargs)
                    if command in self.result_callbacks:
                        ret = self.result_callbacks[command](
                            command, {target_nodes[0].name: ret}, **kwargs
                        )
                    return self._policies_callback_mapping[
                        command_policies.response_policy
                    ](ret)
                else:
                    keys = [node.name for node in target_nodes]
                    values = await asyncio.gather(
                        *(
                            asyncio.create_task(
                                self._execute_command(node, *args, **kwargs)
                            )
                            for node in target_nodes
                        )
                    )
                    if command in self.result_callbacks:
                        return self.result_callbacks[command](
                            command, dict(zip(keys, values)), **kwargs
                        )
                    return self._policies_callback_mapping[
                        command_policies.response_policy
                    ](dict(zip(keys, values)))
            except Exception as e:
                if retry_attempts > 0 and type(e) in self.__class__.ERRORS_ALLOW_RETRY:
                    retry_attempts -= 1
                    failure_count += 1
                    last_failed_node_name = getattr(e, "last_failed_node_name", None)

                    if hasattr(e, "connection"):
                        await self._record_command_metric(
                            command_name=command,
                            duration_seconds=time.monotonic() - start_time,
                            connection=e.connection,
                            error=e,
                        )
                        await self._record_error_metric(
                            error=e,
                            connection=e.connection,
                            retry_attempts=failure_count,
                        )
                    continue
                else:
                    if hasattr(e, "connection"):
                        await self._record_error_metric(
                            error=e,
                            connection=e.connection,
                            retry_attempts=failure_count,
                            is_internal=False,
                        )
                    raise e

    async def _execute_command(
        self, target_node: "ClusterNode", *args: Union[KeyT, EncodableT], **kwargs: Any
    ) -> Any:
        asking = moved = False
        redirect_addr = None
        ttl = self.RedisClusterRequestTTL
        command = args[0]
        start_time = time.monotonic()

        while ttl > 0:
            ttl -= 1
            try:
                if asking:
                    target_node = self.get_node(node_name=redirect_addr)
                    await target_node.execute_command("ASKING")
                    asking = False
                elif moved:
                    slot = await self._determine_slot(*args)
                    target_node = self.nodes_manager.get_node_from_slot(
                        slot,
                        self.read_from_replicas and args[0] in READ_COMMANDS,
                        self.load_balancing_strategy
                        if args[0] in READ_COMMANDS
                        else None,
                    )
                    moved = False

                response = await target_node.execute_command(*args, **kwargs)
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                )
                return response
            except BusyLoadingError as e:
                e.connection = target_node
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                raise
            except MaxConnectionsError as e:
                e.connection = target_node
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                raise
            except (ConnectionError, TimeoutError) as e:
                target_node.update_active_connections_for_reconnect()
                await target_node.disconnect_free_connections()

                self.nodes_manager.move_node_to_end_of_cached_nodes(target_node.name)
                e.last_failed_node_name = target_node.name

                self._initialize = True
                e.connection = target_node
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                raise
            except (ClusterDownError, SlotNotCoveredError) as e:


                await self.aclose()
                await asyncio.sleep(0.25)
                e.connection = target_node
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                raise
            except MovedError as e:
                self.reinitialize_counter += 1
                if (
                    self.reinitialize_steps
                    and self.reinitialize_counter % self.reinitialize_steps == 0
                ):
                    await self.aclose()
                    self.reinitialize_counter = 0
                else:
                    await self.nodes_manager.move_slot(e)
                moved = True
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                await self._record_error_metric(
                    error=e,
                    connection=target_node,
                )
            except AskError as e:
                redirect_addr = get_node_name(host=e.host, port=e.port)
                asking = True
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                await self._record_error_metric(
                    error=e,
                    connection=target_node,
                )
            except TryAgainError as e:
                if ttl < self.RedisClusterRequestTTL / 2:
                    await asyncio.sleep(0.05)
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                await self._record_error_metric(
                    error=e,
                    connection=target_node,
                )
            except ResponseError as e:
                e.connection = target_node
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                raise
            except Exception as e:
                e.connection = target_node
                await self._record_command_metric(
                    command_name=command,
                    duration_seconds=time.monotonic() - start_time,
                    connection=target_node,
                    error=e,
                )
                raise

        e = ClusterError("TTL exhausted.")
        e.connection = target_node
        await self._record_command_metric(
            command_name=command,
            duration_seconds=time.monotonic() - start_time,
            connection=target_node,
            error=e,
        )
        raise e

    def pipeline(
        self, transaction: Optional[Any] = None, shard_hint: Optional[Any] = None
    ) -> "ClusterPipeline":
        """
        Create & return a new :class:`~.ClusterPipeline` object.

        Cluster implementation of pipeline does not support transaction or shard_hint.

        :raises RedisClusterException: if transaction or shard_hint are truthy values
        """
        if shard_hint:
            raise RedisClusterException("shard_hint is deprecated in cluster mode")

        return ClusterPipeline(self, transaction)

    def pubsub(
        self,
        node: Optional["ClusterNode"] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        **kwargs: Any,
    ) -> "ClusterPubSub":
        """
        Create and return a ClusterPubSub instance.

        Allows passing a ClusterNode, or host&port, to get a pubsub instance
        connected to the specified node

        :param node: ClusterNode to connect to
        :param host: Host of the node to connect to
        :param port: Port of the node to connect to
        :param kwargs: Additional keyword arguments
        :return: ClusterPubSub instance
        """
        return ClusterPubSub(self, node=node, host=host, port=port, **kwargs)

    def keyspace_notifications(
        self,
        key_prefix: Union[str, bytes, None] = None,
        ignore_subscribe_messages: bool = True,
    ) -> "AsyncClusterKeyspaceNotifications":
        """
        Return an
        :class:`~redis.asyncio.keyspace_notifications.AsyncClusterKeyspaceNotifications`
        object for subscribing to keyspace and keyevent notifications across
        all primary nodes in the cluster.

        Note: Keyspace notifications must be enabled on all Redis cluster nodes
        via the ``notify-keyspace-events`` configuration option.

        Args:
            key_prefix: Optional prefix to filter and strip from keys in
                        notifications.
            ignore_subscribe_messages: If True, subscribe/unsubscribe
                                      confirmations are not returned by
                                      get_message/listen.
        """
        from redis.asyncio.keyspace_notifications import (
            AsyncClusterKeyspaceNotifications,
        )

        return AsyncClusterKeyspaceNotifications(
            self,
            key_prefix=key_prefix,
            ignore_subscribe_messages=ignore_subscribe_messages,
        )

    def lock(
        self,
        name: KeyT,
        timeout: Optional[float] = None,
        sleep: float = 0.1,
        blocking: bool = True,
        blocking_timeout: Optional[float] = None,
        lock_class: Optional[Type[Lock]] = None,
        thread_local: bool = True,
        raise_on_release_error: bool = True,
    ) -> Lock:
        """
        Return a new Lock object using key ``name`` that mimics
        the behavior of threading.Lock.

        If specified, ``timeout`` indicates a maximum life for the lock.
        By default, it will remain locked until release() is called.

        ``sleep`` indicates the amount of time to sleep per loop iteration
        when the lock is in blocking mode and another client is currently
        holding the lock.

        ``blocking`` indicates whether calling ``acquire`` should block until
        the lock has been acquired or to fail immediately, causing ``acquire``
        to return False and the lock not being acquired. Defaults to True.
        Note this value can be overridden by passing a ``blocking``
        argument to ``acquire``.

        ``blocking_timeout`` indicates the maximum amount of time in seconds to
        spend trying to acquire the lock. A value of ``None`` indicates
        continue trying forever. ``blocking_timeout`` can be specified as a
        float or integer, both representing the number of seconds to wait.

        ``lock_class`` forces the specified lock implementation. Note that as
        of redis-py 3.0, the only lock class we implement is ``Lock`` (which is
        a Lua-based lock). So, it's unlikely you'll need this parameter, unless
        you have created your own custom lock class.

        ``thread_local`` indicates whether the lock token is placed in
        thread-local storage. By default, the token is placed in thread local
        storage so that a thread only sees its token, not a token set by
        another thread. Consider the following timeline:

            time: 0, thread-1 acquires `my-lock`, with a timeout of 5 seconds.
                     thread-1 sets the token to "abc"
            time: 1, thread-2 blocks trying to acquire `my-lock` using the
                     Lock instance.
            time: 5, thread-1 has not yet completed. redis expires the lock
                     key.
            time: 5, thread-2 acquired `my-lock` now that it's available.
                     thread-2 sets the token to "xyz"
            time: 6, thread-1 finishes its work and calls release(). if the
                     token is *not* stored in thread local storage, then
                     thread-1 would see the token value as "xyz" and would be
                     able to successfully release the thread-2's lock.

        ``raise_on_release_error`` indicates whether to raise an exception when
        the lock is no longer owned when exiting the context manager. By default,
        this is True, meaning an exception will be raised. If False, the warning
        will be logged and the exception will be suppressed.

        In some use cases it's necessary to disable thread local storage. For
        example, if you have code where one thread acquires a lock and passes
        that lock instance to a worker thread to release later. If thread
        local storage isn't disabled in this case, the worker thread won't see
        the token set by the thread that acquired the lock. Our assumption
        is that these cases aren't common and as such default to using
        thread local storage."""
        if lock_class is None:
            lock_class = Lock
        return lock_class(
            self,
            name,
            timeout=timeout,
            sleep=sleep,
            blocking=blocking,
            blocking_timeout=blocking_timeout,
            thread_local=thread_local,
            raise_on_release_error=raise_on_release_error,
        )

    async def transaction(
        self, func: Coroutine[None, "ClusterPipeline", Any], *watches, **kwargs
    ):
        """
        Convenience method for executing the callable `func` as a transaction
        while watching all keys specified in `watches`. The 'func' callable
        should expect a single argument which is a Pipeline object.
        """
        shard_hint = kwargs.pop("shard_hint", None)
        value_from_callable = kwargs.pop("value_from_callable", False)
        watch_delay = kwargs.pop("watch_delay", None)
        async with self.pipeline(True, shard_hint) as pipe:
            while True:
                try:
                    if watches:
                        await pipe.watch(*watches)
                    func_value = await func(pipe)
                    exec_value = await pipe.execute()
                    return func_value if value_from_callable else exec_value
                except WatchError:
                    if watch_delay is not None and watch_delay > 0:
                        time.sleep(watch_delay)
                    continue


class ClusterNode:
    """
    Create a new ClusterNode.

    Each ClusterNode manages multiple :class:`~redis.asyncio.connection.Connection`
    objects for the (host, port).
    """

    __slots__ = (
        "_background_tasks",
        "_connections",
        "_free",
        "_lock",
        "_event_dispatcher",
        "connection_class",
        "connection_kwargs",
        "host",
        "max_connections",
        "name",
        "port",
        "response_callbacks",
        "server_type",
    )

    def __init__(
        self,
        host: str,
        port: Union[str, int],
        server_type: Optional[str] = None,
        *,
        max_connections: int = 100,
        connection_class: Type[Connection] = Connection,
        **connection_kwargs: Any,
    ) -> None:
        if host == "localhost":
            host = socket.gethostbyname(host)

        connection_kwargs["host"] = host
        connection_kwargs["port"] = port
        self.host = host
        self.port = port
        self.name = get_node_name(host, port)
        self.server_type = server_type

        self.max_connections = max_connections
        self.connection_class = connection_class
        self.connection_kwargs = connection_kwargs
        self.response_callbacks = connection_kwargs.pop("response_callbacks", {})

        self._connections: List[Connection] = []
        self._free: Deque[Connection] = collections.deque(maxlen=self.max_connections)
        self._background_tasks: Set[asyncio.Task] = set()
        self._event_dispatcher = self.connection_kwargs.get("event_dispatcher", None)
        if self._event_dispatcher is None:
            self._event_dispatcher = EventDispatcher()

    def __repr__(self) -> str:
        return (
            f"[host={self.host}, port={self.port}, "
            f"name={self.name}, server_type={self.server_type}]"
        )

    def __eq__(self, obj: Any) -> bool:
        return isinstance(obj, ClusterNode) and obj.name == self.name

    def __hash__(self) -> int:
        return hash(self.name)

    _DEL_MESSAGE = "Unclosed ClusterNode object"

    def __del__(
        self,
        _warn: Any = warnings.warn,
        _grl: Any = asyncio.get_running_loop,
    ) -> None:
        for connection in self._connections:
            if connection.is_connected:
                _warn(f"{self._DEL_MESSAGE} {self!r}", ResourceWarning, source=self)

                try:
                    context = {"client": self, "message": self._DEL_MESSAGE}
                    _grl().call_exception_handler(context)
                except RuntimeError:
                    pass
                break

    async def disconnect(self) -> None:
        ret = await asyncio.gather(
            *(
                asyncio.create_task(connection.disconnect())
                for connection in self._connections
            ),
            return_exceptions=True,
        )
        exc = next((res for res in ret if isinstance(res, Exception)), None)
        if exc:
            raise exc

    def acquire_connection(self) -> Connection:
        try:
            return self._free.popleft()
        except IndexError:
            if len(self._connections) < self.max_connections:
                retry = Retry(
                    backoff=NoBackoff(),
                    retries=0,
                    supported_errors=(ConnectionError,),
                )
                connection_kwargs = self.connection_kwargs.copy()
                connection_kwargs["retry"] = retry
                connection = self.connection_class(**connection_kwargs)
                self._connections.append(connection)
                return connection

            raise MaxConnectionsError()

    async def disconnect_if_needed(self, connection: Connection) -> None:
        """
        Disconnect a connection if it's marked for reconnect.
        This implements lazy disconnection to avoid race conditions.
        The connection will auto-reconnect on next use.
        """
        if connection.should_reconnect():
            await connection.disconnect()

    def release(self, connection: Connection) -> None:
        """
        Release connection back to free queue.
        If the connection is marked for reconnect, disconnect it before
        returning it to the free queue.
        """
        if connection.should_reconnect():
            task = asyncio.create_task(self._disconnect_and_release(connection))
            self._background_tasks.add(task)
            task.add_done_callback(self._background_tasks.discard)
            return
        self._free.append(connection)

    async def _disconnect_and_release(self, connection: Connection) -> None:
        try:
            await connection.disconnect()
        except Exception as exc:
            logger.debug(
                "disconnecting released cluster connection failed: %r",
                exc,
                exc_info=True,
            )
            try:
                self._connections.remove(connection)
            except ValueError:
                pass
            return

        self._free.append(connection)

    def get_encoder(self) -> Encoder:
        """Return an :class:`Encoder` derived from this node's connection kwargs."""
        kwargs = self.connection_kwargs
        encoder_class = kwargs.get("encoder_class", Encoder)
        return encoder_class(
            encoding=kwargs.get("encoding", "utf-8"),
            encoding_errors=kwargs.get("encoding_errors", "strict"),
            decode_responses=kwargs.get("decode_responses", False),
        )

    def update_active_connections_for_reconnect(self) -> None:
        """
        Mark all in-use (active) connections for reconnect.
        In-use connections are those in _connections but not currently in _free.
        They will be disconnected after their current operation completes.
        """
        free_set = set(self._free)
        for connection in self._connections:
            if connection not in free_set:
                connection.mark_for_reconnect()

    async def disconnect_free_connections(self) -> None:
        """
        Disconnect all free/idle connections in the pool.
        This is useful after topology changes (e.g., failover) to clear
        stale connection state like READONLY mode.
        The connections remain in the pool and will reconnect on next use.
        """
        if self._free:
            await asyncio.gather(
                *(connection.disconnect() for connection in tuple(self._free)),
                return_exceptions=True,
            )

    async def parse_response(
        self, connection: Connection, command: str, **kwargs: Any
    ) -> Any:
        try:
            if NEVER_DECODE in kwargs:
                response = await connection.read_response(disable_decoding=True)
                kwargs.pop(NEVER_DECODE)
            else:
                response = await connection.read_response()
        except ResponseError:
            if EMPTY_RESPONSE in kwargs:
                return kwargs[EMPTY_RESPONSE]
            raise

        if EMPTY_RESPONSE in kwargs:
            kwargs.pop(EMPTY_RESPONSE)

        kwargs.pop("keys", None)

        if command in self.response_callbacks:
            return self.response_callbacks[command](response, **kwargs)

        return response

    async def execute_command(self, *args: Any, **kwargs: Any) -> Any:
        connection = self.acquire_connection()
        try:
            await self.disconnect_if_needed(connection)

            await connection.send_packed_command(connection.pack_command(*args))

            return await self.parse_response(connection, args[0], **kwargs)
        finally:
            try:
                await self.disconnect_if_needed(connection)
            finally:
                self.release(connection)

    async def execute_pipeline(self, commands: List["PipelineCommand"]) -> bool:
        connection = self.acquire_connection()
        try:
            await self.disconnect_if_needed(connection)

            await connection.send_packed_command(
                connection.pack_commands(cmd.args for cmd in commands)
            )

            ret = False
            for cmd in commands:
                try:
                    cmd.result = await self.parse_response(
                        connection, cmd.args[0], **cmd.kwargs
                    )
                except Exception as e:
                    cmd.result = e
                    ret = True

            return ret
        finally:
            try:
                await self.disconnect_if_needed(connection)
            finally:
                self.release(connection)

    async def re_auth_callback(self, token: TokenInterface):
        tmp_queue = collections.deque()
        while self._free:
            conn = self._free.popleft()
            await conn.retry.call_with_retry(
                lambda: conn.send_command(
                    "AUTH", token.try_get("oid"), token.get_value()
                ),
                lambda error: self._mock(error),
            )
            await conn.retry.call_with_retry(
                lambda: conn.read_response(), lambda error: self._mock(error)
            )
            tmp_queue.append(conn)

        while tmp_queue:
            conn = tmp_queue.popleft()
            self._free.append(conn)

    async def _mock(self, error: RedisError):
        """
        Dummy functions, needs to be passed as error callback to retry object.
        :param error:
        :return:
        """
        pass


class NodesManager:
    __slots__ = (
        "_dynamic_startup_nodes",
        "_event_dispatcher",
        "_background_tasks",
        "connection_kwargs",
        "default_node",
        "nodes_cache",
        "_epoch",
        "read_load_balancer",
        "_initialize_lock",
        "require_full_coverage",
        "slots_cache",
        "startup_nodes",
        "address_remap",
    )

    def __init__(
        self,
        startup_nodes: List["ClusterNode"],
        require_full_coverage: bool,
        connection_kwargs: Dict[str, Any],
        dynamic_startup_nodes: bool = True,
        address_remap: Optional[Callable[[Tuple[str, int]], Tuple[str, int]]] = None,
        event_dispatcher: Optional[EventDispatcher] = None,
    ) -> None:
        self.startup_nodes = {node.name: node for node in startup_nodes}
        self.require_full_coverage = require_full_coverage
        self.connection_kwargs = connection_kwargs
        self.address_remap = address_remap

        self.default_node: "ClusterNode" = None
        self.nodes_cache: Dict[str, "ClusterNode"] = {}
        self.slots_cache: Dict[int, List["ClusterNode"]] = {}
        self._epoch: int = 0
        self.read_load_balancer = LoadBalancer()
        self._initialize_lock: asyncio.Lock = asyncio.Lock()

        self._background_tasks: Set[asyncio.Task] = set()
        self._dynamic_startup_nodes: bool = dynamic_startup_nodes
        if event_dispatcher is None:
            self._event_dispatcher = EventDispatcher()
        else:
            self._event_dispatcher = event_dispatcher

    def get_node(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        node_name: Optional[str] = None,
    ) -> Optional["ClusterNode"]:
        if host and port:
            if host == "localhost":
                host = socket.gethostbyname(host)
            return self.nodes_cache.get(get_node_name(host=host, port=port))
        elif node_name:
            return self.nodes_cache.get(node_name)
        else:
            raise DataError(
                "get_node requires one of the following: 1. node name 2. host and port"
            )

    def set_nodes(
        self,
        old: Dict[str, "ClusterNode"],
        new: Dict[str, "ClusterNode"],
        remove_old: bool = False,
    ) -> None:
        if remove_old:
            for name in list(old.keys()):
                if name not in new:
                    removed_node = old.pop(name)
                    removed_node.update_active_connections_for_reconnect()
                    task = asyncio.create_task(
                        removed_node.disconnect_free_connections()
                    )
                    self._background_tasks.add(task)
                    task.add_done_callback(self._background_tasks.discard)

        for name, node in new.items():
            if name in old:
                existing_node = old[name]
                existing_node.server_type = node.server_type
                existing_node.update_active_connections_for_reconnect()
                for conn in existing_node._free:
                    conn.mark_for_reconnect()
                continue
            old[name] = node

    def move_node_to_end_of_cached_nodes(self, node_name: str) -> None:
        """
        Move a failing node to the end of startup_nodes and nodes_cache so it's
        tried last during reinitialization and when selecting the default node.
        If the node is not in the respective list, nothing is done.
        """
        if node_name in self.startup_nodes and len(self.startup_nodes) > 1:
            node = self.startup_nodes.pop(node_name)
            self.startup_nodes[node_name] = node 

        if node_name in self.nodes_cache and len(self.nodes_cache) > 1:
            node = self.nodes_cache.pop(node_name)
            self.nodes_cache[node_name] = node 

    async def move_slot(self, e: AskError | MovedError):
        node_changed = False
        redirected_node = self.get_node(host=e.host, port=e.port)
        if redirected_node:
            if redirected_node.server_type != PRIMARY:
                redirected_node.server_type = PRIMARY
        else:
            redirected_node = ClusterNode(
                e.host, e.port, PRIMARY, **self.connection_kwargs
            )
            self.set_nodes(self.nodes_cache, {redirected_node.name: redirected_node})
        slot_nodes = self.slots_cache[e.slot_id]
        if redirected_node not in slot_nodes:
            self.slots_cache[e.slot_id] = [redirected_node]
            node_changed = True
        elif redirected_node is not slot_nodes[0]:
            old_primary = slot_nodes[0]
            old_primary.server_type = REPLICA
            slot_nodes.append(old_primary)
            slot_nodes.remove(redirected_node)
            slot_nodes[0] = redirected_node
            if self.default_node == old_primary:
                self.default_node = redirected_node
            node_changed = True
        if node_changed:
            try:
                await self._event_dispatcher.dispatch_async(
                    AsyncAfterSlotsCacheRefreshEvent()
                )
            except Exception as exc:
                logger.exception(
                    "listener raised during slots-cache refresh: %s: %s",
                    type(exc).__name__,
                    exc,
                )

    def get_node_from_slot(
        self,
        slot: int,
        read_from_replicas: bool = False,
        load_balancing_strategy=None,
    ) -> "ClusterNode":
        if read_from_replicas is True and load_balancing_strategy is None:
            load_balancing_strategy = LoadBalancingStrategy.ROUND_ROBIN

        try:
            if len(self.slots_cache[slot]) > 1 and load_balancing_strategy:
                primary_name = self.slots_cache[slot][0].name
                node_idx = self.read_load_balancer.get_server_index(
                    primary_name, len(self.slots_cache[slot]), load_balancing_strategy
                )
                return self.slots_cache[slot][node_idx]
            return self.slots_cache[slot][0]
        except (IndexError, TypeError):
            raise SlotNotCoveredError(
                f'Slot "{slot}" not covered by the cluster. '
                f'"require_full_coverage={self.require_full_coverage}"'
            )

    def get_nodes_by_server_type(self, server_type: str) -> List["ClusterNode"]:
        return [
            node
            for node in self.nodes_cache.values()
            if node.server_type == server_type
        ]

    async def initialize(
        self,
        additional_startup_nodes_info: Optional[List[Tuple[str, int]]] = None,
        last_failed_node_name: Optional[str] = None,
    ) -> None:
        self.read_load_balancer.reset()
        tmp_nodes_cache: Dict[str, "ClusterNode"] = {}
        tmp_slots: Dict[int, List["ClusterNode"]] = {}
        disagreements = []
        startup_nodes_reachable = False
        fully_covered = False
        exception = None
        epoch = self._epoch
        if additional_startup_nodes_info is None:
            additional_startup_nodes_info = []

        async with self._initialize_lock:
            if self._epoch != epoch:
                return

            startup_nodes = list(self.startup_nodes.values())
            deferred_failed_nodes = []
            if last_failed_node_name is not None:
                for index, node in enumerate(startup_nodes):
                    if node.name == last_failed_node_name:
                        deferred_failed_nodes.append(startup_nodes.pop(index))
                        break
            if len(startup_nodes) > 1:
                random.shuffle(startup_nodes)
            additional_startup_nodes = [
                ClusterNode(host, port, **self.connection_kwargs)
                for host, port in additional_startup_nodes_info
            ]
            if last_failed_node_name is not None:
                for index, node in enumerate(additional_startup_nodes):
                    if node.name == last_failed_node_name:
                        if not deferred_failed_nodes:
                            deferred_failed_nodes.append(node)
                        additional_startup_nodes.pop(index)
                        break
            for startup_node in chain(
                startup_nodes,
                additional_startup_nodes,
                deferred_failed_nodes,
            ):
                try:
                    try:
                        self._event_dispatcher.dispatch(
                            AfterAsyncClusterInstantiationEvent(
                                self.nodes_cache,
                                self.connection_kwargs.get("credential_provider", None),
                            )
                        )
                        cluster_slots = await startup_node.execute_command(
                            "CLUSTER SLOTS"
                        )
                    except ResponseError:
                        raise RedisClusterException(
                            "Cluster mode is not enabled on this node"
                        )
                    startup_nodes_reachable = True
                except Exception as e:
                    exception = e
                    continue

                if (
                    len(cluster_slots) == 1
                    and not cluster_slots[0][2][0]
                    and len(self.startup_nodes) == 1
                ):
                    cluster_slots[0][2][0] = startup_node.host

                for slot in cluster_slots:
                    for i in range(2, len(slot)):
                        slot[i] = [str_if_bytes(val) for val in slot[i]]
                    primary_node = slot[2]
                    host = primary_node[0]
                    if host == "":
                        host = startup_node.host
                    port = int(primary_node[1])
                    host, port = self.remap_host_port(host, port)

                    nodes_for_slot = []

                    target_node = tmp_nodes_cache.get(get_node_name(host, port))
                    if not target_node:
                        target_node = ClusterNode(
                            host, port, PRIMARY, **self.connection_kwargs
                        )
                    tmp_nodes_cache[target_node.name] = target_node
                    nodes_for_slot.append(target_node)

                    replica_nodes = slot[3:]
                    for replica_node in replica_nodes:
                        host = replica_node[0]
                        port = replica_node[1]
                        host, port = self.remap_host_port(host, port)

                        target_replica_node = tmp_nodes_cache.get(
                            get_node_name(host, port)
                        )
                        if not target_replica_node:
                            target_replica_node = ClusterNode(
                                host, port, REPLICA, **self.connection_kwargs
                            )
                        tmp_nodes_cache[target_replica_node.name] = target_replica_node
                        nodes_for_slot.append(target_replica_node)

                    for i in range(int(slot[0]), int(slot[1]) + 1):
                        if i not in tmp_slots:
                            tmp_slots[i] = nodes_for_slot
                        else:
                            tmp_slot = tmp_slots[i][0]
                            if tmp_slot.name != target_node.name:
                                disagreements.append(
                                    f"{tmp_slot.name} vs {target_node.name} on slot: {i}"
                                )

                                if len(disagreements) > 5:
                                    raise RedisClusterException(
                                        f"startup_nodes could not agree on a valid "
                                        f"slots cache: {', '.join(disagreements)}"
                                    )

                fully_covered = True
                for i in range(REDIS_CLUSTER_HASH_SLOTS):
                    if i not in tmp_slots:
                        fully_covered = False
                        break
                if fully_covered:
                    break

            if not startup_nodes_reachable:
                raise RedisClusterException(
                    f"Redis Cluster cannot be connected. Please provide at least "
                    f"one reachable node: {str(exception)}"
                ) from exception

            if not fully_covered and self.require_full_coverage:
                raise RedisClusterException(
                    f"All slots are not covered after query all startup_nodes. "
                    f"{len(tmp_slots)} of {REDIS_CLUSTER_HASH_SLOTS} "
                    f"covered..."
                )

            self.set_nodes(self.nodes_cache, tmp_nodes_cache, remove_old=True)
            node_lists_by_id: Dict[int, List["ClusterNode"]] = {}
            new_slots_cache: Dict[int, List["ClusterNode"]] = {}
            for slot, nodes in tmp_slots.items():
                node_list_id = id(nodes)
                slot_nodes = node_lists_by_id.get(node_list_id)
                if slot_nodes is None:
                    slot_nodes = [self.nodes_cache[node.name] for node in nodes]
                    node_lists_by_id[node_list_id] = slot_nodes
                new_slots_cache[slot] = slot_nodes
            self.slots_cache = new_slots_cache

            if self._dynamic_startup_nodes:
                self.set_nodes(self.startup_nodes, self.nodes_cache, remove_old=True)

            self.default_node = self.get_nodes_by_server_type(PRIMARY)[0]
            self._epoch += 1
        try:
            await self._event_dispatcher.dispatch_async(
                AsyncAfterSlotsCacheRefreshEvent()
            )
        except Exception as e:
            logger.exception(
                "listener raised during slots-cache refresh: %s: %s",
                type(e).__name__,
                e,
            )

    async def aclose(self, attr: str = "nodes_cache") -> None:
        self.default_node = None
        await asyncio.gather(
            *(
                asyncio.create_task(node.disconnect())
                for node in getattr(self, attr).values()
            )
        )

    def remap_host_port(self, host: str, port: int) -> Tuple[str, int]:
        """
        Remap the host and port returned from the cluster to a different
        internal value.  Useful if the client is not connecting directly
        to the cluster.
        """
        if self.address_remap:
            return self.address_remap((host, port))
        return host, port


class ClusterPipeline(AbstractRedis, AbstractRedisCluster, AsyncRedisClusterCommands):
    """
    Create a new ClusterPipeline object.

    Usage::

        result = await (
            rc.pipeline()
            .set("A", 1)
            .get("A")
            .hset("K", "F", "V")
            .hgetall("K")
            .mset_nonatomic({"A": 2, "B": 3})
            .get("A")
            .get("B")
            .delete("A", "B", "K")
            .execute()
        )

    Note: For commands `DELETE`, `EXISTS`, `TOUCH`, `UNLINK`, `mset_nonatomic`, which
    are split across multiple nodes, you'll get multiple results for them in the array.

    Retryable errors:
        - :class:`~.ClusterDownError`
        - :class:`~.ConnectionError`
        - :class:`~.TimeoutError`

    Redirection errors:
        - :class:`~.TryAgainError`
        - :class:`~.MovedError`
        - :class:`~.AskError`

    :param client:
        | Existing :class:`~.RedisCluster` client
    """

    __slots__ = (
        "cluster_client",
        "_transaction",
        "_execution_strategy",
    )

    _is_async_client: Literal[True] = True

    def __init__(
        self, client: RedisCluster, transaction: Optional[bool] = None
    ) -> None:
        self.cluster_client = client
        self._transaction = transaction
        self._execution_strategy: ExecutionStrategy = (
            PipelineStrategy(self)
            if not self._transaction
            else TransactionStrategy(self)
        )

    @property
    def nodes_manager(self) -> "NodesManager":
        """Get the nodes manager from the cluster client."""
        return self.cluster_client.nodes_manager

    def set_response_callback(self, command: str, callback: ResponseCallbackT) -> None:
        """Set a custom response callback on the cluster client."""
        self.cluster_client.set_response_callback(command, callback)

    async def initialize(self) -> "ClusterPipeline":
        await self._execution_strategy.initialize()
        return self

    async def __aenter__(self) -> "ClusterPipeline":
        return await self.initialize()

    async def __aexit__(self, exc_type: None, exc_value: None, traceback: None) -> None:
        await self.reset()

    def __await__(self) -> Generator[Any, None, "ClusterPipeline"]:
        return self.initialize().__await__()

    def __bool__(self) -> bool:
        "Pipeline instances should  always evaluate to True on Python 3+"
        return True

    def __len__(self) -> int:
        return len(self._execution_strategy)

    def execute_command(
        self, *args: Union[KeyT, EncodableT], **kwargs: Any
    ) -> "ClusterPipeline":
        """
        Append a raw command to the pipeline.

        :param args:
            | Raw command args
        :param kwargs:

            - target_nodes: :attr:`NODE_FLAGS` or :class:`~.ClusterNode`
              or List[:class:`~.ClusterNode`] or Dict[Any, :class:`~.ClusterNode`]
            - Rest of the kwargs are passed to the Redis connection
        """
        return self._execution_strategy.execute_command(*args, **kwargs)

    async def execute(
        self, raise_on_error: bool = True, allow_redirections: bool = True
    ) -> List[Any]:
        """
        Execute the pipeline.

        It will retry the commands as specified by retries specified in :attr:`retry`
        & then raise an exception.

        :param raise_on_error:
            | Raise the first error if there are any errors
        :param allow_redirections:
            | Whether to retry each failed command individually in case of redirection
              errors

        :raises RedisClusterException: if target_nodes is not provided & the command
            can't be mapped to a slot
        """
        try:
            return await self._execution_strategy.execute(
                raise_on_error, allow_redirections
            )
        finally:
            await self.reset()

    def _split_command_across_slots(
        self, command: str, *keys: KeyT
    ) -> "ClusterPipeline":
        for slot_keys in self.cluster_client._partition_keys_by_slot(keys).values():
            self.execute_command(command, *slot_keys)

        return self

    async def reset(self):
        """
        Reset back to empty pipeline.
        """
        await self._execution_strategy.reset()

    def multi(self):
        """
        Start a transactional block of the pipeline after WATCH commands
        are issued. End the transactional block with `execute`.
        """
        self._execution_strategy.multi()

    async def discard(self):
        """ """
        await self._execution_strategy.discard()

    async def watch(self, *names):
        """Watches the values at keys ``names``"""
        await self._execution_strategy.watch(*names)

    async def unwatch(self):
        """Unwatches all previously specified keys"""
        await self._execution_strategy.unwatch()

    async def unlink(self, *names):
        await self._execution_strategy.unlink(*names)

    def mset_nonatomic(
        self, mapping: Mapping[AnyKeyT, EncodableT]
    ) -> "ClusterPipeline":
        return self._execution_strategy.mset_nonatomic(mapping)


for command in PIPELINE_BLOCKED_COMMANDS:
    command = command.replace(" ", "_").lower()
    if command == "mset_nonatomic":
        continue

    setattr(ClusterPipeline, command, block_pipeline_command(command))


class PipelineCommand:
    def __init__(self, position: int, *args: Any, **kwargs: Any) -> None:
        self.args = args
        self.kwargs = kwargs
        self.position = position
        self.result: Union[Any, Exception] = None
        self.command_policies: Optional[CommandPolicies] = None

    def __repr__(self) -> str:
        return f"[{self.position}] {self.args} ({self.kwargs})"


class ExecutionStrategy(ABC):
    @abstractmethod
    async def initialize(self) -> "ClusterPipeline":
        """
        Initialize the execution strategy.

        See ClusterPipeline.initialize()
        """
        pass

    @abstractmethod
    def execute_command(
        self, *args: Union[KeyT, EncodableT], **kwargs: Any
    ) -> "ClusterPipeline":
        """
        Append a raw command to the pipeline.

        See ClusterPipeline.execute_command()
        """
        pass

    @abstractmethod
    async def execute(
        self, raise_on_error: bool = True, allow_redirections: bool = True
    ) -> List[Any]:
        """
        Execute the pipeline.

        It will retry the commands as specified by retries specified in :attr:`retry`
        & then raise an exception.

        See ClusterPipeline.execute()
        """
        pass

    @abstractmethod
    def mset_nonatomic(
        self, mapping: Mapping[AnyKeyT, EncodableT]
    ) -> "ClusterPipeline":
        """
        Executes multiple MSET commands according to the provided slot/pairs mapping.

        See ClusterPipeline.mset_nonatomic()
        """
        pass

    @abstractmethod
    async def reset(self):
        """
        Resets current execution strategy.

        See: ClusterPipeline.reset()
        """
        pass

    @abstractmethod
    def multi(self):
        """
        Starts transactional context.

        See: ClusterPipeline.multi()
        """
        pass

    @abstractmethod
    async def watch(self, *names):
        """
        Watch given keys.

        See: ClusterPipeline.watch()
        """
        pass

    @abstractmethod
    async def unwatch(self):
        """
        Unwatches all previously specified keys

        See: ClusterPipeline.unwatch()
        """
        pass

    @abstractmethod
    async def discard(self):
        pass

    @abstractmethod
    async def unlink(self, *names):
        """
        "Unlink a key specified by ``names``"

        See: ClusterPipeline.unlink()
        """
        pass

    @abstractmethod
    def __len__(self) -> int:
        pass


class AbstractStrategy(ExecutionStrategy):
    def __init__(self, pipe: ClusterPipeline) -> None:
        self._pipe: ClusterPipeline = pipe
        self._command_queue: List["PipelineCommand"] = []

    async def initialize(self) -> "ClusterPipeline":
        if self._pipe.cluster_client._initialize:
            await self._pipe.cluster_client.initialize()
        self._command_queue = []
        return self._pipe

    def execute_command(
        self, *args: Union[KeyT, EncodableT], **kwargs: Any
    ) -> "ClusterPipeline":
        self._command_queue.append(
            PipelineCommand(len(self._command_queue), *args, **kwargs)
        )
        return self._pipe

    def _annotate_exception(self, exception, number, command):
        """
        Provides extra context to the exception prior to it being handled
        """
        cmd = " ".join(map(safe_str, command))
        msg = (
            f"Command # {number} ({truncate_text(cmd)}) of pipeline "
            f"caused error: {exception.args[0]}"
        )
        exception.args = (msg,) + exception.args[1:]

    @abstractmethod
    def mset_nonatomic(
        self, mapping: Mapping[AnyKeyT, EncodableT]
    ) -> "ClusterPipeline":
        pass

    @abstractmethod
    async def execute(
        self, raise_on_error: bool = True, allow_redirections: bool = True
    ) -> List[Any]:
        pass

    @abstractmethod
    async def reset(self):
        pass

    @abstractmethod
    def multi(self):
        pass

    @abstractmethod
    async def watch(self, *names):
        pass

    @abstractmethod
    async def unwatch(self):
        pass

    @abstractmethod
    async def discard(self):
        pass

    @abstractmethod
    async def unlink(self, *names):
        pass

    def __len__(self) -> int:
        return len(self._command_queue)


class PipelineStrategy(AbstractStrategy):
    def __init__(self, pipe: ClusterPipeline) -> None:
        super().__init__(pipe)

    def mset_nonatomic(
        self, mapping: Mapping[AnyKeyT, EncodableT]
    ) -> "ClusterPipeline":
        encoder = self._pipe.cluster_client.encoder

        slots_pairs = {}
        for pair in mapping.items():
            slot = key_slot(encoder.encode(pair[0]))
            slots_pairs.setdefault(slot, []).extend(pair)

        for pairs in slots_pairs.values():
            self.execute_command("MSET", *pairs)

        return self._pipe

    async def execute(
        self, raise_on_error: bool = True, allow_redirections: bool = True
    ) -> List[Any]:
        if not self._command_queue:
            return []

        try:
            retry_attempts = self._pipe.cluster_client.retry.get_retries()
            while True:
                try:
                    if self._pipe.cluster_client._initialize:
                        await self._pipe.cluster_client.initialize()
                    return await self._execute(
                        self._pipe.cluster_client,
                        self._command_queue,
                        raise_on_error=raise_on_error,
                        allow_redirections=allow_redirections,
                    )

                except RedisCluster.ERRORS_ALLOW_RETRY as e:
                    if retry_attempts > 0:
                        retry_attempts -= 1
                        await self._pipe.cluster_client.aclose()
                        await asyncio.sleep(0.25)
                    else:
                        raise e
        finally:
            await self.reset()

    async def _execute(
        self,
        client: "RedisCluster",
        stack: List["PipelineCommand"],
        raise_on_error: bool = True,
        allow_redirections: bool = True,
    ) -> List[Any]:
        todo = [
            cmd for cmd in stack if not cmd.result or isinstance(cmd.result, Exception)
        ]

        nodes = {}
        for cmd in todo:
            passed_targets = cmd.kwargs.pop("target_nodes", None)
            command_policies = await client._policy_resolver.resolve(
                cmd.args[0].lower()
            )

            if passed_targets and not client._is_node_flag(passed_targets):
                target_nodes = client._parse_target_nodes(passed_targets)

                if not command_policies:
                    command_policies = CommandPolicies()
            else:
                if not command_policies:
                    command_flag = client.command_flags.get(cmd.args[0])
                    if not command_flag:
                        if not client.get_default_node():
                            slot = None
                        else:
                            slot = await client._determine_slot(*cmd.args)
                        if slot is None:
                            command_policies = CommandPolicies()
                        else:
                            command_policies = CommandPolicies(
                                request_policy=RequestPolicy.DEFAULT_KEYED,
                                response_policy=ResponsePolicy.DEFAULT_KEYED,
                            )
                    else:
                        if command_flag in client._command_flags_mapping:
                            command_policies = CommandPolicies(
                                request_policy=client._command_flags_mapping[
                                    command_flag
                                ]
                            )
                        else:
                            command_policies = CommandPolicies()

                target_nodes = await client._determine_nodes(
                    *cmd.args,
                    request_policy=command_policies.request_policy,
                    node_flag=passed_targets,
                )
                if not target_nodes:
                    raise RedisClusterException(
                        f"No targets were found to execute {cmd.args} command on"
                    )
            cmd.command_policies = command_policies
            if len(target_nodes) > 1:
                raise RedisClusterException(f"Too many targets for command {cmd.args}")
            node = target_nodes[0]
            if node.name not in nodes:
                nodes[node.name] = (node, [])
            nodes[node.name][1].append(cmd)

        start_time = time.monotonic()

        errors = await asyncio.gather(
            *(
                asyncio.create_task(node[0].execute_pipeline(node[1]))
                for node in nodes.values()
            )
        )

        for node_name, (node, commands) in nodes.items():
            node_error = None
            for cmd in commands:
                if isinstance(cmd.result, Exception):
                    node_error = cmd.result
                    break

            db = node.connection_kwargs.get("db", 0)
            await record_operation_duration(
                command_name="PIPELINE",
                duration_seconds=time.monotonic() - start_time,
                server_address=node.host,
                server_port=node.port,
                db_namespace=str(db) if db is not None else None,
                error=node_error,
            )

        if any(errors):
            if allow_redirections:
                for cmd in todo:
                    if isinstance(cmd.result, (TryAgainError, MovedError, AskError)):
                        try:
                            cmd.result = client._policies_callback_mapping[
                                cmd.command_policies.response_policy
                            ](await client.execute_command(*cmd.args, **cmd.kwargs))
                        except Exception as e:
                            cmd.result = e

            if raise_on_error:
                for cmd in todo:
                    result = cmd.result
                    if isinstance(result, Exception):
                        command = " ".join(map(safe_str, cmd.args))
                        msg = (
                            f"Command # {cmd.position + 1} "
                            f"({truncate_text(command)}) "
                            f"of pipeline caused error: {result.args}"
                        )
                        result.args = (msg,) + result.args[1:]
                        raise result

            default_cluster_node = client.get_default_node()

            if default_cluster_node is not None:
                default_node = nodes.get(default_cluster_node.name)
                if default_node is not None:
                    for cmd in default_node[1]:
                        if type(cmd.result) in RedisCluster.ERRORS_ALLOW_RETRY:
                            client.replace_default_node()
                            break

        return [cmd.result for cmd in stack]

    async def reset(self):
        """
        Reset back to empty pipeline.
        """
        self._command_queue = []

    def multi(self):
        raise RedisClusterException(
            "method multi() is not supported outside of transactional context"
        )

    async def watch(self, *names):
        raise RedisClusterException(
            "method watch() is not supported outside of transactional context"
        )

    async def unwatch(self):
        raise RedisClusterException(
            "method unwatch() is not supported outside of transactional context"
        )

    async def discard(self):
        raise RedisClusterException(
            "method discard() is not supported outside of transactional context"
        )

    async def unlink(self, *names):
        if len(names) != 1:
            raise RedisClusterException(
                "unlinking multiple keys is not implemented in pipeline command"
            )

        return self.execute_command("UNLINK", names[0])


class TransactionStrategy(AbstractStrategy):
    NO_SLOTS_COMMANDS = {"UNWATCH"}
    IMMEDIATE_EXECUTE_COMMANDS = {"WATCH", "UNWATCH"}
    UNWATCH_COMMANDS = {"DISCARD", "EXEC", "UNWATCH"}
    SLOT_REDIRECT_ERRORS = (AskError, MovedError)
    CONNECTION_ERRORS = (
        ConnectionError,
        OSError,
        ClusterDownError,
        SlotNotCoveredError,
    )

    def __init__(self, pipe: ClusterPipeline) -> None:
        super().__init__(pipe)
        self._explicit_transaction = False
        self._watching = False
        self._pipeline_slots: Set[int] = set()
        self._transaction_node: Optional[ClusterNode] = None
        self._transaction_connection: Optional[Connection] = None
        self._executing = False
        self._retry = copy(self._pipe.cluster_client.retry)
        self._retry.update_supported_errors(
            RedisCluster.ERRORS_ALLOW_RETRY + self.SLOT_REDIRECT_ERRORS
        )

    def _get_client_and_connection_for_transaction(
        self,
    ) -> Tuple[ClusterNode, Connection]:
        """
        Find a connection for a pipeline transaction.

        For running an atomic transaction, watch keys ensure that contents have not been
        altered as long as the watch commands for those keys were sent over the same
        connection. So once we start watching a key, we fetch a connection to the
        node that owns that slot and reuse it.
        """
        if not self._pipeline_slots:
            raise RedisClusterException(
                "At least a command with a key is needed to identify a node"
            )

        node: ClusterNode = self._pipe.cluster_client.nodes_manager.get_node_from_slot(
            list(self._pipeline_slots)[0], False
        )
        self._transaction_node = node

        if not self._transaction_connection:
            connection: Connection = self._transaction_node.acquire_connection()
            self._transaction_connection = connection

        return self._transaction_node, self._transaction_connection

    def execute_command(self, *args: Union[KeyT, EncodableT], **kwargs: Any) -> "Any":
        response = None
        error = None

        def runner():
            nonlocal response
            nonlocal error
            try:
                response = asyncio.run(self._execute_command(*args, **kwargs))
            except Exception as e:
                error = e

        thread = threading.Thread(target=runner)
        thread.start()
        thread.join()

        if error:
            raise error

        return response

    async def _execute_command(
        self, *args: Union[KeyT, EncodableT], **kwargs: Any
    ) -> Any:
        if self._pipe.cluster_client._initialize:
            await self._pipe.cluster_client.initialize()

        slot_number: Optional[int] = None
        if args[0] not in self.NO_SLOTS_COMMANDS:
            slot_number = await self._pipe.cluster_client._determine_slot(*args)

        if (
            self._watching or args[0] in self.IMMEDIATE_EXECUTE_COMMANDS
        ) and not self._explicit_transaction:
            if args[0] == "WATCH":
                self._validate_watch()

            if slot_number is not None:
                if self._pipeline_slots and slot_number not in self._pipeline_slots:
                    raise CrossSlotTransactionError(
                        "Cannot watch or send commands on different slots"
                    )

                self._pipeline_slots.add(slot_number)
            elif args[0] not in self.NO_SLOTS_COMMANDS:
                raise RedisClusterException(
                    f"Cannot identify slot number for command: {args[0]},"
                    "it cannot be triggered in a transaction"
                )

            return self._immediate_execute_command(*args, **kwargs)
        else:
            if slot_number is not None:
                self._pipeline_slots.add(slot_number)

            return super().execute_command(*args, **kwargs)

    def _validate_watch(self):
        if self._explicit_transaction:
            raise RedisError("Cannot issue a WATCH after a MULTI")

        self._watching = True

    async def _immediate_execute_command(self, *args, **options):
        return await self._retry.call_with_retry(
            lambda: self._get_connection_and_send_command(*args, **options),
            self._reinitialize_on_error,
            with_failure_count=True,
        )

    async def _get_connection_and_send_command(self, *args, **options):
        redis_node, connection = self._get_client_and_connection_for_transaction()
        if not self._watching:
            await redis_node.disconnect_if_needed(connection)

        start_time = time.monotonic()

        try:
            response = await self._send_command_parse_response(
                connection, redis_node, args[0], *args, **options
            )

            await record_operation_duration(
                command_name=args[0],
                duration_seconds=time.monotonic() - start_time,
                server_address=connection.host,
                server_port=connection.port,
                db_namespace=str(connection.db),
            )

            return response
        except Exception as e:
            e.connection = connection
            await record_operation_duration(
                command_name=args[0],
                duration_seconds=time.monotonic() - start_time,
                server_address=connection.host,
                server_port=connection.port,
                db_namespace=str(connection.db),
                error=e,
            )
            raise

    async def _send_command_parse_response(
        self,
        connection: Connection,
        redis_node: ClusterNode,
        command_name,
        *args,
        **options,
    ):
        """
        Send a command and parse the response
        """

        await connection.send_command(*args)
        output = await redis_node.parse_response(connection, command_name, **options)

        if command_name in self.UNWATCH_COMMANDS:
            self._watching = False
        return output

    async def _reinitialize_on_error(self, error, failure_count):
        if hasattr(error, "connection"):
            await record_error_count(
                server_address=error.connection.host,
                server_port=error.connection.port,
                network_peer_address=error.connection.host,
                network_peer_port=error.connection.port,
                error_type=error,
                retry_attempts=failure_count,
                is_internal=True,
            )

        if self._watching:
            if type(error) in self.SLOT_REDIRECT_ERRORS and self._executing:
                raise WatchError("Slot rebalancing occurred while watching keys")

        if (
            type(error) in self.SLOT_REDIRECT_ERRORS
            or type(error) in self.CONNECTION_ERRORS
        ):
            if self._transaction_connection and self._transaction_node:
                await self._transaction_connection.disconnect()
                self._transaction_node.release(self._transaction_connection)
                self._transaction_connection = None

            self._pipe.cluster_client.reinitialize_counter += 1
            if (
                self._pipe.cluster_client.reinitialize_steps
                and self._pipe.cluster_client.reinitialize_counter
                % self._pipe.cluster_client.reinitialize_steps
                == 0
            ):
                await self._pipe.cluster_client.nodes_manager.initialize()
                self.reinitialize_counter = 0
            else:
                if isinstance(error, AskError):
                    await self._pipe.cluster_client.nodes_manager.move_slot(error)

        self._executing = False

    async def _raise_first_error(self, responses, stack, start_time):
        """
        Raise the first exception on the stack
        """
        for r, cmd in zip(responses, stack):
            if isinstance(r, Exception):
                self._annotate_exception(r, cmd.position + 1, cmd.args)

                await record_operation_duration(
                    command_name="TRANSACTION",
                    duration_seconds=time.monotonic() - start_time,
                    server_address=self._transaction_connection.host,
                    server_port=self._transaction_connection.port,
                    db_namespace=str(self._transaction_connection.db),
                    error=r,
                )

                raise r

    def mset_nonatomic(
        self, mapping: Mapping[AnyKeyT, EncodableT]
    ) -> "ClusterPipeline":
        raise NotImplementedError("Method is not supported in transactional context.")

    async def execute(
        self, raise_on_error: bool = True, allow_redirections: bool = True
    ) -> List[Any]:
        stack = self._command_queue
        if not stack and (not self._watching or not self._pipeline_slots):
            return []

        return await self._execute_transaction_with_retries(stack, raise_on_error)

    async def _execute_transaction_with_retries(
        self, stack: List["PipelineCommand"], raise_on_error: bool
    ):
        return await self._retry.call_with_retry(
            lambda: self._execute_transaction(stack, raise_on_error),
            lambda error, failure_count: self._reinitialize_on_error(
                error, failure_count
            ),
            with_failure_count=True,
        )

    async def _execute_transaction(
        self, stack: List["PipelineCommand"], raise_on_error: bool
    ):
        if len(self._pipeline_slots) > 1:
            raise CrossSlotTransactionError(
                "All keys involved in a cluster transaction must map to the same slot"
            )

        self._executing = True

        redis_node, connection = self._get_client_and_connection_for_transaction()
        if not self._watching:
            await redis_node.disconnect_if_needed(connection)

        stack = chain(
            [PipelineCommand(0, "MULTI")],
            stack,
            [PipelineCommand(0, "EXEC")],
        )
        commands = [c.args for c in stack if EMPTY_RESPONSE not in c.kwargs]
        packed_commands = connection.pack_commands(commands)

        start_time = time.monotonic()

        await connection.send_packed_command(packed_commands)
        errors = []

        try:
            await redis_node.parse_response(connection, "MULTI")
        except ResponseError as e:
            self._annotate_exception(e, 0, "MULTI")
            errors.append(e)
        except self.CONNECTION_ERRORS as cluster_error:
            self._annotate_exception(cluster_error, 0, "MULTI")
            cluster_error.connection = connection
            raise

        for i, command in enumerate(self._command_queue):
            if EMPTY_RESPONSE in command.kwargs:
                errors.append((i, command.kwargs[EMPTY_RESPONSE]))
            else:
                try:
                    _ = await redis_node.parse_response(connection, "_")
                except self.SLOT_REDIRECT_ERRORS as slot_error:
                    self._annotate_exception(slot_error, i + 1, command.args)
                    errors.append(slot_error)
                except self.CONNECTION_ERRORS as cluster_error:
                    self._annotate_exception(cluster_error, i + 1, command.args)
                    cluster_error.connection = connection
                    raise
                except ResponseError as e:
                    self._annotate_exception(e, i + 1, command.args)
                    errors.append(e)

        response = None
        try:
            response = await redis_node.parse_response(connection, "EXEC")
        except ExecAbortError:
            if errors:
                raise errors[0]
            raise

        self._executing = False

        self._watching = False

        if response is None:
            raise WatchError("Watched variable changed.")

        for i, e in errors:
            response.insert(i, e)

        if len(response) != len(self._command_queue):
            raise InvalidPipelineStack(
                "Unexpected response length for cluster pipeline EXEC."
                " Command stack was {} but response had length {}".format(
                    [c.args[0] for c in self._command_queue], len(response)
                )
            )

        if raise_on_error or len(errors) > 0:
            await self._raise_first_error(
                response,
                self._command_queue,
                start_time,
            )

        data = []
        for r, cmd in zip(response, self._command_queue):
            if not isinstance(r, Exception):
                command_name = cmd.args[0]
                if command_name in self._pipe.cluster_client.response_callbacks:
                    r = self._pipe.cluster_client.response_callbacks[command_name](
                        r, **cmd.kwargs
                    )
            data.append(r)

        await record_operation_duration(
            command_name="TRANSACTION",
            duration_seconds=time.monotonic() - start_time,
            server_address=connection.host,
            server_port=connection.port,
            db_namespace=str(connection.db),
        )

        return data

    async def reset(self):
        self._command_queue = []

        try:
            if self._transaction_connection:
                try:
                    if self._watching:
                        await self._transaction_connection.send_command("UNWATCH")
                        await self._transaction_connection.read_response()
                except self.CONNECTION_ERRORS:
                    if self._transaction_connection:
                        await self._transaction_connection.disconnect()
                except asyncio.CancelledError:
                    if self._transaction_connection:
                        await self._transaction_connection.disconnect()
                    raise
                else:
                    await self._transaction_node.disconnect_if_needed(
                        self._transaction_connection
                    )
        finally:
            if self._transaction_connection and self._transaction_node:
                connection, self._transaction_connection = (
                    self._transaction_connection,
                    None,
                )
                self._transaction_node.release(connection)
            self._transaction_connection = None
            self._transaction_node = None
            self._watching = False
            self._explicit_transaction = False
            self._pipeline_slots = set()
            self._executing = False

    def multi(self):
        if self._explicit_transaction:
            raise RedisError("Cannot issue nested calls to MULTI")
        if self._command_queue:
            raise RedisError(
                "Commands without an initial WATCH have already been issued"
            )
        self._explicit_transaction = True

    async def watch(self, *names):
        if self._explicit_transaction:
            raise RedisError("Cannot issue a WATCH after a MULTI")

        return await self.execute_command("WATCH", *names)

    async def unwatch(self):
        if self._watching:
            return await self.execute_command("UNWATCH")

        return True

    async def discard(self):
        await self.reset()

    async def unlink(self, *names):
        return self.execute_command("UNLINK", *names)


class _ClusterNodePoolAdapter(ConnectionPoolInterface):
    """Thin adapter exposing the :class:`ConnectionPoolInterface` that
    :class:`PubSub` requires, backed by a :class:`ClusterNode`'s own
    connection pool.

    Connections are acquired from the node via
    :meth:`ClusterNode.acquire_connection` and returned via
    :meth:`ClusterNode.release`.  :meth:`PubSub.aclose` already
    disconnects the connection *before* calling :meth:`release`, so the
    connection is returned to the node's free-queue in a disconnected
    state — guaranteeing that a subscribed socket is never silently
    reused for regular commands.

    Methods that do not apply to this adapter (the underlying node's
    lifecycle is managed by the cluster, not by individual PubSub
    instances) are implemented as no-ops so the adapter remains a valid
    :class:`ConnectionPoolInterface`.
    """

    def __init__(self, node: "ClusterNode") -> None:
        self._node = node
        self.connection_kwargs = node.connection_kwargs


    def get_encoder(self) -> Encoder:
        return self._node.get_encoder()

    async def get_connection(
        self, command_name: Optional[str] = None, *keys: Any, **options: Any
    ) -> AbstractConnection:
        connection = self._node.acquire_connection()
        try:
            await connection.connect()
        except BaseException:
            await connection.disconnect()
            self._node.release(connection)
            raise
        return connection

    async def release(self, connection: AbstractConnection) -> None:
        await self._node.disconnect_if_needed(connection)
        self._node.release(connection)


    def get_protocol(self):
        return self.connection_kwargs.get("protocol", None)

    def reset(self) -> None:
        pass

    async def disconnect(self, inuse_connections: bool = True) -> None:
        pass

    async def aclose(self) -> None:
        pass

    def set_retry(self, retry: "Retry") -> None:
        pass

    async def re_auth_callback(self, token: TokenInterface) -> None:
        pass

    def get_connection_count(self) -> List[Tuple[int, dict]]:
        return []


def _unregister_slots_cache_listener(
    dispatcher_ref: "weakref.ref[EventDispatcher]",
    listener: AsyncEventListenerInterface,
    event_type: Type[object],
) -> None:
    dispatcher = dispatcher_ref()
    if dispatcher is not None:
        dispatcher.unregister_listeners({event_type: [listener]})


class ClusterPubSubSlotsCacheListener(AsyncEventListenerInterface):
    """
    Async listener that forwards AsyncAfterSlotsCacheRefreshEvent to a
    ClusterPubSub.

    Holds a weak reference to the pubsub so it does not keep the instance
    alive. Deterministic cleanup of the dispatcher's strong reference to this
    listener is performed by a ``weakref.finalize`` attached to the owning
    ClusterPubSub in ``ClusterPubSub.__init__``.
    """

    def __init__(self, pubsub: "ClusterPubSub") -> None:
        self._pubsub_ref: "weakref.ref[ClusterPubSub]" = weakref.ref(pubsub)

    async def listen(self, event: object) -> None:
        pubsub = self._pubsub_ref()
        if pubsub is None:
            return
        try:
            await pubsub.on_slots_changed()
        except Exception as e:
            logger.exception(
                "pubsub %r raised during slots-cache change: %s: %s",
                pubsub,
                type(e).__name__,
                e,
            )


class ClusterPubSub(PubSub):
    """
    Async cluster implementation for pub/sub.

    IMPORTANT: before using ClusterPubSub, read about the known limitations
    with pubsub in Cluster mode and learn how to workaround them:
    https://redis.readthedocs.io/en/stable/clustering.html#known-pubsub-limitations
    """

    def __init__(
        self,
        redis_cluster: "RedisCluster",
        node: Optional["ClusterNode"] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
        push_handler_func: Optional[Callable] = None,
        event_dispatcher: Optional[EventDispatcher] = None,
        **kwargs: Any,
    ) -> None:
        """
        When a pubsub instance is created without specifying a node, a single
        node will be transparently chosen for the pubsub connection on the
        first command execution. The node will be determined by:
         1. Hashing the channel name in the request to find its keyslot
         2. Selecting a node that handles the keyslot: If read_from_replicas is
            set to true or load_balancing_strategy is set, a replica can be selected.

        :param redis_cluster: RedisCluster instance
        :param node: ClusterNode to connect to
        :param host: Host of the node to connect to
        :param port: Port of the node to connect to
        :param push_handler_func: Optional push handler function
        :param event_dispatcher: Optional event dispatcher
        :param kwargs: Additional keyword arguments
        """
        self.node = None
        self.set_pubsub_node(redis_cluster, node, host, port)

        if self.node is not None:
            connection_pool = _ClusterNodePoolAdapter(self.node)
        else:
            connection_pool = None

        self.cluster = redis_cluster
        self.node_pubsub_mapping: Dict[str, PubSub] = {}
        self._shard_channel_to_node: Dict[Any, str] = {}
        self._shard_state_lock: asyncio.Lock = asyncio.Lock()
        self._reconcile_tasks: Set[asyncio.Task] = set()
        self._pubsubs_generator = self._pubsubs_generator()
        if event_dispatcher is None:
            self._event_dispatcher = EventDispatcher()
        else:
            self._event_dispatcher = event_dispatcher
        super().__init__(
            connection_pool=connection_pool,
            encoder=redis_cluster.encoder,
            push_handler_func=push_handler_func,
            event_dispatcher=self._event_dispatcher,
            **kwargs,
        )
        nm_dispatcher = redis_cluster.nodes_manager._event_dispatcher
        self._slots_cache_listener = ClusterPubSubSlotsCacheListener(self)
        nm_dispatcher.register_listeners(
            {AsyncAfterSlotsCacheRefreshEvent: [self._slots_cache_listener]}
        )
        weakref.finalize(
            self,
            _unregister_slots_cache_listener,
            weakref.ref(nm_dispatcher),
            self._slots_cache_listener,
            AsyncAfterSlotsCacheRefreshEvent,
        )

    def set_pubsub_node(
        self,
        cluster: "RedisCluster",
        node: Optional["ClusterNode"] = None,
        host: Optional[str] = None,
        port: Optional[int] = None,
    ) -> None:
        """
        The pubsub node will be set according to the passed node, host and port
        When none of the node, host, or port are specified - the node is set
        to None and will be determined by the keyslot of the channel in the
        first command to be executed.
        RedisClusterException will be thrown if the passed node does not exist
        in the cluster.
        If host is passed without port, or vice versa, a DataError will be
        thrown.
        """
        if node is not None:
            self._raise_on_invalid_node(cluster, node, node.host, node.port)
            pubsub_node = node
        elif host is not None and port is not None:
            node = cluster.get_node(host=host, port=port)
            self._raise_on_invalid_node(cluster, node, host, port)
            pubsub_node = node
        elif host is not None or port is not None:
            raise DataError("Specify both host and port")
        else:
            pubsub_node = None
        self.node = pubsub_node

    def get_pubsub_node(self) -> Optional["ClusterNode"]:
        """
        Get the node that is being used as the pubsub connection.

        :return: The ClusterNode being used for pubsub, or None if not yet determined
        """
        return self.node

    async def _resubscribe_shard_channels(self) -> None:
        by_slot: defaultdict[int, dict] = defaultdict(dict)
        for k, v in self.shard_channels.items():
            by_slot[key_slot(self.encoder.encode(k))][k] = v
        for subscriptions in by_slot.values():
            await self._resubscribe(subscriptions, self.ssubscribe)

    def _get_node_pubsub(self, node: "ClusterNode") -> PubSub:
        """Get or create a PubSub instance for the given node."""
        try:
            return self.node_pubsub_mapping[node.name]
        except KeyError:
            pubsub = PubSub(
                connection_pool=_ClusterNodePoolAdapter(node),
                encoder=self.cluster.encoder,
                push_handler_func=self.push_handler_func,
                event_dispatcher=self._event_dispatcher,
            )
            pubsub._resubscribe_shard_channels = MethodType(
                ClusterPubSub._resubscribe_shard_channels, pubsub
            )
            self.node_pubsub_mapping[node.name] = pubsub
            return pubsub

    def _find_node_name_for_pubsub(self, pubsub: PubSub) -> Optional[str]:
        for name, candidate in self.node_pubsub_mapping.items():
            if candidate is pubsub:
                return name
        return None

    async def _sharded_message_generator(
        self, timeout: float = 0.0
    ) -> Tuple[Optional[PubSub], Optional[Dict[str, Any]]]:
        """Generate messages from shard channels across all nodes."""
        for _ in range(len(self.node_pubsub_mapping)):
            pubsub = next(self._pubsubs_generator)
            message = await pubsub.get_message(
                ignore_subscribe_messages=False, timeout=timeout
            )
            if message is not None:
                return pubsub, message
        return None, None

    def _pubsubs_generator(self) -> Generator[PubSub, None, None]:
        """Generator that yields PubSub instances in round-robin fashion."""
        while True:
            current_nodes = list(self.node_pubsub_mapping.values())
            if not current_nodes:
                return 
            yield from current_nodes

    async def get_sharded_message(
        self,
        ignore_subscribe_messages: bool = False,
        timeout: float = 0.0,
        target_node: Optional["ClusterNode"] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Get a message from shard channels.

        :param ignore_subscribe_messages: Whether to ignore subscribe messages
        :param timeout: Timeout for message retrieval
        :param target_node: Specific node to get message from
        :return: Message dictionary or None
        """
        pubsub: Optional[PubSub]
        if target_node:
            pubsub = self.node_pubsub_mapping.get(target_node.name)
            if pubsub:
                message = await pubsub.get_message(
                    ignore_subscribe_messages=False, timeout=timeout
                )
            else:
                message = None
        else:
            pubsub, message = await self._sharded_message_generator(timeout=timeout)

        if message is None:
            return None
        if str_if_bytes(message["type"]) == "sunsubscribe":
            async with self._shard_state_lock:
                if message["channel"] in self.pending_unsubscribe_shard_channels:
                    self.pending_unsubscribe_shard_channels.remove(message["channel"])
                    self.shard_channels.pop(message["channel"], None)
                    self._shard_channel_to_node.pop(message["channel"], None)
                if pubsub is not None and not pubsub.subscribed:
                    name = self._find_node_name_for_pubsub(pubsub)
                    if name is not None:
                        try:
                            await pubsub.aclose()
                        except Exception:
                            pass
                        self.node_pubsub_mapping.pop(name, None)

        if str_if_bytes(message["type"]) in ("ssubscribe", "sunsubscribe"):
            if self.ignore_subscribe_messages or ignore_subscribe_messages:
                return None
        return message

    async def ssubscribe(
        self, *args: ChannelT | Subscription, **kwargs: PubSubHandler
    ) -> None:
        """
        Subscribe to shard channels.

        :param args: Channel names or ``Subscription`` objects
        :param kwargs: Channel names with handlers
        """
        s_channels = parse_pubsub_subscriptions(args, kwargs)

        async with self._shard_state_lock:
            for s_channel, handler in s_channels.items():
                node = self.cluster.get_node_from_key(s_channel)
                if not node:
                    continue
                normalized_key = next(iter(self._normalize_keys({s_channel: None})))
                old_name = self._shard_channel_to_node.get(normalized_key)
                if old_name and old_name != node.name:
                    await self._migrate_shard_channel(
                        normalized_key,
                        handler,
                        old_name,
                        node,
                    )
                    continue
                pubsub = self._get_node_pubsub(node)
                if handler:
                    await pubsub.ssubscribe(Subscription(s_channel, handler))
                else:
                    await pubsub.ssubscribe(s_channel)
                self.shard_channels.update(pubsub.shard_channels)
                self._shard_channel_to_node[normalized_key] = node.name
                self.pending_unsubscribe_shard_channels.difference_update(
                    self._normalize_keys({s_channel: None})
                )

    async def sunsubscribe(self, *args: Any) -> None:
        """
        Unsubscribe from shard channels.

        :param args: Channel names to unsubscribe from. If empty, unsubscribe from all.
        """
        if args:
            args = list_or_args(args[0], args[1:])
        else:
            args = list(self.shard_channels.keys())

        async with self._shard_state_lock:
            for s_channel in args:
                normalized_key = next(iter(self._normalize_keys({s_channel: None})))
                name = self._shard_channel_to_node.get(normalized_key)
                if name and name in self.node_pubsub_mapping:
                    pubsub = self.node_pubsub_mapping[name]
                else:
                    node = self.cluster.get_node_from_key(s_channel)
                    if not node or node.name not in self.node_pubsub_mapping:
                        continue
                    pubsub = self.node_pubsub_mapping[node.name]
                await pubsub.sunsubscribe(s_channel)
                self.pending_unsubscribe_shard_channels.update(
                    pubsub.pending_unsubscribe_shard_channels
                )

    async def reinitialize_shard_subscriptions(self) -> None:
        """
        Reconcile per-node shard subscriptions against the cluster's current
        slot ownership map. For each tracked shard channel whose owning node
        has changed (e.g. after CLUSTER SETSLOT / failover), sunsubscribe on
        the old node's pubsub and ssubscribe on the new owner's pubsub,
        preserving any registered handler.
        """
        uncovered: list = []
        made_progress = False
        first_migrate_error: Optional[BaseException] = None
        async with self._shard_state_lock:
            for channel, handler in list(self.shard_channels.items()):
                try:
                    new_node = self.cluster.get_node_from_key(channel)
                except SlotNotCoveredError:
                    uncovered.append(channel)
                    continue
                old_name = self._shard_channel_to_node.get(channel)
                if old_name == new_node.name:
                    continue
                try:
                    await self._migrate_shard_channel(
                        channel, handler, old_name, new_node
                    )
                    made_progress = True
                except (ConnectionError, TimeoutError, OSError) as e:
                    logger.warning(
                        "shard channel %r migration deferred: %s: %s",
                        channel,
                        type(e).__name__,
                        e,
                    )
                    if first_migrate_error is None:
                        first_migrate_error = e
                    continue
            for name, pubsub in list(self.node_pubsub_mapping.items()):
                if not pubsub.subscribed:
                    try:
                        await pubsub.aclose()
                    except Exception:
                        pass
                    self.node_pubsub_mapping.pop(name, None)
        if uncovered:
            raise SlotNotCoveredError(
                f"{len(uncovered)} shard channel(s) left unreconciled; "
                f"slot(s) not covered by the cluster: {uncovered!r}"
            )
        if first_migrate_error is not None and not made_progress:
            raise first_migrate_error

    async def _migrate_shard_channel(
        self,
        channel: Any,
        handler: Optional[Callable],
        old_name: Optional[str],
        new_node: "ClusterNode",
    ) -> None:
        if old_name and old_name in self.node_pubsub_mapping:
            old_pubsub = self.node_pubsub_mapping[old_name]
            try:
                await old_pubsub.sunsubscribe(channel)
            except (ConnectionError, TimeoutError, OSError):
                if self.cluster.get_node(node_name=old_name) is None:
                    try:
                        await old_pubsub.aclose()
                    except Exception:
                        pass
                    self.node_pubsub_mapping.pop(old_name, None)
        new_pubsub = self._get_node_pubsub(new_node)
        if handler:
            await new_pubsub.ssubscribe(Subscription(channel, handler))
        else:
            await new_pubsub.ssubscribe(channel)
        self.shard_channels.update(new_pubsub.shard_channels)
        normalized_key = next(iter(self._normalize_keys({channel: None})))
        self._shard_channel_to_node[normalized_key] = new_node.name
        self.pending_unsubscribe_shard_channels.difference_update(
            self._normalize_keys({channel: None})
        )

    async def on_slots_changed(self) -> None:
        if not self.shard_channels:
            return
        task = asyncio.create_task(self.reinitialize_shard_subscriptions())
        self._reconcile_tasks.add(task)
        task.add_done_callback(self._reconcile_tasks.discard)
        task.add_done_callback(self._log_reconcile_task_exception)

    @staticmethod
    def _log_reconcile_task_exception(task: "asyncio.Task") -> None:
        if task.cancelled():
            return
        exc = task.exception()
        if exc is not None:
            logger.error(
                "shard subscription reconciliation failed: %r", exc, exc_info=exc
            )

    def get_redis_connection(self) -> Optional["AbstractConnection"]:
        """
        Get the Redis connection of the pubsub connected node.

        Returns the pubsub's dedicated connection (acquired from its own
        connection pool), not from the ClusterNode's connection pool.
        This avoids the connection pool resource leak that would occur
        if we called node.acquire_connection() without releasing.
        """
        return self.connection

    async def aclose(self) -> None:
        """
        Disconnect the pubsub connection.
        """
        if self._reconcile_tasks:
            tasks = list(self._reconcile_tasks)
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
        async with self._shard_state_lock:
            self._reconcile_tasks.clear()
            for pubsub in self.node_pubsub_mapping.values():
                await pubsub.aclose()
            self.node_pubsub_mapping.clear()
            self._pubsubs_generator = type(self)._pubsubs_generator( 
                self
            )
            await super().aclose()
            self._shard_channel_to_node.clear()

    def _raise_on_invalid_node(
        self,
        redis_cluster: "RedisCluster",
        node: Optional["ClusterNode"],
        host: Optional[str],
        port: Optional[int],
    ) -> None:
        """
        Raise a RedisClusterException if the node is None or doesn't exist in
        the cluster.
        """
        if node is None or redis_cluster.get_node(node_name=node.name) is None:
            raise RedisClusterException(
                f"Node {host}:{port} doesn't exist in the cluster"
            )

    async def execute_command(self, *args: Any, **kwargs: Any) -> Any:
        """
        Execute a command on the appropriate cluster node.

        Taken code from redis-py and tweaked to make it work within a cluster.
        """

        command = args[0].upper() if args else ""
        if command in ("SSUBSCRIBE", "SUNSUBSCRIBE", "SPUBLISH"):
            if len(args) > 1:
                channel = args[1]
                node = self.cluster.get_node_from_key(channel)
                if node:
                    pubsub = self._get_node_pubsub(node)
                    return await pubsub.execute_command(*args, **kwargs)

        if self.connection is None:
            if self.connection_pool is None:
                if len(args) > 1:
                    channel = args[1]
                    slot = self.cluster.keyslot(channel)
                    node = self.cluster.nodes_manager.get_node_from_slot(
                        slot,
                        self.cluster.read_from_replicas,
                        self.cluster.load_balancing_strategy,
                    )
                else:
                    node = self.cluster.get_random_node()
                self.node = node
                self.connection_pool = _ClusterNodePoolAdapter(node)

        return await super().execute_command(*args, **kwargs)
