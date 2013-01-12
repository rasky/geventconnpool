import gevent
from gevent.coros import BoundedSemaphore
from gevent import socket
from collections import deque
from contextlib import contextmanager
from functools import wraps

__all__ = [ "ConnectionPool", "retry" ]

class ConnectionPool(object):
    """
    Generic TCP connection pool, with the following features:
        * Configurable pool size
        * Auto-reconnection when a broken socket is detected
        * Optional periodic keepalive
    """

    # Frequency at which the pool is populated at startup
    SPAWN_FREQUENCY = 0.1

    def __init__(self, size, keepalive=None):
        self.size = size
        self.conn = deque()
        self.lock = BoundedSemaphore(size)
        self.keepalive = keepalive
        for i in xrange(size):
            self.lock.acquire()
        for i in xrange(size):
            gevent.spawn_later(self.SPAWN_FREQUENCY*i, self._addOne)
        if self.keepalive:
            gevent.spawn(self._keepalive_periodic)

    def _new_connection(self):
        """
        Estabilish a new connection (to be implemented in subclasses).
        """
        raise NotImplementedError

    def _keepalive(self, c):
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
                with self.get() as c:
                    self._keepalive(c)
            except socket.error:
                # Nothing to do, the pool will generate a new connection later
                pass
            gevent.sleep(delay)

    def _addOne(self):
        stime = 0.1
        while 1:
            c = self._new_connection()
            if c:
                break
            gevent.sleep(stime)
            if stime < 400:
                stime *= 2

        self.conn.append(c)
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
        try:
            c = self.conn.popleft()
            yield c
        except socket.error:
            # The current connection has failed, drop it and create a new one
            gevent.spawn_later(1, self._addOne)
            raise
        except:
            self.conn.append(c)
            self.lock.release()
            raise
        else:
            # NOTE: cannot use finally because MUST NOT reuse the connection
            # if it failed (socket.error)
            self.conn.append(c)
            self.lock.release()


def retry(f):
    """
    Decorator to automatically reexecute a function if the connection is
    broken for any reason.
    """
    @wraps(f)
    def deco(*args, **kwargs):
        while 1:
            try:
                return f(*args, **kwargs)
            except socket.error:
                continue
    return deco
