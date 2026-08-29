APPNAME := render_sbgn_go
DIST := dist

.PHONY: all test release current clean

all: test release current

test:
	@test -z "$$(gofmt -l .)" || { gofmt -l .; exit 1; }
	go test ./...

release: clean
	mkdir -p $(DIST)
	CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o $(DIST)/$(APPNAME)-linux-amd64 .
	CGO_ENABLED=0 GOOS=darwin GOARCH=arm64 go build -trimpath -ldflags "-s -w" -o $(DIST)/$(APPNAME)-darwin-arm64 .
	CGO_ENABLED=0 GOOS=windows GOARCH=amd64 go build -trimpath -ldflags "-s -w" -o $(DIST)/$(APPNAME)-windows-amd64.exe .

current:
	mkdir -p $(DIST)
	go build -trimpath -o $(DIST)/$(APPNAME) .

clean:
	rm -rf -- $(DIST)
