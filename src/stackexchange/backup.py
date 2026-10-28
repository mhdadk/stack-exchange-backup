from argparse import ArgumentParser, Namespace
from collections.abc import Sequence
from os import PathLike, scandir
from pathlib import Path
from shutil import rmtree
from typing import (
    Literal,
    TypeAlias,
    cast,
    get_args,
)

from attrs import (
    Factory,
    define,
    field,
)
from urllib3.util import parse_url

from stackexchange.api import StackExchangeApi
from stackexchange.model import (
    Answer,
    AnswerMetadata,
    AnswersOnUsersParameters,
    AssociatedUsersParameters,
    Question,
    QuestionMetadata,
    QuestionsByIdsParameters,
    QuestionsOnUsersParameters,
    SitesParameters,
)
from stackexchange.serdes import metadata_converter, query_converter

__all__ = [
    "NetworkUserInfo",
    "get_network_users",
    "acquire_missing_network_users",
    "backup_user_questions",
    "backup_user_answers",
    "create_output_file",
    "get_output_path",
]

# ruff: ignore[UP040]
OutputFormat: TypeAlias = Literal["markdown", "json"]


@define(frozen=True, kw_only=True)
class NetworkUserInfo:
    site_domain_name: str
    user_id: int
    user_question_ids: set[int] = field(default=Factory(set[int]), eq=False)


api = StackExchangeApi()


def main() -> None:
    args = parse_arguments()
    backup_root = Path(args.out_dir, f"stack_user_{args.account_id}").resolve()
    backup_root.mkdir(exist_ok=True)
    if args.clean:
        for entry in scandir(backup_root):
            if entry.is_dir() and not entry.name.startswith("."):
                rmtree(entry.path)
    global api  # pylint: disable=global-statement
    api = StackExchangeApi(api_key=args.api_key, limit_rate=args.limit_rate)
    network_users = get_network_users(args.account_id, args.no_meta)
    print(f"Found {len(network_users)} Stack Exchange sites associated with "
          + f"https://stackexchange.com/users/{args.account_id}/")
    for i, network_user in enumerate(network_users, start=1):
        print("Downloading and writing questions from site "
              + f"{i}/{len(network_users)} "
              + f"({network_user.site_domain_name})...",
              end="",
              flush=True)
        backup_user_questions(network_user, backup_root, args.format)
        print("Done.")
        print("Downloading and writing answers from site "
              + f"{i}/{len(network_users)} "
              + f"({network_user.site_domain_name})...",
              end="",
              flush=True)
        backup_user_answers(network_user, backup_root, args.format)
        print("Done.")


def parse_arguments(args: Sequence[str] | None = None) -> Namespace:
    parser = ArgumentParser(allow_abbrev=False)
    parser.add_argument(
        "--account-id",
        type=int,
        required=True,
        help="user account ID on stackexchange.com",
    )
    parser.add_argument(
        "--out-dir",
        default=".",
        type=str,
        help="output directory (defaults to the current working directory)",
    )
    parser.add_argument(
        "--format",
        default="markdown",
        type=str,
        choices=get_args(OutputFormat),
        help="output file format (default: %(default)s)",
    )
    parser.add_argument(
        "--no-meta",
        action="store_true",
        help="do not back up posts on meta sites",
    )
    parser.add_argument(
        "--clean",
        action="store_true",
        help="remove files from the stack_user_id subdirectory before back up",
    )
    parser.add_argument(
        "--api-key",
        default=StackExchangeApi.API_KEY,
        type=str,
        help="API key (for debugging only)",
    )
    parser.add_argument(
        "--limit-rate",
        default=10,
        type=int,
        help="maximum request rate in requests per second within the integer "
             + f"range of 1 and {StackExchangeApi.MAX_REQUESTS_PER_SECOND} "
             + "inclusive (default: %(default)d)",
    )
    parsed_args = parser.parse_args(args)
    validate_parsed_arguments(parsed_args, parser)
    return parsed_args


def validate_parsed_arguments(args: Namespace, parser: ArgumentParser) -> None:
    if not 1 <= args.limit_rate <= StackExchangeApi.MAX_REQUESTS_PER_SECOND:
        msg = ("argument --limit-rate: out of range int value: "
               + f"'{args.limit_rate}'")
        parser.error(msg)


def get_network_users(account_id: int, no_meta: bool = False) \
        -> set[NetworkUserInfo]:
    associated_users = api.associated_users(
        AssociatedUsersParameters(
            ids=[account_id],
            filter="!2SUoF4c)sOul00Zq",
            types=cast(list[Literal["main_site", "meta_site"]],
                       ["main_site"] if no_meta
                       else ["main_site", "meta_site"]),
        )
    )
    # noinspection PyUnboundLocalVariable, bad-argument-type
    network_users = set[NetworkUserInfo](
        NetworkUserInfo(
            site_domain_name=site_host,
            user_id=associated_user.user_id,
        )
        for associated_user in associated_users
        if associated_user.user_id
        and associated_user.site_url
        and (site_host := parse_url(associated_user.site_url).host)
        and (not no_meta or site_host not in
             {"meta.stackexchange.com", "stackapps.com"})
    )
    if not no_meta:
        acquire_missing_network_users(network_users)
    return network_users


def acquire_missing_network_users(network_users: set[NetworkUserInfo]) -> None:
    """
    Apply fix for :meth:`StackExchangeApi.associated_users` not
    returning results for meta sites.

    :param network_users:
    :return:
    """
    users_dict = {user.site_domain_name: user.user_id
                  for user in network_users}
    for site in api.sites(SitesParameters()):
        if (site.site_type == "main_site"
                and site.site_url
                and (site_host := parse_url(site.site_url).host)
                in users_dict):
            for related_site in site.related_sites or []:
                if (related_site.relation == "meta"
                        and related_site.site_url
                        and (
                                related_site_host
                                := parse_url(related_site.site_url).host
                        )):
                    network_users.add(
                        NetworkUserInfo(
                            site_domain_name=related_site_host,
                            user_id=users_dict[site_host],
                        )
                    )


def backup_user_questions(network_user: NetworkUserInfo,
                          backup_root: str | PathLike[str],
                          output_format: OutputFormat = "markdown") -> None:
    f = "r8cwHZB3p97RraWJSdBqs7HCWXUCebDx9Wuhn_ChbmNDTEZ3_1lkd3suiMKEh6U-zwe.EML1(4mmULGTB"
    questions = api.questions_on_users(
        QuestionsOnUsersParameters(
            ids=[network_user.user_id],
            site=network_user.site_domain_name,
            filter=f,
        )
    )
    for question in questions:
        if question.question_id is not None:
            network_user.user_question_ids.add(question.question_id)
            create_output_file(network_user,
                               backup_root,
                               output_format,
                               "q",
                               question)
            for answer in question.answers or []:
                create_output_file(network_user,
                                   backup_root,
                                   output_format,
                                   "q",
                                   answer)


def backup_user_answers(network_user: NetworkUserInfo,
                        backup_root: str | PathLike[str],
                        output_format: OutputFormat = "markdown") -> None:
    answers = api.answers_on_users(
        AnswersOnUsersParameters(
            ids=[network_user.user_id],
            site=network_user.site_domain_name,
            filter="!6aC-iR(QLBu-5SKm",
        )
    )
    not_my_question_ids = ({answer.question_id for answer in answers
                            if answer.question_id is not None}
                           - network_user.user_question_ids)
    if not not_my_question_ids:
        return
    f = "r8cwHZB3p97RraWJSdBqs7HCWXUCebDx9Wuhn_ChbmNDTEZ3_1lkd3suiMKEh6U-zwe.EML1(4mmULGTB"
    questions = api.questions_by_ids(
        QuestionsByIdsParameters(
            ids=list(not_my_question_ids),
            site=network_user.site_domain_name,
            filter=f,
        )
    )
    for question in questions:
        create_output_file(network_user,
                           backup_root,
                           output_format,
                           "a",
                           question)
        for answer in question.answers or []:
            create_output_file(network_user,
                               backup_root,
                               output_format,
                               "a",
                               answer)


def create_output_file(network_user: NetworkUserInfo,
                       backup_root: str | PathLike[str],
                       output_format: OutputFormat,
                       contribution_type: Literal["a", "q"],
                       post: Question | Answer) -> None:
    output_file = get_output_path(network_user,
                                  backup_root,
                                  output_format,
                                  contribution_type,
                                  post)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with output_file.open(mode="w", encoding="utf-8", newline="") as f:
        match output_format:
            case "markdown":
                post_dict = query_converter.unstructure(post)
                match post:
                    case Question():
                        frontmatter = metadata_converter.structure(
                            post_dict,
                            QuestionMetadata,
                        )
                    case Answer():
                        frontmatter = metadata_converter.structure(
                            post_dict,
                            AnswerMetadata,
                        )
                if frontmatter:
                    metadata_converter.dumps(frontmatter, f)
                if post.body_markdown:
                    f.write(post.body_markdown)
            case "json":
                f.write(query_converter.dumps(post, indent=2))


def get_output_path(network_user: NetworkUserInfo,
                    backup_root: str | PathLike[str],
                    output_format: OutputFormat,
                    contribution_type: Literal["a", "q"],
                    post: Question | Answer) -> Path:
    out_dir = (Path(backup_root,
                    network_user.site_domain_name,
                    contribution_type,
                    str(post.question_id))
               .resolve())
    out_dir.relative_to(backup_root)
    match output_format:
        case "markdown":
            suffix = ".md"
        case "json":
            suffix = ".json"
    match post:
        case Question():
            basename = "index"
        case Answer():
            basename = str(post.answer_id)
    output_file = Path(out_dir, basename).with_suffix(suffix)
    return output_file


if __name__ == "__main__":
    main()
