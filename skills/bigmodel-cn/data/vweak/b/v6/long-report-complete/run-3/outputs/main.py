#!/usr/bin/env python3
import os
import requests

# API Key from environment variable
api_key = os.environ['ZHIPUAI_API_KEY']

# Base URL for ZhipuAI API
base_url = 'https://open.bigmodel.cn/api/paas/v4'

# Function to generate market report
def generate_market_report():
    # Define the prompt for the GLM model
    prompt = {'model': 'glm-5.3',
             'messages': [{'role': 'user', 'content': 'Please generate a market report on the export of new energy vehicles in China in 2026, with specific data and subheadings. The report should be at least 600 words long.'}],
             'stream': False
            }

    # Make the API request
    response = requests.post(f'{base_url}/chat/completions',
                             headers={'Authorization': f'Bearer {api_key}'},
                             json=prompt)

    # Check if the request was successful
    if response.status_code == 200:
        # Extract the generated text from the response
        generated_text = response.json()['choices'][0]['message']['content']

        # Check if the generated text is at least 600 words long
        if len(generated_text.split()) >= 600:
            return generated_text
        else:
            # Generate additional content to meet the word count requirement
            additional_content = requests.post(f'{base_url}/chat/completions',
                                               headers={'Authorization': f'Bearer {api_key}'},
                                               json={'model': 'glm-5.3',
                                                    'messages': [{'role': 'user', 'content': 'The generated text is too short. Please add more content to reach a total of at least 600 words.'}],
                                                   'stream': False
                                                  })
            if additional_content.status_code == 200:
                additional_text = additional_content.json()['choices'][0]['message']['content']
                return generated_text + additional_text
    else:
        raise Exception('Failed to generate market report.')

# Generate and print the market report
generate_market_report()