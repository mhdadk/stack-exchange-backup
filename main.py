"""
Given a network user id <user_id>, this script downloads all questions and answers for
the corresponding user into the following directories:
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
                                    .quota_max;\
                                    .quota_remaining;\
                                    network_user.site_url;\
                                    network_user.user_id",
                         "base":"none",
                         "unsafe":"false"})
network_users_filter = r.json()['items'][0]['filter']

# step 2
r = requests.get(base_url + f"users/{args.user_id}/associated",
                 params={"key":api_key,"filter":network_users_filter})
site_names = []
user_ids = []
for item in r.json()['items']:
    user_ids.append(item['user_id'])
    site_url = item['site_url']
    # skip the first 8 characters in the site url to get the site name. This will be
    # used later to query different sites
    site_names.append(site_url[8:])

# step 3
r = requests.get(base_url + f"filters/create",
                 params={"key":api_key,
                         "include":".items;\
                                    .has_more;\
                                    .quota_max;\
                                    .quota_remaining;\
                                    question.answers;\
                                    question.title;\
                                    question.body_markdown;\
                                    question.comments;\
                                    question.creation_date;\
                                    question.down_vote_count;\
                                    question.up_vote_count;\
                                    question.score;\
                                    question.owner;\
                                    answer.body_markdown;\
                                    answer.comments;\
                                    answer.creation_date;\
                                    answer.is_accepted;\
                                    answer.down_vote_count;\
                                    answer.up_vote_count;\
                                    answer.score:\
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

# create the necessary directories (do nothing if they already exist)
p = pathlib.Path(".")
(p / "q_and_a").mkdir(exist_ok=True)
(p / "q_and_a" / "questions").mkdir(exist_ok=True)
(p / "q_and_a" / "answers").mkdir(exist_ok=True)

# iterate over the sites
for site_name,user_id in zip(site_names,user_ids):
    # get all questions for this site
    r = requests.get(base_url + f"users/{user_id}/questions",
                     params={"key":api_key,
                             "site":site_name,
                             "filter":questions_filter})
    print(r)