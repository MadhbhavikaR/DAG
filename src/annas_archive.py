from contextlib import closing
from http.client import RemoteDisconnected
from math import ceil
from typing import Generator
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urljoin, urlencode
from urllib.request import urlopen, Request

from calibre import browser
from calibre.gui2 import open_url
from calibre.gui2.store import StorePlugin
from calibre.gui2.store.search_result import SearchResult
from calibre.gui2.store.web_store_dialog import WebStoreDialog
from calibre_plugins.store_annas_archive.constants import DEFAULT_MIRRORS, RESULTS_PER_PAGE, SearchOption
from lxml import html

try:
    from qt.core import QUrl
except (ImportError, ModuleNotFoundError):
    from PyQt5.Qt import QUrl

SearchResults = Generator[SearchResult, None, None]


class AnnasArchiveStore(StorePlugin):

    def __init__(self, gui, name, config=None, base_plugin=None):
        super().__init__(gui, name, config, base_plugin)
        self.working_mirror = None

    def _search(self, url: str, max_results: int, timeout: int) -> SearchResults:
        br = browser()
        doc = None
        counter = max_results

        configured_mirrors = self.config.get('mirrors', DEFAULT_MIRRORS)
        mirrors = list(configured_mirrors) if configured_mirrors else list(DEFAULT_MIRRORS)
        mirrors = [mirror for mirror in mirrors if isinstance(mirror, str) and mirror.strip()]
        if self.working_mirror:
            mirrors = [self.working_mirror] + [mirror for mirror in mirrors if mirror != self.working_mirror]

        for page in range(1, ceil(max_results / RESULTS_PER_PAGE) + 1):
            doc = None
            last_error = None
            for mirror in mirrors:
                try:
                    with closing(br.open(url.format(base=mirror, page=page), timeout=timeout)) as resp:
                        if 200 <= resp.code < 300:
                            self.working_mirror = mirror
                            doc = html.fromstring(resp.read())
                            break
                        last_error = f"HTTP status {resp.code}"
                except (HTTPError, URLError, TimeoutError, RemoteDisconnected, OSError) as err:
                    last_error = str(err)
                    continue
            if doc is None:
                self.working_mirror = None
                raise RuntimeError(
                    "No configured Anna's Archive mirror responded successfully."
                    + (f" Last error: {last_error}" if last_error else "")
                )

            books = doc.xpath('//table/tr')
            for book in books:
                if counter <= 0:
                    break
                columns = book.findall("td")
                if len(columns) <= 9:
                    continue
                s = SearchResult()
                cover = columns[0].xpath('./a[@tabindex="-1"]')
                if cover:
                    cover = cover[0]
                else:
                    continue
                s.detail_item = cover.get('href', '').split('/')[-1]
                if not s.detail_item:
                    continue
                s.cover_url = ''.join(cover.xpath('(./span/img/@src)[1]'))
                s.title = ''.join(columns[1].xpath('./a/span/text()'))
                s.author = ''.join(columns[2].xpath('./a/span/text()'))
                s.formats = ''.join(columns[9].xpath('./a/span/text()')).upper()
                s.price = '$0.00'
                s.drm = SearchResult.DRM_UNLOCKED
                counter -= 1
                yield s

    def search(self, query, max_results=10, timeout=60) -> SearchResults:
        url = f'{{base}}/search?page={{page}}&q={quote_plus(query)}&display=table'
        search_opts = self.config.get('search', {})
        for option in SearchOption.options:
            value = search_opts.get(option.config_option, ())
            if isinstance(value, str):
                value = (value,)
            for item in value:
                url += f'&{urlencode({option.url_param: item})}'
        yield from self._search(url, max_results, timeout)

    def open(self, parent=None, detail_item=None, external=False):
        if detail_item:
            url = self._get_url(detail_item)
        elif self.working_mirror is not None:
            url = self.working_mirror
        else:
            configured = self.config.get('mirrors', DEFAULT_MIRRORS)
            url = next((m for m in configured if isinstance(m, str) and m.strip()), None)
            if not url:
                raise RuntimeError("No Anna's Archive mirror is configured.")
        if external or self.config.get('open_external', False):
            open_url(QUrl(url))
        else:
            d = WebStoreDialog(self.gui, self.working_mirror, parent, url)
            d.setWindowTitle(self.name)
            d.set_tags(self.config.get('tags', ''))
            d.exec()

    def get_details(self, search_result: SearchResult, timeout=60):
        if not search_result.formats:
            return
        _format = '.' + search_result.formats.lower()
        link_opts = self.config.get('link', {})
        url_extension = link_opts.get('url_extension', True)
        content_type = link_opts.get('content_type', False)
        br = browser()
        with closing(br.open(self._get_url(search_result.detail_item), timeout=timeout)) as f:
            doc = html.fromstring(f.read())
        for link in doc.xpath('//div[@id="md5-panel-downloads"]/ul[contains(@class, "list-inside")]/li/a[contains(@class, "js-download-link")]'):
            url = link.get('href')
            link_text = ''.join(link.itertext())
            if link_text == 'Libgen.li':
                url = self._get_libgen_link(url, br)
            elif link_text in ('Libgen.rs Fiction', 'Libgen.rs Non-Fiction'):
                url = self._get_libgen_nonfiction_link(url, br)
            elif link_text.startswith('Sci-Hub'):
                url = self._get_scihub_link(url, br)
            elif link_text == 'Z-Library':
                url = self._get_zlib_link(url, br)
            else:
                continue
            if not url:
                continue
            if content_type:
                try:
                    with urlopen(Request(url, method='HEAD'), timeout=timeout) as resp:
                        if resp.info().get_content_maintype() != 'application':
                            continue
                except (HTTPError, URLError, TimeoutError, RemoteDisconnected):
                    pass
            elif url_extension:
                path = url.split("?", 1)[0].lower()
                if not path.endswith(_format):
                    continue
            search_result.downloads[f"{link_text}.{search_result.formats}"] = url

    @staticmethod
    def _get_libgen_link(url: str, br) -> str:
        with closing(br.open(url)) as resp:
            doc = html.fromstring(resp.read())
            base_url = resp.geturl()
        target = ''.join(doc.xpath('//a[h2[text()="GET"]]/@href'))
        if target:
            return urljoin(base_url, target)

    @staticmethod
    def _get_libgen_nonfiction_link(url: str, br) -> str:
        with closing(br.open(url)) as resp:
            doc = html.fromstring(resp.read())
        return ''.join(doc.xpath('//h2/a[text()="GET"]/@href'))

    @staticmethod
    def _get_scihub_link(url, br):
        with closing(br.open(url)) as resp:
            doc = html.fromstring(resp.read())
            scheme, _ = resp.geturl().split('/', 1)
        url = ''.join(doc.xpath('//embed[@id="pdf"]/@src'))
        if url:
            return scheme + url

    @staticmethod
    def _get_zlib_link(url, br):
        with closing(br.open(url)) as resp:
            doc = html.fromstring(resp.read())
            base_url = resp.geturl()
        target = ''.join(doc.xpath('//a[contains(@class, "addDownloadedBook")]/@href'))
        if target:
            return urljoin(base_url, target)

    def _get_url(self, md5):
        mirror = self.working_mirror
        if not mirror:
            configured = self.config.get('mirrors', DEFAULT_MIRRORS)
            mirror = next((item for item in configured if isinstance(item, str) and item.strip()), None)
        if not mirror:
            raise RuntimeError("No Anna's Archive mirror is configured.")
        return f"{mirror.rstrip('/')}/md5/{md5}"

    def config_widget(self):
        from calibre_plugins.store_annas_archive.config import ConfigWidget
        return ConfigWidget(self)

    def save_settings(self, config_widget):
        config_widget.save_settings()
