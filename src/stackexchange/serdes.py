import datetime
import functools
from collections.abc import Callable, Generator
from typing import (
    Any,
    get_args,
    get_origin,
)

import attrs
import cattrs.preconf.json
import cattrs.preconf.pyyaml
from cattrs import Converter, override

# noinspection PyProtectedMember
from cattrs.gen import (
    is_generic,  # pyright: ignore [reportPrivateImportUsage]
    make_dict_structure_fn,
    make_dict_unstructure_fn,
)
from cattrs.preconf import wrap
from ruamel.yaml import YAML
from ruamel.yaml.scalarstring import LiteralScalarString

# noinspection PyProtectedMember
from stackexchange.model import (
    CommentMetadata,
    Metadata,
    Parameters,
    Response,
    content_license_options,
)

__all__ = [
    "query_converter",
    "metadata_converter",
]


# region Query converter


def exclude_unneeded_keys[T](unstructure_hook: Callable[[T], dict[str, Any]]) \
        -> Callable[[T], dict[str, Any]]:
    def wrapper(obj):
        dct = unstructure_hook(obj)
        # We exclude question.answers as they are split into their own files.
        # comment.body is added only to circumvent a bug, it is not needed.
        return {k: v for k, v in dct.items()
                if v is not None and k not in {"answers", "body"}}

    return wrapper


def unstructure_parameters_query(conv: Converter,
                                 params: Parameters) -> dict[str, Any]:
    param_keys_to_exclude = []
    # noinspection PyDataclass, PyTypeChecker
    for f in attrs.fields(type(params)):
        if Parameters.PATH_PARAMETER_KEY in f.metadata:
            param_keys_to_exclude.append(f.name)
        elif isinstance(param := getattr(params, f.name), list):
            setattr(params, f.name, unstructure_as_batched_vectors(param, f))
    params_as_dict: dict[str, Any] = conv.unstructure(params)
    return flatten_dict(params_as_dict,
                        lambda k, v:
                        k in frozenset(param_keys_to_exclude)
                        or v is None)


def unstructure_as_batched_vectors(param: list[Any],
                                   field_: attrs.Attribute) -> list[str]:
    vector_limit = (field_.metadata.get(Parameters.VECTOR_LIMIT_KEY,
                                        Parameters.DEFAULT_VECTOR_LIMIT)
                    if Parameters.PATH_PARAMETER_KEY in field_.metadata
                    else len(param))
    return [
        ";".join(str(e) for e in param[i:i + vector_limit])
        for i in range(0, len(param), vector_limit)
    ]


# https://www.freecodecamp.org/news/how-to-flatten-a-dictionary-in-python-in-4-different-ways/
def flatten_dict(dct: dict[str, Any],
                 exclude_func: Callable[[str, Any], bool]) -> dict[str, Any]:
    return dict(flatten_dict_generator(dct, exclude_func))


def flatten_dict_generator(dct: dict[str, Any],
                           exclude_func: Callable[[str, Any], bool]) \
        -> Generator[tuple[str, Any], None, None]:
    for k, v in dct.items():
        if exclude_func(k, v):
            continue
        if isinstance(v, dict):
            yield from flatten_dict(v, exclude_func).items()
        else:
            yield k, v


def structure_query_response[T](conv: Converter,
                                obj: dict[str, Any],
                                typ: type[Response[T]]) -> Response[T]:
    response_type = get_args(typ)[0]
    # noinspection PyTypeHints
    items_structure_hook = conv.get_structure_hook(list[response_type])
    items = obj.pop("items")
    response = Response(**obj)
    # noinspection PyTypeHints
    response.items = items_structure_hook(items, list[response_type])
    return response


# noinspection PyArgumentList
_json_converter = cattrs.preconf.json.make_converter(forbid_extra_keys=True)
_json_converter.register_unstructure_hook_factory(
    attrs.has,
    lambda cl: make_dict_unstructure_fn(cl, _json_converter)
)
_json_converter.register_structure_hook_factory(
    attrs.has,
    lambda cl: make_dict_structure_fn(cl, _json_converter)
)
query_converter = _json_converter.copy()
query_converter.register_unstructure_hook_factory(
    attrs.has,
    lambda cl: exclude_unneeded_keys(
        make_dict_unstructure_fn(cl, query_converter)
    )
)
query_converter.register_unstructure_hook_func(
    lambda cl: attrs.has(cl) and issubclass(cl, Parameters),
    functools.partial(unstructure_parameters_query, _json_converter)
)
query_converter.register_structure_hook_func(
    lambda cl: is_generic(cl) and get_origin(cl) is Response,
    functools.partial(structure_query_response, query_converter)
)


# endregion

# region Metadata converter

# RuamelyamlConverter and make_yaml_converter are adjusted from
# the code in the cattrs.preconf.pyyaml module.
class RuamelyamlConverter[T](Converter):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.yaml = self.init_yaml()

    @classmethod
    def init_yaml(cls) -> YAML:
        # Always use the pure Python implementation
        # to ensure more consistent behaviors across different environments.
        return YAML(typ="rt", pure=True)

    # https://yaml.dev/doc/ruamel.yaml/api/#top
    # If a parse or dump fails, and throws an exception,
    # the state of the YAML() instance is not guaranteed
    # to be able to handle further processing.
    # We should, at that point, recreate the YAML instance before proceeding.

    def dumps(self,
              obj: Any,
              stream: Any | None = None,
              unstructure_as: Any = None,
              **kwargs: Any) -> Any:
        try:
            if "transform" not in kwargs:
                kwargs["transform"] = lambda s: f"---\n{s}---\n"
            return self.yaml.dump(
                self.unstructure(obj, unstructure_as=unstructure_as),
                stream,
                **kwargs
            )
        except Exception:
            self.yaml = self.init_yaml()
            raise

    def loads(self, data: str, cl: type[T]) -> T:
        try:
            return self.structure(self.yaml.load(data), cl)
        except Exception:
            self.yaml = self.init_yaml()
            raise


@wrap(RuamelyamlConverter)
def make_yaml_converter(*args: Any, **kwargs: Any) -> RuamelyamlConverter:
    kwargs["unstruct_collection_overrides"] = {
        frozenset: list,
        **kwargs.get("unstruct_collection_overrides", {}),
    }
    res = RuamelyamlConverter(*args, **kwargs)
    cattrs.preconf.pyyaml.configure_converter(res)
    return res


def epoch_time_to_date_str(seconds_since_epoch: int | None) -> str | None:
    if seconds_since_epoch is not None:
        try:
            return (datetime.datetime
                    .fromtimestamp(seconds_since_epoch, tz=datetime.UTC)
                    .strftime("%Y-%m-%dT%H:%M:%SZ"))
        except (OverflowError, ValueError, OSError):
            return f"{seconds_since_epoch} seconds since the Unix epoch"
    return None


def linkify_content_license(content_license: str | None) -> str | None:
    if (content_license is not None
            and (applicable_license := content_license_options
                    .get(content_license.removesuffix("?")))):
        return (f"[{applicable_license.name}]({applicable_license.url})"
                + ("?" if content_license.endswith("?") else ""))
    else:
        return content_license


metadata_converter = make_yaml_converter()
metadata_converter.register_unstructure_hook_factory(
    lambda cl: attrs.has(cl) and issubclass(cl, Metadata),
    lambda cl: exclude_unneeded_keys(
        make_dict_unstructure_fn(
            cl,
            metadata_converter,
            **{  # pyright: ignore [reportArgumentType]
                field.name: override(
                    unstruct_hook=epoch_time_to_date_str
                    if field.name.endswith("_date")
                       and field.type in {"int | None", int | None}
                    else linkify_content_license
                    if field.name == "content_license"
                    else (lambda s: LiteralScalarString(s) if s else None)
                    if cl is CommentMetadata
                       and field.name == "body_markdown"
                    else None,
                )
                for field in attrs.fields(cl)
            }
        )
    )
)
metadata_converter.register_structure_hook_factory(
    lambda cl: attrs.has(cl) and issubclass(cl, Metadata),
    lambda cl: make_dict_structure_fn(cl, metadata_converter)
)

# endregion
