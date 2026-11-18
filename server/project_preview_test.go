package server

import "testing"

func TestParseDiffStats(t *testing.T) {
	diff := "@@ -52,7 +52,16 @@ func cancel() {\n context\n-old\n+new\n+added\n--- a/x\n+++ b/x\n"
	adds, dels, hunks := parseDiffStats(diff)
	if adds != 2 || dels != 1 {
		t.Fatalf("adds=%d dels=%d", adds, dels)
	}
	if len(hunks) != 1 || hunks[0].OldStart != 52 || hunks[0].OldLines != 7 || hunks[0].NewStart != 52 || hunks[0].NewLines != 16 {
		t.Fatalf("hunks=%+v", hunks)
	}
}

func TestParseSpringEndpoints(t *testing.T) {
	src := []byte(`package demo;
@RestController
@RequestMapping("/api/appointment")
class AppointmentController {
    @PostMapping("/cancel")
    public void cancel() {}
    @RequestMapping(value = "/{id}", method = RequestMethod.GET)
    public void get() {}
}
`)
	eps := parseSpringEndpoints(src, "AppointmentController.java")
	if len(eps) != 2 {
		t.Fatalf("endpoints=%+v", eps)
	}
	if eps[0].Method != "POST" || eps[0].Path != "/api/appointment/cancel" || eps[0].Line != 5 {
		t.Fatalf("endpoint[0]=%+v", eps[0])
	}
	if eps[1].Method != "GET" || eps[1].Path != "/api/appointment/{id}" {
		t.Fatalf("endpoint[1]=%+v", eps[1])
	}
	if eps[0].Confidence != "direct" {
		t.Fatalf("confidence=%q", eps[0].Confidence)
	}
}
