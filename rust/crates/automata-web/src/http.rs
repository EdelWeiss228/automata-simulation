//! Small HTTP/1.1 request parser and response writer.
//!
//! The server only needs `GET`, so the parser intentionally ignores bodies
//! and keep-alive semantics: every response closes the connection.

use std::io::{self, Read, Write};
use std::net::TcpStream;
use std::time::Duration;

pub const MAX_REQUEST_BYTES: usize = 16 * 1024;

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Request {
    pub method: String,
    pub path: String,
    pub query: Option<String>,
    pub headers: Vec<(String, String)>,
}

impl Request {
    pub fn header(&self, name: &str) -> Option<&str> {
        self.headers
            .iter()
            .find(|(key, _)| key.eq_ignore_ascii_case(name))
            .map(|(_, value)| value.as_str())
    }

    pub fn query_param(&self, name: &str) -> Option<String> {
        let query = self.query.as_deref()?;
        for pair in query.split('&') {
            let (key, value) = pair.split_once('=').unwrap_or((pair, ""));
            if percent_decode(key) == name {
                return Some(percent_decode(value));
            }
        }
        None
    }
}

#[derive(Debug)]
pub struct Response {
    pub status: u16,
    pub content_type: &'static str,
    pub body: Vec<u8>,
    pub headers: Vec<(String, String)>,
}

impl Response {
    pub fn new(status: u16, content_type: &'static str, body: impl Into<Vec<u8>>) -> Self {
        Self {
            status,
            content_type,
            body: body.into(),
            headers: Vec::new(),
        }
    }

    pub fn json(status: u16, body: String) -> Self {
        Self::new(status, "application/json; charset=utf-8", body)
    }

    pub fn text(status: u16, body: impl Into<String>) -> Self {
        Self::new(status, "text/plain; charset=utf-8", body.into())
    }

    pub fn with_header(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.headers.push((name.into(), value.into()));
        self
    }

    pub fn write_to(&self, stream: &mut TcpStream) -> io::Result<()> {
        write!(
            stream,
            "HTTP/1.1 {} {}\r\n",
            self.status,
            reason_phrase(self.status)
        )?;
        write!(stream, "Content-Type: {}\r\n", self.content_type)?;
        write!(stream, "Content-Length: {}\r\n", self.body.len())?;
        write!(stream, "Connection: close\r\n")?;
        write!(stream, "Cache-Control: no-store\r\n")?;
        write!(stream, "X-Content-Type-Options: nosniff\r\n")?;
        for (name, value) in &self.headers {
            write!(stream, "{name}: {value}\r\n")?;
        }
        write!(stream, "\r\n")?;
        stream.write_all(&self.body)?;
        stream.flush()
    }
}

pub fn read_request(stream: &mut TcpStream) -> Result<Request, String> {
    stream
        .set_read_timeout(Some(Duration::from_secs(10)))
        .map_err(|error| error.to_string())?;
    let mut buffer = Vec::new();
    let mut chunk = [0_u8; 1024];
    loop {
        let read = stream.read(&mut chunk).map_err(|error| error.to_string())?;
        if read == 0 {
            return Err("connection closed before the request head".to_string());
        }
        buffer.extend_from_slice(&chunk[..read]);
        if buffer.windows(4).any(|window| window == b"\r\n\r\n") {
            break;
        }
        if buffer.len() > MAX_REQUEST_BYTES {
            return Err("request head is too large".to_string());
        }
    }
    parse_request(&buffer)
}

pub fn parse_request(bytes: &[u8]) -> Result<Request, String> {
    let text = std::str::from_utf8(bytes).map_err(|_| "request is not UTF-8".to_string())?;
    let head = text
        .split_once("\r\n\r\n")
        .map(|(head, _)| head)
        .unwrap_or(text);
    let mut lines = head.split("\r\n");
    let request_line = lines.next().ok_or_else(|| "empty request".to_string())?;
    let mut parts = request_line.split_whitespace();
    let method = parts
        .next()
        .ok_or_else(|| "missing method".to_string())?
        .to_ascii_uppercase();
    let target = parts
        .next()
        .ok_or_else(|| "missing request target".to_string())?;
    let version = parts
        .next()
        .ok_or_else(|| "missing HTTP version".to_string())?;
    if !version.starts_with("HTTP/1.") {
        return Err(format!("unsupported HTTP version {version}"));
    }
    if !target.starts_with('/') {
        return Err("request target must be an absolute path".to_string());
    }

    let (path, query) = match target.split_once('?') {
        Some((path, query)) => (path.to_string(), Some(query.to_string())),
        None => (target.to_string(), None),
    };
    if path.contains("..") {
        return Err("path traversal is not allowed".to_string());
    }

    let mut headers = Vec::new();
    for line in lines {
        if line.is_empty() {
            continue;
        }
        let (name, value) = line
            .split_once(':')
            .ok_or_else(|| format!("malformed header line: {line}"))?;
        headers.push((name.trim().to_ascii_lowercase(), value.trim().to_string()));
    }

    Ok(Request {
        method,
        path,
        query,
        headers,
    })
}

pub fn percent_decode(value: &str) -> String {
    let bytes = value.as_bytes();
    let mut output = Vec::with_capacity(bytes.len());
    let mut index = 0;
    while index < bytes.len() {
        if bytes[index] == b'%' && index + 2 < bytes.len() {
            let high = hex_value(bytes[index + 1]);
            let low = hex_value(bytes[index + 2]);
            if let (Some(high), Some(low)) = (high, low) {
                output.push(high * 16 + low);
                index += 3;
                continue;
            }
        }
        output.push(bytes[index]);
        index += 1;
    }
    String::from_utf8_lossy(&output).into_owned()
}

fn hex_value(byte: u8) -> Option<u8> {
    match byte {
        b'0'..=b'9' => Some(byte - b'0'),
        b'a'..=b'f' => Some(byte - b'a' + 10),
        b'A'..=b'F' => Some(byte - b'A' + 10),
        _ => None,
    }
}

fn reason_phrase(status: u16) -> &'static str {
    match status {
        200 => "OK",
        400 => "Bad Request",
        401 => "Unauthorized",
        404 => "Not Found",
        405 => "Method Not Allowed",
        500 => "Internal Server Error",
        501 => "Not Implemented",
        _ => "Unknown",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_a_get_request_with_headers() {
        let request = parse_request(
            b"GET /api/runs?token=abc HTTP/1.1\r\nHost: localhost\r\nAuthorization: Bearer x\r\n\r\n",
        )
        .expect("request");
        assert_eq!(request.method, "GET");
        assert_eq!(request.path, "/api/runs");
        assert_eq!(request.query_param("token").as_deref(), Some("abc"));
        assert_eq!(request.header("authorization"), Some("Bearer x"));
    }

    #[test]
    fn rejects_traversal_and_non_http_versions() {
        assert!(parse_request(b"GET /../etc/passwd HTTP/1.1\r\n\r\n").is_err());
        assert!(parse_request(b"GET / HTTP/2.0\r\n\r\n").is_err());
        assert!(parse_request(b"GET relative HTTP/1.1\r\n\r\n").is_err());
    }

    #[test]
    fn decodes_percent_encoded_query_values() {
        let request = parse_request(b"GET /?token=a%20b HTTP/1.1\r\n\r\n").expect("request");
        assert_eq!(request.query_param("token").as_deref(), Some("a b"));
    }
}
