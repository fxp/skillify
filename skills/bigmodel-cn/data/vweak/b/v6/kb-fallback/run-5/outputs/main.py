#!/usr/bin/env python3

import os
import requests

# Fetch the API key from the environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Define the base URL for the Zhipu AI platform
base_url = "https://open.bigmodel.cn/api/"

# Define the endpoint for querying the knowledge base
knowledge_base_endpoint = base_url + "paas/v4/knowledge_base/search"

# Define the query to be used for searching the knowledge base
query = "退换货政策的有效期是多久"

# Make the request to the knowledge base endpoint
response = requests.post(knowledge_base_endpoint, headers={
    "Authorization": f"Bearer {api_key}"
}, json={
    "query": query
})

# Check if the request was successful
if response.status_code == 200:
    # Extract the search results from the response
    search_results = response.json().get("results", [])

    # Print the original text from the first search result
    if search_results:
        print(search_results[0].get("original_text"))
    else:
        print("No search results found.")
else:
    print("Failed to retrieve search results.")

# Clean up the temporary resources
import shutil
import tempfile

# Create a temporary directory
temp_dir = tempfile.mkdtemp()

# Copy the FAQ file into the temporary directory
with open("faq.txt", "r", encoding="utf-8") as file:
    with open(os.path.join(temp_dir, "faq.txt"), "w", encoding="utf-8") as temp_file:
        temp_file.write(file.read())

# Create a temporary knowledge base file
with open(os.path.join(temp_dir, "knowledge_base.json"), "w", encoding="utf-8") as file:
    file.write(json.dumps({}))

# Create a temporary configuration file
with open(os.path.join(temp_dir, "config.json"), "w", encoding="utf-8") as file:
    file.write(json.dumps({}))

# Remove the temporary directory
shutil.rmtree(temp_dir)