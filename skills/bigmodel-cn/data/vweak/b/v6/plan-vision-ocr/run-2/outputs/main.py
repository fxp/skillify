#!/usr/bin/env python3

import os
import requests

# Load the API key from the environment variable
api_key = os.getenv('GLM_CODING_PLAN_API_KEY')

# Set the base URL for the GLM Coding Plan API
base_url = 'https://open.bigmodel.cn/api/coding/paas/v4'

# Define the function to call the API and extract text from the invoice image
def extract_text_from_invoice(image_path):
    # Define the API endpoint for image processing
    endpoint = '/images/ocr'
    # Prepare the request data
    data = {'file': (image_path, open(image_path, 'rb'), 'image/jpeg')}
    # Make the API request
    response = requests.post(f'{base_url}{endpoint}', headers={'Authorization': f'Bearer {api_key}'}).
    # Check if the request was successful
    if response.status_code == 200:
        # Parse the response and extract the text
        result = response.json()
        text = result.get('text', '')
        return text
    else:
        # Return an error message
        return 'Error: Unable to process the invoice image.'

# Define the main function
def main():
    # Set the path to the invoice image
    invoice_image_path = 'invoice.png'
    # Call the function to extract text from the invoice image
    text = extract_text_from_invoice(invoice_image_path)
    # Print the extracted text
    print('Extracted text from invoice image:')
    print(text)
    # Print the name of the model used by the API
    print('Model used by the API:', response.json().get('model', ''))

# Run the main function
if __name__ == '__main__':
    main()