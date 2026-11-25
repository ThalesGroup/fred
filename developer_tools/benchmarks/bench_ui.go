package main

import (
	"context"
	"fmt"
	"io"
	"os"
	"os/exec"
	"runtime"
	"strconv"
	"strings"
	"unicode"
	"unicode/utf8"

	"golang.org/x/term"
)

// One input reader serves menus and prompts. Closing the process releases stdin;
// cancellation never waits for another keystroke before restoring the terminal.
type benchUI struct {
	ctx              context.Context
	input            chan byte
	out              io.Writer
	fd               int
	ansi, color, raw bool
}

func newBenchUI(ctx context.Context) *benchUI {
	u := &benchUI{ctx: ctx, input: make(chan byte), out: os.Stdout, fd: int(os.Stdin.Fd())}
	u.ansi = term.IsTerminal(int(os.Stdout.Fd())) && os.Getenv("TERM") != "dumb"
	_, noColor := os.LookupEnv("NO_COLOR")
	u.color = u.ansi && !noColor
	go func() {
		defer close(u.input)
		var b [1]byte
		for {
			if _, err := os.Stdin.Read(b[:]); err != nil {
				return
			}
			select {
			case u.input <- b[0]:
			case <-ctx.Done():
				return
			}
		}
	}()
	return u
}

func terminalText(s string) string {
	return strings.Map(func(r rune) rune {
		if unicode.IsControl(r) || unicode.Is(unicode.Cf, r) {
			return ' '
		}
		return r
	}, s)
}
func (u *benchUI) style(code, s string) string {
	if u.color {
		return "\x1b[" + code + "m" + s + "\x1b[0m"
	}
	return s
}
func (u *benchUI) printf(format string, args ...any) {
	s := fmt.Sprintf(format, args...)
	if u.raw {
		s = strings.ReplaceAll(s, "\n", "\r\n")
	}
	fmt.Fprint(u.out, s)
}
func (u *benchUI) key() (byte, error) {
	select {
	case <-u.ctx.Done():
		return 0, u.ctx.Err()
	case b, ok := <-u.input:
		if !ok {
			return 0, io.EOF
		}
		if b == 3 || b == 4 {
			return 0, context.Canceled
		}
		return b, nil
	}
}
func (u *benchUI) rawMode() (func(), error) {
	if !u.ansi {
		return func() {}, nil
	}
	state, err := term.MakeRaw(u.fd)
	if err != nil {
		return nil, err
	}
	u.raw = true
	return func() { _ = term.Restore(u.fd, state); u.raw = false }, nil
}
func (u *benchUI) ask(label, fallback string) (string, error) {
	restore, err := u.rawMode()
	if err != nil {
		return "", err
	}
	defer restore()
	u.printf("\n%s", label)
	if fallback != "" {
		u.printf(" [%s]", terminalText(fallback))
	}
	u.printf(": ")
	var answer []byte
	for {
		b, err := u.key()
		if err != nil {
			return "", err
		}
		switch b {
		case '\r', '\n':
			u.printf("\n")
			s := strings.TrimSpace(string(answer))
			if s == "" {
				s = fallback
			}
			return s, nil
		case 127, 8:
			if len(answer) > 0 {
				_, n := utf8.DecodeLastRune(answer)
				answer = answer[:len(answer)-n]
				if u.raw {
					u.printf("\b \b")
				}
			}
		default:
			if b >= 32 && b != 127 && len(answer) < 2048 {
				answer = append(answer, b)
				if u.raw {
					u.printf("%s", string([]byte{b}))
				}
			}
		}
	}
}

func (u *benchUI) choose(title string, options []string, selected int) (int, error) {
	if len(options) == 0 {
		return 0, fmt.Errorf("no choices available")
	}
	if selected < 0 || selected >= len(options) {
		selected = 0
	}
	u.printf("\n%s\n", u.style("1", title))
	if !u.ansi {
		for i, s := range options {
			u.printf("  %d. %s\n", i+1, terminalText(s))
		}
		for {
			s, err := u.ask("Choice", strconv.Itoa(selected+1))
			if err != nil {
				return 0, err
			}
			n, err := strconv.Atoi(s)
			if err == nil && n > 0 && n <= len(options) {
				return n - 1, nil
			}
			u.printf("Enter a number from the list.\n")
		}
	}
	restore, err := u.rawMode()
	if err != nil {
		return 0, err
	}
	defer restore()
	u.printf("\x1b[?25l")
	defer u.printf("\x1b[?25h")
	rows := min(8, len(options))
	width, _, err := term.GetSize(int(os.Stdout.Fd()))
	if err != nil || width < 20 {
		width = 80
	}
	draw := func() {
		start := min(max(0, selected-rows/2), len(options)-rows)
		for i := start; i < start+rows; i++ {
			prefix := "  "
			if i == selected {
				prefix = "> "
			}
			label := []rune(terminalText(options[i]))
			if len(label) > (width-6)/2 {
				label = append(label[:(width-6)/2], '…')
			}
			line := prefix + string(label)
			if i == selected {
				line = u.style("36;1", line)
			}
			u.printf("\x1b[2K\r%s\n", line)
		}
		u.printf("\x1b[2K\r↑/↓ select · Enter confirm · Ctrl+C exit  (%d/%d)\n", selected+1, len(options))
	}
	draw()
	for {
		b, err := u.key()
		if err != nil {
			return 0, err
		}
		if b == '\r' || b == '\n' {
			return selected, nil
		}
		switch b {
		case 'k':
			selected = (selected + len(options) - 1) % len(options)
		case 'j':
			selected = (selected + 1) % len(options)
		case 27:
			next, err := u.key()
			if err != nil {
				return 0, err
			}
			if next == '[' || next == 'O' {
				direction, err := u.key()
				if err != nil {
					return 0, err
				}
				if direction == 'A' {
					selected = (selected + len(options) - 1) % len(options)
				}
				if direction == 'B' {
					selected = (selected + 1) % len(options)
				}
			}
		}
		u.printf("\x1b[%dA", rows+1)
		draw()
	}
}

func openBenchURL(target string) error {
	name, args := "xdg-open", []string{target}
	switch runtime.GOOS {
	case "darwin":
		name = "open"
	case "windows":
		name, args = "rundll32", []string{"url.dll,FileProtocolHandler", target}
	}
	cmd := exec.Command(name, args...)
	if err := cmd.Start(); err != nil {
		return err
	}
	go func() { _ = cmd.Wait() }()
	return nil
}
