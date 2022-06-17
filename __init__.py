'''Query *Arch Linux* official and *AUR* packages.

You can search for packages and open their URLs.

Synopsis: <trigger> <pkg_name>'''

import concurrent.futures
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib import parse, request

from albert import Item, UrlAction  # pylint: disable=import-error


__title__ = 'Arch Linux Packages'
__version__ = '0.4.4'
__triggers__ = 'apkg '
__authors__ = ['Steven Xu', 'manuelschneid3r']

ICON_PATH = str(Path(__file__).parent / 'icons/arch.svg')


def to_local_time_str(datetime_obj):
    return datetime_obj.replace(tzinfo=timezone.utc).astimezone().strftime('%F %T')


def highlight_query(query_pattern, name):
    return query_pattern.sub(lambda m: f'<u>{m.group(0)}</u>', name)


class ArchOfficialRepository:
    API_URL = 'https://www.archlinux.org/packages/search/json'

    @staticmethod
    def entry_to_item(entry, query_pattern):
        name = entry['pkgname']
        item = Item(
            id=__title__,
            icon=ICON_PATH,
            text=f'<b>{highlight_query(query_pattern, name)}</b> <i>{entry["pkgver"]}-{entry["pkgrel"]}</i>',
            completion=f'{__triggers__}{name}',
        )
        subtext = entry['pkgdesc']
        if entry['flag_date']:
            date_text = to_local_time_str(datetime.strptime(entry['flag_date'], '%Y-%m-%dT%H:%M:%S.%fZ'))
            subtext = f'<font color="red">[Out of date: {date_text}]</font> {subtext}'
        if not entry['maintainers']:
            subtext = f'<font color="red">[Orphan]</font> {subtext}'
        subtext = f'<font color="dimgray">[{entry["repo"]}]</font> {subtext}'
        item.subtext = subtext

        item.addAction(
            UrlAction(
                'Open Arch repositories website',
                f'https://archlinux.org/packages/{entry["repo"]}/{entry["arch"]}/{name}/',
            )
        )

        if entry['url']:
            item.addAction(UrlAction('Open project website', entry['url']))

        return item

    @classmethod
    def query(cls, query_str):
        repos = ['Core', 'Extra', 'Community']
        repos_lower = [repo.lower() for repo in repos]
        params = [('repo', repo) for repo in repos] + [('q', query_str)]
        url = f'{cls.API_URL}?{parse.urlencode(params)}'
        req = request.Request(url)

        with request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            results = []
            results_json = data['results']
            results_json.sort(
                key=lambda entry_: (repos_lower.index(entry_["repo"]), len(entry_['pkgname']), entry_['pkgname'])
            )

            query_pattern = re.compile(query_str, re.IGNORECASE)
            for entry in results_json:
                # There's no way to only search for package names. We can only search for both name and description,
                # or the exact package name. We filter the results manually. See
                # https://wiki.archlinux.org/title/Official_repositories_web_interface.
                if query_str not in entry['pkgname']:
                    continue
                results.append(cls.entry_to_item(entry, query_pattern))
            return results


class ArchUserRepository:
    API_URL = 'https://aur.archlinux.org/rpc/'

    @staticmethod
    def entry_to_item(entry, query_pattern):
        name = entry['Name']
        item = Item(
            id=__title__,
            icon=ICON_PATH,
            text=f'<b>{highlight_query(query_pattern, name)}</b> <i>{entry["Version"]}</i> ({entry["NumVotes"]})',
            completion=f'{__triggers__}{name}',
        )
        subtext = f'{entry["Description"] if entry["Description"] else "[No description]"}'
        if entry['OutOfDate']:
            date_text = to_local_time_str(datetime.fromtimestamp(entry['OutOfDate']))
            subtext = f'<font color="red">[Out of date: {date_text}]</font> {subtext}'
        if entry['Maintainer'] is None:
            subtext = f'<font color="red">[Orphan]</font> {subtext}'
        subtext = f'<font color="dimgray">[AUR]</font> {subtext}'
        item.subtext = subtext

        item.addAction(UrlAction('Open AUR website', f'https://aur.archlinux.org/packages/{name}/'))

        if entry['URL']:
            item.addAction(UrlAction('Open project website', entry['URL']))

        return item

    @classmethod
    def query(cls, query_str):
        params = {'v': '5', 'type': 'search', 'by': 'name', 'arg': query_str}
        url = f'{cls.API_URL}?{parse.urlencode(params)}'
        req = request.Request(url)

        with request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data['type'] == 'error':
                return Item(
                    id=__title__,
                    icon=ICON_PATH,
                    text='Error',
                    subtext=data['error'],
                )
            results = []
            results_json = data['results']
            results_json.sort(key=lambda entry_: (len(entry_['Name']), entry_['Name']))

            query_pattern = re.compile(query_str, re.IGNORECASE)
            for entry in results_json:
                results.append(cls.entry_to_item(entry, query_pattern))
            return results


def handleQuery(query):
    if not query.isTriggered:
        return None

    query.disableSort()

    query_str = query.string.strip()
    if not query_str:
        return [
            Item(
                id=__title__,
                icon=ICON_PATH,
                text=__title__,
                subtext='Enter a query to search Arch Linux and AUR packages',
                actions=[
                    UrlAction('Open Arch repositories website', 'https://archlinux.org/packages/'),
                    UrlAction('Open AUR website', 'https://aur.archlinux.org/packages/'),
                ],
            ),
        ]

    with concurrent.futures.ThreadPoolExecutor() as executor:
        futures = [
            executor.submit(ArchOfficialRepository.query, query_str),
            executor.submit(ArchUserRepository.query, query_str),
        ]
        results = []
        concurrent.futures.wait(futures)
        for future in futures:
            results.extend(future.result())
        return results
