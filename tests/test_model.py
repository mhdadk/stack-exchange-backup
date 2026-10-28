import io
import warnings

import attrs
import pytest

from stackexchange.api import StackExchangeApi

# noinspection PyProtectedMember
from stackexchange.model import (
    Comment,
    Paging,
    Parameters,
    Question,
    QuestionMetadata,
    ShallowUser,
    SitesParameters,
    parameters,
    path_param,
)

# noinspection PyProtectedMember
from stackexchange.serdes import (
    metadata_converter,
    query_converter,
    unstructure_as_batched_vectors,
)


@pytest.fixture(scope="module", name="api")
def api_fixture():
    return StackExchangeApi()


@pytest.fixture(scope="module", name="params")
def params_fixture():
    Parameters.DEFAULT_VECTOR_LIMIT = 4

    # pylint: disable=too-few-public-methods
    @parameters
    class CustomParameters:
        p_vector: list[int] = path_param(vector_limit=2)
        p_vector_default: list[int] = path_param()
        p_vector_invalid: int = path_param(vector_limit=5)
        p_primitive: str = path_param()
        q_vector: list[str] | None = attrs.field(
            default=None,
            metadata={Parameters.VECTOR_LIMIT_KEY: 3}
        )
        q_vector_default: list[str] | None = None
        q_primitive: str | None = None
        q_none: int | None = None
        q_nested: Paging | None = None

    params = CustomParameters(
        p_vector=[1, 2, 3],
        p_vector_default=[1, 2, 3, 4, 5, 6, 7, 8, 9],
        p_vector_invalid=4,
        p_primitive="tag",
        q_vector=["a", "b", "c", "d"],
        q_vector_default=["e", "f", "g", "h", "i"],
        q_primitive="f",
        q_nested=Paging(page=2, pagesize=7),
    )
    return params


def test_parameters_post_init(api):
    page_size = 2 ** 31 - 2
    assert Parameters.MAX_PAGE_SIZE < page_size
    with pytest.raises(ValueError):
        SitesParameters(paging=Paging(pagesize=page_size))
    with attrs.validators.disabled():
        params = SitesParameters(paging=Paging(pagesize=page_size))
    # The following demo code is outside the scope of this test module,
    # and should therefore not affect the outcome of this test case,
    # even though the assertion statement is expected to pass.
    try:
        sites = next(api.sites(params,
                               auto_pagination=False,
                               items_only=False))
        assert ((paging := params.paging) is not None
                and (pagesize := paging.pagesize) is not None
                and Parameters.MAX_PAGE_SIZE < len(sites.items or []) < pagesize)
    # ruff: ignore[BLE001]
    except Exception as e:  # pylint: disable=broad-exception-caught
        warnings.warn(UserWarning(f"sample code unexpectedly failed:\n{e}"))


def test_path_param_unstructure(params):
    # noinspection PyDataclass, PyTypeChecker
    fields_dict = attrs.fields_dict(type(params))
    for path_param_name, expected in (
            ("p_vector", ["1;2", "3"]),
            ("p_vector_default", ["1;2;3;4", "5;6;7;8", "9"]),
            ("p_vector_invalid", 4),
            ("p_primitive", "tag"),
    ):
        path_param_ = getattr(params, path_param_name)
        actual = (unstructure_as_batched_vectors(path_param_,
                                                 fields_dict[path_param_name])
                  if isinstance(path_param_, list)
                  else path_param_)
        assert actual == expected


def test_query_converter_unstructure(params):
    actual = query_converter.unstructure(params)
    expected = {
        "q_vector": ["a;b;c;d"],
        "q_vector_default": ["e;f;g;h;i"],
        "q_primitive": "f",
        "page": 2,
        "pagesize": 7,
    }
    assert actual == expected


def test_metadata_converter_dumps():
    question = Question(
        title="abc",
        tags=["c", "c++"],
        owner=ShallowUser(
            user_type="registered",
            display_name="anon",
        ),
        score=3,
        creation_date=1295365453,
        last_edit_date=4223295365453,
        comments=[
            Comment(
                creation_date=1246435483,
                content_license="CC BY-SA 2.5",
                body_markdown="No comment.",
            ),
        ],
    )
    question_dict = query_converter.unstructure(question)
    question_metadata = metadata_converter.structure(question_dict,
                                                     QuestionMetadata)
    with io.StringIO() as output:
        metadata_converter.dumps(question_metadata, output)
        actual = output.getvalue()
    expected = """---
title: abc
tags:
- c
- c++
score: 3
owner:
  display_name: anon
  user_type: registered
creation_date: '2011-01-18T15:44:13Z'
last_edit_date: 4223295365453 seconds since the Unix epoch
content_license: '[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/)?'
comments:
- creation_date: '2009-07-01T08:04:43Z'
  content_license: '[CC BY-SA 2.5](https://creativecommons.org/licenses/by-sa/2.5/)'
  body_markdown: |-
    No comment.
---
"""
    assert actual == expected
