use std::collections::HashMap;
use std::env;
use std::error::Error;
use std::fs;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::process::Command;

use base64::engine::general_purpose::STANDARD;
use base64::Engine as _;
use serde::{Deserialize, Serialize};

const CLI_PATH: &str = "/var/task/render_sbgn_rs";
const INPUT_PATH: &str = "/tmp/input.sbgn";
const OUTPUT_PNG: &str = "/tmp/output.png";

type AppResult<T> = Result<T, Box<dyn Error + Send + Sync>>;

#[derive(Deserialize)]
struct RenderEvent {
    xml: String,
}

#[derive(Serialize)]
struct RenderResponse {
    png_base64: String,
}

#[derive(Deserialize)]
struct FunctionUrlRequest {
    body: Option<String>,
    #[serde(default, rename = "isBase64Encoded")]
    is_base64_encoded: bool,
    #[serde(default, rename = "requestContext")]
    request_context: Option<RequestContext>,
}

#[derive(Deserialize)]
struct RequestContext {
    http: Option<HttpContext>,
}

#[derive(Deserialize)]
struct HttpContext {
    method: Option<String>,
}

#[derive(Serialize)]
struct FunctionUrlResponse {
    #[serde(rename = "statusCode")]
    status_code: u16,
    headers: HashMap<String, String>,
    body: String,
    #[serde(rename = "isBase64Encoded")]
    is_base64_encoded: bool,
}

#[derive(Serialize)]
struct ErrorBody {
    error: String,
}

struct Invocation {
    request_id: String,
    body: Vec<u8>,
}

struct HttpResponse {
    status_code: u16,
    headers: HashMap<String, String>,
    body: Vec<u8>,
}

fn main() -> AppResult<()> {
    let runtime_api = env::var("AWS_LAMBDA_RUNTIME_API")
        .map_err(|_| "AWS_LAMBDA_RUNTIME_API is not set; this binary must run in Lambda")?;

    loop {
        let invocation = runtime_next(&runtime_api)?;
        let response = match handle_invocation(&invocation.body) {
            Ok(response) => response,
            Err(err) => json_response(
                500,
                &ErrorBody {
                    error: err.to_string(),
                },
            )?,
        };
        runtime_response(&runtime_api, &invocation.request_id, &response)?;
    }
}

fn handle_invocation(body: &[u8]) -> AppResult<FunctionUrlResponse> {
    if let Ok(event) = serde_json::from_slice::<RenderEvent>(body) {
        let response = render_event(event)?;
        return json_response(200, &response);
    }

    let request: FunctionUrlRequest = serde_json::from_slice(body)?;
    if let Some(method) = request_method(&request) {
        if method != "POST" {
            return json_response(
                405,
                &ErrorBody {
                    error: format!("method {method} is not allowed"),
                },
            );
        }
    }

    let event = parse_function_url_body(request)?;
    let response = render_event(event)?;
    json_response(200, &response)
}

fn request_method(request: &FunctionUrlRequest) -> Option<&str> {
    request
        .request_context
        .as_ref()
        .and_then(|context| context.http.as_ref())
        .and_then(|http| http.method.as_deref())
}

fn parse_function_url_body(request: FunctionUrlRequest) -> AppResult<RenderEvent> {
    let mut body = request.body.unwrap_or_default();
    if request.is_base64_encoded {
        body = String::from_utf8(STANDARD.decode(body)?)?;
    }

    if body.trim().is_empty() {
        return Err("request body is empty".into());
    }

    let event: RenderEvent = serde_json::from_str(&body)?;
    if event.xml.trim().is_empty() {
        return Err("xml is required".into());
    }

    Ok(event)
}

fn render_event(event: RenderEvent) -> AppResult<RenderResponse> {
    fs::write(INPUT_PATH, event.xml)?;
    let _ = fs::remove_file(OUTPUT_PNG);

    let output = Command::new(CLI_PATH)
        .args([
            "draw_sbgnml",
            "--input-path",
            INPUT_PATH,
            "--output-path",
            OUTPUT_PNG,
        ])
        .output()?;

    if !output.status.success() {
        return Err(format!(
            "renderer failed with status {:?}\nstdout:\n{}\nstderr:\n{}",
            output.status.code(),
            String::from_utf8_lossy(&output.stdout),
            String::from_utf8_lossy(&output.stderr)
        )
        .into());
    }

    let png = fs::read(OUTPUT_PNG)?;
    Ok(RenderResponse {
        png_base64: STANDARD.encode(png),
    })
}

fn json_response<T: Serialize>(status_code: u16, payload: &T) -> AppResult<FunctionUrlResponse> {
    let mut headers = HashMap::new();
    headers.insert(
        String::from("content-type"),
        String::from("application/json"),
    );

    Ok(FunctionUrlResponse {
        status_code,
        headers,
        body: serde_json::to_string(payload)?,
        is_base64_encoded: false,
    })
}

fn runtime_next(runtime_api: &str) -> AppResult<Invocation> {
    let response = http_request(
        runtime_api,
        "GET",
        "/2018-06-01/runtime/invocation/next",
        &[],
        &[],
    )?;
    if response.status_code != 200 {
        return Err(format!("runtime next returned HTTP {}", response.status_code).into());
    }

    let request_id = response
        .headers
        .get("lambda-runtime-aws-request-id")
        .cloned()
        .ok_or("runtime next response did not include a request id")?;

    Ok(Invocation {
        request_id,
        body: response.body,
    })
}

fn runtime_response(
    runtime_api: &str,
    request_id: &str,
    response: &FunctionUrlResponse,
) -> AppResult<()> {
    let body = serde_json::to_vec(response)?;
    let path = format!("/2018-06-01/runtime/invocation/{request_id}/response");
    let response = http_request(
        runtime_api,
        "POST",
        &path,
        &[("content-type", "application/json")],
        &body,
    )?;
    if !(200..300).contains(&response.status_code) {
        return Err(format!(
            "runtime response returned HTTP {}: {}",
            response.status_code,
            String::from_utf8_lossy(&response.body)
        )
        .into());
    }
    Ok(())
}

fn http_request(
    runtime_api: &str,
    method: &str,
    path: &str,
    headers: &[(&str, &str)],
    body: &[u8],
) -> AppResult<HttpResponse> {
    let mut stream = TcpStream::connect(runtime_api)?;
    write!(
        stream,
        "{method} {path} HTTP/1.1\r\nHost: {runtime_api}\r\nConnection: close\r\nContent-Length: {}\r\n",
        body.len()
    )?;
    for (name, value) in headers {
        write!(stream, "{name}: {value}\r\n")?;
    }
    stream.write_all(b"\r\n")?;
    stream.write_all(body)?;

    let mut raw = Vec::new();
    stream.read_to_end(&mut raw)?;
    parse_http_response(&raw)
}

fn parse_http_response(raw: &[u8]) -> AppResult<HttpResponse> {
    let header_end = raw
        .windows(4)
        .position(|window| window == b"\r\n\r\n")
        .ok_or("HTTP response did not contain a header terminator")?;
    let header_bytes = &raw[..header_end];
    let body_bytes = &raw[header_end + 4..];
    let header_text = std::str::from_utf8(header_bytes)?;
    let mut lines = header_text.split("\r\n");
    let status_line = lines
        .next()
        .ok_or("HTTP response did not contain a status")?;
    let status_code = status_line
        .split_whitespace()
        .nth(1)
        .ok_or("HTTP response status did not contain a code")?
        .parse::<u16>()?;

    let mut headers = HashMap::new();
    for line in lines {
        if let Some((name, value)) = line.split_once(':') {
            headers.insert(name.trim().to_ascii_lowercase(), value.trim().to_string());
        }
    }

    let body = if headers
        .get("transfer-encoding")
        .is_some_and(|value| value.eq_ignore_ascii_case("chunked"))
    {
        decode_chunked_body(body_bytes)?
    } else {
        body_bytes.to_vec()
    };

    Ok(HttpResponse {
        status_code,
        headers,
        body,
    })
}

fn decode_chunked_body(mut bytes: &[u8]) -> AppResult<Vec<u8>> {
    let mut decoded = Vec::new();
    loop {
        let line_end = bytes
            .windows(2)
            .position(|window| window == b"\r\n")
            .ok_or("chunked body is missing a chunk size terminator")?;
        let size_text = std::str::from_utf8(&bytes[..line_end])?;
        let size_hex = size_text.split(';').next().unwrap_or("").trim();
        let size = usize::from_str_radix(size_hex, 16)?;
        bytes = &bytes[line_end + 2..];
        if size == 0 {
            break;
        }
        if bytes.len() < size + 2 {
            return Err("chunked body ended before the declared chunk size".into());
        }
        decoded.extend_from_slice(&bytes[..size]);
        bytes = &bytes[size + 2..];
    }
    Ok(decoded)
}
