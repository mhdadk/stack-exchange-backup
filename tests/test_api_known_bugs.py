import pytest

from stackexchange.api import StackExchangeApi
from stackexchange.model import AssociatedUsersParameters, Paging


@pytest.fixture(scope="module", name="api")
def api_fixture():
    return StackExchangeApi()


def test_associated_users_parameters_types_meta_site(api):
    params = AssociatedUsersParameters(
        ids=[6],
        filter="!-0ttWpKaHtrB(oS",
        paging=Paging(page=1, pagesize=1),
        types=["meta_site"],
    )
    response = next(api.associated_users(params,
                                         auto_pagination=False,
                                         items_only=False))
    assert response.total > 1
    if response.items == [] or response.has_more is False:
        pytest.xfail("https://stackapps.com/q/8666/")
