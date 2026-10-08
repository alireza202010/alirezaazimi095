import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class FakeResponse:
    def __init__(self, data):
        self._data = data

    def json(self):
        return self._data


class FakeHttp:
    """Routes requests to a handler(method, url, kwargs) -> dict and records the calls."""

    def __init__(self, handler):
        self.handler = handler
        self.calls = []

    def _do(self, method, url, **kwargs):
        self.calls.append((method, url, kwargs))
        return FakeResponse(self.handler(method, url, kwargs))

    def get(self, url, **kwargs):
        return self._do("GET", url, **kwargs)

    def post_json(self, url, payload, **kwargs):
        return self._do("POST", url, json=payload, **kwargs)

    def post_form(self, url, data, **kwargs):
        return self._do("POST", url, data=data, **kwargs)
