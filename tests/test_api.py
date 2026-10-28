from http import HTTPMethod
from pprint import pprint

import pytest
from requests import HTTPError

from stackexchange.api import StackExchangeApi
from stackexchange.model import (
    CreateFilterParameters,
    SimulateErrorParameters,
)
from stackexchange.serdes import query_converter


@pytest.fixture(scope="module", name="api")
def api_fixture():
    return StackExchangeApi()


def test_singleton_metaclass(api):
    api1 = StackExchangeApi(api_key="key", access_token="token")
    api2 = StackExchangeApi(api_key="key", access_token="token")
    assert api is not api1
    assert api2 is api1


def test_simulate_error(api):
    with pytest.raises(HTTPError) as err:
        api.simulate_error(SimulateErrorParameters(id=404))
    assert ((error_response := err.value.response) is not None
            and error_response.json() == {
                "error_id": 404,
                "error_name": "no_method",
                "error_message": "simulated",
            })


# An easier alternative to https://api.stackexchange.com/docs/create-filter
# for writing complex filters from scratch.
def test_create_filter_method_post(api):
    created_filter = api.create_filter(
        CreateFilterParameters(
            include=[
                # You should almost always include these fields in the filter:
                ".backoff",
                ".has_more",
                ".items",
                ".quota_remaining",
                # Specify the rest of your include fields below:
            ],
            exclude=[
                # You should almost always exclude these fields in the filter:
                ".total",
                # Specify the rest of your exclude fields below:
            ],
            base="none",
        ),
        http_method=HTTPMethod.POST,
    )
    pprint(query_converter.unstructure(created_filter),
           indent=2,
           sort_dicts=False)
