package main

import (
	"encoding/json"
	"strings"
	"testing"
)

func ackText(marker turnMarker, previous []turnMarker, profile string) string {
	data, _ := json.Marshal(mockACK{marker, previous})
	text := ackPrefix + string(data) + "\n"
	if profile == "streaming" {
		for i := 2; i <= 100; i++ {
			text += "MOCK_BENCH_FRAGMENT_V1 " + itoa(i) + "/100\n"
		}
	}
	return text
}
func itoa(i int) string {
	const digits = "0123456789"
	if i < 10 {
		return string(digits[i])
	}
	return itoa(i/10) + string(digits[i%10])
}
func TestMockACKDetectsMissingDuplicateMixedAndWrongOrder(t *testing.T) {
	a, b := turnMarker{"c", 1, "n1"}, turnMarker{"c", 2, "n2"}
	current := turnMarker{"c", 3, "n3"}
	want := []turnMarker{a, b}
	if err := validateACK(ackText(current, want, "reference"), current, want, "reference"); err != nil {
		t.Fatal(err)
	}
	for _, prior := range [][]turnMarker{nil, {}, {a, a}, {b, a}, {a, {"foreign", 2, "n2"}}} {
		if err := validateACK(ackText(current, prior, "reference"), current, want, "reference"); err == nil {
			t.Fatal("bad history accepted", prior)
		}
	}
	text := ackText(a, []turnMarker{}, "streaming")
	if err := validateACK(text, a, []turnMarker{}, "streaming"); err != nil {
		t.Fatal(err)
	}
	if err := validateACK(strings.Replace(text, "2/100", "3/100", 1), a, []turnMarker{}, "streaming"); err == nil {
		t.Fatal("fragment gap accepted")
	}
	if err := validateACK(text+text, a, []turnMarker{}, "streaming"); err == nil {
		t.Fatal("duplicate ACK accepted")
	}
}

func TestAnswerObserverBoundedAndActualFragments(t *testing.T) {
	marker := turnMarker{"c", 1, "n"}
	answer := ackText(marker, []turnMarker{}, "reference")
	o := &answerObserver{}
	for _, part := range []string{answer[:10], answer[10:]} {
		data, _ := json.Marshal(map[string]string{"kind": "assistant_delta", "delta": part})
		_, _ = o.decode(data)
	}
	data, _ := json.Marshal(map[string]string{"kind": "final", "content": answer})
	_, _ = o.decode(data)
	if o.fragments != 2 || o.verify(marker, []turnMarker{}, "reference") != nil {
		t.Fatal("invalid streaming observation")
	}
	_, _ = o.decode(data)
	if o.verify(marker, []turnMarker{}, "reference") == nil {
		t.Fatal("multiple finals accepted")
	}
	o = &answerObserver{}
	data, _ = json.Marshal(map[string]string{"kind": "assistant_delta", "delta": strings.Repeat("x", maxAnswerBytes+1)})
	_, _ = o.decode(data)
	if o.deltas.Len() != 0 || o.err == nil {
		t.Fatal("answer bound missing")
	}
}
