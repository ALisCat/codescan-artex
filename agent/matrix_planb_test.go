package agent

import "testing"

func TestMatrixBlockReason(t *testing.T) {
	t.Run("pending seeds and blocks", func(t *testing.T) {
		ts := &ToolSet{}
		seeded := 0
		ts.matrixPending = func() (int, int, error) { return 2, 0, nil }
		ts.matrixSeed = func() (int, error) { seeded = 2; return 2, nil }
		blocked, reason := ts.matrixBlockReason()
		if !blocked || seeded != 2 || reason == "" {
			t.Fatalf("expected blocked+seed, got blocked=%v seeded=%d reason=%q", blocked, seeded, reason)
		}
	})
	t.Run("dispatched blocks", func(t *testing.T) {
		ts := &ToolSet{}
		ts.matrixPending = func() (int, int, error) { return 0, 3, nil }
		blocked, reason := ts.matrixBlockReason()
		if !blocked || reason == "" {
			t.Fatalf("expected dispatched to block, got blocked=%v reason=%q", blocked, reason)
		}
	})
	t.Run("complete", func(t *testing.T) {
		ts := &ToolSet{}
		ts.matrixPending = func() (int, int, error) { return 0, 0, nil }
		blocked, reason := ts.matrixBlockReason()
		if blocked || reason != "" {
			t.Fatalf("expected complete, got blocked=%v reason=%q", blocked, reason)
		}
	})
}
