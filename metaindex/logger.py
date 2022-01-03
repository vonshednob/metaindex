import logging as pythonlogging


_logger = None
_handler = None
_formatter = None


def setup(level=pythonlogging.WARNING, filename=None):
    global _logger
    global _handler
    global _formatter

    _formatter = None
    if filename is None:
        _handler = pythonlogging.StreamHandler()
        _formatter = pythonlogging.Formatter("[%(levelname)s] %(message)s")
    elif isinstance(filename, pythonlogging.Handler):
        _handler = filename
    else:
        _handler = pythonlogging.FileHandler(filename, encoding='utf-8')
        _formatter = pythonlogging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    if _formatter is not None:
        _handler.setFormatter(_formatter)

    _logger = pythonlogging.getLogger('metaindex')
    _logger.propagate = False
    _logger.setLevel(level)
    _logger.addHandler(_handler)


def debug(*args, **kwargs):
    if _logger:
        return _logger.debug(*args, **kwargs)


def info(*args, **kwargs):
    if _logger:
        return _logger.info(*args, **kwargs)


def warning(*args, **kwargs):
    if _logger:
        return _logger.warning(*args, **kwargs)


def error(*args, **kwargs):
    if _logger:
        return _logger.error(*args, **kwargs)


def fatal(*args, **kwargs):
    if _logger:
        return _logger.fatal(*args, **kwargs)

