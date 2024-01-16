"""
Given a network user id <user_id>, this script downloads all questions and answers for
the corresponding user into the following directories:
TODO: change this so that the stack exchange sites are at the top level and the
"questions" and "answers" folders are below them.

questions
|--- stack exchange site 1
|---|--- question_1.md
|---|--- question_2.md
|---|--- ...
|--- stack exchange site 2
|---|--- question_1.md
|---|--- question_2.md
|---|--- ...
answers
|--- stack exchange site 1
|---|--- answer_1.md
|---|--- answer_2.md
|---|--- ...
|--- stack exchange site 2
|---|--- answer_1.md
|---|--- answer_2.md
|---|--- ...

To do this, this script proceeds as follows:
1. Create a filter using the "/filters/create" method to get the network_user.account_id
field from the network_users object returned by the "/users/{ids}/associated" method.
2. Get all "network_user.account_id"'s for all stack exchange sites associated with
the <user_id> using the "/users/{ids}/associated" method.
3. For questions, create a filter using the "/filters/create" method to get the
following fields from the "question" object type
(https://api.stackexchange.com/docs/types/question):
- answers
- body_markdown
- comments
- creation_date
- down_vote_count
- up_vote_count
- score
4. For answers, create a filter using the "/filters/create" method to get the
following fields from the "answer" object type
(https://api.stackexchange.com/docs/types/answer):
- question_id (go to the question and download it with the answers)
TODO: remove these
- accepted
- body_markdown
- comments
- creation_date
- is_accepted
- down_vote_count
- up_vote_count
- score
- question_id
5. For each site extracted from step 2, do the following:
    a. For each question extracted from this site, do the following:
        i. Extract the fields mentioned in step 3 above using the created filter.
        ii. Open a .md file and put the question, along with the answers, into the
        file.
    b. For each answer extracted from this site, do the following:
        i. Extract the question_id field using the filter created in step 4.
        ii. Open a .md file and put the question, along with the extracted answer, into
        the file.

NOTE: According to https://api.stackexchange.com/docs/paging, each response will
have a maximum number of 100 items (the "pagesize" parameter) under the "items"
field. Therefore, if there are more than 100 questions, we will need to process
the first 100 questions, request the next 100 questions, process those, and so on,
until the "has_more" property is set to "False". To request the next 100 questions,
we will need to set the "page" property under the ".wrapper" category to "2", where
this property was set to "1" for the first page. See
https://api.stackexchange.com/docs/wrapper for details. Keep this in mind when
making any request.


NOTE: no need for "api_site_parameter" name. See https://api.stackexchange.com/docs
> Each of these methods operates on a single site at a time, identified by the site
> parameter. This parameter can be the full domain name (ie. "stackoverflow.com"), or a
> short form identified by api_site_parameter on the site object. 

NOTE: need the API key for this app to get a higher quota. See
https://stackapps.com/apps/oauth/view/28114

NOTE: authorization using an access_token is optional and only needed once. It is used
to access specific methods that are restricted for authentication.
Before doing all of this, you will need to authorize this stack app by going to the
following URL ONLY ONCE:
https://stackoverflow.com/oauth/dialog?client_id=28114&redirect_uri=https://stackoverflow.com/oauth/login_success

You will then need to get the access token. See this answer for details:
https://stackapps.com/a/6638/120681

NOTE: the access token is valid for 1 day only and changes every time you authorize
"""

import requests
import argparse
import pathlib
import datetime

# parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--user_id",
                    help='User network ID',
                    required=True,
                    type=str)
args = parser.parse_args()

# need this for a higher request quota per day. See
# https://api.stackexchange.com/docs/authentication for details
api_key = "YLTVFmHkeJbm7ZIOoXstag(("

# this must appear before every request
base_url = "https://api.stackexchange.com/2.3/"

# step 1
r = requests.get(base_url + f"filters/create",
                 params={"key":api_key,
                         "include":".items;\
                                    .has_more;\
                                    .page;\
                                    .pagesize;\
                                    .quota_max;\
                                    .quota_remaining;\
                                    network_user.site_url;\
                                    network_user.user_id",
                         "base":"none",
                         "unsafe":"false"})
network_users_filter = r.json()['items'][0]['filter']

# step 2
has_more = True
page_num = 0
site_names = []
user_ids = []
while has_more:
    if has_more:
        page_num += 1
    # note that the "page" parameter must start at 1. See
    # https://api.stackexchange.com/docs/paging. Also, the "types" parameter is used to
    # get both the main sites (e.g. math.stackexchange.com) and their corresponding
    # meta sites (e.g. math.meta.stackexchange.com)
    r = requests.get(base_url + f"users/{args.user_id}/associated",
                    params={"key":api_key,
                            "filter":network_users_filter,
                            "page":str(page_num),
                            "pagesize":"100",
                            "types":"main_site;meta_site"})
    data = r.json()
    # has_more will be set to False if there are no more pages to request, which
    # breaks us out of this loop
    has_more = data['has_more']
    # extract the site names and their corresponding user ids
    for item in data['items']:
        user_ids.append(item['user_id'])
        site_url = item['site_url']
        # skip the first 8 characters in the site url to get the site name. This will be
        # used later to query each site
        site_names.append(site_url[8:])

print(f"Found {len(site_names)} sites associated with network user {args.user_id}.")

# step 3
"""
NOTE: need the "shallow_user.display_name" field to return the owner associated with
a question or answer, since the return type is "shallow_user". If the owner is not
returned, then this is a community wiki post.
"""
r = requests.get(base_url + f"filters/create",
                 params={"key":api_key,
                         "include":".items;\
                                    .has_more;\
                                    .quota_max;\
                                    .quota_remaining;\
                                    shallow_user.display_name;\
                                    question.answers;\
                                    question.title;\
                                    question.body_markdown;\
                                    question.comments;\
                                    question.creation_date;\
                                    question.down_vote_count;\
                                    question.up_vote_count;\
                                    question.score;\
                                    question.owner;\
                                    question.link;\
                                    question.question_id;\
                                    answer.body_markdown;\
                                    answer.owner;\
                                    answer.comments;\
                                    answer.creation_date;\
                                    answer.is_accepted;\
                                    answer.down_vote_count;\
                                    answer.up_vote_count;\
                                    answer.score;\
                                    comment.body_markdown;\
                                    comment.creation_date;\
                                    comment.owner;\
                                    comment.score",
                         "base":"none",
                         "unsafe":"false"})
questions_filter = r.json()['items'][0]['filter']

# step 4
r = requests.get(base_url + f"filters/create",
                 params={"key":api_key,
                         "include":".items;\
                                    .has_more;\
                                    .quota_max;\
                                    .quota_remaining;\
                                    answer.question_id",
                         "base":"none",
                         "unsafe":"false"})
answers_filter = r.json()['items'][0]['filter']

# step 5

# create the top level directory and do nothing if it already exists
top_level_dir = pathlib.Path("q_and_a")
top_level_dir.mkdir(exist_ok=True)

def write_question(target_dir,question):
    # open the file "questions_dir/<question id>.md" to write to it. Note that the
    # <question id> can be used to contruct the URL for the question as
    # https://<site_name>/<question id>
    # Also, we don't use the question title as the file name because the question
    # title can contain invalid characters (such as "$" for LaTeX). We use the
    # question ID instead.
    f = (target_dir / str(question['question_id'])).with_suffix(".md").open(mode="w")
    # question metadata
    f.write(f"Question downloaded from {question['link']}\n")
    creation_datetime = datetime.datetime.fromtimestamp(question['creation_date'],
                                                        tz=datetime.timezone.utc)
    # question may be a community wiki, in which case it has no owner
    if "owner" in question:
        f.write(f"Question asked by {question['owner']['display_name']} on \
                    {creation_datetime.strftime('%Y-%m-%d')} at \
                    {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
    else:
        f.write(f"Question is community-owned and was asked on \
                    {creation_datetime.strftime('%Y-%m-%d')} at \
                    {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
    f.write(f"Number of up votes: {question['up_vote_count']}\n")
    f.write(f"Number of down votes: {question['down_vote_count']}\n")
    f.write(f"Score: {question['score']}\n")
    # question title
    f.write(f"# {question['title']}\n")
    # question body
    f.write(f"{question['body_markdown']}\n")
    # comments to the question
    # NOTE: it is safer to use the ".get" method on the dict "question" because it may
    # be the case that the 'comments' field does not exist, such as when there are
    # no comments on the question
    for i,comment in enumerate(question.get('comments',[])):
        f.write(f"### Comment {i+1}\n")
        creation_datetime = datetime.datetime.fromtimestamp(comment['creation_date'],
                                                            tz=datetime.timezone.utc)
        if "owner" in comment:
            f.write(f"Comment made by {comment['owner']['display_name']} on \
                    {creation_datetime.strftime('%Y-%m-%d')} at \
                    {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
        else:
            f.write(f"Comment made anonymously and was asked on \
                    {creation_datetime.strftime('%Y-%m-%d')} at \
                    {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
        f.write(f"Comment score: {comment['score']}\n\n")
        f.write(f"{comment['body_markdown']}\n")
    # answers to the question and the comments on each answer
    for i,answer in enumerate(question.get('answers',[])):
        f.write(f"## Answer {i+1}\n")
        creation_datetime = datetime.datetime.fromtimestamp(answer['creation_date'],
                                                            tz=datetime.timezone.utc)
        if "owner" in answer:
            f.write(f"Answer by {answer['owner']['display_name']} on \
                    {creation_datetime.strftime('%Y-%m-%d')} at \
                    {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
        else:
            f.write(f"Anonymous answer that was created on \
                    {creation_datetime.strftime('%Y-%m-%d')} at \
                    {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
        if answer['is_accepted']:
            f.write("This is the accepted answer.\n")
        else:
            f.write("This is not the accepted answer.\n")
        f.write(f"Number of up votes: {answer['up_vote_count']}\n")
        f.write(f"Number of down votes: {answer['down_vote_count']}\n")
        f.write(f"Score: {answer['score']}\n\n")
        f.write(f"{answer['body_markdown']}\n")
        # comments on the answer
        for j,comment in enumerate(answer.get('comments',[])):
            f.write(f"### Comment {j+1}\n")
            creation_datetime = datetime.datetime.fromtimestamp(comment['creation_date'],
                                                                tz=datetime.timezone.utc)
            if "owner" in comment:
                f.write(f"Comment made by {comment['owner']['display_name']} on \
                        {creation_datetime.strftime('%Y-%m-%d')} at \
                        {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
            else:
                f.write(f"Comment made anonymously and was asked on \
                        {creation_datetime.strftime('%Y-%m-%d')} at \
                        {creation_datetime.strftime('%H:%M:%S')} UTC.\n")
            f.write(f"Comment score: {comment['score']}\n\n")
            f.write(f"{comment['body_markdown']}\n")
    # close the file after you are done writing
    f.close()

# iterate over the sites
for i,(site_name,user_id) in enumerate(zip(site_names,user_ids)):
    print(f"Downloading and writing questions from site \
          {i+1}/{len(site_names)} ({site_name})...",end="")
    # create the "questions" directory for this site
    questions_dir = top_level_dir / site_name / "questions"
    questions_dir.mkdir(parents=True,exist_ok=True)
    """
    get all questions for this site
    NOTE: According to https://api.stackexchange.com/docs/paging, each response will
    have a maximum number of 100 items (the "pagesize" parameter) under the "items"
    field. Therefore, if there are more than 100 questions, we will need to process
    the first 100 questions, request the next 100 questions, process those, and so on,
    until the "has_more" property is set to "False". To request the next 100 questions,
    we will need to set the "page" property under the ".wrapper" category to "2", where
    this property was set to "1" for the first page. See
    https://api.stackexchange.com/docs/wrapper for details. 
    """
    # get all questions for this site
    r = requests.get(base_url + f"users/{user_id}/questions",
                     params={"key":api_key,
                             "site":site_name,
                             "filter":questions_filter})
    questions = r.json()['items']
    for question in questions:
        write_question(questions_dir,question)
    print(f"Done.")
    print(f"Downloading and writing answers from site \
          {i+1}/{len(site_names)} ({site_name})...",end="")
    # create the "answers" directory for this site
    answers_dir = top_level_dir / site_name / "answers"
    answers_dir.mkdir(parents=True,exist_ok=True)
    # get all answers for this site
    r = requests.get(base_url + f"users/{user_id}/answers",
                     params={"key":api_key,
                             "site":site_name,
                             "filter":answers_filter})
    answers = r.json()['items']
    # extract the question IDs and put them into a query string
    question_ids = ""
    for i,answer in enumerate(answers):
        question_ids += f"{answer['question_id']}"
        # don't put a semicolon at the end of the query string
        if i < len(answers) - 1:
            question_ids += ";"
    # get all the questions associated with these answers
    r = requests.get(base_url + f"questions/{question_ids}",
                     params={"key":api_key,
                             "site":site_name,
                             "filter":questions_filter})
    questions = r.json()['items']
    for question in questions:
        write_question(questions_dir,question)

    print(r)