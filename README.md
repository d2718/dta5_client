# `dta5_client`

This is like [`dta4_client`](https://github.com/d2718/dta4_client), but for [`dta5`](https://github.com/d2718/dta5). The code is basically the same, except `dta5` uses JSON instead of a `_PREFIX:data` communication protocol.

`dta5.go` requires two external libraries you can `go get`:

  * [`github.com/nsf/termbox-go`](https://github.com/nsf/termbox-go)
  * [`github.com/d2718/dconfig`](https://github.com/d2718/dconfig)

You should be able to just `go build dta5.go`. I have tested this on Ubuntu 16, Ubuntu 14, Windows 10, and Raspbian Jesse; I am willing to bet it works on OS X, too. (I have built `termbox-go` programs on OS X before.) I will also be making binary distributions available somewhere. (The 64-bit Linux version is 4.6MB, a ginormous improvement over the wxPython/PyInstaller binary solution.)

Some current features:

  * You can play the game.
  * Line-wrapping and resizing both work more-or-less seamlessly. (I encountered some resizing weirdness using the PowerShell window, but the game was still playable.)
  * scrollable game window history (the number of lines you want to keep is customizable)
  * Backspace, Delete, Left/Right Arrows, and Home/End keys allow for editing of the current command.
  * Command history accessed through Up/Down Arrow keys.
  * Color.
  * A header bar at the top of the window displays the name of your current location.
  * The `-c` option now allows the specification of an alternate configuration file.
  * The terminal window no longer echoes your password in plain text as you type it.

Some missing features that may exist in the future:

  * ~~command history (This is the biggest priority.)~~ There is command history!
  * ~~The command input window does not scroll horizontally, so you won't be able to see the ends of large commands as you type them. (This is also a big priority.)~~ The behavior isn't exactly how I'd like it to be, but it'll do for now.
  * ~~Home and End should do the right thing in the input window.~~ These work now.
  * ~~logout messaging doesn't display~~ It does now.
  * The footer bar should display some information. (This will evolve as `dta5` evolves and there is some information about your character to display.)
  * logging of game text
  * user-customizable color (Determining a mechanism for this is going to be a significant design decision; it's possible this will only be available for `xterm-256color` terminals.)
  * Eventually I would like to implement some custom highlighing for user-specifiable phrases, but that's an even bigger design decision than just "custom colors".

### UPDATE 2017-08-25:

I deleted the old Python frontend files an renamed the terminal frontend to just plain `dta5.go`.

### UPDATE 2017-08-22:

A functional cross-platform terminal client has been released!

I got tired of wrestling with the issues of compatibility between the different versions of [wxPython](https://wxpython.org) (and the different versions of Python!), and also the weird quirks in the [wxWidgets](https://www.wxwidgets.org) behavior (at least under their Python bindings). I was also not fond of the 50MB-ish binaries generated by PyInstaller. (I _understand_ the necessity of their size, but it's still ridiculous for a program that more or less just processes and transmits text.) I just couldn't make a nice, reasonable, out-of-the-box solution work.

I spent several days looking at higher-level terminal libraries, but none of them really produced the behavior I sought, so I turned to [termbox-go](https://github.com/nsf/termbox-go), bit the bullet, and did text-wrapping the hard way. The result has worked out surprisngly well so far.
