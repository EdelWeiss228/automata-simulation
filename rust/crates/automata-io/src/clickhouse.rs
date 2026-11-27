//! Minimal ClickHouse HTTP client.
//!
//! The build server cannot rely on crates.io, so this module speaks the
//! ClickHouse HTTP protocol directly.  It only needs a TCP socket and is
//! sufficient for `INSERT ... FORMAT CSV`, `SELECT ... FORMAT TSV` and the
//! `ALTER TABLE ... DELETE` used by resume.

use std::fmt;
use std::io::{self, Read, Write};
use std::net::{TcpStream, ToSocketAddrs};
use std::time::Duration;

use crate::uuid::Uuid;

#[derive(Clone)]
pub struct ClickHouseConfig {
    pub host: String,
    pub port: u16,
    pub database: String,
    pub user: String,
    pub password: String,
    pub timeout: Duration,
}

impl ClickHouseConfig {
    pub fn local() -> Self {
        Self {
            host: "127.0.0.1".to_string(),
            port: 8123,
            database: "default".to_string(),
            user: "default".to_string(),
            password: String::new(),
            timeout: Duration::from_secs(30),
        }
    }

    /// Reads `CLICKHOUSE_*` variables.  The password is never printed.
    pub fn from_env() -> Self {
        let mut config = Self::local();
        if let Ok(value) = std::env::var("CLICKHOUSE_HOST") {
            config.host = value;
        }
        if let Ok(value) = std::env::var("CLICKHOUSE_PORT")
            && let Ok(port) = value.parse()
        {
            config.port = port;
        }
        if let Ok(value) = std::env::var("CLICKHOUSE_DATABASE") {
            config.database = value;
        }
        if let Ok(value) = std::env::var("CLICKHOUSE_USER") {
            config.user = value;
        }
        if let Ok(value) = std::env::var("CLICKHOUSE_PASSWORD") {
            config.password = value;
        }
        if let Ok(value) = std::env::var("CLICKHOUSE_TIMEOUT_MS")
            && let Ok(millis) = value.parse()
        {
            config.timeout = Duration::from_millis(millis);
        }
        config
    }
}

impl fmt::Debug for ClickHouseConfig {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("ClickHouseConfig")
            .field("host", &self.host)
            .field("port", &self.port)
            .field("database", &self.database)
            .field("user", &self.user)
            .field("password", &"<redacted>")
            .field("timeout", &self.timeout)
            .finish()
    }
}

#[derive(Debug)]
pub enum ClickHouseError {
    Io(io::Error),
    Protocol(String),
    Server { status: u16, message: String },
}

impl fmt::Display for ClickHouseError {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Io(error) => write!(formatter, "ClickHouse I/O error: {error}"),
            Self::Protocol(message) => write!(formatter, "ClickHouse protocol error: {message}"),
            Self::Server { status, message } => {
                write!(formatter, "ClickHouse returned HTTP {status}: {message}")
            }
        }
    }
}

impl std::error::Error for ClickHouseError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            Self::Io(error) => Some(error),
            _ => None,
        }
    }
}

impl From<io::Error> for ClickHouseError {
    fn from(error: io::Error) -> Self {
        Self::Io(error)
    }
}

#[derive(Clone, Debug)]
pub struct ClickHouseClient {
    config: ClickHouseConfig,
}

impl ClickHouseClient {
    pub fn new(config: ClickHouseConfig) -> Self {
        Self { config }
    }

    pub fn config(&self) -> &ClickHouseConfig {
        &self.config
    }

    pub fn execute(&self, query: &str) -> Result<String, ClickHouseError> {
        self.request(query)
    }

    pub fn ping(&self) -> Result<(), ClickHouseError> {
        self.execute("SELECT 1 FORMAT TSV").map(|_| ())
    }

    pub fn insert(&self, table: &str, columns: &[&str], data: &str) -> Result<(), ClickHouseError> {
        if data.is_empty() {
            return Ok(());
        }
        let query = format!(
            "INSERT INTO {}.{} ({}) FORMAT CSV\n{}",
            self.config.database,
            table,
            columns.join(", "),
            data
        );
        self.execute(&query).map(|_| ())
    }

    pub fn insert_rows(
        &self,
        table: &str,
        columns: &[&str],
        rows: &[String],
    ) -> Result<(), ClickHouseError> {
        if rows.is_empty() {
            return Ok(());
        }
        let mut data = String::with_capacity(rows.iter().map(String::len).sum::<usize>() + 1);
        for row in rows {
            data.push_str(row);
            if !row.ends_with('\n') {
                data.push('\n');
            }
        }
        self.insert(table, columns, &data)
    }

    pub fn run_exists(&self, run_id: Uuid) -> Result<bool, ClickHouseError> {
        let query = format!(
            "SELECT count() FROM {}.simulation_runs WHERE run_id = '{}' FORMAT TSV",
            self.config.database, run_id
        );
        let response = self.execute(&query)?;
        Ok(response.trim().parse::<u64>().unwrap_or(0) > 0)
    }

    /// Removes a partially written tail so that a resumed day can be replayed
    /// without duplicate rows.
    pub fn delete_days(&self, run_id: Uuid, from_day: u32) -> Result<(), ClickHouseError> {
        for table in ["interactions", "agent_states", "agent_relations"] {
            let query = format!(
                "ALTER TABLE {}.{} DELETE WHERE run_id = '{}' AND day_id >= {} SETTINGS mutations_sync = 1",
                self.config.database, table, run_id, from_day
            );
            self.execute(&query)?;
        }
        Ok(())
    }

    /// Removes the whole registry of a run.  The runner rebuilds it from the
    /// restored population, which keeps the stable `agent_id` assignment and
    /// avoids duplicates after a crash in the middle of a rotation.
    pub fn delete_registry(&self, run_id: Uuid) -> Result<(), ClickHouseError> {
        let query = format!(
            "ALTER TABLE {}.agent_registry DELETE WHERE run_id = '{}' SETTINGS mutations_sync = 1",
            self.config.database, run_id
        );
        self.execute(&query).map(|_| ())
    }

    fn request(&self, body: &str) -> Result<String, ClickHouseError> {
        let mut addresses = (self.config.host.as_str(), self.config.port).to_socket_addrs()?;
        let address = addresses.next().ok_or_else(|| {
            ClickHouseError::Protocol("host resolved to no addresses".to_string())
        })?;
        let mut stream = TcpStream::connect_timeout(&address, self.config.timeout)?;
        stream.set_read_timeout(Some(self.config.timeout))?;
        stream.set_write_timeout(Some(self.config.timeout))?;

        let mut request = format!(
            "POST / HTTP/1.1\r\nHost: {}:{}\r\nContent-Length: {}\r\nConnection: close\r\n",
            self.config.host,
            self.config.port,
            body.len()
        );
        if !self.config.user.is_empty() {
            let credentials = format!("{}:{}", self.config.user, self.config.password);
            request.push_str("Authorization: Basic ");
            request.push_str(&base64(credentials.as_bytes()));
            request.push_str("\r\n");
        }
        request.push_str("\r\n");
        request.push_str(body);

        stream.write_all(request.as_bytes())?;
        stream.flush()?;

        let mut response = Vec::new();
        stream.read_to_end(&mut response)?;
        parse_response(&response)
    }
}

fn parse_response(response: &[u8]) -> Result<String, ClickHouseError> {
    let header_end = find(response, b"\r\n\r\n").ok_or_else(|| {
        ClickHouseError::Protocol("response has no header terminator".to_string())
    })?;
    let header = std::str::from_utf8(&response[..header_end])
        .map_err(|error| ClickHouseError::Protocol(format!("header is not UTF-8: {error}")))?;
    let mut lines = header.split("\r\n");
    let status_line = lines
        .next()
        .ok_or_else(|| ClickHouseError::Protocol("response has no status line".to_string()))?;
    let status: u16 = status_line
        .split_whitespace()
        .nth(1)
        .and_then(|value| value.parse().ok())
        .ok_or_else(|| ClickHouseError::Protocol(format!("invalid status line: {status_line}")))?;

    let mut chunked = false;
    let mut content_length = None;
    for line in lines {
        let Some((name, value)) = line.split_once(':') else {
            continue;
        };
        let name = name.trim().to_ascii_lowercase();
        let value = value.trim();
        if name == "transfer-encoding" && value.eq_ignore_ascii_case("chunked") {
            chunked = true;
        } else if name == "content-length" {
            content_length = value.parse::<usize>().ok();
        }
    }

    let body = &response[header_end + 4..];
    let body = if chunked {
        decode_chunked(body)?
    } else if let Some(length) = content_length {
        body[..length.min(body.len())].to_vec()
    } else {
        body.to_vec()
    };
    let text = String::from_utf8_lossy(&body).into_owned();

    if !(200..300).contains(&status) {
        return Err(ClickHouseError::Server {
            status,
            message: text.chars().take(4_096).collect(),
        });
    }
    Ok(text)
}

fn decode_chunked(mut input: &[u8]) -> Result<Vec<u8>, ClickHouseError> {
    let mut output = Vec::new();
    loop {
        let line_end = find(input, b"\r\n").ok_or_else(|| {
            ClickHouseError::Protocol("chunk header has no terminator".to_string())
        })?;
        let size_text = std::str::from_utf8(&input[..line_end]).map_err(|error| {
            ClickHouseError::Protocol(format!("chunk size is not UTF-8: {error}"))
        })?;
        let size_text = size_text.split(';').next().unwrap_or("").trim();
        let size = usize::from_str_radix(size_text, 16)
            .map_err(|_| ClickHouseError::Protocol(format!("invalid chunk size: {size_text}")))?;
        input = &input[line_end + 2..];
        if size == 0 {
            break;
        }
        if input.len() < size + 2 {
            return Err(ClickHouseError::Protocol(
                "chunk is shorter than its declared size".to_string(),
            ));
        }
        output.extend_from_slice(&input[..size]);
        input = &input[size + 2..];
    }
    Ok(output)
}

fn find(haystack: &[u8], needle: &[u8]) -> Option<usize> {
    haystack
        .windows(needle.len())
        .position(|window| window == needle)
}

fn base64(input: &[u8]) -> String {
    const ALPHABET: &[u8; 64] = b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    let mut output = String::with_capacity(input.len().div_ceil(3) * 4);
    for chunk in input.chunks(3) {
        let first = chunk[0];
        let second = chunk.get(1).copied().unwrap_or(0);
        let third = chunk.get(2).copied().unwrap_or(0);
        output.push(ALPHABET[(first >> 2) as usize] as char);
        output.push(ALPHABET[(((first & 0x03) << 4) | (second >> 4)) as usize] as char);
        if chunk.len() > 1 {
            output.push(ALPHABET[(((second & 0x0F) << 2) | (third >> 6)) as usize] as char);
        } else {
            output.push('=');
        }
        if chunk.len() > 2 {
            output.push(ALPHABET[(third & 0x3F) as usize] as char);
        } else {
            output.push('=');
        }
    }
    output
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base64_matches_the_standard_alphabet() {
        assert_eq!(base64(b""), "");
        assert_eq!(base64(b"f"), "Zg==");
        assert_eq!(base64(b"fo"), "Zm8=");
        assert_eq!(base64(b"foo"), "Zm9v");
        assert_eq!(base64(b"user:pass"), "dXNlcjpwYXNz");
    }

    #[test]
    fn parses_a_plain_response() {
        let response = b"HTTP/1.1 200 OK\r\nContent-Length: 3\r\n\r\n1\n";
        assert_eq!(parse_response(response).unwrap(), "1\n");
    }

    #[test]
    fn parses_a_chunked_response() {
        let response =
            b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n3\r\n1\n2\r\n0\r\n\r\n";
        assert_eq!(parse_response(response).unwrap(), "1\n2");
    }

    #[test]
    fn reports_server_errors() {
        let response = b"HTTP/1.1 500 Internal Server Error\r\nContent-Length: 4\r\n\r\nboom";
        let error = parse_response(response).unwrap_err();
        assert!(matches!(error, ClickHouseError::Server { status: 500, .. }));
        assert!(error.to_string().contains("boom"));
    }

    #[test]
    fn debug_redacts_the_password() {
        let mut config = ClickHouseConfig::local();
        config.password = "secret".to_string();
        let debug = format!("{config:?}");
        assert!(!debug.contains("secret"));
        assert!(debug.contains("redacted"));
    }
}
