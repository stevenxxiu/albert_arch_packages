import concurrent.futures
import json
import re
import time
from collections.abc import Generator, Iterator
from datetime import UTC, datetime
from http.client import HTTPResponse
from pathlib import Path
from re import Pattern
from typing import Callable, NotRequired, TypedDict, override
from urllib import parse, request

from albert import openUrl  # pyright: ignore[reportUnknownVariableType]
from albert import (
    Action,
    GeneratorQueryHandler,
    Icon,
    Item,
    PluginInstance,
    QueryContext,
    StandardItem,
)

openUrl: Callable[[str], None]

md_iid = '5.0'
md_version = '1.5'
md_name = 'Arch Linux Packages'
md_description = 'Query Arch Linux official and AUR packages'
md_license = 'MIT'
md_url = 'https://github.com/stevenxxiu/albert_arch_packages'
md_authors = ['@stevenxxiu']

ICON_PATH = Path(__file__).parent / 'icons/arch.svg'


def to_local_time_str(datetime_obj: datetime) -> str:
    return datetime_obj.replace(tzinfo=UTC).astimezone().strftime('%F %T')


def highlight_query(query_pattern: Pattern[str], name: str) -> str:
    return query_pattern.sub(lambda m: f'<u>{m.group(0)}</u>', name)


class ArchQueryEntry(TypedDict):
    pkgname: str
    repo: str
    arch: str
    pkgver: str
    pkgrel: str
    pkgdesc: str
    url: str
    flag_date: str | None
    maintainers: list[str]


class ArchQueryRes(TypedDict):
    results: list[ArchQueryEntry]
    num_pages: int


class ArchOfficialRepository:
    API_URL: str = 'https://www.archlinux.org/packages/search/json'

    @staticmethod
    def entry_to_item(entry: ArchQueryEntry, query_pattern: Pattern[str]) -> Item:
        name: str = entry['pkgname']

        subtext = entry['pkgdesc']
        if entry['flag_date']:
            date_text = to_local_time_str(datetime.strptime(entry['flag_date'], '%Y-%m-%dT%H:%M:%S.%fZ'))
            subtext = f'<font color="red">[Out of date: {date_text}]</font> {subtext}'
        if not entry['maintainers']:
            subtext = f'<font color="red">[Orphan]</font> {subtext}'
        subtext = f'<font color="dimgray">[{entry["repo"]}]</font> {subtext}'

        url = f'https://archlinux.org/packages/{entry["repo"]}/{entry["arch"]}/{name}/'
        actions = [Action('open_arch', 'Open Arch repositories website', lambda: openUrl(url))]
        if entry['url']:
            actions.append(
                Action('open_project', 'Open project website', lambda: openUrl(entry['url'])),
            )

        return StandardItem(
            id=f'arch/{name}',
            text=f'{highlight_query(query_pattern, name)} {entry["pkgver"]}-{entry["pkgrel"]}',
            subtext=subtext,
            icon_factory=lambda: Icon.image(ICON_PATH),
            actions=actions,
        )

    @classmethod
    def query(cls, query_str: str) -> Iterator[list[Item]]:
        repos: list[str] = ['Core', 'Extra']
        params: list[tuple[str, str]] = [('repo', repo) for repo in repos] + [('q', query_str)]
        cur_page = 1
        num_pages = None

        while True:
            if num_pages is not None and cur_page > num_pages:
                return

            url = f'{cls.API_URL}?{parse.urlencode(params + [("page", str(cur_page))])}'
            req = request.Request(url)

            with request.urlopen(req) as response:  # pyright: ignore[reportAny]
                assert isinstance(response, HTTPResponse)
                data: ArchQueryRes = json.loads(response.read().decode())  # pyright: ignore[reportAny]
                if num_pages is None:
                    num_pages = data['num_pages']

                items: list[Item] = []
                query_pattern = re.compile(query_str, re.IGNORECASE)
                for entry in data['results']:
                    # There's no way to only search for package names. We can only search for both name and description,
                    # or the exact package name. We filter the results manually. See
                    # <https://wiki.archlinux.org/title/Official_repositories_web_interface>.
                    if query_str not in entry['pkgname']:
                        continue
                    items.append(cls.entry_to_item(entry, query_pattern))
                yield items
            cur_page += 1


class AurQueryEntry(TypedDict):
    Name: str
    Version: str
    Description: str
    URL: str
    NumVotes: int
    OutOfDate: int | None
    Maintainer: str | None


class AurQueryRes(TypedDict):
    type: str
    results: list[AurQueryEntry]
    error: NotRequired[str]


class ArchUserRepository:
    API_URL: str = 'https://aur.archlinux.org/rpc/'

    @staticmethod
    def entry_to_item(entry: AurQueryEntry, query_pattern: Pattern[str]) -> Item:
        name = entry['Name']

        subtext = f'{entry["Description"] if entry["Description"] else "[No description]"}'
        if entry['OutOfDate']:
            date_text = to_local_time_str(datetime.fromtimestamp(entry['OutOfDate']))
            subtext = f'<font color="red">[Out of date: {date_text}]</font> {subtext}'
        if entry['Maintainer'] is None:
            subtext = f'<font color="red">[Orphan]</font> {subtext}'
        subtext = f'<font color="dimgray">[AUR]</font> {subtext}'

        url = f'https://aur.archlinux.org/packages/{name}/'
        actions = [Action('open_arch', 'Open AUR website', lambda: openUrl(url))]
        if entry['URL']:
            actions.append(
                Action('open_project', 'Open project website', lambda: openUrl(entry['URL'])),
            )

        return StandardItem(
            id=f'aur/{name}',
            text=f'{highlight_query(query_pattern, name)} {entry["Version"]} ({entry["NumVotes"]})',
            subtext=subtext,
            icon_factory=lambda: Icon.image(ICON_PATH),
            actions=actions,
        )

    @classmethod
    def query(cls, query_str: str) -> list[Item]:
        params = {'v': '5', 'type': 'search', 'by': 'name', 'arg': query_str}
        url = f'{cls.API_URL}?{parse.urlencode(params)}'
        req = request.Request(url)

        with request.urlopen(req) as response:  # pyright: ignore[reportAny]
            assert isinstance(response, HTTPResponse)
            data: AurQueryRes = json.loads(response.read().decode())  # pyright: ignore[reportAny]
            if data['type'] == 'error':
                assert 'error' in data
                item = StandardItem(
                    id='aur_error',
                    text='Error',
                    subtext=data['error'],
                    icon_factory=lambda: Icon.image(ICON_PATH),
                )
                return [item]
            results_json = data['results']
            results_json.sort(key=lambda entry_: (len(entry_['Name']), entry_['Name']))

            query_pattern = re.compile(query_str, re.IGNORECASE)
            items = [cls.entry_to_item(entry, query_pattern) for entry in results_json]
            return items


class Plugin(PluginInstance, GeneratorQueryHandler):
    def __init__(self):
        PluginInstance.__init__(self)
        GeneratorQueryHandler.__init__(self)

    @override
    def synopsis(self, _query: str) -> str:
        return 'pkg_name'

    @override
    def defaultTrigger(self):
        return 'apkg '

    @override
    def items(self, ctx: QueryContext) -> Generator[list[Item]]:
        query_str = ctx.query.strip()
        if not query_str:
            item = StandardItem(
                id='empty',
                text=md_name,
                subtext='Enter a query to search Arch Linux and AUR packages',
                icon_factory=lambda: Icon.image(ICON_PATH),
                actions=[
                    Action(
                        'open_arch',
                        'Open Arch repositories website',
                        lambda: openUrl('https://archlinux.org/packages/'),
                    ),
                    Action(
                        'open_aur',
                        'Open AUR website',
                        lambda: openUrl('https://aur.archlinux.org/packages/'),
                    ),
                ],
            )
            yield [item]
            return

        # Avoid rate limiting
        for _ in range(50):
            time.sleep(0.01)
            if not ctx.isValid:
                return

        with concurrent.futures.ThreadPoolExecutor() as executor:
            aur_future = executor.submit(ArchUserRepository.query, query_str)
            for items in ArchOfficialRepository.query(query_str):
                if items:
                    yield items
            items = aur_future.result()
            if items:
                yield items
