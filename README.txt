This is a server structure provided under the MIT license that implements a system of collection servers 
and an API server that reference a shared central manager class, which accumulates the collected data, 
can perform some parsing and processing, and can be interacted with via CLI using a separate input thread.

All threads are daemons, meaning they will close when the main program ends. Should the API thread crash, the 
manager class is able to relaunch it. This can be adapted to relaunch the collection servers, too.

I set this architecture up initially as a IoT system for BLE trackers, and have stripped most of the specialized
code away for this repo. Each collection server could potentially be POSTed data from a different Bluetooth scraping
gateway (through a different port #), allowing the manager to track whether BLE beacons have moved.

As it is currently, there is no security implemented, since this was made for internal, PoC use. HTTPS could be 
theoretically used, as could codes, etc as part of the data.

The Client.py file implements an incredibly simple client that sends a piece of "data" to the collection server
at port 1337, idles while the server manager queue is processed, then requests the accumulated data from that port.
Obviously, one should aim a bit higher when actually using this setup, but it's quite easy to modify, and a simple
POST (or GET) shooter program is invaluable for initial testing. 

Usage:
Run Serv.py to begin the server system. Once the CLI instructions ("q" or "quit" to end) pops up, the server is 
ready to be interacted with.

Run Client.py in a separate console window. It will automatically deposit data, then query the server.