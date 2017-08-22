#!/usr/bin/python

'''
DTA5 game client.

Updated: 2016-08-17
'''

import sys
import os.path
import re
import time
import wx

import dconfig
import djsock

DEBUG = False
DEBUG_ATTR = wx.TextAttr('#ff88ff')

CLIENT_VERSION = 170818

CONFIG_DATA = [
  # 100 normal-sized terminal windows
  ('SCROLLBACK_SIZE', 80 * 24 * 100, dconfig.INT),
  ('FONT_FACE', 'Monospace', dconfig.STRING | dconfig.STRIP),
  # size in points, I guess
  ('FONT_SIZE', 10, dconfig.INT),
  # width, height in pixels
  ('WINDOW_SIZE', (1024, 768), dconfig.INT | dconfig.TUPLE),
  # color names or #rrggbb HTML hex triple
  ('TEXT_BG_COLOR', 'BLACK', dconfig.STRING | dconfig.STRIP),
  ('TEXT_FG_COLOR', 'LIGHT GREY', dconfig.STRING | dconfig.STRIP),
  ('WINDOW_BG_COLOR', '#222', dconfig.STRING | dconfig.STRIP),
  ('WINDOW_FG_COLOR', 'blue', dconfig.STRING | dconfig.STRIP),
  ('INPUT_BG_COLOR', 'WHITE', dconfig.STRING | dconfig.STRIP),
  ('INPUT_FG_COLOR', 'BLACK', dconfig.STRING | dconfig.STRIP),
  ('COMMAND_ECHO_FG_COLOR', 'YELLOW', dconfig.STRING | dconfig.STRIP),
  ('COMMAND_ECHO_BG_COLOR', None,     dconfig.STRING | dconfig.STRIP),
  ('SPEECH_BG_COLOR',  None,  dconfig.STRING | dconfig.STRIP),
  ('SPEECH_FG_COLOR', '#0f0', dconfig.STRING | dconfig.STRIP),
  ('SYSTEM_BG_COLOR',  None,  dconfig.STRING | dconfig.STRIP),
  ('SYSTEM_FG_COLOR', '#f0f', dconfig.STRING | dconfig.STRIP),
  # time in second to wait for server response on connection
  ('TIMEOUT', 15.0, dconfig.FLOAT),
  ('HOST', 'localhost', dconfig.STRING | dconfig.STRIP),
  ('PORT', 10102, dconfig.INT),
  ('LOGIN', None, dconfig.STRING | dconfig.STRIP),
  ('PASSWORD', None, dconfig.STRING)
]

dconfig.add_options(CONFIG_DATA)

NEWS_FILE = 'fe_news.txt'
CONFIG_FILES = [os.path.expanduser('~/.dta5'),
                'client_config.cfg']
if DEBUG:
    CONFIG_FILES.insert(0, 'test_config.cfg')
READ_SIZE = 4096
LOGIN_GRID_GAP = 4
SOCKET_POLL_TIMER = 100 # milliseconds

speech_re = re.compile(r'\S+ (says?|asks?|exclaims?)[^"]+')

the_font = None
the_frame = None
login_frame = None
the_error_frame = None

SCROLLBACK_SIZE = 80*24*100
FONT_FACE       = 'Monospace'
FONT_SIZE       = 10
WINDOW_SIZE     = (1024, 768)
TEXT_BG_COLOR   = 'black'
TEXT_FG_COLOR   = 'light grey'
WINDOW_BG_COLOR = 'dark grey'
WINDOW_FG_COLOR = '#0ff'
INPUT_BG_COLOR  = 'black'
INPUT_FG_COLOR  = 'white'
CMD_ECHO_FG_COL = 'yellow'
CMD_ECHO_BG_COL = None
SPEECH_FG_COLOR = '#0f0'
SPEECH_BG_COLOR = None
SYSTEM_FG_COLOR = '#f0f'
SYSTEM_BG_COLOR = None

COMM_TIMEOUT = 15.0
HOST         = 'localhost'
PORT         = 10102
LOGIN        = None
PASSWORD     = None

DEFAULT_ATTR   = None
CMD_ECHO_ATTR  = None
SPEECH_ATTR    = None
SYSTEM_ATTR    = None
INPUT_ATTR     = None
REV_INPUT_ATTR = None

def exec_config():
  cfg_files = [os.path.expanduser('~/.dta5'), 'client_config.cfg']
  if DEBUG:
    cfg_files.insert(0, 'test_config.cfg')
  
  dconfig.external_config(cfg_files)
  
  global SCROLLBACK_SIZE, FONT_FACE, FONT_SIZE, WINDOW_SIZE
  global TEXT_BG_COLOR, TEXT_FG_COLOR
  global WINDOW_BG_COLOR, WINDOW_FG_COLOR
  global INPUT_BG_COLOR, INPUT_FG_COLOR
  global CMD_ECHO_BG_COL, CMD_ECHO_FG_COL
  global SPEECH_BG_COLOR, SPEECH_FG_COLOR
  global SYSTEM_BG_COLOR, SYSTEM_FG_COLOR
  global COMM_TIMEOUT, HOST, PORT, LOGIN, PASSWORD
  
  FONT_FACE, FONT_SIZE = dconfig.get('FONT_FACE'), dconfig.get('FONT_SIZE')
  if len(dconfig.get('WINDOW_SIZE')) != 2:
    sys.stderr.write('Bad WINDOW_SIZE; using {}\n'.format(WINDOW_SIZE))
  else:
    WINDOW_SIZE = dconfig.get('WINDOW_SIZE')
  
  TEXT_BG_COLOR,   TEXT_FG_COLOR   = dconfig.get('TEXT_BG_COLOR'),     dconfig.get('TEXT_FG_COLOR')
  WINDOW_BG_COLOR, WINDOW_FG_COLOR = dconfig.get('WINDOW_BG_COLOR'),   dconfig.get('WINDOW_FG_COLOR')
  INPUT_BG_COLOR,  INPUT_FG_COLOR  = dconfig.get('INPUT_BG_COLOR'),    dconfig.get('INPUT_FG_COLOR')
  CMD_ECHO_BG_COL, CMD_ECHO_FG_COL = dconfig.get('COMMAND_ECHO_BG_COLOR'), dconfig.get('COMMAND_ECHO_FG_COLOR')
  SPEECH_BG_COLOR, SPEECH_FG_COLOR = dconfig.get('SPEECH_BG_COLOR'),   dconfig.get('SPEECH_FG_COLOR')
  SYSTEM_BG_COLOR, SYSTEM_FG_COLOR = dconfig.get('SYSTEM_BG_COLOR'),   dconfig.get('SYSTEM_FG_COLOR')
  
  COMM_TIMEOUT = dconfig.get('TIMEOUT')
  HOST, PORT      = dconfig.get('HOST'),  dconfig.get('PORT')
  LOGIN, PASSWORD = dconfig.get('LOGIN'), dconfig.get('PASSWORD')
  
  global DEFAULT_ATTR, CMD_ECHO_ATTR, SPEECH_ATTR, SYSTEM_ATTR
  global INPUT_ATTR, REV_INPUT_ATTR
  
  DEFAULT_ATTR   = wx.TextAttr(TEXT_FG_COLOR, TEXT_BG_COLOR)
  INPUT_ATTR     = wx.TextAttr(INPUT_FG_COLOR, INPUT_BG_COLOR)
  REV_INPUT_ATTR = wx.TextAttr(INPUT_BG_COLOR, INPUT_FG_COLOR)
  
  if CMD_ECHO_BG_COL is not None:
    CMD_ECHO_ATTR = wx.TextAttr(CMD_ECHO_FG_COL, CMD_ECHO_BG_COL)
  else:
    CMD_ECHO_ATTR = wx.TextAttr(CMD_ECHO_FG_COL)
  
  if SPEECH_BG_COLOR is not None:
    SPEECH_ATTR = wx.TextAttr(SPEECH_FG_COLOR, SPEECH_BG_COLOR)
  else:
    SPEECH_ATTR = wx.TextAttr(SPEECH_FG_COLOR)
  
  if SYSTEM_BG_COLOR is not None:
    SYSTEM_ATTR = wx.TextAttr(SYSTEM_FG_COLOR, SYSTEM_BG_COLOR)
  else:
    SYSTEM_ATTR = wx.TextAttr(SYSTEM_FG_COLOR)
  
  global the_font
  the_font = wx.Font(
    family=wx.FONTFAMILY_TELETYPE,
    face=FONT_FACE,
    pointSize=FONT_SIZE,
    weight=wx.FONTWEIGHT_NORMAL,
    style=wx.FONTSTYLE_NORMAL)
  

def read_file(fname):
  try:
    with open(fname, 'r') as f:
      return f.read()
  except IOError as e:
    sys.stderr.write('Error with file "{}": {} ({}).\n'.format(
      fname, e, repr(e)))
    return ''

class ErrorWindow(wx.Frame):
  def __init__(self, msg, title='Error'):
    wx.Frame.__init__(self, None, title=title)
    
    self.SetLabel(title)
    self.SetFont(the_font)
    self.SetBackgroundColour(WINDOW_BG_COLOR)
    self.SetForegroundColour(WINDOW_FG_COLOR)
    
    self.mesg = wx.StaticText(self)
    self.mesg.SetLabel(msg)
    self.bttn = wx.Button(self, label='Oh, well!')
    self.bttn.Bind(wx.EVT_BUTTON, self.dismiss)
    
    self.sizer = wx.BoxSizer(wx.VERTICAL)
    self.sizer.Add(self.mesg, 1, wx.EXPAND)
    self.sizer.Add(self.bttn, 0, wx.EXPAND)
    self.SetSizer(self.sizer)
    self.SetAutoLayout(1)
    self.sizer.Fit(self)
    self.Show()
    
    self.bttn.SetFocus()
      
  def dismiss(self, evt):
    self.Destroy()
    sys.exit(0)

class LoginWindow(wx.Frame):
  def __init__(self, login=None, password=None):
    wx.Frame.__init__(self, None, title='DTA5 Login')

    self.SetLabel('DTA5 Login')
    self.SetFont(the_font)
    self.SetBackgroundColour(WINDOW_BG_COLOR)
    self.SetForegroundColour(WINDOW_FG_COLOR)

    self.panel = wx.Panel(self)
    self.panel.SetForegroundColour(WINDOW_FG_COLOR)
    self.panel.SetBackgroundColour(WINDOW_BG_COLOR)
    self.login_label = wx.StaticText(self.panel)
    self.password_label = wx.StaticText(self.panel)
    self.login_field = wx.TextCtrl(self.panel)
    self.password_field = wx.TextCtrl(self.panel, style=wx.TE_PASSWORD)
    self.okay_button = wx.Button(self.panel, label="Play")
    self.cancel_button = wx.Button(self.panel, label="Don't Play")

    self.sizer = wx.GridSizer(rows=3, cols=2,
                                hgap=LOGIN_GRID_GAP,
                                vgap=LOGIN_GRID_GAP)
    self.sizer.Add(self.login_label, 0, wx.EXPAND)
    self.sizer.Add(self.login_field, 0, wx.EXPAND)
    self.sizer.Add(self.password_label, 0, wx.EXPAND)
    self.sizer.Add(self.password_field, 0, wx.EXPAND)
    self.sizer.Add(self.okay_button, 0, wx.EXPAND)
    self.sizer.Add(self.cancel_button, 0, wx.EXPAND)

    self.over_sizer = wx.BoxSizer(wx.VERTICAL)
    self.over_sizer.Add(self.panel, 0, wx.EXPAND)

    self.login_label.SetLabel('Login:')
    self.password_label.SetLabel('Password:')
    if login is not None:
        self.login_field.SetValue(login)
    if password is not None:
        self.password_field.SetValue(password)

    self.okay_button.Bind(wx.EVT_BUTTON, self.login)
    self.cancel_button.Bind(wx.EVT_BUTTON, self.cancel)

    self.panel.SetSizer(self.sizer)
    self.panel.SetAutoLayout(1)
    self.sizer.Fit(self.panel)
    self.SetSizer(self.over_sizer)
    self.SetAutoLayout(1)
    self.over_sizer.Fit(self)
    self.Show()

    if login is not None:
      if password is not None:
        self.okay_button.SetFocus()
      else:
        self.password_field.SetFocus()
    else:
      self.login_field.SetFocus()

  def login(self, evt):
    global the_error_frame
    uname = self.login_field.GetValue()
    paswd = self.password_field.GetValue()
    the_socket = djsock.DJSocket(HOST, PORT, COMM_TIMEOUT)
    msg = the_socket.suck_read(1.0)
    print(msg)
    the_socket.enque({"Type": "version", "Text": "{}".format(CLIENT_VERSION)})
    the_socket.enque({"Type": "uname", "Text": uname})
    the_socket.enque({"Type": "pwd",   "Text": paswd})
    the_socket.send()

    self.spawn_main_window(the_socket)

  def spawn_main_window(self, the_socket):
    global the_frame
    the_frame = MainWindow(None, "DTA5", the_socket)
    sys.stdout.write(read_file(NEWS_FILE))
    the_frame.sock.recv()
    the_frame.read_queue()
    self.Destroy()

  def cancel(self, evt):
    sys.stderr.write('Fine, be that way.\n')
    self.Destroy()
    sys.exit(0)

class MainWindow(wx.Frame):
  def __init__(self, parent, title, the_socket):
    wx.Frame.__init__(self, parent, title=title, size=WINDOW_SIZE)

    self.SetLabel("DTA5")
    self.sock = the_socket

    self.cmds = []
    self.ips = [0]
    self.hn = 0
    
    self.cur_cmd = ''
    self.cur_ip  = 0

    self.read_queue_timer = wx.Timer(self)
    self.Bind(wx.EVT_TIMER, self.check_input_socket, self.read_queue_timer)
    self.read_queue_timer.Start(SOCKET_POLL_TIMER)

    self.SetFont(the_font)
    self.default_attr   = DEFAULT_ATTR
    self.cmd_echo_attr  = CMD_ECHO_ATTR
    self.speech_attr    = SPEECH_ATTR
    self.system_attr    = SYSTEM_ATTR
    self.input_attr     = INPUT_ATTR
    self.rev_input_attr = REV_INPUT_ATTR

    self.SetBackgroundColour(WINDOW_BG_COLOR)
    self.SetForegroundColour(WINDOW_FG_COLOR)

    self.top_bar = wx.StaticText(self)
    self.bottom_bar = wx.StaticText(self)
    self.scrollback = wx.TextCtrl(self, style=wx.TE_MULTILINE|wx.TE_RICH)
    self.input_line = wx.TextCtrl(self, id=wx.ID_ANY,
      style=wx.TE_READONLY|wx.HSCROLL|wx.TE_MULTILINE)
    
    self.scrollback.SetBackgroundColour(TEXT_BG_COLOR)
    self.scrollback.SetForegroundColour(TEXT_FG_COLOR)
    self.input_line.SetBackgroundColour(INPUT_BG_COLOR)
    self.input_line.SetForegroundColour(INPUT_FG_COLOR)

    self.scrollback.Bind(wx.EVT_CHAR, self.char_input)
    #~ self.scrollback.Bind(wx.EVT_TEXT_PASTE, self.paste)
    self.input_line.Bind(wx.EVT_CHAR, self.char_input)

    self.sizer = wx.BoxSizer(wx.VERTICAL)
    self.sizer.Add(self.top_bar, 0, wx.EXPAND)
    self.sizer.Add(self.scrollback, 1, wx.EXPAND)
    self.sizer.Add(self.bottom_bar, 0, wx.EXPAND)
    self.sizer.Add(self.input_line, 0, wx.EXPAND)
    
    self.keyvent_listen = True

    self.SetSizer(self.sizer)
    self.SetAutoLayout(1)
    self.Show()
    self.scrollback.SetFocus()
  
  def display_command(self, cmd, ip):
    self.input_line.SetDefaultStyle(self.input_attr)
    self.input_line.SetValue(cmd[:ip])
    self.input_line.SetDefaultStyle(self.rev_input_attr)
    if ip < len(cmd):
      self.input_line.AppendText(cmd[ip])
      self.input_line.SetDefaultStyle(self.input_attr)
      self.input_line.AppendText(cmd[ip+1:])
    else:
      self.input_line.AppendText('_')
  
  def display_history(self, n):
    if n == len(self.cmds):
      self.display_command(self.cur_cmd, self.cur_ip)
    else:
      self.display_command(self.cmds[n], self.ips[n])

  def add_to_scrollback(self, txt, attr=None):
    if len(self.scrollback.GetValue()) > SCROLLBACK_SIZE:
      self.scrollback.SetValue(
        self.scrollback.GetValue()[-SCROLLBACK_SIZE:])
    if attr is None:
      self.scrollback.SetDefaultStyle(self.default_attr)
    else:
      self.scrollback.SetDefaultStyle(attr)
    self.scrollback.AppendText(txt + '\n')
    
  def pre_add(self, txt, attr=None):
    if attr is None:
      self.scrollback.SetDefaultStyle(self.default_attr)
    else:
      self.scrollback.SetDefaultStyle(attr)
    self.scrollback.AppendText(txt)
    
  def process_text(self, txt):
    self.add_to_scrollback(txt)
  
  def process_speech(self, txt):
    m = speech_re.match(txt)
    if m:
      preamble = txt[:m.end()]
      speech   = txt[m.end():]
      self.pre_add(preamble, self.speech_attr)
      self.add_to_scrollback(speech)
    else:
      self.add_to_scrollback(txt)

  def process_input(self, m):
    typ = m[u'Type']
    pld = m[u'Text']
    if typ == u'txt':
      self.process_text(pld)
    elif typ == u'echo':
      self.add_to_scrollback('\n' + pld, self.cmd_echo_attr)
    elif typ == u'speech':
      self.process_speech(pld)
    elif typ == u'headline':
      self.top_bar.SetLabel(pld)
    elif typ == u'sys':
      self.add_to_scrollback('\n' + pld, self.sys_msg_attr)
    elif typ == u'logout':
      self.quit_me(pld)
    else:
      sys.stderr.write('Unrecognized input: {}\n'.format(m))
      #~ if typ == "PING":
          #~ self.ping_back(dat)
      #~ elif typ == "TEXT":
          #~ self.add_to_scrollback(dat)
      #~ elif typ == "CMDECHO":
          #~ self.add_to_scrollback(dat, self.cmd_echo_attr)
      #~ elif typ == "TOP-LINE":
          #~ self.top_bar.SetLabel(dat)
      #~ elif typ == "BOTTOM-LINE":
          #~ self.bottom_bar.SetLabel(dat)
      #~ elif typ == "QUIT":
          #~ self.quit_me(dat)
      #~ else:
          #~ sys.stderr.write("Unrecognized input type: ({}, {})\n".format(
              #~ typ, dat))

  def read_queue(self):
    cont = True
    while cont:
      m = self.sock.read()
      if m is None:
        cont = False
      else:
        self.process_input(m)

  def check_input_socket(self, evt=None):
    try:
      if self.sock.recv() > 0:
        self.read_queue()
    except IOError as e:
      self.read_queue()
      self.quit_me(str(e))
      
  def cmd_len(self):
    if self.hn > len(self.cmds):
      return len(self.cmds[self.hn])
    else:
      return len(self.cur_cmd)

  def char_input(self, evt):
    k = evt.GetKeyCode()
    if k >= 32 and k <= 126:
      self.insert_char(k)
    elif k == wx.WXK_BACK: #backspace
      self.backspace()
    elif k == wx.WXK_DELETE:
      self.delete()
    elif k == wx.WXK_LEFT:
      self.move_ip(-1)
    elif k == wx.WXK_RIGHT:
      self.move_ip(1)
    elif k == wx.WXK_HOME:
      self.move_ip(-self.cmd_len())
    elif k == wx.WXK_END:
      self.move_ip(self.cmd_len())
    elif k == wx.WXK_UP:
      self.scroll_history_back()
    elif k == wx.WXK_DOWN:
      self.scroll_history_forward()
    elif k == wx.WXK_RETURN:
      self.hit_return()
  
  def bring_history_forward(self):
    if self.hn < len(self.cmds):
      self.cur_cmd = self.cmds[self.hn]
      self.cur_ip = self.ips[self.hn]
      self.hn = len(self.cmds)
  
  def insert_char(self, ch):
    self.bring_history_forward()
    cur_txt = self.cur_cmd
    cur_ip  = self.cur_ip
    new_text = '{}{}{}'.format(cur_txt[:cur_ip], chr(ch), cur_txt[cur_ip:])
    self.cur_cmd = new_text
    self.cur_ip = self.cur_ip + 1
    self.display_command(self.cur_cmd, self.cur_ip)
  
  def hit_return(self):
    self.bring_history_forward()
    if len(self.cur_cmd) > 0:
      self.send_cmd(self.cur_cmd)
      if len(self.cmds) == 0 or self.cur_cmd != self.cmds[-1]:
        self.cmds.append(self.cur_cmd)
        self.ips.append(self.cur_ip)
      self.cur_cmd = ''
      self.cur_ip = 0
      self.hn = len(self.cmds)
      self.display_history(self.hn)

  def move_ip(self, delta):
    if self.hn < len(self.cmds):
      newip = self.ips[self.hn] + delta
      if newip < 0:
        self.ips[self.hn] = 0
      elif newip > len(self.cmds[self.hn]):
        self.ips[self.hn] = len(self.cmds[self.hn])
      else:
        self.ips[self.hn] = newip
    else:
      newip = self.cur_ip + delta
      if newip < 0:
        newip = 0
      elif newip > len(self.cur_cmd):
        newip = len(self.cur_cmd)
      self.cur_ip = newip
    self.display_history(self.hn)
  
  def scroll_history_back(self):
    if self.hn > 0:
      self.hn = self.hn - 1
      self.display_history(self.hn)
  
  def scroll_history_forward(self):
    if self.hn < len(self.cmds):
      self.hn = self.hn + 1
      self.display_history(self.hn)
  
  def backspace(self):
    self.bring_history_forward()
    if self.cur_ip > 0:
      cmd = self.cur_cmd
      ip = self.cur_ip-1
      self.cur_cmd = cmd[:ip] + cmd[ip+1:]
      self.cur_ip = ip
    self.display_history(self.hn)
  
  def delete(self):
    self.bring_history_forward()
    if self.cur_ip < len(self.cur_cmd) - 1:
      cmd = self.cur_cmd
      ip = self.cur_ip
      self.cur_cmd = cmd[ip:] + cmd[:ip+1]
    self.display_history(self.hn)
  
  #~ def paste(self, evt):
    #~ if not wx.TheClipboard.IsOpened():
      #~ wx.TheClipboard.Open()
    #~ do = wx.TextDataObject()
    #~ success = wx.TheClipboard.GetData(do)
    #~ if success:
      #~ charz = do.GetText()
      #~ for ch in charz:
        #~ self.insert_char(ord(ch))

  def send_cmd(self, cmd):
    if len(cmd) > 0:
      msg = {"Type": "cmd", "Text": cmd}
      self.sock.enque(msg)
      self.sock.send()
    else:
      pass
  
  def ping_back(self, timestamp):
      self.debug_msg('* pinging back {} *'.format(timestamp))
      msg = dsock.comm_encode('PING', timestamp)
      self.sock.enque(msg)
      self.sock.send()

  def quit_me(self, msg='no reason'):
      global the_error_frame
      the_error_frame = ErrorWindow(msg, 'Quitting')
      try:
        self.sock.close()
      except IOError:
        pass
      self.Destroy()
  
  def debug_msg(self, msg):
      if DEBUG is True:
          self.add_to_scrollback(msg, DEBUG_ATTR)

#####

try:
    app = wx.App()
    exec_config()

    login_frame = LoginWindow(dconfig.get('LOGIN'), dconfig.get('PASSWORD'))
    app.MainLoop()
except Exception as e:
    print e
    the_frame.quit_me("Run-time exception: {} ({}).\n".format(e, repr(e)))
