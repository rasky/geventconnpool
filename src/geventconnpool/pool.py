import logging
from functools import wraps
from contextlib import contextmanager
from collections import deque

import gevent
from gevent import socket
from gevent.coros import BoundedSemaphore

__all__ = ["ConnectionPool", "retry"]

DEFAULT_EXC_CLASSES = (socket.error, )


class ConnectionPool(object):
    """
    Generic TCP connection pool, with the following features:
        * Configurable pool size
        * Auto-reconnection when a broken socket is detected
        * Optional periodic keepalive
    """

    # Frequency at which the pool is populated at startup
    SPAWN_FREQUENCY = 0.1

    def __init__(self, size, exc_classes=DEFAULT_EXC_CLASSES, keepalive=None):
        """
        :param exc_classes: tuple, exceptions which connection should be dropped when it raises
        """
        self.size = size
        self.connections = deque()
        self.lock = BoundedSemaphore(size)
        self.keepalive = keepalive
        # Exceptions list must be in tuple form to be caught properly
        self.exc_classes = tuple(exc_classes)
        # http://stackoverflow.com/a/31136897/357578
        try:
            xrange
        except NameError:
            xrange = range
        for i in xrange(size):
            self.lock.acquire()
        for i in xrange(size):
            gevent.spawn_later(self.SPAWN_FREQUENCY*i, self._add_one)
        if self.keepalive:
            gevent.spawn(self._keepalive_periodic)

    def _new_connection(self):
        """
        Establish a new connection (to be implemented in subclasses).
        """
        raise NotImplementedError

    def _keepalive(self, conn):
        """
        Implement actual application-level keepalive (to be
        reimplemented in subclasses).

        :raise: socket.error if the connection has been closed or is broken.
        """
        raise NotImplementedError()

    def _keepalive_periodic(self):
        delay = float(self.keepalive) / self.size
        while 1:
            try:
                with self.get() as conn:
                    self._keepalive(conn)
            except self.exc_classes:
                # Nothing to do, the pool will generate a new connection later
                pass
            gevent.sleep(delay)

    def _add_one(self):
        interval = self.SPAWN_FREQUENCY
        conn = self._new_connection()
        while not conn:
            gevent.sleep(interval)
            if interval < 400:
                interval *= 2
            conn = self._new_connection()

        self.connections.append(conn)
        self.lock.release()

    @contextmanager
    def get(self):
        """
        Get a connection from the pool, to make and receive traffic.

        If the connection fails for any reason (socket.error), it is dropped
        and a new one is scheduled. Please use @retry as a way to automatically
        retry whatever operation you were performing.
        """
        self.lock.acquire()
        conn = self.connections.popleft()
        try:
            yield conn
        except self.exc_classes:
            # The current connection has failed, drop it and create a new one
            gevent.spawn_later(self.SPAWN_FREQUENCY, self._add_one)
            raise
        except:
            self.connections.append(conn)
            self.lock.release()
            raise
        else:
            # NOTE: cannot use finally because MUST NOT reuse the connection
            # if it failed (socket.error)
            self.connections.append(conn)
            self.lock.release()


def retry(func, exc_classes=DEFAULT_EXC_CLASSES, logger=None,
          retry_log_level=logging.INFO,
          retry_log_message="Connection broken in '{func}' (error: '{err}'); "
                            "retrying with new connection.",
          max_failures=None, interval=0,
          max_failure_log_level=logging.ERROR,
          max_failure_log_message="Max retries reached for '{func}'. Aborting."):
    """
    Decorator to automatically re-execute a function if the connection is
    broken for any reason.
    """
    exc_classes = tuple(exc_classes)

    @wraps(func)
    def deco(*args, **kwargs):
        failures = 0
        while True:
            try:
                return func(*args, **kwargs)
            except exc_classes as err:
                if logger is not None:
                    message = retry_log_message.format(func=func.func_name, err=err)
                    logger.log(retry_log_level, message)

                failures += 1
                if max_failures is not None and failures > max_failures:
                    if logger is not None:
                        message = max_failure_log_message.format(func=func.func_name)
                        logger.log(max_failure_log_level, message)
                    raise

                gevent.sleep(interval)
    return deco
