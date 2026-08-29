package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"embed"
	"encoding/base64"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"net/http"
	"os"
	"os/exec"
	"path/filepath"
	"reflect"
	"strings"
	"time"

	"github.com/aws/aws-lambda-go/events"
	"github.com/aws/aws-lambda-go/lambda"
	"github.com/aws/aws-sdk-go-v2/aws"
	"github.com/aws/aws-sdk-go-v2/config"
	"github.com/aws/aws-sdk-go-v2/service/s3"
)

const (
	cliPath    = "/var/task/render_sbgn_go"
	inputPath  = "/tmp/input.sbgn"
	outputBase = "/tmp/output"
	outputPNG  = "/tmp/output.png"
	fontDir    = "/tmp/fonts"
	s3Bucket   = "lunean.mcp"
)

// embeddedFonts stores the font files needed by the subprocess renderer.
//
//go:embed fonts/LiberationSans-Regular.ttf fonts/LiberationMono-Regular.ttf
var embeddedFonts embed.FS

// JSONRPCRequest is the minimal JSON-RPC request shape used by MCP.
type JSONRPCRequest struct {
	JSONRPC string          `json:"jsonrpc"`
	ID      any             `json:"id,omitempty"`
	Method  string          `json:"method"`
	Params  json.RawMessage `json:"params,omitempty"`
}

// JSONRPCResponse is the minimal JSON-RPC response shape returned by MCP.
type JSONRPCResponse struct {
	JSONRPC string `json:"jsonrpc"`
	ID      any    `json:"id,omitempty"`
	Result  any    `json:"result,omitempty"`
	Error   any    `json:"error,omitempty"`
}

// Tool describes one callable MCP tool and its generated input schema.
type Tool struct {
	Name        string
	Description string
	Func        any
	InputSchema map[string]any
}

// RenderSBGNPNGInput is the MCP input for rendering an SBGNML document.
type RenderSBGNPNGInput struct {
	XML string `json:"xml"`
}

// RenderSBGNPNGOutput is the file location returned by the MCP render tool.
type RenderSBGNPNGOutput struct {
	URL    string `json:"url"`
	S3URI  string `json:"s3_uri"`
	Bucket string `json:"bucket"`
	Key    string `json:"key"`
}

var tools = map[string]Tool{}

// RegisterTool adds one function-backed MCP tool to the process registry.
// Parameters: name is the MCP tool name; description explains the tool; fn is a function with one struct argument.
func RegisterTool(name string, description string, fn any) {
	tools[name] = Tool{
		Name:        name,
		Description: description,
		Func:        fn,
		InputSchema: schemaFromFunc(fn),
	}
}

// schemaFromFunc generates a basic JSON Schema for a one-struct-argument tool function.
// Parameters: fn is the tool function whose first argument defines the input object.
func schemaFromFunc(fn any) map[string]any {
	t := reflect.TypeOf(fn)
	if t.Kind() != reflect.Func {
		panic("tool must be a function")
	}

	properties := map[string]any{}
	required := []string{}

	if t.NumIn() == 1 && t.In(0).Kind() == reflect.Struct {
		arg := t.In(0)
		for i := 0; i < arg.NumField(); i++ {
			field := arg.Field(i)
			jsonName := jsonFieldName(field)
			if jsonName == "-" {
				continue
			}

			properties[jsonName] = map[string]any{
				"type": goTypeToJSONSchema(field.Type),
			}
			required = append(required, jsonName)
		}
	}

	return map[string]any{
		"type":       "object",
		"properties": properties,
		"required":   required,
	}
}

// jsonFieldName resolves the JSON object key for a struct field.
// Parameters: field is the reflected struct field being described.
func jsonFieldName(field reflect.StructField) string {
	jsonName := field.Tag.Get("json")
	if jsonName == "" {
		return field.Name
	}
	return strings.Split(jsonName, ",")[0]
}

// goTypeToJSONSchema maps simple Go kinds to JSON Schema primitive types.
// Parameters: t is the reflected Go type to describe.
func goTypeToJSONSchema(t reflect.Type) string {
	switch t.Kind() {
	case reflect.String:
		return "string"
	case reflect.Int, reflect.Int64, reflect.Int32:
		return "integer"
	case reflect.Float64, reflect.Float32:
		return "number"
	case reflect.Bool:
		return "boolean"
	case reflect.Map, reflect.Struct:
		return "object"
	case reflect.Slice, reflect.Array:
		return "array"
	default:
		return "string"
	}
}

// RenderSBGNPNG renders SBGNML XML, uploads the PNG to S3, and returns its file location.
// Parameters: input contains the SBGNML XML string to render.
func RenderSBGNPNG(input RenderSBGNPNGInput) (RenderSBGNPNGOutput, error) {
	if strings.TrimSpace(input.XML) == "" {
		return RenderSBGNPNGOutput{}, fmt.Errorf("xml is required")
	}
	if err := installEmbeddedFonts(); err != nil {
		return RenderSBGNPNGOutput{}, err
	}
	if err := os.WriteFile(inputPath, []byte(input.XML), 0o644); err != nil {
		return RenderSBGNPNGOutput{}, err
	}
	_ = os.Remove(outputPNG)

	cmd := exec.Command(
		cliPath,
		"draw_sbgnml",
		"-i", inputPath,
		"-o", outputBase,
		"--format", "png",
	)
	cmd.Env = append(os.Environ(),
		"HOME=/tmp",
		"XDG_DATA_HOME=/tmp",
	)

	output, err := cmd.CombinedOutput()
	if err != nil {
		return RenderSBGNPNGOutput{}, fmt.Errorf("exec failed: %v\n%s", err, string(output))
	}

	data, err := os.ReadFile(outputPNG)
	if err != nil {
		return RenderSBGNPNGOutput{}, err
	}
	return uploadPNGToS3(context.Background(), data)
}

// uploadPNGToS3 stores one rendered PNG in the configured S3 bucket and returns its location.
// Parameters: ctx controls the S3 request lifetime; data contains the PNG bytes to upload.
func uploadPNGToS3(ctx context.Context, data []byte) (RenderSBGNPNGOutput, error) {
	region := awsRegion()
	cfg, err := config.LoadDefaultConfig(ctx, config.WithRegion(region))
	if err != nil {
		return RenderSBGNPNGOutput{}, err
	}

	key := s3ObjectKey(data)
	client := s3.NewFromConfig(cfg)
	_, err = client.PutObject(ctx, &s3.PutObjectInput{
		Bucket:      aws.String(s3Bucket),
		Key:         aws.String(key),
		Body:        bytes.NewReader(data),
		ContentType: aws.String("image/png"),
	})
	if err != nil {
		return RenderSBGNPNGOutput{}, err
	}

	return RenderSBGNPNGOutput{
		URL:    fmt.Sprintf("https://s3.%s.amazonaws.com/%s/%s", region, s3Bucket, key),
		S3URI:  fmt.Sprintf("s3://%s/%s", s3Bucket, key),
		Bucket: s3Bucket,
		Key:    key,
	}, nil
}

// awsRegion returns the AWS region for S3 uploads, defaulting to us-east-1.
// Parameters: none.
func awsRegion() string {
	if region := strings.TrimSpace(os.Getenv("AWS_REGION")); region != "" {
		return region
	}
	if region := strings.TrimSpace(os.Getenv("AWS_DEFAULT_REGION")); region != "" {
		return region
	}
	return "us-east-1"
}

// s3ObjectKey builds the required TIMESTAMP_HASH.png filename for one PNG.
// Parameters: data contains the rendered PNG bytes to hash.
func s3ObjectKey(data []byte) string {
	sum := sha256.Sum256(data)
	hash := hex.EncodeToString(sum[:])
	timestamp := time.Now().UTC().Format("20060102T150405Z")
	return fmt.Sprintf("%s_%s.png", timestamp, hash)
}

// handleMCP routes one JSON-RPC request to the supported MCP methods.
// Parameters: req is the parsed JSON-RPC request from the HTTP body.
func handleMCP(req JSONRPCRequest) JSONRPCResponse {
	switch req.Method {
	case "initialize":
		return JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: map[string]any{
				"protocolVersion": "2024-11-05",
				"serverInfo": map[string]any{
					"name":    "render-sbgn-go-lambda-mcp",
					"version": "1.0.0",
				},
				"capabilities": map[string]any{
					"tools": map[string]any{
						"list": true,
						"call": true,
					},
				},
			},
		}
	case "notifications/initialized":
		return JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  map[string]any{},
		}
	case "tools/list":
		list := []map[string]any{}
		for _, tool := range tools {
			list = append(list, map[string]any{
				"name":        tool.Name,
				"description": tool.Description,
				"inputSchema": tool.InputSchema,
			})
		}
		return JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: map[string]any{
				"tools": list,
			},
		}
	case "tools/call":
		var params struct {
			Name      string          `json:"name"`
			Arguments json.RawMessage `json:"arguments"`
		}
		if err := json.Unmarshal(req.Params, &params); err != nil {
			return rpcError(req.ID, -32602, "invalid params")
		}

		tool, ok := tools[params.Name]
		if !ok {
			return rpcError(req.ID, -32601, "tool not found")
		}

		result, err := callTool(tool, params.Arguments)
		if err != nil {
			return rpcError(req.ID, -32603, err.Error())
		}

		return JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result: map[string]any{
				"content": []map[string]any{
					{
						"type": "text",
						"text": toolResultText(result),
					},
				},
			},
		}
	case "ping":
		return JSONRPCResponse{
			JSONRPC: "2.0",
			ID:      req.ID,
			Result:  map[string]any{},
		}
	default:
		return rpcError(req.ID, -32601, "method not found")
	}
}

// toolResultText serializes tool output into MCP text content.
// Parameters: result is the Go value returned by a tool function.
func toolResultText(result any) string {
	if text, ok := result.(string); ok {
		return text
	}
	data, err := json.Marshal(result)
	if err != nil {
		return fmt.Sprint(result)
	}
	return string(data)
}

// callTool unmarshals JSON arguments, invokes the registered tool function, and returns its result.
// Parameters: tool is the registered MCP tool; rawArgs is the JSON object passed as tool arguments.
func callTool(tool Tool, rawArgs json.RawMessage) (any, error) {
	fnValue := reflect.ValueOf(tool.Func)
	fnType := fnValue.Type()
	if fnType.NumIn() != 1 {
		return nil, fmt.Errorf("tool must accept exactly one argument")
	}

	argType := fnType.In(0)
	argPtr := reflect.New(argType)
	if err := json.Unmarshal(rawArgs, argPtr.Interface()); err != nil {
		return nil, err
	}

	results := fnValue.Call([]reflect.Value{argPtr.Elem()})
	if len(results) == 2 && !results[1].IsNil() {
		return nil, results[1].Interface().(error)
	}
	if len(results) == 0 {
		return nil, nil
	}
	return results[0].Interface(), nil
}

// rpcError builds a JSON-RPC error response.
// Parameters: id is the request id to echo; code is the JSON-RPC error code; message explains the error.
func rpcError(id any, code int, message string) JSONRPCResponse {
	return JSONRPCResponse{
		JSONRPC: "2.0",
		ID:      id,
		Error: map[string]any{
			"code":    code,
			"message": message,
		},
	}
}

// handler accepts Lambda Function URL POST requests containing JSON-RPC MCP requests.
// Parameters: ctx is the Lambda invocation context; event is the Function URL HTTP event.
func handler(ctx context.Context, event events.LambdaFunctionURLRequest) (events.LambdaFunctionURLResponse, error) {
	if event.RequestContext.HTTP.Method != "" && event.RequestContext.HTTP.Method != http.MethodPost {
		return events.LambdaFunctionURLResponse{
			StatusCode: http.StatusMethodNotAllowed,
			Headers:    jsonHeaders(),
			Body:       `{"error":"method not allowed"}`,
		}, nil
	}

	body, err := requestBody(event)
	if err != nil {
		resp := rpcError(nil, -32700, err.Error())
		return rpcHTTPResponse(http.StatusBadRequest, resp)
	}

	var req JSONRPCRequest
	if err := json.Unmarshal([]byte(body), &req); err != nil {
		resp := rpcError(nil, -32700, "parse error")
		return rpcHTTPResponse(http.StatusBadRequest, resp)
	}

	resp := handleMCP(req)
	return rpcHTTPResponse(http.StatusOK, resp)
}

// requestBody decodes the HTTP event body for JSON-RPC parsing.
// Parameters: event is the Lambda Function URL event to read.
func requestBody(event events.LambdaFunctionURLRequest) (string, error) {
	if !event.IsBase64Encoded {
		return event.Body, nil
	}
	decoded, err := base64.StdEncoding.DecodeString(event.Body)
	if err != nil {
		return "", fmt.Errorf("failed to decode base64 request body")
	}
	return string(decoded), nil
}

// rpcHTTPResponse serializes a JSON-RPC response into a Function URL HTTP response.
// Parameters: statusCode is the HTTP status to return; resp is the JSON-RPC response payload.
func rpcHTTPResponse(statusCode int, resp JSONRPCResponse) (events.LambdaFunctionURLResponse, error) {
	body, err := json.Marshal(resp)
	if err != nil {
		return events.LambdaFunctionURLResponse{}, err
	}
	return events.LambdaFunctionURLResponse{
		StatusCode: statusCode,
		Headers:    jsonHeaders(),
		Body:       string(body),
	}, nil
}

// jsonHeaders returns headers for MCP JSON responses.
// Parameters: none.
func jsonHeaders() map[string]string {
	return map[string]string{
		"Content-Type": "application/json",
		"MCP-Version":  "0.6",
	}
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

// main registers renderer tools and starts the Lambda runtime.
// Parameters: none.
func main() {
	RegisterTool("render_sbgn_png", "Render SBGNML XML to PNG, upload it to S3, and return the image file location.", RenderSBGNPNG)
	lambda.Start(handler)
}
