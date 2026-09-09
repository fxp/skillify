#!/usr/bin/env python3

import json
import os
import requests
import numpy as np

# Read API Key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# API endpoint for embeddings
embedding_endpoint = 'https://open.bigmodel.cn/api/paas/v4/embeddings'

# Read the FAQ file and process each line
with open('faq.txt', 'r', encoding='utf-8') as faq_file:
    lines = faq_file.readlines()

    # Vectorize each line using the embedding model
    embeddings = []
    for line in lines:
        response = requests.post(embedding_endpoint, json=
            {
                'model': 'embedding-3',
                'input': [line.strip()]
            },
            headers=
            {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
        )
        data = response.json()
        embeddings.append(data['data'][0]['embedding'])

    # Convert embeddings to a NumPy array
    embeddings_array = np.array(embeddings)

    # Define a query line
    query_line = '发票怎么开'.strip()

    # Vectorize the query line
    query_embedding = np.array([requests.post(embedding_endpoint, json=
            {
                'model': 'embedding-3',
                'input': [query_line]
            },
            headers=
            {
                'Authorization': f'Bearer {api_key}',
                'Content-Type': 'application/json'
            }
        ).json()['data'][0]['embedding'])

    # Calculate cosine similarity between the query embedding and each embedding in the array
    cosine_similarities = np.dot(embeddings_array, query_embedding) / (np.linalg.norm(embeddings_array) * np.linalg.norm(query_embedding))

    # Get the top 3 most similar embeddings
    top_indices = np.argsort(cosine_similarities)[-3:]

    # Get the original lines for the top 3 embeddings
    top_lines = [lines[i].strip() for i in top_indices]

    # Print the top 3 lines
    for line in top_lines:
        print(line)