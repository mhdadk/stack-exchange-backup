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

Before doing all of this, you will need to authorize this stack app by going to the
following URL ONLY ONCE:
https://stackoverflow.com/oauth/dialog?client_id=28114&redirect_uri=https://stackoverflow.com/oauth/login_success

You will then need to get the access token. See this answer for details:
https://stackapps.com/a/6638/120681
"""

import requests

# step 1
