from flask import Flask, send_from_directory, request
from werkzeug.exceptions import NotFound
from contextlib import suppress
from subprocess import Popen, PIPE
from pathlib import Path
import requests
import urllib
import glob


BLACKLIST_FILE = 'blacklist.txt'
LENGTH = 8
OFFSET = 9
URL = 10

blacklist = []


def download_warc(length, offset, url, filename='out.warc.gz'):
    url = 'https://archive.org/download/' + url
    headers = {'Range': f'bytes={offset}-{offset+length-1}'}
    r = requests.get(url, headers=headers)
    with open(filename, 'wb') as f:
        f.write(r.content)


def get_blacklist():
    with open(BLACKLIST_FILE) as f:
        return f.read().split('\n')


def add_to_blacklist(path):
    with open(BLACKLIST_FILE, 'a') as f:
        f.write(path + '\n')


def serve_from_filesystem(path):
    filename = Path(path).name
    if '?' in filename:
        path = path[:path.rfind('?')]
    if path.startswith('games/') and path[path.rfind('/')+1:].isdecimal():
        game_number = path[path.rfind('/')+1:]
        with suppress(IndexError):
            path = glob.glob(f'gm/data/sandbox.yoyogames.com/games/{game_number}-*/index.html')[0]
            path = path[path.find('games/'):]
    elif len(filename.split('.')) == 1:
        path += '/index.html'
    return send_from_directory('data/sandbox.yoyogames.com/', path)


def find_file_in_index(path):
    quoted = urllib.parse.quote(path, safe='/?*')
    print(f'Searching for {quoted} in index')

    p = Popen(['ggrep', '-rie', quoted, 'cdx'], stdout=PIPE)
    for line in p.stdout:
        line = line.decode('utf8')[:-1].split()
        filename = line[0]
        filename = filename[filename.find(')')+2:]
        if path.startswith('games/') and path[path.rfind('/')+1:].isdecimal():
            if filename[:filename.find('-')] == path:
                p.kill()
                return line[LENGTH], line[OFFSET], line[URL]
        if path.endswith('send_download'):
            p.kill()
            return line[LENGTH], line[OFFSET], line[URL]
        if filename == quoted:
            p.kill()
            return line[LENGTH], line[OFFSET], line[URL]
    else:
        add_to_blacklist(path)
        global blacklist
        blacklist.append(path)
        return None, None, None


# 3 stages
#
# turn request into filesystem path (strip query string) and check if it exists already, if it does then serve it

# if not, take original request and grep for it, including query string but but replacing characters with their url encoded counterparts (e.g. %20)
# on an exact match, download and serve the request
#


def create_app():
    app = Flask(__name__)

    global blacklist
    blacklist = get_blacklist()


    @app.route('/games/<int:game_no>/download')
    def download_exe(game_no):
        path = None
        with suppress(IndexError):
            path = glob.glob(f'gm/data/sandbox.yoyogames.com/games/{game_no}*/send_download/index.a')[0]
            path = path[path.find('games/'):]
        if path:
            return serve_from_filesystem(path)
        length, offset, url = find_file_in_index('games/' + str(game_no) + '-.*/send_download')
        p = Popen(['./downloader.py', length, offset, url])
        p.wait()
        p = Popen(['./warc-extractor.py', '-output_path', 'gm/data', '-dump', 'content'])
        p.wait()
        with suppress(IndexError):
            path = glob.glob(f'gm/data/sandbox.yoyogames.com/games/{game_no}*/send_download/index.a')[0]
            path = path[path.find('games/'):]
        if path:
            return serve_from_filesystem(path)
        return "Couldn't find exe", 404


    @app.route('/', defaults={'path': ''})
    @app.route('/<path:path>')
    def gamemaker(path):
        path = request.full_path[1:]
        # Take off the question mark if that's all there is
        if path[-1] == '?':
            path = path[:-1]
        global blacklist
        if path in blacklist:
            return 'Not found - blacklisted', 404

        with suppress(NotFound):
            return serve_from_filesystem(path)

        length, offset, url = find_file_in_index(path)
        if url is None:
            return f'Not found in index', 404

        download_filename = Path(path + '.warc.gz').name
        download_warc(int(length), int(offset), url, 'downloads/' + download_filename)
        p = Popen(['./warc-extractor.py', '-output_path', 'gm/data', '-string', download_filename.replace('?', '\?'), '-path', 'downloads/', '-dump', 'content'])
        p.wait()
        print(f'Successfully downloaded {path}')
        return serve_from_filesystem(path)


    return app
