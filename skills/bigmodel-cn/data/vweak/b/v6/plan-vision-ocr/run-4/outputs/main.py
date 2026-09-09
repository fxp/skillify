#!/usr/bin/env python3

import os
import requests

def main():
    invoice_path = 'invoice.png'
    api_key = os.getenv('GLM_CODING_PLAN_API_KEY')
    base_url = 'https://open.bigmodel.cn/api/coding/paas/v4'

    # Upload the image and get the file ID
    upload_response = requests.post(f'{base_url}/files', headers={'Authorization': f'Bearer {api_key}'}, files={'file': ('invoice.png', open(invoice_path, 'rb'), 'image/png')})
    if upload_response.status_code != 200:
        print('Failed to upload the image.')
        return
    file_id = upload_response.json().get('id')

    # Analyze the content of the image
    analyze_response = requests.post(f'{base_url}/images/analysis', headers={'Authorization': f'Bearer {api_key}'}, json={'file_id': file_id})
    if analyze_response.status_code != 200:
        print('Failed to analyze the image content.')
        return
    content = analyze_response.json().get('content')

    # Print the model response and the actual model used
    print('Model Response:', content)
    print('Model Used:', analyze_response.json().get('model_used'))

if __name__ == '__main__':
    main()