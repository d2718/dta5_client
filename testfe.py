'''

a testing Python client for dta5

2017-08-06
'''

import djsock
import select
import sys

HOST = "localhost"
PORT = 10102
CYCLE_TIMEOUT = 0.1

uname = sys.argv[1]

sock = djsock.DJSocket(HOST, PORT)
msg = sock.suck_read(1.0)
print msg
sock.enque({"Type": "uname", "Payload": uname})
sock.send()

run = True

while run:
  tup = select.select([sys.stdin], [], [], 0)
  if sys.stdin in tup[0]:
    cmd = sys.stdin.readline().strip()
    sock.enque({"Type": "cmd", "Payload": cmd})
    sock.send()
  else:
    msg = sock.suck_read(CYCLE_TIMEOUT)
    if msg is not None:
      t = msg[u'Type']
      if t == u'txt':
        print msg[u'Payload']
      elif t == u'logout':
        print msg[u'Payload']
        run = False
        sock.close()
