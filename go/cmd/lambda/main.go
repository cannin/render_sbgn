package main

import (
	"context"
	"embed"
	"encoding/base64"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"strings"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
)

const (
	cliPath    = "/var/task/render_sbgn_go"
	inputPath  = "/tmp/input.sbgn"
	outputBase = "/tmp/output"
	fontDir    = "/tmp/fonts"
)

// embeddedFonts stores the font files needed by the subprocess renderer.
//
//go:embed fonts/LiberationSans-Regular.ttf fonts/LiberationMono-Regular.ttf
var embeddedFonts embed.FS

// Event is the JSON request accepted by the Lambda wrapper.
type Event struct {
	XML string `json:"xml"`
}

// Response is the JSON response returned by the Lambda wrapper.
type Response struct {
	PNGBase64 string `json:"png_base64"`
}

// main starts the AWS Lambda runtime with the subprocess-backed handler.
// Parameters: none.
func main() {
	lambda.Start(handler)
}

// handler accepts Lambda Function URL requests and returns a JSON HTTP response.
// Parameters: ctx is the Lambda invocation context; request is the Function URL HTTP event.
func handler(ctx context.Context, request events.LambdaFunctionURLRequest) (events.LambdaFunctionURLResponse, error) {
	method := request.RequestContext.HTTP.Method
	if method != "" && method != http.MethodPost {
		return jsonHTTPError(http.StatusMethodNotAllowed, fmt.Errorf("method %s is not allowed", method))
	}

	event, err := parseFunctionURLRequest(request)
	if err != nil {
		return jsonHTTPError(http.StatusBadRequest, err)
	}

	response, err := renderEvent(ctx, event)
	if err != nil {
		return jsonHTTPError(http.StatusInternalServerError, err)
	}

	return jsonHTTPResponse(http.StatusOK, response)
}

// parseFunctionURLRequest decodes the HTTP body into the renderer event payload.
// Parameters: request is the Lambda Function URL event whose body contains JSON.
func parseFunctionURLRequest(request events.LambdaFunctionURLRequest) (Event, error) {
	body := request.Body
	if request.IsBase64Encoded {
		decoded, err := base64.StdEncoding.DecodeString(body)
		if err != nil {
			return Event{}, fmt.Errorf("failed to decode base64 request body: %w", err)
		}
		body = string(decoded)
	}

	if strings.TrimSpace(body) == "" {
		return Event{}, fmt.Errorf("request body is empty")
	}

	var event Event
	if err := json.Unmarshal([]byte(body), &event); err != nil {
		return Event{}, fmt.Errorf("request body must be JSON with an xml field: %w", err)
	}
	if strings.TrimSpace(event.XML) == "" {
		return Event{}, fmt.Errorf("xml is required")
	}

	return event, nil
}

// renderEvent writes SBGNML input, invokes the existing CLI binary, and returns PNG bytes as base64.
// Parameters: ctx is the Lambda invocation context; e contains the SBGNML XML string.
func renderEvent(ctx context.Context, e Event) (Response, error) {
	if err := installEmbeddedFonts(); err != nil {
		return Response{}, err
	}

	if err := os.WriteFile(inputPath, []byte(e.XML), 0o644); err != nil {
		return Response{}, err
	}
	_ = os.Remove(outputBase + ".png")

	cmd := exec.Command(
		cliPath,
		"draw_sbgnml",
		"-i", inputPath,
		"-o", outputBase,
	)
	cmd.Env = append(os.Environ(),
		"HOME=/tmp",
		"XDG_DATA_HOME=/tmp",
	)

	output, err := cmd.CombinedOutput()
	if err != nil {
		return Response{}, fmt.Errorf("exec failed: %v\n%s", err, string(output))
	}

	data, err := os.ReadFile(outputBase + ".png")
	if err != nil {
		return Response{}, err
	}

	return Response{
		PNGBase64: base64.StdEncoding.EncodeToString(data),
	}, nil
}

// jsonHTTPResponse serializes a payload for Lambda Function URL output.
// Parameters: statusCode is the HTTP response code; payload is JSON-serializable response data.
func jsonHTTPResponse(statusCode int, payload any) (events.LambdaFunctionURLResponse, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return events.LambdaFunctionURLResponse{}, err
	}

	return events.LambdaFunctionURLResponse{
		StatusCode: statusCode,
		Headers: map[string]string{
			"content-type": "application/json",
		},
		Body: string(body),
	}, nil
}

// jsonHTTPError serializes an error message without failing the Lambda invocation.
// Parameters: statusCode is the HTTP response code; err is the error to expose in JSON.
func jsonHTTPError(statusCode int, err error) (events.LambdaFunctionURLResponse, error) {
	return jsonHTTPResponse(statusCode, map[string]string{
		"error": err.Error(),
	})
}

// installEmbeddedFonts writes bundled fonts where the unchanged CLI subprocess can discover them.
// Parameters: none.
func installEmbeddedFonts() error {
	if err := os.MkdirAll(fontDir, 0o755); err != nil {
		return err
	}
	for _, name := range []string{
		"LiberationSans-Regular.ttf",
		"LiberationMono-Regular.ttf",
	} {
		if err := writeEmbeddedFont(name); err != nil {
			return err
		}
	}
	return nil
}

// writeEmbeddedFont extracts one embedded font file into /tmp/fonts.
// Parameters: name is the base filename under the embedded fonts directory.
func writeEmbeddedFont(name string) error {
	data, err := embeddedFonts.ReadFile("fonts/" + name)
	if err != nil {
		return err
	}
	return os.WriteFile(filepath.Join(fontDir, name), data, 0o644)
}
