#!/usr/local/bin/python3
import sys
import requests

length = int(sys.argv[1])
offset = int(sys.argv[2])
url = 'https://archive.org/download/' + sys.argv[3]
try:
    filename = sys.argv[4]
except IndexError:
    filename = 'out.warc.gz'

headers = {'Range': f'bytes={offset}-{offset+length-1}'}
r = requests.get(url, headers=headers)
with open(filename, 'wb') as f:
    f.write(r.content)
