package main

import (
	"strings"
	"testing"
)

func TestBundledFontAndFallbackOrder(t *testing.T) {
	if len(liberationSansRegular) == 0 {
		t.Fatal("bundled Liberation Sans font is empty")
	}
	want := []string{"Liberation Sans", "Arial", "DejaVu Sans", "Helvetica", "sans-serif"}
	if strings.Join(fontFamilyFallbacks, "|") != strings.Join(want, "|") {
		t.Fatalf("font fallback order = %v, want %v", fontFamilyFallbacks, want)
	}
}
