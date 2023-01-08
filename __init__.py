import concurrent.futures
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from re import Pattern
from typing import List
from urllib import parse, request

from albert import Action, Item, Query, QueryHandler, openUrl  # pylint: disable=import-error


md_iid = '0.5'
md_version = '1.0'
md_name = 'Arch Linux Packages'
md_description = 'Query *Arch Linux* official and *AUR* packages. Search for packages, open their URLs.'
md_url = 'https://github.com/stevenxxiu/albert_arch_packages'
md_maintainers = '@stevenxxiu'

TRIGGER = 'apkg'
ICON_PATH = str(Path(__file__).parent / 'icons/arch.svg')


def to_local_time_str(datetime_obj: datetime) -> str:
    return datetime_obj.replace(tzinfo=timezone.utc).astimezone().strftime('%F %T')


def highlight_query(query_pattern: Pattern, name: str) -> str:
    return query_pattern.sub(lambda m: f'<u>{m.group(0)}</u>', name)


class ArchOfficialRepository:
    API_URL = 'https://www.archlinux.org/packages/search/json'

    @staticmethod
    def entry_to_item(entry: dict, query_pattern: Pattern) -> Item:
        name: str = entry['pkgname']

        subtext = entry['pkgdesc']
        if entry['flag_date']:
            date_text = to_local_time_str(datetime.strptime(entry['flag_date'], '%Y-%m-%dT%H:%M:%S.%fZ'))
            subtext = f'<font color="red">[Out of date: {date_text}]</font> {subtext}'
        if not entry['maintainers']:
            subtext = f'<font color="red">[Orphan]</font> {subtext}'
        subtext = f'<font color="dimgray">[{entry["repo"]}]</font> {subtext}'

        url = f'https://archlinux.org/packages/{entry["repo"]}/{entry["arch"]}/{name}/'
        actions = [Action(f'{md_name}/{url}', 'Open Arch repositories website', lambda: openUrl(url))]
        if entry['url']:
            actions.append(
                Action(f'{md_name}/{entry["url"]}', 'Open project website', lambda: openUrl(entry['url'])),
            )

        return Item(
            id=f'{md_name}/{entry["repo"]}/{entry["arch"]}/{name}',
            text=f'{highlight_query(query_pattern, name)} {entry["pkgver"]}-{entry["pkgrel"]}',
            subtext=subtext,
            completion=f'{TRIGGER} {name}',
            icon=[ICON_PATH],
            actions=actions,
        )

    @classmethod
    def query(cls, query_str: str) -> List[Item]:
        repos: List[str] = ['Core', 'Extra', 'Community']
        repos_lower: List[str] = [repo.lower() for repo in repos]
        params: List[tuple[str, str]] = [('repo', repo) for repo in repos] + [('q', query_str)]
        url = f'{cls.API_URL}?{parse.urlencode(params)}'
        req = request.Request(url)

        with request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            items: List[Item] = []
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
                items.append(cls.entry_to_item(entry, query_pattern))
            return items


class ArchUserRepository:
    API_URL = 'https://aur.archlinux.org/rpc/'

    @staticmethod
    def entry_to_item(entry: dict, query_pattern: Pattern) -> Item:
        name = entry['Name']

        subtext = f'{entry["Description"] if entry["Description"] else "[No description]"}'
        if entry['OutOfDate']:
            date_text = to_local_time_str(datetime.fromtimestamp(entry['OutOfDate']))
            subtext = f'<font color="red">[Out of date: {date_text}]</font> {subtext}'
        if entry['Maintainer'] is None:
            subtext = f'<font color="red">[Orphan]</font> {subtext}'
        subtext = f'<font color="dimgray">[AUR]</font> {subtext}'

        url = f'https://aur.archlinux.org/packages/{name}/'
        actions = [Action(f'{md_name}/{url}', 'Open AUR website', lambda: openUrl(url))]
        if entry['URL']:
            actions.append(
                Action(f'{md_name}/{entry["URL"]}', 'Open project website', lambda: openUrl(entry['URL'])),
            )

        return Item(
            id=f'{md_name}/AUR/{name}',
            text=f'<b>{highlight_query(query_pattern, name)}</b> <i>{entry["Version"]}</i> ({entry["NumVotes"]})',
            subtext=subtext,
            completion=f'{TRIGGER} {name}',
            icon=[ICON_PATH],
            actions=actions,
        )

    @classmethod
    def query(cls, query_str: str) -> List[Item]:
        params = {'v': '5', 'type': 'search', 'by': 'name', 'arg': query_str}
        url = f'{cls.API_URL}?{parse.urlencode(params)}'
        req = request.Request(url)

        with request.urlopen(req) as response:
            data = json.loads(response.read().decode())
            if data['type'] == 'error':
                return [
                    Item(
                        id=f'{md_name}/aur_error',
                        text='Error',
                        subtext=data['error'],
                        icon=[ICON_PATH],
                    )
                ]
            results_json = data['results']
            results_json.sort(key=lambda entry_: (len(entry_['Name']), entry_['Name']))

            query_pattern = re.compile(query_str, re.IGNORECASE)
            items = [cls.entry_to_item(entry, query_pattern) for entry in results_json]
            return items


class Plugin(QueryHandler):
    def id(self) -> str:
        return __name__

    def name(self) -> str:
        return md_name

    def description(self) -> str:
        return md_description

    def defaultTrigger(self) -> str:
        return TRIGGER

    def synopsis(self) -> str:
        return 'pkg_name'

    def handleQuery(self, query: Query) -> None:
        query_str = query.string.strip()
        if not query_str:
            item = Item(
                id=f'{md_name}/open_websites',
                text=md_name,
                subtext='Enter a query to search Arch Linux and AUR packages',
                icon=[ICON_PATH],
                actions=[
                    Action(
                        f'{md_name}/open_arch_repos',
                        'Open Arch repositories website',
                        lambda: openUrl('https://archlinux.org/packages/'),
                    ),
                    Action(
                        f'{md_name}/open_aur',
                        'Open AUR website',
                        lambda: openUrl('https://aur.archlinux.org/packages/'),
                    ),
                ],
            )
            query.add(item)
            return

        # Avoid rate limiting
        time.sleep(0.2)
        if not query.isValid:
            return

        with concurrent.futures.ThreadPoolExecutor() as executor:
            futures = [
                executor.submit(ArchOfficialRepository.query, query_str),
                executor.submit(ArchUserRepository.query, query_str),
            ]
            concurrent.futures.wait(futures)
            for future in futures:
                for item in future.result():
                    query.add(item)
