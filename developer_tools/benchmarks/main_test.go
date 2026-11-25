package main

import (
	"flag"
	"net/http"
	"net/http/httptest"
	"os"
	"os/exec"
	"strings"
	"sync/atomic"
	"testing"
)

func TestCLIHelper(t *testing.T) {
	if os.Getenv("BENCH_TEST_CLI") != "1" {
		return
	}
	args := strings.Split(os.Getenv("BENCH_TEST_ARGS"), "\n")
	os.Args = append([]string{"bench"}, args...)
	flag.CommandLine = flag.NewFlagSet("bench", flag.ExitOnError)
	main()
}

func TestWeaverRejectedBeforeNetwork(t *testing.T) {
	var calls atomic.Int32
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { calls.Add(1) }))
	defer server.Close()
	cmd := exec.Command(os.Args[0], "-test.run=^TestCLIHelper$")
	cmd.Env = append(os.Environ(), "BENCH_TEST_CLI=1", "BENCH_TEST_ARGS=-target=weaver\n-url="+server.URL+"\n-ensure-v2-definition-ref=any\n-agent-create-url="+server.URL)
	output, err := cmd.CombinedOutput()
	var exitCode int
	if exit, ok := err.(*exec.ExitError); ok {
		exitCode = exit.ExitCode()
	}
	if exitCode != 2 || !strings.Contains(string(output), "weaver requires") || calls.Load() != 0 {
		t.Fatalf("exit=%d calls=%d output=%s", exitCode, calls.Load(), output)
	}
}
