.. _install_sandboxes_grpc_bridge:

gRPC Bridge
===========

Envoy gRPC
~~~~~~~~~~

The gRPC bridge sandbox is an example usage of Envoy's
:ref:`gRPC bridge filter <config_http_filters_grpc_bridge>`.

This is an example of a key-value store where an ``http``-based client CLI, written in Python,
updates a remote store, written in Go, using the stubs generated for both languages.

The clients use the ``gRPC`` stubs and send messages through a proxy
that upgrades the HTTP requests from http/1.1 to http/2.

* Client: talks in python and sends HTTP/1.1 requests (gRPC stubs)
  * Client-Proxy: Envoy setup that acts as an egress and converts the HTTP/1.1 call to HTTP/2.
* Server: talks in golang and receives HTTP/2 requests (gRPC stubs)
  * Server-Proxy: Envoy setup that acts as an ingress and receives the HTTP/2 calls

``[client](http/1.1) -> [client-egress-proxy](http/2) -> [server-ingress-proxy](http/2) -> [server]``

Another Envoy feature demonstrated in this example is Envoy's ability to do authority
base routing via its route configuration.

Running the Sandbox
~~~~~~~~~~~~~~~~~~~

**Step 1: Install Docker**

Ensure that you have a recent versions of ``docker`` and ``docker-compose``.

A simple way to achieve this is via the `Docker Desktop <https://www.docker.com/products/docker-desktop>`_.

**Step 2: Clone the Envoy repository**

If you have not cloned the Envoy repository, clone it with ``git clone git@github.com:envoyproxy/envoy``
or ``git clone https://github.com/envoyproxy/envoy.git``.

**Step 3: Generate the protocol stubs**

A docker-compose file is provided that uses the ``protos`` dir and generates the stubs for both
``client`` and ``server``.

If you inspect the file ``docker-compose-protos.yaml`` you will see that it contains the ``python``
and ``go`` gRPC protoc commands for generating the protocol stubs.

This should be run as follows:

.. code-block:: console

  $ pwd
  envoy/examples/grpc-bridge
  $ docker-compose -f docker-compose-protos.yaml up
  Starting grpc-bridge_stubs_python_1 ... done
  Starting grpc-bridge_stubs_go_1     ... done
  Attaching to grpc-bridge_stubs_go_1, grpc-bridge_stubs_python_1
  grpc-bridge_stubs_go_1 exited with code 0
  grpc-bridge_stubs_python_1 exited with code 0

You may wish to clean up left over containers with the following command:

.. code-block:: console

  $ docker container prune

You can view the generated `kv` modules for both the client and server in their
respective directories:

.. code-block:: console

  $ ls -la client/kv/kv_pb2.py
  -rw-r--r--  1 mdesales  CORP\Domain Users  9527 Nov  6 21:59 client/kv/kv_pb2.py

  $ ls -la server/kv/kv.pb.go
  -rw-r--r--  1 mdesales  CORP\Domain Users  9994 Nov  6 21:59 server/kv/kv.pb.go

These generated ``python`` and ``go`` stubs can be included as external modules.

**Step 4: Start all of our containers**

To build this sandbox example and start the example services, run the following commands::

.. code-block:: console

  $ pwd
  envoy/examples/grpc-bridge
  $ docker-compose pull
  $ docker-compose up --build -d
  $ docker-compose ps

                 Name                             Command                  State                         Ports
  ------------------------------------------------------------------------------------------------------------------------------------------
  grpc-bridge_grpc-client-proxy_1        /docker-entrypoint.sh /bin ...    Up      10000/tcp, 0.0.0.0:9911->9911/tcp, 0.0.0.0:9991->9991/tcp
  grpc-bridge_grpc-client_1              /bin/sh -c tail -f /dev/null      Up
  grpc-bridge_grpc-server-proxy_1        /docker-entrypoint.sh /bin ...    Up      10000/tcp, 0.0.0.0:8811->8811/tcp, 0.0.0.0:8881->8881/tcp
  grpc-bridge_grpc-server_1              /bin/sh -c /bin/server            Up      0.0.0.0:8081->8081/tcp


Sending requests to the Key/Value store
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

To use the Python service and send gRPC requests:

.. code-block:: console

  $ pwd
  envoy/examples/grpc-bridge

Set a key

.. code-block:: console

  $ docker-compose exec python /client/client.py set foo bar
  setf foo to bar


Get a key

.. code-block:: console

  $ docker-compose exec python /client/client.py get foo
  bar

Modify an existing key

.. code-block:: console

  $ docker-compose exec python /client/client.py set foo baz
  setf foo to baz

Get the modified key

.. code-block:: console

  $ docker-compose exec python /client/client.py get foo
  baz

In the running docker-compose container, you should see the gRPC service printing a record of its activity.

.. code-block:: console

  $ docker-compose logs grpc-server
  grpc_1    | 2017/05/30 12:05:09 set: foo = bar
  grpc_1    | 2017/05/30 12:05:12 get: foo
  grpc_1    | 2017/05/30 12:05:18 set: foo = baz
