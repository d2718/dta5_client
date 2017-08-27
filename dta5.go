//
// DTA5 terminal frontend
//
// 2017-08-27
//
package main

import( "bufio"; "encoding/json"; "flag"; "fmt"; "io"; "io/ioutil";
        "log"; "net"; "os"; "regexp"; "strings";
        "github.com/nsf/termbox-go";
        "github.com/d2718/dconfig";
)

const DEBUG bool = false
const clientVersion = 170827

// Configurable Values
// (Some are currently configurable; some are potentially configurable at
// some point in the future.)

var host = "localhost"
var port = 10102

var SpeechFg   = termbox.ColorGreen
var SpeechBg   = termbox.ColorBlack
var HeadTailFg = termbox.ColorWhite
var HeadTailBg = termbox.ColorBlue
var EchoFg     = termbox.ColorYellow
var EchoBg     = termbox.ColorBlack
var SysFg      = termbox.ColorMagenta
var SysBg      = termbox.ColorBlack
// Whether a blank line should be inserted before echoed commands to
// increase readability.
var SkipAfterSend = true
// Whether the contents of fe_news.txt should be echoed to the terminal
// window upon launch.
var ShowNews      = true
var Uname = ""
var Pwd   = ""

// Size of the scrollback history in Lines triggering the oldest to be
// discarded.
var MaxScrollbackLines = 512
// Number of most recent lines to keep when scrollback history is being trimmed.
var MinScrollbackLines = 256
// When scrolling the game window history back (and forward), the number of
// rows of text adjacent screens should have in common.
var ScrollbackOverlap = 2
// Number of remembered commands that triggers the command history to be
// trimmed.
var MaxCmdHistSize     = 128
// Number of most recent commands to keep after trimming.
var MinCmdHistSize     = 64
// Minimum size (in characters) of a command for it to be remembered.
var MinCmdLen int = 3

var DefaultCfgFile = "dta5.conf"
// Used by ProcessEnvelope() to add color to the first part of lines of
// dialog (so they stand out).
var SpeechRe = regexp.MustCompile(`^[^"]+ (says?|asks?|exclaims?)[^"]+`)
var NewsFile = "fe_news.txt"
var LogFileName  = "termfe.log"
var LogFile *os.File
// Number of unprocessed termbox.Events that are allowed to pile up before
// they start getting dropped. Honestly, the program seems to run just fine
// with an unbuffered event channel.
var EventChanSize = 16

// The CharClass type is used by the line wrapping algorithm to help
// identify where text should be wrapped. "Breaking" characters are characters
// that can be wrapped directly after, even in the middle of a word (so far
// just '-', '/', '_').
//
type CharClass int

const(  Whitespace CharClass = iota
        Normal
        Breaking
)

var BreakingChars = map[rune]bool{ 45: true, 47: true, 95: true }

// I probably didn't need to redefine the termbox.Cell.
type Cell termbox.Cell

// (Cell) CharClass() returns what class of character (Normal, Whitespace,
// Breaking) its receiver has. This is obviously used during wrapping.
//
func (c Cell) Class() CharClass {
  if c.Ch < 33 {
    return Whitespace
  } else if BreakingChars[c.Ch] {
    return Breaking
  } else {
    return Normal
  }
}

// A Line represents a single newline-terminated "line" of text in the
// game window. If it is longer than the window is wide, it will be wrapped
// and occupy more than a single row of characters on the terminal window.
//
// The wrapping algorithm (see (*Line) Wrap(), below) stores the indices of
// the Cell slice where each successive wrapped line of text should start
// and end. The DrawScrollBack() function uses these offsets to appropriately
// populate the game window with text.
//
// The Width field stores the window width for which the Line was wrapped,
// so that it only needs to be re-wrapped if the window width changes.
//
type Line struct {
  C      []Cell
  Width  int
  Starts []int
  Ends   []int
}

// This is only really used for debugging and logging.
//
func (l Line) String() string {
  runez := make([]rune, 0, len(l.C))
  for _, ch := range l.C {
    runez = append(runez, ch.Ch)
  }
  return string(runez)
}

// (Line) Len() returns the number of rows of characters the given Line has
// been wrapped to display. It is a poorly-named function. Sorry.
//
func (l Line) Len() int {
  if l.Starts == nil {
    return 0
  } else {
    return len(l.Starts)
  }
}

// Return the next index after pos where the Line could break.
//
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

// Return the next index after pos where a new line of text could start
// (that is, the index of the first non-whitespace character).
//
func (l *Line) nextWordStart(pos int) int {
  fence := len(l.C)
  for n := pos; n < fence; n++ {
    if l.C[n].Class() != Whitespace {
      return n
    }
  }
  return fence
}

// (*Line) Wrap() steps through the Line's Cells, recording the offsets
// where each row of text should begin and end. This information is then used
// by DrawScrollBack() (below) when writing characters to the game window.
//
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
  if len(starts) == 0 {
    starts = []int{0}
    ends   = []int{0}
  }
  l.Starts = starts
  l.Ends   = ends
  l.Width  = width
  
  log.Println("Starts, Ends, Width:", l.Starts, l.Ends, l.Width)
  log.Println("...(*Line) Wrap() ends")
  
}

// Returns a new *Line with the given text and attributes.
//
func NewLine(text string, fg, bg termbox.Attribute) *Line {
  cellz := make([]Cell, 0, len(text))
  for _, ch := range text {
    cellz = append(cellz, Cell{ Ch: ch, Fg: fg, Bg: bg, })
  }
  
  return &Line{ C: cellz, Width: -1, Starts: nil, Ends: nil, }
}

// Appends the given text with the supplied attributes to the receiving *Line.
//
func (l *Line) Add(text string, fg, bg termbox.Attribute) {
  for _, ch := range text {
    l.C = append(l.C, Cell{ Ch: ch, Fg: fg, Bg: bg, })
  }
  l.Width = -1
  l.Starts = nil
  l.Ends = nil
}

// All currently-remembered Lines of game window history.
var Lines []*Line = make([]*Line, 0, 0)
// Dimensions of the terminal window. Set with Recalculate() (below).
var TermW, TermH int
// Vertical offsets of the Header line, the game window, the Footer line,
// and the command input line.
var HeadY, SbackY, FootY, InputY int
// If the insertion point in the command entry line gets this far to the
// right, the view of the command entry line will scroll to prevent it from
// moving any farther.
var InputRL int
// Default terminal colors.
var DefaultFg, DefaultBg = termbox.ColorDefault, termbox.ColorBlack
// Contents of the lines directly above and below the game window. As of
// 2017-08-27, the HeadLine shows the character's current Room name, and
// the FootLine shows debugging information (when DEBUG == true).
var HeadLine, FootLine *Line
// Characters in the command currently being input.
var Input = make([]rune, 0, 0)
// Offset of the insertion point in the Input slice.
var IP int = 0
// The number of rows of text the game window has been scrolled back. (This is
// not Lines, but physical rows of characters.)
var ScrollbackPos int = 0
// Slice storing remembered commands.
var cmdHist = make([]string, 0, 0)
// Which remembered command in the command history is currently being shown.
// This is equal to len(cmdHist) when the newest, not-yet-remembered command
// is being entered.
var cmdHistPtr int = 0
// Where the latest command is stored when the player starts scrolling back
// through the command history.
var cmdStash []rune
// Where termbox.Events are queued by the goroutine that listens for them.
// (NB: All evidence suggests that this channel doesn't even need to be
// buffered, and while I tend to agree with YAGN, accommodating the possibility
// of a really fast typist with a really slow computer doesn't seem to
// noticeably complicate the implementation.
var EventChan = make(chan termbox.Event, EventChanSize)
// This gets set to false when the client should stop running.
var KeepRunning = true
// When the user scrolls the game window back to the earliest remembered line,
// this gets set to false so they don't just scroll endlessly back through
// space.
var CanScrollBack = false
// Messages from the game server about being logged out arrive before
// the termbox display is torn down but need to be displayed afterward. They
// get stashed here.
var LogoutMessages = make([]string, 0, 0)

// Adds a line of text to the game window. If the number of remembered lines
// exceeds MaxScrollbackLines, the oldest get trimmed down so only
// MinScrollbackLines are remembered.
//
func AddLine(newLine *Line) {
  log.Println("AddLine(", newLine.String(), "):")
  if len(Lines) >= MaxScrollbackLines {
    log.Println("    reallocating buffer")
    new_lines := make([]*Line, 0, MaxScrollbackLines)
    new_lines = append(new_lines, Lines[len(Lines)-MinScrollbackLines:]...)
    Lines = new_lines
  }
  Lines = append(Lines, newLine)
  log.Println("    buffer lines:", len(Lines))
}

// Adds a line of text with the default attributes.
//
func AddDefaultLine(text string) {
  AddLine(NewLine(text, DefaultFg, DefaultBg))
}

// Sets the remembered terminal dimensions to the actual terminal dimensions.
// Called at initialization and every time the terminal window is resized.
//
func Redimension(x, y int) {
  TermW, TermH = x, y
  log.Println("Redimension()ing: (", TermW, TermH, ")")
}

// Recalculates some important values. Called every time Redimension() is.
//
func Recalculate() {
  HeadY  = 0
  SbackY = 1
  FootY  = TermH - 2
  InputY = TermH -1
  InputRL = (2 * TermW) / 3
  log.Println("Recalculate()ing: HeadY, SbackY, FootY, InputY:",
              HeadY, SbackY, FootY, InputY)
}

// Draws the Head Line (above the game window). Called when its text changes.
//
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

// Draw the Foot line (below the game window). Called when its text changes.
//
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

// Draw the current command input line. Called when its contents changes.
//
func DrawInput() {
  var n int = 0
  var scroll int = 0
  
  if IP > InputRL {
    scroll = IP - InputRL
  }
  if scroll < 0 {
    scroll = 0
  }
  
  ip_pos := IP - scroll
  input_end := len(Input) - scroll
  
  for n := 0; n < ip_pos; n++ {
    termbox.SetCell(n, InputY, Input[n+scroll], DefaultFg, DefaultBg)
  }
  if IP == len(Input) {
    termbox.SetCell(ip_pos, InputY, ' ', DefaultFg | termbox.AttrReverse,
                                         DefaultBg | termbox.AttrReverse)
    for n = ip_pos+1; n < TermW; n++ {
      termbox.SetCell(n, InputY, ' ', DefaultFg, DefaultBg)
    }
  } else {
    termbox.SetCell(ip_pos, InputY, Input[IP], DefaultFg | termbox.AttrReverse, 
                                               DefaultBg | termbox.AttrReverse)
    for n = ip_pos+1; n < input_end; n++ {
      termbox.SetCell(n, InputY, Input[n+scroll], DefaultFg, DefaultBg)
    }
    for n = input_end; n < TermW; n++ {
      termbox.SetCell(n, InputY, ' ', DefaultFg, DefaultBg)
    }
  }
  
  if scroll > 0 {
    termbox.SetCell(0, InputY, '<', DefaultFg | termbox.AttrReverse,
                                    DefaultBg | termbox.AttrReverse)
  }
  if len(Input) > scroll + TermW {
    termbox.SetCell(TermW - 1, InputY, '>', DefaultFg | termbox.AttrReverse,
                                            DefaultBg | termbox.AttrReverse)
  }
  
  
}

// Helper function used by DrawScrollback(). After a Line of text has been
// Wrap()ped, it draws the chunkth row of characters from that line on the
// yth row of the terminal window.
//
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

// Scroll the game window history one screen backward (if possible).
//
func ScrollBackward() {
  if CanScrollBack {
    delta := (FootY - SbackY) - ScrollbackOverlap
    ScrollbackPos = ScrollbackPos + delta
    DrawScrollback()
  }
}

// Scroll the game window history one screen forward (if possible).
//
func ScrollForward() {
  if ScrollbackPos > 0 {
    delta := (FootY - SbackY) - ScrollbackOverlap
    ScrollbackPos = ScrollbackPos - delta
    if ScrollbackPos < 0 {
      ScrollbackPos = 0
    }
    DrawScrollback()
  }
}

// Jump the game window history to the most recent messaging.
//
func ScrollToFront() {
  if ScrollbackPos > 0 {
    ScrollbackPos = 0
    DrawScrollback()
  }
}

// Draw the game window.
//
// This is the most complex of all the drawing operations. Overview:
// 
// Starting with the most recent Line:
//   * Wrap() it if it is not already wrapped to the current terminal width.
//   * Write those rows to the terminal, starting from the bottom-most row
//     and working upward.
// Repeat with the next-most recent Line, continuing until either the top of
// the game window has been reached, or the text of all the lines has been
// written.
//
// If the most recent history isn't being viewed (that is, if
// ScrollbackPos > 0), then wrap lines and count rows of text but don't start
// writing to the bottom of the game window until the ScrollbackPosth row of
// text is reached.
//
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
  
  if ScrollbackPos > 0 {
    termbox.SetCell(TermW-1, FootY-1, 'v', DefaultFg | termbox.AttrReverse,
                                           DefaultBg | termbox.AttrReverse)
  }
  if CanScrollBack {
    termbox.SetCell(TermW-1, SbackY, '^', DefaultFg | termbox.AttrReverse,
                                          DefaultBg | termbox.AttrReverse)
  }
  
  log.Println("...DrawScrollback() finished")
}

// Insert a character into the current command and redraw the input line.
//
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

// If possible, delete the character to the left of the insertion point in
// the current command, then redraw the input line.
//
func InputBackspace() {
  if IP > 0 {
    Input = append(Input[:IP-1], Input[IP:]...)
    IP--
    DrawInput()
  }
}

// If possible, delete the character at the insertion point in the current
// command, then redraw the input line.
//
func InputDelete() {
  if IP < len(Input) {
    Input = append(Input[:IP], Input[IP+1:]...)
    DrawInput()
  }
}

// Move the insertion point in the current command right delta characters
// (negative values of delta will move the IP left). Bound movement so that
// the IP doesn't go beyond the beginning or end of the current command.
// Redraw the input line.
//
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

// If possible, populate the command input line with a command from earlier in
// command the history. Stash the latest command first, if necessary. Redraw
// the input line.
//
func CmdHistBack() {
  if cmdHistPtr > 0 {
    if cmdHistPtr == len(cmdHist) {
      cmdStash = Input
    }
    cmdHistPtr--
    Input = []rune(cmdHist[cmdHistPtr])
    IP = len(Input)
    DrawInput()
  }
}

// If possible, populate the command input line with a command from later in
// command the history, retrieving the latest command from the stash, if
// necessary. Redraw the input line.
//
func CmdHistForward() {
  if cmdHistPtr < len(cmdHist) {
    cmdHistPtr++
    if cmdHistPtr == len(cmdHist) {
      Input = cmdStash
    } else {
      Input = []rune(cmdHist[cmdHistPtr])
    }
    IP = len(Input)
    DrawInput()
  }
}

// Send the current command to the game. Add it to the history if it's long
// enough, and clear the input line. Redraw the input line.
//
func SendCommand() {
  log.Println("SendCommand():")
  if len(Input) > 0 {
    e := Env{ Type: "cmd", Text: string(Input) }
    ncdr.Encode(e)
    log.Println("    sent:", e)
    if len(Input) >= MinCmdLen {
      if len(cmdHist) == 0 {
        cmdHist = append(cmdHist, string(Input))
      } else {
        cmd_str := string(Input)
        if cmd_str != cmdHist[len(cmdHist)-1] {
          cmdHist = append(cmdHist, cmd_str)
        }
      }
    }
    
    if len(cmdHist) >= MaxCmdHistSize {
      new_hist := make([]string, 0, MaxCmdHistSize)
      new_hist = append(new_hist, cmdHist[len(cmdHist)-MinCmdHistSize:]...)
      cmdHist = new_hist
    }
    
    cmdHistPtr = len(cmdHist)
    Input = make([]rune, 0, 0)
    IP = 0
    DrawInput()
  }
}

// This is meant to be run as a goroutine, listening for termbox.Events
// and queuing them to be handled.
//
func ListenForEvents() {
  for {
    EventChan <- termbox.PollEvent()
  }
}

// Dispatch handling for queued termbox.Events. These include key (adding
// characters to or editing the current command, scrolling the history window)
// and resize events.
//
func HandleEvent(e termbox.Event) {
  switch e.Type {
  
  case termbox.EventKey:
  
    if e.Ch != 0 {
      InsertInInput(e.Ch)
      if DEBUG {
        FootLine = NewLine(fmt.Sprintf("Ch: %d, Mod: %d", e.Ch, e.Mod),
                           HeadTailFg, HeadTailBg)
      }
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
      case termbox.KeyHome:
        MoveInputIp(-len(Input))
      case termbox.KeyEnd:
        MoveInputIp(len(Input))
      case 13:    // return
        SendCommand()
      case termbox.KeyArrowUp:
        CmdHistBack()
      case termbox.KeyArrowDown:
        CmdHistForward()
      case termbox.KeyPgup:
        ScrollBackward()
      case termbox.KeyPgdn:
        ScrollForward()
      case termbox.KeyF12:
        ScrollToFront()
      }
      if DEBUG {
        FootLine = NewLine(fmt.Sprintf("Key: %d, Mod: %d", e.Key, e.Mod),
                           HeadTailFg, HeadTailBg)
      }
    }
    
    if DEBUG {
      DrawFootline()
    }
    
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

// Panic on error with an appropriate message. Certain errors just shouldn't
// be recoverable.
//
func die(err error, fmtstr string, args ...interface{}) {
  if err != nil {
    fmt.Printf(fmtstr, args...)
    panic(err)
  }
}

// An Env represents an envelope for a message sent to or received from the
// game.
//
type Env struct {
  Type string
  Text string
}

// Holds queued Envs for processing.
var EnvChan = make(chan Env, 256)
// For sending and receiving data from the game.
var ncdr *json.Encoder
var dcdr *json.Decoder

// This is meant to be run as a goroutine. It listens for messages sent from
// the game and queues them for handling.
//
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

// Handle queued messages from the game, adding text to the game window,
// changing the Head line or Foot line, or logging the user out as appropriate.
//
func ProcessEnvelope(e Env) {
  switch e.Type {
  
  case "txt":
    for _, line := range strings.Split(e.Text, "\n") {
      AddDefaultLine(line)
    }
    DrawScrollback()
  case "headline":
    HeadLine = NewLine(e.Text, HeadTailFg, HeadTailBg)
    DrawHeadLine()
  case "echo":
    if SkipAfterSend {
      AddDefaultLine(" ")
    }
    AddLine(NewLine(e.Text, EchoFg, EchoBg))
    ScrollbackPos = 0
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
  case "wall", "sys":
    for _, line := range strings.Split(e.Text, "\n") {
      AddLine(NewLine(line, SysFg, SysBg))
    }
    DrawScrollback()
  case "logout":
    KeepRunning = false
    LogoutMessages = append(LogoutMessages, e.Text)
  default:
    log.Println("Unknown Env type:", e)
  }
  
  termbox.Flush()
}

// Read the configuration file and set the appropriate variable values.
//
func Config() {
  var cfg_file string
  flag.StringVar(&cfg_file, "c", DefaultCfgFile, "configuration file to use")
  flag.Parse()
  
  dconfig.Reset()
  dconfig.AddString(&host,            "host",       dconfig.STRIP)
  dconfig.AddInt(&port,               "port",       dconfig.UNSIGNED)
  dconfig.AddInt(&MinScrollbackLines, "scrollback", dconfig.UNSIGNED)
  dconfig.AddInt(&ScrollbackOverlap,  "scrollback_overlap", dconfig.UNSIGNED)
  dconfig.AddBool(&SkipAfterSend,     "extra_line")
  dconfig.AddBool(&ShowNews,          "show_news")
  dconfig.AddInt(&MinCmdLen,          "min_cmd_len", dconfig.UNSIGNED)
  dconfig.AddInt(&MinCmdHistSize,     "cmd_history", dconfig.UNSIGNED)
  dconfig.AddString(&Uname,           "uname",       dconfig.STRIP)
  dconfig.AddString(&Pwd,             "pwd",         dconfig.STRIP)
  dconfig.Configure([]string{cfg_file}, true)
  
  MaxScrollbackLines = 2 * MinScrollbackLines
  MaxCmdHistSize     = 2 * MinCmdHistSize
}

// Tear down the termbox display and write any logout messages to stdout.
//
func Finalize() {
  termbox.Close()
  for _, m := range LogoutMessages {
    fmt.Printf("\n%s\n", m)
  }
}
// Enter a very primitive termbox interaction mode to get the user's password,
// so as to echo '*'s instead of the password characters.
//
func getPassword() (string, error) {
  err := termbox.Init()
  if err != nil {
    panic(err)
  }
  defer termbox.Close()
  
  pwd_chars := make([]rune, 0, 0)
  prompt := "Password: "
  lp := len(prompt)
  
  for {
    w, h := termbox.Size()
    y := h-1
    for n, r := range prompt {
      termbox.SetCell(n, y, r, DefaultFg, DefaultBg)
    }
    for n, _ := range pwd_chars {
      termbox.SetCell(n+lp, y, '*', DefaultFg, DefaultBg)
    }
    for x := lp + len(pwd_chars); x < w; x++ {
      termbox.SetCell(x, y, ' ', DefaultFg, DefaultBg)
    }
    termbox.Flush()
    
    e := termbox.PollEvent()
    switch e.Type {
    case termbox.EventKey:
      if e.Ch != 0 {
        pwd_chars = append(pwd_chars, e.Ch)
      } else {
        switch e.Key {
        case termbox.KeyBackspace, 127:
          if len(pwd_chars) > 0 {
            pwd_chars = pwd_chars[:len(pwd_chars)-1]
          }
        case 13:
          return string(pwd_chars), nil
        case termbox.KeyEsc:
          return string(pwd_chars), fmt.Errorf("You cancelled password entry.")
        }
      }
    }
  }
}


func main() {
  var err error
  Config()
  
  // Set up logging if DEBUG == true.
  if DEBUG {
    LogFile, err = os.OpenFile(LogFileName, os.O_TRUNC|os.O_WRONLY|os.O_CREATE, 0644)
    if err != nil {
      panic(err)
    }
    defer LogFile.Close()
    log.SetOutput(LogFile)
  } else {
    log.SetFlags(0)
    log.SetOutput(ioutil.Discard)
  }
  
  fmt.Printf("DTA5 Client v.%d\n\n", clientVersion)

  if ShowNews {
    newsf, err := os.Open(NewsFile)
    if err == nil {
      bufio.NewReader(newsf).WriteTo(os.Stdout)
      fmt.Printf("\n")
    }
  }
  
  // Read uname and password if necessary.
  var uname, pwd string
  login_scanner := bufio.NewScanner(os.Stdin)
  if Uname == "" {
    fmt.Printf("login: ")
    login_scanner.Scan()
    uname = login_scanner.Text()
  } else {
    uname = Uname
  }
  if Pwd == "" {
    pwd, err = getPassword()
    if err != nil {
      fmt.Sprintf("Error getting your password: %s\n", err)
      return
    }
  } else {
    pwd = Pwd
  }
  
  // Initiate connection and do protocol.
  conn, err := net.Dial("tcp", fmt.Sprintf("%s:%d", host, port))
  die(err, "Error connecting to %s:%d: %s\n", host, port, err)
  defer conn.Close()
  
  ncdr = json.NewEncoder(conn)
  dcdr = json.NewDecoder(conn)
  
  var m Env
  // The first message rec'd from the game is the required frontend
  // version, but the message isn't used.
  err = dcdr.Decode(&m)
  die(err, "Error decoding welcome message: %s\n", err)
  if m.Type != "version" {
    die(fmt.Errorf("bad message"), "Welcome message incorrect type: %q\n", m)
  }
  fmt.Printf("Req'd frontend version: %s\n", m.Text)
  
  // The game then expects the client version, the username, and the password.
  // (The game will log us out if the client isn't sufficently up-to-date.)
  err = ncdr.Encode(Env{ Type: "version", Text: fmt.Sprintf("%d", clientVersion) })
  die(err, "Error sending version: %s\n", err)
  err = ncdr.Encode(Env{ Type: "uname", Text: uname })
  die(err, "Error sending login: %s\n", err)
  err = ncdr.Encode(Env{ Type: "pwd", Text: pwd })
  die(err, "Error sending password: %s\b", err)
  
  // Set up the termbox interface and draw initial versions of everything.
  err = termbox.Init()
  if err != nil {
    panic(err)
  }
  defer Finalize()  // includes call to termbox.Close()
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
  
  // Launch our goroutines which listen for messages from the game and
  // input from the user.
  go ListenForEnvelopes(dcdr)
  go ListenForEvents()
  
  // Process queued events until we get logged out!
  for KeepRunning {
    select {
    case e := <- EventChan:
      HandleEvent(e)
    case e := <- EnvChan:
      ProcessEnvelope(e)
    }
  }
}
