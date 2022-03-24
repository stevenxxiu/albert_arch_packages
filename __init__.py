# -*- coding: utf-8 -*-

'''Query ArchLinux User Repository (AUR) packages.

You can search for packages and open their URLs.

Synopsis: <trigger> <pkg_name>'''

import json
import re
from datetime import datetime
from pathlib import Path
from urllib import parse, request

from albert import Item, UrlAction  # pylint: disable=import-error


__title__ = 'Archlinux User Repository'
__version__ = '0.4.3'
__triggers__ = 'aur '
__authors__ = 'manuelschneid3r'

icon_path = str(Path(__file__).parent / 'icons/arch.svg')
baseurl = 'https://aur.archlinux.org/rpc/'


def entry_to_item(entry, query_pattern):
    name = entry['Name']
    item = Item(
        id=__title__,
        icon=icon_path,
        text=(
            f'<b>{query_pattern.sub(lambda m: f"<u>{m.group(0)}</u>", name)}</b> '
            f'<i>{entry["Version"]}</i> ({entry["NumVotes"]})'
        ),
        completion=f'{__triggers__}{name}',
    )
    subtext = entry['Description'] if entry['Description'] else '[No description]'
    if entry['OutOfDate']:
        date_text = datetime.fromtimestamp(entry['OutOfDate']).strftime('%F')
        subtext = f'<font color="red">[Out of date: {date_text}]</font> {subtext}'
    if entry['Maintainer'] is None:
        subtext = f'<font color="red">[Orphan]</font> {subtext}'
    item.subtext = subtext

    item.addAction(UrlAction('Open AUR website', f'https://aur.archlinux.org/packages/{name}/'))

    if entry['URL']:
        item.addAction(UrlAction('Open project website', entry['URL']))


def handleQuery(query):
    if not query.isTriggered:
        return None

    query.disableSort()

    stripped = query.string.strip()

    if not stripped:
        return Item(
            id=__title__,
            icon=icon_path,
            text=__title__,
            subtext='Enter a query to search the AUR',
            actions=[UrlAction('Open AUR packages website', 'https://aur.archlinux.org/packages/')],
        )

    params = {'v': '5', 'type': 'search', 'by': 'name', 'arg': stripped}
    url = f'{baseurl}?{parse.urlencode(params)}'
    req = request.Request(url)

    with request.urlopen(req) as response:
        data = json.loads(response.read().decode())
        if data['type'] == 'error':
            return Item(
                id=__title__,
                icon=icon_path,
                text='Error',
                subtext=data['error'],
            )
        results = []
        query_pattern = re.compile(query.string, re.IGNORECASE)
        results_json = data['results']
        results_json.sort(key=lambda item: item['Name'])
        results_json.sort(key=lambda item: len(item['Name']))

        for entry in results_json:
            results.append(entry_to_item(entry, query_pattern))
        return results
