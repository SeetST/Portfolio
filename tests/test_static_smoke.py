import contextlib
import http.server
import pathlib
import socketserver
import threading
import unittest
import urllib.parse
import urllib.request
from html.parser import HTMLParser


ROOT_DIR = pathlib.Path(__file__).resolve().parents[1]


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self.assets = []

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "a":
            href = attributes.get("href")
            if href:
                self.links.append(href)
            return

        if tag == "link":
            href = attributes.get("href")
            if href:
                self.assets.append(href)
            return

        src = attributes.get("src")
        if src:
            self.assets.append(src)


class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        return


class StaticSmokeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        handler = lambda *args, **kwargs: QuietHandler(  # noqa: E731
            *args, directory=str(ROOT_DIR), **kwargs
        )
        cls.server = socketserver.TCPServer(("127.0.0.1", 0), handler)
        cls.port = cls.server.server_address[1]
        cls.server_thread = threading.Thread(
            target=cls.server.serve_forever,
            daemon=True,
        )
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.server_thread.join(timeout=5)

    def fetch(self, path):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as response:
            return response.status, response.read(), response.headers.get_content_type()

    def fetch_text(self, path):
        status, body, _ = self.fetch(path)
        return status, body.decode("utf-8")

    def assert_local_assets_resolve(self, body):
        parser = LinkParser()
        parser.feed(body)

        for asset in parser.assets:
            if not asset.startswith("./"):
                continue
            request_path = urllib.parse.quote(
                asset.split("?", 1)[0].removeprefix("."),
                safe="/:-._~",
            )
            status, _, _ = self.fetch(request_path)
            self.assertEqual(status, 200, msg=f"{asset} did not resolve")

        return parser

    def assert_page_contains(self, path, *snippets):
        status, body = self.fetch_text(path)
        self.assertEqual(status, 200, msg=f"{path} did not return 200")
        for snippet in snippets:
            self.assertIn(snippet, body, msg=f"{path} missing expected snippet: {snippet}")
        self.assert_local_assets_resolve(body)
        return body

    def test_homepage_case_study_links_resolve(self):
        body = self.assert_page_contains(
            "/index.html",
            "./card-chat-case-study.html",
            "./credit-card-revamp.html",
            "./mobile-usability-research.html",
        )
        parser = self.assert_local_assets_resolve(body)

        for href in (
            "./card-chat-case-study.html",
            "./credit-card-revamp.html",
            "./mobile-usability-research.html",
        ):
            self.assertIn(href, parser.links)
            status, _, _ = self.fetch(href.removeprefix("."))
            self.assertEqual(status, 200, msg=f"{href} did not resolve from homepage")

    def test_card_chat_case_study_renders_problem_framing_content(self):
        self.assert_page_contains(
            "/card-chat-case-study.html",
            "Understanding the Real Problem",
            '"How do we improve filters on the listing page?"',
            '"How might AI help users decide with confidence?"',
        )

    def test_credit_card_revamp_renders_expected_title_and_back_link(self):
        body = self.assert_page_contains(
            "/credit-card-revamp.html",
            "Designing for Decision:",
            "./index.html",
        )
        self.assertIn("The Credit Card Listing Revamp", body)

    def test_mobile_usability_research_renders_expected_title_and_back_link(self):
        body = self.assert_page_contains(
            "/mobile-usability-research.html",
            "Personal Loans",
            "Mobile Usability Research",
            "./index.html#projects",
        )
        self.assertIn("Reducing drop-off by improving trust", body)


if __name__ == "__main__":
    with contextlib.suppress(KeyboardInterrupt):
        unittest.main()
