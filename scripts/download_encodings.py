#!/usr/bin/env python3
"""
A tokenizer is responsible for breaking down into smaller units called tokens.
Those *.tiktoken files contain the necessary configuration and vocabulary for tokenizing and detokenizing texts.
For example, cl100k_base.tiktoken is specifically defined for openAI models.

For other encodings look here : https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/tiktoken/model.py
    and eventually here for the URL : https://github.com/openai/tiktoken/blob/97e49cbadd500b5cc9dbb51a486f0b42e6701bee/tiktoken_ext/openai_public.py

in offline environments, tiktoken cannot download those encoding files, so we have to dispose them directly on the image,
    in a specific location, and under a specific name corresponding to a "cache key" based on source URL of the *.tiktoken file.

The script here calculate the cache key of the source URL of an encoding tiktoken file 
    then download the tiktoken file to the local tiktoken cache directory under the appropriate name 

"""

import requests
import hashlib
import sys
import os


## First step : The cache key
#### the encoding file must have a specific name corresponding to the cache key based on the source URL of the file 


# blobpath="https://openaipublic.blob.core.windows.net/encodings/cl100k_base.tiktoken"
blobpath=sys.argv[1]

cache_key=hashlib.sha1(blobpath.encode()).hexdigest()
print(cache_key)

## Second step download the *.tiktoken file and save it under the "cache key" name.

encodings_cache_directory = os.environ['TIKTOKEN_CACHE_DIR']

response = requests.get(blobpath)

if response.status_code == 200:
   with open( encodings_cache_directory + "/" + cache_key , "wb" ) as file:
      file.write(response.content)
   print("The encoding file have been properly downloaded and stored")
else:
   print(f"Download failure. Status: {response.status_code}")
