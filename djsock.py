"""

a buffered socket protocol for sending and receiving JSON data

2017-08-06
"""

import json
import select
import socket
import sys
import time

DEFAULT_TIMEOUT = 1000
READ_SIZE = 4096
BUSY_WAIT_INTERVAL = 0.1

class DJSockErr(IOError):
  pass

class DJSocket:
  def __init__(self, host, port, timeout=DEFAULT_TIMEOUT):
    self.out_buff = ''
    self.in_buff = ''
    self.sock = socket.create_connection((host, port), timeout)
  
  def ready_to_recv(self):
    tup = select.select([self.sock], [], [], 0)
    if self.sock in tup[0]:
      return True
    else:
      return False
  
  def ready_to_send(self):
    tup = select.select([], [self.sock], [], 0)
    if self.sock in tup[1]:
      return True
    else:
      return False
  
  def enque(self, obj):
    self.out_buff += (json.dumps(obj) + '\n')
  
  def send(self):
    bytes_sent = 0
    while len(self.out_buff) > 0 and self.ready_to_send():
      sent_now = self.sock.send(self.out_buff)
      if sent_now == 0:
        raise DJSockErr('connection discovered broken on send')
      else:
        bytes_sent += sent_now
        self.out_buff = self.out_buff[sent_now:]
    return bytes_sent
  
  def recv(self):
    bytes_read = 0
    while self.ready_to_recv():
      chunk = self.sock.recv(READ_SIZE)
      if chunk == '':
        raise DJSockErr('connection discovered broken on read')
      else:
        bytes_read += len(chunk)
        self.in_buff += chunk
    return bytes_read
  
  def read(self):
    try:
      idx = self.in_buff.index('\n')
      chunk = self.in_buff[:idx]
      self.in_buff = self.in_buff[idx+1:]
      return json.loads(chunk)
    except ValueError:
      return None
  
  def suck_read(self, wait=False, interval=BUSY_WAIT_INTERVAL):
    err = False
    try:
      self.recv()
    except DJSockErr as e:
      err = e
    r_val = self.read()
    if r_val == None:
      if err:
        raise err
      if wait:
        elapsed = 0.0
        while elapsed < wait:
          try:
            recd = self.recv()
          except DJSockErr as e:
            err = e
          if (recd > 0) or err:
            r_val = self.read()
            if r_val is not None:
              return r_val
            else:
              if err:
                raise err
          time.sleep(interval)
          elapsed += interval
    return r_val
  
  def close(self):
    self.sock.shutdown(socket.SHUT_RDWR)
    self.sock.close()
    self.in_buff = ''
    self.out_buff = ''
