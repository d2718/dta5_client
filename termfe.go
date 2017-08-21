//
// DTA5 terminal frontend
//
// 2017-08-20
//
package main

import( "bufio"; "encoding/json"; "fmt"; "io"; "log"; "net"; "os";
        "regexp"; "strings";
        "github.com/nsf/termbox-go";
        "github.com/d2718/dconfig";
)

// Configurable Values

var host = "localhost"
var port = 10102

var SpeechFg = termbox.ColorGreen
var SpeechBg = termbox.ColorBlack
var HeadTailFg = termbox.ColorWhite
var HeadTailBg = termbox.ColorBlue
var EchoFg = termbox.ColorYellow | termbox.AttrBold
var EchoBg = termbox.ColorBlack

var MaxScrollbackLines = 512
var MinScrollbackLines = 256

var SpeechRe = regexp.MustCompile(`^\S+ (says?|asks?|exclaims?)[^"]+`)

type CharClass int

const(  Whitespace CharClass = iota
        Normal
        Breaking
)

var BreakingChars = map[rune]bool{ 45: true, 47: true, 95: true }

type Cell termbox.Cell

func (c Cell) Class() CharClass {
  if c.Ch < 33 {
    return Whitespace
  } else if BreakingChars[c.Ch] {
    return Breaking
  } else {
    return Normal
  }
}

type Line struct {
  C      []Cell
  Width  int
  Starts []int
  Ends   []int
}

func (l Line) String() string {
  runez := make([]rune, 0, len(l.C))
  for _, ch := range l.C {
    runez = append(runez, ch.Ch)
  }
  return string(runez)
}

func (l Line) Len() int {
  if l.Starts == nil {
    return 0
  } else {
    return len(l.Starts)
  }
}

func (l *Line) nextWordEnd(pos int) int {
  fence := len(l.C)
  for n := pos; n < fence; n++ {
    if l.C[n].Class() == Whitespace {
      return n
    } else if l.C[n].Class() == Breaking {
      return n+1
    }
  }
  return fence
}

func (l *Line) nextWordStart(pos int) int {
  fence := len(l.C)
  for n := pos; n < fence; n++ {
    if l.C[n].Class() != Whitespace {
      return n
    }
  }
  return fence
}

func (l *Line) Wrap(width int) {
  
  log.Println("(*Line).Wrap() called... (", l.String(), ")")
  
  var c_idx int = 0
  var fence int = len(l.C)
  var starts []int = make([]int, 0, 1)
  var ends   []int = make([]int, 0, 0)
  
  var t, adv, l_idx int
  
  pre_start:
  // trim any whitespace before beginning the next line
  t = l.nextWordStart(c_idx)
  if t == fence { goto end }
  starts = append(starts, t)
  c_idx = t
  l_idx = 0
  
  //start:
  // Check to see if the current word is too long for the line; if so,
  // break the word at the terminal width.
  t = l.nextWordEnd(c_idx)
  adv = t - c_idx
  if adv >= width {
    c_idx = c_idx + width
    ends = append(ends, c_idx)
    goto pre_start
  }
  l_idx = l_idx + adv
  c_idx = c_idx + adv
  
  word_end:
  // Check to see if the next breakable spot is beyond the end of the line;
  // if so, wrap now.
  t = l.nextWordEnd(l.nextWordStart(c_idx))
  adv = t - c_idx
  l_idx = l_idx + adv
  if l_idx >= width {
    ends = append(ends, c_idx)
    goto pre_start
  }
  c_idx = c_idx + adv
  if c_idx == fence {
    ends = append(ends, c_idx)
    goto end
  }
  goto word_end
  
  end:
  l.Starts = starts
  l.Ends   = ends
  l.Width  = width
  
  log.Println("Starts, Ends, Width:", l.Starts, l.Ends, l.Width)
  log.Println("...(*Line) Wrap() ends")
  
}

func NewLine(text string, fg, bg termbox.Attribute) *Line {
  cellz := make([]Cell, 0, len(text))
  for _, ch := range text {
    cellz = append(cellz, Cell{ Ch: ch, Fg: fg, Bg: bg, })
  }
  
  return &Line{ C: cellz, Width: -1, Starts: nil, Ends: nil, }
}

func (l *Line) Add(text string, fg, bg termbox.Attribute) {
  for _, ch := range text {
    l.C = append(l.C, Cell{ Ch: ch, Fg: fg, Bg: bg, })
  }
  l.Width = -1
  l.Starts = nil
  l.Ends = nil
}

var Lines []*Line = make([]*Line, 0, 0)
var TermW, TermH int
var HeadY, SbackY, FootY, InputY int
var DefaultFg, DefaultBg = termbox.ColorDefault, termbox.ColorBlack
var HeadLine, FootLine *Line
var Input = make([]rune, 0, 0)
var IP int = 0
var ScrollbackPos int = 0
// var TermLock = new(sync.Mutex)
var EventChan = make(chan termbox.Event)
var KeepRunning = true
var CanScrollBack = false

func AddLine(newLine *Line) {
  log.Println("AddLine(", newLine.String(), "):")
  if len(Lines) > MaxScrollbackLines {
    log.Println("    reallocating buffer")
    new_lines := make([]*Line, 0, MaxScrollbackLines)
    new_lines = append(new_lines, Lines[len(Lines)-MinScrollbackLines:]...)
    Lines = new_lines
  }
  Lines = append(Lines, newLine)
  log.Println("    buffer lines:", len(Lines))
}

func AddDefaultLine(text string) {
  AddLine(NewLine(text, DefaultFg, DefaultBg))
}

func Redimension(x, y int) {
  TermW, TermH = x, y
  log.Println("Redimension()ing: (", TermW, TermH, ")")
}

func Recalculate() {
  HeadY  = 0
  SbackY = 1
  FootY  = TermH - 2
  InputY = TermH -1
  log.Println("Recalculate()ing: HeadY, SbackY, FootY, InputY:",
              HeadY, SbackY, FootY, InputY)
}

func DrawHeadLine() {
  var fence int
  
  if len(HeadLine.C) <= TermW {
    fence = len(HeadLine.C)
  } else {
    fence = TermW
  }
  
  for n := 0; n < fence; n++ {
    ch := HeadLine.C[n]
    termbox.SetCell(n, HeadY, ch.Ch, ch.Fg, ch.Bg)
  }
  for n := fence; n < TermW; n++ {
    termbox.SetCell(n, HeadY, ' ', HeadTailFg, HeadTailBg)
  }
}

func DrawFootline() {
  var fence int
  
  if len(FootLine.C) <= TermW {
    fence = len(FootLine.C)
  } else {
    fence = TermW
  }
  
  for n := 0; n < fence; n++ {
    ch := FootLine.C[n]
    termbox.SetCell(n, FootY, ch.Ch, ch.Fg, ch.Bg)
  }
  for n := fence; n < TermW; n++ {
    termbox.SetCell(n, FootY, ' ', HeadTailFg, HeadTailBg)
  }
}

func DrawInput() {
  
  //~ log.Println("DrawInput() called...")
  //~ log.Println("Input:", string(Input))
  //~ log.Println("IP, TermW:", IP, TermW)
  
  var n int = 0
  for ; n < IP; n++ {
    termbox.SetCell(n, InputY, Input[n], DefaultFg, DefaultBg)
  }
  if IP == len(Input) {
    termbox.SetCell(IP, InputY, ' ', DefaultFg | termbox.AttrReverse,
                                     DefaultBg | termbox.AttrReverse)
    for n = IP+1; n < TermW; n++ {
      termbox.SetCell(n, InputY, ' ', DefaultFg, DefaultBg)
    }
  } else {
    termbox.SetCell(IP, InputY, Input[IP], DefaultFg | termbox.AttrReverse,
                                           DefaultBg | termbox.AttrReverse)
    for n = IP+1; n < len(Input); n++ {
      termbox.SetCell(n, InputY, Input[n], DefaultFg, DefaultBg)
    }
    for n = len(Input); n < TermW; n++ {
      termbox.SetCell(n, InputY, ' ', DefaultFg, DefaultBg)
    }
  }
}

func DrawLineChunk(l *Line, chunk int, y int) {
  log.Println("(*Line) DrawLineChunk(): [", l.Starts[chunk], l.Ends[chunk],
              "], pos:", y, "(", l.String(), ")")
  var term_x int = 0
  var end_x  int = l.Ends[chunk]
  var ch Cell
  for n := l.Starts[chunk]; n < end_x; n++ {
    ch = l.C[n]
    termbox.SetCell(term_x, y, ch.Ch, ch.Fg, ch.Bg)
    term_x++
  }
  for ; term_x < TermW; term_x++ {
    termbox.SetCell(term_x, y, ' ', DefaultFg, DefaultBg)
  }
}

func ScrollBackward() {
  if CanScrollBack {
    delta := (FootY - SbackY) - 2
    ScrollbackPos = ScrollbackPos + delta
    DrawScrollback()
  }
}

func ScrollForward() {
  if ScrollbackPos > 0 {
    delta := (FootY - SbackY) - 2
    ScrollbackPos = ScrollbackPos - delta
    if ScrollbackPos < 0 {
      ScrollbackPos = 0
    }
    DrawScrollback()
  }
}

func ScrollToFront() {
  if ScrollbackPos > 0 {
    ScrollbackPos = 0
    DrawScrollback()
  }
}

func DrawScrollback() {
  log.Println("DrawScrollback() called...")
  write_start := FootY - 1
  yp := write_start + ScrollbackPos
  lidx := len(Lines) - 1
  var cur_line *Line
  CanScrollBack = true
  
  for (yp >= SbackY) && (lidx >= 0) {
    if lidx == 0 {
      CanScrollBack = false
    }
    
    log.Println("yp, lidx:", yp, lidx)
    
    cur_line = Lines[lidx]
    if cur_line.Width != TermW {
      cur_line.Wrap(TermW)
    }
    
    for n := cur_line.Len()-1; (n >= 0) && (yp >= SbackY); n-- {
      if yp <= write_start {
        DrawLineChunk(cur_line, n, yp)
      }
      yp--
    }
    lidx--
  }
  
  for yp >= SbackY {
    for n := 0; n < TermW; n++ {
      termbox.SetCell(n, yp, ' ', DefaultFg, DefaultBg)
    }
    yp--
  }
  log.Println("...DrawScrollback() finished")
}

func InsertInInput(r rune) {
  if IP == len(Input) {
    Input = append(Input, r)
  } else {
    new_input := make([]rune, 0, len(Input)+1)
    new_input = append(new_input, Input[:IP]...)
    new_input = append(new_input, r)
    new_input = append(new_input, Input[IP:]...)
    Input = new_input
  }
  IP++
  
  DrawInput()
}

func InputBackspace() {
  if IP > 0 {
    Input = append(Input[:IP-1], Input[IP:]...)
    IP--
    DrawInput()
  }
}

func InputDelete() {
  if IP < len(Input) {
    Input = append(Input[:IP], Input[IP+1:]...)
    DrawInput()
  }
}

func MoveInputIp(delta int) {
  new_ip := IP + delta
  if new_ip < 0 {
    IP = 0
  } else if new_ip > len(Input) {
    IP = len(Input)
  } else {
    IP = new_ip
  }
  DrawInput()
}

//~ func SendCommand() {
  //~ log.Println("SendCommand() called...")
  //~ if len(Input) > 0 {
    //~ log.Println("Input is", string(Input))
    //~ Lines = append(Lines, NewLine(string(Input), DefaultFg, DefaultBg))
    //~ Input = make([]rune, 0, 0)
    //~ IP = 0
  
    //~ DrawScrollback()
    //~ DrawInput()
  //~ }
  
  //~ log.Println("...SendCommand() finished")
//~ }

func SendCommand() {
  log.Println("SendCommand():")
  if len(Input) > 0 {
    e := Env{ Type: "cmd", Text: string(Input) }
    ncdr.Encode(e)
    log.Println("    sent:", e)
    Input = make([]rune, 0, 0)
    IP = 0
    DrawInput()
  }
}

func ListenForEvents() {
  for {
    EventChan <- termbox.PollEvent()
  }
}

func HandleEvent(e termbox.Event) {
  switch e.Type {
  
  case termbox.EventKey:
  
    if e.Ch != 0 {
      InsertInInput(e.Ch)
      FootLine = NewLine(fmt.Sprintf("Ch: %d, Mod: %d", e.Ch, e.Mod), HeadTailFg, HeadTailBg)
    } else {
      switch e.Key {
      case termbox.KeySpace:
        InsertInInput(' ')
      case termbox.KeyBackspace, 127:
        InputBackspace()
      case termbox.KeyDelete:
        InputDelete()
      case termbox.KeyArrowLeft:
        MoveInputIp(-1)
      case termbox.KeyArrowRight:
        MoveInputIp(1)
      case 13:    // return
        SendCommand()
      case termbox.KeyPgup:
        ScrollBackward()
      case termbox.KeyPgdn:
        ScrollForward()
      case termbox.KeyF12:
        ScrollToFront()
      case termbox.KeyF1:
        KeepRunning = false
      }
      FootLine = NewLine(fmt.Sprintf("Key: %d, Mod: %d", e.Key, e.Mod), HeadTailFg, HeadTailBg)
    }
    DrawFootline()
    
  case termbox.EventResize:
    log.Println("Rec'd EventResize: (", e.Width, e.Height, ")")
    termbox.Clear(DefaultFg, DefaultBg)
    Redimension(e.Width, e.Height)
    Recalculate()
    DrawHeadLine()
    DrawScrollback()
    DrawFootline()
    DrawInput()
    termbox.Sync()
  }

  termbox.Flush()
}

func die(err error, fmtstr string, args ...interface{}) {
  if err != nil {
    fmt.Printf(fmtstr, args...)
    panic(err)
  }
}

type Env struct {
  Type string
  Text string
}

var EnvChan = make(chan Env, 256)
const clientVersion = 170821
var ncdr *json.Encoder
var dcdr *json.Decoder

func ListenForEnvelopes(d *json.Decoder) {
  var e Env
  var err error
  
  for {
    err = d.Decode(&e)
    if err == nil {
      log.Println("ListenForEnvelopes() rec'd Env:", e)
      EnvChan <- e
    } else if err == io.EOF {
      log.Println("ListenForEnvelopes(): EOF rec'd; quitting")
      EnvChan <- Env{ Type: "logout", Text: "connection broken" }
      return
    } else {
      log.Println("Error decoding JSON:", err)
    }
  }
}

func ProcessEnvelope(e Env) {
  switch e.Type {
  
  case "txt", "wall", "sys":
    for _, line := range strings.Split(e.Text, "\n") {
      AddDefaultLine(line)
    }
    DrawScrollback()
  case "headline":
    HeadLine = NewLine(e.Text, HeadTailFg, HeadTailBg)
    DrawHeadLine()
  case "echo":
    echo_line := NewLine(e.Text, EchoFg, EchoBg)
    AddLine(echo_line)
    DrawScrollback()
  case "speech":
    idxs := SpeechRe.FindStringIndex(e.Text)
    if idxs == nil {
      AddDefaultLine(e.Text)
    } else {
      new_line := NewLine(e.Text[:idxs[1]], SpeechFg, SpeechBg)
      new_line.Add(e.Text[idxs[1]:], DefaultFg, DefaultBg)
      AddLine(new_line)
    }
    DrawScrollback()
  case "logout":
    KeepRunning = false
    fmt.Printf("%s\n", e.Text)
  default:
    log.Println("Unknown Env type:", e)
  }
  
  termbox.Flush()
}

func Config() {
  dconfig.Reset()
  dconfig.AddString(&host,            "host", dconfig.STRIP)
  dconfig.AddInt(&port,               "port", dconfig.UNSIGNED)
  dconfig.AddInt(&MinScrollbackLines, "scrollback", dconfig.UNSIGNED)
  dconfig.Configure([]string{"dta5.conf"}, true)
  
  MaxScrollbackLines = 2 * MinScrollbackLines
}

func main() {
  
  logf, err := os.OpenFile("term.log", os.O_TRUNC|os.O_WRONLY|os.O_CREATE, 0644)
  if err != nil {
    panic(err)
  }
  defer logf.Close()
  log.SetOutput(logf)
  
  Config()
  
  login_scanner := bufio.NewScanner(os.Stdin)
  fmt.Printf("login: ")
  login_scanner.Scan()
  uname := login_scanner.Text()
  fmt.Printf("password: ")
  login_scanner.Scan()
  pwd := login_scanner.Text()
  
  conn, err := net.Dial("tcp", fmt.Sprintf("%s:%d", host, port))
  die(err, "Error connecting to %s:%d: %s\n", host, port, err)
  defer conn.Close()
  
  ncdr = json.NewEncoder(conn)
  dcdr = json.NewDecoder(conn)
  
  var m Env
  err = dcdr.Decode(&m)
  die(err, "Error decoding welcome message: %s\n", err)
  if m.Type != "version" {
    die(fmt.Errorf("bad message"), "Welcome message incorrect type: %q\n", m)
  }
  fmt.Printf("Req'd frontend version: %s\n", m.Text)
  
  err = ncdr.Encode(Env{ Type: "version", Text: fmt.Sprintf("%d", clientVersion) })
  die(err, "Error sending version: %s\n", err)
  err = ncdr.Encode(Env{ Type: "uname", Text: uname })
  die(err, "Error sending login: %s\n", err)
  err = ncdr.Encode(Env{ Type: "pwd", Text: pwd })
  die(err, "Error sending password: %s\b", err)
  
  err = termbox.Init()
  if err != nil {
    panic(err)
  }
  defer termbox.Close()
  log.Println("termbox initialized")
  
  termbox.SetInputMode(termbox.InputAlt)
  
  HeadLine = NewLine("", DefaultFg, DefaultBg)
  FootLine = NewLine("", DefaultFg, DefaultBg)
  
  {
    x, y := termbox.Size()
    Redimension(x, y)
    Recalculate()
    DrawHeadLine()
    DrawScrollback()
    DrawFootline()
    DrawInput()
  }
  
  go ListenForEnvelopes(dcdr)
  go ListenForEvents()
  
  for KeepRunning {
    select {
    case e := <- EventChan:
      HandleEvent(e)
    case e := <- EnvChan:
      ProcessEnvelope(e)
    }
  }
}