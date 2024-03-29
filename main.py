import requests
import argparse
import pathlib
import datetime
import html
import time

# parse command-line arguments
parser = argparse.ArgumentParser()
parser.add_argument("--user_id",
                    help='User network ID',
                    required=True,
                    type=str)
args = parser.parse_args()

# need this Stack API key for a higher request quota per day.
# See also https://api.stackexchange.com/docs/authentication for details
api_key = "YLTVFmHkeJbm7ZIOoXstag(("

# this must appear before every request
base_url = "https://api.stackexchange.com/2.3/"

#%% step 1
"""
Filters are useful for saving bandwidth and getting only the fields that you need in the
response. See https://api.stackexchange.com/docs/filters for details.

There is no need for the "api_site_parameter" name if you have the site URL. See
https://api.stackexchange.com/docs, where it states:
> Each of these methods operates on a single site at a time, identified by the site
> parameter. This parameter can be the full domain name (ie. "stackoverflow.com"), or a
> short form identified by api_site_parameter on the site object.

Need the ".backoff" parameter to detect throttling. See https://api.stackexchange.com/docs/throttle
for details.
"""
r = requests.get(base_url + f"filters/create",
                 params={"key":api_key,
                         "include":".items;"\
                                   ".has_more;"\
                                   ".page;"\
                                   ".page_size;"\
                                   ".quota_max;"\
                                   ".quota_remaining;"\
                                   ".backoff;"\
                                   "network_user.site_url;"\
                                   "network_user.user_id",
                         "base":"none",
                         "unsafe":"false"})
network_users_filter = r.json()['items'][0]['filter']

"""
According to https://api.stackexchange.com/docs/paging, each response will
have a maximum number of 100 items (the "pagesize" parameter) under the "items"
field. Therefore, if there are more than 100 questions/answers/comment/etc., we will
need to process the first 100 questions, request the next 100 questions, process those,
and so on, until the "has_more" property is set to "False". To request the next 100
questions, we will need to set the "page" property under the ".wrapper" category to "2",
where this property was set to "1" for the first page. See
https://api.stackexchange.com/docs/wrapper for details. Keep this in mind when
making any request.
"""
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

print(f"Found {len(site_names)} Stack Exchange sites associated with "\
      f"https://stackexchange.com/users/{args.user_id}")

"""
For questions, create a filter using the "/filters/create" method to get the
following fields from the "question" object type
(https://api.stackexchange.com/docs/types/question):
- answers
- body_markdown
- comments
- creation_date
- down_vote_count
- up_vote_count
- score

Need the "shallow_user.display_name" field to return the owner associated with
a question or answer, since the return type is "shallow_user". If the owner is not
returned, then this is a community wiki post.

For some reason, I can't request the "comment.body_markdown" field without also
requesting the "comment.body" field. If I try to do this, I won't get the
"comment.body_markdown" field in the response.
"""
r = requests.get(base_url + f"filters/create",
                 params={"key":api_key,
                         "include":".items;"\
                                    ".has_more;"\
                                    ".page;"\
                                    ".page_size;"\
                                    ".quota_max;"\
                                    ".quota_remaining;"\
                                    ".backoff;"\
                                    "shallow_user.display_name;"\
                                    "question.answers;"\
                                    "question.title;"\
                                    "question.body_markdown;"\
                                    "question.comments;"\
                                    "question.creation_date;"\
                                    "question.down_vote_count;"\
                                    "question.up_vote_count;"\
                                    "question.score;"\
                                    "question.owner;"\
                                    "question.link;"\
                                    "question.question_id;"\
                                    "answer.body_markdown;"\
                                    "answer.owner;"\
                                    "answer.comments;"\
                                    "answer.creation_date;"\
                                    "answer.is_accepted;"\
                                    "answer.down_vote_count;"\
                                    "answer.up_vote_count;"\
                                    "answer.score;"\
                                    "comment.body;"\
                                    "comment.body_markdown;"\
                                    "comment.creation_date;"\
                                    "comment.owner;"\
                                    "comment.score",
                         "base":"none",
                         "unsafe":"false"})
questions_filter = r.json()['items'][0]['filter']

"""
For answers, create a filter using the "/filters/create" method to get the
following fields from the "answer" object type
(https://api.stackexchange.com/docs/types/answer):
- question_id (to go to the question and download it along with its answers)
"""
r = requests.get(base_url + f"filters/create",
                 params={"key":api_key,
                         "include":".items;"\
                                   ".has_more;"\
                                   ".page;"\
                                   ".page_size;"\
                                   ".quota_max;"\
                                   ".quota_remaining;"\
                                   ".backoff;"\
                                   "answer.question_id",
                         "base":"none",
                         "unsafe":"false"})
answers_filter = r.json()['items'][0]['filter']

#%% step 2
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
    # we are assuming that question IDs for each site are unique, so there is no
    # need to deliberately avoid overwriting
    fpath = (target_dir / str(question['question_id'])).with_suffix(".md")
    # if the file already exists, then skip it to save time
    if fpath.exists():
        return
    # see https://stackoverflow.com/a/42495690/13809128 for why "encoding" parameter is
    # needed
    f = fpath.open(mode="w",encoding="utf-8")
    # question metadata
    f.write(f"Question downloaded from {question['link']}\\\n")
    creation_datetime = datetime.datetime.fromtimestamp(question['creation_date'],
                                                        tz=datetime.timezone.utc)
    # question may be a community wiki, in which case it has no owner
    if "owner" in question:
        if "display_name" in question["owner"]:
            f.write(f"Question asked by {question['owner']['display_name']} on "\
                    f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                    f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
        else:
            f.write(f"Question is community-owned and was asked on "\
                    f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                    f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
    else:
        f.write(f"Question is community-owned and was asked on "\
                f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
    f.write(f"Number of up votes: {question['up_vote_count']}\\\n")
    f.write(f"Number of down votes: {question['down_vote_count']}\\\n")
    f.write(f"Score: {question['score']}\n")
    # question title
    f.write(f"# {question['title']}\n")
    # question body
    # See https://stackoverflow.com/q/2087370/13809128 for why "html.unescape" is
    # needed.
    f.write(html.unescape(f"{question['body_markdown']}\n"))
    # comments to the question
    # it is safer to use the ".get" method on the dict "question" because it may
    # be the case that the 'comments' field does not exist, such as when there are
    # no comments on the question
    for i,comment in enumerate(question.get('comments',[])):
        f.write(f"### Comment {i+1}\n")
        creation_datetime = datetime.datetime.fromtimestamp(comment['creation_date'],
                                                            tz=datetime.timezone.utc)
        if "owner" in comment:
            if "display_name" in comment["owner"]:
                f.write(f"Comment made by {comment['owner']['display_name']} on "\
                        f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                        f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
            else:
                f.write(f"Comment made anonymously and was asked on "\
                        f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                        f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
        else:
            f.write(f"Comment made anonymously and was asked on "\
                    f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                    f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
        f.write(f"Comment score: {comment['score']}\n\n")
        f.write(html.unescape(f"{comment['body_markdown']}\n"))
    # answers to the question and the comments on each answer
    for i,answer in enumerate(question.get('answers',[])):
        f.write(f"## Answer {i+1}\n")
        creation_datetime = datetime.datetime.fromtimestamp(answer['creation_date'],
                                                            tz=datetime.timezone.utc)
        if "owner" in answer:
            if "display_name" in answer["owner"]:
                f.write(f"Answer by {answer['owner']['display_name']} on "\
                        f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                        f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
            else:
                f.write(f"Anonymous answer that was created on "\
                        f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                        f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
        else:
            f.write(f"Anonymous answer that was created on "\
                    f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                    f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
        if answer['is_accepted']:
            f.write("This is the accepted answer.\\\n")
        else:
            f.write("This is not the accepted answer.\\\n")
        f.write(f"Number of up votes: {answer['up_vote_count']}\\\n")
        f.write(f"Number of down votes: {answer['down_vote_count']}\\\n")
        f.write(f"Score: {answer['score']}\n\n")
        f.write(html.unescape(f"{answer['body_markdown']}\n"))
        # comments on the answer
        for j,comment in enumerate(answer.get('comments',[])):
            f.write(f"### Comment {j+1}\n")
            creation_datetime = datetime.datetime.fromtimestamp(comment['creation_date'],
                                                                tz=datetime.timezone.utc)
            if "owner" in comment:
                if "display_name" in comment["owner"]:
                    f.write(f"Comment made by {comment['owner']['display_name']} on "\
                            f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                            f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
                else:
                    f.write(f"Comment made anonymously and was asked on "\
                        f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                        f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
            else:
                f.write(f"Comment made anonymously and was asked on "\
                        f"{creation_datetime.strftime('%Y-%m-%d')} at "\
                        f"{creation_datetime.strftime('%H:%M:%S')} UTC.\\\n")
            f.write(f"Comment score: {comment['score']}\n\n")
            f.write(html.unescape(f"{comment['body_markdown']}\n"))
    # close the file after you are done writing
    f.close()

# iterate over the sites
for i,(site_name,user_id) in enumerate(zip(site_names,user_ids)):
    print(f"Downloading and writing questions from site "\
          f"{i+1}/{len(site_names)} ({site_name})...",end="",flush=True)
    #%% step 3(a)
    # create the "questions" directory for this site
    questions_dir = top_level_dir / site_name / "questions"
    questions_dir.mkdir(parents=True,exist_ok=True)
    has_more = True
    page_num = 0
    while has_more:
        if has_more:
            page_num += 1
        #%% step 3(b)
        r = requests.get(base_url + f"users/{user_id}/questions",
                        params={"key":api_key,
                                "site":site_name,
                                "filter":questions_filter,
                                "page":str(page_num),
                                "pagesize":"100"})
        data = r.json()
        has_more = data['has_more']
        questions = data['items']
        #%% step 3(c)
        # if there are no questions associated with this site, then "questions"
        # will be an empty list, such that the following for loop will be skipped.
        for question in questions:
            write_question(questions_dir,question)
        """
        According to https://api.stackexchange.com/docs/throttle:

        > A dynamic throttle is also in place on a per-method level. If an application
        > receives a response with the backoff field set, it must wait that many seconds
        > before hitting the same method again. For the purposes of throttling, all /me
        > routes are considered to be identical to their /users/{ids} equivalent. Note
        > that backoff is set based on a combination of factors, and may not be
        > consistently returned for the same arguments to the same method. Additionally,
        > all methods (even seemingly trivial ones) may return backoff.

        So, we will need to wait a certain amount of time if the "backoff" parameter is
        returned in the response before making another request.
        """
        if "backoff" in data:
            print("We've made too many requests to the Stack Exchange API, so we will "\
                  f"need to wait for {data['backoff']} seconds. Please be patient...",flush=True)
            time.sleep(data['backoff'] + 1) # add a second just in case
            print(f"Downloading and writing the remaining questions from {site_name}...",
                  end="",flush=True)
    print(f"Done.")
    print(f"Downloading and writing answers from site "\
          f"{i+1}/{len(site_names)} ({site_name})...",end="",flush=True)
    #%% step 3(d)
    # create the "answers" directory for this site
    answers_dir = top_level_dir / site_name / "answers"
    answers_dir.mkdir(parents=True,exist_ok=True)
    has_more = True
    page_num = 0
    while has_more:
        backoff = False
        if has_more:
            page_num += 1
        #%% step 3(e)
        r = requests.get(base_url + f"users/{user_id}/answers",
                        params={"key":api_key,
                                "site":site_name,
                                "filter":answers_filter,
                                "page":str(page_num),
                                "pagesize":"100"})
        data = r.json()
        has_more = data['has_more']
        answers = data['items']
        # in case there are no answers associated with this site, skip it
        if len(answers) == 0:
            continue
        if "backoff" in data:
            backoff = True
            backoff_time = data["backoff"]
        #%% step 3(f)
        question_ids = ""
        for i,answer in enumerate(answers):
            question_ids += f"{answer['question_id']}"
            # don't put a semicolon at the end of the query string as this will throw
            # an error
            if i < len(answers) - 1:
                question_ids += ";"
        #%% step 3(g)
        # get all the questions associated with these answers. Since there will always
        # be a maximum of 100 answers, then there will always be 100 questions, and
        # so we don't need to iterate through pages here
        r = requests.get(base_url + f"questions/{question_ids}",
                        params={"key":api_key,
                                "site":site_name,
                                "filter":questions_filter,
                                "pagesize":"100"})
        data = r.json()
        questions = data['items']
        if "backoff" in data:
            if backoff: # if "backoff" is already needed from the previous method
                backoff_time = max(data["backoff"],backoff_time)
            else:
                backoff = True
                backoff_time = data["backoff"]
        for question in questions:
            write_question(answers_dir,question)
        if backoff:
            print("We've made too many requests to the Stack Exchange API, so we will "\
                f"need to wait for {backoff_time} seconds. Please be patient...",flush=True)
            time.sleep(backoff_time + 1) # add a second just in case
            print(f"Downloading and writing the remaining answers from {site_name}..."
                  ,end="",flush=True)
    print(f"Done.")
