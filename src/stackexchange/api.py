# https://github.com/microsoft/pyright/issues/1575#issuecomment-1304571290
# pyright: reportCallIssue=information
# https://github.com/microsoft/pyright/issues/9149
# pyright: reportArgumentType=information
# Should show "23 informations"
import datetime
import functools
import inspect
import threading
import time
from collections import deque
from collections.abc import Callable, Generator
from http import HTTPMethod
from typing import (
    Any,
    ClassVar,
    Literal,
    overload,
)

import attrs
import requests
import requests.adapters
import requests.auth
import urllib3

from stackexchange.model import *

# noinspection PyProtectedMember
from stackexchange.serdes import (
    query_converter,
    unstructure_as_batched_vectors,
)

__version__ = "2.3"
__all__ = ["StackExchangeApi"]


# https://stackoverflow.com/q/6760685
# https://gist.github.com/wowkin2/3af15bfbf197a14a2b0b2488a1e8c787
class SingletonMeta(type):
    _instances: ClassVar[dict] = {}
    _init: ClassVar[dict] = {}

    # noinspection PyUnusedLocal
    def __init__(cls, clsname, bases, dct, **kwds):
        super().__init__(type)
        cls._init[cls] = dct.get("__init__", None)

    def __call__(cls, *args, **kwargs):
        if (init := cls._init[cls]) is not None:
            bound = inspect.signature(init).bind(None, *args, **kwargs)
            bound.apply_defaults()
            callargs = bound.arguments.items()
            key = (cls, frozenset(callargs))
        else:
            key = cls
        if key not in cls._instances:
            cls._instances[key] = (super()
                                   .__call__(*args, **kwargs))
        return cls._instances[key]

    def __new__(mcs, clsname, bases, dct, **kwds):
        return (super()
                .__new__(mcs, clsname, bases, dct, **kwds))


@attrs.define(frozen=True, kw_only=True)
class PathParamsInfo:
    vector_key: str | None
    path_params: dict[str, Any]


def api_method(func):
    def wrapper(*args, **kwargs):
        api_method_name = func.__name__
        return func(*args, **kwargs, initiator=api_method_name)

    return wrapper


# pylint: disable=too-few-public-methods
class BearerAuth(requests.auth.AuthBase):
    def __init__(self, token):
        self.token = token

    def __call__(self, r):
        if self.token:
            r.headers["Authorization"] = "Bearer " + self.token
        return r


# pylint: disable=too-many-instance-attributes
# noinspection PyTypeChecker
class StackExchangeApi(metaclass=SingletonMeta):
    API_ROOT: ClassVar[str] = f"https://api.stackexchange.com/{__version__}"
    API_KEY: ClassVar[str] = "YLTVFmHkeJbm7ZIOoXstag(("
    MAX_REQUESTS_PER_DAY: ClassVar[int] = 10_000
    MAX_REQUESTS_PER_SECOND: ClassVar[int] = 30
    """If a single IP is making more than 30 requests a second, new 
    requests will be dropped.
    """
    MAX_CONCURRENT_REQUESTS: ClassVar[int] = 1
    """Just being conservative here, as the exact rate limit mechanisms 
    are not well-understood.
    """

    def __init__(self,
                 api_key: str | None = API_KEY,
                 access_token: str | None = None,
                 limit_rate: int = MAX_REQUESTS_PER_SECOND) -> None:
        self.api_key: str | None = api_key
        """API keys, also known as request keys or app keys,
        grant more requests per day (10,000 vs 300 for anonymous API 
        access) and allow querying results past page 25.
        """
        self.access_token: str | None = access_token
        self._limit_rate: int = (
            limit_rate
            if 1 <= limit_rate <= StackExchangeApi.MAX_REQUESTS_PER_SECOND
            else StackExchangeApi.MAX_REQUESTS_PER_SECOND
        )
        self._limit_rate_deque: deque[int] = deque(
            [0] * StackExchangeApi.MAX_CONCURRENT_REQUESTS,
            maxlen=StackExchangeApi.MAX_CONCURRENT_REQUESTS,
        )
        self._limit_rate_timer = threading.Thread(
            target=self._refill_limit_rate_deque,
            name="Thread-Limit-Rate-Timer",
            daemon=True,
        )
        self._quota_remaining: int = StackExchangeApi.MAX_REQUESTS_PER_DAY
        self._backoff: dict[str, int] = {}
        """
        `Documentation <https://api.stackexchange.com/docs/throttle>`_:
        A dynamic throttle is also in place on a per-method level.
        If an application receives a response with the backoff field 
        set, it must wait that many seconds before hitting the same 
        method again.
        All methods (even seemingly trivial ones) may return backoff.
        """
        session = requests.Session()
        session.mount(
            "https://",
            requests.adapters.HTTPAdapter(pool_connections=1,
                                          pool_maxsize=1,
                                          max_retries=urllib3.Retry(total=5))
        )
        self.proxied_request = self._request_hook(session.request)
        self._limit_rate_timer.start()

    @property
    def limit_rate(self):
        return self._limit_rate

    def _refill_limit_rate_deque(self) -> None:
        while True:
            time.sleep(1 / self.limit_rate)
            self._limit_rate_deque.appendleft(0)

    def _request_hook(self, request: Callable[..., requests.models.Response]):
        def wrapped_request(initiator: str, params: Parameters):
            @functools.wraps(requests.request)
            def api_request(method: str, url: str, **kwargs) \
                    -> requests.models.Response:
                self._respect_quota_remaining()
                self._respect_backoff(initiator)
                self._respect_rate_limit()
                self._assign_request_parameters(params, method, kwargs)
                response = request(method, url, **kwargs)
                return response

            return api_request

        return wrapped_request

    def _respect_quota_remaining(self):
        if self._quota_remaining <= 0:
            print("We've reached the daily usage quota. "
                  + "The program will resume from sleep in 24 hours "
                  + "(press Ctrl+C to abort the pending operation).",
                  flush=True)
            time.sleep(24 * 60 * 60)

    def _respect_backoff(self, initiator: str) -> None:
        if lift_backoff_timestamp := self._backoff.pop(initiator, None):
            now_timestamp = datetime.datetime.now(datetime.UTC).timestamp()
            if (wait_seconds := int(lift_backoff_timestamp - now_timestamp)
                                + 1) > 0:  # Add 1 more second just to be safe
                print(
                    "We've made too many requests to the Stack Exchange API, "
                    + f"so we will need to wait for {wait_seconds} seconds. "
                    + "Please be patient...",
                    flush=True,
                )
                time.sleep(wait_seconds)

    def _respect_rate_limit(self):
        while True:
            try:
                self._limit_rate_deque.pop()
                break
            except IndexError:
                print("Rate limiting has kicked in at "
                      + f"{self.limit_rate} requests per second.")
                time.sleep(1 / self.limit_rate)

    def _assign_request_parameters(self,
                                   params: Parameters,
                                   method: str,
                                   kwargs: dict[str, Any]) -> None:
        if "auth" not in kwargs:
            kwargs["auth"] = BearerAuth(self.api_key)
        if "timeout" not in kwargs:
            kwargs["timeout"] = (5, 30)
        if "allow_redirects" not in kwargs:
            kwargs["allow_redirects"] = False
        match method:
            case HTTPMethod.GET:
                kwargs["params"] = query_converter.unstructure(params)
            case _:
                kwargs["data"] = query_converter.unstructure(params)

    def _process_response[T](self,
                             response: requests.models.Response,
                             model: type[T],
                             request_initiator: str) -> Response[T]:
        self._inspect_response_status(response)
        # noinspection PyTypeHints
        structured_response = query_converter.loads(response.content or b"",
                                                    Response[model])
        self._inspect_quota_remaining(structured_response)
        self._inspect_backoff(structured_response, request_initiator)
        return structured_response

    @classmethod
    def _inspect_response_status(cls, response: requests.models.Response) \
            -> None:
        if not response.ok:
            x_headers = {
                k: v for k, v in response.headers.lower_items()
                if k in (
                    "x-request-guid",
                    "x-route-name",
                    "x-error-status",
                    "x-error-name",
                    "x-error-message",
                )
            }
            raise requests.HTTPError(x_headers, response=response)

    def _inspect_quota_remaining(self, response: Response) -> None:
        if (quota_remaining := response.quota_remaining) is not None:
            self._quota_remaining = quota_remaining

    def _inspect_backoff(self,
                         response: Response,
                         request_initiator: str) -> None:
        if response.backoff:
            self._backoff[request_initiator] = (
                    int(datetime.datetime.now(datetime.UTC).timestamp())
                    + response.backoff
                    + 1  # Add 1 more second just to be safe
            )

    @classmethod
    def path_params_info(cls, params: Parameters) -> PathParamsInfo:
        params_type = type(params)
        vector_key = None
        path_params_dict = {}
        # noinspection PyDataclass
        fields_dict = attrs.fields_dict(params_type)
        for k, v in fields_dict.items():
            if (Parameters.PATH_PARAMETER_KEY in v.metadata
                    and (path_param_ := getattr(params, k)) is not None):
                path_params_dict[k] = path_param_
                if isinstance(path_param_, list):
                    vector_key = k
        if vector_key:
            path_params_dict[vector_key] = unstructure_as_batched_vectors(
                path_params_dict[vector_key],
                fields_dict[vector_key],
            )
        return PathParamsInfo(vector_key=vector_key,
                              path_params=path_params_dict)

    @overload
    # pylint: disable=too-many-arguments
    def _call_api[T](self,
                     /,
                     url_template: str,
                     params: Parameters,
                     model: type[T],
                     *,
                     initiator: str = ...,
                     http_method: HTTPMethod = ...,
                     auto_pagination: bool = ...,
                     items_only: Literal[False],
                     **kwargs) \
            -> Generator[Response[T], None, None]:
        ...

    @overload
    # pylint: disable=too-many-arguments
    def _call_api[T](self,
                     /,
                     url_template: str,
                     params: Parameters,
                     model: type[T],
                     *,
                     initiator: str = ...,
                     http_method: HTTPMethod = ...,
                     auto_pagination: bool = ...,
                     items_only: Literal[True] = ...,
                     **kwargs) \
            -> Generator[T, None, None]:
        ...

    # pylint: disable=too-many-arguments, too-many-locals
    def _call_api[T](self,
                     /,
                     url_template: str,
                     params: Parameters,
                     model: type[T],
                     *,
                     initiator="unknown",
                     http_method: HTTPMethod = HTTPMethod.GET,
                     auto_pagination=True,
                     items_only=True,
                     **kwargs) \
            -> Generator[Response[T] | T, None, None]:
        info = self.path_params_info(params)
        batched_vectors = (info.path_params[info.vector_key]
                           if info.vector_key
                           else [0])
        for vector in batched_vectors:
            if info.vector_key:
                info.path_params[info.vector_key] = vector
            url = url_template.format(**info.path_params)
            page = 0
            has_more = True
            while has_more:
                page += 1
                if auto_pagination:
                    # ruff: ignore[B010]
                    setattr(
                        params,
                        "paging",
                        Paging(page=page, pagesize=Parameters.MAX_PAGE_SIZE)
                    )
                request = self.proxied_request(initiator, params)
                response = request(http_method, url, **kwargs)
                structured_response \
                    = self._process_response(response, model, initiator)
                has_more = ((structured_response.has_more
                             or structured_response.items)
                            and auto_pagination)
                if items_only:
                    yield from structured_response.items or []
                else:
                    yield structured_response

    @overload
    @api_method
    def questions_by_ids(self,
                         /,
                         params: QuestionsByIdsParameters,
                         *,
                         items_only: Literal[False],
                         **kwargs) \
            -> Generator[Response[Question], None, None]:
        ...

    @overload
    @api_method
    def questions_by_ids(self,
                         /,
                         params: QuestionsByIdsParameters,
                         *,
                         items_only: Literal[True] = ...,
                         **kwargs) \
            -> Generator[Question, None, None]:
        ...

    @api_method
    def questions_by_ids(self,
                         /,
                         params: QuestionsByIdsParameters,
                         *,
                         items_only=True,
                         **kwargs) \
            -> Generator[Response[Question] | Question, None, None]:
        """`Documentation <https://api.stackexchange.com/docs/questions-by-ids>`_
        Returns the questions identified in {ids}.

        :param params:
        :param items_only:
        :return:
        """
        return self._call_api(
            StackExchangeApi.API_ROOT + "/questions/{ids}",
            params,
            Question,
            auto_pagination=True,
            items_only=items_only,
            **kwargs,
        )

    @overload
    @api_method
    def answers_on_users(self,
                         /,
                         params: AnswersOnUsersParameters,
                         *,
                         auto_pagination: bool = ...,
                         items_only: Literal[False],
                         **kwargs) \
            -> Generator[Response[Answer], None, None]:
        ...

    @overload
    @api_method
    def answers_on_users(self,
                         /,
                         params: AnswersOnUsersParameters,
                         *,
                         auto_pagination: bool = ...,
                         items_only: Literal[True] = ...,
                         **kwargs) \
            -> Generator[Answer, None, None]:
        ...

    @api_method
    def answers_on_users(self,
                         /,
                         params: AnswersOnUsersParameters,
                         *,
                         auto_pagination=True,
                         items_only=True,
                         **kwargs) \
            -> Generator[Response[Answer] | Answer, None, None]:
        """`Documentation <https://api.stackexchange.com/docs/answers-on-users>`_
        Returns the answers the users in {ids} have posted.

        :param params:
        :param auto_pagination:
        :param items_only:
        :return:
        """
        return self._call_api(
            StackExchangeApi.API_ROOT + "/users/{ids}/answers",
            params,
            Answer,
            auto_pagination=auto_pagination,
            items_only=items_only,
            **kwargs,
        )

    @overload
    @api_method
    def questions_on_users(self,
                           /,
                           params: QuestionsOnUsersParameters,
                           *,
                           auto_pagination: bool = ...,
                           items_only: Literal[False],
                           **kwargs) \
            -> Generator[Response[Question], None, None]:
        ...

    @overload
    @api_method
    def questions_on_users(self,
                           /,
                           params: QuestionsOnUsersParameters,
                           *,
                           auto_pagination: bool = ...,
                           items_only: Literal[True] = ...,
                           **kwargs) \
            -> Generator[Question, None, None]:
        ...

    @api_method
    def questions_on_users(self,
                           /,
                           params: QuestionsOnUsersParameters,
                           *,
                           auto_pagination=True,
                           items_only=True,
                           **kwargs) \
            -> Generator[Response[Question] | Question, None, None]:
        """`Documentation <https://api.stackexchange.com/docs/questions-on-users>`_
        Gets the questions asked by the users in {ids}.

        :param params:
        :param auto_pagination:
        :param items_only:
        :return:
        """
        return self._call_api(
            StackExchangeApi.API_ROOT + "/users/{ids}/questions",
            params,
            Question,
            auto_pagination=auto_pagination,
            items_only=items_only,
            **kwargs,
        )

    @api_method
    def simulate_error(self, /, params: SimulateErrorParameters, **kwargs) \
            -> Response[Any]:
        """`Documentation <https://api.stackexchange.com/docs/simulate-error>`_
        This method allows you to generate an error.

        :param params:
        :return:
        """
        return next(
            self._call_api(
                StackExchangeApi.API_ROOT + "/errors/{id}",
                params,
                Error,
                auto_pagination=False,
                items_only=False,
                **kwargs,
            )
        )

    @overload
    @api_method
    def create_filter(self,
                      /,
                      params: CreateFilterParameters,
                      *,
                      http_method: Literal[HTTPMethod.GET, HTTPMethod.POST] = ...,
                      items_only: Literal[False],
                      **kwargs) \
            -> Response[Filter]:
        ...

    @overload
    @api_method
    def create_filter(self,
                      /,
                      params: CreateFilterParameters,
                      *,
                      http_method: Literal[HTTPMethod.GET, HTTPMethod.POST] = ...,
                      items_only: Literal[True] = ...,
                      **kwargs) \
            -> Filter:
        ...

    @api_method
    def create_filter(self,
                      /,
                      params: CreateFilterParameters,
                      *,
                      http_method: Literal[HTTPMethod.GET, HTTPMethod.POST] = HTTPMethod.GET,
                      items_only=True,
                      **kwargs) \
            -> Response[Filter] | Filter:
        """`Documentation <https://api.stackexchange.com/docs/create-filter>`_
        Creates a new filter given a list of includes, excludes, a base
        filter, and whether or not this filter should be "unsafe".

        When building filters, refer to the fields of the
        common wrapper object with a leading "."

        :param params:
        :param http_method:
        :param items_only:
        :return:
        """
        return next(
            self._call_api(
                StackExchangeApi.API_ROOT + "/filters/create",
                params,
                Filter,
                http_method=http_method,
                auto_pagination=False,
                items_only=items_only,
                **kwargs,
            )
        )

    @overload
    @api_method
    def read_filter(self,
                    /,
                    params: ReadFilterParameters,
                    *,
                    items_only: Literal[False],
                    **kwargs) \
            -> Generator[Response[Filter], None, None]:
        ...

    @overload
    @api_method
    def read_filter(self,
                    /,
                    params: ReadFilterParameters,
                    *,
                    items_only: Literal[True] = ...,
                    **kwargs) \
            -> Generator[Filter, None, None]:
        ...

    @api_method
    def read_filter(self,
                    /,
                    params: ReadFilterParameters,
                    *,
                    items_only=True,
                    **kwargs) \
            -> Generator[Response[Filter] | Filter, None, None]:
        """`Documentation <https://api.stackexchange.com/docs/read-filter>`_
        Returns the fields included by the given filters,
        and the "safeness" of those filters.

        :param params:
        :param items_only:
        :return:
        """
        return self._call_api(
            StackExchangeApi.API_ROOT + "/filters/{filters}",
            params,
            Filter,
            auto_pagination=True,
            items_only=items_only,
            **kwargs,
        )

    @overload
    @api_method
    def sites(self,
              /,
              params: SitesParameters,
              *,
              auto_pagination: bool = ...,
              items_only: Literal[False],
              **kwargs) \
            -> Generator[Response[Site], None, None]:
        ...

    @overload
    @api_method
    def sites(self,
              /,
              params: SitesParameters,
              *,
              auto_pagination: bool = ...,
              items_only: Literal[True] = ...,
              **kwargs) \
            -> Generator[Site, None, None]:
        ...

    @api_method
    def sites(self,
              /,
              params: SitesParameters,
              *,
              auto_pagination=True,
              items_only=True,
              **kwargs) \
            -> Generator[Response[Site] | Site, None, None]:
        """`Documentation <https://api.stackexchange.com/docs/sites>`_
        Returns all sites in the network.

        :param params:
        :param auto_pagination:
        :param items_only:
        :return:
        """
        return self._call_api(
            StackExchangeApi.API_ROOT + "/sites",
            params,
            Site,
            auto_pagination=auto_pagination,
            items_only=items_only,
            **kwargs,
        )

    @overload
    @api_method
    def associated_users(self,
                         /,
                         params: AssociatedUsersParameters,
                         *,
                         auto_pagination: bool = ...,
                         items_only: Literal[False],
                         **kwargs) \
            -> Generator[Response[NetworkUser], None, None]:
        ...

    @overload
    @api_method
    def associated_users(self,
                         /,
                         params: AssociatedUsersParameters,
                         *,
                         auto_pagination: bool = ...,
                         items_only: Literal[True] = ...,
                         **kwargs) \
            -> Generator[NetworkUser, None, None]:
        ...

    @api_method
    def associated_users(self,
                         /,
                         params: AssociatedUsersParameters,
                         *,
                         auto_pagination=True,
                         items_only=True,
                         **kwargs) \
            -> Generator[Response[NetworkUser] | NetworkUser, None, None]:
        """`Documentation <https://api.stackexchange.com/docs/associated-users>`_
        Returns all of a user's associated accounts,
        given their account_ids in {ids}.
        It is a `known bug <https://stackapps.com/q/8666/>`_ that
        results are not returned for meta sites.

        :param params:
        :param auto_pagination:
        :param items_only:
        :return:
        """
        return self._call_api(
            StackExchangeApi.API_ROOT + "/users/{ids}/associated",
            params,
            NetworkUser,
            auto_pagination=auto_pagination,
            items_only=items_only,
            **kwargs,
        )
