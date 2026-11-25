package main

import (
	"crypto/sha256"
	"encoding/json"
	"strings"
	"testing"
)

func TestAnswerObserverBoundedAndActualFragments(t *testing.T) {
	answer := "An ordinary answer with citations [1]."
	o := &answerObserver{}
	for _, part := range []string{answer[:10], answer[10:]} {
		data, _ := json.Marshal(map[string]string{"kind": "assistant_delta", "delta": part})
		_, _ = o.decode(data)
	}
	data, _ := json.Marshal(map[string]string{"kind": "final", "content": answer})
	_, _ = o.decode(data)
	if o.fragments != 2 || o.verify() != nil {
		t.Fatal("invalid streaming observation")
	}
	_, _ = o.decode(data)
	if o.verify() == nil {
		t.Fatal("multiple finals accepted")
	}
	o = &answerObserver{}
	data, _ = json.Marshal(map[string]string{"kind": "assistant_delta", "delta": strings.Repeat("x", maxAnswerBytes+1)})
	_, _ = o.decode(data)
	if o.deltas.Len() != 0 || o.err == nil {
		t.Fatal("answer bound missing")
	}
}

func TestGenericAnswerValidation(t *testing.T) {
	for _, tc := range []struct {
		final, delta string
		count        int
		want         bool
	}{
		{"Arbitrary natural answer", "", 1, true},
		{"Réponse [1]", "Réponse [1]", 1, true},
		{"", "Partial answer", 0, false},
		{"", "", 1, false},
		{"Changed", "Original", 1, false},
	} {
		o := &answerObserver{final: tc.final, finals: tc.count}
		o.deltas.WriteString(tc.delta)
		if (o.verify() == nil) != tc.want {
			t.Fatalf("unexpected validation: %+v", tc)
		}
	}
}

func TestHistoryChecksObservedContentAndPairing(t *testing.T) {
	turns := []completedTurn{{sha256.Sum256([]byte("Question")), sha256.Sum256([]byte("Answer"))}}
	message := func(role, text, exchange, session string, rank int) json.RawMessage {
		data, _ := json.Marshal(map[string]any{"session_id": session, "exchange_id": exchange, "rank": rank, "role": role, "channel": "final", "parts": []map[string]string{{"type": "text", "text": text}}})
		return data
	}
	good := []json.RawMessage{message("user", "Question", "e1", "s", 1), message("assistant", "Answer", "e1", "s", 2)}
	if err := verifyHistory(good, "s", turns); err != nil {
		t.Fatal(err)
	}
	for _, bad := range [][]json.RawMessage{
		good[:1],
		{good[0], message("assistant", "Foreign answer", "e1", "s", 2)},
		{message("user", "Changed question", "e1", "s", 1), good[1]},
		{good[0], message("assistant", "Answer", "e2", "s", 2)},
		{good[0], message("assistant", "Answer", "e1", "other", 2)},
		{good[0], message("assistant", "Answer", "e1", "s", 1)},
		{good[0], good[1], good[1]},
	} {
		if verifyHistory(bad, "s", turns) == nil {
			t.Fatal("invalid history accepted")
		}
	}
}
