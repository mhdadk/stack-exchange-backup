# import requests

# url = "https://stats.stackexchange.com/questions/505358/one-class-classifier-vs-binary-classifier"

# r = requests.get(url)
# with open('test2.htm', 'w') as file:
#     file.write(r.text)

import requests
from bs4 import BeautifulSoup

url = "https://stats.stackexchange.com/questions/633692/when-are-random-variables-easier-to-use-than-sample-spaces/633695#633695"

# Send an HTTP request to the URL
response = requests.get(url)

# Check if the request was successful (status code 200)
if response.status_code == 200:
    # Parse the HTML content of the page using BeautifulSoup
    soup = BeautifulSoup(response.text, 'html.parser')

    # Save the content to a file (e.g., HTML or text file)
    with open("downloaded_page.html", "w", encoding="utf-8") as file:
        file.write(str(soup))

    print("Page downloaded successfully.")
else:
    print(f"Failed to download the page. Status code: {response.status_code}")
