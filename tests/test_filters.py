from typing import (
    Literal,
    TypeAlias,
    TypeIs,
    get_args,
)

import pytest

from stackexchange.api import StackExchangeApi
from stackexchange.model import (
    BakedInFilter,
    Filter,
    ReadFilterParameters,
)

# ruff: ignore[UP040]
FilterType: TypeAlias = Literal["safe", "unsafe", "invalid"]


@pytest.fixture(scope="module", name="custom_filters")
def custom_filters_fixture():
    api = StackExchangeApi()
    # pylint: disable=no-member
    baked_in_filters = get_args(BakedInFilter.__value__)
    return sorted(
        api.read_filter(ReadFilterParameters(filters=list(baked_in_filters))),
        key=lambda f: f.filter or "",
    )


@pytest.fixture(scope="module", name="defined_filters")
def defined_filters_fixture():
    def is_filter_type(filter_type: str) -> TypeIs[FilterType]:
        assert filter_type in get_args(FilterType)
        return True

    return sorted(
        (
            Filter(
                filter=filter_,
                filter_type=filter_type,
                included_fields=sorted(included_fields),
            )
            for filter_, filter_type, included_fields in
            (
                (
                    "!-0ttWpKaHtrB(oS",
                    "safe",
                    [
                        ".backoff",
                        ".has_more",
                        ".items",
                        ".quota_remaining",
                        ".total",
                    ],
                ),
                (
                    "!2SUoF4c)sOul00Zq",
                    "safe",
                    [
                        ".backoff",
                        ".has_more",
                        ".items",
                        ".quota_remaining",
                        "network_user.site_url",
                        "network_user.user_id",
                    ],
                ),
                # Due to a bug mentioned in
                # https://meta.stackexchange.com/q/247899,
                # we must also include comment.body in the filter
                # in order to get comment.body_markdown in the response.
                (
                    # pylint: disable=line-too-long
                    "r8cwHZB3p97RraWJSdBqs7HCWXUCebDx9Wuhn_ChbmNDTEZ3_1lkd3suiMKEh6U-zwe.EML1(4mmULGTB",
                    "unsafe",
                    [
                        ".backoff",
                        ".has_more",
                        ".items",
                        ".quota_remaining",
                        "answer.answer_id",
                        "answer.awarded_bounty_amount",
                        "answer.body_markdown",
                        "answer.comments",
                        "answer.community_owned_date",
                        "answer.content_license",
                        "answer.creation_date",
                        "answer.down_vote_count",
                        "answer.is_accepted",
                        "answer.last_edit_date",
                        "answer.owner",
                        "answer.question_id",
                        "answer.score",
                        "answer.share_link",
                        "answer.up_vote_count",
                        "comment.body",
                        "comment.body_markdown",
                        "comment.content_license",
                        "comment.creation_date",
                        "comment.link",
                        "comment.owner",
                        "comment.score",
                        "question.answers",
                        "question.body_markdown",
                        "question.comments",
                        "question.community_owned_date",
                        "question.content_license",
                        "question.creation_date",
                        "question.down_vote_count",
                        "question.last_edit_date",
                        "question.owner",
                        "question.question_id",
                        "question.score",
                        "question.share_link",
                        "question.tags",
                        "question.title",
                        "question.up_vote_count",
                        "question.view_count",
                        "shallow_user.display_name",
                        "shallow_user.link",
                        "shallow_user.reputation",
                        "shallow_user.user_type",
                    ],
                ),
                (
                    "!6aC-iR(QLBu-5SKm",
                    "safe",
                    [
                        ".backoff",
                        ".has_more",
                        ".items",
                        ".quota_remaining",
                        "answer.question_id",
                    ],
                ),
            )
            if is_filter_type(filter_type)
        ),
        key=lambda f: f.filter or "",
    )


@pytest.mark.parametrize(
    ("custom", "defined"),
    [("custom_filters", "defined_filters")],
)
def test_filters(custom, defined, request):
    actual = request.getfixturevalue(custom)
    expected = request.getfixturevalue(defined)
    assert actual == expected
