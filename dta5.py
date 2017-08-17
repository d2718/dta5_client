#!/usr/bin/python

'''
DTA5 game client.

Updated: 2016-08-06
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

CLIENT_VERSION = 170807

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
    ('WINDOW_BG_COLOR', 'DARK GREY', dconfig.STRING | dconfig.STRIP),
    ('WINDOW_FG_COLOR', 'blue', dconfig.STRING | dconfig.STRIP),
    ('INPUT_BG_COLOR', 'WHITE', dconfig.STRING | dconfig.STRIP),
    ('INPUT_FG_COLOR', 'BLACK', dconfig.STRING | dconfig.STRIP),
    ('COMMAND_ECHO_FG_COLOR', 'YELLOW', dconfig.STRING | dconfig.STRIP),
    ('COMMAND_ECHO_BG_COLOR', None, dconfig.STRING | dconfig.STRIP),
    ('SPEECH_COLOR', None, dconfig.STRING | dconfig.STRIP),
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

SPEECH_COLOR = "#0f0"

speech_re = re.compile(r'\S+ (says?|asks?|exclaims?)[^"]+')

the_font = None
the_frame = None
login_frame = None
the_error_frame = None

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
        self.SetBackgroundColour(dconfig.get('WINDOW_BG_COLOR'))
        self.SetForegroundColour(dconfig.get('WINDOW_FG_COLOR'))
        
        self.mesg = wx.StaticText(self)
        self.mesg.SetLabel(msg)
        self.bttn = wx.Button(self, label='k!')
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
        self.Close()
        sys.exit(0)

class LoginWindow(wx.Frame):
    def __init__(self, login=None, password=None):
        wx.Frame.__init__(self, None, title='DTA4 Login')

        self.SetLabel('DTA4 Login')
        self.SetFont(the_font)
        self.SetBackgroundColour(dconfig.get('WINDOW_BG_COLOR'))
        self.SetForegroundColour(dconfig.get('WINDOW_FG_COLOR'))

        self.panel = wx.Panel(self)
        self.panel.SetForegroundColour(dconfig.get('WINDOW_FG_COLOR'))
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
        the_socket = djsock.DJSocket(dconfig.get('HOST'),
                                     dconfig.get('PORT'),
                                     dconfig.get('TIMEOUT'))
        msg = the_socket.suck_read(1.0)
        print(msg)
        the_socket.enque({"Type": "version", "Payload": "{}".format(CLIENT_VERSION)})
        the_socket.enque({"Type": "uname", "Payload": uname})
        the_socket.enque({"Type": "pwd",   "Payload": paswd})
        the_socket.send()
        #msg = the_socket.suck_read(wait=dconfig.get('TIMEOUT'), interval=0.2)
        #if typ == "WELCOME":
        self.spawn_main_window(the_socket)
        #~ elif typ == "TEXT":
            #~ the_error_frame = ErrorWindow(dat, 'Error')
            #~ self.Close()
        #~ else:
            #~ the_error_frame = ErrorWindow(
                #~ "The server failed to respond appropriately.\n")
            #~ self.Close()

    def spawn_main_window(self, the_socket):
        global the_frame
        the_frame = MainWindow(None, "DTA5", the_socket)
        sys.stdout.write(read_file(NEWS_FILE))
        the_frame.sock.recv()
        the_frame.read_queue()
        self.Close()

    def cancel(self, evt):
        sys.stderr.write('Fine, be that way.\n')
        self.Close()
        sys.exit(0)

class MainWindow(wx.Frame):
    def __init__(self, parent, title, the_socket):
        wx.Frame.__init__(self, parent, title=title, size=WINDOW_SIZE)

        self.SetLabel("DTA5")
        self.sock = the_socket

        self.current_cmd = ''
        self.cmd_history = []
        self.history_idx = 0

        self.read_queue_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.check_input_socket, self.read_queue_timer)
        self.read_queue_timer.Start(100)

        self.SetFont(the_font)
        self.default_attr = wx.TextAttr(dconfig.get('TEXT_FG_COLOR'),
                                        dconfig.get('TEXT_BG_COLOR'))
        if dconfig.get('COMMAND_ECHO_BG_COLOR') is not None:
            self.cmd_echo_attr = wx.TextAttr(
                                    dconfig.get('COMMAND_ECHO_FG_COLOR'),
                                    dconfig.get('COMMAND_ECHO_BG_COLOR'))
        else:
            self.cmd_echo_attr = wx.TextAttr(
                                    dconfig.get('COMMAND_ECHO_FG_COLOR'))
        if dconfig.get('SPEECH_COLOR') is not None:
            self.speech_attr = wx.TextAttr(
                                  dconfig.get('SPEECH_COLOR'),
                                  dconfig.get('TEXT_BG_COLOR'))
        else:
            self.speech_attr = wx.TextAttr(
                                  SPEECH_COLOR, dconfig.get('TEXT_BG_COLOR'))

        self.SetBackgroundColour(dconfig.get('WINDOW_BG_COLOR'))
        self.SetForegroundColour(dconfig.get('WINDOW_FG_COLOR'))

        self.top_bar = wx.StaticText(self)
        self.bottom_bar = wx.StaticText(self)
        self.scrollback = wx.TextCtrl(self, style=wx.TE_MULTILINE|wx.TE_RICH)
        self.input_line = wx.TextCtrl(self)

        self.scrollback.SetBackgroundColour(dconfig.get('TEXT_BG_COLOR'))
        self.scrollback.SetForegroundColour(dconfig.get('TEXT_FG_COLOR'))
        self.input_line.SetBackgroundColour(dconfig.get('INPUT_BG_COLOR'))
        self.input_line.SetForegroundColour(dconfig.get('INPUT_FG_COLOR'))

        #~ wx.EVT_CHAR(self.input_line, self.char_input)
        #~ wx.EVT_CHAR(self.scrollback, self.char_input)
        self.scrollback.Bind(wx.EVT_CHAR, self.char_input)
        self.input_line.Bind(wx.EVT_CHAR, self.char_input)
        
        #~ self.Bind(wx.EVT_CHAR, self.char_input)
        #~ self.scrollback.Bind(wx.EVT_CHAR, self.char_input)
        #~ self.input_line.Bind(wx.EVT_CHAR, self.char_input)
        #~ self.Bind(wx.EVT_CHAR, self.char_input)

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
      pld = m[u'Payload']
      if typ == u'txt':
        self.process_text(pld)
      elif typ == u'echo':
        self.add_to_scrollback('\n' + pld, self.cmd_echo_attr)
      elif typ == u'headline':
        self.top_bar.SetLabel(pld)
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
            self.quit_me(str(e))

    def char_input(self, evt):
        if self.keyvent_listen:
          self.keyvent_listen = False
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
              self.move_ip(-len(self.input_line.GetValue()))
          elif k == wx.WXK_END:
              self.move_ip(len(self.input_line.GetValue()))
          elif k == wx.WXK_UP:
              self.scroll_history_back()
          elif k == wx.WXK_DOWN:
              self.scroll_history_forward()
          elif k == wx.WXK_RETURN:
              self.send_cmd(self.input_line.GetValue())
              self.input_line.SetValue('')
          
          self.scrollback.SetFocus()
          self.keyvent_listen = True

    def insert_char(self, ch):
        ipx = self.input_line.GetInsertionPoint()
        cur_txt = self.input_line.GetValue()
        new_txt = '{}{}{}'.format(
            cur_txt[:ipx],
            chr(ch),
            cur_txt[ipx:])
        self.input_line.SetValue(new_txt)
        self.input_line.SetInsertionPoint(ipx + 1)

    def move_ip(self, delta):
        newip = self.input_line.GetInsertionPoint() + delta
        if newip < 0:
            newip = 0
        elif newip > len(self.input_line.GetValue()):
            newip = len(self.input_line.GetValue())
        self.input_line.SetInsertionPoint(newip)

    def move_ip_left(self):
        ipx = self.input_line.GetInsertionPoint()
        if ipx > 0:
            self.input_line.SetInsertionPoint(ipx - 1)

    def move_ip_right(self):
        ipx = self.input_line.GetInsertionPoint()
        if ipx < len(self.input_line.GetValue()):
            self.input_line.SetInsertionPoint(ipx + 1)

    def scroll_history_back(self):
        if self.history_idx < len(self.cmd_history):
            if self.history_idx == 0:
                self.current_cmd = self.input_line.GetValue()
            self.history_idx += 1
            self.input_line.SetValue(self.cmd_history[-self.history_idx])
            self.move_ip(len(self.input_line.GetValue()))

    def scroll_history_forward(self):
        if self.history_idx > 0:
            self.history_idx -= 1
            if self.history_idx == 0:
                self.input_line.SetValue(self.current_cmd)
            else:
                self.input_line.SetValue(self.cmd_history[-self.history_idx])
            self.move_ip(len(self.input_line.GetValue()))

    def backspace(self):
        ipx = self.input_line.GetInsertionPoint()
        if ipx > 0:
            cur_txt = self.input_line.GetValue()
            self.move_ip_left()
            new_txt = '{}{}'.format(
                cur_txt[0:ipx-1],
                cur_txt[ipx:])
            self.input_line.SetValue(new_txt)
            self.input_line.SetInsertionPoint(ipx-1)

    def delete(self):
        cur_txt = self.input_line.GetValue()
        ipx = self.input_line.GetInsertionPoint()
        if ipx < len(cur_txt):
            new_txt = '{}{}'.format(
                cur_txt[0:ipx],
                cur_txt[ipx+1:])
            self.input_line.SetValue(new_txt)
            self.input_line.SetInsertionPoint(ipx)

    def send_cmd(self, cmd):
        if len(cmd) > 0:
            self.cmd_history.append(cmd)
            self.history_idx = 0
            msg = {"Type": "cmd", "Payload": cmd}
            self.sock.enque(msg)
            self.sock.send()
        else:
          pass
            #~ self.sock.enque(dsock.comm_encode('IDLE', ''))
            #~ self.sock.send()
    
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
        self.Close()
    
    def debug_msg(self, msg):
        if DEBUG is True:
            self.add_to_scrollback(msg, DEBUG_ATTR)

#####

dconfig.external_config(CONFIG_FILES)

if len(dconfig.get('WINDOW_SIZE')) != 2:
    sys.stderr.write('Bad window size in configuration file; using 640,480.\n')
    WINDOW_SIZE = (640, 480)
else:
    WINDOW_SIZE = dconfig.get('WINDOW_SIZE')
SCROLLBACK_SIZE = dconfig.get('SCROLLBACK_SIZE')

try:
    app = wx.App()
    the_font = wx.Font(
            family=wx.FONTFAMILY_TELETYPE,
            face=dconfig.get('FONT_FACE'),
            pointSize=dconfig.get('FONT_SIZE'),
            weight=wx.FONTWEIGHT_NORMAL,
            style=wx.FONTSTYLE_NORMAL)
    login_frame = LoginWindow(dconfig.get('LOGIN'), dconfig.get('PASSWORD'))
    app.MainLoop()
except Exception as e:
    the_frame.quit_me("Run-time exception: {} ({}).\n".format(e, repr(e)))
