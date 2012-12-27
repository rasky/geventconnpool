geventconnpool
==============
This package implements a generic TCP connection pool for gevent-based
applications. It can be used every time your program needs to connnect to
an external service through a TCP-based protocol (including all HTTP protocols
like REST APIs), and you want your process to keep and manage a pool of
connections to the remote endpoint.

A typical scenario might be a gunicorn-based web application with gevent backend,
that accesses remote service through HTTPS APIs. In this case, using the pool
shorten the request and minimize the latency because the pool keeps open
connections to the remote endpoints, and it is not necessary to do a full SSL
handshake every time we need to issue a command.

Quickstart
==========
To install the package, use pip::

    $ pip install geventconnpool

or easy_install::

    $ easy_install geventconnpool

You need to derive from ``ConnectionPool`` and reimplement ``_new_connection``,
to specify how to open a connection to the remove site. For instance:

.. code-block:: python

    from geventconnpool import ConnectionPool
    from gevent import socket

    class MyPool(ConnectionPool):
        def _new_connection(self):
            return socket.create_connection(('test.example.org', 2485))

In this case, we're simply opening a TCP connection to a specified peer.

The pool can be istantiated by specifying how many connections we want to
keep open at the same time:

.. code-block:: python

    pool = MyPool(20)  # always keep 20 connections open


To access a connection within the pool:

.. code-block:: python

    with pool.get() as c:
        c.send("PING\n")
        if c.recv(5) != "PONG\n":
            raise socket.error("something awful happened")

If the context is quit through a ``socket.error`` exception, the connection is
discarded and a new open is opened in background, to keep the pool always full
of valid connections. Any other exception does not have a special meaning, and
the connection will be reinserted into the pool to be reused later.

Automatic retrying
==================
If you want to be resilent to temporary network errors, you can use the ``retry``
decorator that will re-execute the function if it is quit with a ``socket.error``
exception:

.. code-block:: python

    from geventconnpool import retry

    @retry
    def senddata(data):
        with pool.get() as c:
            c.send(data)
            if c.recv(2) != "OK":
                raise socket.error("something awful happened")

Since the pool discards the connections when a ``1`` exception is
generated, the net effect of `retry` is that a different connection will be
used for each attempt.

Advanced connection examples
============================
When implement a connection pool, it is advisable to perform all the
initialization phases of the application protocol within the ``_new_connection``
callback. For instance, a protocol might allow to switch to TLS
(with a STARTTLS-like) and then require authentication:

.. code-block:: python

    from geventconnpool import ConnectionPool
    from gevent import socket, ssl

    class MyPool(ConnectionPool):
        def _new_connection(self):
            s = socket.create_connection(('test.example.org', 2485))
            s.send("STARTTLS\n")
            res = s.recv(3)
            if res == "OK\n":
                s = ssl.wrap_socket(s)
            elif res == "NO\n":
                pass
            else:
                raise socket.error("invalid response to STARTTLS")

            s.send("LOGIN: %s\n" % MY_LOGIN_NAME);
            s.send("PASS: %s\n" % MY_PASS);
            res = s.recv(2)
            if res != "OK":
                raise socket.error("authentication failed")
            return s

As you can see, it is possible to simply raise ``socket.error`` if something
went wrong. The pool is resistant to temporary connection errors and will retry
automatically to estabilish new connections later.

Another common situation might involve the usage of third-party libraries like for
instance using `boto <http://docs.pythonboto.org/en/latest/>`_ to connect to
Amazon AWS:

.. code-block:: python

    from geventconnpool import ConnectionPool
    import boto
    from boto.exception import NoAuthHanlder

    class UsersPool(ConnectionPool):
        def _new_connection(self):
            try:
                c = boto.connect_dynamodb(MY_AWS_KEY_ID, MY_AWS_SECRET_KEY)
                return c.get_table("users")
            except:
                raise socket.error("error connecting to AWS")

In this case, we don't only connect to AWS and authenticate, but we also open
a specific table and return a reference to that table. In fact, it is not
necessary for the return value of ``_new_connection()`` to be a socket (or
socket-like): ``ConnectionPool`` treats it as a black.box and return it when
``get`` is called.

.. note:: boto has an internal connection pool, but it is only used to be
    fully-thread safe, and does not preemptively open the connections,
    authenticate, and perform initialization. This means that it still makes
    sense to use ``ConnectionPool`` to minimize the latency when communicating
    to AWS.

Keepalive
=========
Some protocols or networks might require a keepalive mechanism to keep a
connection open if it is idle. For instance, the remote peer, a firewall or a
load-balancer might close a connection if it is idle for too long.

Sometimes, it is sufficient to rely on the standard TCP-level keeaplive, that
can be turned on any TCP socket:

.. code-block:: python

    from geventconnpool import ConnectionPool
    from gevent import socket

    class MyPool(ConnectionPool):
        def _new_connection(self):
            s = socket.create_connection(('test.example.org', 2485))
            s._sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            return s

The TCP keepalive uses ACK packets to continously communicating with the remote
peer. To tune the keepalive parameters (delay between ACKs, number of unanswered
ACKs to consider the connnection dropped, etc.), you need to tweak with the
proc filesystem (yes, it's a global per-computer configuration).

Alternatively, it is possible to implement an application-level keepalive
by implemening the ``_keepalive`` method and specifying the keepalive frequency
in the constructor:

.. code-block:: python

    from geventconnpool import ConnectionPool
    from gevent import socket

    class MyPool(ConnectionPool):
        def _new_connection(self):
            return socket.create_connection(('test.example.org', 2485))

        def _keepalive(self, c):
            c.send("PING\n")
            if c.recv(5) != "PONG\n":
                raise socket.error

    pool = MyPool(20, keepalive=30)

The above code uses a keepalive based on an application-level command (PING),
and specifies that it should be executed every 30 seconds (per each connection).

``_keepalive`` should raise ``socket.error`` to communicate that the connection
appears to be broken and should be discarded by the pool.
