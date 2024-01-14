"""
Given a network user id <user_id>, this script downloads all questions and answers for
the corresponding user in the following format:
questions
|--- stack exchange site 1
|---|--- question 1
|---|--- question 2
|---|--- ...
|--- stack exchange site 2
|---|--- question 1
|---|--- question 2
|---|--- ...
answers
|--- stack exchange site 1
|---|--- answer 1
|---|--- answer 2
|---|--- ...
|--- stack exchange site 2
|---|--- answer 1
|---|--- answer 2
|---|--- ...
"""

import requests

# get all the stack exchange sites associated with this account
