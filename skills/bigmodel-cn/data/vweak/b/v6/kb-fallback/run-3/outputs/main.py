#!/usr/bin/env python3

import os
import requests

# Read API Key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Function to search the knowledge base
def search_knowledge_base(question):
    url = "https://open.bigmodel.cn/api/paas/v4/knowledgebase/search"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    data = {
        "question": question
    }
    response = requests.post(url, headers=headers, json=data)
    return response.json()

# Function to read the FAQ file
def read_faq_file(filename):
    with open(filename, "r", encoding="utf-8") as file:
        return file.read()

# Main function
if __name__ == "__main__":
    # Read the FAQ file
    faq_content = read_faq_file("faq.txt")
    # Search the knowledge base
    search_results = search_knowledge_base("退换货政策的有效期是多久")
    # Print the search results
    print(search_results)
