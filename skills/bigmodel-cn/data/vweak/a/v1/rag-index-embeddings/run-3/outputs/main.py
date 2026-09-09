#!/usr/bin/env python3

import requests

def load_api_key():
    return os.environ['ZHIPUAI_API_KEY']

def load_vectors():
    with open('vectors.json', 'r') as f:
        return json.load(f)

def cosine_similarity(a, b):
    dot_product = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x ** 2 for x in a))
    norm_b = math.sqrt(sum(y ** 2 for y in b))
    return dot_product / (norm_a * norm_b)

def query vectors, query_vector:
    similarities = [(cosine_similarity(query_vector, v), i) for i, v in enumerate(vectors)]
    return sorted(similarities, reverse=True)[:3], [vectors[i] for i in sorted(similarities, reverse=True)[:3]]

if __name__ == '__main__':
    api_key = load_api_key()
    vectors = load_vectors()
    query = '发票怎么开'
    print(query)
    print(query vectors, vectors[0])
    print(query vectors, vectors[1])
    print(query vectors, vectors[2])
