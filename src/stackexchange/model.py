# pylint: disable=too-few-public-methods
import datetime
import math
from abc import ABCMeta
from typing import (
    ClassVar,
    dataclass_transform,
    get_args,
)

from attr import attrib
from attrs import (
    Converter,
    define,
    field,
    make_class,
)
from urllib3.util import Url, parse_url

# noinspection PyProtectedMember
from stackexchange.generated._model_openapi import *

__all__ = [
    # Component schemas (re-exported from .generated._model_openapi)
    ## Top level types
    "Answer",
    "Collective",
    "Comment",
    "Error",
    "Filter",
    "NetworkUser",
    "Question",
    "Site",
    ## Member types
    "BadgeCount",
    "ClosedDetails",
    "CollectiveExternalLink",
    "CollectiveRecommendation",
    "MigrationInfo",
    "NetworkPost",
    "Notice",
    "OriginalQuestion",
    "RelatedSite",
    "ShallowUser",
    "Styling",
    # Component parameters (re-exported from .generated._model_openapi)
    "Paging",
    "Complex",
    # Types
    "BuiltInFilter",
    "BakedInFilter",
    # Generic response
    "Response",
    # Parameters
    "Parameters",
    "QuestionsByIdsParameters",
    "AnswersOnUsersParameters",
    "QuestionsOnUsersParameters",
    "SimulateErrorParameters",
    "CreateFilterParameters",
    "ReadFilterParameters",
    "SitesParameters",
    "AssociatedUsersParameters",
    # YAML frontmatter metadata
    "Metadata",
    "ShallowUserMetadata",
    "CommentMetadata",
    "AnswerMetadata",
    "QuestionMetadata",
]

type BuiltInFilter = Literal[
    "default",
    "withbody",
    "none",
    "total",
]
type BakedInFilter = Literal[
    "!-0ttWpKaHtrB(oS",
    "!2SUoF4c)sOul00Zq",
    "r8cwHZB3p97RraWJSdBqs7HCWXUCebDx9Wuhn_ChbmNDTEZ3_1lkd3suiMKEh6U-zwe.EML1(4mmULGTB",
    "!6aC-iR(QLBu-5SKm",
]


# pylint: disable=too-many-instance-attributes
@define(kw_only=True)
class Response[T]:
    backoff: int | None = None
    error_id: int | None = None
    """
    refers to an Error
    """
    error_message: str | None = None
    error_name: str | None = None
    has_more: bool | None = None
    items: list[T] | None = None
    """
    an array of the type found in type
    """
    page: int | None = None
    page_size: int | None = None
    quota_max: int | None = None
    quota_remaining: int | None = None
    total: int | None = None
    type: str | None = None


@define(frozen=True)
class ContentLicenseOption:
    name: str
    url: Url
    starting_date: float
    ending_date: float


# https://meta.stackexchange.com/help/licensing
content_license_options = {
    content_license_option.name: content_license_option
    for content_license_option in (
        ContentLicenseOption(
            "CC BY-SA 4.0",
            parse_url("https://creativecommons.org/licenses/by-sa/4.0/"),
            datetime.datetime(2018, 5, 2, tzinfo=datetime.UTC).timestamp(),
            math.inf,
        ),
        ContentLicenseOption(
            "CC BY-SA 3.0",
            parse_url("https://creativecommons.org/licenses/by-sa/3.0/"),
            datetime.datetime(2011, 4, 8, tzinfo=datetime.UTC).timestamp(),
            datetime.datetime(2018, 5, 2, tzinfo=datetime.UTC).timestamp(),
        ),
        ContentLicenseOption(
            "CC BY-SA 2.5",
            parse_url("https://creativecommons.org/licenses/by-sa/2.5/"),
            -math.inf,
            datetime.datetime(2011, 4, 8, tzinfo=datetime.UTC).timestamp(),
        ),
    )
}


# https://meta.stackexchange.com/q/411264
def guess_content_license_from_publication_date(lic: str | None, obj) \
        -> str | None:
    if (lic is None
            and ((publication_date := getattr(obj, "last_edit_date", 0))
                or (publication_date := getattr(obj, "creation_date", 0)))):
        for content_license_option in content_license_options.values():
            if (content_license_option.starting_date
                    <= publication_date
                    < content_license_option.ending_date):
                lic = content_license_option.name + "?"
    return lic


globals()["Question"] = define(
    make_class(
        Question.__name__,
        {
            "content_license": field(
                default=None,
                converter=Converter(
                    guess_content_license_from_publication_date,
                    takes_self=True,
                ),
            ),
        },
        bases=(Question,),
    ),
    kw_only=True,
)


# region Parameters


class Parameters(metaclass=ABCMeta):
    PATH_PARAMETER_KEY: ClassVar[str] = "PATH_PARAMETER"
    VECTOR_LIMIT_KEY: ClassVar[str] = "VECTOR_LIMIT"
    DEFAULT_VECTOR_LIMIT: ClassVar[int] = 100
    MAX_PAGE_SIZE: ClassVar[int] = 100


@dataclass_transform(kw_only_default=True, field_specifiers=(attrib, field))
def parameters[T](cls: type[T]) -> type[T]:
    return Parameters.register(
        define(
            cls,
            kw_only=True,
            field_transformer=parameters_post_init,
        )
    )


# noinspection PyUnusedLocal
def parameters_post_init(cls: type, fields_: list) -> list:
    return [
        f.evolve(validator=is_allowed_paging)
        if f.name == "paging"
        else f.evolve(validator=is_registered_filter)
        if f.name == "filter"
        else f
        for f in fields_
    ]


# noinspection PyUnusedLocal
def is_allowed_paging(inst, attr, value: Paging | None) -> None:
    if value is None:
        return
    if value.page is not None and not 1 <= value.page < 2 ** 31:
        raise ValueError("page number out of bounds")
    if (value.pagesize is not None
            and not 1 <= value.pagesize <= Parameters.MAX_PAGE_SIZE):
        raise ValueError("page size out of bounds")


# noinspection PyUnusedLocal
def is_registered_filter(inst, attr, value: str | None) -> None:
    if value is not None and value not in {
        literal_value for literal_args_tuples in
        # pylint: disable=no-member
        get_args(BuiltInFilter.__value__ | BakedInFilter.__value__)
        for literal_value in get_args(literal_args_tuples)
    }:
        raise ValueError("filter is not registered")


def path_param(vector_limit: int | None = None):
    kwds: dict[str, Any] = {"metadata": {Parameters.PATH_PARAMETER_KEY: True}}
    if vector_limit is not None:
        kwds["metadata"][Parameters.VECTOR_LIMIT_KEY] = vector_limit
    return field(**kwds)


@parameters
class QuestionsByIdsParameters(QuestionsByIdsParametersQuery):
    ids: list[int] = path_param(vector_limit=Parameters.DEFAULT_VECTOR_LIMIT)


@parameters
class AnswersOnUsersParameters(AnswersOnUsersParametersQuery):
    ids: list[int] = path_param(vector_limit=Parameters.DEFAULT_VECTOR_LIMIT)


@parameters
class QuestionsOnUsersParameters(QuestionsOnUsersParametersQuery):
    ids: list[int] = path_param(vector_limit=Parameters.DEFAULT_VECTOR_LIMIT)


@parameters
class SimulateErrorParameters(SimulateErrorParametersQuery):
    id: int = path_param()


@parameters
class CreateFilterParameters(CreateFilterParametersQuery):
    pass


@parameters
class ReadFilterParameters(ReadFilterParametersQuery):
    filters: list[str] = path_param(vector_limit=20)


@parameters
class SitesParameters(SitesParametersQuery):
    pass


@parameters
class AssociatedUsersParameters(AssociatedUsersParametersQuery):
    ids: list[int] = path_param(vector_limit=Parameters.DEFAULT_VECTOR_LIMIT)


# endregion

# region YAML frontmatter metadata


class Metadata(metaclass=ABCMeta):
    pass


@dataclass_transform(kw_only_default=True,
                     frozen_default=True,
                     field_specifiers=(attrib, field))
def metadata[T](cls: type[T]) -> type[T]:
    return Metadata.register(define(cls, frozen=True, kw_only=True))


@metadata
class ShallowUserMetadata:
    display_name: str | None = None
    user_type: str | None = None
    reputation: int | None = None
    link: str | None = None


@metadata
class CommentMetadata:
    score: int | None = None
    creation_date: int | None = None
    content_license: str | None = None
    link: str | None = None
    owner: ShallowUserMetadata | None = None
    body_markdown: str | None = None


@metadata
class AnswerMetadata:
    is_accepted: bool | None = None
    awarded_bounty_amount: int | None = None
    score: int | None = None
    up_vote_count: int | None = None
    down_vote_count: int | None = None
    owner: ShallowUserMetadata | None = None
    creation_date: int | None = None
    last_edit_date: int | None = None
    community_owned_date: int | None = None
    content_license: str | None = None
    share_link: str | None = None
    comments: list[CommentMetadata] | None = None


@metadata
class QuestionMetadata:
    title: str | None = None
    tags: list[str] | None = None
    view_count: int | None = None
    score: int | None = None
    up_vote_count: int | None = None
    down_vote_count: int | None = None
    owner: ShallowUserMetadata | None = None
    creation_date: int | None = None
    last_edit_date: int | None = None
    community_owned_date: int | None = None
    content_license: str | None = None
    share_link: str | None = None
    comments: list[CommentMetadata] | None = None

# endregion
