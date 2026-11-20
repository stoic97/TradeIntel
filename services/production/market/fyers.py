"""RED stub."""


class ExchangeFailed(Exception):
    pass


class Paced:
    def __init__(self, client, clock=None, sleep=None):
        self.client = client

    def history(self, data):
        raise NotImplementedError


def exchange(app, code):
    raise NotImplementedError


def history_client(app, token):
    raise NotImplementedError
